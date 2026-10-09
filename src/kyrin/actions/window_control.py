"""Route authorized window commands to a replaceable desktop controller."""

from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.commands.models import CommandKind
from kyrin.desktop.window_control import (
    AppWindowController,
    WindowControlStatus,
    WindowOperation,
)

_OPERATIONS = {
    CommandKind.RESTORE_APP: WindowOperation.RESTORE,
    CommandKind.MINIMIZE_APP: WindowOperation.MINIMIZE,
    CommandKind.CLOSE_APP_WINDOW: WindowOperation.CLOSE,
    CommandKind.MAXIMIZE_APP: WindowOperation.MAXIMIZE,
    CommandKind.UNMAXIMIZE_APP: WindowOperation.UNMAXIMIZE,
    CommandKind.FULLSCREEN_APP: WindowOperation.FULLSCREEN,
    CommandKind.UNFULLSCREEN_APP: WindowOperation.UNFULLSCREEN,
}


class WindowControlExecutor:
    def __init__(
        self, fallback: ActionExecutor, controller: AppWindowController
    ) -> None:
        self._fallback = fallback
        self._controller = controller

    def execute(self, request: ActionRequest) -> ActionResult:
        operation = _OPERATIONS.get(request.intent.kind)
        if operation is None:
            return self._fallback.execute(request)
        status = self._controller.control(request.intent.target, operation)
        if status is WindowControlStatus.CONFIRMED:
            return ActionResult(
                request.key,
                ActionOutcome.CONFIRMED,
                observed_active_app=(
                    request.intent.target
                    if operation is WindowOperation.RESTORE
                    else None
                ),
            )
        if status is WindowControlStatus.UNKNOWN:
            return ActionResult(
                request.key, ActionOutcome.UNKNOWN, error_code="window_unverified"
            )
        return ActionResult(request.key, ActionOutcome.FAILED, error_code=status.value)
