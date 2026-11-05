"""Inert targeted-tab execution preserves target, grants and one-use choice."""

import subprocess
from dataclasses import replace
from time import monotonic

import pytest

from kyrin.actions.cancellation import ActionExecutionContext
from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.platforms.desktop_control import DesktopControlExecutor
from kyrin.actions.platforms.ptyxis_tabs import PtyxisTabExecutor
from kyrin.app.permissions import PermissionPolicy
from kyrin.app.settings import AllowedApp, AppSettings
from kyrin.commands.models import CommandIntent, CommandKind
from kyrin.desktop.window_observation import WindowObservation

APP = "org.gnome.Ptyxis.desktop"
GEN = "a" * 32


class Inert:
    def __init__(self) -> None:
        self.requests: list[ActionRequest] = []

    def execute(self, request: ActionRequest) -> ActionResult:
        self.requests.append(request)
        return ActionResult(request.key, ActionOutcome.DISPATCHED_UNVERIFIED)


def setup() -> tuple[PtyxisTabExecutor, Inert, list[str]]:
    controls = Inert()
    focus = ["one"]
    executor = PtyxisTabExecutor(
        Inert(),
        controls,
        app_id="terminal",
        desktop_id=APP,
        permissions=PermissionPolicy(
            AppSettings(
                action_execution_enabled=True,
                allowed_apps=(AllowedApp("terminal", APP),),
                allowed_window_apps=("terminal",),
                allow_desktop_control=True,
            )
        ),
        identity_reader=lambda: (APP, 5),
        token_reader=lambda: focus[0],
    )
    return executor, controls, focus


def request(*, selection: bool = False) -> ActionRequest:
    now = monotonic()
    return ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.NEW_APP_TAB,
            "terminal",
            tab_selection_id=GEN if selection else None,
            window_index=2 if selection else None,
            tab_observation=None
            if selection
            else WindowObservation(APP, 5, "one", "obs", now, now + 10),
        ),
    )


def test_focused_tab_uses_explicit_accessible_menu_never_cli() -> None:
    executor, controls, _ = setup()
    req = request()
    result = executor.execute(req)
    assert result.outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert [r.intent.kind for r in controls.requests] == [CommandKind.NEW_APP_TAB]
    assert all(
        r.key == req.key and r.intent.tab_observation == req.intent.tab_observation
        for r in controls.requests
    )


@pytest.mark.parametrize(
    "case", ["focus", "expired", "cancelled", "no_control", "no_app", "disabled"]
)
def test_no_input_when_original_authority_or_target_is_invalid(case: str) -> None:
    executor, controls, focus = setup()
    req = request()
    if case == "focus":
        focus[0] = "other-window-same-process"
    elif case == "expired":
        assert req.intent.tab_observation
        w = req.intent.tab_observation
        # Derive the deadline from the shifted start, as the contract does;
        # shifting both bounds can exceed the age limit by one rounding step.
        stale = w.observed_at - 20
        req = replace(
            req,
            intent=replace(
                req.intent,
                tab_observation=replace(w, observed_at=stale, deadline=stale + 10),
            ),
        )
    elif case == "cancelled":
        ctx = ActionExecutionContext(1)
        ctx.cancel()
        req = replace(req, context=ctx)
    else:
        settings = executor._permissions.settings
        if case == "no_control":
            settings = replace(settings, allow_desktop_control=False)
        elif case == "no_app":
            settings = replace(settings, allowed_apps=(), allowed_window_apps=())
        else:
            settings = replace(settings, action_execution_enabled=False)
        executor._permissions = PermissionPolicy(settings)
    assert executor.execute(req).outcome in (
        ActionOutcome.FAILED,
        ActionOutcome.UNKNOWN,
    )
    assert not controls.requests


