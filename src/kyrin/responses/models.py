"""Language-neutral status messages for the user-facing response layer."""

from dataclasses import dataclass
from enum import StrEnum

from kyrin.commands.models import ResponseChannel


class SystemNoticeKind(StrEnum):
    PROCESSING_DELAYED = "processing_delayed"
    PROCESSING_READY = "processing_ready"
    PROCESSING_OVERLOADED = "processing_overloaded"
    AUDIO_INPUT_FAILURE = "audio_input_failure"
    COMPUTE_UNAVAILABLE = "compute_unavailable"
    MODEL_UNAVAILABLE = "model_unavailable"
    TRANSCRIPTION_FAILURE = "transcription_failure"
    GENERAL_FAILURE = "general_failure"
    LISTENING_RETRY = "listening_retry"


@dataclass(frozen=True, slots=True)
class SystemNotice:
    """A user-facing state change; raw exceptions remain outside this contract."""

    kind: SystemNoticeKind
    channel: ResponseChannel
    language: str | None = None
