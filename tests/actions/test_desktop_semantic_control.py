"""Real resolver/action path against deterministic AT-SPI and owner transports."""

import importlib.util
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from time import monotonic
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from kyrin.actions.desktop_input import DesktopInputBroker, DesktopInputExecutor
from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.platforms import desktop_accessibility as accessibility
from kyrin.actions.platforms import desktop_control
from kyrin.commands.models import CommandIntent, CommandKind
from kyrin.desktop.accessibility_target import AccessibilityTarget
from kyrin.desktop.window_observation import WindowObservation
from kyrin.operations import OperationStopped, current_operation
from tests.desktop.test_backend_protocol import bus_reply

ROLES = (
    "FRAME",
    "WINDOW",
    "DIALOG",
    "PANEL",
    "CHECK_BOX",
    "CHECK_MENU_ITEM",
    "SWITCH",
    "TOGGLE_BUTTON",
    "BUTTON",
    "ICON",
    "LINK",
    "MENU_ITEM",
    "PUSH_BUTTON_MENU",
    "RADIO_BUTTON",
    "RADIO_MENU_ITEM",
)
STATES = (
    "ACTIVE",
    "VISIBLE",
    "SHOWING",
    "ENABLED",
    "SENSITIVE",
    "DEFUNCT",
    "STALE",
    "INVALID",
    "CHECKED",
    "INDETERMINATE",
)
NORMAL = {"VISIBLE", "SHOWING", "ENABLED", "SENSITIVE"}
FRAME = ("example.desktop", 42, 10, 20, 800, 600, 0, 0)


@dataclass(eq=False)
class Node:
    role: str = "BUTTON"
    name: str = "Settings"
    pid: int = 42
    states: set[str] = field(default_factory=lambda: set(NORMAL))
    children: list[Node] = field(default_factory=list)
    parent: Node | None = field(default=None, repr=False)
    bounds: tuple[int, int, int, int] | None = (40, 80, 90, 20)
    relative_bounds: tuple[int, int, int, int] | None = None
    actions: list[str] | None = field(default_factory=lambda: ["show menu", "click"])
    calls: list[int] = field(default_factory=list)
    invoked: bool = True
    change_checked: bool = False
    reads: int = 0

    def add(self, child: Node) -> Node:
        child.parent = self
        self.children.append(child)
        return child

    def get_child_count(self) -> int:
        return len(self.children)

    def get_child_at_index(self, index: int) -> Node:
        return self.children[index]

    def get_parent(self) -> Node | None:
        return self.parent

    def get_index_in_parent(self) -> int:
        assert self.parent is not None
        return self.parent.children.index(self)

    def get_process_id(self) -> int:
        return self.pid

    def get_role(self) -> str:
        return self.role

    def get_name(self) -> str:
        return self.name

    def clear_cache(self) -> None:
        self.reads += 1

    def get_state_set(self) -> Node:
        return self

    def contains(self, value: str) -> bool:
        return value in self.states

    def get_component_iface(self) -> Node | None:
        return self if self.bounds is not None else None

    def get_extents(self, coord: str) -> SimpleNamespace:
        assert coord in {"SCREEN", "WINDOW"} and self.bounds is not None
        bounds = self.bounds if coord == "SCREEN" else self.relative_bounds
        return SimpleNamespace(
            **dict(
                zip(
                    ("x", "y", "width", "height"), bounds or (-1, -1, 0, 0), strict=True
                )
            )
        )

    def get_action_iface(self) -> Node | None:
        return self if self.actions is not None else None

    def get_n_actions(self) -> int:
        assert self.actions is not None
        return len(self.actions)

    def get_action_name(self, index: int) -> str:
        assert self.actions is not None
        return self.actions[index]

    def do_action(self, index: int) -> bool:
        self.calls.append(index)
        if self.change_checked:
            self.states.symmetric_difference_update({"CHECKED"})
        return self.invoked


@dataclass
class Owner:
    events: list[bool] = field(default_factory=list)
    revoked: bool = False

    def check(self, *, input_event: bool = False) -> None:
        self.events.append(input_event)
        if self.revoked:
            raise OperationStopped("owner cancelled or permission revoked")


@pytest.fixture
def semantic(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    gi = ModuleType("gi")
    repository: Any = ModuleType("gi.repository")
    monkeypatch.setattr(repository, "Gio", ModuleType("Gio"), raising=False)
    monkeypatch.setattr(repository, "GLib", ModuleType("GLib"), raising=False)
    repository.GLib.Error = RuntimeError
    monkeypatch.setattr(repository.Gio, "DBusConnection", object, raising=False)
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", repository)
    path = Path(desktop_control.__file__).with_name("desktop_control_helper.py")
    spec = importlib.util.spec_from_file_location("semantic_helper_test", path)
    assert spec is not None and spec.loader is not None
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)

    def handshake_transport(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        assert args[-1] == "GetCapabilities", "unexpected unmocked desktop call"
        return bus_reply(
            "GetActiveWindow",
            "GetActiveWindowToken",
            "GetActiveWindowAndPointer",
        )

    monkeypatch.setattr(helper, "run_process", handshake_transport)
    desktop = Node(role="DESKTOP", name="desktop")
    app = desktop.add(Node(role="APPLICATION", name="app"))
    window = app.add(
        Node(role="FRAME", name="Main", states=NORMAL | {"ACTIVE"}, bounds=FRAME[2:6])
    )
    panel = window.add(Node(role="PANEL", name="Navigation"))
    node = panel.add(Node())
    atspi = SimpleNamespace(
        Role=SimpleNamespace(**dict(zip(ROLES, ROLES, strict=True))),
        StateType=SimpleNamespace(**dict(zip(STATES, STATES, strict=True))),
        CoordType=SimpleNamespace(SCREEN="SCREEN", WINDOW="WINDOW"),
        get_desktop=lambda _i: desktop,
    )
    token = ["window-7"]
    now = [101.0]
    observation = WindowObservation(
        "example.desktop", 42, "window-7", "initial", 100, 110
    )
    monkeypatch.setattr(helper, "_atspi", lambda: atspi)
    monkeypatch.setattr(helper, "_focused_identity", lambda: FRAME[:2])
    monkeypatch.setattr(helper, "_focused_window_token", lambda: token[0])
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: FRAME)
    monkeypatch.setattr(helper, "monotonic", lambda: now[0])
    monkeypatch.setattr(
        helper, "sleep", lambda duration: now.__setitem__(0, now[0] + duration)
    )
    owner = Owner()

    def invoke(
        desired: bool | None = None,
        target: AccessibilityTarget | None = None,
        *,
        label: str = "Settings",
    ) -> str:
        result = helper._semantic_control(
            FRAME[:2], label, desired, observation, owner, target
        )
        assert isinstance(result, str)
        return result

    return SimpleNamespace(
        helper=helper,
        node=node,
        window=window,
        panel=panel,
        app=app,
        desktop=desktop,
        atspi=atspi,
        owner=owner,
        token=token,
        now=now,
        observation=observation,
        invoke=invoke,
    )


@pytest.mark.parametrize("role", ["BUTTON", "LINK", "MENU_ITEM"])
def test_invokes_advertised_nonzero_action_without_coordinates(
    semantic: SimpleNamespace,
    role: str,
) -> None:
    semantic.node.role = role
    semantic.node.bounds = None
    assert semantic.invoke() == "ACTION_DISPATCHED"
    assert semantic.node.calls == [1]
    assert semantic.owner.events[:2] == [True, False]
    assert semantic.owner.events[2:] and not any(semantic.owner.events[2:])


