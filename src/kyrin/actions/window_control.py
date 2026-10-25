"""Route authorized window commands to a replaceable desktop controller."""

from time import monotonic

from kyrin.actions.cancellation import execute_with_budget
from kyrin.actions.control_policy import (
    ControlApproval,
    ControlCapability,
    ControlConfirmation,
    ControlConfirmer,
    ControlEvidence,
)
from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.app.permissions import PermissionPolicy
from kyrin.backend_protocol import backend_error
from kyrin.commands.models import CommandKind
from kyrin.desktop.window_control import (
    AppWindowController,
    AuthorizedWindowCloser,
    NativeWindowCloseConfirmer,
    WindowControlStatus,
    WindowOperation,
)
from kyrin.operations import check_operation

_OPERATIONS = {
    CommandKind.RESTORE_APP: WindowOperation.RESTORE,
    CommandKind.MINIMIZE_APP: WindowOperation.MINIMIZE,
    CommandKind.MAXIMIZE_APP: WindowOperation.MAXIMIZE,
    CommandKind.UNMAXIMIZE_APP: WindowOperation.UNMAXIMIZE,
    CommandKind.FULLSCREEN_APP: WindowOperation.FULLSCREEN,
    CommandKind.UNFULLSCREEN_APP: WindowOperation.UNFULLSCREEN,
}


class WindowControlExecutor:
    def __init__(
        self,
        fallback: ActionExecutor,
        controller: AppWindowController,
        *,
        confirmation: ControlConfirmer | None = None,
        permissions: PermissionPolicy | None = None,
        allowed_close_apps: frozenset[str] = frozenset(),
        allowed_window_apps: frozenset[str] = frozenset(),
    ) -> None:
        self._fallback = fallback
        self._controller = controller
        self._confirmation = confirmation
        self._permissions = permissions
        self._allowed_close_apps = allowed_close_apps
        self._allowed_window_apps = allowed_window_apps

    def execute(self, request: ActionRequest) -> ActionResult:
        if request.intent.kind in (
            CommandKind.CLOSE_APP_WINDOW,
            CommandKind.CLOSE_SHOWN_WINDOW,
        ):
            return execute_with_budget(request, lambda: self._close(request))
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
        if reason := backend_error(self._controller):
            return ActionResult(request.key, ActionOutcome.UNKNOWN, error_code=reason)
        if status is WindowControlStatus.UNKNOWN:
            return ActionResult(
                request.key, ActionOutcome.UNKNOWN, error_code="window_unverified"
            )
        return ActionResult(request.key, ActionOutcome.FAILED, error_code=status.value)

    def _close(self, request: ActionRequest) -> ActionResult:
        def failed(code: str) -> ActionResult:
            return ActionResult(request.key, ActionOutcome.FAILED, error_code=code)

        native = (
            self._controller
            if isinstance(self._controller, NativeWindowCloseConfirmer)
            else None
        )
        if self._permissions is not None and not self._permissions.allows_intent(
            request.intent
        ):
            return failed("action_not_allowed")
        if self._permissions is None and self._confirmation is None and native is None:
            return failed("window_close_confirmation_required")
        window = self._controller.prepare_close(
            request.intent.target, request.intent.window_index
        )
        if window is None or not window.current(window.window_token, monotonic()):
            return failed(backend_error(self._controller) or "window_state_changed")
        if (
            window.app_id not in self._allowed_close_apps
            or (
                request.intent.target != "desktop"
                and window.app_id != request.intent.target
            )
            or (
                request.intent.kind is CommandKind.CLOSE_SHOWN_WINDOW
                and window.app_id not in self._allowed_window_apps
            )
        ):
            return failed("app_not_configured")
        prompt = ControlConfirmation(
            request.key,
            ControlCapability.CLOSE_WINDOW,
            ControlEvidence(window.app_id, "window", None, None, None),
            window,
            None,
            request.language,
        )
        check_operation()
        if self._permissions is not None:
            approved = self._permissions.allows("close_window", window.app_id)
        elif native is not None:
            approved = native.confirm_close(window, request.language)
        else:
            assert self._confirmation is not None
            approved = self._confirmation(prompt)
        if approved is not True:
            return failed("window_close_confirmation_declined")
        approval = ControlApproval(prompt)
        check_operation()
        if not approval.consume(prompt, monotonic()):
            return failed("window_state_changed")
        # The platform re-resolves and consumes the exact prepared target in
        # the same event-loop turn as normal close, eliminating the D-Bus race.
        if self._permissions is not None:
            if not self._permissions.allows("close_window", window.app_id):
                return failed("action_not_allowed")
            if not isinstance(self._controller, AuthorizedWindowCloser):
                return failed("backend:missing_capabilities:CloseAuthorizedWindow")
            status = self._controller.close_authorized(window)
        else:
            status = self._controller.close_confirmed(window)
        if status is WindowControlStatus.CONFIRMED:
            return ActionResult(request.key, ActionOutcome.CONFIRMED)
        close_error = getattr(self._controller, "close_error_code", None)
        return ActionResult(
            request.key,
            ActionOutcome.UNKNOWN,
            error_code=backend_error(self._controller)
            or (close_error if isinstance(close_error, str) else "window_unverified"),
        )
