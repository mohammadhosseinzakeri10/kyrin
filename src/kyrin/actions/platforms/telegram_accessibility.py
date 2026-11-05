"""Live Telegram menu/search locators; missing semantics never imply a position."""

from dataclasses import dataclass
from typing import Any

from kyrin.actions.platforms.desktop_accessibility import (
    ControlUnavailable,
    valid_node,
)
from kyrin.desktop.accessibility_target import AccessibilityTarget
from kyrin.operations import check_operation

# Exact accessible labels only. Other translations/builds fail closed.
MENU_LABELS = frozenset({"main menu", "منوی اصلی"})
SEARCH_LABELS = frozenset({"search", "جستجو", "جست‌وجو"})
MENU_ITEM_LABELS = frozenset({
    "my profile", "calls", "settings", "contacts", "saved messages",
    "new group", "new channel",
})


class MenuNotOpen(ControlUnavailable):
    """No visible menu rows; this is not evidence for selecting a target."""


class MenuItemMissing(ControlUnavailable):
    """Menu rows exist, but the requested row does not."""


@dataclass(frozen=True)
class TelegramControl:
    node: Any
    target: AccessibilityTarget
    bounds: tuple[int, int, int, int]
    qt_window_local: bool = False


def _active_window(atspi: Any, pid: int) -> tuple[Any, bool]:
    """Qt Telegram exports its top-level QWidget as an ACTIVE FILLER.

    Keep this provider profile local to semantic Telegram actions. A same-PID
    FRAME/WINDOW/DIALOG still participates in ambiguity checks; size alone never
    identifies a window. The caller brackets traversal with Shell ID/PID/token.
    """
    desktop = atspi.get_desktop(0)
    if desktop.get_child_count() > 200:
        raise ControlUnavailable("incomplete Telegram accessibility tree")
    standard_roles = {atspi.Role.FRAME, atspi.Role.WINDOW, atspi.Role.DIALOG}
    candidates: list[tuple[Any, bool]] = []
    for index in range(desktop.get_child_count()):
        check_operation()
        app = desktop.get_child_at_index(index)
        if app.get_process_id() != pid:
            continue
        provider = getattr(app, "get_toolkit_name", None)
        qt = callable(provider) and provider() == "Qt"
        count = app.get_child_count()
        if count > 200:
            raise ControlUnavailable("incomplete Telegram children")
        for child_index in range(count):
            window = app.get_child_at_index(child_index)
            window.clear_cache()
            role = window.get_role()
            qt_root = (
                qt and role == getattr(atspi.Role, "FILLER", None)
                and window.get_parent() == app
            )
            if (role in standard_roles or qt_root) and window.get_state_set().contains(
                atspi.StateType.ACTIVE
            ):
                candidates.append((window, qt_root))
    if len(candidates) != 1:
        raise ControlUnavailable("Telegram has no unique accessible window")
    return candidates[0]


