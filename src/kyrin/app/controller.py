"""Supervise one live-command session without owning UI or platform adapters."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import StrEnum
from threading import Event, Lock, Thread
from time import monotonic
from typing import Protocol, cast

from kyrin.app.permissions import PermissionPolicy
from kyrin.app.settings import AppSettings
from kyrin.runtime.listening_diagnostics import ListeningDiagnostics
from kyrin.runtime.voice_control import VoiceMode, VoiceModeChanged
from kyrin.system_power.flow import PowerAction, SystemPowerFlow


class RuntimeSession(Protocol):
    """The existing LiveCommandRuntime satisfies this small lifecycle boundary."""

    def run(self) -> None: ...

    def stop(self) -> None: ...


SessionFactory = Callable[[AppSettings], AbstractContextManager[RuntimeSession]]


class ApplicationState(StrEnum):
    STOPPED = "stopped"
    PAUSED = "paused"
    SETUP_REQUIRED = "setup_required"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ApplicationStatus:
    state: ApplicationState
    error: Exception | None = None


class ApplicationController:
    """Keep the UI responsive while one owned live session runs.

    The caller loads/saves preferences. The injected factory opens the STT
    engine, microphone pipeline, response speaker, and existing command
    runtime, then releases its owned resources when the context exits.
    Status is a snapshot the future UI can poll without touching the worker.
    """

    def __init__(
        self,
        factory: SessionFactory,
        system_power: SystemPowerFlow | None = None,
        *,
        start_in_standby: bool = False,
    ) -> None:
        self._factory = factory
        self._system_power = system_power
        self._lock = Lock()
        self._status = ApplicationStatus(ApplicationState.STOPPED)
        self._thread: Thread | None = None
        self._stop_thread: Thread | None = None
        self._session: RuntimeSession | None = None
        self._stop_requested = Event()
        self._start_in_standby = start_in_standby
        self._commands_active = not start_in_standby
        self._generation = 0
        self._diagnostics = ListeningDiagnostics()
        self._last_runtime_diagnostics: tuple[str, ...] = ()
        self._last_voice_state: VoiceModeChanged | None = None
        self._diagnostics.state(
            "application",
            "stopped",
            reason="constructed",
            source="startup",
        )

    def status(self) -> ApplicationStatus:
        with self._lock:
            if self._stop_thread is not None and self._stop_thread.is_alive():
                if self._status.state is ApplicationState.STOPPED:
                    return ApplicationStatus(ApplicationState.STOPPING)
            if self._status.state is ApplicationState.STOPPING and not any(
                thread is not None and thread.is_alive()
                for thread in (self._thread, self._stop_thread)
            ):
                return ApplicationStatus(
                    ApplicationState.ERROR
                    if self._status.error is not None
                    else ApplicationState.STOPPED,
                    self._status.error,
                )
            return self._status

    def start(
        self,
        settings: AppSettings,
        *,
        commands_active: bool | None = None,
    ) -> ApplicationStatus:
        """Begin listening if configured; never open audio for incomplete setup."""
        with self._lock:
            if self._system_power is not None:
                self._system_power.configure(
                    enabled=PermissionPolicy(settings).allows("system_power"),
                    permissions=PermissionPolicy(settings),
                )
            if (self._thread is not None and self._thread.is_alive()) or (
                self._stop_thread is not None and self._stop_thread.is_alive()
            ):
                raise RuntimeError("the previous listening session is still active")
            if not settings.listening_enabled:
                self._status = ApplicationStatus(ApplicationState.PAUSED)
                self._diagnostics.state(
                    "application",
                    "paused",
                    reason="listening_disabled",
                    source="settings",
                    generation=self._generation,
                )
                return self._status
            if settings.stt is None:
                self._status = ApplicationStatus(ApplicationState.SETUP_REQUIRED)
                self._diagnostics.state(
                    "application",
                    "setup_required",
                    reason="missing_stt",
                    source="settings",
                    generation=self._generation,
                )
                return self._status
            self._generation += 1
            self._last_voice_state = None
            self._last_runtime_diagnostics = ()
            self._commands_active = (
                not self._start_in_standby
                if commands_active is None
                else commands_active
            )
            self._stop_requested = Event()
            self._session = None
            self._status = ApplicationStatus(ApplicationState.STARTING)
            self._diagnostics.state(
                "application",
                "starting",
                reason="session_requested",
                source="startup" if commands_active is None else "restart",
                generation=self._generation,
            )
            thread = Thread(
                target=self._run_session,
                args=(settings, self._stop_requested),
                name="kyrin-application-session",
            )
            self._thread = thread
            thread.start()
            return self._status

    def _voice_state_locked(self) -> VoiceModeChanged | None:
        getter = getattr(self._session, "voice_mode_state", None)
        return (
            cast(VoiceModeChanged, getter())
            if getter is not None
            else self._last_voice_state
        )

    def event_belongs_to_session(self, session_id: str) -> bool:
        with self._lock:
            state = self._voice_state_locked()
            return state is not None and state.session_id == session_id

    def voice_event_is_current(self, event: VoiceModeChanged) -> bool:
        with self._lock:
            state = self._voice_state_locked()
            return bool(event.session_id) and event == state

    def listening_diagnostics(self) -> tuple[str, ...]:
        with self._lock:
            diagnostics = getattr(self._session, "listening_diagnostics", None)
            runtime = (
                diagnostics.snapshot()
                if isinstance(diagnostics, ListeningDiagnostics)
                else self._last_runtime_diagnostics
            )
            return (
                "KYRIN listening diagnostics L01-v2",
                *self._diagnostics.snapshot(),
                *runtime,
            )

    def commands_active(self) -> bool:
        with self._lock:
            state = self._voice_state_locked()
            if self._status.state not in (
                ApplicationState.RUNNING,
                ApplicationState.STARTING,
            ):
                return False
            return state.mode is VoiceMode.ACTIVE if state else self._commands_active

    def set_commands_active(
        self,
        active: bool,
        *,
        source: str = "controller",
        reason: str = "explicit_control",
    ) -> None:
        """Switch command routing while keeping the microphone session alive."""
        with self._lock:
            self._commands_active = active
            self._diagnostics.state(
                "command_request",
                "active" if active else "standby",
                source=source,
                reason=reason,
                generation=self._generation,
            )
            session = self._session
            if session is not None:
                setter = getattr(session, "set_commands_active", None)
                if setter is not None:
                    if getattr(session, "voice_mode_state", None) is not None:
                        setter(active, source=source, reason=reason)
                    else:
                        setter(active)

    def request_stop(
        self,
        *,
        source: str = "controller",
        reason: str = "stop_requested",
    ) -> None:
        """Request a stop without blocking a future graphical control thread."""
        with self._lock:
            self._commands_active = False
            self._diagnostics.state(
                "application",
                "stopping",
                source=source,
                reason=reason,
                generation=self._generation,
            )
            thread = self._thread
            if thread is None or not thread.is_alive():
                if self._status.state is not ApplicationState.ERROR and (
                    self._stop_thread is None or not self._stop_thread.is_alive()
                ):
                    self._status = ApplicationStatus(ApplicationState.STOPPED)
                    self._diagnostics.state(
                        "application",
                        "stopped",
                        reason="no_active_session",
                        source=source,
                        generation=self._generation,
                    )
                return
            self._stop_requested.set()
            self._status = ApplicationStatus(ApplicationState.STOPPING)
            session = self._session
            if session is None or (
                self._stop_thread is not None and self._stop_thread.is_alive()
            ):
                return
            stop_thread = Thread(
                target=self._stop_session,
                args=(session,),
                name="kyrin-application-stop",
                daemon=True,
            )
            self._stop_thread = stop_thread
            stop_thread.start()

    def respond_to_system_action(self, request_id: int, answer: str) -> bool:
        if self._system_power is not None:
            return self._system_power.respond(request_id, answer)
        with self._lock:
            session = self._session
        method = getattr(session, "respond_to_system_action", None)
        return bool(method(request_id, answer)) if method is not None else False

    def expire_system_action(self) -> None:
        if self._system_power is not None:
            self._system_power.expire()
            return
        with self._lock:
            session = self._session
        method = getattr(session, "expire_system_action", None)
        if method is not None:
            method()

    def request_system_action(self, action: PowerAction) -> bool:
        return (
            self._system_power.start(action)
            if self._system_power is not None
            else False
        )

    def preview_system_action(self, action: PowerAction) -> bool:
        return (
            self._system_power.start_preview(action)
            if self._system_power is not None
            else False
        )

    def wait_until_stopped(self, timeout_s: float | None = None) -> bool:
        """Allow an application shutdown path to wait for complete cleanup."""
        if timeout_s is not None and timeout_s < 0:
            raise ValueError("timeout_s must be nonnegative")
        with self._lock:
            threads = (self._thread, self._stop_thread)
        deadline = None if timeout_s is None else monotonic() + timeout_s
        for thread in threads:
            if thread is not None:
                remaining = (
                    None if deadline is None else max(0.0, deadline - monotonic())
                )
                thread.join(remaining)
        return all(thread is None or not thread.is_alive() for thread in threads)

    def _run_session(self, settings: AppSettings, stop_requested: Event) -> None:
        try:
            with self._factory(settings) as session:
                with self._lock:
                    self._session = session
                    setter = getattr(session, "set_commands_active", None)
                    if setter is not None:
                        if getattr(session, "voice_mode_state", None) is not None:
                            setter(
                                self._commands_active,
                                source="controller",
                                reason="session_mode_restored",
                            )
                        else:
                            setter(self._commands_active)
                    cancelled = stop_requested.is_set()
                    if not cancelled:
                        self._status = ApplicationStatus(ApplicationState.RUNNING)
                        self._diagnostics.state(
                            "application",
                            "running",
                            reason="session_opened",
                            source="controller",
                            generation=self._generation,
                        )
                if cancelled:
                    session.stop()
                else:
                    session.run()
        except Exception as exc:
            # The thread boundary must preserve unexpected adapter failures
            # for the UI instead of silently losing them in a worker thread.
            with self._lock:
                self._status = ApplicationStatus(ApplicationState.ERROR, exc)
                self._diagnostics.state(
                    "application",
                    "error",
                    reason=type(exc).__name__,
                    source="error",
                    generation=self._generation,
                )
        else:
            with self._lock:
                if self._status.error is not None:
                    self._status = ApplicationStatus(
                        ApplicationState.ERROR, self._status.error
                    )
                else:
                    self._status = ApplicationStatus(ApplicationState.STOPPED)
                self._diagnostics.state(
                    "application",
                    self._status.state.value,
                    reason="session_returned",
                    source="controller",
                    generation=self._generation,
                )
        finally:
            with self._lock:
                self._last_voice_state = self._voice_state_locked()
                diagnostics = getattr(self._session, "listening_diagnostics", None)
                if isinstance(diagnostics, ListeningDiagnostics):
                    self._last_runtime_diagnostics = diagnostics.snapshot()
                self._session = None

    def _stop_session(self, session: RuntimeSession) -> None:
        try:
            session.stop()
        except Exception as exc:
            # A failed stop must remain visible while run() may still be active.
            with self._lock:
                self._status = ApplicationStatus(ApplicationState.STOPPING, exc)
                self._diagnostics.state(
                    "application",
                    "stop_failed",
                    reason=type(exc).__name__,
                    source="error",
                    generation=self._generation,
                )
