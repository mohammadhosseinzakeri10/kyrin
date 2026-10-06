from threading import Event, Thread
from time import sleep
from types import TracebackType

import pytest
import sounddevice as sd  # type: ignore[import-untyped]
from pytest import MonkeyPatch

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.microphone.errors import MicrophoneError, MicrophoneOverflowError
from kyrin.audio.microphone.input import MicrophoneInput


class FakeRawInputStream:
    read_count: int = 0
    last_read_frames: int | None = None
    last_samplerate: int | None = None
    last_device: int | None = None
    last_channels: int | None = None
    last_dtype: str | None = None

    def __init__(
        self,
        device: int,
        samplerate: int,
        channels: int,
        dtype: str,
    ) -> None:
        FakeRawInputStream.last_samplerate = samplerate
        FakeRawInputStream.last_device = device
        FakeRawInputStream.last_channels = channels
        FakeRawInputStream.last_dtype = dtype

    def __enter__(self) -> FakeRawInputStream:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        pass

    def read(self, frames: int) -> tuple[bytes, bool]:
        FakeRawInputStream.last_read_frames = frames
        FakeRawInputStream.read_count += 1
        return b"fake audio", False


class OverflowingFakeRawInputStream(FakeRawInputStream):
    def read(self, frames: int) -> tuple[bytes, bool]:
        return b"fake audio", True


class MultiChunkFakeRawInputStream(FakeRawInputStream):
    read_count: int = 0

    def read(self, frames: int) -> tuple[bytes, bool]:
        MultiChunkFakeRawInputStream.read_count += 1

        if MultiChunkFakeRawInputStream.read_count == 1:
            return b"chunk 01", False

        return b"chunk 02", False


class FailingRawInputStream(FakeRawInputStream):
    def __enter__(self) -> FailingRawInputStream:
        raise sd.PortAudioError("fake PortAudio failure")


class ReadFailingRawInputStream(FakeRawInputStream):
    def read(self, frames: int) -> tuple[bytes, bool]:
        raise sd.PortAudioError("fake PortAudio failure")


class BlockingRawInputStream(FakeRawInputStream):
    entered = Event()
    released = Event()
    aborted = False

    def read(self, frames: int) -> tuple[bytes, bool]:
        BlockingRawInputStream.entered.set()
        assert BlockingRawInputStream.released.wait(1)
        raise sd.PortAudioError("read interrupted")

    def abort(self) -> None:
        BlockingRawInputStream.aborted = True
        BlockingRawInputStream.released.set()


class ShortReadRawInputStream(FakeRawInputStream):
    entered = Event()
    aborted = False

    def read(self, frames: int) -> tuple[bytes, bool]:
        ShortReadRawInputStream.entered.set()
        sleep(0.03)
        return b"fake audio", False

    def abort(self) -> None:
        ShortReadRawInputStream.aborted = True


def test_capture_yields_audio_data(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "kyrin.audio.microphone.input.sd.RawInputStream",
        FakeRawInputStream,
    )

    audio_format = AudioFormat(
        sample_rate=44100,
        channels=1,
        sample_format=AudioSampleFormat.INT16,
    )

    microphone = MicrophoneInput(
        device=5,
        audio_format=audio_format,
        frames_per_chunk=1024,
    )

    generator = microphone.capture()
    audio_chunk = next(generator)

    assert isinstance(audio_chunk, AudioData)
    assert audio_chunk.data == b"fake audio"
    assert audio_chunk.audio_format == audio_format

    assert FakeRawInputStream.last_read_frames == 1024
    assert FakeRawInputStream.last_samplerate == 44100
    assert FakeRawInputStream.last_device == 5
    assert FakeRawInputStream.last_channels == 1
    assert FakeRawInputStream.last_dtype == "int16"


def test_capture_raises_on_overflow(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "kyrin.audio.microphone.input.sd.RawInputStream",
        OverflowingFakeRawInputStream,
    )

    audio_format = AudioFormat(
        sample_rate=44100,
        channels=1,
        sample_format=AudioSampleFormat.INT16,
    )

    microphone = MicrophoneInput(
        device=5,
        audio_format=audio_format,
        frames_per_chunk=1024,
    )

    generator = microphone.capture()

    with pytest.raises(MicrophoneOverflowError):
        next(generator)


