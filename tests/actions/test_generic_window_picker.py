"""Non-terminal previews use the existing allowlist-filtered Shell snapshot."""

import json
import subprocess
from pathlib import Path

import pytest

from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.platforms.open_windows import OpenWindowPickerExecutor
from kyrin.actions.platforms.ptyxis import PtyxisActionExecutor
from kyrin.commands.models import CommandIntent, CommandKind
from tests.desktop.test_backend_protocol import bus_reply


class NoFallback:
    def execute(self, request: ActionRequest) -> ActionResult:
        raise AssertionError(f"unexpected fallback: {request.intent}")


@pytest.mark.parametrize("selection_status", ["requested", "stale"])
def test_app_preview_bypasses_terminal_adapter_and_selects_fresh_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, selection_status: str
) -> None:
    entry = tmp_path / "org.gnome.Ptyxis.desktop"
    entry.write_text("[Desktop Entry]\n")
    commands: list[list[str]] = []
    statuses = iter(("requested", selection_status))

    def run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes] | subprocess.CompletedProcess[str]:
        if command[-1] == "GetCapabilities":
            return bus_reply("ShowOpenWindows", "ActivateShownOpenWindow")
        commands.append(command)
        return subprocess.CompletedProcess(
            command, 0, json.dumps({"data": [next(statuses)]}).encode(), b""
        )

    monkeypatch.setattr(subprocess, "run", run)
    executor = OpenWindowPickerExecutor(
        PtyxisActionExecutor(NoFallback(), "terminal", entry),
        {"browser": "chrome.desktop", "terminal": entry.name},
    )
    shown = executor.execute(ActionRequest(
        ActionKey(0, 0), CommandIntent(CommandKind.SHOW_APP_WINDOWS, "browser")
    ))
    assert shown.outcome is ActionOutcome.LAUNCH_ACCEPTED
    assert commands[0][-4:] == ["ShowOpenWindows", "as", "1", "chrome.desktop"]
    selected = executor.execute(ActionRequest(
        ActionKey(0, 1),
        CommandIntent(CommandKind.SELECT_APP_WINDOW, "desktop", window_index=2),
    ))
    assert selected.outcome is (
        ActionOutcome.LAUNCH_ACCEPTED if selection_status == "requested"
        else ActionOutcome.UNKNOWN
    )
    if selection_status == "stale":
        assert selected.error_code == "window_state_changed"
    assert commands[1][-3:] == ["ActivateShownOpenWindow", "u", "2"]


def test_unknown_app_preview_never_falls_back_or_calls_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        raise AssertionError("No Shell call for an unregistered app")

    monkeypatch.setattr(subprocess, "run", forbidden)
    executor = OpenWindowPickerExecutor(NoFallback(), {"browser": "chrome.desktop"})
    result = executor.execute(ActionRequest(
        ActionKey(0, 0), CommandIntent(CommandKind.SHOW_APP_WINDOWS, "unbound")
    ))
    assert result.outcome is ActionOutcome.FAILED
    assert result.error_code == "app_not_configured"


def test_terminal_keeps_reviewed_legacy_picker_protocol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.actions.test_ptyxis_actions import Presence

    entry = tmp_path / "org.gnome.Ptyxis.desktop"
    entry.write_text("[Desktop Entry]\n")
    commands: list[list[str]] = []

    def run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes] | subprocess.CompletedProcess[str]:
        if command[-1] == "GetCapabilities":
            return bus_reply("ShowAppWindows", "ActivateShownAppWindow")
        commands.append(command)
        return subprocess.CompletedProcess(
            command, 0, json.dumps({"data": ["requested"]}).encode(), b""
        )

    monkeypatch.setattr(subprocess, "run", run)
    executor = OpenWindowPickerExecutor(
        PtyxisActionExecutor(NoFallback(), "terminal", entry, Presence(3)),
        {"terminal": entry.name}, legacy_picker_app="terminal",
    )
    for index, intent in enumerate((
        CommandIntent(CommandKind.SHOW_APP_WINDOWS, "terminal"),
        CommandIntent(CommandKind.SELECT_APP_WINDOW, "terminal", window_index=2),
    )):
        assert executor.execute(ActionRequest(
            ActionKey(0, index), intent
        )).outcome is ActionOutcome.LAUNCH_ACCEPTED
    assert commands[0][-3:] == ["ShowAppWindows", "s", entry.name]
    assert commands[1][-4:] == ["ActivateShownAppWindow", "su", entry.name, "2"]


def test_scoped_preview_cancel_only_hides_picker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes] | subprocess.CompletedProcess[str]:
        if command[-1] == "GetCapabilities":
            return bus_reply("ShowOpenWindows", "HideOpenWindows")
        commands.append(command)
        return subprocess.CompletedProcess(
            command, 0, json.dumps({"data": ["requested"]}).encode(), b""
        )

    monkeypatch.setattr(subprocess, "run", run)
    executor = OpenWindowPickerExecutor(NoFallback(), {"browser": "chrome.desktop"})
    for index, intent in enumerate((
        CommandIntent(CommandKind.SHOW_APP_WINDOWS, "browser"),
        CommandIntent(CommandKind.HIDE_APP_WINDOWS, "desktop"),
    )):
        assert executor.execute(ActionRequest(
            ActionKey(0, index), intent
        )).outcome is ActionOutcome.LAUNCH_ACCEPTED
    assert commands[1][-1] == "HideOpenWindows"
    assert not any("Close" in part or "Activate" in part
                   for command in commands for part in command)
