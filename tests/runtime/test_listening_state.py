"""Listening intent is independent of backend lifecycle and queued controls."""

from collections.abc import Generator
from pathlib import Path

import pytest

from kyrin.audio.audio_errors import AudioQueueOverflowError
from kyrin.runtime.command_runtime import LiveCommandRuntime
from kyrin.runtime.listening_diagnostics import ListeningDiagnostics
from kyrin.runtime.speech_sessions import SpeechRuntimeEvent, SpeechSessionEnded
from kyrin.runtime.voice_control import VoiceMode, VoiceModeChanged, control_phrase
from kyrin.stt.errors import SpeechToTextError
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


class Source:
    def __init__(self, events: tuple[SpeechRuntimeEvent, ...] = ()) -> None:
        self.updates = events

    def events(self) -> Generator[SpeechRuntimeEvent]:
        yield from self.updates

    def stop(self) -> None:
        pass


def make_runtime(
    source: Source,
    modes: list[VoiceModeChanged],
    *,
    standby: bool = False,
) -> LiveCommandRuntime:
    return LiveCommandRuntime(
        source,
        coordinator=None,
        gate=None,
        observer=None,
        executor=None,
        on_live_event=lambda _: None,
        on_command_event=lambda _: None,
        on_action_output=lambda _: None,
        on_session_end=lambda _: None,
        voice_standby=standby,
        on_voice_mode=modes.append,
        clock_ns=lambda: 100,
    )


@pytest.mark.parametrize(
    "text",
    [
        "don't stop listening",
        "do not stop listening",
        "I said stop listening",
        '"Stop listening"',
        "«Stop listening»",
        "‘Stop listening’",
        "گوش دادن را متوقف نکن",
        "استاپ لیسنینگ",
        "stop listning",
        "start listning",
        "turn microfon off",
        "ordinary private conversation",
    ],
)
def test_only_explicit_whole_controls(text: str) -> None:
    assert control_phrase(text, active=True) is None
    modes: list[VoiceModeChanged] = []
    runtime = make_runtime(
        Source(
            (
                TranscriptUpdate(0, text, TranscriptStatus.FINAL),
                TranscriptUpdate(1, "stop listening", TranscriptStatus.PARTIAL),
            )
        ),
        modes,
    )
    runtime.run()
    assert runtime.voice_mode_state().mode is VoiceMode.ACTIVE
    assert modes == []
    assert text not in "\n".join(runtime.listening_diagnostics.snapshot())


@pytest.mark.parametrize("standby", [False, True])
def test_backend_retry_and_segment_end_preserve_authorized_mode(standby: bool) -> None:
    modes: list[VoiceModeChanged] = []
    runtime = make_runtime(
        Source(
            (
                TranscriptUpdate(0, "private words", TranscriptStatus.FINAL),
                SpeechSessionEnded(0, SpeechToTextError("private backend message"), 0),
                TranscriptUpdate(0, "another segment", TranscriptStatus.FINAL),
                SpeechSessionEnded(1, None),
            )
        ),
        modes,
        standby=standby,
    )
    runtime.run()
    assert runtime.voice_mode_state().mode is (
        VoiceMode.STANDBY if standby else VoiceMode.ACTIVE
    )
    assert modes == []
    report = "\n".join(runtime.listening_diagnostics.snapshot())
    assert "retrying" in report and "gen=1" in report
    assert "private" not in report


def test_queued_control_produced_before_gui_request_is_ignored() -> None:
    modes: list[VoiceModeChanged] = []
    runtime = make_runtime(Source(), modes)
    runtime.set_commands_active(True)
    runtime._control_speech(
        TranscriptUpdate(
            0,
            "stop listening",
            TranscriptStatus.FINAL,
            emitted_ns=99,
        )
    )
    assert runtime.voice_mode_state().mode is VoiceMode.ACTIVE
    assert modes == []
    runtime._control_speech(
        TranscriptUpdate(
            1,
            "stop listening",
            TranscriptStatus.FINAL,
            emitted_ns=101,
        )
    )
    assert runtime.voice_mode_state().mode is VoiceMode.STANDBY
    assert modes[0].previous is VoiceMode.ACTIVE
    assert modes[0].source == "voice"
    assert modes[0].segment_id == 1
    assert modes[0].session_id == runtime.listening_diagnostics.session_id


def test_off_is_terminal_until_controller_stops_capture() -> None:
    modes: list[VoiceModeChanged] = []
    runtime = make_runtime(
        Source(
            (
                TranscriptUpdate(0, "turn microphone off", TranscriptStatus.FINAL),
                TranscriptUpdate(1, "start listening", TranscriptStatus.FINAL),
            )
        ),
        modes,
    )
    runtime.run()
    assert [event.mode for event in modes] == [VoiceMode.OFF]


def test_diagnostics_are_bounded_and_do_not_persist(tmp_path: Path) -> None:
    diagnostics = ListeningDiagnostics()
    for index in range(200):
        diagnostics.state("mode", str(index), reason="test", source="test")
        diagnostics.pulse("capture")
    report = diagnostics.snapshot()
    assert len(report) == 67
    assert "capture=200/age=" in report[-1]
    assert list(tmp_path.iterdir()) == []


def test_terminal_stt_error_does_not_become_a_stop_control() -> None:
    class FailingSource(Source):
        def events(self) -> Generator[SpeechRuntimeEvent]:
            raise SpeechToTextError("private backend details")
            yield from ()

    modes: list[VoiceModeChanged] = []
    runtime = make_runtime(FailingSource(), modes)
    with pytest.raises(SpeechToTextError):
        runtime.run()
    assert runtime.voice_mode_state().mode is VoiceMode.ACTIVE
    assert modes == []
    assert "private" not in "\n".join(runtime.listening_diagnostics.snapshot())


def test_worker_error_and_overload_do_not_change_mode() -> None:
    modes: list[VoiceModeChanged] = []
    runtime = make_runtime(Source(), modes)
    runtime._understanding_overload(
        TranscriptUpdate(0, "private utterance", TranscriptStatus.FINAL)
    )
    runtime._understanding_failed()
    assert runtime.voice_mode_state().mode is VoiceMode.ACTIVE
    assert modes == []
    report = "\n".join(runtime.listening_diagnostics.snapshot())
    assert "understanding_overload=1" in report
    assert "worker_error" in report
    assert "private" not in report


def test_overflow_trace_has_stage_and_limits_without_private_error_message() -> None:
    modes: list[VoiceModeChanged] = []
    runtime = make_runtime(
        Source(
            (
                SpeechSessionEnded(
                    0,
                    AudioQueueOverflowError(
                        "PRIVATE_BACKEND_DETAILS",
                        buffer="stt_backlog",
                        pending=5010,
                        limit=5000,
                        unit="ms",
                    ),
                    1,
                ),
            )
        ),
        modes,
    )
    runtime.run()
    report = "\n".join(runtime.listening_diagnostics.snapshot())
    assert "stt_backlog pending=5010 limit=5000 unit=ms" in report
    assert "PRIVATE_BACKEND_DETAILS" not in report
    assert runtime.voice_mode_state().mode is VoiceMode.ACTIVE
    assert modes == []
