from kyrin.audio.audio_errors import AudioError
from kyrin.audio.microphone.errors import MicrophoneError, MicrophoneOverflowError


def test_microphone_overflow_error_is_audio_error() -> None:
    assert issubclass(MicrophoneOverflowError, AudioError)
    assert issubclass(MicrophoneOverflowError, MicrophoneError)
