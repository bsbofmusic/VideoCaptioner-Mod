"""Mechanical reflow policy tests for provider integration."""

from __future__ import annotations

import importlib

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.entities import TranscribeConfig, TranscribeModelEnum


def test_mechanical_split_forces_real_word_timestamps_for_public_providers(tmp_path):
    from videocaptioner.core.asr.transcribe import _create_bijian_asr, _create_jianying_asr

    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF-placeholder")
    config = TranscribeConfig(need_word_time_stamp=False, mechanical_split=True)

    for factory in (_create_bijian_asr, _create_jianying_asr):
        chunked = factory(str(audio_path), config)
        assert chunked.asr_kwargs["need_word_time_stamp"] is True
        assert chunked.chunk_concurrency == 1


def test_minimax_mechanical_split_forces_words_and_keeps_480_second_chunks(tmp_path):
    from videocaptioner.core.asr.transcribe import _create_minimax_asr

    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF-placeholder")
    config = TranscribeConfig(
        need_word_time_stamp=False,
        mechanical_split=True,
        minimax_api_key="test-key",
    )

    chunked = _create_minimax_asr(str(audio_path), config)
    assert chunked.asr_kwargs["need_word_time_stamp"] is True
    assert chunked.chunk_concurrency == 1
    assert chunked.chunk_length_ms == 480 * 1000


def test_transcribe_mechanical_split_reflows_real_word_timestamps(monkeypatch):
    from videocaptioner.core.asr import transcribe as transcribe_fn
    transcribe_module = importlib.import_module("videocaptioner.core.asr.transcribe")

    class FakeASR:
        def run(self, callback=None):
            return ASRData(
                [
                    ASRDataSeg(ch, index * 100, (index + 1) * 100)
                    for index, ch in enumerate("这是一个很长的句子需要机械断句并且不能调用大模型继续往后还有内容")
                ]
            )

    monkeypatch.setattr(transcribe_module, "_create_asr_instance", lambda *_: FakeASR())

    result = transcribe_fn(
        "unused.wav",
        TranscribeConfig(
            transcribe_model=TranscribeModelEnum.BIJIAN,
            mechanical_split=True,
            need_word_time_stamp=False,
            max_word_count_cjk=10,
            max_word_count_english=8,
        ),
    )

    assert len(result.segments) >= 3
    assert max(len(seg.text) for seg in result.segments) <= 10


def test_transcribe_skips_mechanical_split_when_provider_does_not_return_real_words(monkeypatch):
    from videocaptioner.core.asr import transcribe as transcribe_fn
    transcribe_module = importlib.import_module("videocaptioner.core.asr.transcribe")

    class FakeASR:
        def run(self, callback=None):
            return ASRData([ASRDataSeg("provider sentence remains unchanged", 100, 3100)])

    monkeypatch.setattr(transcribe_module, "_create_asr_instance", lambda *_: FakeASR())

    messages: list[str] = []
    result = transcribe_fn(
        "unused.wav",
        TranscribeConfig(
            transcribe_model=TranscribeModelEnum.BIJIAN,
            mechanical_split=True,
            need_word_time_stamp=False,
        ),
        callback=lambda _pct, message: messages.append(message),
    )

    assert [seg.text for seg in result.segments] == ["provider sentence remains unchanged"]
    assert result.segments[0].start_time == 100
    assert result.segments[0].end_time == 3100
    assert any("real word timestamps" in message for message in messages)
