"""Read a minimal active-app ID exposed by the KYRIN GNOME Shell extension."""

import json
import math
import subprocess
from collections.abc import Mapping

_BUS_NAME = "org.gnome.Shell"
_OBJECT_PATH = "/org/kyrin/ActiveApp"
_INTERFACE = "org.kyrin.ActiveApp"


class GnomeShellActiveAppObserver:
    """Map a fresh GNOME desktop ID to a trusted internal KYRIN app ID."""

    def __init__(
        self,
        app_ids: Mapping[str, str],
        *,
        timeout_s: float = 1.0,
    ) -> None:
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be finite and positive")
        if any(
            not external.strip() or not internal.strip()
            for external, internal in app_ids.items()
        ):
            raise ValueError("app identifiers must not be empty")
        self._app_ids = dict(app_ids)
        self._timeout_s = timeout_s

    def observe_active_app(self) -> str | None:
        """Return only a configured app; never reuse an earlier observation."""
        raw_id = self.read_active_app_id()
        return self._app_ids.get(raw_id) if raw_id is not None else None

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
