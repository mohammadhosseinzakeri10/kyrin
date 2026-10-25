"""A real executor must require scoped consent for non-navigation controls."""

import json
import subprocess
from dataclasses import replace
from time import monotonic

import pytest

from kyrin.actions.cancellation import ActionExecutionContext
from kyrin.actions.control_policy import (
    ControlApproval,
    ControlCapability,
    ControlConfirmation,
    ControlEvidence,
)
from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.platforms import desktop_control
from kyrin.actions.visible_control import VisibleControlTarget
from kyrin.commands.models import CommandIntent, CommandKind
from kyrin.desktop.accessibility_target import AccessibilityTarget
from kyrin.desktop.window_observation import WindowObservation
from kyrin.vision.capture_geometry import CaptureGeometry


class Delegate:
    def execute(self, request: ActionRequest) -> ActionResult:
        pytest.fail("control must not delegate")


def request(label: str, state: bool | None = None) -> ActionRequest:
    now = monotonic()
    return ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL,
            label,
            control_state=state,
            control_observation=WindowObservation(
                "example.desktop", 42, "window-7", "initial-1", now, now + 10
            ),
        ),
    )


@pytest.mark.parametrize(
    "label", ["تنظیمات", "جست‌وجو", "Einstellungen", "Paramètres", "Ayuda"]
)
def test_multilingual_navigation_reaches_supported_tool(
    monkeypatch: pytest.MonkeyPatch,
    label: str,
) -> None:
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "ACTION_DISPATCHED", "")

    monkeypatch.setattr(desktop_control, "run_process", run)
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: ("example.desktop", 42),
        token_reader=lambda: "window-7",
    )
    assert (
        executor.execute(request(label)).outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    )
    assert len(calls) == 1 and calls[0][2] == "semantic"


def test_confirmed_unknown_control_resolves_again_before_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = ControlEvidence(
        "Apply All Devices",
        "accessibility",
        "BUTTON",
        None,
        (85, 90),
        AccessibilityTarget(
            ((0, "FRAME", "Example"), (1, "BUTTON", "Apply All Devices"))
        ),
    )
    events: list[str] = []

    def resolve(*args: object) -> ControlEvidence:
        events.append("resolve")
        return evidence

    def confirm(prompt: object) -> bool:
        events.append("dialog")
        return True

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        events.append("input")
        return subprocess.CompletedProcess(args, 0, "ACTION_DISPATCHED", "")

    monkeypatch.setattr(desktop_control, "run_process", run)
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: ("example.desktop", 42),
        token_reader=lambda: "window-7",
        confirmation=confirm,
        control_resolver=resolve,
    )
    assert (
        executor.execute(request(evidence.label)).outcome
        is ActionOutcome.DISPATCHED_UNVERIFIED
    )
    assert events == ["resolve", "dialog", "resolve", "input"]


@pytest.mark.parametrize("change", ["none", "target", "cancelled", "denied"])
def test_saved_control_consent_replaces_only_the_dialog(
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    from kyrin.app.permissions import PermissionPolicy
    from kyrin.app.settings import AppSettings

    events: list[str] = []
    context = ActionExecutionContext(1)
    target = evidence("Mode")

    def resolve(*args: object) -> ControlEvidence:
        events.append("resolve")
        if change == "cancelled":
            context.cancel()
        return (
            replace(target, anchor=(1, 2))
            if change == "target" and len(events) > 1
            else target
        )

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        events.append("input")
        return subprocess.CompletedProcess(args, 0, "ACTION_DISPATCHED", "")

    monkeypatch.setattr(desktop_control, "run_process", run)
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: ("example.desktop", 42),
        token_reader=lambda: "window-7",
        control_resolver=resolve,
        permissions=PermissionPolicy(
            AppSettings(
                action_execution_enabled=True, allow_desktop_control=change != "denied"
            )
        ),
        confirmation=lambda _: pytest.fail("saved control opened confirmation"),
    )
    executor.execute(replace(request("Mode"), context=context))
    assert ("input" in events) == (change == "none")
    if change == "none":
        assert events == ["resolve", "resolve", "input"]


def evidence(label: str = "Mode", checked: bool | None = None) -> ControlEvidence:
    return ControlEvidence(
        label,
        "accessibility",
        "BUTTON",
        checked,
        (85, 90),
        AccessibilityTarget(((0, "FRAME", "Example"), (1, "BUTTON", label))),
    )


