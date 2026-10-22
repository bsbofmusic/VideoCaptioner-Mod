"""Tests for the Windows child-console hiding patch."""

import importlib
import inspect
import subprocess
from typing import Any

import pytest

import videocaptioner
from videocaptioner import _win_console

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_CONSOLE = 0x00000010


def _install_fake_popen(monkeypatch: pytest.MonkeyPatch) -> type:
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


def test_package_import_installs_the_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Removing the call from videocaptioner/__init__.py must fail a test."""
    calls: list[bool] = []

    def fake_hide_child_console_windows() -> bool:
        calls.append(True)
        return True

    monkeypatch.setattr(
        _win_console, "hide_child_console_windows", fake_hide_child_console_windows
    )
    importlib.reload(videocaptioner)

    assert calls == [True]


def test_creationflags_position_matches_popen_signature() -> None:
    parameters = list(inspect.signature(subprocess.Popen.__init__).parameters)
    # _CREATIONFLAGS_POSITION counts positional slots after ``self`` through creationflags.
    assert parameters.index("creationflags") == _win_console._CREATIONFLAGS_POSITION


class _FakeKernel32:
    def __init__(self, handle: int = 0) -> None:
        self.handle = handle

    def GetConsoleWindow(self) -> int:
        if self.handle < 0:
            raise OSError("no console")
        return self.handle


class _FakeWindll:
    def __init__(self, kernel32: _FakeKernel32) -> None:
        self.kernel32 = kernel32


def _install_fake_windll(monkeypatch: pytest.MonkeyPatch, kernel32: _FakeKernel32) -> None:
    monkeypatch.setattr(_win_console.ctypes, "windll", _FakeWindll(kernel32), raising=False)


def test_parent_has_console_detects_window_handle(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_windll(monkeypatch, _FakeKernel32(0))
    assert _win_console._parent_has_console() is False

    _install_fake_windll(monkeypatch, _FakeKernel32(42))
    assert _win_console._parent_has_console() is True


def test_parent_has_console_fails_safe_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_windll(monkeypatch, _FakeKernel32(-1))
    assert _win_console._parent_has_console() is True


def test_parent_has_console_fails_safe_without_windll(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(_win_console.ctypes, "windll", raising=False)
    assert _win_console._parent_has_console() is True
