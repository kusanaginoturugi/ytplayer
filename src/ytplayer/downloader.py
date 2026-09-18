from __future__ import annotations

import os
from pathlib import Path

import yt_dlp

from .models import Track
from .youtube import _SilentLogger, options


MUSIC_DIR = Path(os.environ.get(
    "YTPLAYER_MUSIC_DIR",
    Path(os.environ.get("XDG_MUSIC_DIR", Path.home() / "Music")) / "ytplayer",
))


def existing_audio(track: Track, directory: Path = MUSIC_DIR) -> Path | None:
    """Find an earlier download by immutable YouTube video ID, not by title."""
    if not directory.is_dir():
        return None
    marker = f"[{track.id}]"
    for path in directory.iterdir():
        if path.is_file() and marker in path.name and not path.name.endswith(".part"):
            return path
    return None


def download_audio(track: Track, directory: Path = MUSIC_DIR) -> Path:
    existing = existing_audio(track, directory)
    if existing:
        return existing
    directory.mkdir(parents=True, exist_ok=True)
    ydl_options = options()
    ydl_options.pop("extract_flat", None)
    ydl_options.update({
        "format": "bestaudio[ext=m4a]/bestaudio",
        "noplaylist": True,
        "outtmpl": str(directory / "%(title).180B [%(id)s].%(ext)s"),
        "logger": _SilentLogger(),
        "overwrites": False,
    })
    # No postprocessor is used: yt-dlp downloads only the source audio stream,
    # avoiding video data and an unnecessary lossy transcode.
    with yt_dlp.YoutubeDL(ydl_options) as ydl:
        info = ydl.extract_info(track.url, download=True)
        requested = info.get("requested_downloads") or []
        if requested and requested[0].get("filepath"):
            return Path(requested[0]["filepath"])
        filename = Path(ydl.prepare_filename(info))
    if filename.exists():
        return filename
    existing = existing_audio(track, directory)
    if existing:
        return existing
    raise RuntimeError("音声ファイルの保存先を特定できなかった")
