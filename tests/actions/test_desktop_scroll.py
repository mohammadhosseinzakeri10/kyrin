"""Desktop scroll actions must keep their app, window and focus boundary."""

import subprocess
from pathlib import Path

import pytest

from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.platforms import desktop_scroll
from kyrin.commands.models import CommandIntent, CommandKind
from kyrin.desktop.window_observation import WindowObservation


class Delegate:
    def execute(self, request: ActionRequest) -> ActionResult:
        return ActionResult(request.key, ActionOutcome.DISPATCHED_UNVERIFIED)


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(desktop_scroll, "monotonic", lambda: 101.0)


def _window(app_id: str, pid: int, token: str = "window-1") -> WindowObservation:
    return WindowObservation(app_id, pid, token, "initial", 100.0, 110.0)


def _executor(
    identity: tuple[str, int],
    *,
    desktop_ids: dict[str, str] | None = None,
    token: str | None = "window-1",
    allow_any_focused_app: bool = False,
) -> desktop_scroll.DesktopScrollExecutor:
    return desktop_scroll.DesktopScrollExecutor(
        Delegate(),
        desktop_ids=desktop_ids or {},
        identity_reader=lambda: identity,
        token_reader=lambda: token,
        allow_any_focused_app=allow_any_focused_app,
        helper_path=Path("/tmp/scroll-helper.py"),
    )


def _recording(
    monkeypatch: pytest.MonkeyPatch, stdout: str = "SCROLL_DISPATCHED", code: int = 0
) -> list[list[str]]:
    commands: list[list[str]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        timeout = kwargs["timeout"]
        assert isinstance(timeout, float) and 0 < timeout <= 9.0
        return subprocess.CompletedProcess(args, code, stdout, "")

    monkeypatch.setattr(desktop_scroll, "run_process", run)
    return commands


def _no_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        desktop_scroll, "run_process",
        lambda *_args, **_kwargs: pytest.fail("scroll must not dispatch"),
    )


def test_scroll_dispatch_uses_focused_allowed_app_and_its_window_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands = _recording(monkeypatch)
    executor = _executor(
        ("org.telegram.desktop", 42),
        desktop_ids={"telegram": "org.telegram.desktop"},
    )
    evidence = _window("org.telegram.desktop", 42)
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.SCROLL_DOWN, "telegram", scroll_observation=evidence
        ),
    )
    assert executor.execute(request) == ActionResult(
        request.key, ActionOutcome.DISPATCHED_UNVERIFIED
    )
    assert commands[0][-6:] == [
        "42", "down", "3", "left", evidence.to_json(), "desktop-scroll"
    ]


def test_scroll_rejects_changed_focus_without_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_dispatch(monkeypatch)
    executor = _executor(
        ("other.desktop", 42), desktop_ids={"telegram": "org.telegram.desktop"}
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.SCROLL_UP,
            "telegram",
            scroll_observation=_window("org.telegram.desktop", 42),
        ),
    )
    assert executor.execute(request) == ActionResult(
        request.key, ActionOutcome.FAILED, error_code="scroll_focus_changed"
    )


@pytest.mark.parametrize(
    ("identity", "token", "evidence"),
    [
        # Same application and process, but a different window is now focused.
        (("viewer.desktop", 42), "window-2", _window("viewer.desktop", 42)),
        # The process changed although the application ID did not.
        (("viewer.desktop", 43), "window-1", _window("viewer.desktop", 42)),
        # The focused-window token is unavailable.
        (("viewer.desktop", 42), None, _window("viewer.desktop", 42)),
        # The evidence belongs to another application.
        (("viewer.desktop", 42), "window-1", _window("other.desktop", 42)),
        # No window evidence travelled with the request.
        (("viewer.desktop", 42), "window-1", None),
    ],
)
def test_replaced_changed_or_missing_window_sends_no_scroll(
    monkeypatch: pytest.MonkeyPatch,
    identity: tuple[str, int],
    token: str | None,
    evidence: WindowObservation | None,
) -> None:
    _no_dispatch(monkeypatch)
    executor = _executor(identity, token=token, allow_any_focused_app=True)
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.SCROLL_DOWN, "viewer.desktop", scroll_observation=evidence
        ),
    )
    assert executor.execute(request) == ActionResult(
        request.key, ActionOutcome.FAILED, error_code="scroll_focus_changed"
    )


