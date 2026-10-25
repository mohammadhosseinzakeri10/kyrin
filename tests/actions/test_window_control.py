"""Window actions never turn into process termination or a new launch."""

from dataclasses import replace
from time import monotonic

import pytest

from kyrin.actions import window_control
from kyrin.actions.cancellation import ActionExecutionContext
from kyrin.actions.control_policy import ControlCapability, ControlConfirmation
from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.window_control import WindowControlExecutor
from kyrin.commands.models import CommandIntent, CommandKind
from kyrin.desktop.platforms.gnome_window_control import GnomeAppWindowController
from kyrin.desktop.window_control import WindowControlStatus, WindowOperation
from kyrin.desktop.window_observation import WindowObservation


class StubController:
    def __init__(self, status: WindowControlStatus) -> None:
        self.status = status
        self.calls: list[tuple[str, WindowOperation]] = []
        now = monotonic()
        self.window = WindowObservation("telegram", 42, "17", "binding", now, now + 10)
        self.prepared: list[tuple[str, int | None]] = []
        self.closed: list[WindowObservation] = []

    def control(self, app_id: str, operation: WindowOperation) -> WindowControlStatus:
        self.calls.append((app_id, operation))
        return self.status

    def prepare_close(
        self, app_id: str, window_index: int | None = None
    ) -> WindowObservation:
        self.prepared.append((app_id, window_index))
        return self.window

    def close_confirmed(self, window: WindowObservation) -> WindowControlStatus:
        self.closed.append(window)
        return self.status

    def close_authorized(self, window: WindowObservation) -> WindowControlStatus:
        self.closed.append(window)
        return self.status


class StubFallback:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, request: ActionRequest) -> ActionResult:
        self.calls += 1
        return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)


def test_close_without_shared_confirmation_never_controls_a_window() -> None:
    fallback = StubFallback()
    controller = StubController(WindowControlStatus.CONFIRMED)
    executor = WindowControlExecutor(fallback, controller)
    request = ActionRequest(
        ActionKey(0, 0), CommandIntent(CommandKind.CLOSE_APP_WINDOW, "telegram")
    )

    assert executor.execute(request).outcome is ActionOutcome.FAILED
    assert controller.calls == []
    assert fallback.calls == 0


@pytest.mark.parametrize("trust", [False, True])
@pytest.mark.parametrize("change", ["none", "target", "expired", "cancelled"])
def test_persistent_close_keeps_target_expiry_and_cancellation(
    trust: bool,
    change: str,
) -> None:
    from kyrin.app.permissions import PermissionPolicy
    from kyrin.app.settings import AllowedApp, AppSettings

    controller = StubController(WindowControlStatus.CONFIRMED)
    settings = AppSettings(
        action_execution_enabled=True,
        trust_all_capabilities=trust,
        allowed_apps=(AllowedApp("telegram", "telegram.desktop"),),
        allowed_close_apps=("telegram",),
    )
    context = ActionExecutionContext(1)
    if change == "target":
        controller.window = replace(controller.window, app_id="other")
    elif change == "expired":
        controller.window = replace(
            controller.window, observed_at=monotonic() - 20, deadline=monotonic() - 11
        )
    elif change == "cancelled":
        context.cancel()
    executor = WindowControlExecutor(
        StubFallback(),
        controller,
        permissions=PermissionPolicy(settings),
        allowed_close_apps=frozenset({"telegram"}),
        confirmation=lambda _prompt: pytest.fail("persistent close opened a dialog"),
    )
    result = executor.execute(
        ActionRequest(
            ActionKey(1, 1),
            CommandIntent(CommandKind.CLOSE_APP_WINDOW, "telegram"),
            context=context,
        )
    )
    assert bool(controller.closed) == (change == "none")
    assert (result.outcome is ActionOutcome.CONFIRMED) == (change == "none")


def test_missing_saved_permission_does_not_prepare_or_show_confirmation() -> None:
    from kyrin.app.permissions import PermissionPolicy
    from kyrin.app.settings import AppSettings

    controller = StubController(WindowControlStatus.CONFIRMED)
    executor = WindowControlExecutor(
        StubFallback(),
        controller,
        permissions=PermissionPolicy(AppSettings()),
        allowed_close_apps=frozenset({"telegram"}),
        confirmation=lambda _prompt: pytest.fail("denied action opened a dialog"),
    )
    result = executor.execute(
        ActionRequest(
            ActionKey(1, 1), CommandIntent(CommandKind.CLOSE_APP_WINDOW, "telegram")
        )
    )
    assert result.error_code == "action_not_allowed"
    assert not controller.prepared and not controller.closed


