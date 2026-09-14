"""Regression tests for bundled ffmpeg/ffprobe discovery."""

import sys
from pathlib import Path
from types import ModuleType

import pytest

from videocaptioner.cli.commands import doctor


def _set_bundled_bin(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    runtime_config = ModuleType("videocaptioner.config")
    runtime_config.BUNDLED_BIN_PATH = path
    monkeypatch.setitem(sys.modules, "videocaptioner.config", runtime_config)


def test_path_executable_wins_over_bundled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    (bundled / "ffmpeg").touch()
    path_exe = tmp_path / "path" / "ffmpeg"
    _set_bundled_bin(monkeypatch, bundled)
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: str(path_exe))
    assert doctor._resolve_command("ffmpeg") == str(path_exe)


def test_runtime_venv_bin_is_discovered_before_bundled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_bin = tmp_path / "runtime-bin"
    runtime_bin.mkdir()
    runtime_python = runtime_bin / "python"
    runtime_python.touch()
    runtime_ffmpeg = runtime_bin / "ffmpeg"
    runtime_ffmpeg.touch()
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    (bundled / "ffmpeg").touch()
    _set_bundled_bin(monkeypatch, bundled)
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)
    monkeypatch.setattr(doctor.sys, "executable", str(runtime_python))
    assert doctor._resolve_command("ffmpeg") == str(runtime_ffmpeg)


@pytest.mark.parametrize("filename", ["ffmpeg", "ffmpeg.exe", "ffprobe", "ffprobe.exe"])
def test_bundled_media_tool_is_discovered(
    filename: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    executable = bundled / filename
    executable.touch()
    _set_bundled_bin(monkeypatch, bundled)
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)
    logical_name = filename.removesuffix(".exe")
    assert doctor._resolve_command(logical_name) == str(executable)


def test_missing_media_tool_remains_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    _set_bundled_bin(monkeypatch, bundled)
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)
    assert doctor._resolve_command("ffmpeg") is None
