"""Errors raised by the microphone audio source."""

from kyrin.audio.audio_errors import AudioError


class MicrophoneError(AudioError):
    """Base exception for microphone-related errors."""


class MicrophoneOverflowError(MicrophoneError):
    """Raised when microphone input overflows."""
