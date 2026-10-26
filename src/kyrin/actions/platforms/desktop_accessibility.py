"""Limit AT-SPI traversal to one active top-level window in the process."""

from collections.abc import Callable
from time import sleep
from typing import Any

from kyrin.desktop.accessibility_target import AccessibilityTarget

Control = tuple[Any, AccessibilityTarget, bool, bool | None, tuple[int, int] | None]


def active_accessible_window(
    desktop: Any, pid: int, atspi: Any, *, diagnostics: dict[str, int] | None = None
) -> Any:
    """Ambiguous/missing active windows supply no control evidence.

    ACTIVE is a window state, unlike FOCUSED on its keyboard-focus child:
    https://docs.gtk.org/atspi2/enum.StateType.html
    Callers handle transport errors and bracket traversal with GNOME's token.
    """
    windows = []
    for index in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(index)
        if app.get_process_id() != pid:
            continue
        if diagnostics is not None:
            diagnostics["matching_applications"] = (
                diagnostics.get("matching_applications", 0) + 1
            )
        count = app.get_child_count()
        if count > 200:
            raise ControlUnavailable("incomplete window inventory")
        for child_index in range(count):
            window = app.get_child_at_index(child_index)
            window.clear_cache()
            if window.get_role() in (
                atspi.Role.FRAME,
                atspi.Role.WINDOW,
                atspi.Role.DIALOG,
            ) and window.get_state_set().contains(atspi.StateType.ACTIVE):
                windows.append(window)
    if diagnostics is not None:
        diagnostics["active_windows"] = len(windows)
    return windows[0] if len(windows) == 1 else None


class ControlUnavailable(ValueError):
    """Unsafe, ambiguous or incomplete accessibility evidence; never click instead."""


def _remote_reference(node: Any) -> tuple[str, str] | None:
    """Internal diagnostic comparison only; never export endpoint identifiers."""
    path = getattr(node, "path", None)
    application = getattr(node, "app", None)
    bus_name = getattr(application, "bus_name", None)
    if isinstance(path, str) and path and isinstance(bus_name, str) and bus_name:
        return bus_name, path
    return None


def _ancestry_diagnostic(
    child: Any,
    parent: Any,
    expected: Any,
    depth: int,
    index: int,
    diagnostics: dict[str, int],
    child_probe: Callable[[Any, int], dict[str, int]] | None = None,
) -> None:
    """Measure one rejected edge; refreshed data never rescues this snapshot."""
    diagnostics.update(
        ancestry_failing_depth=depth,
        ancestry_child_index=index,
        ancestry_child_missing=int(child is None),
    )
    if child is None:
        expected.clear_cache()
        diagnostics["ancestry_fresh_child_count"] = expected.get_child_count()
        fresh_child = expected.get_child_at_index(index)
        diagnostics["ancestry_fresh_child_missing"] = int(fresh_child is None)
        if fresh_child is not None:
            fresh_child.clear_cache()
            diagnostics["ancestry_fresh_child_parent_matches"] = int(
                fresh_child.get_parent() == expected
            )
        if child_probe is not None:
            diagnostics.update(child_probe(expected, index))
        return
    reference, expected_reference = (
        _remote_reference(parent),
        _remote_reference(expected),
    )
    diagnostics.update(
        ancestry_parent_missing=int(parent is None),
        ancestry_parent_same_reference=(
            int(reference == expected_reference)
            if reference is not None and expected_reference is not None
            else -1
        ),
    )
    child.clear_cache()
    fresh_parent = child.get_parent()
    diagnostics.update(
        ancestry_fresh_parent_matches=int(fresh_parent == expected),
        ancestry_fresh_parent_missing=int(fresh_parent is None),
    )


def _roles(atspi: Any) -> tuple[set[Any], set[Any]]:
    states = {
        atspi.Role.CHECK_BOX,
        atspi.Role.CHECK_MENU_ITEM,
        atspi.Role.SWITCH,
        atspi.Role.TOGGLE_BUTTON,
    }
    clicks = states | {
        atspi.Role.BUTTON,
        atspi.Role.ICON,
        atspi.Role.LINK,
        atspi.Role.MENU_ITEM,
        atspi.Role.PUSH_BUTTON_MENU,
        atspi.Role.RADIO_BUTTON,
        atspi.Role.RADIO_MENU_ITEM,
    }
    return states, clicks


def valid_node(node: Any, atspi: Any, *, interactive: bool = False) -> bool:
    node.clear_cache()
    state = node.get_state_set()
    required = [atspi.StateType.VISIBLE, atspi.StateType.SHOWING]
    if interactive:
        required += [atspi.StateType.ENABLED, atspi.StateType.SENSITIVE]
    return all(state.contains(item) for item in required) and not any(
        state.contains(item)
        for item in (
            atspi.StateType.DEFUNCT,
            atspi.StateType.STALE,
            atspi.StateType.INVALID,
        )
    )


