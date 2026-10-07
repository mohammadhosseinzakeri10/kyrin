"""Platform-independent boundary for carrying out authorized actions."""

import logging
from typing import Protocol

from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult

_LOGGER = logging.getLogger(__name__)


class ActionExecutor(Protocol):
    """A platform adapter reports what it knows, not what it assumes."""

    def execute(self, request: ActionRequest) -> ActionResult: ...


def execute_with_unknown_fallback(
    executor: ActionExecutor, request: ActionRequest
) -> ActionResult:
    """Keep an executor exception from becoming a false claim of failure."""
    try:
        return executor.execute(request)
    except Exception:
        # The executor is an OS/plugin boundary. It may have acted before
        # raising, so the only safe user-facing outcome is UNKNOWN.
        _LOGGER.exception("Action executor raised for %s", request.key)
        return ActionResult(
            request.key,
            ActionOutcome.UNKNOWN,
            error_code="executor_exception",
        )
