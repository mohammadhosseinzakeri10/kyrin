"""Generic visible controls stay bound to one focused window and one label."""

import subprocess
from dataclasses import replace
from time import monotonic

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
from kyrin.desktop.window_observation import WindowObservation
from kyrin.vision.capture_geometry import CaptureGeometry
from kyrin.vision.ocr.contracts import OcrDevice, OcrResult, RecognizedText, TextBox
from kyrin.vision.text_reader import IdentifiedWindowText


def _evidence() -> WindowObservation:
    now = monotonic()
    return WindowObservation(
        "example.desktop", 42, "window-7", "initial-1", now, now + 10
    )


def _geometry(width: int = 800, height: int = 600) -> CaptureGeometry:
    return CaptureGeometry(
        "logical_desktop",
        0,
        (0, 0, width, height),
        (width, height),
        1,
        1,
        (0, 0, 0, 0),
        (0, 0),
        (1, 1),
        "window-7",
        "fresh-1",
        monotonic(),
        (0, 0, width, height),
    )


def _arguments(args: list[str]) -> list[str]:
    return [arg for arg in args if not arg.startswith(("geometry=", "observation="))]


class Delegate:
    def execute(self, request: ActionRequest) -> ActionResult:
        return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)


class Verifier:
    def __init__(self, target: VisibleControlTarget | None) -> None:
        self.target = (
            replace(target, geometry=_geometry(target.image_width, target.image_height))
            if target is not None and target.geometry is None
            else target
        )

    def ready(self) -> bool:
        return True

    def find_visible_control(
        self, app_id: str, pid: int, label: str
    ) -> VisibleControlTarget | None:
        assert (app_id, pid, label) == ("example.desktop", 42, "Advanced")
        return self.target


