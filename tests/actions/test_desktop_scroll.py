"""Desktop scroll actions must keep their app and focus boundary."""

import subprocess
from pathlib import Path

import pytest

from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.platforms import desktop_scroll
from kyrin.commands.models import CommandIntent, CommandKind


class Delegate:
    def execute(self, request: ActionRequest) -> ActionResult:
        return ActionResult(request.key, ActionOutcome.DISPATCHED_UNVERIFIED)


def test_scroll_dispatch_uses_focused_allowed_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, "SCROLL_DISPATCHED", "")

    monkeypatch.setattr(desktop_scroll, "run_process", run)
    executor = desktop_scroll.DesktopScrollExecutor(
        Delegate(), desktop_ids={"telegram": "org.telegram.desktop"},
        identity_reader=lambda: ("org.telegram.desktop", 42),
        helper_path=Path("/tmp/scroll-helper.py"),
    )
    request = ActionRequest(
        ActionKey(0, 1), CommandIntent(CommandKind.SCROLL_DOWN, "telegram")
    )
    assert executor.execute(request) == ActionResult(
        request.key, ActionOutcome.DISPATCHED_UNVERIFIED
    )
    assert commands[0][-5:] == ["42", "down", "3", "left", "desktop-scroll"]


def test_scroll_rejects_changed_focus_without_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        desktop_scroll, "run_process",
        lambda *_args, **_kwargs: pytest.fail("scroll must not dispatch"),
    )
    executor = desktop_scroll.DesktopScrollExecutor(
        Delegate(), desktop_ids={"telegram": "org.telegram.desktop"},
        identity_reader=lambda: ("other.desktop", 42),
    )
    request = ActionRequest(
        ActionKey(0, 1), CommandIntent(CommandKind.SCROLL_UP, "telegram")
    )
    assert executor.execute(request) == ActionResult(
        request.key, ActionOutcome.FAILED, error_code="scroll_focus_changed"
    )


def test_other_app_scroll_still_targets_window_center(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, "SCROLL_DISPATCHED", "")

    monkeypatch.setattr(desktop_scroll, "run_process", run)
    executor = desktop_scroll.DesktopScrollExecutor(
        Delegate(), desktop_ids={"firefox": "firefox.desktop"},
        identity_reader=lambda: ("firefox.desktop", 21),
    )
    request = ActionRequest(
        ActionKey(0, 1), CommandIntent(CommandKind.SCROLL_DOWN, "firefox")
    )
    assert executor.execute(request).outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert commands[0][-2:] == ["center", "desktop-scroll"]


def test_scroll_amount_reaches_bounded_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, "SCROLL_DISPATCHED", "")

    monkeypatch.setattr(desktop_scroll, "run_process", run)
    executor = desktop_scroll.DesktopScrollExecutor(
        Delegate(), desktop_ids={"telegram": "org.telegram.desktop"},
        identity_reader=lambda: ("org.telegram.desktop", 42),
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(CommandKind.SCROLL_DOWN, "telegram", scroll_steps=2),
    )
    assert executor.execute(request).outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert commands[0][-3:] == ["2", "left", "desktop-scroll"]


def test_telegram_open_chat_scroll_targets_right_pane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, "SCROLL_DISPATCHED", "")

    monkeypatch.setattr(desktop_scroll, "run_process", run)
    executor = desktop_scroll.DesktopScrollExecutor(
        Delegate(), desktop_ids={"telegram": "org.telegram.desktop"},
        identity_reader=lambda: ("org.telegram.desktop", 42),
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.SCROLL_DOWN, "telegram", scroll_area="chat"
        ),
    )
    assert executor.execute(request).outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert commands[0][-2:] == ["right", "desktop-scroll"]


def test_chat_area_cannot_be_sent_to_another_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        desktop_scroll, "run_process",
        lambda *_args, **_kwargs: pytest.fail("scroll must not dispatch"),
    )
    executor = desktop_scroll.DesktopScrollExecutor(
        Delegate(), desktop_ids={"firefox": "firefox.desktop"},
        identity_reader=lambda: ("firefox.desktop", 21),
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(CommandKind.SCROLL_DOWN, "firefox", scroll_area="chat"),
    )
    assert executor.execute(request).error_code == "unsupported_scroll_area"


def test_global_scroll_dispatches_for_unselected_focused_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, "SCROLL_DISPATCHED", "")

    monkeypatch.setattr(desktop_scroll, "run_process", run)
    executor = desktop_scroll.DesktopScrollExecutor(
        Delegate(),
        desktop_ids={},
        identity_reader=lambda: ("unselected.desktop", 42),
        allow_any_focused_app=True,
    )
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(CommandKind.SCROLL_DOWN, "unselected.desktop"),
    )
    assert executor.execute(request).outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert commands[0][-6:] == [
        "unselected.desktop", "42", "down", "3", "center", "desktop-scroll"
    ]
    changed = ActionRequest(
        ActionKey(0, 2),
        CommandIntent(CommandKind.SCROLL_DOWN, "other.desktop"),
    )
    assert executor.execute(changed) == ActionResult(
        changed.key, ActionOutcome.FAILED, error_code="scroll_focus_changed"
    )
    assert len(commands) == 1
