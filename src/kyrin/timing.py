"""Small content-free timing events at existing command/action boundaries."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from time import perf_counter_ns
from typing import Literal

from kyrin.actions.models import ActionKey

Temperature = Literal["cold", "warm", "unknown"]


@dataclass(frozen=True, slots=True)
class TimingEvent:
    session_id: str
    key: ActionKey
    stage: str
    at_ns: int
    route: str = "command"
    temperature: Temperature = "unknown"


@dataclass(frozen=True)
class TimingScope:
    session_id: str
    key: ActionKey
    publish: Callable[[TimingEvent], None]
    clock_ns: Callable[[], int] = perf_counter_ns
    route: str = "command"
    temperature: Temperature = "unknown"

    def mark(
        self, stage: str, *, key: ActionKey | None = None, at_ns: int | None = None
    ) -> None:
        self.publish(
            TimingEvent(
                self.session_id,
                self.key if key is None else key,
                stage,
                self.clock_ns() if at_ns is None else at_ns,
                self.route,
                self.temperature,
            )
        )


_current: ContextVar[TimingScope | None] = ContextVar("kyrin_timing", default=None)


@contextmanager
def timing_scope(scope: TimingScope) -> Iterator[None]:
    token = _current.set(scope)
    try:
        yield
    finally:
        _current.reset(token)


def mark(stage: str, *, key: ActionKey | None = None) -> None:
    scope = _current.get()
    if scope is not None:
        scope.mark(stage, key=key)


@contextmanager
def timed_stage(stage: str, *, key: ActionKey | None = None) -> Iterator[None]:
    scope = _current.get()
    if scope is None:
        yield
        return
    if key is not None:
        scope = replace(scope, key=key)
    with timing_scope(scope):
        scope.mark(stage + "_started")
        try:
            yield
        finally:
            scope.mark(stage + "_finished")
