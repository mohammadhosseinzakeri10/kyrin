class AudioError(Exception):
    """Base exception for audio-related errors."""

    pass


class AudioQueueOverflowError(AudioError):
    """Raised when live capture outpaces downstream processing."""


class AudioCaptureStopError(AudioError):
    """Raised when a capture worker cannot be stopped cleanly."""