def _request_window_export(window: Any, diagnostics: dict[str, int] | None) -> bool:
    """Request standard attributes before reading a demand-built control tree.

    Some providers publish only their top-level frame until a client requests
    extended properties. Values are not retained or used as target evidence.
    A short readiness probe never substitutes for the full scan below.
    """
    request = getattr(window, "get_attributes", None)
    if not callable(request):
        return False
    request()
    if diagnostics is not None:
        diagnostics["export_attributes_requested"] = 1
    for attempt in range(3):
        window.clear_cache()
        count = window.get_child_count()
        if type(count) is not int or not 0 <= count <= 200:
            raise ControlUnavailable("incomplete accessibility children")
        if diagnostics is not None:
            diagnostics["export_readiness_reads"] = attempt + 1
        if count == 0 or window.get_child_at_index(0) is not None:
            return True
        if attempt < 2:
            sleep(0.05)
    if diagnostics is not None:
        diagnostics["export_still_missing_child"] = 1
    return True


def control_snapshot(
    desktop: Any,
    pid: int,
    atspi: Any,
    frame: tuple[int, int, int, int],
    *,
    diagnostics: dict[str, int] | None = None,
    geometry: dict[str, object] | None = None,
    child_probe: Callable[[Any, int], dict[str, int]] | None = None,
) -> list[Control]:
    """Keep invalid named candidates too, so they cannot authorize OCR fallback.

    Traversal and parent links must agree. A nested top-level window is never
    part of the active window's control tree. Incomplete scans fail closed.
    """
    window = active_accessible_window(desktop, pid, atspi, diagnostics=diagnostics)
    if window is None:
        # No exported application is a missing capability; an exported but
        # ambiguous/inactive window is unsafe evidence.
        if any(
            desktop.get_child_at_index(i).get_process_id() == pid
            for i in range(desktop.get_child_count())
        ):
            raise ControlUnavailable("no unique active window")
        return []
    if not valid_node(window, atspi):
        raise ControlUnavailable("invalid active window")
    if _request_window_export(window, diagnostics):
        # Export can be asynchronous and can rebuild objects. Select and check
        # the active window again, then validate all geometry and ancestry.
        window = active_accessible_window(desktop, pid, atspi)
        if window is None:
            raise ControlUnavailable("no unique active window")
        if not valid_node(window, atspi):
            raise ControlUnavailable("invalid active window")
    component = window.get_component_iface()
    if component is None:
        raise ControlUnavailable("window has no bounds")
    rect = component.get_extents(atspi.CoordType.SCREEN)
    fx, fy, fw, fh = frame
    fits_frame = (
        rect.width > 0
        and rect.height > 0
        and fx <= rect.x
        and fy <= rect.y
        and rect.x + rect.width <= fx + fw
        and rect.y + rect.height <= fy + fh
    )
    # Some providers expose a zero-origin SCREEN rectangle even though GNOME's
    # focused frame is elsewhere. Bind only the unique active same-PID window
    # with exactly matching dimensions and an explicit WINDOW rectangle. This
    # permits semantic Actions; it does not establish any global input point.
    relative_only = False
    if (
        not fits_frame
        and fw > 0
        and fh > 0
        and (rect.x, rect.y, rect.width, rect.height) == (0, 0, fw, fh)
    ):
        relative = component.get_extents(atspi.CoordType.WINDOW)
        relative_only = (relative.x, relative.y, relative.width, relative.height) == (
            0,
            0,
            fw,
            fh,
        )
    if geometry is not None:
        # Owner-opted-in measurements of the actual guard, including rejection.
        # Never reinterpret, rescale or translate these into execution evidence.
        geometry.update(
            coordinate_type="screen",
            focused_frame=dict(zip(("x", "y", "width", "height"), frame, strict=True)),
            accessible_window={
                "x": rect.x,
                "y": rect.y,
                "width": rect.width,
                "height": rect.height,
            },
            edge_delta={
                "left": rect.x - fx,
                "top": rect.y - fy,
                "right": rect.x + rect.width - (fx + fw),
                "bottom": rect.y + rect.height - (fy + fh),
            },
            fits_focused_frame=fits_frame,
        )
        if relative_only:
            geometry["coordinate_binding"] = "window_relative_semantic_only"
    if not fits_frame and not relative_only:
        raise ControlUnavailable("active window outside focused frame")
    state_roles, click_roles = _roles(atspi)
    window_roles = {atspi.Role.FRAME, atspi.Role.WINDOW, atspi.Role.DIALOG}
    path: tuple[tuple[int, str, str], ...] = (
        (window.get_index_in_parent(), str(window.get_role()), window.get_name()),
    )
    queue: list[tuple[Any, tuple[tuple[int, str, str], ...], bool]] = [
        (window, path, True)
    ]
    found: list[Control] = []
    inspected = 0
    while queue:
        node, ancestry, ancestors_valid = queue.pop()
        inspected += 1
        if diagnostics is not None:
            diagnostics["nodes_inspected"] = inspected
            diagnostics["max_depth"] = max(
                diagnostics.get("max_depth", 0), len(ancestry)
            )
            # Aggregate counters only: no names, values, geometry or ancestry.
            state = node.get_state_set()
            for state_name in ("VISIBLE", "SHOWING", "ENABLED", "SENSITIVE"):
                if not state.contains(getattr(atspi.StateType, state_name)):
                    key = "missing_" + state_name.lower()
                    diagnostics[key] = diagnostics.get(key, 0) + 1
            if not ancestors_valid:
                diagnostics["invalid_ancestor_nodes"] = (
                    diagnostics.get("invalid_ancestor_nodes", 0) + 1
                )
            if node.get_process_id() != pid:
                diagnostics["foreign_process_nodes"] = (
                    diagnostics.get("foreign_process_nodes", 0) + 1
                )
        if inspected > 3000 or len(ancestry) > 100:
            raise ControlUnavailable("incomplete accessibility tree")
        role, name = node.get_role(), node.get_name()
        valid = ancestors_valid and valid_node(node, atspi, interactive=True)
        if node != window and role in window_roles:
            valid = False
        if node.get_process_id() != pid:
            valid = False
        if role in click_roles and 1 <= len(name.strip()) <= 80:
            state = node.get_state_set()
            checked = (
                state.contains(atspi.StateType.CHECKED)
                if role in state_roles
                and not state.contains(atspi.StateType.INDETERMINATE)
                else None
            )
            point = None
            component = node.get_component_iface()
            if relative_only:
                if component is None:
                    valid = False
                else:
                    local = component.get_extents(atspi.CoordType.WINDOW)
                    valid = valid and (
                        local.width > 0
                        and local.height > 0
                        and 0 <= local.x
                        and 0 <= local.y
                        and local.x + local.width <= fw
                        and local.y + local.height <= fh
                    )
                # Never synthesize a screen point from an unlocated provider.
            elif component is not None:
                rect = component.get_extents(atspi.CoordType.SCREEN)
                x, y = rect.x + rect.width // 2, rect.y + rect.height // 2
                if (
                    rect.width > 0
                    and rect.height > 0
                    and (fx <= x < fx + fw and fy <= y < fy + fh)
                ):
                    point = (x, y)
                else:
                    valid = False
            found.append(
                (
                    node,
                    AccessibilityTarget(ancestry),
                    valid and valid_node(node, atspi, interactive=True),
                    checked,
                    point,
                )
            )
        count = node.get_child_count()
        if type(count) is not int or not 0 <= count <= 200:
            raise ControlUnavailable("incomplete accessibility children")
        for index in range(count):
            child = node.get_child_at_index(index)
            parent = child.get_parent() if child is not None else None
            if child is None or parent != node:
                if diagnostics is not None:
                    diagnostics["ancestry_declared_child_count"] = count
                    _ancestry_diagnostic(
                        child,
                        parent,
                        node,
                        len(ancestry),
                        index,
                        diagnostics,
                        child_probe,
                    )
                raise ControlUnavailable("inconsistent ancestry")
            queue.append(
                (
                    child,
                    (*ancestry, (index, str(child.get_role()), child.get_name())),
                    valid,
                )
            )
    return found


