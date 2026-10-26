"""Cooperative cancellation for one action-session generation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kyrin.actions.models import ActionRequest, ActionResult


class ActionCancelled(Exception):
    """Input ownership was refused before the operation started."""


@dataclass(frozen=True, slots=True)
class ActionExecutionContext:
    """Shared by queued commands and running steps; never undoes dispatched work.

    The dispatcher owns cancellation. Requests carry it through input admission
    and operation budgets; helpers check it before each input and are reaped on
    cancellation. Already dispatched input cannot be undone.
    """

    generation: int
    _cancelled: Event = field(default_factory=Event, repr=False, compare=False)

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel(self) -> None:
        self._cancelled.set()


def execute_with_budget(
    request: ActionRequest,
    operation: Callable[[], ActionResult],
    *,
    timeout_s: float = 65.0,
) -> ActionResult:
    """Keep one action budget through nested adapters and report uncertain input."""
    from kyrin.actions.models import ActionOutcome, ActionResult
    from kyrin.operations import OperationStopped, budget

    try:
        with budget(
            timeout_s,
            cancelled=lambda: request.context is not None and request.context.cancelled,
        ):
            return operation()
    except OperationStopped:
        return ActionResult(
            request.key, ActionOutcome.UNKNOWN, error_code="action_interrupted"
        )
