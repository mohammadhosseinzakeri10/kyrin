"""A saved opt-in removes only the group dialog, never scope or execution gates."""

from dataclasses import replace
from pathlib import Path

import pytest

from kyrin.actions.cancellation import ActionExecutionContext
from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest
from kyrin.actions.window_control import WindowControlExecutor
from kyrin.app.permissions import PermissionPolicy
from kyrin.app.settings import AllowedApp, AppSettings
from kyrin.app.settings_store import JsonSettingsStore
from kyrin.commands.models import CommandIntent, CommandKind
from kyrin.desktop.window_control import WindowControlStatus
from kyrin.desktop.window_group import WindowGroupObservation
from tests.actions.test_window_control import StubFallback
from tests.actions.test_window_group_close import GroupController

GRANT = "close_all_without_confirmation"


class AuthorizedGroup(GroupController):
    def close_all_authorized(
        self, group: WindowGroupObservation
    ) -> WindowControlStatus:
        self.group_calls.append("authorized")
        return self.status


@pytest.mark.parametrize(
    "mode",
    [
        "default",
        "grant",
        "trust",
        "disabled",
        "no_app",
        "revoked",
        "cancelled",
        "wrong_app",
        "uncertain",
    ],
)
def test_saved_bulk_grant_removes_dialog_only_when_authorized(mode: str) -> None:
    settings = AppSettings(
        action_execution_enabled=mode != "disabled",
        trust_all_capabilities=mode == "trust",
        capability_grants=() if mode in {"default", "revoked"} else (GRANT,),
        allowed_apps=(AllowedApp("telegram", "telegram.desktop"),),
        allowed_close_apps=() if mode == "no_app" else ("telegram",),
    )
    controller = AuthorizedGroup()
    if mode == "wrong_app":
        controller.group = WindowGroupObservation(
            tuple(replace(w, app_id="other") for w in controller.group.windows)
        )
    if mode == "uncertain":
        controller.status = WindowControlStatus.UNKNOWN
    context = ActionExecutionContext(7)
    if mode == "cancelled":
        context.cancel()
    executor = WindowControlExecutor(
        StubFallback(),
        controller,
        permissions=PermissionPolicy(settings),
        allowed_close_apps=frozenset({"telegram"}),
    )
    result = executor.execute(
        ActionRequest(
            ActionKey(7, 1),
            CommandIntent(CommandKind.CLOSE_ALL_APP_WINDOWS, "telegram"),
            context=context,
        )
    )
    allowed = mode not in {"disabled", "no_app", "cancelled", "wrong_app"}
    direct = allowed and mode not in {"default", "revoked"}
    assert ("authorized" in controller.group_calls) == direct
    assert ("confirm" in controller.group_calls) == (allowed and not direct)
    assert (result.outcome is ActionOutcome.CONFIRMED) == (
        allowed and mode != "uncertain"
    )


def test_bulk_opt_in_roundtrip_and_revocation_do_not_grant_close(
    tmp_path: Path,
) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(action_execution_enabled=True, capability_grants=(GRANT,)))
    reopened = store.load()
    policy = PermissionPolicy(reopened)
    assert policy.allows(GRANT)
    assert not policy.allows_intent(
        CommandIntent(CommandKind.CLOSE_ALL_APP_WINDOWS, "telegram")
    )
    store.save(replace(reopened, capability_grants=()))
    assert not PermissionPolicy(store.load()).allows(GRANT)


def test_cancel_after_prepare_still_blocks_saved_group_commit() -> None:
    context = ActionExecutionContext(9)

    class CancelsOnPrepare(AuthorizedGroup):
        def prepare_close_all(self, app: str) -> WindowGroupObservation:
            group = super().prepare_close_all(app)
            context.cancel()
            return group

    controller = CancelsOnPrepare()
    policy = PermissionPolicy(
        AppSettings(
            action_execution_enabled=True,
            allowed_close_apps=("telegram",),
            allowed_apps=(AllowedApp("telegram", "telegram.desktop"),),
            capability_grants=(GRANT,),
        )
    )
    result = WindowControlExecutor(
        StubFallback(),
        controller,
        permissions=policy,
        allowed_close_apps=frozenset({"telegram"}),
    ).execute(
        ActionRequest(
            ActionKey(9, 1),
            CommandIntent(CommandKind.CLOSE_ALL_APP_WINDOWS, "telegram"),
            context=context,
        )
    )
    assert result.outcome is ActionOutcome.UNKNOWN
    assert controller.group_calls == ["prepare"]
