"""FIFO ownership of compound desktop input across independent callers."""

from collections import deque
from collections.abc import Callable
from threading import Condition, get_ident
from time import monotonic

from kyrin.actions.cancellation import ActionCancelled, execute_with_budget
from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionRequest, ActionResult
from kyrin.operations import Operation, current_operation


class DesktopInputBroker:
    """Run one whole input operation at a time, on its calling thread.

    The condition protects admission only: adapters, observations and callbacks
    run without it. Nested executor delegation on the owner thread reuses its
    ownership. Waiting callers are FIFO; cancellation removes only that caller.
    Active operations keep ownership until they return, even after close times
    out. This broker does not terminate helpers or undo input already sent.
    """

    def __init__(self) -> None:
        self._condition = Condition()
        self._waiting: deque[object] = deque()
        self._owner: int | None = None
        self._closed = False
        self._active_operation: Operation | None = None

    def run[T](
        self,
        operation: Callable[[], T],
        *,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> T:
        caller = get_ident()
        operation_context = current_operation()
        with self._condition:
            nested = self._owner == caller
            if not nested:
                ticket = object()
                self._waiting.append(ticket)
                self._condition.notify_all()
                try:
                    while True:
                        if (
                            self._closed
                            or cancelled()
                            or (
                                operation_context is not None
                                and operation_context.stopped
                            )
                        ):
                            raise ActionCancelled("desktop input has not started")
                        if self._owner is None and self._waiting[0] is ticket:
                            self._owner = caller
                            self._active_operation = operation_context
                            break
                        # Event-based cancellation also works without needing
                        # a callback into this broker from the cancelling thread.
                        self._condition.wait(0.05)
                finally:
                    self._waiting.remove(ticket)
                    self._condition.notify_all()
        try:
            return operation()
        finally:
            if not nested:
                with self._condition:
                    self._owner = None
                    self._active_operation = None
                    self._condition.notify_all()

    def close(self, *, timeout_s: float = 20.0) -> None:
        """Reject waiting/new input and wait for the current owner to finish.

        May be retried after timeout; ownership is never released by timeout.
        Calling close from inside an owned operation is an error, not a join
        on oneself. Nested delegation by an active owner may still finish.
        """
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        deadline = monotonic() + timeout_s
        with self._condition:
            if self._owner == get_ident():
                raise RuntimeError("cannot close desktop input from its owner")
            self._closed = True
            if self._active_operation is not None:
                self._active_operation.cancel()
            self._condition.notify_all()
            while self._owner is not None:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise RuntimeError("desktop input operation did not stop")
                self._condition.wait(remaining)


class DesktopInputExecutor:
    """Put the entire executor chain, including focus changes, under one owner."""

    def __init__(self, delegate: ActionExecutor, broker: DesktopInputBroker) -> None:
        self._delegate = delegate
        self._broker = broker

    def execute(self, request: ActionRequest) -> ActionResult:
        return execute_with_budget(request, lambda: self._broker.run(
            lambda: self._delegate.execute(request),
            cancelled=lambda: request.context is not None and request.context.cancelled,
        ))
