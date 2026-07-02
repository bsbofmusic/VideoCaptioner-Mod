"""Path helpers for Windows-safe user-derived file names."""

from __future__ import annotations

import os
import re
from pathlib import Path

WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def sanitize_path_component(
    name: str,
    replacement: str = "_",
    default: str = "untitled",
    max_length: int = 180,
) -> str:
    """Return a Windows-safe single path component."""
    forbidden_chars = r'<>:"/\\|?*'
    sanitized = re.sub(f"[{re.escape(forbidden_chars)}]", replacement, str(name))
    sanitized = re.sub(r"[\0-\31]", "", sanitized)
    sanitized = sanitized.strip(" .")

    if max_length > 0 and len(sanitized) > max_length:
        base, ext = os.path.splitext(sanitized)
        base_max_length = max(max_length - len(ext), 1)
        sanitized = (base[:base_max_length] + ext).strip(" .")

    if not sanitized:
        sanitized = default

    name_without_ext = os.path.splitext(sanitized)[0].upper()
    if name_without_ext in WINDOWS_RESERVED_NAMES:
        sanitized = f"{sanitized}_"

    return sanitized


def safe_stem(path: str | Path, default: str = "untitled") -> str:
    """Return a sanitized stem for a user-provided path."""
    return sanitize_path_component(Path(path).stem, default=default)
