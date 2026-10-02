"""Contract for streaming voice activity detection."""

from typing import Protocol

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat


class VoiceActivityDetector(Protocol):
    """Classify fixed audio windows while keeping per-stream model state."""

    @property
    def input_format(self) -> AudioFormat: ...

    @property
    def frames_per_window(self) -> int: ...

    def detect(self, window: AudioData) -> bool: ...

    def reset(self) -> None: ...
