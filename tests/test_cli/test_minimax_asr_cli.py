"""CLI surface tests for MiniMax ASR."""

from videocaptioner.cli.commands.doctor import _check_transcribe
from videocaptioner.cli.commands.transcribe import _resolve_mechanical_split
from videocaptioner.cli.config import DEFAULTS, ENV_MAP
from videocaptioner.cli.main import build_parser


def test_transcribe_parser_accepts_minimax_options():
    args = build_parser().parse_args(
        [
            "transcribe",
            "sample.wav",
            "--asr",
            "minimax",
            "--minimax-api-key",
            "[REDACTED_SECRET]",
            "--minimax-api-base",
            "https://api.minimaxi.com/v1",
            "--minimax-model",
            "asr-1.0",
        ]
    )

    assert args.asr == "minimax"
    assert args.minimax_api_key == "[REDACTED_SECRET]"
    assert args.minimax_api_base == "https://api.minimaxi.com/v1"
    assert args.minimax_model == "asr-1.0"


def test_process_parser_accepts_minimax():
    args = build_parser().parse_args(["process", "sample.mp4", "--asr", "minimax"])
    assert args.asr == "minimax"


def test_transcribe_parser_accepts_mechanical_split_override():
    enabled = build_parser().parse_args(
        ["transcribe", "sample.wav", "--asr", "bijian", "--mechanical-split"]
    )
    disabled = build_parser().parse_args(
        ["transcribe", "sample.wav", "--asr", "minimax", "--no-mechanical-split"]
    )
    assert enabled.mechanical_split is True
    assert disabled.mechanical_split is False


def test_mechanical_split_provider_defaults_are_conservative():
    config = DEFAULTS
    assert _resolve_mechanical_split("minimax", None, config) is True
    assert _resolve_mechanical_split("bijian", None, config) is False
    assert _resolve_mechanical_split("jianying", None, config) is False
    assert _resolve_mechanical_split("whisper-api", None, config) is False
    assert _resolve_mechanical_split("bijian", True, config) is True
    assert _resolve_mechanical_split("minimax", False, config) is False


def test_minimax_defaults_and_environment_mapping_exist():
    assert DEFAULTS["minimax_api"] == {
        "api_key": "",
        "api_base": "https://api.minimaxi.com/v1",
        "model": "asr-1.0",
    }
    assert DEFAULTS["transcribe"]["mechanical_split"] == {
        "minimax": True,
        "public": False,
        "max_cjk": 18,
        "max_english": 12,
    }
    assert DEFAULTS["subtitle"]["split"] is False
    assert ENV_MAP["VIDEOCAPTIONER_MINIMAX_API_KEY"] == "minimax_api.api_key"
    assert ENV_MAP["VIDEOCAPTIONER_MINIMAX_API_BASE"] == "minimax_api.api_base"
    assert ENV_MAP["VIDEOCAPTIONER_MINIMAX_MODEL"] == "minimax_api.model"


def test_doctor_reports_missing_minimax_key():
    config = {
        "transcribe": {"asr": "minimax"},
        "minimax_api": {"api_key": ""},
    }
    checks = _check_transcribe(config)
    assert any(c.name == "minimax_api.api_key" and c.status == "error" for c in checks)


def test_doctor_accepts_configured_minimax_key():
    config = {
        "transcribe": {"asr": "minimax"},
        "minimax_api": {"api_key": "configured"},
    }
    checks = _check_transcribe(config)
    assert not any(c.name == "minimax_api.api_key" and c.status == "error" for c in checks)
