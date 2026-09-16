"""Deterministic subtitle reflow tests.

The mechanical path must only reorganize real word timestamps. It must not call
an LLM, invent timing, lose text, or create punctuation-leading captions.
"""

from __future__ import annotations

import re

import pytest

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.asr.mechanical_reflow import mechanical_reflow


def _cjk_words(text: str, step_ms: int = 120) -> ASRData:
    return ASRData(
        [ASRDataSeg(ch, i * step_ms, (i + 1) * step_ms) for i, ch in enumerate(text)]
    )


def _normalized(text: str) -> str:
    return re.sub(r"\s+", "", text)


def test_cjk_reflow_preserves_text_and_uses_readable_boundaries():
    original = "称之类的，还有包括像一些这个单位内的一些考核，这些考试其实也都可以算啊，只是"
    result = mechanical_reflow(_cjk_words(original), max_cjk=18, max_english=12)

    assert "".join(seg.text for seg in result.segments) == original
    assert len(result.segments) >= 3
    assert max(len(re.sub(r"\W", "", seg.text)) for seg in result.segments) <= 18
    assert all(not seg.text.startswith(("，", "。", "！", "？", ",", ".", "!", "?")) for seg in result.segments)
    assert [seg.start_time for seg in result.segments] == sorted(seg.start_time for seg in result.segments)
    assert all(seg.end_time >= seg.start_time for seg in result.segments)


def test_pause_is_a_hard_mechanical_boundary():
    data = ASRData(
        [
            ASRDataSeg("今", 0, 100),
            ASRDataSeg("天", 100, 200),
            ASRDataSeg("很", 900, 1000),
            ASRDataSeg("好", 1000, 1100),
        ]
    )
    result = mechanical_reflow(data, max_cjk=18, max_english=12, pause_ms=500)
    assert [seg.text for seg in result.segments] == ["今天", "很好"]
    assert result.segments[0].end_time == 200
    assert result.segments[1].start_time == 900


def test_english_reflow_inserts_display_spaces_without_losing_tokens():
    words = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen".split()
    data = ASRData(
        [ASRDataSeg(word, i * 100, (i + 1) * 100) for i, word in enumerate(words)]
    )
    result = mechanical_reflow(data, max_cjk=18, max_english=12)

    assert len(result.segments) == 2
    assert all(len(seg.text.split()) <= 12 for seg in result.segments)
    assert _normalized(" ".join(seg.text for seg in result.segments)) == _normalized(" ".join(words))


def test_strong_punctuation_stays_with_previous_caption():
    data = _cjk_words("这是第一句。这里是第二句！最后一句")
    result = mechanical_reflow(data, max_cjk=18, max_english=12)
    assert [seg.text for seg in result.segments] == ["这是第一句。", "这里是第二句！", "最后一句"]


def test_mechanical_reflow_rejects_sentence_timestamps_instead_of_estimating():
    data = ASRData([ASRDataSeg("这是一个完整句子，不能伪造逐字时间戳。", 0, 5000)])
    with pytest.raises(ValueError, match="real word timestamps"):
        mechanical_reflow(data)


def test_hard_split_cannot_leave_punctuation_at_next_cue_start():
    tokens = [
        "alpha",
        "beta",
        "gamma",
        "delta",
        "walk",
        "，",
        ".",
        "home",
        "weather",
        "signal",
        "person",
    ]
    data = ASRData(
        [
            ASRDataSeg(token, index * 100, (index + 1) * 100)
            for index, token in enumerate(tokens)
        ]
    )

    result = mechanical_reflow(data, max_cjk=18, max_english=9, pause_ms=500)

    assert "".join(seg.text.replace(" ", "") for seg in result.segments) == "".join(tokens)
    assert all(
        not seg.text.startswith(("，", "。", "！", "？", ",", ".", "!", "?", "；", ";", "：", ":"))
        for seg in result.segments
    )
