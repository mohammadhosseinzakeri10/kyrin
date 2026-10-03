"""STT failures visible to callers regardless of the selected backend."""


class SpeechToTextError(Exception):
    """Base exception for speech-to-text failures."""


class DeviceUnavailableError(SpeechToTextError):
    """The requested CPU or GPU cannot run the selected STT backend."""
