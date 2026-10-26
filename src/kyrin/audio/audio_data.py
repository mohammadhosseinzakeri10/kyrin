from dataclasses import dataclass, field

from kyrin.audio.audio_format import AudioFormat


@dataclass(frozen=True)
class AudioData:
    """Represent immutable audio data and its format."""

    data: bytes
    audio_format: AudioFormat
    capture_start_ns: int | None = field(default=None, compare=False)

    @property
    def capture_end_ns(self) -> int | None:
        if self.capture_start_ns is None:
            return None
        frames = len(self.data) // self.audio_format.bytes_per_frame
        return (
            self.capture_start_ns
            + frames * 1_000_000_000 // self.audio_format.sample_rate
        )

    def __post_init__(self) -> None:
        if len(self.data) % self.audio_format.bytes_per_frame != 0:
            raise ValueError("audio data length must align with audio frame size")
