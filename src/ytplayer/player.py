from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path

from .models import Track


class Player:
    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.socket_path = Path(f"/tmp/ytplayer-mpv-{os.getpid()}.sock")

    def play(self, track: Track) -> None:
        self.stop()
        self.socket_path.unlink(missing_ok=True)
        command = [
            "mpv", "--no-video", "--force-window=no", "--terminal=no", "--really-quiet",
            f"--input-ipc-server={self.socket_path}", track.url,
        ]
        # Forward the same opt-in authentication setting to mpv's yt-dlp hook.
        browser = os.environ.get("YTPLAYER_COOKIES_FROM_BROWSER")
        cookie_file = os.environ.get("YTPLAYER_COOKIES")
        if browser:
            command.insert(-1, f"--ytdl-raw-options=cookiesfrombrowser={browser}")
        elif cookie_file:
            command.insert(-1, f"--ytdl-raw-options=cookiefile={cookie_file}")
        # mpv must never share stdout/stderr with curses: its stream/caption listing
        # would overwrite the TUI.  Playback state is presented by app.py instead.
        self.process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def toggle_pause(self) -> None:
        self._command(["cycle", "pause"])

    def jump_chapter(self, index: int) -> None:
        self._command(["set_property", "chapter", index])

    def time_position(self) -> float | None:
        response = self._command(["get_property", "time-pos"], response=True)
        if isinstance(response, dict) and isinstance(response.get("data"), (int, float)):
            return float(response["data"])
        return None

    def _command(self, command: list[object], response: bool = False) -> dict[str, object] | None:
        if self.process and self.process.poll() is None:
            try:
                with socket.socket(socket.AF_UNIX) as client:
                    client.settimeout(0.15)
                    client.connect(str(self.socket_path))
                    client.sendall(json.dumps({"command": command}).encode() + b"\n")
                    if response:
                        return json.loads(client.recv(4096).decode())
            except OSError:
                pass  # mpv has not created its IPC socket yet.
            except (json.JSONDecodeError, TimeoutError):
                pass
        return None

    def finished(self) -> bool:
        return self.process is not None and self.process.poll() is not None

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
        self.process = None
        self.socket_path.unlink(missing_ok=True)
