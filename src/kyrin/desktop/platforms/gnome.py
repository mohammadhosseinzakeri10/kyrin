"""Read a minimal active-app ID exposed by the KYRIN GNOME Shell extension."""

import json
import math
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from kyrin.backend_protocol import BackendStatus, probe_gnome
from kyrin.desktop.app_catalog import AppCatalog
from kyrin.desktop.app_identity import AppIdentityResolver
from kyrin.operations import current_operation, run_process

_BUS_NAME = "org.gnome.Shell"
_OBJECT_PATH = "/org/kyrin/ActiveApp"
_INTERFACE = "org.kyrin.ActiveApp"


@dataclass(frozen=True, slots=True)
class ActiveWindowIdentity:
    platform_app_id: str
    process_id: int


class GnomeShellActiveAppObserver:
    """Map a fresh GNOME desktop ID to a trusted internal KYRIN app ID."""

    @staticmethod
    def available() -> bool:
        return probe_gnome("ActiveApp", {"GetActiveApp"}, run=subprocess.run).ready

    def __init__(
        self,
        app_ids: Mapping[str, str],
        *,
        catalog: AppCatalog | None = None,
        timeout_s: float = 1.0,
    ) -> None:
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be finite and positive")
        self._identity = AppIdentityResolver(app_ids, catalog)
        self._timeout_s = timeout_s
        self.backend_status = BackendStatus(False, "not_probed")

    def observe_active_app(self) -> str | None:
        """Return only a configured app; never reuse an earlier observation."""
        raw_id = self.read_active_app_id()
        return self._identity.resolve(raw_id)

    def read_active_app_id(self) -> str | None:
        """Return the Shell's current desktop ID, or None if unavailable."""
        self.backend_status = probe_gnome(
            "ActiveApp",
            {"GetActiveApp"},
            run=subprocess.run if current_operation() is None else run_process,
        )
        if not self.backend_status.ready:
            return None
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
                    "GetActiveApp",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
                timeout=self._timeout_s,
            )
        except FileNotFoundError, PermissionError, subprocess.TimeoutExpired, OSError:
            return None
        if completed.returncode != 0:
            return None
        try:
            reply: object = json.loads(completed.stdout)
        except json.JSONDecodeError, UnicodeError:
            return None
        if not isinstance(reply, dict) or reply.get("type") != "s":
            return None
        data = reply.get("data")
        if not isinstance(data, list) or len(data) != 1:
            return None
        app_id = data[0]
        return app_id if isinstance(app_id, str) and app_id else None

    def read_active_window_identity(self) -> ActiveWindowIdentity | None:
        """Read the focused desktop ID and PID together, when supported."""
        self.backend_status = probe_gnome(
            "ActiveApp",
            {"GetActiveWindow"},
            run=subprocess.run if current_operation() is None else run_process,
        )
        if not self.backend_status.ready:
            return None
        try:
            # Desktop actions and OCR share their caller's remaining budget;
            # unrelated observation keeps its existing transport contract.
            run = subprocess.run if current_operation() is None else run_process
            completed = run(
                [
                    "busctl",
                    "--user",
                    "--json=short",
                    "call",
                    _BUS_NAME,
                    _OBJECT_PATH,
                    _INTERFACE,
                    "GetActiveWindow",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
                timeout=self._timeout_s,
            )
        except FileNotFoundError, PermissionError, subprocess.TimeoutExpired, OSError:
            return None
        if completed.returncode != 0:
            return None
        try:
            reply: object = json.loads(completed.stdout)
        except json.JSONDecodeError, UnicodeError:
            return None
        if not isinstance(reply, dict) or reply.get("type") != "su":
            return None
        data = reply.get("data")
        if not isinstance(data, list) or len(data) != 2:
            return None
        app_id, pid = data
        if (
            not isinstance(app_id, str)
            or not app_id
            or not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
        ):
            return None
        return ActiveWindowIdentity(app_id, pid)


def read_active_window_token(
    *,
    run: Callable[..., subprocess.CompletedProcess[str]] = run_process,
) -> str | None:
    """Read the focused Meta.Window's stable token from GNOME."""
    if not probe_gnome("ActiveApp", {"GetActiveWindowToken"}, run=run).ready:
        return None
    try:
        completed = run(
            [
                "busctl",
                "--user",
                "--json=short",
                "call",
                _BUS_NAME,
                _OBJECT_PATH,
                _INTERFACE,
                "GetActiveWindowToken",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        payload = json.loads(completed.stdout)
    except OSError, subprocess.TimeoutExpired, json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    values = payload.get("data")
    if (
        completed.returncode
        or payload.get("type") != "s"
        or not isinstance(values, list)
        or len(values) != 1
        or not isinstance(values[0], str)
        or not values[0]
    ):
        return None
    return values[0]
