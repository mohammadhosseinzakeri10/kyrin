"""Platform-independent boundary for carrying out authorized actions."""

import logging
from dataclasses import replace
from typing import Protocol

from kyrin.actions.cancellation import ActionCancelled, ActionExecutionContext
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.timing import timed_stage

_LOGGER = logging.getLogger(__name__)


class ActionExecutor(Protocol):
    """A platform adapter reports what it knows, not what it assumes."""

    def execute(self, request: ActionRequest) -> ActionResult: ...


def execute_with_unknown_fallback(
    executor: ActionExecutor,
    request: ActionRequest,
    *,
    context: ActionExecutionContext | None = None,
) -> ActionResult:
    """Keep an executor exception from becoming a false claim of failure."""
    try:
        with timed_stage("dispatch", key=request.key):
            return executor.execute(
                replace(request, context=context) if context is not None else request
            )
    except ActionCancelled:
        raise
    except Exception:
        # The executor is an OS/plugin boundary. It may have acted before
        # raising, so the only safe user-facing outcome is UNKNOWN.
        _LOGGER.exception("Action executor raised for %s", request.key)
        return ActionResult(
            request.key,
            ActionOutcome.UNKNOWN,
            error_code="executor_exception",
        )
