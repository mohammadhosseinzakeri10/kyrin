"""Bulk close keeps independent permission, one-use snapshot and native approval."""

from dataclasses import replace
from time import monotonic

import pytest

from kyrin.actions.cancellation import ActionExecutionContext
from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest
from kyrin.actions.window_control import WindowControlExecutor
from kyrin.app.permissions import PermissionPolicy
from kyrin.app.settings import AllowedApp, AppSettings
from kyrin.commands.models import CommandIntent, CommandKind
from kyrin.desktop.window_control import WindowControlStatus
from kyrin.desktop.window_group import WindowGroupObservation
from kyrin.desktop.window_observation import WindowObservation
from tests.actions.test_window_control import StubController, StubFallback


class GroupController(StubController):
    def __init__(self) -> None:
        super().__init__(WindowControlStatus.CONFIRMED)
        now = monotonic()
        self.group = WindowGroupObservation(
            tuple(
                WindowObservation("telegram", 42, str(i), "group", now, now + 10)
                for i in (1, 2)
            )
        )
        self.approved = True
        self.group_calls: list[str] = []
        self.context: ActionExecutionContext | None = None

    def prepare_close_all(self, app: str) -> WindowGroupObservation:
        self.group_calls.append("prepare")
        return self.group

    def confirm_close_all(
        self, group: WindowGroupObservation, language: str | None
    ) -> bool:
        self.group_calls.append("confirm")
        if self.context is not None:
            self.context.cancel()
        return self.approved

    def close_all_confirmed(self, group: WindowGroupObservation) -> WindowControlStatus:
        self.group_calls.append("close")
        return self.status


@pytest.mark.parametrize(
    "change",
    [
        "none",
        "deny",
        "decline",
        "wrong_app",
        "expired",
        "cancelled",
        "cancel_during_confirm",
        "uncertain",
    ],
)
def test_bulk_close_is_guarded_even_with_remembered_permission(change: str) -> None:
    controller = GroupController()
    settings = AppSettings(
        action_execution_enabled=True,
        allowed_apps=(AllowedApp("telegram", "telegram.desktop"),),
        allowed_close_apps=() if change == "deny" else ("telegram",),
    )
    context = ActionExecutionContext(1)
    if change == "decline":
        controller.approved = False
    elif change == "wrong_app":
        controller.group = WindowGroupObservation(
            tuple(replace(w, app_id="other") for w in controller.group.windows)
        )
    elif change == "expired":
        now = monotonic()
        controller.group = WindowGroupObservation(
            tuple(
                replace(w, observed_at=now - 20, deadline=now - 11)
                for w in controller.group.windows
            )
        )
    elif change == "cancelled":
        context.cancel()
    elif change == "cancel_during_confirm":
        controller.context = context
    elif change == "uncertain":
        controller.status = WindowControlStatus.UNKNOWN
    executor = WindowControlExecutor(
        StubFallback(),
        controller,
        permissions=PermissionPolicy(settings),
        allowed_close_apps=frozenset({"telegram"}),
    )
    result = executor.execute(
        ActionRequest(
            ActionKey(1, 1),
            CommandIntent(CommandKind.CLOSE_ALL_APP_WINDOWS, "telegram"),
            "en",
            context=context,
        )
    )
    assert (result.outcome is ActionOutcome.CONFIRMED) == (change == "none")
    assert ("close" in controller.group_calls) == (change in {"none", "uncertain"})
    if change == "none":
        assert controller.group_calls == ["prepare", "confirm", "close"]
    assert not controller.closed and not controller.prepared and not controller.calls


@pytest.mark.parametrize("change", ["duplicate", "different_app", "too_many"])
def test_group_snapshot_rejects_inconsistent_or_unbounded_members(change: str) -> None:
    group = GroupController().group
    windows = (
        (group.windows[0], group.windows[0])
        if change == "duplicate"
        else (group.windows[0], replace(group.windows[1], app_id="other"))
        if change == "different_app"
        else tuple(replace(group.windows[0], window_token=str(i)) for i in range(33))
    )
    with pytest.raises(ValueError):
        WindowGroupObservation(windows)