@pytest.fixture
def no_accessible_action(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate existing coordinate-stage contracts with no semantic capability."""
    monkeypatch.setattr(
        desktop_control.DesktopControlExecutor,
        "_try_accessible",
        lambda *_a: None,
    )


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


def test_visible_target_keeps_capture_and_frame_rectangles() -> None:
    title = RecognizedText("Advanced", TextBox(40, 80, 90, 18), 0.9)
    observation = IdentifiedWindowText(
        "example.desktop",
        42,
        OcrResult((title,), "eng", OcrDevice.CPU, "test"),
        (796, 570),
        (12, 48, 796, 570),
        (10, 20, 800, 600),
    )
    assert unique_visible_target(
        observation, "example.desktop", 42, "Advanced"
    ) == VisibleControlTarget(
        40,
        80,
        90,
        18,
        796,
        570,
        (12, 48, 796, 570),
        (10, 20, 800, 600),
    )


def test_generic_command_requires_current_focus_and_permission() -> None:
    rules = DemoCommandInterpreter(control_any_focused_app=True)
    context = CommandContext(observed_scroll_app="example.desktop")
    assert rules.interpret(
        "Go to Advanced", language="en", context=context, pending=None
    ) == ReadyCommand(
        CommandIntent(
            CommandKind.VISIBLE_CONTROL,
            "Advanced",
            control_window_app="example.desktop",
        )
    )
    assert rules.interpret(
        "Go to Settings", language="en", context=context, pending=None
    ) == ReadyCommand(
        CommandIntent(
            CommandKind.VISIBLE_CONTROL,
            "Settings",
            control_window_app="example.desktop",
        )
    )
    assert rules.interpret(
        "Turn on Notifications", language="en", context=context, pending=None
    ) == ReadyCommand(
        CommandIntent(
            CommandKind.VISIBLE_CONTROL,
            "Notifications",
            control_state=True,
            control_window_app="example.desktop",
        )
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


@pytest.mark.usefixtures("no_accessible_action")
def test_focused_click_dispatches_one_checked_box(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, "CLICK_DISPATCHED", "")

    monkeypatch.setattr(desktop_control, "run_process", run)
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL, "Advanced", control_observation=_evidence()
        ),
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: ("example.desktop", 42),
        verifier=Verifier(VisibleControlTarget(40, 80, 90, 18, 800, 600)),
    )
    assert executor.execute(request) == ActionResult(
        request.key, ActionOutcome.DISPATCHED_UNVERIFIED
    )
    initial = request.intent.control_observation
    assert initial is not None
    sent_evidence = next(arg for arg in commands[0] if arg.startswith("observation="))
    assert (
        WindowObservation.from_json(sent_evidence.removeprefix("observation="))
        == initial
    )
    assert _arguments(commands[0])[-9:] == [
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


@pytest.mark.usefixtures("no_accessible_action")
def test_spoken_quotes_are_removed_before_accessibility_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, "CLICK_DISPATCHED", "")

    monkeypatch.setattr(desktop_control, "run_process", run)
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL, '"Settings"', control_observation=_evidence()
        ),
    )

    class MissingOcrVerifier:
        def ready(self) -> bool:
            return True

        def find_visible_control(self, app_id: str, pid: int, label: str) -> None:
            assert (app_id, pid, label) == ("example.desktop", 42, "Settings")
            return None

    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: ("example.desktop", 42),
        verifier=MissingOcrVerifier(),
    )
    assert executor.execute(request).outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert _arguments(commands[0])[-3:] == ["click", "Settings", "accessible"]


def test_quoted_sensitive_control_still_stops_before_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        desktop_control,
        "run_process",
        lambda *_args, **_kwargs: pytest.fail("sensitive control must not click"),
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL, '"Delete"', control_observation=_evidence()
        ),
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: ("example.desktop", 42),
        verifier=Verifier(None),
    )
    assert executor.execute(request).error_code == "visible_control_sensitive"


@pytest.mark.parametrize(
    "label",
    (
        "Delete...",
        "Log out now",
        "Erase disk",
        "Ｄｅｌｅｔｅ…",
        "حذف…",
        "Send message",
        "Pay now",
        "Submit form",
        "Quit",
    ),
)
def test_consequential_control_never_reaches_input(
    monkeypatch: pytest.MonkeyPatch, label: str
) -> None:
    monkeypatch.setattr(
        desktop_control,
        "run_process",
        lambda *_args, **_kwargs: pytest.fail("consequential control must not click"),
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL, label, control_observation=_evidence()
        ),
    )

    class AnyLabelVerifier:
        def ready(self) -> bool:
            return True

        def find_visible_control(
            self, app_id: str, pid: int, found_label: str
        ) -> VisibleControlTarget:
            assert (app_id, pid, found_label) == ("example.desktop", 42, label)
            return VisibleControlTarget(40, 80, 90, 18, 800, 600)

    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: ("example.desktop", 42),
        verifier=AnyLabelVerifier(),
    )
    assert executor.execute(request).error_code == "visible_control_sensitive"


def test_unknown_consequence_control_is_blocked_before_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        desktop_control,
        "run_process",
        lambda *_args, **_kwargs: pytest.fail("unknown consequence must not click"),
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL,
            "Apply All Devices",
            control_observation=_evidence(),
        ),
    )

    class AnyLabelVerifier:
        def ready(self) -> bool:
            return True

        def find_visible_control(
            self, app_id: str, pid: int, label: str
        ) -> VisibleControlTarget:
            return VisibleControlTarget(40, 80, 90, 18, 800, 600)

    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: ("example.desktop", 42),
        verifier=AnyLabelVerifier(),
    )
    assert executor.execute(request).error_code == "visible_control_risk_unknown"


def test_quotes_without_a_control_name_do_not_reach_accessibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        desktop_control,
        "run_process",
        lambda *_args, **_kwargs: pytest.fail("empty control name must not click"),
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL, '""', control_observation=_evidence()
        ),
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: ("example.desktop", 42),
        verifier=Verifier(None),
    )
    assert executor.execute(request).error_code == "visible_control_uncertain"


@pytest.mark.usefixtures("no_accessible_action")
def test_focused_click_passes_captured_geometry_to_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, "CLICK_DISPATCHED", "")

    monkeypatch.setattr(desktop_control, "run_process", run)
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL, "Advanced", control_observation=_evidence()
        ),
    )
    target = VisibleControlTarget(
        40,
        80,
        90,
        18,
        796,
        570,
        (12, 48, 796, 570),
        (10, 20, 800, 600),
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: ("example.desktop", 42),
        verifier=Verifier(target),
    )
    assert executor.execute(request).outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert _arguments(commands[0])[-8:] == [
        "12",
        "48",
        "796",
        "570",
        "10",
        "20",
        "800",
        "600",
    ]


@pytest.mark.usefixtures("no_accessible_action")
def test_focus_change_stops_before_input(monkeypatch: pytest.MonkeyPatch) -> None:
    observations = iter((("example.desktop", 42), ("other.desktop", 7)))
    monkeypatch.setattr(
        desktop_control, "run_process", lambda *_a, **_k: pytest.fail("no input")
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL, "Advanced", control_observation=_evidence()
        ),
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: next(observations),
        verifier=Verifier(VisibleControlTarget(40, 80, 90, 18, 800, 600)),
    )
    assert executor.execute(request).error_code == "visible_control_focus_changed"


def test_inferred_control_does_not_move_to_a_different_focused_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        desktop_control,
        "run_process",
        lambda *_a, **_k: pytest.fail("must not click in a different app"),
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL,
            "Advanced",
            control_window_app="example.desktop",
            control_observation=_evidence(),
        ),
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: ("other.desktop", 7),
        verifier=Verifier(None),
    )
    assert executor.execute(request).error_code == "visible_control_focus_changed"


def test_model_selected_ocr_option_must_still_be_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        desktop_control,
        "run_process",
        lambda *_args, **_kwargs: pytest.fail("must not click a vanished OCR option"),
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL,
            "Settings",
            control_source="ocr",
            control_observation=_evidence(),
        ),
    )

    class MissingVerifier:
        def ready(self) -> bool:
            return True

        def find_visible_control(self, *_args: object) -> None:
            return None

    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: ("example.desktop", 42),
        verifier=MissingVerifier(),
    )
    assert executor.execute(request).error_code == "visible_control_uncertain"


@pytest.mark.usefixtures("no_accessible_action")
def test_model_selected_accessibility_icon_stays_on_accessibility_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, "CLICK_DISPATCHED", "")

    monkeypatch.setattr(desktop_control, "run_process", run)
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL,
            "Search",
            control_source="accessibility",
            control_anchor=(40, 20),
            control_observation=_evidence(),
        ),
    )

    class AccessibleVerifier:
        def ready(self) -> bool:
            return True

        def find_visible_control(self, *_args: object) -> None:
            pytest.fail("selected accessible icon must not use OCR coordinates")

    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: ("example.desktop", 42),
        verifier=AccessibleVerifier(),
    )
    assert executor.execute(request).outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert _arguments(commands[0])[-3:] == ["accessible", "40", "20"]


def test_moved_ocr_option_stops_before_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        desktop_control,
        "run_process",
        lambda *_args, **_kwargs: pytest.fail("moved target must not be clicked"),
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL,
            "Advanced",
            control_source="ocr",
            control_anchor=(250, 80),
            control_observation=_evidence(),
        ),
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: ("example.desktop", 42),
        verifier=Verifier(VisibleControlTarget(40, 80, 90, 18, 800, 600)),
    )
    assert (
        executor.execute(request).error_code
        == "visible_control_target_changed:ocr_anchor"
    )


def test_portal_pointer_change_reports_its_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        desktop_control,
        "run_process",
        lambda args, **_kwargs: subprocess.CompletedProcess(
            args, 2, "TARGET_CHANGED:pointer_or_window", ""
        ),
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL, "Advanced", control_observation=_evidence()
        ),
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: ("example.desktop", 42),
        verifier=Verifier(VisibleControlTarget(40, 80, 90, 18, 800, 600)),
    )
    assert (
        executor.execute(request).error_code
        == "visible_control_target_changed:pointer_or_window"
    )


def test_image_size_diagnostic_keeps_only_dimensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        desktop_control,
        "run_process",
        lambda args, **_kwargs: subprocess.CompletedProcess(
            args, 2, "TARGET_CHANGED:image_scale_949x656_png_899x569", ""
        ),
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL, "Advanced", control_observation=_evidence()
        ),
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: ("example.desktop", 42),
        verifier=Verifier(VisibleControlTarget(40, 80, 90, 18, 800, 600)),
    )
    assert (
        executor.execute(request).error_code
        == "visible_control_target_changed:image_scale_949x656_png_899x569"
    )


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ("content", "content"),
        ("window_token", "window_token"),
        ("stale_capture", "stale_capture"),
        ("stale_or_window", "stale_or_window"),
        ("frame_size", "frame_size"),
        ("pointer_or_window", "pointer_or_window"),
        (
            "image_scale_949x656_png_899x569",
            "image_scale_949x656_png_899x569",
        ),
        ("arbitrary stdout text", "unknown"),
        ("TARGET_CHANGED:content\nextra", "unknown"),
    ],
)
def test_target_change_diagnostic_uses_only_known_codes(
    detail: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        desktop_control,
        "run_process",
        lambda args, **_kwargs: subprocess.CompletedProcess(
            args, 2, f"TARGET_CHANGED:{detail}", ""
        ),
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL, "Advanced", control_observation=_evidence()
        ),
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: ("example.desktop", 42),
        verifier=Verifier(VisibleControlTarget(40, 80, 90, 18, 800, 600)),
    )

    assert (
        executor.execute(request).error_code
        == f"visible_control_target_changed:{expected}"
    )


def test_legacy_capture_reports_extension_update_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        desktop_control,
        "run_process",
        lambda args, **_kwargs: subprocess.CompletedProcess(
            args, 2, "CAPTURE_GEOMETRY_REQUIRED", ""
        ),
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL, "Advanced", control_observation=_evidence()
        ),
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: ("example.desktop", 42),
        verifier=Verifier(VisibleControlTarget(40, 80, 90, 18, 800, 600)),
    )
    assert (
        executor.execute(request).error_code
        == "visible_control_capture_geometry_required"
    )


def test_unknown_state_change_stops_before_accessibility_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        desktop_control,
        "run_process",
        lambda *_args, **_kwargs: pytest.fail("unknown state change must not click"),
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL,
            "Advanced",
            control_state=True,
            control_observation=_evidence(),
        ),
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: ("example.desktop", 42),
        verifier=Verifier(None),
    )
    assert executor.execute(request).error_code == "visible_control_risk_unknown"


def test_missing_initial_window_identity_requires_request_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        sent.append(args)
        return subprocess.CompletedProcess(args, 0, "CLICK_DISPATCHED", "")

    monkeypatch.setattr(desktop_control, "run_process", run)
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: ("example.desktop", 42),
        verifier=Verifier(VisibleControlTarget(40, 80, 90, 18, 800, 600)),
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL,
            "Advanced",
            control_window_app="example.desktop",
        ),
    )
    result = executor.execute(request)
    assert result.error_code == "visible_control_target_changed:window_token"
    assert sent == []


@pytest.mark.usefixtures("no_accessible_action")
def test_fresh_target_does_not_renew_original_request_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _evidence()
    clock = [evidence.observed_at + 1]
    monkeypatch.setattr(desktop_control, "monotonic", lambda: clock[0])

    class SlowVerifier(Verifier):
        def find_visible_control(
            self, app_id: str, pid: int, label: str
        ) -> VisibleControlTarget | None:
            clock[0] = evidence.deadline
            return super().find_visible_control(app_id, pid, label)

    monkeypatch.setattr(
        desktop_control,
        "run_process",
        lambda *_a, **_k: pytest.fail("expired request must not dispatch"),
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: evidence.identity,
        token_reader=lambda: evidence.window_token,
        verifier=SlowVerifier(VisibleControlTarget(40, 80, 90, 18, 800, 600)),
    )
    result = executor.execute(
        ActionRequest(
            ActionKey(0, 1),
            CommandIntent(
                CommandKind.VISIBLE_CONTROL, "Advanced", control_observation=evidence
            ),
        )
    )
    assert result.error_code == "visible_control_target_changed:stale_or_window"


def test_semantic_control_dispatches_with_ocr_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert kwargs["helper"] is True
        return subprocess.CompletedProcess(args, 0, "ACTION_DISPATCHED", "")

    monkeypatch.setattr(desktop_control, "run_process", run)

    class OffVerifier:
        def ready(self) -> bool:
            pytest.fail("semantic control must not depend on OCR readiness")

        def find_visible_control(self, *_args: object) -> None:
            pytest.fail("semantic control must not capture a screenshot")

    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL, "Settings", control_observation=_evidence()
        ),
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        token_reader=lambda: "window-7",
        identity_reader=lambda: ("example.desktop", 42),
        verifier=OffVerifier(),
    )
    assert executor.execute(request).outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert len(calls) == 1
    assert calls[0][2] == "semantic"


def test_independent_resolver_accepts_structural_action_without_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    from kyrin.desktop.accessibility_target import AccessibilityTarget

    structure = AccessibilityTarget(
        ((0, "FRAME", "Main"), (1, "BUTTON", "Test button"))
    )
    payload = [
        {
            "label": "Test button",
            "role": "BUTTON",
            "checked": None,
            "x": None,
            "y": None,
            "accessibility": structure.to_json(),
        }
    ]
    monkeypatch.setattr(
        desktop_control,
        "run_process",
        lambda args, **_kw: subprocess.CompletedProcess(
            args,
            0,
            json.dumps(
                {"version": 1, "status": "ok", "controls": payload, "rejected": []}
            ),
            "",
        ),
    )
    executor = desktop_control.DesktopControlExecutor(
        Delegate(),
        identity_reader=lambda: ("example.desktop", 42),
        token_reader=lambda: "window-7",
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL, "Test button", control_observation=_evidence()
        ),
    )
    evidence = executor._resolve_control(
        request, ("example.desktop", 42), "Test button"
    )
    assert evidence is not None
    assert evidence.accessibility == structure and evidence.anchor is None