def test_expired_window_evidence_sends_no_scroll(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_dispatch(monkeypatch)
    monkeypatch.setattr(desktop_scroll, "monotonic", lambda: 110.0)
    executor = _executor(("viewer.desktop", 42), allow_any_focused_app=True)
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.SCROLL_DOWN,
            "viewer.desktop",
            scroll_observation=_window("viewer.desktop", 42),
        ),
    )
    assert executor.execute(request) == ActionResult(
        request.key, ActionOutcome.FAILED, error_code="scroll_focus_changed"
    )


def test_helper_rejection_before_input_is_a_truthful_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The helper reports FOCUS_CHANGED only before sending any input, e.g.
    # after another same-app window gained focus while the request was queued.
    _recording(monkeypatch, stdout="FOCUS_CHANGED\n", code=2)
    executor = _executor(("viewer.desktop", 42), allow_any_focused_app=True)
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.SCROLL_DOWN,
            "viewer.desktop",
            scroll_observation=_window("viewer.desktop", 42),
        ),
    )
    assert executor.execute(request) == ActionResult(
        request.key, ActionOutcome.FAILED, error_code="scroll_focus_changed"
    )


def test_uncertain_helper_result_stays_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _recording(monkeypatch, stdout="SCROLL_UNCERTAIN\n", code=2)
    executor = _executor(("viewer.desktop", 42), allow_any_focused_app=True)
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.SCROLL_DOWN,
            "viewer.desktop",
            scroll_observation=_window("viewer.desktop", 42),
        ),
    )
    assert executor.execute(request) == ActionResult(
        request.key, ActionOutcome.UNKNOWN, error_code="scroll_unavailable"
    )


def test_other_app_scroll_still_targets_window_center(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands = _recording(monkeypatch)
    executor = _executor(
        ("firefox.desktop", 21), desktop_ids={"firefox": "firefox.desktop"}
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.SCROLL_DOWN,
            "firefox",
            scroll_observation=_window("firefox.desktop", 21),
        ),
    )
    assert executor.execute(request).outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert commands[0][-3] == "center"
    assert commands[0][-1] == "desktop-scroll"


def test_scroll_amount_reaches_bounded_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands = _recording(monkeypatch)
    executor = _executor(
        ("org.telegram.desktop", 42),
        desktop_ids={"telegram": "org.telegram.desktop"},
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.SCROLL_DOWN,
            "telegram",
            scroll_steps=2,
            scroll_observation=_window("org.telegram.desktop", 42),
        ),
    )
    assert executor.execute(request).outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert commands[0][-4:-2] == ["2", "left"]


def test_telegram_open_chat_scroll_targets_right_pane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands = _recording(monkeypatch)
    executor = _executor(
        ("org.telegram.desktop", 42),
        desktop_ids={"telegram": "org.telegram.desktop"},
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.SCROLL_DOWN,
            "telegram",
            scroll_area="chat",
            scroll_observation=_window("org.telegram.desktop", 42),
        ),
    )
    assert executor.execute(request).outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert commands[0][-3] == "right"


def test_chat_area_cannot_be_sent_to_another_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_dispatch(monkeypatch)
    executor = _executor(
        ("firefox.desktop", 21), desktop_ids={"firefox": "firefox.desktop"}
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.SCROLL_DOWN,
            "firefox",
            scroll_area="chat",
            scroll_observation=_window("firefox.desktop", 21),
        ),
    )
    assert executor.execute(request).error_code == "unsupported_scroll_area"


def test_global_scroll_dispatches_for_unselected_focused_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands = _recording(monkeypatch)
    executor = _executor(("unselected.desktop", 42), allow_any_focused_app=True)
    evidence = _window("unselected.desktop", 42)
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.SCROLL_DOWN, "unselected.desktop", scroll_observation=evidence
        ),
    )
    assert executor.execute(request).outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert commands[0][-7:] == [
        "unselected.desktop", "42", "down", "3", "center",
        evidence.to_json(), "desktop-scroll",
    ]
    changed = ActionRequest(
        ActionKey(0, 2),
        CommandIntent(
            CommandKind.SCROLL_DOWN,
            "other.desktop",
            scroll_observation=_window("other.desktop", 42),
        ),
    )
    assert executor.execute(changed) == ActionResult(
        changed.key, ActionOutcome.FAILED, error_code="scroll_focus_changed"
    )
    assert len(commands) == 1