@pytest.mark.parametrize(
    "frame", [(67, 32, 1853, 1048), (-1920, 32, 1853, 1048), (100, 200, 800, 600)]
)
def test_zero_origin_window_can_use_semantic_action_without_inventing_screen_point(
    semantic: SimpleNamespace,
    inventory: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    frame: tuple[int, int, int, int],
) -> None:
    semantic.window.bounds = semantic.window.relative_bounds = (
        0,
        0,
        frame[2],
        frame[3],
    )
    semantic.node.relative_bounds = (40, 80, 90, 20)
    focused = (*FRAME[:2], *frame, 0, 0)
    monkeypatch.setattr(semantic.helper, "_window_and_pointer", lambda: focused)
    monkeypatch.setattr(inventory, "_window_and_pointer", lambda: focused)
    reply = inventory.observe_controls(*FRAME[:2], "window-7")
    assert reply.status == "ok" and len(reply.controls) == 1
    control = reply.controls[0]
    assert control["x"] is None and control["y"] is None
    target = AccessibilityTarget.from_json(str(control["accessibility"]))
    assert semantic.invoke(target=target) == "ACTION_DISPATCHED"
    assert semantic.node.calls == [1]


@pytest.fixture
def relative_semantic(semantic: SimpleNamespace) -> SimpleNamespace:
    semantic.window.bounds = semantic.window.relative_bounds = (0, 0, 800, 600)
    semantic.node.relative_bounds = (40, 80, 90, 20)
    return semantic


@pytest.mark.parametrize(
    "bad_evidence",
    [
        "root_relative_origin",
        "root_relative_size",
        "screen_size",
        "disabled",
        "foreign_pid",
        "off_window",
        "duplicate",
        "second_active",
        "ancestry",
        "missing_component",
    ],
)
def test_relative_geometry_does_not_bypass_window_or_control_validation(
    relative_semantic: SimpleNamespace,
    bad_evidence: str,
) -> None:
    scene = relative_semantic
    if bad_evidence == "root_relative_origin":
        scene.window.relative_bounds = (1, 0, 800, 600)
    elif bad_evidence == "root_relative_size":
        scene.window.relative_bounds = (0, 0, 799, 600)
    elif bad_evidence == "screen_size":
        scene.window.bounds = (0, 0, 1600, 1200)
    elif bad_evidence == "disabled":
        scene.node.states.remove("ENABLED")
    elif bad_evidence == "foreign_pid":
        scene.node.pid = 99
    elif bad_evidence == "off_window":
        scene.node.relative_bounds = (790, 80, 90, 20)
    elif bad_evidence == "duplicate":
        scene.panel.add(Node(relative_bounds=(140, 80, 90, 20)))
    elif bad_evidence == "second_active":
        scene.app.add(Node(role="DIALOG", states=NORMAL | {"ACTIVE"}))
    elif bad_evidence == "ancestry":
        scene.node.parent = scene.window
    else:
        scene.node.bounds = None
    with pytest.raises(accessibility.ControlUnavailable):
        scene.invoke()
    assert scene.node.calls == [] and scene.owner.events == []


def test_relative_geometry_cannot_authorize_coordinate_fallback(
    relative_semantic: SimpleNamespace,
) -> None:
    scene = relative_semantic
    scene.node.actions = None
    assert scene.invoke() == "NO_ACCESSIBLE_ACTION"
    assert (
        scene.helper._accessible_control(
            "Settings", FRAME[2:6], 42, near=None, state_required=False
        )
        is None
    )
    assert scene.node.calls == [] and scene.owner.events == []


def test_relative_checkbox_repeated_state_request_keeps_requested_state(
    relative_semantic: SimpleNamespace,
) -> None:
    scene = relative_semantic
    scene.node.role = "CHECK_BOX"
    scene.node.actions = ["toggle"]
    scene.node.change_checked = True
    for desired in (True, False, True):
        before = len(scene.node.calls)
        assert scene.invoke(desired) == "STATE_CONFIRMED"
        assert scene.invoke(desired) == "STATE_ALREADY_SET"
        assert ("CHECKED" in scene.node.states) is desired
        assert len(scene.node.calls) == before + 1


@pytest.mark.parametrize("role", ["BUTTON", "CHECK_BOX"])
def test_shared_reader_requests_attributes_before_enumerating_lazy_export(
    relative_semantic: SimpleNamespace,
    inventory: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
) -> None:
    scene = relative_semantic
    requested: list[bool] = []
    scene.node.role = role

    def attributes() -> dict[str, str]:
        requested.append(True)
        return {"private": "ignored attribute values"}

    def child(_index: int) -> Node | None:
        return scene.panel if requested else None

    monkeypatch.setattr(scene.window, "get_attributes", attributes, raising=False)
    monkeypatch.setattr(scene.window, "get_child_at_index", child)
    reply = inventory.observe_controls(*FRAME[:2], "window-7")
    assert reply.status == "ok" and len(reply.controls) == 1
    assert reply.controls[0]["label"] == "Settings"
    assert requested == [True]
    assert "private" not in reply.to_json()
    scene.node.actions = ["toggle"] if role == "CHECK_BOX" else ["click"]
    scene.node.change_checked = role == "CHECK_BOX"
    assert scene.invoke(True if role == "CHECK_BOX" else None) == (
        "STATE_CONFIRMED" if role == "CHECK_BOX" else "ACTION_DISPATCHED"
    )
    assert scene.node.calls == [0]


