"""Keep ordered desktop actions off the live audio event consumer."""

from collections.abc import Callable
from queue import Empty, Full, Queue
from threading import Lock, Thread

from kyrin.actions.models import (
    ActionFeedback,
    ActionKey,
    ActionNotice,
    ActionNoticeReason,
)
from kyrin.commands.models import CommandPlanResolution, CommandResolution

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


class QueuedActionDispatcher:
    """One bounded FIFO worker owns action policy and execution.

    Submit never waits for an OS operation. On close, unstarted commands are
    cancelled and the current operation is allowed a bounded time to finish.
    """

    def __init__(
        self,
        process: Callable[[FinalActionCommand], tuple[ActionOutput, ...]],
        on_output: Callable[[ActionOutput], None],
        *,
        max_queued: int = 4,
    ) -> None:
        if max_queued <= 0:
            raise ValueError("max_queued must be positive")
        self._process = process
        self._on_output = on_output
        self._queue: Queue[FinalActionCommand] = Queue(maxsize=max_queued)
        self._lock = Lock()
        self._thread: Thread | None = None
        self._closed = False
        self._error: Exception | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None or self._closed:
                raise RuntimeError("action dispatcher cannot be restarted")
            self._thread = Thread(target=self._run, name="kyrin-actions", daemon=True)
            self._thread.start()

    def submit(self, command: FinalActionCommand) -> ActionNotice | None:
        """Enqueue a final command or return a visible capacity notice."""
        if isinstance(command, CommandResolution) and command.intent is None:
            return None
        with self._lock:
            if self._thread is None or self._closed or self._error is not None:
                raise RuntimeError("action dispatcher is not running")
            try:
                self._queue.put_nowait(command)
            except Full:
                return _notice_for(command, ActionNoticeReason.BUSY)
        return None

    def close(self, *, timeout_s: float = 20.0) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        with self._lock:
            if self._closed:
                return
            self._closed = True
            thread = self._thread
            cancelled: list[FinalActionCommand] = []
            while True:
                try:
                    cancelled.append(self._queue.get_nowait())
                except Empty:
                    break
        for command in cancelled:
            self._on_output(_notice_for(command, ActionNoticeReason.CANCELLED))
        if thread is not None:
            thread.join(timeout_s)
            if thread.is_alive():
                raise RuntimeError("action worker did not stop")
        if self._error is not None:
            raise RuntimeError("action worker failed") from self._error

    def _run(self) -> None:
        while True:
            with self._lock:
                if self._closed:
                    return
            try:
                command = self._queue.get(timeout=0.05)
            except Empty:
                continue
            with self._lock:
                cancelled = self._closed
            if cancelled:
                self._on_output(_notice_for(command, ActionNoticeReason.CANCELLED))
                return
            try:
                for output in self._process(command):
                    self._on_output(output)
            except Exception as exc:
                with self._lock:
                    self._error = exc
                return
