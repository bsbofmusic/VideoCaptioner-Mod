"""Policy tests for rate-limited public ASR chunking."""

import pytest

from videocaptioner.core.asr.transcribe import _create_bijian_asr, _create_jianying_asr
from videocaptioner.core.entities import TranscribeConfig


@pytest.mark.parametrize("factory", [_create_bijian_asr, _create_jianying_asr])
def test_public_remote_asr_chunking_is_serial(factory, tmp_path):
    """Long-audio chunking must not fan out concurrent charity API requests."""
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF-test-audio-placeholder")

    chunked = factory(
        str(audio_path),
        TranscribeConfig(need_word_time_stamp=False),
    )

    assert chunked.chunk_concurrency == 1
