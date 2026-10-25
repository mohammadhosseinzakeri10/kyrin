"""A command model must not turn idle silence into an STT backlog failure."""

from collections.abc import Callable, Iterator
from threading import Event, Thread

import pytest

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_errors import AudioQueueOverflowError
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.live_speech_pipeline import LiveSpeechPipeline
from kyrin.model_resources import MemorySnapshot, ModelResources, Workload
from kyrin.stt.backends.whisper import WhisperSession
from kyrin.stt.capabilities import SpeechToTextCapabilities
from kyrin.stt.contracts import SpeechToTextSession
from kyrin.stt.device import ComputeDevice, SpeechToTextOptions
from kyrin.stt.resources import ManagedSttEngine

FORMAT = AudioFormat(16000, 1, AudioSampleFormat.INT16)


@pytest.mark.parametrize("speech", [False, True])
def test_model_wait_does_not_queue_idle_silence_but_still_bounds_speech(
    speech: bool,
) -> None:
    source_ready = Event()
    command_admitted = Event()
    all_audio_observed = Event()
    errors: list[Exception] = []
    source_stopped = Event()
    resources = ModelResources(memory=lambda: MemorySnapshot())

    class Source:
        def capture(self) -> Iterator[AudioData]:
            yield AudioData(bytes(320 * 100), FORMAT)  # One second, no real clock.

        def stop_capture(self) -> None:
            source_stopped.set()

    class Detector:
        input_format = FORMAT
        frames_per_window = 160
        observed = 0

        def detect(self, window: AudioData) -> bool:
            self.observed += 1
            if self.observed == 100:
                all_audio_observed.set()
            return speech

        def reset(self) -> None:
            self.observed = 0

    class Engine:
        capabilities = SpeechToTextCapabilities(
            frozenset({ComputeDevice.CPU}),
            frozenset({"en"}),
            True,
            False,
        )

        def open_session(self, options: SpeechToTextOptions) -> SpeechToTextSession:
            return WhisperSession(lambda *_: "", "en", lambda: None)

        def close(self) -> None:
            pass

    engine = ManagedSttEngine(Engine, resources, "synthetic-stt")

    def ready() -> None:
        source_ready.set()
        assert command_admitted.wait(2)

    pipeline = LiveSpeechPipeline(
        Source(),
        FORMAT,
        Detector(),
        engine,
        start_confirm_ms=10,
        pause_confirm_ms=10,
        backlog_warning_ms=50,
        backlog_recovery_ms=10,
        backlog_maximum_ms=100,
        on_audio_ready=ready,
        idle_preroll_ms=20,
    )

    def run() -> None:
        try:
            with pipeline.open() as stream:
                list(stream)
        except Exception as exc:
            errors.append(exc)

    runner = Thread(target=run)
    runner.start()
    try:
        assert source_ready.wait(2)
        with resources.use(Workload.COMMAND, "synthetic-command"):
            command_admitted.set()
            all_audio_observed.wait(1)
        runner.join(3)
        assert not runner.is_alive()
        if speech:
            assert len(errors) == 1
            assert isinstance(errors[0], AudioQueueOverflowError)
            assert errors[0].buffer == "stt_backlog"
            assert errors[0].limit == 100
            assert errors[0].pending is not None and errors[0].pending > 100
            assert errors[0].unit == "ms"
        else:
            assert errors == []
            assert all_audio_observed.is_set()
        assert source_stopped.is_set()
    finally:
        command_admitted.set()
        runner.join(3)
        engine.close()


def windowed_pipeline(
    infer: Callable[[bytes, str], str],
    decisions: list[bool],
    *,
    start_confirm_ms: int = 10,
    pause_confirm_ms: int = 10,
    idle_preroll_ms: int = 20,
) -> tuple[LiveSpeechPipeline, list[bytes]]:
    pcm = [bytes([i + 1, 0]) * 160 for i in range(len(decisions))]

    class Source:
        def capture(self) -> Iterator[AudioData]:
            yield AudioData(b"".join(pcm), FORMAT)

        def stop_capture(self) -> None:
            pass

    class Detector:
        input_format = FORMAT
        frames_per_window = 160

        def reset(self) -> None:
            self.decisions = iter(decisions)

        def detect(self, window: AudioData) -> bool:
            return next(self.decisions)

    class Engine:
        capabilities = SpeechToTextCapabilities(
            frozenset({ComputeDevice.CPU}),
            frozenset({"en"}),
            True,
            False,
        )

        def open_session(self, options: SpeechToTextOptions) -> SpeechToTextSession:
            return WhisperSession(infer, "en", lambda: None, emit_partials=False)

        def close(self) -> None:
            pass

    return LiveSpeechPipeline(
        Source(),
        FORMAT,
        Detector(),
        Engine(),
        start_confirm_ms=start_confirm_ms,
        pause_confirm_ms=pause_confirm_ms,
        idle_preroll_ms=idle_preroll_ms,
    ), pcm


def test_gaps_keep_preroll_onset_and_confirmed_pause_audio_in_both_turns() -> None:
    inferred: list[bytes] = []

    def infer(pcm: bytes, language: str) -> str:
        inferred.append(pcm)
        return "hello"

    decisions = [False] * 5 + [True] * 3 + [False] * 2
    decisions += [False] * 5 + [True] * 2 + [False] * 2
    pipeline, pcm = windowed_pipeline(
        infer,
        decisions,
        start_confirm_ms=20,
        pause_confirm_ms=20,
        idle_preroll_ms=30,
    )
    with pipeline.open() as stream:
        list(stream)
    assert inferred == [b"".join(pcm[4:10]), b"".join(pcm[14:19])]


def test_gaps_preserve_explicit_listening_controls() -> None:
    from kyrin.runtime.command_runtime import LiveCommandRuntime
    from kyrin.runtime.speech_sessions import SpeechSessionController
    from kyrin.runtime.voice_control import VoiceMode, VoiceModeChanged

    controls = iter(
        ("start listening", "stop listening", "start listening", "turn microphone off")
    )
    pipeline, _ = windowed_pipeline(
        lambda *_: next(controls),
        ([False] * 10 + [True] * 3 + [False]) * 4,
    )
    modes: list[VoiceModeChanged] = []
    runtime = LiveCommandRuntime(
        SpeechSessionController(lambda: pipeline),
        coordinator=None,
        gate=None,
        observer=None,
        executor=None,
        on_live_event=lambda _: None,
        on_command_event=lambda _: None,
        on_action_output=lambda _: None,
        on_session_end=lambda _: None,
        voice_standby=True,
        on_voice_mode=modes.append,
    )
    runtime.run()
    assert [event.mode for event in modes] == [
        VoiceMode.ACTIVE,
        VoiceMode.STANDBY,
        VoiceMode.ACTIVE,
        VoiceMode.OFF,
    ]


@pytest.mark.parametrize("preroll", [9, 5000])
def test_preroll_must_cover_confirmation_and_fit_the_bounded_backlog(
    preroll: int,
) -> None:
    with pytest.raises(ValueError, match="idle preroll"):
        windowed_pipeline(lambda *_: "", [], idle_preroll_ms=preroll)