def prompt() -> ControlConfirmation:
    action = request("Mode")
    assert action.intent.control_observation is not None
    return ControlConfirmation(
        action.key,
        ControlCapability.ACTIVATE,
        evidence(),
        action.intent.control_observation,
        None,
    )


@pytest.mark.parametrize("change", ["operation", "key", "target", "window", "state"])
def test_approval_is_bound_and_bad_consumption_burns_it(change: str) -> None:
    original = prompt()
    modified = {
        "operation": replace(original, capability=ControlCapability.SET_STATE),
        "key": replace(original, key=ActionKey(0, 2)),
        "target": replace(original, target=evidence("Other")),
        "window": replace(
            original, window=replace(original.window, window_token="other")
        ),
        "state": replace(original, desired_state=True),
    }[change]
    approval = ControlApproval(original)
    assert not approval.consume(modified, original.window.observed_at + 1)
    assert not approval.consume(original, original.window.observed_at + 1)


def test_approval_expires_and_can_only_be_used_once() -> None:
    original = prompt()
    approval = ControlApproval(original)
    assert approval.consume(original, original.window.observed_at + 1)
    assert not approval.consume(original, original.window.observed_at + 1)
    assert not ControlApproval(original).consume(original, original.window.deadline)


@pytest.mark.parametrize(
    "change", ["label", "anchor", "ancestry", "checked", "role", "gone"]
)
def test_target_changed_during_dialog_never_reaches_input(
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    before = evidence()
    after = {
        "label": replace(before, label="Other"),
        "anchor": replace(before, anchor=(86, 90)),
        "ancestry": replace(
            before, accessibility=AccessibilityTarget(((2, "BUTTON", "Mode"),))
        ),
        "checked": replace(before, checked=True),
        "role": replace(before, role="SWITCH"),
        "gone": None,
    }[change]
    observations = iter((before, after))
    monkeypatch.setattr(
        desktop_control, "run_process", lambda *_a, **_k: pytest.fail("no input")
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: ("example.desktop", 42),
        token_reader=lambda: "window-7",
        confirmation=lambda _p: True,
        control_resolver=lambda *_a: next(observations),
    )
    assert (
        executor.execute(request("Mode")).error_code == "visible_control_target_changed"
    )


@pytest.mark.parametrize("change", ["window", "expiry", "cancel"])
def test_old_or_cancelled_confirmation_never_reaches_input(
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    action = request("Mode")
    assert action.intent.control_observation is not None
    observation = action.intent.control_observation
    now = [observation.observed_at + 1]
    token = ["window-7"]
    context = ActionExecutionContext(1)
    action = replace(action, context=context)
    monkeypatch.setattr(desktop_control, "monotonic", lambda: now[0])
    monkeypatch.setattr(
        desktop_control, "run_process", lambda *_a, **_k: pytest.fail("no input")
    )

    def confirm(_prompt: ControlConfirmation) -> bool:
        if change == "window":
            token[0] = "window-8"
        elif change == "expiry":
            now[0] = observation.deadline
        else:
            context.cancel()
        return True

    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: observation.identity,
        token_reader=lambda: token[0],
        confirmation=confirm,
        control_resolver=lambda *_a: evidence(),
    )
    result = executor.execute(action)
    assert result.error_code == (
        "action_interrupted"
        if change == "cancel"
        else "visible_control_confirmation_expired"
    )


def test_declining_confirmation_does_not_resolve_or_input_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolutions: list[str] = []

    def resolve(*_args: object) -> ControlEvidence:
        resolutions.append("read")
        return evidence()

    monkeypatch.setattr(
        desktop_control, "run_process", lambda *_a, **_k: pytest.fail("no input")
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: ("example.desktop", 42),
        token_reader=lambda: "window-7",
        confirmation=lambda _p: False,
        control_resolver=resolve,
    )
    assert (
        executor.execute(request("Mode")).error_code
        == "visible_control_confirmation_declined"
    )
    assert resolutions == ["read"]


@pytest.mark.parametrize("label", ["Send", "Delete", "Pay", "ارسال", "حذف", "پرداخت"])
def test_generic_consent_never_authorizes_unsupported_consequence(
    monkeypatch: pytest.MonkeyPatch,
    label: str,
) -> None:
    monkeypatch.setattr(
        desktop_control, "run_process", lambda *_a, **_k: pytest.fail("no input")
    )

    def forbidden(*_args: object) -> bool:
        pytest.fail("no generic confirmation for unsupported consequence")

    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: ("example.desktop", 42),
        token_reader=lambda: "window-7",
        confirmation=forbidden,
    )
    assert executor.execute(request(label)).error_code == "visible_control_sensitive"


