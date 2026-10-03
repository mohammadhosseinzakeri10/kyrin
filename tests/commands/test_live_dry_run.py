"""Replay one live VAD/STT stream through command decisions without hardware."""

from collections.abc import Iterator, Sequence

from kyrin.audio.activity.speech_activity_monitor import SpeechActivityFrame
from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.live_speech_pipeline import LiveSpeechPipeline
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import (
    CommandCandidateUpdate,
    CommandEvent,
    CommandIntent,
    CommandKind,
    CommandResolution,
)
from kyrin.stt.capabilities import SpeechToTextCapabilities
from kyrin.stt.device import ComputeDevice, SpeechToTextOptions
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate

FORMAT = AudioFormat(16000, 1, AudioSampleFormat.INT16)


class Source:
    def capture(self) -> Iterator[AudioData]:
        for index in range(3):
            yield AudioData(bytes([index + 1, 0]) * 160, FORMAT)

    def stop_capture(self) -> None:
        pass


class Detector:
    input_format = FORMAT
    frames_per_window = 160

    def __init__(self) -> None:
        self.observations = iter((True, False, False))

    def detect(self, window: AudioData) -> bool:
        return next(self.observations)

    def reset(self) -> None:
        pass


class Session:
    input_format = FORMAT
    compute_device = ComputeDevice.CPU
    supports_partial_updates = True

    def __init__(self) -> None:
        self.accepted = 0
        self.closed = False

    def accept_audio(self, chunk: AudioData) -> Sequence[TranscriptUpdate]:
        self.accepted += 1
        text = "تلگرام را باز کن" if self.accepted < 3 else "تلگرام را باز نکن"
        return (TranscriptUpdate(0, text, TranscriptStatus.PARTIAL, "fa"),)

    def finish(self) -> Sequence[TranscriptUpdate]:
        return (TranscriptUpdate(0, "تلگرام را باز نکن", TranscriptStatus.FINAL, "fa"),)

    def close(self) -> None:
        self.closed = True


class Engine:
    capabilities: SpeechToTextCapabilities

    def __init__(self, session: Session) -> None:
        self.session = session

    def open_session(self, options: SpeechToTextOptions) -> Session:
        return self.session

    def close(self) -> None:
        pass


def test_live_partial_correction_retracts_without_executing_anything() -> None:
    session = Session()
    pipeline = LiveSpeechPipeline(
        Source(),
        FORMAT,
        Detector(),
        Engine(session),
        start_confirm_ms=1,
        pause_confirm_ms=1,
    )
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    decisions: list[CommandEvent] = []
    activity: list[SpeechActivityFrame] = []
    with pipeline.open() as stream:
        for event in stream:
            if isinstance(event, SpeechActivityFrame):
                activity.append(event)
            elif isinstance(event, TranscriptUpdate):
                decisions.extend(coordinator.observe(event))

    assert len(activity) == 2  # start and pause, neither ends the STT session
    assert decisions == [
        CommandCandidateUpdate(0, CommandIntent(CommandKind.OPEN_APP, "telegram")),
        CommandCandidateUpdate(0, None),
        CommandResolution(0, None),
    ]
    assert session.accepted == 3
    assert session.closed
