"""Subtitle dubbing pipeline."""

from typing import TYPE_CHECKING, Any

from .models import DubbingConfig, DubbingResult, DubbingSegment, SpeakerProfile
from .presets import available_dubbing_presets, get_dubbing_preset

if TYPE_CHECKING:
    from .pipeline import DubbingPipeline

__all__ = [
    "DubbingConfig",
    "DubbingPipeline",
    "DubbingResult",
    "DubbingSegment",
    "SpeakerProfile",
    "available_dubbing_presets",
    "get_dubbing_preset",
]


def __getattr__(name: str) -> Any:
    """Load the heavy dubbing pipeline only when the public export is requested."""
    if name == "DubbingPipeline":
        from .pipeline import DubbingPipeline

        globals()[name] = DubbingPipeline
        return DubbingPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
