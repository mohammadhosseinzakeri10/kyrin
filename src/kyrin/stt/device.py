"""Backend-independent device and language requests for STT sessions."""

from dataclasses import dataclass
from enum import StrEnum


class DevicePreference(StrEnum):
    """Where the user would like STT inference to run."""

    AUTO = "auto"
    CPU = "cpu"
    GPU = "gpu"


class ComputeDevice(StrEnum):
    """The device actually used by an STT session."""

    CPU = "cpu"
    GPU = "gpu"


@dataclass(frozen=True, slots=True)
class SpeechToTextOptions:
    """Portable session requests; model paths remain backend-specific."""

    device: DevicePreference = DevicePreference.AUTO
    language_hint: str | None = None

    def __post_init__(self) -> None:
        if self.language_hint is not None and not self.language_hint.strip():
            raise ValueError("language_hint must not be empty")