@pytest.mark.parametrize("rejected", [True, False])
def test_approved_close_keeps_backend_stage_without_opening_or_retrying(
    monkeypatch: pytest.MonkeyPatch, rejected: bool
) -> None:
    controller = GnomeAppWindowController({"telegram": "telegram.desktop"}, attempts=1)
    now = monotonic()
    window = WindowObservation("telegram.desktop", 42, "17", "bound", now, now + 10)
    replies = iter(
        [(window.to_json(),), ("approved",), ("stale",)]
        if rejected
        else [
            (window.to_json(),),
            ("approved",),
            ("requested",),
            ('{"minimized":false}',),
        ]
    )
    calls: list[str] = []

    def call(method: str, *_args: str, **_kwargs: object) -> tuple[str, ...]:
        calls.append(method)
        return next(replies)

    monkeypatch.setattr(controller, "_call", call)
    fallback = StubFallback()
    executor = WindowControlExecutor(
        fallback,
        controller,
        confirmation=lambda prompt: pytest.fail(
            "GNOME close must not open the Qt dialog"
        ),
        allowed_close_apps=frozenset({"telegram"}),
    )
    result = executor.execute(
        ActionRequest(
            ActionKey(1, 1), CommandIntent(CommandKind.CLOSE_APP_WINDOW, "telegram")
        )
    )
    assert result.outcome is ActionOutcome.UNKNOWN
    assert result.error_code == (
        "window_close_rejected:stale"
        if rejected
        else "window_close_unverified:window_present"
    )
    assert fallback.calls == 0
    assert calls.count("CloseConfirmedWindow") == 1
    assert "ControlAppWindow" not in calls


@pytest.mark.parametrize("app", ["terminal", "editor"])
@pytest.mark.parametrize("numbered", [False, True])
@pytest.mark.parametrize("approved", [False, True])
def test_every_close_requires_shared_window_bound_consent(
    app: str, numbered: bool, approved: bool
) -> None:
    controller = StubController(WindowControlStatus.CONFIRMED)
    controller.window = replace(controller.window, app_id=app)
    prompts: list[ControlConfirmation] = []

    def confirm(prompt: ControlConfirmation) -> bool:
        prompts.append(prompt)
        assert controller.closed == []
        return approved

    executor = WindowControlExecutor(
        StubFallback(),
        controller,
        confirmation=confirm,
        allowed_close_apps=frozenset({app}),
        allowed_window_apps=frozenset({app}),
    )
    request = ActionRequest(
        ActionKey(3, 7, 1),
        CommandIntent(
            CommandKind.CLOSE_SHOWN_WINDOW
            if numbered
            else CommandKind.CLOSE_APP_WINDOW,
            "desktop" if numbered else app,
            window_index=2 if numbered else None,
        ),
        "fa",
    )
    result = executor.execute(request)
    assert len(prompts) == 1
    prompt = prompts[0]
    assert prompt.key == request.key
    assert prompt.capability is ControlCapability.CLOSE_WINDOW
    assert prompt.window == controller.window
    assert prompt.target.source == "window" and prompt.language == "fa"
    assert controller.prepared == [(request.intent.target, request.intent.window_index)]
    assert controller.calls == []  # No app-name-only control(CLOSE).
    assert controller.closed == ([controller.window] if approved else [])
    assert result.outcome is (
        ActionOutcome.CONFIRMED if approved else ActionOutcome.FAILED
    )


@pytest.mark.parametrize(
    "change", ["expiry", "cancel", "permission", "wrong_app", "window_permission"]
)
@pytest.mark.parametrize("native", [False, True])
def test_stale_or_unpermitted_close_never_reaches_platform_commit(
    monkeypatch: pytest.MonkeyPatch, change: str, native: bool
) -> None:
    controller = StubController(WindowControlStatus.CONFIRMED)
    now = [controller.window.observed_at + 1]
    monkeypatch.setattr(window_control, "monotonic", lambda: now[0])
    context = ActionExecutionContext(1)

    def decision(window: WindowObservation) -> bool:
        if change == "expiry":
            now[0] = window.deadline
        elif change == "cancel":
            context.cancel()
        else:
            pytest.fail("unpermitted or mismatched app must fail before consent")
        return True

    if native:
        monkeypatch.setattr(
            controller,
            "confirm_close",
            lambda window, language: decision(window),
            raising=False,
        )

    def confirm(prompt: ControlConfirmation) -> bool:
        assert not native, "native confirmation must not fall back to Qt"
        return decision(prompt.window)

    executor = WindowControlExecutor(
        StubFallback(),
        controller,
        confirmation=confirm,
        allowed_close_apps=(
            frozenset() if change == "permission" else frozenset({"telegram"})
        ),
    )
    result = executor.execute(
        ActionRequest(
            ActionKey(1, 1),
            CommandIntent(
                CommandKind.CLOSE_SHOWN_WINDOW
                if change == "window_permission"
                else CommandKind.CLOSE_APP_WINDOW,
                "other" if change == "wrong_app" else "telegram",
                window_index=2 if change == "window_permission" else None,
            ),
            context=context,
        )
    )
    assert result.outcome in {ActionOutcome.FAILED, ActionOutcome.UNKNOWN}
    assert not controller.closed and not controller.calls


def test_declined_native_confirmation_does_not_fall_back_or_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = StubController(WindowControlStatus.CONFIRMED)
    monkeypatch.setattr(controller, "confirm_close", lambda *args: False, raising=False)
    fallback = StubFallback()
    executor = WindowControlExecutor(
        fallback,
        controller,
        confirmation=lambda prompt: pytest.fail("must not ask twice"),
        allowed_close_apps=frozenset({"telegram"}),
    )
    result = executor.execute(
        ActionRequest(
            ActionKey(1, 1), CommandIntent(CommandKind.CLOSE_APP_WINDOW, "telegram")
        )
    )
    assert result.error_code == "window_close_confirmation_declined"
    assert not controller.closed and not controller.calls and not fallback.calls


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