def test_window_change_before_helper_prevents_tab_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor, controls, focus = setup()
    real = DesktopControlExecutor(
        Inert(),
        identity_reader=lambda: (APP, 5),
        token_reader=lambda: focus[0],
        permissions=executor._permissions,
    )

    def changed(req: ActionRequest) -> ActionResult:
        focus[0] = "other"
        return real.execute(req)

    monkeypatch.setattr(controls, "execute", changed)
    assert executor.execute(request()).outcome is ActionOutcome.FAILED


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "wrong_generation",
        "stale_native",
        "other_token",
        "replay",
        "expired",
        "revoked",
        "cancel",
    ],
)
def test_selection_consumes_only_its_displayed_request(
    case: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor, controls, focus = setup()
    methods: list[str] = []

    def native(method: str, _signature: str, *_args: str) -> dict[str, object]:
        methods.append(method)
        if method == "ShowAppWindowsForTab":
            return {"status": "requested", "generation": GEN, "count": 2}
        if case == "stale_native":
            return {"status": "stale"}
        focus[0] = "wrong" if case == "other_token" else "selected-two"
        return {
            "status": "requested",
            "generation": GEN,
            "app_id": APP,
            "process_id": 5,
            "window_token": "selected-two",
        }

    monkeypatch.setattr(executor, "_call", native)
    shown = ActionRequest(
        ActionKey(0, 0),
        CommandIntent(CommandKind.SHOW_APP_WINDOWS, "terminal", tab_selection_id=GEN),
    )
    assert executor.execute(shown).outcome is ActionOutcome.LAUNCH_ACCEPTED
    assert not controls.requests
    req = request(selection=True)
    if case == "wrong_generation":
        req = replace(req, intent=replace(req.intent, tab_selection_id="b" * 32))
    elif case == "expired":
        executor._selection = (GEN, monotonic() - 1)
    elif case == "revoked":
        executor._permissions = PermissionPolicy(
            replace(executor._permissions.settings, allowed_window_apps=())
        )
    elif case == "cancel":
        executor.execute(
            ActionRequest(
                ActionKey(0, 2), CommandIntent(CommandKind.HIDE_APP_WINDOWS, "terminal")
            )
        )
    result = executor.execute(req)
    valid = case in {"valid", "replay"}
    assert (result.outcome is ActionOutcome.DISPATCHED_UNVERIFIED) is valid
    assert len(controls.requests) == (1 if valid else 0)
    calls = len(methods)
    assert executor.execute(req).outcome is ActionOutcome.FAILED
    assert len(methods) == calls


def test_semantic_failure_does_not_fall_back_to_new_terminal_or_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor, controls, _ = setup()

    def fail(req: ActionRequest) -> ActionResult:
        controls.requests.append(req)
        return ActionResult(
            req.key,
            ActionOutcome.FAILED,
            error_code="visible_control_observation:target_not_found",
        )

    monkeypatch.setattr(controls, "execute", fail)
    assert executor.execute(request()).outcome is ActionOutcome.FAILED
    assert len(controls.requests) == 1


def test_tab_client_requires_fixed_semantic_helper_and_original_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor, _, focus = setup()
    sent: list[list[str]] = []
    controls = DesktopControlExecutor(
        Inert(),
        identity_reader=lambda: (APP, 5),
        token_reader=lambda: focus[0],
        permissions=executor._permissions,
    )

    def helper(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert args[2] == "ptyxis-tab"
        assert kwargs["helper_capabilities"] == {"desktop_control-v1", "ptyxis-tab-v1"}
        assert WindowObservation.from_json(args[3]) == original.intent.tab_observation
        sent.append(args)
        return subprocess.CompletedProcess(args, 0, "TAB_ITEM:ACTION_DISPATCHED", "")

    monkeypatch.setattr("kyrin.actions.platforms.desktop_control.run_process", helper)
    executor._controls = controls
    original = request()
    assert executor.execute(original).outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert len(sent) == 1


@pytest.mark.parametrize("label,stage", [("Main Menu", "menu"), ("New Tab", "item")])
def test_tab_failure_identifies_step_and_preserves_localized_reason(
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    stage: str,
) -> None:
    from kyrin.actions.models import ActionFeedback
    from kyrin.commands.models import ResponseChannel
    from kyrin.responses.presenter import ResponsePresenter

    executor, _, focus = setup()
    reason = "visible_control_observation:target_not_found"
    controls = DesktopControlExecutor(
        Inert(),
        identity_reader=lambda: (APP, 5),
        token_reader=lambda: focus[0],
        permissions=executor._permissions,
    )

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args, 2, f"TAB_{stage.upper()}:OBSERVATION_FAILED:target_not_found", ""
        )

    monkeypatch.setattr("kyrin.actions.platforms.desktop_control.run_process", run)
    executor._controls = controls
    req = request()
    result = executor.execute(req)
    assert result.error_code == f"terminal_tab_{stage}:{reason}"
    feedback = ActionFeedback(
        req.key,
        req.intent,
        result.outcome,
        ResponseChannel.TEXT_AND_VOICE,
        error_code=result.error_code,
    )
    for locale in ("en", "fa"):
        presenter = ResponsePresenter(locale)
        assert presenter.present(feedback) == presenter.present(
            replace(feedback, error_code=reason)
        )


def test_incident_containment_returns_actionable_failure_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kyrin.actions.models import ActionFeedback
    from kyrin.commands.models import ResponseChannel
    from kyrin.responses.presenter import ResponsePresenter

    executor, _, focus = setup()
    controls = DesktopControlExecutor(
        Inert(),
        identity_reader=lambda: (APP, 5),
        token_reader=lambda: focus[0],
        permissions=executor._permissions,
    )
    calls = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(
            args, 2, "TAB_MENU:TERMINAL_MENU_AUTOMATION_BLOCKED", ""
        )

    monkeypatch.setattr("kyrin.actions.platforms.desktop_control.run_process", run)
    executor._controls = controls
    req = request()
    result = executor.execute(req)
    assert result.outcome is ActionOutcome.FAILED and len(calls) == 1
    assert result.error_code == "terminal_tab_menu:terminal_menu_automation_blocked"
    feedback = ActionFeedback(
        req.key, req.intent, result.outcome, ResponseChannel.TEXT_AND_VOICE,
        error_code=result.error_code,
    )
    for locale, text in (("en", "manually"), ("fa", "دستی")):
        rendered = ResponsePresenter(locale).present(feedback)
        assert rendered is not None and text in rendered.text


def test_explicit_keyboard_grant_routes_tab_without_popup_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor, _, focus = setup()
    policy = PermissionPolicy(replace(
        executor._permissions.settings,
        capability_grants=("terminal_tab_keyboard",),
    ))
    controls = DesktopControlExecutor(
        Inert(), permissions=policy,
        identity_reader=lambda: (APP, 5), token_reader=lambda: focus[0],
    )
    sent = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        from pathlib import Path

        assert Path(args[1]).name == "terminal_tab_helper.py"
        assert kwargs["helper_capabilities"] == {"terminal-tab-keyboard-v1"}
        sent.append(args)
        return subprocess.CompletedProcess(args, 0, "TAB_ITEM:ACTION_DISPATCHED", "")

    monkeypatch.setattr("kyrin.actions.platforms.desktop_control.run_process", run)
    executor._controls = controls
    result = executor.execute(request())
    assert result.outcome is ActionOutcome.DISPATCHED_UNVERIFIED and len(sent) == 1
