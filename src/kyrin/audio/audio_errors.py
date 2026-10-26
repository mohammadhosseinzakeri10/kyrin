from typing import Literal


class AudioError(Exception):
    """Base exception for audio-related errors."""

    pass


class AudioQueueOverflowError(AudioError):
    """Raised when live capture outpaces downstream processing."""

    def __init__(
        self,
        message: str = "Audio processing queue overflowed",
        *,
        buffer: Literal["capture_queue", "stt_backlog", "unknown"] = "unknown",
        pending: int | None = None,
        limit: int | None = None,
        unit: Literal["chunks", "ms", "unknown"] = "unknown",
    ) -> None:
        super().__init__(message)
        self.buffer = buffer
        self.pending = pending
        self.limit = limit
        self.unit = unit


class AudioCaptureStopError(AudioError):
    """Raised when a capture worker cannot be stopped cleanly."""
