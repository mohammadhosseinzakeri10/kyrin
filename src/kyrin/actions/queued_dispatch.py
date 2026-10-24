"""Keep ordered desktop actions off the live audio event consumer."""

from collections.abc import Callable
from queue import Empty, Full, Queue
from threading import Condition, Lock, Thread

from kyrin.actions.cancellation import ActionExecutionContext
from kyrin.actions.models import (
    ActionFeedback,
    ActionKey,
    ActionNotice,
    ActionNoticeReason,
    ActionOutcome,
)
from kyrin.commands.models import (
    CommandPlanResolution,
    CommandResolution,
    ResponseChannel,
)

FinalActionCommand = CommandResolution | CommandPlanResolution
ActionOutput = ActionNotice | ActionFeedback


def _notice_for(
    command: FinalActionCommand, reason: ActionNoticeReason
) -> ActionNotice:
    intent = (
        command.plan.steps[0]
        if isinstance(command, CommandPlanResolution)
        else command.intent
    )
    assert intent is not None
    return ActionNotice(
        ActionKey(command.stream_id, command.segment_id),
        intent,
        reason,
        language=command.language,
    )


def _unknown_for(command: FinalActionCommand) -> ActionFeedback:
    """Report a fatal processing error without claiming the action failed."""
    intent = (
        command.plan.steps[0]
        if isinstance(command, CommandPlanResolution)
        else command.intent
    )
    assert intent is not None
    return ActionFeedback(
        ActionKey(command.stream_id, command.segment_id),
        intent,
        ActionOutcome.UNKNOWN,
        ResponseChannel.TEXT_AND_VOICE,
        error_code="action_worker_failed",
        language=command.language,
    )


class QueuedActionDispatcher:
    """One bounded FIFO worker owns action policy and execution.

    Live submit never waits for an OS operation. Finite sources may wait for
    queue capacity. Close can drain or cancel unstarted commands.
    """

    def __init__(
        self,
        process: Callable[
            [FinalActionCommand, ActionExecutionContext], tuple[ActionOutput, ...]
        ],
        on_output: Callable[[ActionOutput], None],
        *,
        max_queued: int = 4,
        on_timing: Callable[[FinalActionCommand, str], None] | None = None,
    ) -> None:
        if max_queued <= 0:
            raise ValueError("max_queued must be positive")
        self._on_timing = on_timing
        self._process = process
        self._on_output = on_output
        self._queue: Queue[tuple[ActionExecutionContext, FinalActionCommand]] = Queue(
            maxsize=max_queued
        )
        self._lock = Lock()
        self._capacity = Condition(self._lock)
        self._thread: Thread | None = None
        self._closed = False
        self._drain = False
        self._context = ActionExecutionContext(0)
        self._error: Exception | None = None

    @property
    def generation(self) -> int:
        with self._lock:
            return self._context.generation

    def start(self) -> None:
        with self._lock:
            if self._thread is not None or self._closed:
                raise RuntimeError("action dispatcher cannot be restarted")
            self._thread = Thread(target=self._run, name="kyrin-actions", daemon=True)
            self._thread.start()

    def submit(
        self,
        command: FinalActionCommand,
        *,
        wait_for_capacity: bool = False,
        generation: int | None = None,
    ) -> ActionNotice | None:
        """Enqueue a final command or return a visible capacity notice."""
        if isinstance(command, CommandResolution) and command.intent is None:
            return None
        with self._capacity:
            submitted_generation = (
                self._context.generation if generation is None else generation
            )
            while True:
                if self._thread is None or self._closed or self._error is not None:
                    raise RuntimeError("action dispatcher is not running")
                if submitted_generation != self._context.generation:
                    return _notice_for(command, ActionNoticeReason.CANCELLED)
                try:
                    if self._on_timing is not None and not self._queue.full():
                        self._on_timing(command, "action_queued")
                    self._queue.put_nowait((self._context, command))
                    break
                except Full:
                    if not wait_for_capacity:
                        return _notice_for(command, ActionNoticeReason.BUSY)
                    self._capacity.wait()
        return None

    def invalidate_pending(self) -> None:
        """Invalidate queued work and prevent later steps of active plans."""
        with self._capacity:
            self._context.cancel()
            self._context = ActionExecutionContext(self._context.generation + 1)
            cancelled: list[FinalActionCommand] = []
            while True:
                try:
                    cancelled.append(self._queue.get_nowait()[1])
                except Empty:
                    break
            self._capacity.notify_all()
        for command in cancelled:
            self._on_output(_notice_for(command, ActionNoticeReason.CANCELLED))

    def close(self, *, drain: bool = False, timeout_s: float = 20.0) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        with self._capacity:
            if self._closed:
                return
            self._closed = True
            self._drain = drain
            thread = self._thread
            cancelled: list[FinalActionCommand] = []
            if not drain:
                self._context.cancel()
                while True:
                    try:
                        cancelled.append(self._queue.get_nowait()[1])
                    except Empty:
                        break
            self._capacity.notify_all()
        for command in cancelled:
            self._on_output(_notice_for(command, ActionNoticeReason.CANCELLED))
        if thread is not None:
            thread.join(timeout_s)
            if thread.is_alive():
                timed_out: list[FinalActionCommand] = []
                with self._capacity:
                    self._drain = False
                    self._context.cancel()
                    while True:
                        try:
                            timed_out.append(self._queue.get_nowait()[1])
                        except Empty:
                            break
                    self._capacity.notify_all()
                for command in timed_out:
                    self._on_output(_notice_for(command, ActionNoticeReason.CANCELLED))
                raise RuntimeError("action worker did not stop")
        if self._error is not None:
            raise RuntimeError("action worker failed") from self._error

    def _run(self) -> None:
        while True:
            with self._lock:
                if self._closed and (not self._drain or self._queue.empty()):
                    return
            try:
                context, command = self._queue.get(timeout=0.05)
            except Empty:
                continue
            with self._capacity:
                self._capacity.notify_all()
                cancelled = (self._closed and not self._drain) or context.cancelled
            if cancelled:
                self._on_output(_notice_for(command, ActionNoticeReason.CANCELLED))
                continue
            try:
                outputs = self._process(command, context)
            except Exception as exc:
                with self._capacity:
                    self._error = exc
                    self._capacity.notify_all()
                try:
                    self._on_output(_unknown_for(command))
                except Exception:
                    # A broken presentation callback cannot report its own
                    # failure. close() still raises the original worker error.
                    pass
                return
            for output in outputs:
                try:
                    self._on_output(output)
                except Exception as exc:
                    with self._capacity:
                        self._error = exc
                        self._capacity.notify_all()
                    return
