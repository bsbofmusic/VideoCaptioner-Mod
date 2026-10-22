"""Tests for the Windows child-console hiding patch."""

import subprocess
from typing import Any

import pytest

from videocaptioner import _win_console

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_CONSOLE = 0x00000010


def _install_fake_popen(monkeypatch: pytest.MonkeyPatch) -> type:
    """Replace ``subprocess.Popen`` with a class that records its constructor kwargs."""

    class FakePopen:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    return FakePopen


def _simulate_windowless_windows(monkeypatch: pytest.MonkeyPatch) -> type:
    monkeypatch.setattr(_win_console, "_IS_WINDOWS", True)
    monkeypatch.setattr(_win_console, "_parent_has_console", lambda: False)
    return _install_fake_popen(monkeypatch)


def test_patch_adds_create_no_window(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _simulate_windowless_windows(monkeypatch)

    assert _win_console.hide_child_console_windows() is True

    process = fake(["ffmpeg", "-version"])
    assert process.kwargs["creationflags"] & CREATE_NO_WINDOW


def test_patch_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _simulate_windowless_windows(monkeypatch)

    assert _win_console.hide_child_console_windows() is True
    assert _win_console.hide_child_console_windows() is False

    process = fake(["ffprobe"])
    assert process.kwargs["creationflags"] & CREATE_NO_WINDOW


def test_explicit_console_flags_are_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _simulate_windowless_windows(monkeypatch)
    _win_console.hide_child_console_windows()

    process = fake(["ffmpeg"], creationflags=CREATE_NEW_CONSOLE)
    assert process.kwargs["creationflags"] == CREATE_NEW_CONSOLE


def test_positional_creationflags_is_not_duplicated(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _simulate_windowless_windows(monkeypatch)
    _win_console.hide_child_console_windows()

    # Popen(args, bufsize, executable, stdin, stdout, stderr, preexec_fn, close_fds,
    #       shell, cwd, env, universal_newlines, startupinfo, creationflags)
    positional = ["ffmpeg"] + [None] * 12 + [CREATE_NEW_CONSOLE]
    process = fake(*positional)

    assert "creationflags" not in process.kwargs
    assert process.args[13] == CREATE_NEW_CONSOLE


def test_no_patch_when_parent_has_console(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_win_console, "_IS_WINDOWS", True)
    monkeypatch.setattr(_win_console, "_parent_has_console", lambda: True)
    fake = _install_fake_popen(monkeypatch)

    assert _win_console.hide_child_console_windows() is False

    process = fake(["ffmpeg"])
    assert "creationflags" not in process.kwargs


def test_no_patch_on_non_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_win_console, "_IS_WINDOWS", False)
    fake = _install_fake_popen(monkeypatch)

    assert _win_console.hide_child_console_windows() is False

    process = fake(["ffmpeg"])
    assert "creationflags" not in process.kwargs
