from __future__ import annotations

import os
import shutil
import subprocess

from .models import Track


class Artwork:
    """Place a YouTube thumbnail in kitty's terminal graphics layer."""

    def __init__(self) -> None:
        self.available = bool(os.environ.get("KITTY_WINDOW_ID")) and shutil.which("kitty") is not None
        self.active: tuple[str, str] | None = None

    def show(self, track: Track, width: int, height: int, left: int, top: int) -> None:
        if not self.available or not track.thumbnail:
            return
        place = f"{width}x{height}@{left}x{top}"
        identity = (track.thumbnail, place)
        if identity == self.active:
            return
        self._run([
            "kitty", "+kitten", "icat", "--stdin=no", "--transfer-mode=stream",
            "--image-id=9271", "--place", place, "--scale-up", track.thumbnail,
        ])
        self.active = identity

    def clear(self) -> None:
        if self.available and self.active:
            self._run(["kitty", "+kitten", "icat", "--clear", "--stdin=no"])
        self.active = None

    @staticmethod
    def _run(command: list[str]) -> None:
        try:
            with open("/dev/tty", "wb", buffering=0) as terminal:
                subprocess.run(
                    command, stdin=subprocess.DEVNULL, stdout=terminal, stderr=subprocess.DEVNULL,
                    timeout=10, check=False,
                )
        except (OSError, subprocess.TimeoutExpired):
            pass
