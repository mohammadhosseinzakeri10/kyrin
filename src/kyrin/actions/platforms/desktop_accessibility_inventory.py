"""Read names of actionable controls in the currently focused window.

This small process uses Ubuntu's system Python for AT-SPI. It never clicks.
"""

import json
import sys
from collections import Counter
from pathlib import Path

import gi  # type: ignore[import-not-found]

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, GLib  # type: ignore[import-not-found]  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from kyrin.actions.platforms.desktop_accessibility import (  # noqa: E402
    control_snapshot,
)
from kyrin.actions.platforms.telegram_portal_helper import (  # noqa: E402
    _focused_identity,
    _focused_window_token,
    _window_and_pointer,
)


def list_controls(app_id: str, pid: int, window_token: str) -> list[dict[str, object]]:
    if (
        _focused_identity() != (app_id, pid)
        or not window_token
        or _focused_window_token() != window_token
    ):
        return []
    frame = _window_and_pointer()
    if frame is None or frame[:2] != (app_id, pid):
        return []
    _, _, frame_x, frame_y, frame_w, frame_h, *_ = frame
    try:
        snapshot = control_snapshot(
            Atspi.get_desktop(0), pid, Atspi, (frame_x, frame_y, frame_w, frame_h)
        )
    except GLib.Error, TypeError, ValueError, AttributeError:
        return []
    names = [" ".join(item[0].get_name().casefold().split()) for item in snapshot]
    counts = Counter(names)
    controls: list[dict[str, object]] = []
    for (node, target, valid, checked, point), name in zip(
        snapshot, names, strict=True
    ):
        if not valid:
            continue
        # Duplicate names (including invalid nodes) are deliberately omitted.
        if counts[name] != 1:
            continue
        controls.append(
            {
                "label": node.get_name().strip(),
                "role": str(node.get_role()),
                "checked": checked,
                "x": point[0] - frame_x if point is not None else None,
                "y": point[1] - frame_y if point is not None else None,
                "accessibility": target.to_json(),
            }
        )
    if (
        _focused_identity() != (app_id, pid)
        or not window_token
        or _focused_window_token() != window_token
    ):
        return []
    return controls


if __name__ == "__main__":
    try:
        if len(sys.argv) != 4:
            raise ValueError("expected app id, process id and window token")
        print(
            json.dumps(
                list_controls(sys.argv[1], int(sys.argv[2]), sys.argv[3]),
                ensure_ascii=False,
            )
        )
    except GLib.Error, RuntimeError, ValueError, OSError, AttributeError:
        print("[]")
