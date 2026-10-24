"""One absolute budget across synchronous calls, Qt work and owned processes.

Context-local propagation keeps observation contracts independent of actions.
Cross-thread callers must explicitly carry the Operation object. Cancellation
never means rollback; an interrupted actuator has an unknown outcome.
"""

from __future__ import annotations

import os
import select
import signal
import socket
import subprocess
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Event
from time import monotonic
from typing import Any


class OperationStopped(RuntimeError):
    """The shared deadline expired or the operation was cancelled."""


@dataclass
class Operation:
    deadline: float
    clock: Callable[[], float] = monotonic
    cancelled: Callable[[], bool] = lambda: False
    parent: Operation | None = None
    _stop: Event = field(default_factory=Event, repr=False)

    @property
    def stopped(self) -> bool:
        return (
            self._stop.is_set()
            or self.cancelled()
            or self.clock() >= self.deadline
            or (self.parent is not None and self.parent.stopped)
        )

    def cancel(self) -> None:
        self._stop.set()

    def remaining(self, limit: float | None = None) -> float:
        if self.stopped:
            raise OperationStopped("operation cancelled or deadline expired")
        value = self.deadline - self.clock()
        if value <= 0:
            raise OperationStopped("operation deadline expired")
        return min(value, limit) if limit is not None else value


_current: ContextVar[Operation | None] = ContextVar("kyrin_operation", default=None)


def current_operation() -> Operation | None:
    return _current.get()


@contextmanager
def activate(operation: Operation) -> Iterator[Operation]:
    token = _current.set(operation)
    try:
        yield operation
    finally:
        _current.reset(token)


@contextmanager
def budget(
    seconds: float,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    clock: Callable[[], float] = monotonic,
) -> Iterator[Operation]:
    parent = current_operation()
    deadline = clock() + seconds
    inherited = os.environ.get("KYRIN_OPERATION_DEADLINE")
    if parent is None and inherited is not None:
        inherited_deadline = (
            float(inherited)
            if clock is monotonic
            else clock() + max(0.0, float(inherited) - monotonic())
        )
        deadline = min(deadline, inherited_deadline)
    if parent is not None:
        # Clocks use the same monotonic domain in production. The conversion
        # also allows deterministic clocks at individual adapter boundaries.
        parent_deadline = (
            parent.deadline if clock is parent.clock else clock() + parent.remaining()
        )
        deadline = min(deadline, parent_deadline)
    operation = Operation(deadline, clock, cancelled, parent)
    with activate(operation):
        operation.remaining()
        yield operation


def remaining(limit: float) -> float:
    operation = current_operation()
    return operation.remaining(limit) if operation is not None else limit


def check_operation() -> None:
    operation = current_operation()
    if operation is not None:
        operation.remaining()


def _stop_process(process: subprocess.Popen[Any], *, group: bool) -> None:
    """Retain ownership until reaped, including a bounded graceful-close phase."""

    def send(sig: signal.Signals) -> None:
        try:
            if group:
                os.killpg(process.pid, sig)
            else:
                process.send_signal(sig)
        except ProcessLookupError:
            pass

    send(signal.SIGTERM)
    try:
        process.communicate(timeout=0.3)
    except subprocess.TimeoutExpired:
        send(signal.SIGKILL)
        # Reap even when the OS delays killing an uninterruptible native call.
        # This deliberately retains the owner rather than admitting new work.
        process.communicate()


def run_process(
    args: Sequence[str],
    *,
    timeout: float,
    input: bytes | None = None,
    text: bool = False,
    capture_output: bool = True,
    stdout: int | None = None,
    stderr: int | None = None,
    check: bool = False,
    env: dict[str, str] | None = None,
    helper: bool = False,
    helper_capabilities: set[str] | None = None,
) -> subprocess.CompletedProcess[Any]:
    """Poll cancellation, kill/reap on stop and authorize each helper input.

    The private socket is inherited only by the helper. It asks the owner for
    current generation authorization immediately before each Notify* call.
    """
    with budget(timeout) as operation:
        if helper_capabilities is not None:
            from kyrin.backend_protocol import (
                BackendStatus,
                BackendUnavailable,
                assess,
            )

            try:
                reply = run_process(
                    [*args[:2], "--capabilities"],
                    timeout=min(timeout, 2),
                    text=True,
                    env=env,
                )
            except FileNotFoundError as error:
                raise BackendUnavailable(
                    BackendStatus(False, "helper_transport_missing")
                ) from error
            except PermissionError as error:
                raise BackendUnavailable(
                    BackendStatus(False, "helper_access_denied")
                ) from error
            except OSError as error:
                raise BackendUnavailable(
                    BackendStatus(False, "helper_transport_unavailable")
                ) from error
            status = (
                assess(reply.stdout, helper_capabilities)
                if reply.returncode == 0
                else BackendStatus(False, "helper_unavailable")
            )
            if not status.ready:
                raise BackendUnavailable(status)
        parent_socket: socket.socket | None = None
        child_socket: socket.socket | None = None
        environment = dict(os.environ if env is None else env)
        pass_fds: tuple[int, ...] = ()
        if helper:
            parent_socket, child_socket = socket.socketpair()
            parent_socket.setblocking(False)
            pass_fds = (child_socket.fileno(),)
            environment["KYRIN_OPERATION_FD"] = str(child_socket.fileno())
            environment["KYRIN_OPERATION_DEADLINE"] = str(operation.deadline)
        process: subprocess.Popen[Any] | None = None
        try:
            operation.remaining()
            own_group = "KYRIN_OPERATION_FD" not in os.environ
            process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE if input is not None else None,
                stdout=stdout
                if stdout is not None
                else subprocess.PIPE
                if capture_output
                else None,
                stderr=stderr
                if stderr is not None
                else subprocess.PIPE
                if capture_output
                else None,
                text=text,
                env=environment,
                pass_fds=pass_fds,
                start_new_session=own_group,
            )
            if child_socket is not None:
                child_socket.close()
            first = True
            while True:
                operation.remaining()
                if (
                    parent_socket is not None
                    and select.select([parent_socket], [], [], 0)[0]
                ):
                    try:
                        request = os.read(parent_socket.fileno(), 1)
                        if request:
                            operation.remaining()
                            os.write(parent_socket.fileno(), b"Y")
                    except BrokenPipeError, ConnectionResetError:
                        pass
                try:
                    stdout, stderr = process.communicate(
                        input=input if first else None,
                        timeout=min(0.02, operation.remaining()),
                    )
                    break
                except subprocess.TimeoutExpired:
                    first = False
            # A late completion is data, not authorization for another stage.
            operation.remaining()
            result = subprocess.CompletedProcess(
                args, process.returncode, stdout, stderr
            )
            if check:
                result.check_returncode()
            return result
        except BaseException:
            if process is not None:
                _stop_process(process, group=own_group)
            raise
        finally:
            if child_socket is not None:
                child_socket.close()
            if parent_socket is not None:
                parent_socket.close()
