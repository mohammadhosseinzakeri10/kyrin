"""Finite files preserve turn boundaries without real-time replay."""

import wave
from pathlib import Path
from time import monotonic

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.file_input import FILE_AUDIO_FORMAT, AudioFileInput
from kyrin.audio.file_speech_pipeline import FileSpeechPipeline
from kyrin.stt.device import ComputeDevice
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


def test_file_is_processed_faster_than_playback_and_keeps_turn(tmp_path: Path) -> None:
    path = tmp_path / "command.wav"
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\x01\x00" * 16000 + b"\0\0" * 8000)

    class Detector:
        input_format = FILE_AUDIO_FORMAT
        frames_per_window = 160

        def reset(self) -> None:
            pass

        def detect(self, chunk: AudioData) -> bool:
            return any(chunk.data)

    class Session:
        input_format = FILE_AUDIO_FORMAT
        compute_device = ComputeDevice.CPU
        supports_partial_updates = False

        def __init__(self) -> None:
            self.bytes_seen = 0
            self.started = 0
            self.ended = 0
            self.closed = False

        def start_turn(self):  # type: ignore[no-untyped-def]
            self.started += 1
            return ()

        def accept_audio(self, chunk: AudioData):  # type: ignore[no-untyped-def]
            self.bytes_seen += len(chunk.data)
            return ()

        def end_turn(self):  # type: ignore[no-untyped-def]
            self.ended += 1
            return (TranscriptUpdate(0, "Open Telegram", TranscriptStatus.FINAL),)

        def finish(self):  # type: ignore[no-untyped-def]
            return ()

        def close(self) -> None:
            self.closed = True

    class Engine:
        def __init__(self) -> None:
            self.session = Session()

        def open_session(self, options):  # type: ignore[no-untyped-def]
            return self.session

    engine = Engine()
    pipeline = FileSpeechPipeline(AudioFileInput(path), Detector(), engine)  # type: ignore[arg-type]
    started = monotonic()
    with pipeline.open() as stream:
        events = list(stream)
    assert monotonic() - started < 1.25
    assert engine.session.bytes_seen == 48000
    assert (engine.session.started, engine.session.ended) == (1, 1)
    assert engine.session.closed
    assert any(
        isinstance(event, TranscriptUpdate)
        and event.text == "Open Telegram"
        and event.status is TranscriptStatus.FINAL
        for event in events
    )


def test_streaming_backend_receives_continuous_resampled_audio(tmp_path: Path) -> None:
    path = tmp_path / "voice.wav"
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\x01\x00" * 16000)

    class Detector:
        input_format = FILE_AUDIO_FORMAT
        frames_per_window = 160

        def reset(self) -> None:
            pass

        def detect(self, chunk: AudioData) -> bool:
            return True

    class Session:
        input_format = AudioFormat(8000, 1, AudioSampleFormat.INT16)
        compute_device = ComputeDevice.CPU
        supports_partial_updates = False

        def __init__(self) -> None:
            self.frames = 0

        def accept_audio(self, chunk: AudioData):  # type: ignore[no-untyped-def]
            assert chunk.audio_format == self.input_format
            self.frames += len(chunk.data) // 2
            return ()

        def finish(self):  # type: ignore[no-untyped-def]
            return ()

        def close(self) -> None:
            pass

    class Engine:
        def __init__(self) -> None:
            self.session = Session()

        def open_session(self, options):  # type: ignore[no-untyped-def]
            return self.session

    engine = Engine()
    pipeline = FileSpeechPipeline(AudioFileInput(path), Detector(), engine)  # type: ignore[arg-type]
    with pipeline.open() as stream:
        list(stream)
    assert engine.session.frames == 8000
