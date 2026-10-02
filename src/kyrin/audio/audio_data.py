from dataclasses import dataclass

from kyrin.audio.audio_format import AudioFormat


@dataclass(frozen=True)
class AudioData:
    """Represent immutable audio data and its format."""

    data: bytes
    audio_format: AudioFormat

    def __post_init__(self) -> None:
        if len(self.data) % self.audio_format.bytes_per_frame != 0:
            raise ValueError("audio data length must align with audio frame size")
