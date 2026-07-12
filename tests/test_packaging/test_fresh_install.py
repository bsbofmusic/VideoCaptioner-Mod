"""Fresh virtual-environment smoke tests for built wheel dependency layers."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

OPTIONAL_MODULES = ["PyQt5", "qfluentwidgets", "modelscope", "psutil", "GPUtil", "edge_tts"]


def _wheel_path() -> Path:
    value = os.environ.get("VIDEOCAPTIONER_TEST_WHEEL")
    if not value:
        pytest.skip("set VIDEOCAPTIONER_TEST_WHEEL to a built wheel to run fresh-install smoke")
    wheel = Path(value).resolve()
    assert wheel.is_file(), f"wheel not found: {wheel}"
    return wheel


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _venv_script(venv: Path, name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return venv / ("Scripts" if os.name == "nt" else "bin") / f"{name}{suffix}"


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _install_fresh(tmp_path: Path, requirement: str, name: str) -> Path:
    uv = shutil.which("uv")
    if not uv:
        pytest.skip("uv is required for isolated wheel smoke tests")
    venv = tmp_path / name
    env = _clean_env()
    subprocess.run(
        [uv, "venv", "--python", sys.executable, str(venv)],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [uv, "pip", "install", "--python", str(_venv_python(venv)), requirement],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )
    return venv


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=_clean_env(), capture_output=True, text=True)


def test_core_only_wheel_has_no_optional_modules_and_core_cli_works(tmp_path: Path) -> None:
    wheel = _wheel_path()
    venv = _install_fresh(tmp_path, str(wheel), "core")
    python = _venv_python(venv)
    cli = _venv_script(venv, "videocaptioner")
    gui_cli = _venv_script(venv, "videocaptioner-gui")

    probe = _run(
        [
            str(python),
            "-c",
            (
                "import importlib.util, json; "
                f"mods={OPTIONAL_MODULES!r}; "
                "print(json.dumps({m: importlib.util.find_spec(m) is not None for m in mods}))"
            ),
        ],
        cwd=venv,
    )
    assert probe.returncode == 0, probe.stderr
    assert json.loads(probe.stdout) == {module: False for module in OPTIONAL_MODULES}

    for args in (["--version"], ["--help"], ["transcribe", "--help"]):
        result = _run([str(cli), *args], cwd=venv)
        assert result.returncode == 0, result.stderr
        assert "Traceback" not in result.stderr

    for command in ([str(cli)], [str(cli), "gui"], [str(gui_cli)]):
        result = _run(command, cwd=venv)
        combined = result.stdout + result.stderr
        assert result.returncode == 4, combined
        assert "pip install 'videocaptioner[gui]'" in combined
        assert "Traceback" not in combined


def test_all_extra_wheel_imports_gui_and_dubbing_and_builds_cli_parser(tmp_path: Path) -> None:
    wheel = _wheel_path()
    venv = _install_fresh(tmp_path, f"{wheel}[all]", "all")
    python = _venv_python(venv)
    cli = _venv_script(venv, "videocaptioner")

    probe = _run(
        [
            str(python),
            "-c",
            (
                "import importlib.util; "
                f"mods={OPTIONAL_MODULES!r}; "
                "assert all(importlib.util.find_spec(m) is not None for m in mods); "
                "import PyQt5, edge_tts; "
                "from videocaptioner.ui.main import main as gui_main; "
                "from videocaptioner.core.dubbing import DubbingPipeline; "
                "from videocaptioner.cli.main import build_parser; "
                "assert gui_main and DubbingPipeline and build_parser(); "
                "print('all-extra imports ok')"
            ),
        ],
        cwd=venv,
    )
    assert probe.returncode == 0, probe.stdout + probe.stderr
    assert "all-extra imports ok" in probe.stdout

    help_result = _run([str(cli), "--help"], cwd=venv)
    assert help_result.returncode == 0, help_result.stderr
    assert "transcribe" in help_result.stdout
