"""Recheck the shared permission snapshot after desktop input admission."""

from kyrin.actions.cancellation import execute_with_budget
from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.app.permissions import PermissionPolicy
from kyrin.operations import check_operation


class PermissionExecutor:
    def __init__(self, delegate: ActionExecutor, permissions: PermissionPolicy) -> None:
        self._delegate = delegate
        self._permissions = permissions

    def execute(self, request: ActionRequest) -> ActionResult:
        return execute_with_budget(request, lambda: self._execute(request))

    def _execute(self, request: ActionRequest) -> ActionResult:
        check_operation()
        if not self._permissions.allows_intent(request.intent):
            return ActionResult(
                request.key, ActionOutcome.FAILED, error_code="action_not_allowed"
            )
        return self._delegate.execute(request)
