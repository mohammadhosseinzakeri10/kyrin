"""Bounded, ordered understanding with generation-checked state and delivery."""

from collections import deque
from collections.abc import Callable, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from threading import Condition, RLock, Thread

from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.models import CommandEvent
from kyrin.operations import Operation, OperationStopped, activate
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from kyrin.timing import TimingScope, timing_scope


@dataclass(frozen=True, slots=True)
class CommandWork:
    update: TranscriptUpdate
    action_generation: int
    stream_id: int
    timing: TimingScope | None = None


@dataclass(frozen=True, slots=True)
class UnderstoodCommand:
    work: CommandWork
    generation: int
    active_app: str | None
    decisions: Sequence[CommandEvent]


class CommandUnderstandingWorker:
    """One runtime owns this worker and the coordinator snapshots it commits.

    Four waiting updates by default, plus one in flight. Finals retain FIFO
    order; queued previews are expendable. Invalidation never waits for inference.
    A running Python thread cannot be killed: close reports a join timeout.
    Presentation callbacks passed to publish must be short and nonblocking.
    """

    def __init__(
        self,
        coordinator: CommandCoordinator,
        process: Callable[
            [CommandCoordinator, TranscriptUpdate, int],
            tuple[str | None, Sequence[CommandEvent]],
        ],
        on_result: Callable[[UnderstoodCommand], None],
        on_error: Callable[[], None],
        *,
        max_queued: int = 4,
    ) -> None:
        if max_queued < 1:
            raise ValueError("max_queued must be positive")
        self._coordinator = coordinator.fork()
        self._process = process
        self._on_result = on_result
        self._on_error = on_error
        self._max_queued = max_queued
        self._queue: deque[tuple[int, CommandWork]] = deque()
        self._condition = Condition(RLock())
        self._generation = 0
        self._closed = False
        self._drain = False
        self._error: Exception | None = None
        self._thread: Thread | None = None
        self._finished = False
        self._stop_requested = False
        self._active_work: CommandWork | None = None
        self._active_operation: Operation | None = None

    def start(self) -> None:
        with self._condition:
            if self._thread is not None or self._closed:
                raise RuntimeError("understanding worker cannot be restarted")
            self._thread = Thread(
                target=self._run, name="kyrin-command-understanding", daemon=True
            )
            self._thread.start()

    @property
    def generation(self) -> int:
        with self._condition:
            return self._generation

    def submit(
        self,
        work: CommandWork,
        *,
        wait_for_capacity: bool = False,
        generation: int | None = None,
    ) -> bool:
        with self._condition:
            if generation is None:
                generation = self._generation
            if generation != self._generation or self._stop_requested:
                self._release_audio(work)
                return False
            if work.update.status is TranscriptStatus.FINAL:
                self._queue = deque(
                    item
                    for item in self._queue
                    if item[1].update.status is TranscriptStatus.FINAL
                )
            while len(self._queue) >= self._max_queued:
                if not wait_for_capacity:
                    self._release_audio(work)
                    return False
                self._condition.wait()
                if generation != self._generation or self._closed:
                    self._release_audio(work)
                    return False
                self._raise_if_failed()
            self._raise_if_failed()
            if self._closed or self._thread is None:
                self._release_audio(work)
                return False
            if work.timing is not None:
                work.timing.mark("understanding_queued")
            self._queue.append((generation, work))
            self._condition.notify_all()
            return True

    def publish(self, generation: int, callback: Callable[[], None]) -> bool:
        """Serialize short delivery/commit against invalidation, never inference."""
        with self._condition:
            if generation != self._generation:
                return False
            callback()
            return True

    def invalidate(
        self, *, new_stream: bool = False, clear_dialogue: bool = True
    ) -> Sequence[CommandEvent]:
        with self._condition:
            self._generation += 1
            for _, work in self._queue:
                self._release_audio(work)
            if self._active_work is not None:
                self._release_audio(self._active_work)
            if self._active_operation is not None:
                self._active_operation.cancel()
            self._queue.clear()
            # In-flight interpretation only mutates its private snapshot.
            if clear_dialogue:
                self._coordinator.cancel_dialogue()
            else:
                self._coordinator.cancel_fragment()
            events = self._coordinator.start_new_stream() if new_stream else ()
            self._condition.notify_all()
            return events

    def request_stop(self) -> None:
        """Reject further work and shorten an active or future drain wait."""
        with self._condition:
            self._stop_requested = True
            self.invalidate()

    def close(self, *, drain: bool, timeout_s: float) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        with self._condition:
            self._closed = True
            self._drain = drain and not self._stop_requested
            if self._stop_requested:
                timeout_s = min(1.0, timeout_s)
            if not self._drain:
                self.invalidate()
            self._condition.notify_all()
            thread = self._thread
            generation = self._generation
        if thread is not None:
            with self._condition:
                self._condition.wait_for(
                    lambda: self._finished or generation != self._generation,
                    timeout_s,
                )
                if not self._finished and generation != self._generation:
                    # A stop during EOF draining must shorten that drain wait.
                    self._condition.wait_for(
                        lambda: self._finished, min(1.0, timeout_s)
                    )
                if not self._finished:
                    self._drain = False
                    self.invalidate()
                    raise RuntimeError(
                        "command understanding worker did not stop; "
                        "in-flight inference may still be running (results invalidated)"
                    )
            thread.join()
        self._raise_if_failed()

    @staticmethod
    def _release_audio(work: CommandWork) -> None:
        if work.update.retained_audio is not None:
            work.update.retained_audio.close()

    def _raise_if_failed(self) -> None:
        if self._error is not None:
            raise RuntimeError("command understanding worker failed") from self._error

    def _run(self) -> None:
        try:
            while True:
                with self._condition:
                    self._condition.wait_for(
                        lambda: (
                            self._closed or self._stop_requested or bool(self._queue)
                        )
                    )
                    if self._stop_requested:
                        return
                    if self._closed and (not self._drain or not self._queue):
                        return
                    generation, work = self._queue.popleft()
                    self._active_work = work
                    operation = Operation(float("inf"))
                    self._active_operation = operation
                    coordinator = self._coordinator.fork()
                    self._condition.notify_all()
                try:
                    with (
                        activate(operation),
                        timing_scope(work.timing) if work.timing else nullcontext(),
                    ):
                        if work.timing is not None:
                            work.timing.mark("understanding_started")
                        active_app, decisions = self._process(
                            coordinator, work.update, generation
                        )
                        if work.timing is not None:
                            work.timing.mark("understanding_finished")
                except OperationStopped:
                    continue
                finally:
                    self._release_audio(work)
                    with self._condition:
                        self._active_work = None
                        self._active_operation = None
                with self._condition:
                    if generation != self._generation or operation.stopped:
                        continue
                    self._coordinator = coordinator
                self._on_result(
                    UnderstoodCommand(work, generation, active_app, decisions)
                )
        except Exception as exc:
            # Preserve adapter/callback failures at this thread boundary.
            with self._condition:
                self._error = exc
                self.invalidate()
            self._on_error()
        finally:
            with self._condition:
                if self._active_work is not None:
                    self._release_audio(self._active_work)
                    self._active_work = None
                self._finished = True
                self._condition.notify_all()