def test_attribute_request_does_not_hide_persistent_null_child(
    semantic: SimpleNamespace,
    inventory: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = semantic
    waits: list[float] = []
    monkeypatch.setattr(scene.window, "get_attributes", lambda: {}, raising=False)
    monkeypatch.setattr(scene.window, "get_child_at_index", lambda _index: None)
    monkeypatch.setattr(accessibility, "sleep", waits.append, raising=False)
    reply = inventory.observe_controls(*FRAME[:2], "window-7")
    assert reply.status == "ancestry_inconsistent" and reply.controls == ()
    assert waits == [0.05, 0.05]
    assert scene.node.calls == [] and scene.owner.events == []


def test_delayed_export_is_revalidated_after_bounded_read_only_settling(
    semantic: SimpleNamespace,
    inventory: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = semantic
    ready = [False]
    monkeypatch.setattr(scene.window, "get_attributes", lambda: {}, raising=False)
    monkeypatch.setattr(
        scene.window,
        "get_child_at_index",
        lambda _index: scene.panel if ready[0] else None,
    )
    monkeypatch.setattr(
        accessibility,
        "sleep",
        lambda _duration: ready.__setitem__(0, True),
        raising=False,
    )
    reply = inventory.observe_controls(*FRAME[:2], "window-7")
    assert reply.status == "ok" and len(reply.controls) == 1
    assert scene.node.calls == [] and scene.owner.events == []


@pytest.mark.parametrize(
    "change", ["inactive", "disabled", "foreign", "wrong_parent", "negative_count"]
)
def test_export_request_never_waives_fresh_validation(
    semantic: SimpleNamespace,
    inventory: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    scene = semantic

    def attributes() -> dict[str, str]:
        if change == "inactive":
            scene.window.states.remove("ACTIVE")
        elif change == "disabled":
            scene.node.states.remove("ENABLED")
        elif change == "foreign":
            scene.node.pid = 99
        elif change == "wrong_parent":
            scene.node.parent = scene.window
        else:
            monkeypatch.setattr(scene.window, "get_child_count", lambda: -1)
        return {}

    monkeypatch.setattr(scene.window, "get_attributes", attributes, raising=False)
    reply = inventory.observe_controls(*FRAME[:2], "window-7")
    assert not reply.controls
    if change == "wrong_parent":
        assert reply.status == "ancestry_inconsistent"
    elif change == "negative_count":
        assert reply.status == "tree_incomplete"
    elif change == "inactive":
        assert reply.status == "window_ambiguous_or_inactive"
    else:
        assert reply.rejection_for("Settings") == "target_invalid"
    assert scene.node.calls == [] and scene.owner.events == []


@pytest.mark.parametrize(
    "bad_state",
    ["hidden", "not_showing", "disabled", "insensitive", "defunct", "stale"],
)
@pytest.mark.parametrize("where", ["node", "parent"])
def test_invalid_node_or_ancestry_cannot_dispatch(
    semantic: SimpleNamespace,
    bad_state: str,
    where: str,
) -> None:
    node = semantic.node if where == "node" else semantic.panel
    missing = {
        "hidden": "VISIBLE",
        "not_showing": "SHOWING",
        "disabled": "ENABLED",
        "insensitive": "SENSITIVE",
    }
    if bad_state in missing:
        node.states.remove(missing[bad_state])
    else:
        node.states.add(bad_state.upper())
    with pytest.raises(accessibility.ControlUnavailable):
        semantic.invoke()
    assert semantic.node.calls == []
    assert semantic.owner.events == []


def test_named_checkbox_repeated_state_requests_never_reverse_state(
    semantic: SimpleNamespace,
) -> None:
    semantic.node.name = "Test option"
    semantic.node.role = "CHECK_BOX"
    semantic.node.actions = ["toggle"]
    semantic.node.change_checked = True
    for desired in (True, False, True):
        before = len(semantic.node.calls)
        assert semantic.invoke(desired, label="Test option") == "STATE_CONFIRMED"
        assert ("CHECKED" in semantic.node.states) is desired
        assert semantic.invoke(desired, label="Test option") == "STATE_ALREADY_SET"
        assert ("CHECKED" in semantic.node.states) is desired
        assert len(semantic.node.calls) == before + 1


@pytest.mark.parametrize("relative", [False, True])
@pytest.mark.parametrize("desired", [False, True])
def test_directional_checkbox_actions_keep_requested_state_on_repeat(
    semantic: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    relative: bool,
    desired: bool,
) -> None:
    scene = semantic
    scene.node.name = "Test option"
    scene.node.role = "CHECK_BOX"
    scene.node.actions = ["focus", "dynamic"]
    scene.node.change_checked = True
    if not desired:
        scene.node.states.add("CHECKED")
    if relative:
        scene.window.bounds = scene.window.relative_bounds = (0, 0, 800, 600)
        scene.node.relative_bounds = (40, 80, 90, 20)

    def name(index: int) -> str:
        if index == 0:
            return "focus"
        return "uncheck" if "CHECKED" in scene.node.states else "check"

    monkeypatch.setattr(scene.node, "get_action_name", name)
    for requested in (desired, not desired, desired):
        before = len(scene.node.calls)
        assert scene.invoke(requested, label="Test option") == "STATE_CONFIRMED"
        assert ("CHECKED" in scene.node.states) is requested
        assert scene.invoke(requested, label="Test option") == "STATE_ALREADY_SET"
        assert len(scene.node.calls) == before + 1
    assert scene.node.calls == [1, 1, 1]


@pytest.mark.parametrize("checked", [False, True])
def test_directional_checkbox_click_uses_observed_opposite_state(
    semantic: SimpleNamespace,
    checked: bool,
) -> None:
    semantic.node.role = "CHECK_BOX"
    semantic.node.actions = ["focus", "uncheck" if checked else "check"]
    semantic.node.change_checked = True
    if checked:
        semantic.node.states.add("CHECKED")
    assert semantic.invoke() == "ACTION_DISPATCHED"
    assert ("CHECKED" in semantic.node.states) is not checked
    assert semantic.node.calls == [1]


@pytest.mark.parametrize("desired", [False, True, None])
@pytest.mark.parametrize("checked", [False, True])
def test_directional_action_cannot_run_in_wrong_direction(
    semantic: SimpleNamespace,
    desired: bool | None,
    checked: bool,
) -> None:
    semantic.node.role = "CHECK_BOX"
    semantic.node.actions = ["check" if checked else "uncheck"]
    if checked:
        semantic.node.states.add("CHECKED")
    if desired is checked:
        assert semantic.invoke(desired) == "STATE_ALREADY_SET"
    else:
        with pytest.raises(accessibility.ControlUnavailable):
            semantic.invoke(desired)
    assert semantic.node.calls == []


@pytest.mark.parametrize("actions", [["check", "toggle"], ["check", "check"]])
def test_directional_actions_preserve_unique_action_requirement(
    semantic: SimpleNamespace,
    actions: list[str],
) -> None:
    semantic.node.role = "CHECK_BOX"
    semantic.node.actions = actions
    with pytest.raises(accessibility.ControlUnavailable):
        semantic.invoke(True)
    assert semantic.node.calls == []


@pytest.mark.parametrize("desired", [False, True, None])
def test_directional_actions_require_readable_boolean_state(
    semantic: SimpleNamespace,
    desired: bool | None,
) -> None:
    # A plain button named like an action does not acquire checkbox semantics.
    semantic.node.actions = ["uncheck" if desired is False else "check"]
    if desired is None:
        with pytest.raises(accessibility.ControlUnavailable):
            semantic.invoke()
    else:
        assert semantic.invoke(desired) == "STATE_UNAVAILABLE"
    assert semantic.node.calls == []


@pytest.mark.parametrize("desired", [False, True])
def test_directional_pair_selects_only_requested_transition(
    semantic: SimpleNamespace,
    desired: bool,
) -> None:
    semantic.node.role = "CHECK_BOX"
    semantic.node.actions = ["focus", "uncheck", "check"]
    semantic.node.change_checked = True
    if not desired:
        semantic.node.states.add("CHECKED")
    assert semantic.invoke(desired) == "STATE_CONFIRMED"
    assert semantic.node.calls == [2 if desired else 1]


def test_directional_action_without_state_effect_remains_unverified(
    semantic: SimpleNamespace,
) -> None:
    semantic.node.role = "CHECK_BOX"
    semantic.node.actions = ["check"]
    assert semantic.invoke(True) == "ACTION_DISPATCHED"
    assert "CHECKED" not in semantic.node.states
    assert semantic.node.calls == [0]


def test_directional_action_is_revalidated_at_input_boundary(
    semantic: SimpleNamespace,
) -> None:
    semantic.node.role = "CHECK_BOX"
    semantic.node.actions = ["check"]
    original = semantic.owner.check

    def change(*, input_event: bool = False) -> None:
        original(input_event=input_event)
        if input_event:
            semantic.node.actions = ["uncheck"]

    semantic.owner.check = change
    with pytest.raises(accessibility.ControlUnavailable):
        semantic.invoke(True)
    assert semantic.node.calls == []


def test_absent_named_control_does_not_activate_same_prefix(
    semantic: SimpleNamespace,
) -> None:
    semantic.node.name = "Test"
    assert semantic.invoke(label="Test button") == "NO_ACCESSIBLE_ACTION"
    assert semantic.node.calls == []
    assert semantic.owner.events == []


def test_same_label_is_ambiguous_even_with_an_anchor(semantic: SimpleNamespace) -> None:
    semantic.panel.add(Node(bounds=(300, 80, 90, 20)))
    with pytest.raises(accessibility.ControlUnavailable):
        semantic.invoke()
    assert semantic.node.calls == []


@pytest.mark.parametrize(
    "change",
    ["token", "inactive", "bounds", "nested", "parent_link", "ambiguous_window"],
)
def test_other_window_or_inconsistent_parent_is_rejected(
    semantic: SimpleNamespace,
    change: str,
) -> None:
    if change == "token":
        semantic.token[0] = "window-8"
        assert semantic.invoke() == "TARGET_CHANGED:stale_or_window"
    else:
        if change == "inactive":
            semantic.window.states.remove("ACTIVE")
        elif change == "bounds":
            semantic.window.bounds = (900, 20, 800, 600)
        elif change == "nested":
            semantic.panel.role = "DIALOG"
        elif change == "parent_link":
            semantic.node.parent = semantic.window
        else:
            semantic.app.add(Node(role="DIALOG", states=NORMAL | {"ACTIVE"}))
        with pytest.raises(accessibility.ControlUnavailable):
            semantic.invoke()
    assert semantic.node.calls == []


@pytest.mark.parametrize("change", ["role", "ancestry", "reparent"])
def test_observed_structure_cannot_be_replaced(
    semantic: SimpleNamespace,
    change: str,
) -> None:
    target = accessibility.control_snapshot(
        semantic.desktop, 42, semantic.atspi, FRAME[2:6]
    )[0][1]
    if change == "role":
        semantic.node.role = "LINK"
    elif change == "ancestry":
        semantic.panel.name = "Another panel"
    else:
        semantic.panel.children.remove(semantic.node)
        semantic.window.add(semantic.node)
    with pytest.raises(accessibility.ControlUnavailable):
        semantic.invoke(target=target)
    assert semantic.node.calls == []


@pytest.mark.parametrize("actions", [None, []])
def test_only_missing_action_allows_coordinate_fallback(
    semantic: SimpleNamespace,
    actions: list[str] | None,
) -> None:
    semantic.node.actions = actions
    assert semantic.invoke() == "NO_ACCESSIBLE_ACTION"
    assert semantic.node.calls == []
    control = semantic.helper._accessible_control(
        "Settings",
        FRAME[2:6],
        42,
        near=None,
        state_required=False,
    )
    assert control is not None and control[3:] == (None, (85, 90))


@pytest.mark.parametrize("actions", [["show menu"], ["click", "press"]])
def test_unsupported_or_ambiguous_action_does_not_allow_click(
    semantic: SimpleNamespace,
    actions: list[str],
) -> None:
    semantic.node.actions = actions
    with pytest.raises(accessibility.ControlUnavailable):
        semantic.invoke()
    with pytest.raises(accessibility.ControlUnavailable):
        semantic.helper._accessible_control(
            "Settings",
            FRAME[2:6],
            42,
            near=None,
            state_required=False,
        )
    assert semantic.node.calls == []


@pytest.mark.parametrize("desired", [False, True])
@pytest.mark.parametrize("changes", [False, True])
def test_boolean_postcondition_is_read_after_action(
    semantic: SimpleNamespace,
    desired: bool,
    changes: bool,
) -> None:
    semantic.node.role = "CHECK_BOX"
    semantic.node.actions = ["show menu", "toggle"]
    semantic.node.change_checked = changes
    if not desired:
        semantic.node.states.add("CHECKED")
    assert semantic.invoke(desired) == (
        "STATE_CONFIRMED" if changes else "ACTION_DISPATCHED"
    )
    assert semantic.node.calls == [1]
    assert semantic.node.reads > 0


def test_already_set_and_indeterminate_states_are_distinct(
    semantic: SimpleNamespace,
) -> None:
    semantic.node.role = "SWITCH"
    semantic.node.states.add("CHECKED")
    assert semantic.invoke(True) == "STATE_ALREADY_SET"
    semantic.node.states.add("INDETERMINATE")
    assert semantic.invoke(True) == "STATE_UNAVAILABLE"
    assert semantic.node.calls == []


def test_false_invocation_is_never_retried_with_coordinates(
    semantic: SimpleNamespace,
) -> None:
    semantic.node.invoked = False
    assert semantic.invoke() == "ACTION_UNCONFIRMED"
    assert semantic.node.calls == [1]


def test_uncertain_invocation_reads_state_before_any_retry(
    semantic: SimpleNamespace,
) -> None:
    semantic.node.role = "SWITCH"
    semantic.node.actions = ["toggle"]
    semantic.node.invoked = False
    semantic.node.change_checked = True
    assert semantic.invoke(True) == "STATE_CONFIRMED"
    assert semantic.node.calls == [0]


def test_navigation_waits_for_exact_active_dialog(
    semantic: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def sleep(seconds: float) -> None:
        semantic.now[0] += seconds
        if semantic.now[0] >= 101.1 and "ACTIVE" in semantic.window.states:
            semantic.window.states.remove("ACTIVE")
            semantic.app.add(
                Node(role="DIALOG", name="Settings", states=NORMAL | {"ACTIVE"})
            )
            semantic.token[0] = "settings-dialog"

    monkeypatch.setattr(semantic.helper, "sleep", sleep)
    assert semantic.invoke() == "NAVIGATION_CONFIRMED"
    assert semantic.node.calls == [1]


def test_expiry_and_owner_revocation_prevent_action(semantic: SimpleNamespace) -> None:
    semantic.now[0] = 110
    assert semantic.invoke() == "TARGET_CHANGED:stale_or_window"
    semantic.now[0] = 101
    semantic.owner.revoked = True
    with pytest.raises(OperationStopped):
        semantic.invoke()
    assert semantic.node.calls == []


def test_window_switch_during_owner_check_prevents_action(
    semantic: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def check(**_kw: object) -> None:
        semantic.token[0] = "window-8"

    monkeypatch.setattr(semantic.owner, "check", check)
    assert semantic.invoke() == "TARGET_CHANGED:stale_or_window"
    assert semantic.node.calls == []


def test_post_dispatch_disappearance_is_unknown(
    semantic: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic.node.role = "CHECK_BOX"
    semantic.node.actions = ["toggle"]

    def invoke(_index: int) -> bool:
        semantic.node.states.add("DEFUNCT")
        return True

    monkeypatch.setattr(semantic.node, "do_action", invoke)
    assert semantic.invoke(True) == "ACTION_DISPATCHED"


def test_coordinate_path_rejects_action_appearing_after_probe(
    semantic: SimpleNamespace,
) -> None:
    with pytest.raises(accessibility.ControlUnavailable):
        semantic.helper._accessible_control(
            "Settings",
            FRAME[2:6],
            42,
            near=None,
            state_required=False,
        )
    assert semantic.node.calls == []


@pytest.mark.parametrize(
    "marker,expected",
    [
        ("ACTION_DISPATCHED", ActionOutcome.DISPATCHED_UNVERIFIED),
        ("STATE_CONFIRMED", ActionOutcome.CONFIRMED),
        ("ACTION_UNCONFIRMED", ActionOutcome.UNKNOWN),
        ("TARGET_UNCERTAIN", ActionOutcome.FAILED),
    ],
)
@pytest.mark.parametrize("with_ocr", [False, True])
def test_executor_result_contract_and_owner(
    monkeypatch: pytest.MonkeyPatch,
    marker: str,
    expected: ActionOutcome,
    with_ocr: bool,
) -> None:
    class Delegate:
        def execute(self, request: ActionRequest) -> ActionResult:
            pytest.fail("visible control must not delegate")

    class OffVerifier:
        def ready(self) -> bool:
            pytest.fail("semantic dispatch must not consult OCR")

        def find_visible_control(self, *_a: object) -> None:
            pytest.fail("semantic dispatch must not capture")

    broker = DesktopInputBroker()
    now = monotonic()
    target = AccessibilityTarget(((0, "FRAME", "Main"), (0, "BUTTON", "Settings")))
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL,
            "Settings",
            control_source="accessibility",
            control_accessibility=target,
            control_observation=WindowObservation(
                "example.desktop", 42, "window-7", "one", now, now + 10
            ),
        ),
    )
    calls = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert args[2] == "semantic"
        assert AccessibilityTarget.from_json(args[-1]) == target
        assert kwargs["helper"] is True and current_operation() is not None
        assert broker._owner is not None
        calls.append(args)
        return subprocess.CompletedProcess(
            args, 0 if marker != "TARGET_UNCERTAIN" else 2, marker, ""
        )

    monkeypatch.setattr(desktop_control, "run_process", run)
    executor = DesktopInputExecutor(
        desktop_control.DesktopControlExecutor(
            Delegate(),
            identity_reader=lambda: FRAME[:2],
            token_reader=lambda: "window-7",
            verifier=OffVerifier() if with_ocr else None,
        ),
        broker,
    )
    assert executor.execute(request).outcome is expected
    assert len(calls) == 1 and broker._owner is None
    broker.close()


def test_target_serialization_and_command_contract() -> None:
    target = AccessibilityTarget(((0, "FRAME", "Main"), (1, "BUTTON", "Settings")))
    assert AccessibilityTarget.from_json(target.to_json()) == target
    with pytest.raises(ValueError):
        AccessibilityTarget.from_json('[[true,"BUTTON","Settings"]]')
    with pytest.raises(ValueError):
        CommandIntent(CommandKind.OPEN_APP, "Settings", control_accessibility=target)
    with pytest.raises(ValueError):
        replace(
            CommandIntent(CommandKind.VISIBLE_CONTROL, "Settings"),
            control_accessibility=target,
        )


def test_state_change_during_owner_check_prevents_action(
    semantic: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def check(*, input_event: bool = False) -> None:
        if input_event:
            semantic.node.states.remove("ENABLED")

    monkeypatch.setattr(semantic.owner, "check", check)
    with pytest.raises(accessibility.ControlUnavailable):
        semantic.invoke()
    assert semantic.node.calls == []


@pytest.fixture
def inventory(
    semantic: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> ModuleType:
    # Use the actual read-only helper, without touching the session bus.
    gi = sys.modules["gi"]
    monkeypatch.setattr(gi, "require_version", lambda *_a: None, raising=False)
    repository = sys.modules["gi.repository"]
    monkeypatch.setattr(repository, "Atspi", semantic.atspi, raising=False)
    path = Path(desktop_control.__file__).with_name(
        "desktop_accessibility_inventory.py"
    )
    spec = importlib.util.spec_from_file_location("accessible_inventory_test", path)
    assert spec is not None and spec.loader is not None
    inventory = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inventory)
    monkeypatch.setattr(inventory, "_focused_identity", lambda: FRAME[:2])
    monkeypatch.setattr(inventory, "_focused_window_token", lambda: "window-7")
    monkeypatch.setattr(inventory, "_window_and_pointer", lambda: FRAME)
    monkeypatch.setattr(inventory, "probe_missing_child", lambda *_args: {})
    return inventory


def test_inventory_uses_same_resolver_and_keeps_structure_without_coordinates(
    semantic: SimpleNamespace,
    inventory: ModuleType,
) -> None:
    semantic.node.bounds = None
    semantic.panel.add(Node(name="Hidden", states=NORMAL - {"VISIBLE"}))
    semantic.panel.add(Node(name="Dead", states=NORMAL | {"DEFUNCT"}))
    semantic.panel.add(Node(name="Disabled", states=NORMAL - {"ENABLED"}))
    semantic.panel.add(Node(name="Duplicate"))
    semantic.panel.add(Node(name="Duplicate"))
    controls = inventory.list_controls(*FRAME[:2], "window-7")
    assert len(controls) == 1
    control = controls[0]
    assert control["label"] == "Settings" and control["x"] is control["y"] is None
    structure = AccessibilityTarget.from_json(control["accessibility"])
    assert structure.ancestry[-1][1:] == ("BUTTON", "Settings")
    assert semantic.invoke(target=structure) == "ACTION_DISPATCHED"


def test_structured_inventory_preserves_invalid_and_ambiguous_evidence(
    semantic: SimpleNamespace,
    inventory: ModuleType,
) -> None:
    from kyrin.actions.platforms.control_inventory_protocol import ControlInventoryReply

    semantic.panel.add(Node(name="Disabled", states=NORMAL - {"ENABLED"}))
    semantic.panel.add(Node(name="Duplicate"))
    semantic.panel.add(Node(name="Duplicate", states=NORMAL - {"VISIBLE"}))
    reply = inventory.observe_controls(*FRAME[:2], "window-7")
    decoded = ControlInventoryReply.from_output(reply.to_json(), 0)
    assert decoded.status == "ok"
    assert [item["label"] for item in decoded.controls] == ["Settings"]
    assert decoded.rejection_for("disabled") == "target_invalid"
    assert decoded.rejection_for("Duplicate") == "target_ambiguous"
    assert semantic.node.calls == [] and semantic.owner.events == []


@pytest.mark.parametrize(
    "issue,status",
    [
        ("inactive", "window_ambiguous_or_inactive"),
        ("bounds", "window_bounds_mismatch"),
        ("children", "tree_incomplete"),
        ("unexported", "application_not_exported"),
    ],
)
def test_real_inventory_returns_stage_instead_of_empty_list(
    semantic: SimpleNamespace,
    inventory: ModuleType,
    issue: str,
    status: str,
) -> None:
    if issue == "inactive":
        semantic.window.states.remove("ACTIVE")
    elif issue == "bounds":
        semantic.window.bounds = (900, 20, 800, 600)
    elif issue == "children":
        for _ in range(201):
            semantic.panel.add(Node())
    else:
        semantic.app.pid = 99
    reply = inventory.observe_controls(*FRAME[:2], "window-7")
    assert reply.status == status and reply.controls == ()


def test_semantic_cli_preserves_observation_failure_and_closes_owner(
    semantic: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    closed = []
    lifetime = SimpleNamespace(
        check=semantic.owner.check, close=lambda: closed.append(True)
    )
    monkeypatch.setattr(
        semantic.helper, "shared_session", lambda _devices: (lifetime, "/live")
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "helper.py",
            "semantic",
            "example.desktop",
            "42",
            "click",
            "Settings",
            semantic.observation.to_json(),
        ],
    )
    semantic.window.states.remove("ACTIVE")
    assert semantic.helper.main() == 2
    assert (
        capsys.readouterr().out.strip()
        == "OBSERVATION_FAILED:window_ambiguous_or_inactive"
    )
    assert closed == [True] and semantic.node.calls == []


def test_diagnostic_uses_real_resolver_without_disclosing_unrequested_names(
    semantic: SimpleNamespace,
    inventory: ModuleType,
) -> None:
    import json

    semantic.node.name = "Private unrelated label"
    semantic.panel.add(Node(name="Test button"))
    semantic.panel.add(Node(name="Test option", role="CHECK_BOX"))
    report = inventory.diagnose_controls(["Test button", "Test option", "Absent"])
    assert report["status"] == "ok"
    assert report["scan"]["matching_applications"] == 1
    assert report["scan"]["active_windows"] == 1
    assert report["scan"]["named_controls"] == 3
    assert [item["matches"] for item in report["requested"]] == [1, 1, 0]
    assert report["requested"][1]["controls"][0]["checked"] is False
    assert "Private unrelated label" not in json.dumps(report)
    assert "Main" not in json.dumps(report)
    assert "window-7" not in json.dumps(report)
    assert semantic.node.calls == [] and semantic.owner.events == []


def test_action_diagnostic_reveals_only_fixed_names_for_requested_controls(
    semantic: SimpleNamespace,
    inventory: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    semantic.node.actions = ["Private custom action", "check", "uncheck"]
    unrelated = semantic.panel.add(Node(name="Unrequested private control"))

    def forbidden() -> None:
        pytest.fail("unrequested control capabilities must not be queried")

    monkeypatch.setattr(unrelated, "get_action_iface", forbidden)
    report = inventory.diagnose_controls(["Settings"])
    actions = report["requested"][0]["controls"][0]["actions"]
    assert actions == {
        "status": "ok",
        "count": 3,
        "known": [{"name": "check", "index": 1}, {"name": "uncheck", "index": 2}],
        "other_count": 1,
    }
    assert "Private" not in json.dumps(report)
    assert "Unrequested" not in json.dumps(report)
    assert semantic.node.calls == [] and semantic.owner.events == []


@pytest.mark.parametrize("issue", ["absent", "error", "limit", "negative"])
def test_action_diagnostic_bounds_and_sanitizes_capability_failure(
    semantic: SimpleNamespace,
    inventory: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    issue: str,
) -> None:
    if issue == "absent":
        semantic.node.actions = None
    elif issue == "error":

        def fail(_index: int) -> None:
            raise RuntimeError("Private error content")

        monkeypatch.setattr(semantic.node, "get_action_name", fail)
    else:
        monkeypatch.setattr(
            semantic.node, "get_n_actions", lambda: 65 if issue == "limit" else -1
        )
    report = inventory.diagnose_controls(["Settings"])
    assert report["status"] == "ok"
    actions = report["requested"][0]["controls"][0]["actions"]
    assert actions == {
        "status": "absent"
        if issue == "absent"
        else "unavailable"
        if issue == "error"
        else "invalid"
    }
    assert "Private" not in str(report)
    assert semantic.node.calls == []


@pytest.mark.parametrize(
    "issue", ["duplicate", "disabled", "hidden", "indeterminate", "ancestor"]
)
def test_diagnostic_distinguishes_unusable_control_evidence(
    semantic: SimpleNamespace,
    inventory: ModuleType,
    issue: str,
) -> None:
    if issue == "duplicate":
        semantic.panel.add(Node())
    elif issue == "disabled":
        semantic.node.states.remove("ENABLED")
    elif issue == "hidden":
        semantic.node.states.remove("VISIBLE")
    elif issue == "ancestor":
        semantic.panel.states.remove("SENSITIVE")
    else:
        semantic.node.role = "CHECK_BOX"
        semantic.node.states.add("INDETERMINATE")
    report = inventory.diagnose_controls(["Settings"])
    assert report["status"] == "ok"
    (item,) = report["requested"]
    if issue == "duplicate":
        assert item["matches"] == 2
    elif issue == "indeterminate":
        assert item["controls"][0]["checked"] is None
    else:
        assert item["controls"][0]["valid"] is False
    assert semantic.node.calls == []


@pytest.mark.parametrize(
    "issue", ["unexported", "inactive", "limit", "focus", "transport"]
)
def test_diagnostic_reports_scan_failure_separately_from_missing_name(
    semantic: SimpleNamespace,
    inventory: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    issue: str,
) -> None:
    expected = "scan_rejected"
    if issue == "unexported":
        semantic.app.pid = 99
        expected = "application_not_exported"
    elif issue == "inactive":
        semantic.window.states.remove("ACTIVE")
    elif issue == "limit":
        for _ in range(201):
            semantic.panel.add(Node())
    elif issue == "transport":

        def fail(_index: int) -> None:
            raise RuntimeError("Private transport message")

        monkeypatch.setattr(semantic.atspi, "get_desktop", fail)
        expected = "accessibility_error"
    else:
        tokens = iter(("window-7", "window-8"))
        monkeypatch.setattr(inventory, "_focused_window_token", lambda: next(tokens))
        expected = "focus_changed"
    report = inventory.diagnose_controls(["Settings"])
    assert report["status"] == expected
    assert "requested" not in report or issue == "unexported"
    assert "Private" not in str(report)


@pytest.mark.parametrize(
    "bounds,fits,edges",
    [
        ((10, 20, 800, 600), True, (0, 0, 0, 0)),
        ((12, 44, 796, 572), True, (2, 24, -2, -4)),
        ((0, 0, 800, 600), False, (-10, -20, -10, -20)),
        ((9, 19, 802, 602), False, (-1, -1, 1, 1)),
        ((20, 40, 1600, 1200), False, (10, 20, 810, 620)),
        ((900, 20, 800, 600), False, (890, 0, 890, 0)),
        ((10, 20, 0, 600), False, (0, 0, -800, 0)),
    ],
)
def test_opt_in_geometry_measures_guard_without_changing_its_decision(
    semantic: SimpleNamespace,
    inventory: ModuleType,
    bounds: tuple[int, int, int, int],
    fits: bool,
    edges: tuple[int, int, int, int],
) -> None:
    semantic.window.bounds = bounds
    default = inventory.diagnose_controls(["Settings"])
    detailed = inventory.diagnose_controls(["Settings"], include_geometry=True)
    assert "geometry" not in default
    measured = detailed.pop("geometry")
    assert detailed == default
    assert measured == {
        "coordinate_type": "screen",
        "focused_frame": {"x": 10, "y": 20, "width": 800, "height": 600},
        "accessible_window": dict(
            zip(("x", "y", "width", "height"), bounds, strict=True)
        ),
        "edge_delta": dict(zip(("left", "top", "right", "bottom"), edges, strict=True)),
        "fits_focused_frame": fits,
    }
    assert detailed["status"] == ("ok" if fits else "scan_rejected")
    if not fits:
        assert detailed["reason_code"] == "window_bounds_mismatch"
        assert "requested" not in detailed
    assert "Main" not in str(measured) and "window-7" not in str(measured)
    assert semantic.node.calls == [] and semantic.owner.events == []


def test_focus_change_during_rejected_scan_is_not_reported_as_stable_bounds_error(
    semantic: SimpleNamespace,
    inventory: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic.window.bounds = (0, 0, 800, 600)
    tokens = iter(("window-7", "window-8"))
    monkeypatch.setattr(inventory, "_focused_window_token", lambda: next(tokens))
    report = inventory.diagnose_controls([], include_geometry=True)
    assert report["status"] == "focus_changed"
    assert "reason_code" not in report and "requested" not in report
    assert semantic.node.calls == []


@pytest.mark.parametrize("missing", ["child", "parent", "different_parent"])
def test_ancestry_diagnostic_identifies_rejected_edge_without_names(
    semantic: SimpleNamespace,
    inventory: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    scene = semantic
    scene.node.name = "Private label"
    if missing == "child":
        monkeypatch.setattr(scene.panel, "get_child_at_index", lambda _index: None)
    elif missing == "parent":
        scene.node.parent = None
    else:
        scene.node.parent = scene.window
    report = inventory.diagnose_controls([])
    assert report["status"] == "scan_rejected"
    assert report["reason_code"] == "ancestry_inconsistent"
    metrics = report["scan"]
    assert metrics["ancestry_failing_depth"] == 2
    assert metrics["ancestry_child_index"] == 0
    assert metrics["ancestry_child_missing"] == int(missing == "child")
    if missing != "child":
        assert metrics["ancestry_parent_missing"] == int(missing == "parent")
        assert metrics["ancestry_fresh_parent_matches"] == 0
        assert metrics["ancestry_fresh_parent_missing"] == int(missing == "parent")
    assert "Private" not in str(report) and "Main" not in str(report)
    assert "requested" not in report
    assert scene.node.calls == [] and scene.owner.events == []


def test_ancestry_cache_probe_does_not_authorize_partial_snapshot(
    semantic: SimpleNamespace,
    inventory: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = semantic
    scene.node.parent = None

    def refresh() -> None:
        scene.node.parent = scene.panel

    monkeypatch.setattr(scene.node, "clear_cache", refresh)
    report = inventory.diagnose_controls([])
    assert report["status"] == "scan_rejected"
    assert report["reason_code"] == "ancestry_inconsistent"
    assert report["scan"]["ancestry_parent_missing"] == 1
    assert report["scan"]["ancestry_fresh_parent_matches"] == 1
    assert "requested" not in report
    assert scene.node.calls == [] and scene.owner.events == []


def test_missing_root_child_is_probed_but_partial_snapshot_stays_rejected(
    relative_semantic: SimpleNamespace,
    inventory: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = relative_semantic
    reads = [0]

    def child(_index: int) -> Node | None:
        reads[0] += 1
        return None if reads[0] == 1 else scene.panel

    def wire_probe(node: Node, index: int) -> dict[str, int]:
        assert node is scene.window and index == 0
        return {"wire_child_is_null": 0}

    monkeypatch.setattr(scene.window, "get_child_at_index", child)
    monkeypatch.setattr(inventory, "probe_missing_child", wire_probe)
    report = inventory.diagnose_controls([], include_geometry=True)
    assert report["status"] == "scan_rejected"
    assert report["reason_code"] == "ancestry_inconsistent"
    metrics = report["scan"]
    assert metrics["nodes_inspected"] == 1
    assert metrics["ancestry_declared_child_count"] == 1
    assert metrics["ancestry_child_missing"] == 1
    assert metrics["ancestry_fresh_child_missing"] == 0
    assert metrics["ancestry_fresh_child_parent_matches"] == 1
    assert metrics["wire_child_is_null"] == 0
    assert report["geometry"]["coordinate_binding"] == "window_relative_semantic_only"
    assert "requested" not in report
    assert scene.node.calls == [] and scene.owner.events == []


def test_missing_child_execution_does_not_run_diagnostic_wire_probe(
    semantic: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = semantic
    monkeypatch.setattr(scene.window, "get_child_at_index", lambda _index: None)
    with pytest.raises(accessibility.ControlUnavailable):
        accessibility.control_snapshot(
            scene.desktop,
            42,
            scene.atspi,
            FRAME[2:6],
            child_probe=lambda *_args: pytest.fail("execution must not run wire probe"),
        )
    assert scene.node.calls == [] and scene.owner.events == []


@pytest.mark.parametrize("same_reference", [False, True])
def test_ancestry_reference_comparison_is_diagnostic_and_never_exports_endpoints(
    semantic: SimpleNamespace,
    inventory: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    same_reference: bool,
) -> None:
    scene = semantic
    other = Node(role="PANEL", name="Private other parent")
    scene.node.parent = other
    for node in (scene.panel, other):
        monkeypatch.setattr(node, "path", "/private/endpoint", raising=False)
        monkeypatch.setattr(
            node, "app", SimpleNamespace(bus_name=":private-owner"), raising=False
        )
    if not same_reference:
        monkeypatch.setattr(other, "path", "/private/different", raising=False)
    report = inventory.diagnose_controls([])
    assert report["status"] == "scan_rejected"
    assert report["scan"]["ancestry_parent_same_reference"] == int(same_reference)
    assert "private" not in str(report).lower()
    assert scene.node.calls == [] and scene.owner.events == []


def test_failed_ancestry_probe_keeps_original_rejection_and_hides_transport_error(
    semantic: SimpleNamespace,
    inventory: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = semantic
    scene.node.parent = None

    def fail() -> None:
        raise RuntimeError("Private transport endpoint")

    monkeypatch.setattr(scene.node, "clear_cache", fail)
    report = inventory.diagnose_controls([])
    assert report["status"] == "scan_rejected"
    assert report["reason_code"] == "ancestry_inconsistent"
    assert report["scan"]["ancestry_probe_failed"] == 1
    assert "Private" not in str(report) and "requested" not in report
    assert scene.node.calls == [] and scene.owner.events == []


def test_no_action_fallback_retains_same_input_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kyrin.actions.visible_control import VisibleControlTarget
    from kyrin.vision.capture_geometry import CaptureGeometry

    class Delegate:
        def execute(self, request: ActionRequest) -> ActionResult:
            pytest.fail("control must not delegate")

    broker = DesktopInputBroker()
    now = monotonic()
    geometry = CaptureGeometry(
        "logical_desktop",
        0,
        (10, 20, 800, 600),
        (800, 600),
        1,
        1,
        (0, 0, 0, 0),
        (0, 0),
        (1, 1),
        "window-7",
        "capture-1",
        now,
        (10, 20, 800, 600),
    )
    calls = []
    owners = []

    class Verifier:
        def ready(self) -> bool:
            return True

        def find_visible_control(self, *_args: object) -> VisibleControlTarget:
            calls.append("ocr")
            owners.append(broker._owner)
            return VisibleControlTarget(40, 80, 90, 20, 800, 600, geometry=geometry)

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert kwargs["helper"] is True and current_operation() is not None
        owners.append(broker._owner)
        semantic = args[2] == "semantic"
        calls.append("semantic" if semantic else "pointer")
        return subprocess.CompletedProcess(
            args, 0, "NO_ACCESSIBLE_ACTION" if semantic else "CLICK_DISPATCHED", ""
        )

    monkeypatch.setattr(desktop_control, "run_process", run)
    request = ActionRequest(
        ActionKey(0, 1),
        CommandIntent(
            CommandKind.VISIBLE_CONTROL,
            "Settings",
            control_observation=WindowObservation(
                "example.desktop",
                42,
                "window-7",
                "one",
                now,
                now + 10,
            ),
        ),
    )
    executor = DesktopInputExecutor(
        desktop_control.DesktopControlExecutor(
            Delegate(),
            identity_reader=lambda: FRAME[:2],
            token_reader=lambda: "window-7",
            verifier=Verifier(),
        ),
        broker,
    )
    assert executor.execute(request).outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert calls == ["semantic", "ocr", "pointer"]
    assert owners[0] is not None and owners == [owners[0]] * 3
    assert broker._owner is None
    broker.close()


@pytest.mark.parametrize("change", ["none", "hidden", "disabled", "action"])
def test_coordinate_fallback_rechecks_node_after_pointer_motion(
    semantic: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    semantic.node.actions = None
    pointer = [FRAME]
    calls: list[str] = []
    helper = semantic.helper
    monkeypatch.setattr(helper, "_window_and_pointer", lambda: pointer[0])
    helper.Gio.DBusCallFlags = SimpleNamespace(NONE=0)
    helper.GLib.Variant = lambda _signature, value: value

    def wait(*_args: object) -> bool:
        pointer[0] = (*FRAME[:6], 85, 90)
        if change == "hidden":
            semantic.node.states.remove("VISIBLE")
        elif change == "disabled":
            semantic.node.states.remove("ENABLED")
        elif change == "action":
            semantic.node.actions = ["click"]
        return True

    def call(_bus: str, _path: str, _iface: str, method: str, *_a: object) -> None:
        calls.append(method)

    monkeypatch.setattr(helper, "_wait_for_pointer", wait)

    def click() -> str:
        result = helper._click(
            SimpleNamespace(call_sync=call),
            "/session",
            FRAME[:2],
            (0, 0, 0, 0, 0, 0),
            "Settings",
            None,
            True,
            None,
            observation=semantic.observation,
        )
        assert isinstance(result, str)
        return result

    if change == "none":
        assert click() == "CLICK_DISPATCHED"
        assert calls == [
            "NotifyPointerMotion",
            "NotifyPointerButton",
            "NotifyPointerButton",
        ]
    else:
        with pytest.raises(accessibility.ControlUnavailable):
            click()
        assert calls == ["NotifyPointerMotion"]


def test_semantic_cli_borrows_owner_without_new_portal_connection(
    semantic: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    closed = []
    lifetime = SimpleNamespace(
        check=semantic.owner.check, close=lambda: closed.append(True)
    )
    monkeypatch.setattr(
        semantic.helper, "shared_session", lambda _devices: (lifetime, "/live")
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "helper.py",
            "semantic",
            "example.desktop",
            "42",
            "click",
            "Settings",
            semantic.observation.to_json(),
        ],
    )
    # Gio.bus_get_sync is deliberately absent from this fixture.
    assert semantic.helper.main() == 0
    assert capsys.readouterr().out.strip() == "ACTION_DISPATCHED"
    assert semantic.node.calls == [1] and closed == [True]


@pytest.mark.parametrize("role,title", [("DIALOG", "Other"), ("FRAME", "Settings")])
def test_navigation_noop_or_wrong_destination_stays_unverified(
    semantic: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    title: str,
) -> None:
    def invoke(index: int) -> bool:
        semantic.node.calls.append(index)
        semantic.window.states.remove("ACTIVE")
        semantic.app.add(Node(role=role, name=title, states=NORMAL | {"ACTIVE"}))
        return True

    monkeypatch.setattr(semantic.node, "do_action", invoke)
    assert semantic.invoke() == "ACTION_DISPATCHED"
    assert semantic.node.calls == [1]


def test_preexisting_dialog_is_not_proof_of_a_click(semantic: SimpleNamespace) -> None:
    semantic.window.role = "DIALOG"
    semantic.window.name = "Settings"
    assert semantic.invoke() == "ACTION_DISPATCHED"
    assert semantic.node.calls == [1]


@pytest.mark.parametrize(
    "already_set,changes", [(True, False), (False, True), (False, False)]
)
def test_coordinate_toggle_reads_boolean_postcondition(
    semantic: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    already_set: bool,
    changes: bool,
) -> None:
    semantic.node.role = "SWITCH"
    semantic.node.actions = None
    if already_set:
        semantic.node.states.add("CHECKED")
    pointer = [0, 0]
    events: list[str] = []
    monkeypatch.setattr(
        semantic.helper, "_window_and_pointer", lambda: (*FRAME[:6], *pointer)
    )
    semantic.helper.GLib.Variant = lambda _signature, value: value
    semantic.helper.Gio.DBusCallFlags = SimpleNamespace(NONE=0)

    class Bus:
        def call_sync(
            self,
            _bus: Any,
            _obj: Any,
            _iface: Any,
            method: str,
            arguments: Any,
            *_rest: Any,
        ) -> None:
            events.append(method)
            if method == "NotifyPointerMotion":
                pointer[:] = [85, 90]
            elif arguments[-1] == 0 and changes:
                semantic.node.states.add("CHECKED")

    result = semantic.helper._click(
        Bus(),
        "/session",
        FRAME[:2],
        (0, 0, 0, 0, 0, 0),
        "Settings",
        True,
        True,
        None,
        observation=semantic.observation,
    )
    assert result == (
        "STATE_ALREADY_SET"
        if already_set
        else "STATE_CONFIRMED"
        if changes
        else "CLICK_DISPATCHED"
    )
    assert events == (
        []
        if already_set
        else [
            "NotifyPointerMotion",
            "NotifyPointerButton",
            "NotifyPointerButton",
        ]
    )


def test_replaced_toggle_cannot_supply_original_postcondition(
    semantic: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic.node.role = "SWITCH"
    semantic.node.actions = ["toggle"]

    def invoke(index: int) -> bool:
        semantic.node.calls.append(index)
        semantic.panel.children.clear()
        semantic.panel.add(Node(role="SWITCH", states=NORMAL | {"CHECKED"}))
        return True

    monkeypatch.setattr(semantic.node, "do_action", invoke)
    assert semantic.invoke(True) == "ACTION_DISPATCHED"
    assert semantic.node.calls == [0]


@pytest.mark.parametrize("desired", [None, True])
def test_postcondition_read_finishing_after_settle_deadline_is_unverified(
    semantic: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    desired: bool | None,
) -> None:
    if desired is None:

        def navigation(*_args: object) -> bool:
            semantic.now[0] += 0.5
            return True

        monkeypatch.setattr(semantic.helper, "_navigation_confirmed", navigation)
    else:
        semantic.node.role = "SWITCH"
        semantic.node.states.add("CHECKED")
        control = accessibility.control_snapshot(
            semantic.desktop, 42, semantic.atspi, FRAME[2:6]
        )[0]

        def resolve(*_args: object) -> accessibility.Control:
            semantic.now[0] += 0.5
            return control

        monkeypatch.setattr(semantic.helper, "resolve_control", resolve)
    assert (
        semantic.helper._control_postcondition(
            FRAME[:2],
            "Settings",
            desired,
            semantic.observation,
            None,
            semantic.owner,
            expected_node=semantic.node,
        )
        is None
    )
    assert semantic.node.calls == []


@pytest.mark.parametrize("change", ["position", "state"])
def test_semantic_action_checks_approved_target_again_at_input_boundary(
    semantic: SimpleNamespace,
    change: str,
) -> None:
    # Exact window-relative center and checked state from the consent snapshot.
    consent = (75, 70, None)
    if change == "position":
        semantic.node.bounds = (41, 80, 90, 20)
    else:
        semantic.node.role = "CHECK_BOX"
    result = semantic.helper._semantic_control(
        FRAME[:2],
        "Settings",
        None,
        semantic.observation,
        semantic.owner,
        None,
        consent,
    )
    assert result == "TARGET_UNCERTAIN"
    assert semantic.node.calls == []


def test_consent_target_cannot_move_while_input_owner_authorizes(
    semantic: SimpleNamespace,
) -> None:
    original = semantic.owner.check

    def change(*, input_event: bool = False) -> None:
        original(input_event=input_event)
        if input_event:
            semantic.node.bounds = (41, 80, 90, 20)

    semantic.owner.check = change
    result = semantic.helper._semantic_control(
        FRAME[:2],
        "Settings",
        None,
        semantic.observation,
        semantic.owner,
        None,
        (75, 70, None),
    )
    assert result == "TARGET_UNCERTAIN"
    assert semantic.node.calls == []
