"""Playback suppression must not change microphone acquisition itself."""

from collections.abc import Iterator
from threading import Event

import pytest

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
    is_playing = False


def test_only_playback_time_chunks_are_silenced_and_capture_remains_open() -> None:
    source = Source()
    playback = Playback()
    guard_states: list[bool] = []
    guarded = PlaybackGuardInput(source, playback, on_guard=guard_states.append)
    chunks = guarded.capture()

    assert next(chunks).data == b"\x01\x02" * 160
    playback.is_playing = True
    assert next(chunks).data == bytes(320)
    playback.is_playing = False
    assert next(chunks).data == b"\x01\x02" * 160
    guarded.stop_capture()
    assert source.stopped
    assert guard_states == [False, True, False]


def test_echo_guard_preserves_timestamps_and_silences_until_tail_expires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kyrin.commands.models import ResponseChannel
    from kyrin.responses import speech
    from kyrin.responses.presenter import PresentedResponse

    class Synth:
        is_playing = False
        last_playback_end = 0.0
        started = Event()
        release = Event()

        def speak(self, text: str, language: str) -> None:
            self.started.set()
            assert self.release.wait(2)

    class TimedSource(Source):
        def capture(self) -> Iterator[AudioData]:
            for _ in range(5):
                yield AudioData(b"\x01\x02" * 160, FORMAT, 1_000_000)

    now = 10.0
    monkeypatch.setattr(speech, "monotonic", lambda: now)
    synth = Synth()
    speaker = speech.ResponseSpeaker(synth, on_error=lambda exc: None, tail_s=0.35)
    chunks = PlaybackGuardInput(TimedSource(), speaker).capture()
    try:
        speaker.submit(
            PresentedResponse(None, None, "hello", ResponseChannel.TEXT_AND_VOICE, "en")
        )
        assert synth.started.wait(2)
        # Synthesis and waiting queue have no acoustic output.
        assert next(chunks).data != bytes(320)
        synth.is_playing = True
        guarded = next(chunks)
        assert guarded.data == bytes(320)
        assert guarded.capture_start_ns == 1_000_000
        assert guarded.capture_end_ns == 11_000_000
        speaker.interrupt()
        synth.is_playing = False
        synth.last_playback_end = now
        assert next(chunks).data == bytes(320)
        now += 0.34
        assert next(chunks).data == bytes(320)
        now += 0.02
        assert next(chunks).data != bytes(320)
    finally:
        synth.release.set()
        speaker.close()
