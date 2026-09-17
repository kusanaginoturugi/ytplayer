from __future__ import annotations

import re
import os
from typing import Any

import yt_dlp

from .models import Chapter, Track


class _SilentLogger:
    """yt-dlp reports per-video failures through a logger even with quiet=True."""
    def debug(self, message: str) -> None: pass
    def warning(self, message: str) -> None: pass
    def error(self, message: str) -> None: pass


def options() -> dict[str, object]:
    settings: dict[str, object] = {
        "quiet": True, "no_warnings": True, "ignoreerrors": True, "logger": _SilentLogger(),
        "extract_flat": "discard_in_playlist",
    }
    # This is opt-in.  It uses the locally logged-in browser only; no cookie is copied
    # into the project or the history database.
    browser = os.environ.get("YTPLAYER_COOKIES_FROM_BROWSER")
    if browser:
        name, separator, profile = browser.partition(":")
        settings["cookiesfrombrowser"] = (name, profile or None) if separator else (name,)
    cookie_file = os.environ.get("YTPLAYER_COOKIES")
    if cookie_file:
        settings["cookiefile"] = cookie_file
    return settings


def search(query: str, limit: int = 20) -> list[Track]:
    # ignoreerrors prevents one age-restricted result from aborting the entire search.
    ydl_options = options()
    with yt_dlp.YoutubeDL(ydl_options) as ydl:
        result = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    return [_track(entry) for entry in result.get("entries", []) if entry]


def details(track: Track) -> Track:
    """Fetch full metadata only for the selected video, including chapters."""
    ydl_options = options()
    ydl_options.pop("extract_flat", None)
    with yt_dlp.YoutubeDL(ydl_options) as ydl:
        data = ydl.extract_info(track.url, download=False)
    return _track(data)


def _track(data: dict[str, Any]) -> Track:
    description = data.get("description") or ""
    video_id = str(data.get("id", ""))
    # YouTube metadata is inconsistent; retain the useful fields when present.
    return Track(
        id=video_id, title=data.get("title") or "(untitled)",
        url=data.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}",
        artist=data.get("artist") or data.get("uploader") or "",
        singer=data.get("artist") or data.get("uploader") or "",
        songwriter=data.get("track") and data.get("artist") or data.get("songwriter") or "",
        composer=data.get("composer") or "", genre=", ".join(data.get("categories") or []),
        lyrics=_lyrics(description), duration=data.get("duration"), thumbnail=_thumbnail(data, video_id),
        chapters=tuple(
            Chapter(
                title=chapter.get("title") or "(タイトルなし)",
                start_time=float(chapter.get("start_time") or 0),
                end_time=float(chapter["end_time"]) if chapter.get("end_time") is not None else None,
            )
            for chapter in data.get("chapters") or []
        ),
    )


def _lyrics(description: str) -> str:
    text = re.sub(r"https?://\S+", "", description).strip()
    return re.sub(r"\s+", " ", text)[:240]


def _thumbnail(data: dict[str, Any], video_id: str) -> str:
    if data.get("thumbnail"):
        return str(data["thumbnail"])
    thumbnails = data.get("thumbnails") or []
    if thumbnails:
        return str(thumbnails[-1].get("url") or "")
    # Flat yt-dlp search results occasionally omit thumbnails.  YouTube publishes
    # this stable fallback for ordinary video IDs, without an extra API request.
    if re.fullmatch(r"[\w-]{11}", video_id):
        return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    return ""
