"""Playback suppression must not change microphone acquisition itself."""

from collections.abc import Iterator

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.playback_guard import PlaybackGuardInput

FORMAT = AudioFormat(16000, 1, AudioSampleFormat.INT16)


class Source:
    stopped = False

    def capture(self) -> Iterator[AudioData]:
        for _ in range(3):
            yield AudioData(b"\x01\x02" * 160, FORMAT)

    def stop_capture(self) -> None:
        self.stopped = True


class Playback:
    is_active = False


def test_only_playback_time_chunks_are_silenced_and_capture_remains_open() -> None:
    source = Source()
    playback = Playback()
    guarded = PlaybackGuardInput(source, playback)
    chunks = guarded.capture()

    assert next(chunks).data == b"\x01\x02" * 160
    playback.is_active = True
    assert next(chunks).data == bytes(320)
    playback.is_active = False
    assert next(chunks).data == b"\x01\x02" * 160
    guarded.stop_capture()
    assert source.stopped
