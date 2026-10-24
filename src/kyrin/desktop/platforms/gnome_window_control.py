"""GNOME Shell adapter for one pre-authorized, existing app window."""

import json
import math
import subprocess
from collections.abc import Mapping
from dataclasses import replace
from time import sleep

from kyrin.backend_protocol import BackendStatus, probe_gnome
from kyrin.desktop.window_control import WindowControlStatus, WindowOperation
from kyrin.desktop.window_observation import WindowObservation
from kyrin.operations import run_process

_BUS_NAME = "org.gnome.Shell"
_OBJECT_PATH = "/org/kyrin/ActiveApp"
_INTERFACE = "org.kyrin.ActiveApp"


class GnomeAppWindowController:
    def __init__(
        self,
        desktop_ids: Mapping[str, str],
        *,
        timeout_s: float = 1.0,
        attempts: int = 5,
        retry_delay_s: float = 0.15,
    ) -> None:
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be finite and positive")
        if attempts <= 0 or not math.isfinite(retry_delay_s) or retry_delay_s < 0:
            raise ValueError("invalid verification retries")
        if any(
            not app_id.strip()
            or not desktop_id.endswith(".desktop")
            or "/" in desktop_id
            or "\\" in desktop_id
            for app_id, desktop_id in desktop_ids.items()
        ):
            raise ValueError("window control requires registered desktop IDs")
        self._desktop_ids = dict(desktop_ids)
        self._timeout_s = timeout_s
        self._attempts = attempts
        self._retry_delay_s = retry_delay_s
        self.backend_status = BackendStatus(False, "not_probed")

    @staticmethod
    def available() -> bool:
        return probe_gnome(
            "ActiveApp",
            {
                "ControlAppWindow",
                "GetAppWindowState",
                "PrepareWindowClose",
                "CloseConfirmedWindow",
            },
            run=subprocess.run,
        ).ready

    def _call(self, method: str, signature: str, *args: str) -> tuple[str, ...] | None:
        required = {method}
        if method in {"ControlAppWindow", "PrepareWindowClose", "CloseConfirmedWindow"}:
            required.add("GetAppWindowState")
        if method == "PrepareWindowClose":
            required.add("CloseConfirmedWindow")
        self.backend_status = probe_gnome("ActiveApp", required, run=run_process)
        if not self.backend_status.ready:
            return None
        try:
            completed = run_process(
                [
                    "busctl",
                    "--user",
                    "--json=short",
                    "call",
                    _BUS_NAME,
                    _OBJECT_PATH,
                    _INTERFACE,
                    method,
                    signature,
                    *args,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout_s,
            )
        except OSError, subprocess.TimeoutExpired:
            return None
        if completed.returncode != 0:
            return None
        try:
            reply: object = json.loads(completed.stdout)
        except json.JSONDecodeError, UnicodeError:
            return None
        if not isinstance(reply, dict) or reply.get("type") not in ("s", "ss"):
            return None
        data = reply.get("data")
        if not isinstance(data, list) or not all(
            isinstance(item, str) for item in data
        ):
            return None
        if len(data) != len(reply["type"]):
            return None
        return tuple(data)

    def control(self, app_id: str, operation: WindowOperation) -> WindowControlStatus:
        if operation is WindowOperation.CLOSE:
            # Closing must pass the shared per-window confirmation, never an
            # app-name-only D-Bus call (including on an old loaded extension).
            return WindowControlStatus.UNAVAILABLE
        desktop_id = self._desktop_ids.get(app_id)
        if desktop_id is None:
            return WindowControlStatus.UNKNOWN
        reply = self._call("ControlAppWindow", "ss", desktop_id, operation.value)
        if reply is None or len(reply) != 2:
            return WindowControlStatus.UNKNOWN
        status, token = reply
        if status == "no_window":
            return WindowControlStatus.NO_WINDOW
        if status == "multiple_windows":
            return WindowControlStatus.MULTIPLE_WINDOWS
        if status == "unavailable":
            return WindowControlStatus.UNAVAILABLE
        if status != "requested" or not token.isdecimal():
            return WindowControlStatus.UNKNOWN
        expected = {
            WindowOperation.RESTORE: ("focused", True),
            WindowOperation.MINIMIZE: ("minimized", True),
            WindowOperation.MAXIMIZE: ("maximized", True),
            WindowOperation.UNMAXIMIZE: ("maximized", False),
            WindowOperation.FULLSCREEN: ("fullscreen", True),
            WindowOperation.UNFULLSCREEN: ("fullscreen", False),
        }
        for index in range(self._attempts):
            if index:
                sleep(self._retry_delay_s)
            state_reply = self._call("GetAppWindowState", "ss", desktop_id, token)
            if state_reply is None or len(state_reply) != 1:
                continue
            state = state_reply[0]
            try:
                observed: object = json.loads(state)
            except json.JSONDecodeError:
                continue
            if not isinstance(observed, dict):
                continue
            field, wanted = expected[operation]
            if observed.get(field) is wanted and (
                operation is not WindowOperation.UNMAXIMIZE
                or observed.get("fullscreen") is False
            ):
                return WindowControlStatus.CONFIRMED
        return WindowControlStatus.UNKNOWN

    def prepare_close(
        self, app_id: str, window_index: int | None = None
    ) -> WindowObservation | None:
        desktop_id = "" if app_id == "desktop" else self._desktop_ids.get(app_id)
        if desktop_id is None:
            return None
        reply = self._call(
            "PrepareWindowClose", "su", desktop_id, str(window_index or 0)
        )
        if reply is None or len(reply) != 1:
            return None
        try:
            observation = WindowObservation.from_json(reply[0])
        except ValueError, TypeError:
            return None
        resolved_app = next(
            (
                key
                for key, value in self._desktop_ids.items()
                if value == observation.app_id
            ),
            None,
        )
        if resolved_app is None:
            return None
        # Keep platform desktop IDs at the platform boundary; the shared
        # prompt and allowlist use the same internal app IDs as ActionGate.
        return replace(observation, app_id=resolved_app)

    def close_confirmed(self, window: WindowObservation) -> WindowControlStatus:
        desktop_id = self._desktop_ids.get(window.app_id)
        if desktop_id is None:
            return WindowControlStatus.UNKNOWN
        reply = self._call("CloseConfirmedWindow", "s", window.generation)
        if reply != ("requested",):
            return WindowControlStatus.UNKNOWN
        for index in range(self._attempts):
            if index:
                sleep(self._retry_delay_s)
            state = self._call(
                "GetAppWindowState", "ss", desktop_id, window.window_token
            )
            if state == ("no_window",):
                return WindowControlStatus.CONFIRMED
        # A save dialog, an ignored request or an uncertain transport is never
        # permission to force-close, retry close or answer the application's UI.
        return WindowControlStatus.UNKNOWN
