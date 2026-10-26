"""Controller observes runtime intent without replaying queued GUI events."""

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Event

from kyrin.app.controller import ApplicationController, RuntimeSession
from kyrin.app.settings import AppSettings, SttSelection
from kyrin.runtime.command_runtime import LiveCommandRuntime
from kyrin.runtime.speech_sessions import SpeechRuntimeEvent
from kyrin.runtime.voice_control import VoiceMode, VoiceModeChanged
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


def test_runtime_is_authoritative_and_old_events_cannot_override_gui(
    tmp_path: Path,
) -> None:
    modes: list[VoiceModeChanged] = []
    runtimes: list[LiveCommandRuntime] = []
    running = Event()
    stopped = Event()

    class Source:
        def events(self) -> Generator[SpeechRuntimeEvent]:
            running.set()
            assert stopped.wait(3)
            yield from ()

        def stop(self) -> None:
            stopped.set()

    @contextmanager
    def factory(_settings: AppSettings) -> Iterator[RuntimeSession]:
        runtime = LiveCommandRuntime(
            Source(),
            coordinator=None,
            gate=None,
            observer=None,
            executor=None,
            on_live_event=lambda _: None,
            on_command_event=lambda _: None,
            on_action_output=lambda _: None,
            on_session_end=lambda _: None,
            on_voice_mode=modes.append,
            voice_standby=True,
        )
        runtimes.append(runtime)
        yield runtime

    controller = ApplicationController(factory, start_in_standby=True)
    settings = AppSettings(stt=SttSelection("vosk", tmp_path / "model", "en"))
    controller.start(settings)
    try:
        assert running.wait(2)
        runtime = runtimes[-1]
        runtime._control_speech(
            TranscriptUpdate(
                0,
                "start listening",
                TranscriptStatus.FINAL,
            )
        )
        assert controller.commands_active()  # No Qt event processing required.
        runtime._control_speech(
            TranscriptUpdate(
                1,
                "stop listening",
                TranscriptStatus.FINAL,
            )
        )
        standby = modes[-1]
        assert not controller.commands_active()
        assert controller.voice_event_is_current(standby)
        controller.set_commands_active(True)
        assert controller.commands_active()
        assert not controller.voice_event_is_current(standby)
        assert not controller.voice_event_is_current(VoiceModeChanged(VoiceMode.OFF))
        controller.request_stop(source="restart", reason="settings_changed")
        assert controller.wait_until_stopped(2)
        running.clear()
        stopped.clear()
        controller.start(settings, commands_active=True)
        assert running.wait(2)
        assert controller.commands_active()
        assert not controller.voice_event_is_current(standby)
        assert runtimes[-1].voice_mode_state().session_id != standby.session_id
    finally:
        controller.request_stop()
        assert controller.wait_until_stopped(2)