def resolve_control(
    desktop: Any,
    pid: int,
    atspi: Any,
    frame: tuple[int, int, int, int],
    label: str,
    target: AccessibilityTarget | None = None,
) -> Control | None:
    def normalize(text: str) -> str:
        return " ".join(text.casefold().split())

    matches = [
        item
        for item in control_snapshot(desktop, pid, atspi, frame)
        if normalize(item[0].get_name()) == normalize(label)
    ]
    if not matches:
        if target is not None:
            raise ControlUnavailable("observed control disappeared")
        return None
    if len(matches) != 1:
        raise ControlUnavailable("ambiguous control")
    if not matches[0][2]:
        raise ControlUnavailable("invalid control")
    if target is not None and matches[0][1] != target:
        raise ControlUnavailable("role or ancestry changed")
    return matches[0]


def action_index(
    node: Any, desired: bool | None, *, checked: bool | None = None
) -> tuple[Any, int] | None:
    """Only absence of Action permits a coordinate fallback.

    Names from Action.get_action_name are non-localized. Never assume that
    action zero is the primary action. Directional check/uncheck verbs require
    readable boolean evidence and must agree with the requested transition.
    """
    action = node.get_action_iface()
    if action is None:
        return None
    count = action.get_n_actions()
    if count == 0:
        return None
    names = [(action.get_action_name(i).casefold(), i) for i in range(count)]
    accepted = (
        {"toggle", "click", "press", "activate"}
        if desired is not None
        else {"click", "press", "activate", "open", "jump"}
    )
    if checked is not None:
        transition = not checked if desired is None else desired
        if transition != checked:
            accepted.add("check" if transition else "uncheck")
    matching = [index for name, index in names if name in accepted]
    if len(matching) != 1:
        raise ControlUnavailable("no unique supported action")
    return action, matching[0]
