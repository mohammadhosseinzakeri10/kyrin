"""Read one allowed app's window presence from the optional GNOME adapter."""

import json
import subprocess
from collections.abc import Mapping

from kyrin.backend_protocol import BackendStatus, probe_gnome
from kyrin.desktop.window_presence import WindowPresence

_BUS_NAME = "org.gnome.Shell"
_OBJECT_PATH = "/org/kyrin/ActiveApp"
_INTERFACE = "org.kyrin.ActiveApp"


class GnomeAppWindowPresence:
    def __init__(self, desktop_ids: Mapping[str, str]) -> None:
        self._desktop_ids = dict(desktop_ids)
        self.backend_status = BackendStatus(False, "not_probed")

    def _call(self, method: str, app_id: str) -> tuple[str, object] | None:
        desktop_id = self._desktop_ids.get(app_id)
        if desktop_id is None:
            return None
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
                    _BUS_NAME,
                    _OBJECT_PATH,
                    _INTERFACE,
                    method,
                    "s",
                    desktop_id,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=0.5,
            )
        except OSError, subprocess.TimeoutExpired:
            return None
        if result.returncode != 0:
            return None
        try:
            reply: object = json.loads(result.stdout)
        except json.JSONDecodeError, UnicodeError:
            return None
        if not isinstance(reply, dict):
            return None
        data = reply.get("data")
        if not isinstance(data, list) or len(data) != 1:
            return None
        reply_type = reply.get("type")
        if not isinstance(reply_type, str):
            return None
        return reply_type, data[0]

    def observe(self, app_id: str) -> WindowPresence:
        reply = self._call("HasAppWindow", app_id)
        if reply is None or reply[0] != "s" or not isinstance(reply[1], str):
            return WindowPresence.UNKNOWN
        try:
            return WindowPresence(reply[1])
        except ValueError:
            return WindowPresence.UNKNOWN

    def count(self, app_id: str) -> int | None:
        reply = self._call("CountAppWindows", app_id)
        if reply is None or reply[0] != "i" or type(reply[1]) is not int:
            return None
        return reply[1] if reply[1] >= 0 else None
