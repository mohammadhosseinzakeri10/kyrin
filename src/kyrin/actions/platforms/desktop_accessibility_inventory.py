"""Read names of actionable controls in the currently focused window.

This small process uses Ubuntu's system Python for AT-SPI. It never clicks.
"""

import json
import sys
from collections import deque
from pathlib import Path

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, GLib  # type: ignore[import-not-found]  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from kyrin.actions.platforms.telegram_portal_helper import (  # noqa: E402
    _focused_identity,
    _window_and_pointer,
)


def list_controls(app_id: str, pid: int) -> list[dict[str, object]]:
    if _focused_identity() != (app_id, pid):
        return []
    frame = _window_and_pointer()
    if frame is None or frame[:2] != (app_id, pid):
        return []
    _, _, frame_x, frame_y, frame_w, frame_h, *_ = frame
    state_roles = {
        Atspi.Role.CHECK_BOX,
        Atspi.Role.CHECK_MENU_ITEM,
        Atspi.Role.SWITCH,
        Atspi.Role.TOGGLE_BUTTON,
    }
    actionable = state_roles | {
        Atspi.Role.BUTTON,
        Atspi.Role.ICON,
        Atspi.Role.LINK,
        Atspi.Role.MENU_ITEM,
        Atspi.Role.PUSH_BUTTON_MENU,
        Atspi.Role.RADIO_BUTTON,
        Atspi.Role.RADIO_MENU_ITEM,
    }
    desktop = Atspi.get_desktop(0)
    queue = deque()
    for index in range(desktop.get_child_count()):
        try:
            app = desktop.get_child_at_index(index)
            if app.get_process_id() == pid:
                queue.append(app)
        except GLib.Error, TypeError, ValueError, AttributeError:
            continue
    controls: list[dict[str, object]] = []
    inspected = 0
    while queue and inspected < 3000 and len(controls) < 300:
        node = queue.popleft()
        inspected += 1
        try:
            role = node.get_role()
            name = node.get_name().strip()
            if role in actionable and 1 <= len(name) <= 80:
                component = node.get_component()
                if component is not None:
                    rect = component.get_extents(Atspi.CoordType.SCREEN)
                    x = rect.x + rect.width // 2
                    y = rect.y + rect.height // 2
                    state = node.get_state_set()
                    if (
                        frame_x <= x < frame_x + frame_w
                        and frame_y <= y < frame_y + frame_h
                        and state.contains(Atspi.StateType.ENABLED)
                    ):
                        controls.append(
                            {
                                "label": name,
                                "role": str(role),
                                "checked": (
                                    state.contains(Atspi.StateType.CHECKED)
                                    if role in state_roles
                                    else None
                                ),
                                "x": x - frame_x,
                                "y": y - frame_y,
                            }
                        )
            queue.extend(
                node.get_child_at_index(i)
                for i in range(min(node.get_child_count(), 200))
            )
        except GLib.Error, TypeError, ValueError, AttributeError:
            continue
    if _focused_identity() != (app_id, pid):
        return []
    return controls


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise ValueError("expected app id and process id")
        print(
            json.dumps(list_controls(sys.argv[1], int(sys.argv[2])), ensure_ascii=False)
        )
    except GLib.Error, RuntimeError, ValueError, OSError, AttributeError:
        print("[]")