@pytest.mark.parametrize("label", ["Settings", "Mode"])
def test_permission_does_not_create_missing_tool_capability(
    monkeypatch: pytest.MonkeyPatch,
    label: str,
) -> None:
    monkeypatch.setattr(
        desktop_control, "run_process", lambda *_a, **_k: pytest.fail("no input")
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: ("example.desktop", 42),
        token_reader=lambda: "window-7",
        confirmation=lambda _p: True,
        capabilities=frozenset(),
    )
    assert (
        executor.execute(request(label)).error_code
        == "visible_control_capability_required"
    )


@pytest.mark.parametrize("desired", [True, False])
def test_confirmed_boolean_control_uses_desired_state_and_real_read_only_resolver(
    monkeypatch: pytest.MonkeyPatch,
    desired: bool,
) -> None:
    target = evidence("Notifications", checked=not desired)
    assert target.accessibility is not None
    structural_json = target.accessibility.to_json()
    calls: list[list[str]] = []
    prompts: list[ControlConfirmation] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[1].endswith("desktop_accessibility_inventory.py"):
            assert kwargs.get("helper") is None
            return subprocess.CompletedProcess(
                args,
                0,
                json.dumps(
                    [
                        {
                            "label": target.label,
                            "role": "CHECK_BOX",
                            "checked": not desired,
                            "x": 85,
                            "y": 90,
                            "accessibility": structural_json,
                        }
                    ]
                ),
                "",
            )
        assert args[2] == "semantic" and args[5] == ("on" if desired else "off")
        assert "consent=" + json.dumps([85, 90, not desired]) in args
        return subprocess.CompletedProcess(args, 0, "STATE_CONFIRMED", "")

    def confirm(value: ControlConfirmation) -> bool:
        prompts.append(value)
        return True

    monkeypatch.setattr(desktop_control, "run_process", run)
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: ("example.desktop", 42),
        token_reader=lambda: "window-7",
        confirmation=confirm,
    )
    assert (
        executor.execute(request(target.label, desired)).outcome
        is ActionOutcome.CONFIRMED
    )
    assert len(calls) == 3
    assert len(prompts) == 1 and prompts[0].desired_state is desired
    assert prompts[0].capability is ControlCapability.SET_STATE


def test_unknown_toggle_without_observed_boolean_cannot_ask_for_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(_prompt: ControlConfirmation) -> bool:
        pytest.fail("unreadable state must fail before dialog")

    monkeypatch.setattr(
        desktop_control, "run_process", lambda *_a, **_k: pytest.fail("no input")
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: ("example.desktop", 42),
        token_reader=lambda: "window-7",
        confirmation=forbidden,
        control_resolver=lambda *_a: evidence(),
    )
    assert (
        executor.execute(request("Mode", True)).error_code
        == "visible_control_state_unavailable"
    )


@pytest.mark.parametrize("move_on_read", [0, 3])
def test_ocr_consent_rechecks_exact_box_even_after_dialog_resolution(
    monkeypatch: pytest.MonkeyPatch,
    move_on_read: int,
) -> None:
    now = monotonic()
    geometry = CaptureGeometry(
        "logical_desktop",
        0,
        (0, 0, 800, 600),
        (800, 600),
        1,
        1,
        (0, 0, 0, 0),
        (0, 0),
        (1, 1),
        "window-7",
        "fresh",
        now,
        (0, 0, 800, 600),
    )
    reads = 0
    inputs: list[list[str]] = []

    class Verifier:
        def ready(self) -> bool:
            return True

        def find_visible_control(self, *_args: object) -> VisibleControlTarget:
            nonlocal reads
            reads += 1
            return VisibleControlTarget(
                41 if reads == move_on_read else 40,
                80,
                90,
                20,
                800,
                600,
                geometry=geometry,
            )

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        inputs.append(args)
        return subprocess.CompletedProcess(args, 0, "CLICK_DISPATCHED", "")

    monkeypatch.setattr(desktop_control, "run_process", run)
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: ("example.desktop", 42),
        token_reader=lambda: "window-7",
        verifier=Verifier(),
        confirmation=lambda _p: True,
    )
    action = request("Apply All Devices")
    action = replace(action, intent=replace(action.intent, control_source="ocr"))
    result = executor.execute(action)
    assert reads == 3
    if move_on_read:
        assert result.error_code == "visible_control_target_changed"
        assert inputs == []
    else:
        assert result.outcome is ActionOutcome.DISPATCHED_UNVERIFIED
        assert len(inputs) == 1
