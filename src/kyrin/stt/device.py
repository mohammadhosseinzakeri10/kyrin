"""Backend-independent device and language requests for STT sessions."""

from dataclasses import dataclass
from enum import StrEnum

from kyrin.stt.audio_recovery import AudioRecoveryPolicy


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
    """Portable session requests; finite inputs may skip provisional previews."""

    device: DevicePreference = DevicePreference.AUTO
    language_hint: str | None = None
    vocabulary_hints: tuple[str, ...] = ()
    emit_partials: bool = True
    include_evidence: bool = False
    maximum_alternatives: int = 3
    audio_recovery: AudioRecoveryPolicy | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.maximum_alternatives <= 4:
            raise ValueError("maximum_alternatives must be between one and four")
        if self.language_hint is not None and not self.language_hint.strip():
            raise ValueError("language_hint must not be empty")
        if (
            not isinstance(self.vocabulary_hints, tuple)
            or len(self.vocabulary_hints) > 16
            or any(
                not isinstance(hint, str)
                or not hint.strip()
                or len(hint) > 64
                or "\r" in hint
                or "\n" in hint
                for hint in self.vocabulary_hints
            )
        ):
            raise ValueError("vocabulary_hints must contain at most 16 short terms")
