"""Output backends: clipboard (wl-copy), keystroke synthesis (wtype/ydotool), KDE notify.

Missing tools surface as `RuntimeError` for primary backends (clipboard, type)
so the daemon can log them. `notify` is best-effort and silently no-ops if
`notify-send` isn't installed.
"""
from __future__ import annotations

import shutil
import subprocess


def to_clipboard(text: str) -> None:
    try:
        subprocess.run(["wl-copy"], input=text.encode(), check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("wl-copy not found (install wl-clipboard)") from exc


def type_text(text: str) -> None:
    if shutil.which("wtype"):
        subprocess.run(["wtype", "--", text], check=True)
    elif shutil.which("ydotool"):
        subprocess.run(["ydotool", "type", "--", text], check=True)
    else:
        raise RuntimeError("neither wtype nor ydotool found in PATH")


def notify(title: str, body: str = "", icon: str = "audio-input-microphone") -> None:
    try:
        subprocess.run(
            ["notify-send", "--app-name=flm-voice", "--icon", icon, title, body],
            check=False,
        )
    except FileNotFoundError:
        pass
