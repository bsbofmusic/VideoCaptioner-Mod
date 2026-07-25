"""Regression coverage for GUI events delivered during base-window construction."""

import ast
from pathlib import Path

MAIN_WINDOW_PATH = (
    Path(__file__).resolve().parents[2] / "videocaptioner" / "ui" / "view" / "main_window.py"
)


def test_event_filter_handles_events_before_stacked_widget_initialization() -> None:
    source = MAIN_WINDOW_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    main_window = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "MainWindow"
    )
    event_filter = next(
        node
        for node in main_window.body
        if isinstance(node, ast.FunctionDef) and node.name == "eventFilter"
    )
    function_source = ast.get_source_segment(source, event_filter)

    assert function_source is not None
    fragments = [
        'stacked_widget = getattr(self, "stackedWidget", None)',
        "if stacked_widget is None:",
        "return super().eventFilter(obj, event)",
        "if obj is stacked_widget",
    ]
    positions = [function_source.index(fragment) for fragment in fragments]

    assert positions == sorted(positions)
    assert "self.stackedWidget" not in function_source
