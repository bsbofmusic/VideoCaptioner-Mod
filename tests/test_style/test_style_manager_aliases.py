"""Regression tests for legacy subtitle style names."""

import json
from pathlib import Path

import pytest

from videocaptioner.core.subtitle.style_manager import (
    StyleMode,
    available_style_names,
    load_style,
)


def _write_style(styles_dir: Path, filename: str, *, name: str, mode: str, font_size: int) -> None:
    payload = {
        "name": name,
        "description": f"{mode} {name}",
        "mode": mode,
        "font_name": "Noto Sans SC",
        "font_size": font_size,
    }
    if mode == "rounded":
        payload.update({"text_color": "#000000", "bg_color": "#ffffff"})
    else:
        payload.update({"primary_color": "#ffffff", "outline_color": "#000000"})
    (styles_dir / filename).write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def styles_dir(tmp_path: Path) -> Path:
    _write_style(tmp_path, "ass-default.json", name="default", mode="ass", font_size=40)
    _write_style(tmp_path, "rounded-default.json", name="default", mode="rounded", font_size=28)
    _write_style(tmp_path, "ass-anime.json", name="anime", mode="ass", font_size=46)
    _write_style(tmp_path, "ass-vertical.json", name="vertical", mode="ass", font_size=34)
    return tmp_path


@pytest.mark.parametrize(
    ("legacy_name", "canonical_name"),
    [
        ("毕导科普风", "default"),
        ("番剧可爱风", "anime"),
        ("竖屏", "vertical"),
    ],
)
def test_load_style_resolves_legacy_aliases(
    styles_dir: Path,
    legacy_name: str,
    canonical_name: str,
) -> None:
    style = load_style(legacy_name, styles_dir=styles_dir)

    assert style is not None
    assert style.name == canonical_name


def test_legacy_default_alias_preserves_mode_preference(styles_dir: Path) -> None:
    ass_style = load_style("毕导科普风", styles_dir=styles_dir, mode="ass")
    rounded_style = load_style("毕导科普风", styles_dir=styles_dir, mode="rounded")

    assert ass_style is not None
    assert ass_style.mode is StyleMode.ASS
    assert ass_style.font_size == 40
    assert rounded_style is not None
    assert rounded_style.mode is StyleMode.ROUNDED
    assert rounded_style.font_size == 28


def test_legacy_aliases_do_not_pollute_canonical_style_names(styles_dir: Path) -> None:
    names = available_style_names(styles_dir)

    assert names == ["anime", "default", "vertical"]
    assert "毕导科普风" not in names
    assert "番剧可爱风" not in names
    assert "竖屏" not in names
