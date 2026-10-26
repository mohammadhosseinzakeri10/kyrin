from collections.abc import Iterator
from typing import Protocol

from kyrin.audio.audio_data import AudioData


class AudioInput(Protocol):
    def capture(self) -> Iterator[AudioData]: ...

    def stop_capture(self) -> None:
        """Request capture to stop, including a read waiting in another thread."""
        ...
