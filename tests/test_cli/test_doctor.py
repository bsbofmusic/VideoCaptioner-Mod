"""Focused tests for doctor dependency resolution."""

import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType

import pytest

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli.commands import doctor
from videocaptioner.cli.config import DEFAULTS
from videocaptioner.cli.main import main


def _set_bundled_bin(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    runtime_config = ModuleType("videocaptioner.config")
    setattr(runtime_config, "BUNDLED_BIN_PATH", path)
    monkeypatch.setitem(sys.modules, "videocaptioner.config", runtime_config)


def test_check_command_prefers_path_executable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundled_bin = tmp_path / "bundled"
    bundled_bin.mkdir()
    (bundled_bin / "ffmpeg").touch()
    path_executable = tmp_path / "path" / "ffmpeg"
    _set_bundled_bin(monkeypatch, bundled_bin)
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: str(path_executable))
    monkeypatch.setattr(doctor, "_command_version", lambda _path: "")

    check = doctor._check_command("ffmpeg", "purpose")

    assert check.status == "ok"
    assert check.message == str(path_executable)


def test_check_command_falls_back_to_bundled_extensionless_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundled_bin = tmp_path / "bundled"
    bundled_bin.mkdir()
    bundled_executable = bundled_bin / "ffmpeg"
    bundled_executable.touch()
    _set_bundled_bin(monkeypatch, bundled_bin)
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)
    monkeypatch.setattr(doctor, "_command_version", lambda _path: "")

    check = doctor._check_command("ffmpeg", "purpose")

    assert check.status == "ok"
    assert check.message == str(bundled_executable)


def test_check_command_falls_back_to_bundled_exe_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundled_bin = tmp_path / "bundled"
    bundled_bin.mkdir()
    bundled_executable = bundled_bin / "ffmpeg.exe"
    bundled_executable.touch()
    _set_bundled_bin(monkeypatch, bundled_bin)
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)
    monkeypatch.setattr(doctor, "_command_version", lambda _path: "")

    check = doctor._check_command("ffmpeg", "purpose")

    assert check.status == "ok"
    assert check.message == str(bundled_executable)


def test_check_command_preserves_missing_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundled_bin = tmp_path / "bundled"
    bundled_bin.mkdir()
    _set_bundled_bin(monkeypatch, bundled_bin)
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)

    check = doctor._check_command("ffmpeg", "Required for media processing.")

    assert check == doctor.Check(
        "ffmpeg",
        "error",
        "ffmpeg not found. Required for media processing.",
        "Install ffmpeg and make sure it is on PATH",
    )


def test_check_command_probes_resolved_executable_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path_executable = tmp_path / "path" / "ffmpeg"
    probed: list[str] = []
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: str(path_executable))

    def fake_version(path: str) -> str:
        probed.append(path)
        return "ffmpeg test version"

    monkeypatch.setattr(doctor, "_command_version", fake_version)

    check = doctor._check_command("ffmpeg", "purpose")

    assert probed == [str(path_executable)]
    assert "ffmpeg test version" in check.message


def test_doctor_json_succeeds_with_bundled_media_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundled_bin = tmp_path / "bundled"
    bundled_bin.mkdir()
    for name in ("ffmpeg", "ffprobe"):
        (bundled_bin / name).touch()
    _set_bundled_bin(monkeypatch, bundled_bin)
    monkeypatch.setattr(
        doctor.shutil,
        "which",
        lambda name: "/usr/bin/yt-dlp" if name == "yt-dlp" else None,
    )
    monkeypatch.setattr(doctor, "_command_version", lambda _path: "test version")
    monkeypatch.setattr(
        "videocaptioner.cli.main._load_config",
        lambda _args: deepcopy(DEFAULTS),
    )

    result = main(["doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert result == EXIT.SUCCESS
    media_checks = {check["name"]: check for check in payload["checks"] if check["name"] in {"ffmpeg", "ffprobe"}}
    assert media_checks["ffmpeg"]["status"] == "ok"
    assert media_checks["ffprobe"]["status"] == "ok"
