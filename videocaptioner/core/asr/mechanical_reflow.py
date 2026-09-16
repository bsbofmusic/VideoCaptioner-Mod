"""Deterministic subtitle reflow for real word-level ASR timestamps.

This module intentionally does not call an LLM and never fabricates word timing.
It only groups provider-supplied word/character timestamp segments into readable
caption cues using punctuation, pauses, and hard display-length limits.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from videocaptioner.core.utils.text_utils import count_words, is_mainly_cjk, is_pure_punctuation

from .asr_data import ASRData, ASRDataSeg

DEFAULT_MAX_CJK = 18
DEFAULT_MAX_ENGLISH = 12
DEFAULT_PAUSE_MS = 500

_STRONG_PUNCTUATION = "。！？!?；;"
_WEAK_PUNCTUATION = "，,、：:"
_CLOSING_PUNCTUATION = "”’\"')）]】}》〉」』"
_OPENING_PUNCTUATION = "“‘\"'(（[【{《〈「『"
_ATTACH_LEFT_PUNCTUATION = set(
    "，。！？；：、,.!?;:%…)]}）】》〉」』”’"
)
_WORDISH_RE = re.compile(
    r"[\w\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff\u0900-\u0dff]+",
    re.UNICODE,
)


def _strip_token(text: str) -> str:
    return text.strip()


def _has_terminal(text: str, punctuation: str) -> bool:
    stripped = _strip_token(text).rstrip(_CLOSING_PUNCTUATION)
    return bool(stripped) and stripped[-1] in punctuation


def _is_punctuation_token(text: str) -> bool:
    stripped = _strip_token(text)
    return bool(stripped) and is_pure_punctuation(stripped)


def _join_tokens(segments: Sequence[ASRDataSeg]) -> str:
    """Join word tokens into display text without changing token order/content."""
    parts: list[str] = []
    previous = ""
    for segment in segments:
        token = _strip_token(segment.text)
        if not token:
            continue
        if not parts:
            parts.append(token)
            previous = token
            continue

        attach_left = token[0] in _ATTACH_LEFT_PUNCTUATION
        previous_opens = previous[-1] in _OPENING_PUNCTUATION if previous else False
        no_space_language = is_mainly_cjk("".join(parts) + token)
        if attach_left or previous_opens or no_space_language:
            parts.append(token)
        else:
            parts.append(" " + token)
        previous = token
    return "".join(parts).strip()


def _display_units(segments: Sequence[ASRDataSeg]) -> int:
    """Count visible language units while ignoring punctuation-only tokens."""
    text = _join_tokens(segments)
    if not text:
        return 0
    cleaned = " ".join(_WORDISH_RE.findall(text))
    return count_words(cleaned)


def _limit_for(segments: Sequence[ASRDataSeg], max_cjk: int, max_english: int) -> int:
    text = _join_tokens(segments)
    return max_cjk if is_mainly_cjk(text) else max_english


def _last_weak_boundary(segments: Sequence[ASRDataSeg], limit: int) -> int | None:
    """Return an inclusive split index near the end at weak punctuation."""
    minimum_units = max(2, limit // 2)
    candidate: int | None = None
    for index, segment in enumerate(segments):
        if _display_units(segments[: index + 1]) < minimum_units:
            continue
        if _has_terminal(segment.text, _WEAK_PUNCTUATION):
            candidate = index
    return candidate


def _cue(segments: Sequence[ASRDataSeg]) -> ASRDataSeg:
    return ASRDataSeg(
        text=_join_tokens(segments),
        start_time=segments[0].start_time,
        end_time=segments[-1].end_time,
    )


def mechanical_reflow(
    asr_data: ASRData,
    *,
    max_cjk: int = DEFAULT_MAX_CJK,
    max_english: int = DEFAULT_MAX_ENGLISH,
    pause_ms: int = DEFAULT_PAUSE_MS,
) -> ASRData:
    """Group real word timestamps into readable caption cues.

    Boundaries are deterministic and prioritized as follows:
    1. provider-supplied pauses of at least ``pause_ms``;
    2. strong sentence punctuation;
    3. weak punctuation once a cue approaches its display limit;
    4. a hard display-length split.

    The input must already contain genuine word/character timestamp segments.
    Sentence-level timestamps are rejected instead of being expanded using
    estimated timing.
    """
    if max_cjk < 1 or max_english < 1:
        raise ValueError("Mechanical reflow limits must be positive")
    if pause_ms < 0:
        raise ValueError("Mechanical reflow pause must be non-negative")
    if not asr_data.segments:
        return ASRData([])
    if not asr_data.is_word_timestamp():
        raise ValueError("Mechanical reflow requires real word timestamps")

    output: list[ASRDataSeg] = []
    current: list[ASRDataSeg] = []

    def flush(group: Sequence[ASRDataSeg]) -> None:
        if not group:
            return
        pending = list(group)
        while pending and output and _is_punctuation_token(pending[0].text):
            punctuation = pending.pop(0)
            output[-1].text = f"{output[-1].text}{_strip_token(punctuation.text)}"
            output[-1].end_time = max(output[-1].end_time, punctuation.end_time)
        if not pending:
            return
        cue = _cue(pending)
        if cue.text:
            output.append(cue)

    for segment in asr_data.segments:
        token = _strip_token(segment.text)
        if not token:
            continue

        if current:
            gap = segment.start_time - current[-1].end_time
            if gap >= pause_ms:
                flush(current)
                current = []

        # Never let punctuation become the first visible character of a new cue.
        if not current and _is_punctuation_token(token) and output:
            output[-1].text = f"{output[-1].text}{token}"
            output[-1].end_time = max(output[-1].end_time, segment.end_time)
            continue

        current.append(segment)
        limit = _limit_for(current, max_cjk, max_english)
        units = _display_units(current)

        if _has_terminal(token, _STRONG_PUNCTUATION):
            flush(current)
            current = []
            continue

        # Prefer a natural weak-punctuation boundary as we approach the cap.
        if units >= max(2, int(limit * 0.75)) and _has_terminal(token, _WEAK_PUNCTUATION):
            flush(current)
            current = []
            continue

        if units >= limit:
            split_index = _last_weak_boundary(current, limit)
            if split_index is not None and split_index < len(current) - 1:
                flush(current[: split_index + 1])
                current = current[split_index + 1 :]
            else:
                flush(current)
                current = []

    flush(current)
    return ASRData(output)
