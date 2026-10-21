"""Generic visible controls stay bound to one focused window and one label."""

import subprocess

import pytest

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import (
    ActionKey,
    ActionNotice,
    ActionNoticeReason,
    ActionOutcome,
    ActionRequest,
    ActionResult,
)
from kyrin.actions.platforms import desktop_control
from kyrin.actions.visible_control import VisibleControlTarget, unique_visible_target
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.interpreter import ReadyCommand
from kyrin.commands.models import (
    CommandContext,
    CommandIntent,
    CommandKind,
    CommandResolution,
)
from kyrin.vision.ocr.contracts import OcrDevice, OcrResult, RecognizedText, TextBox
from kyrin.vision.text_reader import IdentifiedWindowText


class Delegate:
    def execute(self, request: ActionRequest) -> ActionResult:
        return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)


class Verifier:
    def __init__(self, target: VisibleControlTarget | None) -> None:
        self.target = target

    def ready(self) -> bool:
        return True

    def find_visible_control(
        self, app_id: str, pid: int, label: str
    ) -> VisibleControlTarget | None:
        assert (app_id, pid, label) == ("example.desktop", 42, "Advanced")
        return self.target


def _observation(*spans: RecognizedText) -> IdentifiedWindowText:
    return IdentifiedWindowText(
        "example.desktop",
        42,
        OcrResult(spans, "eng", OcrDevice.CPU, "test"),
        (800, 600),
    )


def test_visible_target_requires_one_confident_label() -> None:
    title = RecognizedText("Advanced", TextBox(40, 80, 90, 18), 0.9)
    assert unique_visible_target(
        _observation(title), "example.desktop", 42, "advanced"
    ) == (VisibleControlTarget(40, 80, 90, 18, 800, 600))
    duplicate = RecognizedText("Advanced", TextBox(40, 150, 90, 18), 0.9)
    assert (
        unique_visible_target(
            _observation(title, duplicate), "example.desktop", 42, "advanced"
        )
        is None
    )
    assert (
        unique_visible_target(_observation(title), "other.desktop", 42, "advanced")
        is None
    )
    low = RecognizedText("Advanced", TextBox(40, 80, 90, 18), 0.3)
    assert (
        unique_visible_target(_observation(low), "example.desktop", 42, "advanced")
        is None
    )


def test_generic_command_requires_current_focus_and_permission() -> None:
    rules = DemoCommandInterpreter(control_any_focused_app=True)
    context = CommandContext(observed_scroll_app="example.desktop")
    assert rules.interpret(
        "Go to Advanced", language="en", context=context, pending=None
    ) == ReadyCommand(CommandIntent(CommandKind.VISIBLE_CONTROL, "Advanced"))
    assert rules.interpret(
        "Go to Settings", language="en", context=context, pending=None
    ) == ReadyCommand(CommandIntent(CommandKind.VISIBLE_CONTROL, "Settings"))
    assert rules.interpret(
        "Turn on Notifications", language="en", context=context, pending=None
    ) == ReadyCommand(
        CommandIntent(CommandKind.VISIBLE_CONTROL, "Notifications", control_state=True)
    )
    intent = CommandIntent(CommandKind.VISIBLE_CONTROL, "Advanced")
    denied = ActionGate(ActionPolicy(supported_kinds=frozenset({intent.kind})))
    assert denied.observe(CommandResolution(0, intent)) == ActionNotice(
        ActionKey(0, 0), intent, ActionNoticeReason.NOT_ALLOWED
    )
    allowed = ActionGate(
        ActionPolicy(
            allow_focused_control=True,
            supported_kinds=frozenset({intent.kind}),
        )
    )
    assert allowed.observe(CommandResolution(0, intent)) == ActionRequest(
        ActionKey(0, 0), intent
    )


def test_focused_click_dispatches_one_checked_box(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, "CLICK_DISPATCHED", "")

    monkeypatch.setattr(desktop_control.subprocess, "run", run)
    request = ActionRequest(
        ActionKey(0, 1), CommandIntent(CommandKind.VISIBLE_CONTROL, "Advanced")
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: ("example.desktop", 42),
        verifier=Verifier(VisibleControlTarget(40, 80, 90, 18, 800, 600)),
    )
    assert executor.execute(request) == ActionResult(
        request.key, ActionOutcome.LAUNCH_ACCEPTED
    )
    assert commands[0][-9:] == [
        "40",
        "80",
        "90",
        "18",
        "800",
        "600",
        "click",
        "Advanced",
        "visible",
    ]


def test_focus_change_stops_before_input(monkeypatch: pytest.MonkeyPatch) -> None:
    observations = iter((("example.desktop", 42), ("other.desktop", 7)))
    monkeypatch.setattr(
        desktop_control.subprocess, "run", lambda *_a, **_k: pytest.fail("no input")
    )
    request = ActionRequest(
        ActionKey(0, 1), CommandIntent(CommandKind.VISIBLE_CONTROL, "Advanced")
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: next(observations),
        verifier=Verifier(VisibleControlTarget(40, 80, 90, 18, 800, 600)),
    )
    assert executor.execute(request).error_code == "visible_control_focus_changed"


def test_unlabeled_icon_uses_accessibility_and_unknown_state_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 2, "STATE_UNAVAILABLE", "")

    monkeypatch.setattr(desktop_control.subprocess, "run", run)
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(CommandKind.VISIBLE_CONTROL, "Advanced", control_state=True),
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: ("example.desktop", 42),
        verifier=Verifier(None),
    )
    assert executor.execute(request).error_code == "visible_control_state_unavailable"
    assert commands[0][-1] == "accessible"
