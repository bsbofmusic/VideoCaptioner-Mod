"""Package metadata tests for the core/GUI/dubbing dependency split."""

import re
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[2]
OPTIONAL_RUNTIME = {
    "pyqt5",
    "pyqt-fluent-widgets",
    "modelscope",
    "psutil",
    "gputil",
    "edge-tts",
}
GUI_RUNTIME = {
    "pyqt5",
    "pyqt-fluent-widgets",
    "modelscope",
    "psutil",
    "gputil",
}


def _name(requirement: str) -> str:
    return re.split(r"[<>=!~;\s\[]", requirement, maxsplit=1)[0].lower()


def _names(requirements: list[str]) -> set[str]:
    return {_name(requirement) for requirement in requirements}


def _metadata() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_base_dependencies_are_cli_only_and_include_httpx() -> None:
    metadata = _metadata()
    base = _names(metadata["project"]["dependencies"])

    assert "httpx" in base
    assert base.isdisjoint(OPTIONAL_RUNTIME)


def test_gui_dubbing_and_all_extras_are_complete() -> None:
    metadata = _metadata()
    extras = metadata["project"]["optional-dependencies"]

    assert _names(extras["gui"]) == GUI_RUNTIME
    assert _names(extras["dubbing"]) == {"edge-tts"}
    assert _names(extras["all"]) == OPTIONAL_RUNTIME


def test_dev_environment_keeps_optional_runtime_for_full_tests() -> None:
    metadata = _metadata()
    dev = _names(metadata["dependency-groups"]["dev"])

    assert OPTIONAL_RUNTIME <= dev
