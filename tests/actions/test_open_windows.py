"""Global picker sends only registered, permitted desktop IDs to GNOME."""

import json
import subprocess

from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest
from kyrin.actions.platforms import open_windows
from kyrin.commands.models import CommandIntent, CommandKind
from tests.desktop.test_backend_protocol import bus_reply


class Fallback:
    def execute(self, request: ActionRequest):
        raise AssertionError(f"unexpected fallback: {request}")


def test_picker_uses_allowed_desktop_ids_and_rejects_stale_selection(
    monkeypatch,
) -> None:
    commands: list[list[str]] = []
    replies = iter(("requested", "stale", "requested", "requested"))

    def run(command, **kwargs):
        if command[-1] == "GetCapabilities":
            return bus_reply(
                "ShowOpenWindows", "ActivateShownOpenWindow", "ActivateShownOpenApp",
                "HideOpenWindows", "ShowAppWindows", "ActivateShownAppWindow",
                "HideAppWindows", "ShowAllWindows",
            )
        commands.append(command)
        return subprocess.CompletedProcess(
            command, 0, json.dumps({"data": [next(replies)]}).encode(), b""
        )

    monkeypatch.setattr(open_windows.subprocess, "run", run)
    executor = open_windows.OpenWindowPickerExecutor(
        Fallback(), {"telegram": "telegram.desktop", "browser": "firefox.desktop"}
    )
    intents = (
        CommandIntent(CommandKind.SHOW_ALL_WINDOWS, "desktop"),
        CommandIntent(CommandKind.SELECT_APP_WINDOW, "desktop", window_index=2),
        CommandIntent(CommandKind.SELECT_OPEN_APP_WINDOW, "telegram"),
        CommandIntent(CommandKind.HIDE_APP_WINDOWS, "desktop"),
    )
    outcomes = tuple(
        executor.execute(ActionRequest(ActionKey(0, index), intent))
        for index, intent in enumerate(intents)
    )
    assert [item.outcome for item in outcomes] == [
        ActionOutcome.LAUNCH_ACCEPTED,
        ActionOutcome.UNKNOWN,
        ActionOutcome.LAUNCH_ACCEPTED,
        ActionOutcome.LAUNCH_ACCEPTED,
    ]
    assert commands[0][-4:] == ["as", "2", "firefox.desktop", "telegram.desktop"]
    assert commands[1][-2:] == ["u", "2"]
    assert commands[2][-2:] == ["s", "telegram.desktop"]
    assert commands[3][-1] == "HideOpenWindows"


def test_unbound_app_cannot_be_selected(monkeypatch) -> None:
    monkeypatch.setattr(
        open_windows.subprocess, "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("bus call")),
    )
    executor = open_windows.OpenWindowPickerExecutor(Fallback(), {})
    result = executor.execute(
        ActionRequest(
            ActionKey(0, 0),
            CommandIntent(CommandKind.SELECT_OPEN_APP_WINDOW, "unbound"),
        )
    )
    assert result.outcome is ActionOutcome.FAILED


def test_numbered_close_cannot_bypass_shared_confirmation(
    monkeypatch,
) -> None:
    calls: list[list[str]] = []
    replies = iter(("requested", "requested"))

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command, 0, json.dumps({"data": [next(replies)]}).encode(), b""
        )

    monkeypatch.setattr(open_windows.subprocess, "run", run)
    executor = open_windows.OpenWindowPickerExecutor(
        Fallback(),
        {"telegram": "telegram.desktop", "browser": "firefox.desktop"},
        {"telegram": "telegram.desktop"},
    )
    close = CommandIntent(CommandKind.CLOSE_SHOWN_WINDOW, "desktop", window_index=2)
    before = executor.execute(ActionRequest(ActionKey(0, 0), close))
    assert before.outcome is ActionOutcome.FAILED
    executor.execute(ActionRequest(
        ActionKey(0, 1), CommandIntent(CommandKind.SHOW_ALL_WINDOWS, "desktop")
    ))
    result = executor.execute(ActionRequest(ActionKey(0, 2), close))
    assert result.outcome is ActionOutcome.FAILED
    assert result.error_code == "window_close_confirmation_required"
    assert len(calls) == 1
    assert executor.execute(
        ActionRequest(ActionKey(0, 3), close)
    ).outcome is ActionOutcome.FAILED
