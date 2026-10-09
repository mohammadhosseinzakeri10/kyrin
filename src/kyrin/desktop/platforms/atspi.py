"""On-demand, read-only Ubuntu accessibility observation."""

import json
import math
import subprocess
from pathlib import Path

from kyrin.desktop.app_catalog import AppCatalog
from kyrin.desktop.platforms.gnome import GnomeShellActiveAppObserver
from kyrin.desktop.screen_observation import ScreenObservation, VisibleElement

_PROBE = Path(__file__).with_name("atspi_probe.py")


class UbuntuAtspiScreenObserver:
    """Match a focused GNOME window PID to one active AT-SPI window.

    A snapshot is read-only and never authorizes a later desktop action.
    """

    def __init__(
        self,
        catalog: AppCatalog,
        active_app: GnomeShellActiveAppObserver,
        *,
        system_python: str = "/usr/bin/python3",
        timeout_s: float = 8.0,
        max_nodes: int = 120,
        max_depth: int = 6,
    ) -> None:
        if not system_python or not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("a system Python and positive finite timeout are required")
        if not 1 <= max_nodes <= 500 or not 0 <= max_depth <= 12:
            raise ValueError("observation bounds are out of range")
        self._catalog = catalog
        self._active_app = active_app
        self._system_python = system_python
        self._timeout_s = timeout_s
        self._max_nodes = max_nodes
        self._max_depth = max_depth

    def observe(self) -> ScreenObservation | None:
        focused = self._active_app.read_active_window_identity()
        if focused is None:
            return None
        app = self._catalog.find_app(focused.platform_app_id)
        if app is None:
            return None
        try:
            completed = subprocess.run(
                [
                    self._system_python,
                    str(_PROBE),
                    str(focused.process_id),
                    str(self._max_nodes),
                    str(self._max_depth),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
                timeout=self._timeout_s,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0:
            return None
        try:
            payload: object = json.loads(completed.stdout)
        except (json.JSONDecodeError, UnicodeError):
            return None
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            return None
        name = payload.get("app_name")
        raw_elements = payload.get("elements")
        truncated = payload.get("truncated")
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(raw_elements, list)
            or len(raw_elements) > self._max_nodes
            or not isinstance(truncated, bool)
        ):
            return None
        elements: list[VisibleElement] = []
        for item in raw_elements:
            if not isinstance(item, dict):
                return None
            role, label = item.get("role"), item.get("name")
            if not isinstance(role, str) or not isinstance(label, str):
                return None
            elements.append(VisibleElement(role, label))
        if self._active_app.read_active_window_identity() != focused:
            return None
        return ScreenObservation(
            focused.platform_app_id, name, tuple(elements), truncated
        )
