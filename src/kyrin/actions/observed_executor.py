"""Confirm an accepted app launch only from a fresh foreground observation."""

import math
from time import sleep

from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.commands.models import CommandKind
from kyrin.desktop.active_app import ActiveAppObserver


class ObservedAppExecutor:
    """Decorate an executor without changing its launch or failure behavior.

    A matching foreground app confirms the observed state, not that the
    launcher created a new window. Missing or different focus leaves the
    original `LAUNCH_ACCEPTED` result unchanged.
    """

    def __init__(
        self,
        executor: ActionExecutor,
        observer: ActiveAppObserver,
        *,
        attempts: int = 4,
        retry_delay_s: float = 0.2,
    ) -> None:
        if attempts <= 0:
            raise ValueError("attempts must be positive")
        if not math.isfinite(retry_delay_s) or retry_delay_s < 0:
            raise ValueError("retry_delay_s must be finite and nonnegative")
        self._executor = executor
        self._observer = observer
        self._attempts = attempts
        self._retry_delay_s = retry_delay_s

    def execute(self, request: ActionRequest) -> ActionResult:
        result = self._executor.execute(request)
        if (
            request.intent.kind is not CommandKind.OPEN_APP
            or result.outcome is not ActionOutcome.LAUNCH_ACCEPTED
        ):
            return result
        for attempt in range(self._attempts):
            if attempt:
                sleep(self._retry_delay_s)
            if self._observer.observe_active_app() == request.intent.target:
                return ActionResult(
                    request.key,
                    ActionOutcome.CONFIRMED,
                    observed_active_app=request.intent.target,
                )
        return result
