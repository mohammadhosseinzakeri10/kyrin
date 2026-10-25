"""Persistent consent does not provide target evidence or a live request."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from kyrin.actions.authorized import PermissionExecutor
from kyrin.actions.cancellation import ActionExecutionContext
from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import (
    ActionKey,
    ActionNotice,
    ActionNoticeReason,
    ActionOutcome,
    ActionRequest,
    ActionResult,
)
from kyrin.app.permissions import CAPABILITIES, Capability, PermissionPolicy
from kyrin.app.settings import AllowedApp, AppSettings
from kyrin.app.settings_store import JsonSettingsStore, SettingsError
from kyrin.commands.models import CommandIntent, CommandKind, CommandResolution
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog


@pytest.mark.parametrize("trust", [False, True])
def test_saved_close_consent_survives_restart_and_revocation(
    tmp_path: Path, trust: bool
) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    settings = AppSettings(
        action_execution_enabled=True,
        trust_all_capabilities=trust,
        allowed_apps=(AllowedApp("chrome", "chrome.desktop"),),
        allowed_close_apps=("chrome",),
    )
    store.save(settings)
    reopened = JsonSettingsStore(store.path).load()
    intent = CommandIntent(CommandKind.CLOSE_APP_WINDOW, "chrome")
    assert PermissionPolicy(reopened).allows_intent(intent)
    store.save(replace(reopened, trust_all_capabilities=False, allowed_close_apps=()))
    assert not PermissionPolicy(JsonSettingsStore(store.path).load()).allows_intent(
        intent
    )


def test_old_settings_keep_scoped_consent_without_enabling_global_trust(
    tmp_path: Path,
) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(
        AppSettings(
            action_execution_enabled=True,
            allowed_apps=(AllowedApp("chrome", "chrome.desktop"),),
            allowed_close_apps=("chrome",),
        )
    )
    document = json.loads(store.path.read_text())
    document["schema_version"] = 16
    del document["trust_all_capabilities"], document["capability_grants"]
    store.path.write_text(json.dumps(document))
    policy = PermissionPolicy(store.load())
    assert policy.allows("close_window", "chrome")
    assert not policy.settings.trust_all_capabilities
    assert not policy.allows("system_power")


@pytest.mark.parametrize("value", [1, "true", None, []])
def test_malformed_trust_is_never_a_grant(tmp_path: Path, value: object) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(AppSettings())
    document = json.loads(store.path.read_text())
    document["trust_all_capabilities"] = value
    store.path.write_text(json.dumps(document))
    with pytest.raises(SettingsError):
        store.load()


def test_trust_covers_new_registered_capability_without_new_confirmation_logic(
    tmp_path: Path,
) -> None:
    # Simulate a future supported command being registered with this capability.
    future = Capability(
        "future_input",
        "Future input",
        "ورودی آینده",
        frozenset({CommandKind.VISIBLE_CONTROL}),
    )
    registry = tuple(
        item for item in CAPABILITIES if item.identifier != "desktop_control"
    ) + (future,)
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(action_execution_enabled=True, trust_all_capabilities=True))
    policy = PermissionPolicy(store.load(), registry)
    intent = CommandIntent(CommandKind.VISIBLE_CONTROL, "Mode")
    gate = ActionGate(
        ActionPolicy(
            authorize=policy.allows_intent, supported_kinds=frozenset({intent.kind})
        )
    )
    assert isinstance(gate.observe(CommandResolution(0, intent)), ActionRequest)
    assert not policy.allows("not_registered")
    granular = PermissionPolicy(
        replace(
            policy.settings,
            trust_all_capabilities=False,
            capability_grants=("future_input",),
        ),
        registry,
    )
    assert granular.allows_intent(intent)
    assert not PermissionPolicy(
        replace(granular.settings, capability_grants=()), registry
    ).allows_intent(intent)


def test_every_current_command_declares_one_permission() -> None:
    kinds = [kind for item in CAPABILITIES for kind in item.kinds]
    assert len(kinds) == len(set(kinds))
    assert set(kinds) == set(CommandKind)


@pytest.mark.parametrize("clarification", ["action", "number", "name", "windows"])
def test_saved_consent_removes_action_questions_but_preserves_target_choices(
    clarification: str,
) -> None:
    from kyrin.commands.app_names import SpokenAppCandidate
    from kyrin.commands.coordinator import CommandCoordinator
    from kyrin.commands.interpreter import Interpretation, NeedsClarification
    from kyrin.commands.models import (
        CommandContext,
        PendingActionConfirmation,
        PendingAppClarification,
        PendingCommandClarification,
        PendingNumberedCloseConfirmation,
        PendingWindowSelection,
        ResponseRequest,
    )
    from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate

    candidate = SpokenAppCandidate("terminal", "Terminal")
    questions: dict[str, PendingCommandClarification] = {
        "action": PendingActionConfirmation(candidate, CommandKind.CLOSE_APP_WINDOW),
        "number": PendingNumberedCloseConfirmation(candidate, 2, 3),
        "name": PendingAppClarification(
            (candidate,), confirmation=True, operation=CommandKind.CLOSE_APP_WINDOW
        ),
        "windows": PendingWindowSelection(candidate, 3),
    }

    class Interpreter:
        def interpret(
            self,
            text: str,
            *,
            language: str | None,
            context: CommandContext,
            pending: PendingCommandClarification | None,
        ) -> Interpretation:
            return NeedsClarification(questions[clarification])

    policy = PermissionPolicy(
        AppSettings(action_execution_enabled=True, trust_all_capabilities=True)
    )
    coordinator = CommandCoordinator(
        Interpreter(), action_authorizer=policy.allows_intent
    )
    events = coordinator.observe(
        TranscriptUpdate(0, "Close Terminal", TranscriptStatus.FINAL, "en")
    )
    assert any(isinstance(event, ResponseRequest) for event in events) == (
        clarification in {"name", "windows"}
    )
    intents = [
        event.intent
        for event in events
        if isinstance(event, CommandResolution) and event.intent
    ]
    assert bool(intents) == (clarification in {"action", "number"})
    if clarification == "number":
        assert intents[0].window_index == 2


def test_trust_expansion_preserves_granular_settings_and_discovers_new_apps(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "applications"
    directory.mkdir()

    def install(name: str) -> None:
        (directory / f"{name}.desktop").write_text(
            f"[Desktop Entry]\nType=Application\nName={name}\nExec=true\n"
        )

    install("first")
    policy = PermissionPolicy(
        AppSettings(action_execution_enabled=True, trust_all_capabilities=True)
    )
    catalog = XdgDesktopAppCatalog((tmp_path,))
    assert len(policy.effective_settings(catalog).allowed_apps) == 1
    install("second")
    assert (
        len(policy.effective_settings(XdgDesktopAppCatalog((tmp_path,))).allowed_apps)
        == 2
    )
    assert policy.settings.allowed_apps == ()
    assert (
        PermissionPolicy(replace(policy.settings, trust_all_capabilities=False))
        .effective_settings(catalog)
        .allowed_apps
        == ()
    )


@pytest.mark.parametrize(
    "enabled,granted,cancelled",
    [
        (True, True, False),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ],
)
def test_gate_and_execution_share_consent_and_cancellation(
    enabled: bool, granted: bool, cancelled: bool
) -> None:
    policy = PermissionPolicy(
        AppSettings(action_execution_enabled=enabled, allow_desktop_scroll=granted)
    )
    intent = CommandIntent(CommandKind.SCROLL_UP, "focused.desktop")
    gate = ActionGate(
        ActionPolicy(
            authorize=policy.allows_intent, supported_kinds=frozenset({intent.kind})
        )
    )
    decision = gate.observe(CommandResolution(0, intent))
    calls: list[ActionRequest] = []

    class Delegate:
        def execute(self, request: ActionRequest) -> ActionResult:
            calls.append(request)
            return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

    context = ActionExecutionContext(1)
    if cancelled:
        context.cancel()
    request = ActionRequest(ActionKey(0, 0), intent, context=context)
    result = PermissionExecutor(Delegate(), policy).execute(request)
    assert bool(calls) == (enabled and granted and not cancelled)
    if not enabled or not granted:
        assert isinstance(decision, ActionNotice)
        assert decision.reason is ActionNoticeReason.NOT_ALLOWED
        assert result.error_code == "action_not_allowed"
