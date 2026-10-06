"""Small structural contracts for replaceable STT backends."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat
from kyrin.stt.capabilities import SpeechToTextCapabilities
from kyrin.stt.device import ComputeDevice, SpeechToTextOptions
from kyrin.stt.transcript import TranscriptUpdate


class SpeechToTextSession(Protocol):
    """Recognize one ordered audio stream while retaining decoder state.

    Pauses in speech do not end the session. The caller must feed audio in
    input_format, finish only when the stream truly ends, and always close the
    session to release its resources. Inference may block; the future live
    pipeline must keep microphone capture independent from this work.
    """

    @property
    def input_format(self) -> AudioFormat: ...

    @property
    def compute_device(self) -> ComputeDevice: ...

    @property
    def supports_partial_updates(self) -> bool: ...

    def accept_audio(self, chunk: AudioData) -> Sequence[TranscriptUpdate]:
        """Accept the next chunk and return any newly available updates."""
        ...

    def finish(self) -> Sequence[TranscriptUpdate]:
        """Flush pending results at the actual end of this audio stream."""
        ...

    def close(self) -> None:
        """Release the session, including when the stream stops early."""
        ...


@runtime_checkable
class TurnAwareSpeechToTextSession(Protocol):
    """Optional turn hints for windowed backends; streaming STT need not use them."""

    def start_turn(self) -> Sequence[TranscriptUpdate]: ...

    def end_turn(self) -> Sequence[TranscriptUpdate]: ...


class SpeechToTextEngine(Protocol):
    """Create sessions without exposing a model library to audio consumers."""

    @property
    def capabilities(self) -> SpeechToTextCapabilities: ...

    def open_session(self, options: SpeechToTextOptions) -> SpeechToTextSession:
        """Open a local session and resolve its requested compute device.

        AUTO may select an available device. An explicit CPU or GPU request
        must be honored or raise DeviceUnavailableError. The resolved device
        is available through the returned session's compute_device property.
        """
        ...

    def close(self) -> None:
        """Release the loaded model after all of its sessions have closed."""
        ...
