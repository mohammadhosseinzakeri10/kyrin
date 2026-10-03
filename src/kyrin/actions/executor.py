"""Platform-independent boundary for carrying out authorized actions."""

from typing import Protocol

from kyrin.actions.models import ActionRequest, ActionResult


class ActionExecutor(Protocol):
    """A platform adapter reports what it knows, not what it assumes."""

    def execute(self, request: ActionRequest) -> ActionResult: ...
