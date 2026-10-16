"""The application controls a session without a microphone or desktop UI."""

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread

import pytest

from kyrin.app.controller import (
    ApplicationController,
    ApplicationState,
    RuntimeSession,
)
from kyrin.app.settings import AppSettings, SttSelection
from kyrin.audio.live_speech_pipeline import LiveSpeechEvent
from kyrin.runtime.command_runtime import LiveCommandRuntime
from kyrin.runtime.speech_sessions import SpeechRuntimeEvent
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


def _configured_settings(tmp_path: Path) -> AppSettings:
    return AppSettings(stt=SttSelection("whisper", tmp_path / "model.bin", "en"))


class FakeSession:
    def __init__(self) -> None:
        self.running = Event()
        self.finished = Event()
        self.stop_called = Event()

    def run(self) -> None:
        self.running.set()
        assert self.finished.wait(2), "test session was not stopped"

    def stop(self) -> None:
        self.stop_called.set()
        self.finished.set()


def test_paused_or_unconfigured_app_never_constructs_audio(tmp_path: Path) -> None:
    calls: list[AppSettings] = []

    @contextmanager
    def factory(settings: AppSettings) -> Iterator[RuntimeSession]:
        calls.append(settings)
        yield FakeSession()

    controller = ApplicationController(factory)
    paused = replace(_configured_settings(tmp_path), listening_enabled=False)
    assert controller.start(paused).state is ApplicationState.PAUSED
    assert controller.start(AppSettings()).state is ApplicationState.SETUP_REQUIRED
    assert calls == []
    controller.request_stop()
    assert controller.status().state is ApplicationState.STOPPED


def test_start_stop_cleanup_and_restart_without_duplicate_session(
    tmp_path: Path,
) -> None:
    sessions: list[FakeSession] = []
    closed: list[FakeSession] = []

    @contextmanager
    def factory(settings: AppSettings) -> Iterator[RuntimeSession]:
        assert settings.stt is not None
        session = FakeSession()
        sessions.append(session)
        try:
            yield session
        finally:
            closed.append(session)

    controller = ApplicationController(factory)
    settings = _configured_settings(tmp_path)
    controller.start(settings)
    assert sessions[0].running.wait(1)
    assert controller.status().state is ApplicationState.RUNNING
    with pytest.raises(RuntimeError, match="still active"):
        controller.start(settings)

    controller.request_stop()
    assert controller.wait_until_stopped(2)
    assert sessions[0].stop_called.is_set()
    assert closed == sessions[:1]
    assert controller.status().state is ApplicationState.STOPPED

    controller.start(settings)
    assert sessions[1].running.wait(1)
    controller.request_stop()
    assert controller.wait_until_stopped(2)
    assert closed == sessions


def test_standby_session_switches_command_routing_without_stopping_audio(
    tmp_path: Path,
) -> None:
    modes: list[bool] = []

    class ModeSession(FakeSession):
        def set_commands_active(self, active: bool) -> None:
            modes.append(active)

    sessions: list[ModeSession] = []
    created = Event()

    @contextmanager
    def factory(_settings: AppSettings) -> Iterator[RuntimeSession]:
        session = ModeSession()
        sessions.append(session)
        created.set()
        yield session

    controller = ApplicationController(factory, start_in_standby=True)
    controller.start(_configured_settings(tmp_path))
    assert created.wait(1)
    assert sessions[0].running.wait(1)
    assert modes == [False]
    controller.set_commands_active(True)
    assert controller.commands_active()
    controller.set_commands_active(False)
    assert not controller.commands_active()
    assert not sessions[0].stop_called.is_set()
    assert modes == [False, True, False]
    controller.request_stop()
    assert controller.wait_until_stopped(2)


