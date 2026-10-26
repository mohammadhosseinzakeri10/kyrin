"""Isolated Ubuntu AT-SPI reader, invoked with the system Python interpreter.

The accessibility bridge may abort on a missing bus. Keeping it in a short-lived
process prevents an unavailable desktop service from stopping KYRIN.
"""

import json
import sys


def main() -> int:
    import gi  # type: ignore[import-not-found]

    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi, GLib  # type: ignore[import-not-found]

    expected_pid = int(sys.argv[1])
    max_nodes = int(sys.argv[2])
    max_depth = int(sys.argv[3])
    desktop = Atspi.get_desktop(0)
    active = []
    showing = []
    for app_index in range(desktop.get_child_count()):
        try:
            app = desktop.get_child_at_index(app_index)
            if app.get_process_id() != expected_pid:
                continue
            for window_index in range(app.get_child_count()):
                window = app.get_child_at_index(window_index)
                states = window.get_state_set()
                if states.contains(Atspi.StateType.SHOWING):
                    showing.append((app, window))
                    if states.contains(Atspi.StateType.ACTIVE):
                        active.append((app, window))
        except (GLib.Error, RuntimeError, TypeError, ValueError):
            continue
    matches = active if active else showing
    if len(matches) != 1:
        print(json.dumps({"status": "unavailable"}))
        return 0

    app, window = matches[0]
    elements: list[dict[str, str]] = []
    visited = 0
    truncated = False
    stack = [(window, 0)]
    while stack:
        node, depth = stack.pop()
        if visited >= max_nodes:
            truncated = True
            break
        visited += 1
        try:
            states = node.get_state_set()
            if not states.contains(Atspi.StateType.SHOWING):
                continue
            role = node.get_role_name()
            name = node.get_name()
            if isinstance(role, str) and isinstance(name, str) and name.strip():
                elements.append({"role": role[:80], "name": name.strip()[:160]})
            if depth < max_depth:
                count = node.get_child_count()
                for index in range(min(count, max_nodes) - 1, -1, -1):
                    stack.append((node.get_child_at_index(index), depth + 1))
            elif node.get_child_count() > 0:
                truncated = True
        except (GLib.Error, RuntimeError, TypeError, ValueError):
            continue
    print(
        json.dumps(
            {
                "status": "ok",
                "app_name": app.get_name(),
                "elements": elements,
                "truncated": truncated,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
