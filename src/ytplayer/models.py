from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chapter:
    title: str
    start_time: float
    end_time: float | None = None


@dataclass(frozen=True)
class Track:
    id: str
    title: str
    url: str
    artist: str = ""
    singer: str = ""
    songwriter: str = ""
    composer: str = ""
    genre: str = ""
    lyrics: str = ""
    duration: int | None = None
    thumbnail: str = ""
    chapters: tuple[Chapter, ...] = ()
    audio_path: str = ""

    def facets(self) -> dict[str, str]:
        return {
            "タイトル": self.title,
            "歌手": self.singer or self.artist,
            "作詞": self.songwriter,
            "作曲": self.composer,
            "ジャンル": self.genre,
            "歌詞": self.lyrics,
        }
