from dataclasses import dataclass
from enum import StrEnum


class AudioSampleFormat(StrEnum):
    """Audio sample format enumeration."""

    INT16 = "int16"
    FLOAT32 = "float32"

    @property
    def bytes_per_sample(self) -> int:
        if self is AudioSampleFormat.INT16:
            return 2

        if self is AudioSampleFormat.FLOAT32:
            return 4

        raise ValueError(f"Unsupported audio sample format: {self}")


@dataclass(frozen=True)
class AudioFormat:
    """Represent an immutable audio format."""

    sample_rate: int
    channels: int
    sample_format: AudioSampleFormat

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")

        if self.channels <= 0:
            raise ValueError("channels must be positive")

    @property
    def bytes_per_frame(self) -> int:
        """Return the number of bytes per audio frame."""
        return self.channels * self.sample_format.bytes_per_sample