def test_controller_runs_existing_command_runtime_without_hardware(
    tmp_path: Path,
) -> None:
    seen: list[LiveSpeechEvent] = []
    delivered = Event()
    stopped = Event()

    class Source:
        def events(self) -> Generator[SpeechRuntimeEvent]:
            yield TranscriptUpdate(0, "hello", TranscriptStatus.FINAL, "en")
            assert stopped.wait(2)

        def stop(self) -> None:
            stopped.set()

    def on_live(event: LiveSpeechEvent) -> None:
        seen.append(event)
        delivered.set()

    @contextmanager
    def factory(settings: AppSettings) -> Iterator[RuntimeSession]:
        runtime = LiveCommandRuntime(
            Source(),
            coordinator=None,
            gate=None,
            observer=None,
            executor=None,
            on_live_event=on_live,
            on_command_event=lambda event: None,
            on_action_output=lambda event: None,
            on_session_end=lambda event: None,
        )
        yield runtime

    controller = ApplicationController(factory)
    controller.start(_configured_settings(tmp_path))
    assert delivered.wait(1)
    controller.request_stop()
    assert controller.wait_until_stopped(2)
    assert seen == [TranscriptUpdate(0, "hello", TranscriptStatus.FINAL, "en")]
    assert controller.status().state is ApplicationState.STOPPED


def test_stop_during_slow_setup_never_begins_capture(tmp_path: Path) -> None:
    entered_factory = Event()
    finish_factory = Event()
    session = FakeSession()

    @contextmanager
    def factory(settings: AppSettings) -> Iterator[RuntimeSession]:
        entered_factory.set()
        assert finish_factory.wait(2)
        yield session

    controller = ApplicationController(factory)
    controller.start(_configured_settings(tmp_path))
    assert entered_factory.wait(1)

    controller.request_stop()
    finish_factory.set()

    assert controller.wait_until_stopped(2)
    assert session.stop_called.is_set()
    assert not session.running.is_set()
    assert controller.status().state is ApplicationState.STOPPED


def test_stop_request_does_not_wait_for_slow_audio_shutdown(tmp_path: Path) -> None:
    release_stop = Event()
    entered_stop = Event()

    class SlowStopSession(FakeSession):
        def stop(self) -> None:
            entered_stop.set()
            assert release_stop.wait(2)
            super().stop()

    session = SlowStopSession()

    @contextmanager
    def factory(settings: AppSettings) -> Iterator[RuntimeSession]:
        yield session

    controller = ApplicationController(factory)
    controller.start(_configured_settings(tmp_path))
    assert session.running.wait(1)

    caller = Thread(target=controller.request_stop)
    try:
        caller.start()
        caller.join(0.5)
        assert not caller.is_alive(), "stop request blocked the control thread"
        assert entered_stop.wait(1)
        assert controller.status().state is ApplicationState.STOPPING
    finally:
        release_stop.set()
        caller.join(1)
        assert controller.wait_until_stopped(2)

    assert controller.status().state is ApplicationState.STOPPED


def test_missing_model_or_runtime_failure_is_visible_and_resources_close(
    tmp_path: Path,
) -> None:
    closed = Event()

    @contextmanager
    def missing_model(settings: AppSettings) -> Iterator[RuntimeSession]:
        raise FileNotFoundError("selected model is missing")
        yield FakeSession()

    controller = ApplicationController(missing_model)
    controller.start(_configured_settings(tmp_path))
    assert controller.wait_until_stopped(2)
    status = controller.status()
    assert status.state is ApplicationState.ERROR
    assert isinstance(status.error, FileNotFoundError)

    class BrokenSession(FakeSession):
        def run(self) -> None:
            raise RuntimeError("model server stopped")

    @contextmanager
    def broken_runtime(settings: AppSettings) -> Iterator[RuntimeSession]:
        try:
            yield BrokenSession()
        finally:
            closed.set()

    controller = ApplicationController(broken_runtime)
    controller.start(_configured_settings(tmp_path))
    assert controller.wait_until_stopped(2)
    assert closed.is_set()
    assert controller.status().state is ApplicationState.ERROR
    assert isinstance(controller.status().error, RuntimeError)
