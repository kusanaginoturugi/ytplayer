from __future__ import annotations

import curses
import os
import unicodedata
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from .artwork import Artwork
from .downloader import MUSIC_DIR, download_audio
from .history import History
from .models import Chapter, Track
from .player import Player
from .youtube import details, search


DATA_DIR = Path(os.environ.get(
    "YTPLAYER_DATA_DIR",
    Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "ytplayer",
))
CTRL_P = 16
CTRL_N = 14
CTRL_A = 1
CTRL_B = 2
CTRL_D = 4
CTRL_E = 5
CTRL_F = 6
CTRL_K = 11
CTRL_U = 21


class App:
    def __init__(self, screen: curses.window) -> None:
        self.screen = screen
        self.history = History(DATA_DIR / "history.sqlite3")
        self.player = Player()
        self.artwork = Artwork()
        self.current: Track | None = None
        self.queued: tuple[Track, tuple[str, str] | None] | None = None
        self.queue_future: Future[Track] | None = None
        self.queue_enqueued = False
        self.queue_is_suggestion = False
        self.suggestion_future: Future[Track | None] | None = None
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ytplayer")
        self.retry: tuple[list[Track], str, tuple[str, str] | None, bool] | None = None
        self.status = "s: 検索 / m: メタデータから次曲 / q: 終了"
        curses.curs_set(0)
        self.screen.timeout(250)  # poll mpv while still accepting keyboard input

    def run(self) -> None:
        try:
            while True:
                self.draw()
                key = self.screen.getch()
                self.poll_queue()
                self.advance_if_finished()
                if key == -1:
                    continue
                if key == ord("q"):
                    return
                if key == ord("s"):
                    self.search_and_play()
                elif key == ord("m") and self.current:
                    self.select_facet()
                elif key == ord("n"):
                    self.skip_to_next()
                elif key == ord("p"):
                    self.player.toggle_pause()
                    self.status = "一時停止 / 再開を切り替えた"
                elif key == ord("r"):
                    self.retry_selection()
                elif key == ord("f"):
                    self.toggle_favorite()
                elif key == ord("l"):
                    self.open_favorites()
                elif key == ord("c"):
                    self.select_chapter()
        finally:
            self.player.stop()
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.artwork.clear()
            self.history.close()

    def draw(self) -> None:
        self.screen.erase()
        height, width = self.screen.getmaxyx()
        show_artwork = width >= 90 and height >= 16
        artwork_width = width // 3
        # Terminal cells are roughly twice as tall as they are wide, so this
        # preserves a 16:9 thumbnail rather than stretching it vertically.
        artwork_height = min(height - 7, max(10, artwork_width * 9 // 32))
        metadata_width = width - artwork_width - 2 if show_artwork else width - 1
        self._line(0, "ytplayer  |  YouTube metadata radio", curses.A_BOLD)
        if self.current:
            row = self._write_wrapped(2, f"▶ 再生中  {self.current.title}", curses.A_BOLD, metadata_width, height - 3)
            chapter = self.current_chapter()
            if chapter:
                row = self._write_wrapped(
                    row, f"♪ {self._format_time(chapter.start_time)}  {chapter.title}", 0, metadata_width, height - 3,
                )
            if self.history.is_favorite(self.current.id):
                row = self._write_wrapped(row, "★ お気に入り", 0, metadata_width, height - 3)
            row += 1
            for label, value in self.current.facets().items():
                if value:
                    row = self._write_wrapped(row, f"{label}: {value}", 0, metadata_width, height - 3)
        else:
            self._line(2, "曲を検索して始めよう。")
        if self.queued:
            prefix = "次の候補" if self.queue_is_suggestion else "次の予約"
            state = "（準備中）" if self.queue_future and not self.queue_future.done() else ""
            self._line(height - 4, f"{prefix}: {self.queued[0].title}{state}", curses.A_BOLD)
        self._line(height - 2, self.status[:width - 1], curses.A_REVERSE)
        retry_hint = "  r 選び直す" if self.retry else ""
        self._line(height - 1, f"s 検索  m 次曲を選ぶ  n 次曲へ  c チャプタ  f お気に入り  l 一覧  p pause{retry_hint}  q 終了")
        self.screen.refresh()
        # Keep the artwork in a right-hand panel, leaving the metadata readable.
        if self.current and show_artwork:
            self.artwork.show(self.current, artwork_width, artwork_height, width - artwork_width - 1, 2)
        else:
            self.artwork.clear()

    def _line(self, y: int, text: str, style: int = 0, max_width: int | None = None) -> None:
        height, width = self.screen.getmaxyx()
        if 0 <= y < height:
            limit = width - 1 if max_width is None else min(width - 1, max_width)
            self.screen.addstr(y, 0, self._truncate_cells(text, max(0, limit)), style)

    @staticmethod
    def _cell_width(char: str) -> int:
        if unicodedata.combining(char):
            return 0
        return 2 if unicodedata.east_asian_width(char) in "FW" else 1

    @classmethod
    def _truncate_cells(cls, text: str, limit: int) -> str:
        result: list[str] = []
        used = 0
        for char in text:
            char_width = cls._cell_width(char)
            if used + char_width > limit:
                break
            result.append(char)
            used += char_width
        return "".join(result)

    @classmethod
    def _wrap_cells(cls, text: str, limit: int) -> list[str]:
        lines: list[str] = []
        current: list[str] = []
        used = 0
        for char in text:
            if char == "\n":
                lines.append("".join(current))
                current, used = [], 0
                continue
            char_width = cls._cell_width(char)
            if current and used + char_width > limit:
                lines.append("".join(current))
                current, used = [], 0
            current.append(char)
            used += char_width
        lines.append("".join(current))
        return lines

    def _write_wrapped(self, row: int, text: str, style: int, limit: int, bottom: int) -> int:
        for line in self._wrap_cells(text, limit):
            if row >= bottom:
                return row
            self._line(row, line, style, limit)
            row += 1
        return row

    def prompt(self, message: str) -> str:
        height, width = self.screen.getmaxyx()
        curses.curs_set(1)
        self.screen.timeout(-1)  # A search term must wait for Enter, not the mpv poll timer.
        chars: list[str] = []
        cursor = 0
        try:
            while True:
                self.screen.addnstr(height - 2, 0, message, width - 1, curses.A_REVERSE)
                self.screen.clrtoeol()
                value = "".join(chars)
                self.screen.addnstr(height - 1, 0, value, width - 1)
                self.screen.clrtoeol()
                self.screen.move(height - 1, min(width - 1, self._display_width("".join(chars[:cursor]))))
                self.screen.refresh()
                key = self.screen.get_wch()
                if key in ("\n", "\r", curses.KEY_ENTER):
                    return value.strip()
                if key == "\x1b":
                    return ""
                if key in (CTRL_A, chr(CTRL_A)):
                    cursor = 0
                elif key in (CTRL_E, chr(CTRL_E)):
                    cursor = len(chars)
                elif key in (CTRL_B, chr(CTRL_B)):
                    cursor = max(0, cursor - 1)
                elif key in (CTRL_F, chr(CTRL_F)):
                    cursor = min(len(chars), cursor + 1)
                elif key in (CTRL_D, chr(CTRL_D)):
                    if cursor < len(chars):
                        chars.pop(cursor)
                elif key in (CTRL_K, chr(CTRL_K)):
                    del chars[cursor:]
                elif key in (CTRL_U, chr(CTRL_U)):
                    chars.clear()
                    cursor = 0
                elif key in ("\b", "\x7f", curses.KEY_BACKSPACE):
                    if cursor:
                        chars.pop(cursor - 1)
                        cursor -= 1
                elif isinstance(key, str) and key.isprintable():
                    chars.insert(cursor, key)
                    cursor += 1
        finally:
            curses.curs_set(0)
            self.screen.timeout(250)

    @staticmethod
    def _display_width(text: str) -> int:
        return sum(App._cell_width(char) for char in text)

    def search_and_play(self) -> None:
        query = self.prompt("検索語を入力: ")
        if not query:
            return
        self.status = "YouTube を検索中…"
        self.draw()
        try:
            candidates = [track for track in search(query) if track.id not in self.history.recent_video_ids(100)]
            if not candidates:
                self.status = "直近100曲を除く候補が見つからない"
                return
            chosen = self.choose_track(candidates, "再生する曲を選ぶ")
            if chosen:
                queue_after_current = self.current is not None
                self.retry = (candidates, "再生する曲を選び直す", None, queue_after_current)
                if queue_after_current:
                    self.queue_next(chosen, None)
                    self.status = f"次の曲を予約: {chosen.title}"
                else:
                    self.play(chosen)
        except Exception as exc:
            self.status = f"検索失敗: {exc}"

    def select_facet(self) -> None:
        assert self.current
        facets = [(name, value) for name, value in self.current.facets().items() if value]
        if not facets:
            self.status = "選べるメタデータがない"
            return
        self.artwork.clear()
        index = 0
        while True:
            self.screen.erase()
            self._line(0, "次曲の起点を選ぶ（↑↓ / Enter / Esc）", curses.A_BOLD)
            for row, (name, value) in enumerate(facets, 2):
                self._line(row, f"{name}: {value}", curses.A_REVERSE if row - 2 == index else 0)
            self.screen.refresh()
            key = self.screen.getch()
            if key in (27, ord("q")):
                return
            if key in (curses.KEY_UP, CTRL_P):
                index = (index - 1) % len(facets)
            elif key in (curses.KEY_DOWN, CTRL_N):
                index = (index + 1) % len(facets)
            elif key in (curses.KEY_ENTER, 10, 13):
                self.recommend(*facets[index])
                return

    def recommend(self, field: str, value: str) -> None:
        # A phrase works better as a search query than opaque per-field filters.
        query = value if field != "歌詞" else f'"{value[:80]}" music'
        self.status = f"{field} から候補を選別中…"
        self.draw()
        try:
            candidates = search(query)
            recent_ids = self.history.recent_video_ids(100)
            candidates = [track for track in candidates if track.id not in recent_ids]
            if not candidates:
                self.status = "直近100曲を除く候補が見つからない"
                return
            candidates.sort(key=self.history.score, reverse=True)
            chosen = self.choose_track(candidates, "次に予約する曲を選ぶ")
            if chosen:
                self.queue_next(chosen, (field, value))
                self.retry = (candidates, "次に予約する曲を選び直す", (field, value), True)
                self.status = f"次の曲を予約: {chosen.title}（起点: {field}）"
        except Exception as exc:
            self.status = f"候補取得失敗: {exc}"

    def play(self, track: Track, selected: tuple[str, str] | None = None) -> None:
        try:
            track = details(track)
        except Exception:
            pass  # Search metadata is still enough to play when detail extraction fails.
        try:
            self.status = "音声をライブラリへ保存中…"
            self.draw()
            track = replace(track, audio_path=str(download_audio(track)))
        except Exception as exc:
            self.status = f"音声の保存失敗。ストリーミング再生: {exc}"
        self.player.play(track)
        self.current = track
        self.history.record_play(track, selected)
        self.schedule_suggestion(track)
        source = f"（起点: {selected[0]}）" if selected else ""
        saved = "（保存済み）" if track.audio_path else "（ストリーミング）"
        self.status = f"再生開始: {track.title}{source} {saved}"

    @staticmethod
    def prepare(track: Track) -> Track:
        """Fetch enough metadata to play, then make the local audio available."""
        try:
            track = details(track)
        except Exception:
            pass
        return replace(track, audio_path=str(download_audio(track)))

    @staticmethod
    def second_candidate(track: Track, recent_ids: set[str]) -> Track | None:
        candidates = [candidate for candidate in search(track.title) if candidate.id not in recent_ids]
        if not candidates:
            return None
        # The second result is deliberately the provisional choice.  The top
        # result tends to be the same upload, cover, or a low-value duplicate.
        return candidates[1] if len(candidates) > 1 else candidates[0]

    def schedule_suggestion(self, track: Track) -> None:
        """Look up a provisional next track while the current one is playing."""
        self.queued = None
        self.queue_future = None
        self.queue_enqueued = False
        self.queue_is_suggestion = False
        recent_ids = self.history.recent_video_ids(100)
        self.suggestion_future = self.executor.submit(self.second_candidate, track, recent_ids)

    def queue_next(self, track: Track, selected: tuple[str, str] | None, *, suggestion: bool = False) -> None:
        if self.queue_enqueued:
            self.player.discard_next()
        self.queued = (track, selected)
        self.queue_future = self.executor.submit(self.prepare, track)
        self.queue_enqueued = False
        self.queue_is_suggestion = suggestion
        self.suggestion_future = None

    def poll_queue(self) -> None:
        """Promote a finished lookup/download without blocking the TUI."""
        if self.suggestion_future and self.suggestion_future.done():
            future = self.suggestion_future
            self.suggestion_future = None
            try:
                suggestion = future.result()
            except Exception:
                suggestion = None
            if suggestion and not self.queued:
                self.queue_next(suggestion, None, suggestion=True)
                self.status = f"次の候補を準備中: {suggestion.title}"

        if not self.queued or not self.queue_future or not self.queue_future.done():
            return
        try:
            track = self.queue_future.result()
        except Exception as exc:
            self.status = f"次曲の準備に失敗: {exc}"
            self.queued = None
            self.queue_future = None
            return
        selected = self.queued[1]
        self.queued = (track, selected)
        if not self.queue_enqueued and self.player.process and not self.player.finished():
            self.queue_enqueued = self.player.enqueue(track)

    def start_queued_track(self) -> None:
        assert self.queued
        track, selected = self.queued
        self.queued = None
        self.queue_future = None
        self.queue_enqueued = False
        self.queue_is_suggestion = False
        self.player.play(track)
        self.current = track
        self.history.record_play(track, selected)
        self.schedule_suggestion(track)
        self.status = f"再生開始: {track.title}（準備済み）"

    @staticmethod
    def _format_time(seconds: float) -> str:
        minutes, seconds = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"

    def current_chapter(self) -> Chapter | None:
        if not self.current or not self.current.chapters:
            return None
        position = self.player.time_position()
        if position is None:
            return None
        for chapter in reversed(self.current.chapters):
            if position >= chapter.start_time:
                return chapter
        return self.current.chapters[0]

    def select_chapter(self) -> None:
        if not self.current or not self.current.chapters:
            self.status = "この動画にはチャプタ情報がない"
            return
        chapters = self.current.chapters
        active = self.current_chapter()
        index = chapters.index(active) if active else 0
        self.artwork.clear()
        self.screen.timeout(-1)
        try:
            while True:
                self.screen.erase()
                height, _ = self.screen.getmaxyx()
                self._line(0, "チャプタへジャンプ（↑↓ / C-p C-n / Enter / Esc）", curses.A_BOLD)
                visible = max(1, height - 4)
                start = min(max(0, index - visible // 2), max(0, len(chapters) - visible))
                for row, chapter in enumerate(chapters[start:start + visible], 2):
                    actual = start + row - 2
                    self._line(row, f"{self._format_time(chapter.start_time):>8}  {chapter.title}", curses.A_REVERSE if actual == index else 0)
                self._line(height - 1, f"{index + 1}/{len(chapters)}  Esc: キャンセル")
                self.screen.refresh()
                key = self.screen.getch()
                if key in (27, ord("q")):
                    return
                if key in (curses.KEY_UP, CTRL_P):
                    index = (index - 1) % len(chapters)
                elif key in (curses.KEY_DOWN, CTRL_N):
                    index = (index + 1) % len(chapters)
                elif key in (curses.KEY_ENTER, 10, 13):
                    self.player.jump_chapter(index)
                    self.status = f"チャプタへ移動: {chapters[index].title}"
                    return
        finally:
            self.screen.timeout(250)

    def choose_track(self, candidates: list[Track], heading: str) -> Track | None:
        """Let the listener choose from the ranking without leaving the TUI."""
        index = 0
        self.artwork.clear()
        self.screen.timeout(-1)
        try:
            while True:
                self.screen.erase()
                height, _ = self.screen.getmaxyx()
                self._line(0, f"{heading}（↑↓ または C-p/C-n / Enter / Esc）", curses.A_BOLD)
                visible = max(1, height - 4)
                start = min(max(0, index - visible // 2), max(0, len(candidates) - visible))
                for row, track in enumerate(candidates[start:start + visible], 2):
                    actual = start + row - 2
                    artist = track.singer or track.artist or "不明な歌手"
                    genre = f"  [{track.genre}]" if track.genre else ""
                    line = f"{actual + 1:>2}. {track.title} — {artist}{genre}"
                    style = curses.A_REVERSE if actual == index else 0
                    self._line(row, line, style)
                self._line(height - 1, f"{index + 1}/{len(candidates)}  Esc: キャンセル")
                self.screen.refresh()
                key = self.screen.getch()
                if key in (27, ord("q")):
                    self.status = "曲の選択をキャンセルした"
                    return None
                if key in (curses.KEY_UP, CTRL_P):
                    index = (index - 1) % len(candidates)
                elif key in (curses.KEY_DOWN, CTRL_N):
                    index = (index + 1) % len(candidates)
                elif key in (curses.KEY_ENTER, 10, 13):
                    return candidates[index]
        finally:
            self.screen.timeout(250)

    def advance_if_finished(self) -> None:
        if not self.current:
            return
        if self.queued and self.queue_enqueued:
            queued_track, selected = self.queued
            if self.player.current_path() == (queued_track.audio_path or queued_track.url):
                self.current = queued_track
                self.queued = None
                self.queue_future = None
                self.queue_enqueued = False
                self.queue_is_suggestion = False
                self.history.record_play(queued_track, selected)
                self.schedule_suggestion(queued_track)
                self.status = f"再生開始: {queued_track.title}（曲間なし）"
                return
        if not self.player.finished():
            return
        finished_track = self.current
        self.current = None
        if self.queued:
            if self.queue_future and not self.queue_future.done():
                self.status = "次曲を準備中…"
                return
            self.start_queued_track()
        elif self.suggestion_future:
            self.status = "次の候補を検索中…"
        else:
            self.autoplay_from_title(finished_track)

    def autoplay_from_title(self, finished_track: Track) -> None:
        self.status = f"再生終了。{finished_track.title} から次曲を検索中…"
        self.draw()
        try:
            recent_ids = self.history.recent_video_ids(100)
            candidates = [track for track in search(finished_track.title) if track.id not in recent_ids]
            if not candidates:
                self.status = "自動再生: 直近100曲を除く候補が見つからない"
                return
            self.play(candidates[0])
        except Exception as exc:
            self.status = f"自動再生の検索失敗: {exc}"

    def skip_to_next(self) -> None:
        if not self.current:
            self.status = "次へ進める再生中の曲がない"
            return
        if self.queued:
            if self.queue_future and not self.queue_future.done():
                self.status = "次曲を準備中…"
                return
            if self.queue_enqueued:
                self.player.discard_next()
            self.player.stop()
            self.start_queued_track()
            return
        self.autoplay_from_title(self.current)

    def retry_selection(self) -> None:
        if not self.retry:
            self.status = "選び直せる候補がない"
            return
        candidates, heading, selected, is_queue = self.retry
        chosen = self.choose_track(candidates, heading)
        if not chosen:
            return
        if is_queue:
            self.queue_next(chosen, selected)
            self.status = f"次の予約を変更: {chosen.title}"
        else:
            self.play(chosen)

    def toggle_favorite(self) -> None:
        if not self.current:
            self.status = "お気に入りにする再生中の曲がない"
            return
        if self.history.toggle_favorite(self.current):
            self.status = f"★ お気に入りに追加: {self.current.title}"
        else:
            self.status = f"お気に入りから削除: {self.current.title}"

    def open_favorites(self) -> None:
        favorites = self.history.favorites()
        if not favorites:
            self.status = "お気に入りはまだない"
            return
        chosen = self.choose_track(favorites, "お気に入り")
        if chosen:
            self.retry = (favorites, "お気に入りから曲を選び直す", None, False)
            self.play(chosen)


def main() -> None:
    curses.wrapper(lambda screen: App(screen).run())


if __name__ == "__main__":
    main()
