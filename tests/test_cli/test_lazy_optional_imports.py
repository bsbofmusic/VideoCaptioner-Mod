"""Subprocess tests for lazy optional dependency imports."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_cli_parser_and_presets_do_not_import_pipeline_or_edge_tts() -> None:
    code = r'''
import builtins
import sys

real_import = builtins.__import__

def blocked_import(name, *args, **kwargs):
    if name == "edge_tts" or name.startswith("edge_tts."):
        raise ModuleNotFoundError("edge_tts intentionally unavailable")
    return real_import(name, *args, **kwargs)

builtins.__import__ = blocked_import
from videocaptioner.cli.main import build_parser
from videocaptioner.core.dubbing.presets import available_dubbing_presets

parser = build_parser()
assert parser.prog == "videocaptioner"
assert available_dubbing_presets()
assert "videocaptioner.core.dubbing.pipeline" not in sys.modules
assert "edge_tts" not in sys.modules

from videocaptioner.core.dubbing import DubbingPipeline
assert DubbingPipeline.__name__ == "DubbingPipeline"
assert "edge_tts" not in sys.modules
'''
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
