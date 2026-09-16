"""GUI task-factory policy tests for deterministic ASR reflow."""

from videocaptioner.core.entities import TranscribeModelEnum
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.task_factory import resolve_mechanical_split


def test_gui_config_defaults_match_frozen_blueprint():
    assert cfg.minimax_mechanical_split.defaultValue is True
    assert cfg.public_asr_mechanical_split.defaultValue is False
    assert cfg.mechanical_max_word_count_cjk.defaultValue == 18
    assert cfg.mechanical_max_word_count_english.defaultValue == 12


def test_gui_policy_defaults_can_keep_bj_untouched_and_minimax_reflowed():
    assert resolve_mechanical_split(
        TranscribeModelEnum.MINIMAX_API,
        minimax_enabled=True,
        public_enabled=False,
    ) is True
    assert resolve_mechanical_split(
        TranscribeModelEnum.BIJIAN,
        minimax_enabled=True,
        public_enabled=False,
    ) is False
    assert resolve_mechanical_split(
        TranscribeModelEnum.JIANYING,
        minimax_enabled=True,
        public_enabled=False,
    ) is False


def test_gui_policy_allows_public_asr_opt_in_without_affecting_other_engines():
    assert resolve_mechanical_split(
        TranscribeModelEnum.BIJIAN,
        minimax_enabled=True,
        public_enabled=True,
    ) is True
    assert resolve_mechanical_split(
        TranscribeModelEnum.JIANYING,
        minimax_enabled=True,
        public_enabled=True,
    ) is True
    assert resolve_mechanical_split(
        TranscribeModelEnum.WHISPER_API,
        minimax_enabled=True,
        public_enabled=True,
    ) is False
