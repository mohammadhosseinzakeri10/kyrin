"""Fixed, authorized Ptyxis desktop actions; never run transcript as a command."""

import json
import subprocess
from pathlib import Path

from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.commands.models import CommandKind
from kyrin.desktop.window_presence import AppWindowPresence

_FLAGS = {
    CommandKind.NEW_APP_WINDOW: "--new-window",
    CommandKind.NEW_APP_TAB: "--tab",
    CommandKind.APP_PREFERENCES: "--preferences",
}


class PtyxisActionExecutor:
    """Offer only actions advertised by the bound Ptyxis desktop entry."""

    def __init__(
        self,
        fallback: ActionExecutor,
        app_id: str,
        entry: Path,
        window_presence: AppWindowPresence | None = None,
    ) -> None:
        if entry.name != "org.gnome.Ptyxis.desktop" or not entry.is_file():
            raise ValueError("Ptyxis actions require its installed desktop entry")
        self._fallback = fallback
        self._app_id = app_id
        self._entry = entry
        self._window_presence = window_presence
        self._picker_open = False

    def _dismiss_picker(self) -> None:
        if not self._picker_open:
            return
        self._picker_open = False
        try:
            subprocess.run(
                [
                    "busctl", "--user", "call", "org.gnome.Shell",
                    "/org/kyrin/ActiveApp", "org.kyrin.ActiveApp",
                    "HideAppWindows", "s", self._entry.name,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=0.5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

    def execute(self, request: ActionRequest) -> ActionResult:
        intent = request.intent
        if intent.kind not in (
            *_FLAGS,
            CommandKind.SHOW_ALL_WINDOWS,
            CommandKind.SHOW_APP_WINDOWS,
            CommandKind.SELECT_APP_WINDOW,
            CommandKind.CLOSE_SHOWN_WINDOW,
            CommandKind.HIDE_APP_WINDOWS,
        ):
            self._dismiss_picker()
            return self._fallback.execute(request)
        if intent.target != self._app_id:
            return ActionResult(
                request.key, ActionOutcome.FAILED, error_code="app_not_configured"
            )
        if intent.kind is CommandKind.CLOSE_SHOWN_WINDOW and not self._picker_open:
            return ActionResult(
                request.key, ActionOutcome.FAILED, error_code="window_state_changed"
            )
        if intent.kind is CommandKind.NEW_APP_TAB and (
            self._window_presence is None
            or self._window_presence.count(self._app_id) != 1
        ):
            return ActionResult(
                request.key, ActionOutcome.UNKNOWN, error_code="window_state_changed"
            )
        if intent.kind is CommandKind.SHOW_APP_WINDOWS:
            if self._window_presence is None or (
                count := self._window_presence.count(self._app_id)
            ) is None or count < 2:
                return ActionResult(
                    request.key,
                    ActionOutcome.UNKNOWN,
                    error_code="window_state_changed",
                )
        if intent.kind in (
            CommandKind.SHOW_ALL_WINDOWS,
            CommandKind.SHOW_APP_WINDOWS,
            CommandKind.SELECT_APP_WINDOW,
            CommandKind.CLOSE_SHOWN_WINDOW,
            CommandKind.HIDE_APP_WINDOWS,
        ):
            method = {
                CommandKind.SHOW_ALL_WINDOWS: "ShowAllWindows",
                CommandKind.SHOW_APP_WINDOWS: "ShowAppWindows",
                CommandKind.SELECT_APP_WINDOW: "ActivateShownAppWindow",
                CommandKind.CLOSE_SHOWN_WINDOW: "CloseShownAppWindow",
                CommandKind.HIDE_APP_WINDOWS: "HideAppWindows",
            }[intent.kind]
            command = [
                "busctl", "--user", "--json=short", "call", "org.gnome.Shell",
                "/org/kyrin/ActiveApp", "org.kyrin.ActiveApp", method,
            ]
            if intent.kind in (
                CommandKind.SHOW_APP_WINDOWS,
                CommandKind.HIDE_APP_WINDOWS,
            ):
                command.extend(("s", self._entry.name))
            elif intent.kind in (
                CommandKind.SELECT_APP_WINDOW,
                CommandKind.CLOSE_SHOWN_WINDOW,
            ):
                assert intent.window_index is not None
                command.extend(("su", self._entry.name, str(intent.window_index)))
        else:
            command = ["ptyxis", _FLAGS[intent.kind]]
        try:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5.0,
                start_new_session=True,
            )
        except subprocess.TimeoutExpired:
            return ActionResult(
                request.key, ActionOutcome.UNKNOWN, error_code="launcher_timeout"
            )
        except OSError:
            return ActionResult(
                request.key, ActionOutcome.FAILED, error_code="launcher_unavailable"
            )
        if result.returncode != 0:
            return ActionResult(
                request.key, ActionOutcome.FAILED, error_code="launcher_failed"
            )
        if intent.kind in (
            CommandKind.SHOW_APP_WINDOWS,
            CommandKind.SELECT_APP_WINDOW,
            CommandKind.CLOSE_SHOWN_WINDOW,
            CommandKind.HIDE_APP_WINDOWS,
        ):
            try:
                response = json.loads(result.stdout)
                status = response["data"][0]
            except (ValueError, KeyError, IndexError, TypeError):
                status = "unknown"
            if status != "requested":
                return ActionResult(
                    request.key,
                    ActionOutcome.UNKNOWN,
                    error_code="window_state_changed"
                    if status in {"stale", "no_window", "not_shown"}
                    else "window_unverified",
                )
            self._picker_open = intent.kind is CommandKind.SHOW_APP_WINDOWS
        return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)
