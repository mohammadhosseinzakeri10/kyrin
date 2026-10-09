"""Window actions never turn into process termination or a new launch."""

from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.window_control import WindowControlExecutor
from kyrin.commands.models import CommandIntent, CommandKind
from kyrin.desktop.window_control import WindowControlStatus, WindowOperation


class StubController:
    def __init__(self, status: WindowControlStatus) -> None:
        self.status = status
        self.calls: list[tuple[str, WindowOperation]] = []

    def control(self, app_id: str, operation: WindowOperation) -> WindowControlStatus:
        self.calls.append((app_id, operation))
        return self.status


class StubFallback:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, request: ActionRequest) -> ActionResult:
        self.calls += 1
        return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)


def test_close_one_window_uses_controller_only() -> None:
    fallback = StubFallback()
    controller = StubController(WindowControlStatus.CONFIRMED)
    executor = WindowControlExecutor(fallback, controller)
    request = ActionRequest(
        ActionKey(0, 0), CommandIntent(CommandKind.CLOSE_APP_WINDOW, "telegram")
    )

    assert executor.execute(request) == ActionResult(
        request.key, ActionOutcome.CONFIRMED
    )
    assert controller.calls == [("telegram", WindowOperation.CLOSE)]
    assert fallback.calls == 0


def test_multiple_windows_are_reported_without_fallback_launch() -> None:
    fallback = StubFallback()
    controller = StubController(WindowControlStatus.MULTIPLE_WINDOWS)
    executor = WindowControlExecutor(fallback, controller)
    request = ActionRequest(
        ActionKey(0, 0), CommandIntent(CommandKind.MINIMIZE_APP, "telegram")
    )

    assert executor.execute(request) == ActionResult(
        request.key, ActionOutcome.FAILED, error_code="multiple_windows"
    )
    assert fallback.calls == 0