def locate_control(
    atspi: Any, pid: int, frame: tuple[int, int, int, int], kind: str
) -> TelegramControl:
    """Resolve a unique live node inside the sole active window, in any layout."""
    window, qt_root = _active_window(atspi, pid)
    if qt_root:
        component = window.get_component_iface()
        if component is None:
            raise ControlUnavailable("Telegram control has no bounds")
        rect = component.get_extents(atspi.CoordType.SCREEN)
        if (rect.x, rect.y, rect.width, rect.height) != (0, 0, frame[2], frame[3]):
            raise ControlUnavailable("Telegram root extents mismatch")
        # This provider's SCREEN rectangles are window-local on Wayland. They
        # bind semantic objects only; never translate them into pointer clicks.
        frame = (0, 0, frame[2], frame[3])
    menu_item = (
        kind.removeprefix("menu-item:") if kind.startswith("menu-item:") else None
    )
    if menu_item is not None and menu_item not in MENU_ITEM_LABELS:
        raise ControlUnavailable("unsupported Telegram menu destination")
    labels = (
        frozenset({menu_item}) if menu_item is not None
        else MENU_LABELS if kind == "menu" else SEARCH_LABELS
    )
    roles = (
        {atspi.Role.PUSH_BUTTON_MENU, atspi.Role.BUTTON}
        if kind == "menu" or menu_item is not None
        else {atspi.Role.ENTRY, atspi.Role.TEXT}
    )
    window_roles = {atspi.Role.FRAME, atspi.Role.WINDOW, atspi.Role.DIALOG}
    queue: list[tuple[Any, tuple[tuple[int, str, str], ...], bool]] = [
        (window, (), True)
    ]
    matches: list[TelegramControl] = []
    anchors: list[Any] = []
    # Counts only distinguish fixed failure reasons; they never authorize input.
    labelled = role_labelled = 0
    inspected = 0
    fx, fy, fw, fh = frame
    while queue:
        check_operation()
        node, ancestry, parents_valid = queue.pop()
        inspected += 1
        if inspected > 3000 or len(ancestry) >= 100:
            raise ControlUnavailable("incomplete Telegram accessibility tree")
        node.clear_cache()
        role, name = node.get_role(), node.get_name()
        path = (*ancestry, (node.get_index_in_parent(), str(role), name))
        valid = (
            parents_valid
            and valid_node(node, atspi, interactive=True)
            and node.get_process_id() == pid
            and (node == window or role not in window_roles)
        )
        label_matches = node != window and " ".join(name.casefold().split()) in labels
        labelled += label_matches
        named = label_matches and role in roles
        role_labelled += named
        if (
            menu_item is not None and node != window and role in roles and valid
            and " ".join(name.casefold().split()) in MENU_ITEM_LABELS
        ):
            anchors.append(node)
        if named:
            state = node.get_state_set()
            named = state.contains(atspi.StateType.VISIBLE) and state.contains(
                atspi.StateType.SHOWING
            )
            if named and kind == "search":
                # Qt exposes Search text wrappers as well as the actual editor.
                # Hidden clones/labels cannot authorize editing or ambiguity.
                named = (
                    state.contains(atspi.StateType.EDITABLE)
                    and node.get_editable_text_iface() is not None
                    and node.get_text_iface() is not None
                )
        if node == window or named:
            component = node.get_component_iface()
            if component is None:
                raise ControlUnavailable("Telegram control has no bounds")
            rect = component.get_extents(atspi.CoordType.SCREEN)
            bounds = (rect.x, rect.y, rect.width, rect.height)
            if not valid:
                raise ControlUnavailable(
                    "Telegram window state invalid" if node == window
                    else "Telegram control state invalid"
                )
            if not (
                rect.width > 0
                and rect.height > 0
                and fx <= rect.x
                and fy <= rect.y
                and rect.x + rect.width <= fx + fw
                and rect.y + rect.height <= fy + fh
            ):
                raise ControlUnavailable(
                    "Telegram window bounds invalid" if node == window
                    else "Telegram control bounds invalid"
                )
            if node != window:
                matches.append(TelegramControl(
                    node, AccessibilityTarget(path), bounds, qt_root
                ))
        count = node.get_child_count()
        if count > 200:
            raise ControlUnavailable("incomplete Telegram children")
        for index in range(count):
            child = node.get_child_at_index(index)
            if child is None or child.get_parent() != node:
                raise ControlUnavailable("inconsistent Telegram ancestry")
            queue.append((child, path, valid))
    if menu_item is not None:
        if not anchors:
            raise MenuNotOpen("Telegram menu rows unavailable")
        if not matches:
            raise MenuItemMissing("Telegram menu destination unavailable")
        if len(matches) == 1:
            parent = matches[0].node.get_parent()
            if sum(node.get_parent() == parent for node in anchors) < 2:
                raise ControlUnavailable("Telegram menu context unverified")
    if len(matches) > 1:
        raise ControlUnavailable("Telegram control ambiguous")
    if not matches:
        raise ControlUnavailable(
            "Telegram control label absent" if not labelled
            else "Telegram control role unsupported" if not role_labelled
            else "Telegram control not visible or usable"
        )
    return matches[0]


# Fixed, content-free reason codes for opt-in menu tracing. Keys are this
# package's own literal exception messages, never labels, names or targets.
FAILURE_CODES = {
    "incomplete Telegram accessibility tree": "tree_incomplete",
    "incomplete Telegram children": "children_incomplete",
    "inconsistent Telegram ancestry": "ancestry_inconsistent",
    "Telegram has no unique accessible window": "no_unique_window",
    "Telegram root extents mismatch": "root_extents",
    "Telegram control has no bounds": "no_component",
    "unsupported Telegram menu destination": "unsupported_destination",
    "Telegram window state invalid": "window_state",
    "Telegram window bounds invalid": "window_bounds",
    "Telegram control state invalid": "control_state",
    "Telegram control bounds invalid": "control_bounds",
    "Telegram menu rows unavailable": "rows_unavailable",
    "Telegram menu destination unavailable": "destination_missing",
    "Telegram menu context unverified": "menu_context",
    "Telegram control ambiguous": "ambiguous",
    "Telegram control label absent": "label_absent",
    "Telegram control role unsupported": "role_unsupported",
    "Telegram control not visible or usable": "not_usable",
    # telegram_portal_helper.py and the shared action selector.
    "Telegram accessibility unavailable": "atspi_unavailable",
    "Telegram window identity unavailable": "identity_unavailable",
    "Telegram window changed during resolution": "window_changed_in_resolution",
    "Telegram field identity or layout changed": "control_changed",
    "Telegram control lost focus": "focus_not_observed",
    "Telegram focus changed before input": "focus_changed_before_input",
    "Telegram window changed before input": "window_changed_before_input",
    "Telegram menu focus rejected": "focus_rejected",
    "Telegram menu has no supported action": "no_action",
    "no unique supported action": "no_unique_action",
    "Telegram menu opening rejected": "opener_rejected",
    "Telegram menu destination activation rejected": "destination_rejected",
    "Telegram focus changed before search": "search_focus_changed",
    "Telegram search clear failed": "search_clear_failed",
    "Telegram search contents changed": "search_contents_changed",
    "Telegram search insert failed": "search_insert_failed",
    "Telegram search text unverified": "search_text_unverified",
    "Telegram search window changed": "search_window_changed",
    "Telegram search focus rejected": "search_focus_rejected",
}
MENU_TRACE_STAGES = frozenset({
    "rows_absent_before_open", "opener_located", "opener_focus_route",
    "opener_action_route", "opener_dispatched", "rows_not_ready",
    "visual_fallback_required", "destination_verified", "destination_dispatched",
    *("failure_" + code for code in {*FAILURE_CODES.values(), "other"}),
})


def failure_code(error: ControlUnavailable) -> str:
    """Map a known literal reason to a fixed code; anything else is ``other``."""
    return FAILURE_CODES.get(str(error), "other")
