"""Windows-only: keep console windows of child processes hidden.

The desktop entry point runs through ``pythonw.exe`` (no console). Every console
child process spawned without ``CREATE_NO_WINDOW`` then gets a fresh console
window of its own. Most call sites in this project pass the flag explicitly, but
third-party code (pydub when exporting ASR chunks, media probing, yt-dlp helpers)
cannot be fixed at the call site, so ffmpeg windows used to flash during
transcription and synthesis.

Patching ``subprocess.Popen.__init__`` once at package import covers every child
process, including future and third-party spawns. It only takes effect when the
current process has no console, so CLI usage in a terminal keeps its inherited
console behaviour.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
from typing import Any

_IS_WINDOWS = os.name == "nt"

_CREATE_NO_WINDOW = 0x08000000
# The child already received an explicit console mode: leave it untouched.
_EXPLICIT_CONSOLE_FLAGS = (
    _CREATE_NO_WINDOW
    | getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)
    | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
)
# Popen.__init__ positional slots after ``self`` up to and including creationflags.
_CREATIONFLAGS_POSITION = 14


def _parent_has_console() -> bool:
    """True when this process owns a console; children inherit it and need no patch."""
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return True
    try:
        return bool(windll.kernel32.GetConsoleWindow())
    except Exception:
        return True


def hide_child_console_windows() -> bool:
    """Default all child processes to ``CREATE_NO_WINDOW`` on Windows.

    Only active on Windows, and only when the current process has no console.
    Idempotent; returns True when this call installed the patch.
    """
    if not _IS_WINDOWS or _parent_has_console():
        return False

    popen = subprocess.Popen
    if getattr(popen, "_hides_child_console_windows", False):
        return False

    original_init = popen.__init__

    def _init_with_hidden_console(self: Any, *args: Any, **kwargs: Any) -> None:
        if len(args) >= _CREATIONFLAGS_POSITION:
            # creationflags was passed positionally: injecting a keyword would duplicate it.
            original_init(self, *args, **kwargs)
            return
        flags = kwargs.get("creationflags") or 0
        if not flags & _EXPLICIT_CONSOLE_FLAGS:
            kwargs["creationflags"] = flags | _CREATE_NO_WINDOW
        original_init(self, *args, **kwargs)

    setattr(popen, "__init__", _init_with_hidden_console)
    setattr(popen, "_hides_child_console_windows", True)
    return True
