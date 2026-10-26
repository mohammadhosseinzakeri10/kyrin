"""Raise an existing app window, or launch when none exists."""

import math
from time import sleep

from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.backend_protocol import backend_error
from kyrin.commands.models import CommandKind
from kyrin.desktop.active_app import ActiveAppObserver
from kyrin.desktop.app_activation import ActivationAttempt, ExistingAppActivator


class ActivateOrLaunchExecutor:
    """Confirm focus after activation; never launch again if it may have worked."""

    def __init__(
        self,
        launcher: ActionExecutor,
        activator: ExistingAppActivator,
        observer: ActiveAppObserver,
        *,
        attempts: int = 4,
        retry_delay_s: float = 0.2,
    ) -> None:
        if attempts <= 0:
            raise ValueError("attempts must be positive")
        if not math.isfinite(retry_delay_s) or retry_delay_s < 0:
            raise ValueError("retry_delay_s must be finite and nonnegative")
        self._launcher = launcher
        self._activator = activator
        self._observer = observer
        self._attempts = attempts
        self._retry_delay_s = retry_delay_s

    def execute(self, request: ActionRequest) -> ActionResult:
        if request.intent.kind is not CommandKind.OPEN_APP:
            return self._launcher.execute(request)

        attempt = self._activator.activate_existing_app(request.intent.target)
        if attempt is ActivationAttempt.NO_WINDOW:
            return self._launcher.execute(request)
        if attempt is ActivationAttempt.MULTIPLE_WINDOWS:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="multiple_windows",
            )
        if attempt is ActivationAttempt.UNKNOWN:
            return ActionResult(
                request.key,
                ActionOutcome.UNKNOWN,
                error_code=backend_error(self._activator) or "activation_unknown",
            )

        for index in range(self._attempts):
            if index:
                sleep(self._retry_delay_s)
            if self._observer.observe_active_app() == request.intent.target:
                return ActionResult(
                    request.key,
                    ActionOutcome.CONFIRMED,
                    observed_active_app=request.intent.target,
                )
        return ActionResult(
            request.key,
            ActionOutcome.UNKNOWN,
            error_code=backend_error(self._observer) or "activation_unverified",
        )
