from pathlib import Path
from types import SimpleNamespace

import pytest

from videocaptioner.core.speech import (
    EdgeTTSSpeechSynthesizer,
    SpeechProviderConfig,
    SynthesisRequest,
    providers,
)


class FakeCommunicate:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls.append(kwargs)

    async def save(self, audio_fname):
        Path(audio_fname).write_bytes(b"fake-mp3")


def test_edge_tts_synthesizer_writes_mp3(tmp_path, monkeypatch):
    monkeypatch.setattr(
        providers,
        "_load_edge_tts",
        lambda: SimpleNamespace(Communicate=FakeCommunicate),
    )

    config = SpeechProviderConfig(
        provider="edge",
        api_key="",
        model="edge-tts",
        default_voice="zh-CN-XiaoxiaoNeural",
        speed=1.2,
        gain=-10,
    )
    result = EdgeTTSSpeechSynthesizer(config).synthesize(
        SynthesisRequest(text="你好", output_path=str(tmp_path / "line.wav"))
    )

    assert result.output_path.endswith(".mp3")
    assert Path(result.output_path).read_bytes() == b"fake-mp3"
    assert result.voice == "zh-CN-XiaoxiaoNeural"
    assert FakeCommunicate.calls[-1]["rate"] == "+20%"
    assert FakeCommunicate.calls[-1]["volume"] == "-10%"


def test_missing_edge_tts_has_actionable_extra_hint(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "edge_tts" or name.startswith("edge_tts."):
            raise ModuleNotFoundError("edge_tts intentionally unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    with pytest.raises(RuntimeError, match=r"pip install 'videocaptioner\[dubbing\]'"):
        providers._load_edge_tts()
