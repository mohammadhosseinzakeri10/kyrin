"""Group PCM audio into processing windows without changing its format."""

from collections.abc import Iterable, Iterator

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat


class AudioFramer:
    """Build fixed-size windows from audio chunks of arbitrary sizes."""

    def __init__(self, audio_format: AudioFormat, frames_per_window: int) -> None:
        if frames_per_window <= 0:
            raise ValueError("frames_per_window must be positive")

        self.audio_format = audio_format
        self.frames_per_window = frames_per_window
        self._bytes_per_window = frames_per_window * audio_format.bytes_per_frame

    def frame(self, chunks: Iterable[AudioData]) -> Iterator[AudioData]:
        """Yield full windows as they form, then an unpadded final remainder.

        Each call has its own buffer. A continuously running source only yields
        full windows until it actually ends.
        """
        pending = bytearray()

        for chunk in chunks:
            if chunk.audio_format != self.audio_format:
                raise ValueError("audio chunk format changed during framing")

            data = chunk.data
            if not data:
                continue

            if pending:
                missing = self._bytes_per_window - len(pending)
                pending.extend(data[:missing])
                data = data[missing:]
                if len(pending) == self._bytes_per_window:
                    yield AudioData(bytes(pending), self.audio_format)
                    pending.clear()

            complete_windows = len(data) // self._bytes_per_window
            complete_bytes = complete_windows * self._bytes_per_window
            for start in range(0, complete_bytes, self._bytes_per_window):
                window = data[start : start + self._bytes_per_window]
                yield AudioData(window, self.audio_format)

            pending.extend(data[complete_bytes:])

        if pending:
            yield AudioData(bytes(pending), self.audio_format)