def test_capture_yields_multiple_chunks(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "kyrin.audio.microphone.input.sd.RawInputStream",
        MultiChunkFakeRawInputStream,
    )

    audio_format = AudioFormat(
        sample_rate=44100,
        channels=1,
        sample_format=AudioSampleFormat.INT16,
    )

    microphone = MicrophoneInput(
        device=5,
        audio_format=audio_format,
        frames_per_chunk=1024,
    )

    generator = microphone.capture()

    first_chunk = next(generator)
    second_chunk = next(generator)

    assert first_chunk.data == b"chunk 01"
    assert second_chunk.data == b"chunk 02"

    assert first_chunk.audio_format == audio_format
    assert second_chunk.audio_format == audio_format


def test_capture_translates_portaudio_error(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "kyrin.audio.microphone.input.sd.RawInputStream",
        FailingRawInputStream,
    )

    audio_format = AudioFormat(
        sample_rate=44100,
        channels=1,
        sample_format=AudioSampleFormat.INT16,
    )

    microphone = MicrophoneInput(
        device=5,
        audio_format=audio_format,
        frames_per_chunk=1024,
    )

    generator = microphone.capture()

    with pytest.raises(MicrophoneError) as exc_info:
        next(generator)

    assert isinstance(exc_info.value.__cause__, sd.PortAudioError)


def test_capture_translates_read_portaudio_error(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "kyrin.audio.microphone.input.sd.RawInputStream",
        ReadFailingRawInputStream,
    )

    audio_format = AudioFormat(
        sample_rate=44100,
        channels=1,
        sample_format=AudioSampleFormat.INT16,
    )

    microphone = MicrophoneInput(
        device=5,
        audio_format=audio_format,
        frames_per_chunk=1024,
    )

    generator = microphone.capture()

    with pytest.raises(MicrophoneError) as exc_info:
        next(generator)

    assert isinstance(exc_info.value.__cause__, sd.PortAudioError)


def test_microphone_input_rejects_zero_frames_per_chunk() -> None:
    audio_format = AudioFormat(
        sample_rate=44100,
        channels=1,
        sample_format=AudioSampleFormat.INT16,
    )

    with pytest.raises(ValueError):
        MicrophoneInput(
            device=5,
            audio_format=audio_format,
            frames_per_chunk=0,
        )


def test_microphone_input_rejects_negative_frames_per_chunk() -> None:
    audio_format = AudioFormat(
        sample_rate=44100,
        channels=1,
        sample_format=AudioSampleFormat.INT16,
    )

    with pytest.raises(ValueError):
        MicrophoneInput(
            device=5,
            audio_format=audio_format,
            frames_per_chunk=-1,
        )


def test_stop_capture_interrupts_a_pending_read(monkeypatch: MonkeyPatch) -> None:
    BlockingRawInputStream.entered.clear()
    BlockingRawInputStream.released.clear()
    BlockingRawInputStream.aborted = False
    monkeypatch.setattr(
        "kyrin.audio.microphone.input.sd.RawInputStream", BlockingRawInputStream
    )
    microphone = MicrophoneInput(5, AudioFormat(16000, 1, AudioSampleFormat.INT16), 512)
    finished = Event()

    def capture_one() -> None:
        assert list(microphone.capture()) == []
        finished.set()

    worker = Thread(target=capture_one)
    worker.start()
    assert BlockingRawInputStream.entered.wait(1)

    microphone.stop_capture()
    worker.join(1)

    assert finished.is_set()
    assert BlockingRawInputStream.aborted
    assert not worker.is_alive()


def test_stop_capture_allows_short_read_to_finish_without_abort(
    monkeypatch: MonkeyPatch,
) -> None:
    ShortReadRawInputStream.entered.clear()
    ShortReadRawInputStream.aborted = False
    monkeypatch.setattr(
        "kyrin.audio.microphone.input.sd.RawInputStream", ShortReadRawInputStream
    )
    microphone = MicrophoneInput(5, AudioFormat(16000, 1, AudioSampleFormat.INT16), 512)
    finished = Event()

    def capture_one() -> None:
        assert list(microphone.capture()) == []
        finished.set()

    worker = Thread(target=capture_one)
    worker.start()
    assert ShortReadRawInputStream.entered.wait(1)

    microphone.stop_capture()
    worker.join(1)

    assert finished.is_set()
    assert not ShortReadRawInputStream.aborted


def test_stopped_microphone_cannot_silently_restart() -> None:
    microphone = MicrophoneInput(0, AudioFormat(16000, 1, AudioSampleFormat.INT16), 512)
    microphone.stop_capture()

    with pytest.raises(MicrophoneError, match="cannot be restarted"):
        list(microphone.capture())
