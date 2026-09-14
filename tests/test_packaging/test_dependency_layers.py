"""Package metadata tests for the 0.0.9 lightweight core / optional GUI split."""

import re
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[2]
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
    assert base.isdisjoint(GUI_RUNTIME)


def test_gui_and_all_extras_contain_only_gui_runtime_for_upstream_142() -> None:
    extras = _metadata()["project"]["optional-dependencies"]
    assert _names(extras["gui"]) == GUI_RUNTIME
    assert _names(extras["dubbing"]) == set()
    assert _names(extras["all"]) == GUI_RUNTIME


def test_gui_console_script_uses_guarded_cli_wrapper() -> None:
    scripts = _metadata()["project"]["scripts"]
    assert scripts["videocaptioner"] == "videocaptioner.cli.main:main"
    assert scripts["videocaptioner-gui"] == "videocaptioner.cli.main:gui_main"


def test_packaged_gui_resources_are_explicitly_included() -> None:
    force_include = _metadata()["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert force_include == {
        "resource/assets": "videocaptioner/resources/assets",
        "resource/subtitle_style": "videocaptioner/resources/subtitle_style",
        "resource/translations": "videocaptioner/resources/translations",
    }
