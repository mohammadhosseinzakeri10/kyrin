"""Request focus for a registered GNOME application already on screen."""

import json
import math
import subprocess
from collections.abc import Mapping

from kyrin.backend_protocol import BackendStatus, probe_gnome
from kyrin.desktop.app_activation import ActivationAttempt

_BUS_NAME = "org.gnome.Shell"
_OBJECT_PATH = "/org/kyrin/ActiveApp"
_INTERFACE = "org.kyrin.ActiveApp"


class GnomeExistingAppActivator:
    """Pass only exact installed desktop IDs to the optional Shell extension."""

    @staticmethod
    def available() -> bool:
        return probe_gnome(
            "ActiveApp", {"ActivateExistingApp"}, run=subprocess.run
        ).ready

    def __init__(
        self, desktop_ids: Mapping[str, str], *, timeout_s: float = 1.0
    ) -> None:
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be finite and positive")
        if any(
            not app_id.strip()
            or not desktop_id.strip()
            or not desktop_id.endswith(".desktop")
            for app_id, desktop_id in desktop_ids.items()
        ):
            raise ValueError("activation requires registered desktop IDs")
        self._desktop_ids = dict(desktop_ids)
        self._timeout_s = timeout_s
        self.backend_status = BackendStatus(False, "not_probed")

    def activate_existing_app(self, app_id: str) -> ActivationAttempt:
        desktop_id = self._desktop_ids.get(app_id)
        if desktop_id is None:
            return ActivationAttempt.UNKNOWN
        self.backend_status = probe_gnome(
            "ActiveApp", {"ActivateExistingApp"}, run=subprocess.run
        )
        if not self.backend_status.ready:
            return ActivationAttempt.UNKNOWN
        try:
            completed = subprocess.run(
                [
                    "busctl",
                    "--user",
                    "--json=short",
                    "call",
                    _BUS_NAME,
                    _OBJECT_PATH,
                    _INTERFACE,
                    "ActivateExistingApp",
                    "s",
                    desktop_id,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout_s,
            )
        except OSError, subprocess.TimeoutExpired:
            return ActivationAttempt.UNKNOWN
        if completed.returncode != 0:
            return ActivationAttempt.UNKNOWN
        try:
            reply: object = json.loads(completed.stdout)
        except json.JSONDecodeError, UnicodeError:
            return ActivationAttempt.UNKNOWN
        if not isinstance(reply, dict) or reply.get("type") != "s":
            return ActivationAttempt.UNKNOWN
        data = reply.get("data")
        if not isinstance(data, list) or len(data) != 1:
            return ActivationAttempt.UNKNOWN
        if data[0] == ActivationAttempt.REQUESTED.value:
            return ActivationAttempt.REQUESTED
        if data[0] == ActivationAttempt.NO_WINDOW.value:
            return ActivationAttempt.NO_WINDOW
        if data[0] == ActivationAttempt.MULTIPLE_WINDOWS.value:
            return ActivationAttempt.MULTIPLE_WINDOWS
        return ActivationAttempt.UNKNOWN
