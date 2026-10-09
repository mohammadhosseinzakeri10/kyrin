"""Read a minimal active-app ID exposed by the KYRIN GNOME Shell extension."""

import json
import math
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass

from kyrin.desktop.app_catalog import AppCatalog
from kyrin.desktop.app_identity import AppIdentityResolver

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
        """Check the optional Shell endpoint once, before starting live audio."""
        try:
            result = subprocess.run(
                [
                    "busctl",
                    "--user",
                    "introspect",
                    _BUS_NAME,
                    _OBJECT_PATH,
                    _INTERFACE,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=0.5,
            )
        except OSError, subprocess.TimeoutExpired:
            return False
        return result.returncode == 0

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

    def observe_active_app(self) -> str | None:
        """Return only a configured app; never reuse an earlier observation."""
        raw_id = self.read_active_app_id()
        return self._identity.resolve(raw_id)

    def read_active_app_id(self) -> str | None:
        """Return the Shell's current desktop ID, or None if unavailable."""
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
                    "GetActiveWindow",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
                timeout=self._timeout_s,
            )
        except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired, OSError):
            return None
        if completed.returncode != 0:
            return None
        try:
            reply: object = json.loads(completed.stdout)
        except (json.JSONDecodeError, UnicodeError):
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
