"""GNOME picker for windows of explicitly permitted installed applications."""

import json
import subprocess
from collections.abc import Mapping

from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.backend_protocol import BackendStatus, probe_gnome
from kyrin.commands.models import CommandKind


class OpenWindowPickerExecutor:
    """The Shell owns the displayed snapshot and validates it again on selection."""

    def __init__(
        self,
        fallback: ActionExecutor,
        desktop_ids: Mapping[str, str],
        close_desktop_ids: Mapping[str, str] | None = None,
    ) -> None:
        self._fallback = fallback
        self._desktop_ids = dict(desktop_ids)
        self._close_desktop_ids = dict(close_desktop_ids or {})
        self._picker_open = False
        self.backend_status = BackendStatus(False, "not_probed")

    def execute(self, request: ActionRequest) -> ActionResult:
        intent = request.intent
        if intent.kind is CommandKind.CLOSE_SHOWN_WINDOW:
            # Only the outer WindowControlExecutor may confirm and close.
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="window_close_confirmation_required",
            )
        kinds = {
            CommandKind.SHOW_ALL_WINDOWS,
            CommandKind.SELECT_APP_WINDOW,
            CommandKind.SELECT_OPEN_APP_WINDOW,
            CommandKind.HIDE_APP_WINDOWS,
        }
        global_picker = intent.kind in kinds and (
            intent.target == "desktop"
            or intent.kind is CommandKind.SELECT_OPEN_APP_WINDOW
        )
        if not global_picker:
            if self._picker_open:
                self._call("HideOpenWindows")
                self._picker_open = False
            return self._fallback.execute(request)
        args: tuple[str, ...]
        if intent.kind is CommandKind.SELECT_OPEN_APP_WINDOW:
            desktop_id = self._desktop_ids.get(intent.target)
            if desktop_id is None:
                return ActionResult(
                    request.key, ActionOutcome.FAILED, error_code="app_not_configured"
                )
            method, args = "ActivateShownOpenApp", ("s", desktop_id)
        elif intent.kind is CommandKind.SHOW_ALL_WINDOWS:
            ids = tuple(sorted(self._desktop_ids.values()))
            method, args = "ShowOpenWindows", ("as", str(len(ids)), *ids)
        elif intent.kind is CommandKind.SELECT_APP_WINDOW:
            assert intent.window_index is not None
            method, args = "ActivateShownOpenWindow", ("u", str(intent.window_index))
        else:
            method, args = "HideOpenWindows", ()
        status = self._call(method, *args)
        if status != "requested":
            return ActionResult(
                request.key,
                ActionOutcome.UNKNOWN,
                error_code="window_state_changed"
                if status in {"stale", "not_shown", "no_window"}
                else "multiple_windows"
                if status == "ambiguous"
                else "backend:" + self.backend_status.reason
                if not self.backend_status.ready
                else "window_unverified",
            )
        self._picker_open = intent.kind is CommandKind.SHOW_ALL_WINDOWS
        return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

    def _call(self, method: str, *args: str) -> str | None:
        self.backend_status = probe_gnome("ActiveApp", {method}, run=subprocess.run)
        if not self.backend_status.ready:
            return None
        try:
            result = subprocess.run(
                [
                    "busctl",
                    "--user",
                    "--json=short",
                    "call",
                    "org.gnome.Shell",
                    "/org/kyrin/ActiveApp",
                    "org.kyrin.ActiveApp",
                    method,
                    *args,
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=5.0,
            )
        except OSError, subprocess.TimeoutExpired:
            return None
        if result.returncode != 0:
            return None
        try:
            response = json.loads(result.stdout)
            status = response["data"][0]
        except ValueError, KeyError, IndexError, TypeError:
            return None
        return status if isinstance(status, str) else None
