"""Supervise one live-command session without owning UI or platform adapters."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import StrEnum
from threading import Event, Lock, Thread
from time import monotonic
from typing import Protocol

from kyrin.app.settings import AppSettings
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

    def start(self, settings: AppSettings) -> ApplicationStatus:
        """Begin listening if configured; never open audio for incomplete setup."""
        with self._lock:
            if self._system_power is not None:
                self._system_power.configure(
                    enabled=(
                        settings.action_execution_enabled
                        and settings.system_power_enabled
                    )
                )
            if (self._thread is not None and self._thread.is_alive()) or (
                self._stop_thread is not None and self._stop_thread.is_alive()
            ):
                raise RuntimeError("the previous listening session is still active")
            if not settings.listening_enabled:
                self._status = ApplicationStatus(ApplicationState.PAUSED)
                return self._status
            if settings.stt is None:
                self._status = ApplicationStatus(ApplicationState.SETUP_REQUIRED)
                return self._status
            self._commands_active = not self._start_in_standby
            self._stop_requested = Event()
            self._session = None
            self._status = ApplicationStatus(ApplicationState.STARTING)
            thread = Thread(
                target=self._run_session,
                args=(settings, self._stop_requested),
                name="kyrin-application-session",
            )
            self._thread = thread
            thread.start()
            return self._status

    def commands_active(self) -> bool:
        with self._lock:
            return self._commands_active

    def set_commands_active(self, active: bool) -> None:
        """Switch command routing while keeping the microphone session alive."""
        with self._lock:
            self._commands_active = active
            session = self._session
            if session is not None:
                setter = getattr(session, "set_commands_active", None)
                if setter is not None:
                    setter(active)

    def request_stop(self) -> None:
        """Request a stop without blocking a future graphical control thread."""
        with self._lock:
            self._commands_active = False
            thread = self._thread
            if thread is None or not thread.is_alive():
                if self._status.state is not ApplicationState.ERROR and (
                    self._stop_thread is None or not self._stop_thread.is_alive()
                ):
                    self._status = ApplicationStatus(ApplicationState.STOPPED)
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
                        setter(self._commands_active)
                    cancelled = stop_requested.is_set()
                    if not cancelled:
                        self._status = ApplicationStatus(ApplicationState.RUNNING)
                if cancelled:
                    session.stop()
                else:
                    session.run()
        except Exception as exc:
            # The thread boundary must preserve unexpected adapter failures
            # for the UI instead of silently losing them in a worker thread.
            with self._lock:
                self._status = ApplicationStatus(ApplicationState.ERROR, exc)
        else:
            with self._lock:
                if self._status.error is not None:
                    self._status = ApplicationStatus(
                        ApplicationState.ERROR, self._status.error
                    )
                else:
                    self._status = ApplicationStatus(ApplicationState.STOPPED)
        finally:
            with self._lock:
                self._session = None

    def _stop_session(self, session: RuntimeSession) -> None:
        try:
            session.stop()
        except Exception as exc:
            # A failed stop must remain visible while run() may still be active.
            with self._lock:
                self._status = ApplicationStatus(ApplicationState.STOPPING, exc)
