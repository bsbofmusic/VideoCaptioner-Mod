"""Root-level test configuration and shared fixtures."""

import os
from typing import Dict, List

import pytest

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.translate import SubtitleProcessData, TargetLanguage
from videocaptioner.core.utils import cache


@pytest.fixture(autouse=True)
def isolate_global_cache_switch():
    """Prevent tests that enable the process-global cache from leaking state."""
    cache.disable_cache()
    yield
    cache.disable_cache()


@pytest.fixture
def sample_asr_data():
    """Create sample ASR data for translation testing."""
    segments = [
        ASRDataSeg(start_time=0, end_time=1000, text="I am a student"),
        ASRDataSeg(start_time=1000, end_time=2000, text="You are a teacher"),
        ASRDataSeg(start_time=2000, end_time=3000, text="VideoCaptioner is a tool for captioning videos"),
    ]
    return ASRData(segments)


@pytest.fixture
def sample_translate_data():
    """Create sample translation data for testing."""
    return [
        SubtitleProcessData(index=1, original_text="I am a student", translated_text=""),
        SubtitleProcessData(index=2, original_text="You are a teacher", translated_text=""),
        SubtitleProcessData(index=3, original_text="VideoCaptioner is a tool for captioning videos", translated_text=""),
    ]


@pytest.fixture
def target_language():
    """Default target language for translation tests."""
    return TargetLanguage.SIMPLIFIED_CHINESE


@pytest.fixture
def check_env_vars():
    """Check if required environment variables are set."""
    def _check(*var_names):
        missing = [var for var in var_names if not os.getenv(var)]
        if missing:
            pytest.skip(f"Required environment variables not set: {', '.join(missing)}")
    return _check


@pytest.fixture
def mock_llm_client(monkeypatch):
    """Provide a deterministic local OpenAI-compatible stub for pipeline tests."""
    import ast
    import json
    import re
    from types import SimpleNamespace

    monkeypatch.setenv("OPENAI_BASE_URL", "https://mock.invalid/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

    def fake_call_llm(*, messages, model, **kwargs):
        del model, kwargs
        user_content = messages[1]["content"] if len(messages) > 1 else messages[-1]["content"]

        if "<input_subtitle>" in user_content:
            raw = user_content.split("<input_subtitle>", 1)[1].split("</input_subtitle>", 1)[0]
            payload = ast.literal_eval(raw)
            content = json.dumps(payload, ensure_ascii=False)
        elif user_content.startswith("Please use multiple <br> tags"):
            text = user_content.split("\n", 1)[1] if "\n" in user_content else user_content
            parts = [part for part in re.split(r"(?<=[。！？.!?])\s*", text) if part]
            content = "<br>".join(parts or [text])
        else:
            try:
                payload = json.loads(user_content)
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = None
            content = (
                json.dumps(payload, ensure_ascii=False)
                if isinstance(payload, dict)
                else str(user_content)
            )

        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

    monkeypatch.setattr(
        "videocaptioner.ui.thread.subtitle_thread.check_llm_connection",
        lambda *_args, **_kwargs: (True, "ok"),
    )
    for target in (
        "videocaptioner.core.split.split_by_llm.call_llm",
        "videocaptioner.core.optimize.optimize.call_llm",
        "videocaptioner.core.translate.llm_translator.call_llm",
    ):
        monkeypatch.setattr(target, fake_call_llm)

    return fake_call_llm


@pytest.fixture
def expected_translations() -> Dict[str, Dict[str, List[str]]]:
    """Expected translation keywords for quality validation."""
    return {
        "简体中文": {
            "I am a student": ["学生"],
            "You are a teacher": ["老师", "教师"],
            "VideoCaptioner is a tool for captioning videos": ["工具"],
        },
        "日本語": {
            "I am a student": ["学生"],
            "You are a teacher": ["先生", "教師"],
        },
        "English": {
            "我是学生": ["student"],
            "你是老师": ["teacher"],
        },
    }


def assert_translation_quality(original: str, translated: str, expected_keywords: List[str]) -> None:
    """Validate translation contains expected keywords."""
    assert translated, f"Translation is empty for: {original}"
    found_keywords = [kw for kw in expected_keywords if kw in translated]
    assert found_keywords, (
        f"Translation quality issue:\n"
        f"  Original: {original}\n"
        f"  Translated: {translated}\n"
        f"  Expected keywords: {expected_keywords}"
    )
