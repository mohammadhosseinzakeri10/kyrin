"""Telegram's real live locator and batch editing against a mutable fake UI."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from kyrin.actions.platforms.desktop_accessibility import ControlUnavailable
from kyrin.operations import OperationStopped
from tests.actions.test_telegram_portal_focus import helper as helper  # noqa: F401

NORMAL = {"VISIBLE", "SHOWING", "ENABLED", "SENSITIVE"}
EXPECTED = ("org.telegram.desktop", 42)


@dataclass(eq=False)
class Node:
    role: str
    name: str = ""
    states: set[str] = field(default_factory=lambda: set(NORMAL))
    bounds: tuple[int, int, int, int] = (0, 0, 1600, 900)
    pid: int = 42
    parent: Any = None
    children: list[Node] = field(default_factory=list)
    text: str = "old query"
    edits: list[str] = field(default_factory=list)
    on_edit: Callable[[], None] = lambda: None
    clicks: list[int] = field(default_factory=list)
    accepted: bool = True
    toolkit: str = ""
    action_names: tuple[str, ...] = ("show info", "press")
    on_action: Callable[[], None] = lambda: None

    def get_toolkit_name(self) -> str:
        return self.toolkit

    def add(self, child: Node) -> Node:
        child.parent = self
        self.children.append(child)
        return child

    def get_child_count(self) -> int:
        return len(self.children)

    def get_child_at_index(self, index: int) -> Node:
        return self.children[index]

    def get_parent(self) -> Any:
        return self.parent

    def get_index_in_parent(self) -> int:
        return self.parent.children.index(self) if self.parent else 0

    def get_process_id(self) -> int:
        return self.pid

    def get_role(self) -> str:
        return self.role

    def get_name(self) -> str:
        return self.name

    def clear_cache(self) -> None:
        pass

    def get_state_set(self) -> Node:
        return self

    def contains(self, state: str) -> bool:
        return state in self.states

    def get_component_iface(self) -> Node:
        return self

    def get_extents(self, _coord: str) -> SimpleNamespace:
        return SimpleNamespace(
            **dict(zip(("x", "y", "width", "height"), self.bounds, strict=True))
        )

    def grab_focus(self) -> bool:
        self.states.add("FOCUSED")
        return self.accepted

    def get_editable_text_iface(self) -> Node:
        return self

    def get_text_iface(self) -> Node:
        return self

    def get_text(self, start: int, end: int) -> str:
        assert (start, end) == (0, -1)
        return self.text

    def set_text_contents(self, value: str) -> bool:
        if self.accepted:
            self.text = value
        return self.accepted

    def insert_text(self, position: int, value: str, length: int) -> bool:
        assert length == len(value.encode("utf-8"))
        if self.accepted:
            self.text = self.text[:position] + value + self.text[position:]
            self.edits.append(value)
            self.on_edit()
        return self.accepted

    def get_action_iface(self) -> Node:
        return self

    def get_n_actions(self) -> int:
        return len(self.action_names)

    def get_action_name(self, index: int) -> str:
        return self.action_names[index]

    def do_action(self, index: int) -> bool:
        self.clicks.append(index)
        if self.action_names[index].casefold() == "setfocus" and self.accepted:
            self.states.add("FOCUSED")
        self.on_action()
        return self.accepted


@dataclass
class Owner:
    stopped: bool = False
    checks: int = 0

    def check(self, *, input_event: bool = False) -> None:
        if self.stopped:
            raise OperationStopped("owner cancelled or permission revoked")
        self.checks += int(input_event)

    def close(self) -> None:
        pass


@pytest.fixture
def ui(helper: ModuleType, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    desktop = Node("DESKTOP")
    app = desktop.add(Node("APPLICATION"))
    window = app.add(Node("FRAME", "Telegram", NORMAL | {"ACTIVE"}))
    panel = window.add(Node("PANEL", "Chat list"))
    menu = panel.add(Node("PUSH_BUTTON_MENU", "Main menu", bounds=(14, 26, 28, 32)))
    search = panel.add(
        Node("ENTRY", "Search", NORMAL | {"EDITABLE"}, (60, 30, 300, 40))
    )
    composer = window.add(Node("ENTRY", "Message", NORMAL | {"EDITABLE"}))
    roles = (
        "FRAME", "WINDOW", "DIALOG", "BUTTON", "PUSH_BUTTON_MENU", "ENTRY", "TEXT",
        "FILLER",
    )
    states = (*NORMAL, "ACTIVE", "FOCUSED", "EDITABLE", "DEFUNCT", "STALE", "INVALID")
    atspi = SimpleNamespace(
        Role=SimpleNamespace(**dict(zip(roles, roles, strict=True))),
        StateType=SimpleNamespace(**dict(zip(states, states, strict=True))),
        CoordType=SimpleNamespace(SCREEN="SCREEN"),
        Text=SimpleNamespace(
            get_text=lambda node, start, end: node.get_text(start, end)
        ),
        get_desktop=lambda _i: desktop,
    )
    state = SimpleNamespace(
        expected=EXPECTED,
        token="window-7",
        frame=(0, 0, 1600, 900),
        desktop=desktop,
        app=app,
        window=window,
        panel=panel,
        menu=menu,
        search=search,
        composer=composer,
        keys=[],
        owner=Owner(),
        helper=helper,
    )
    monkeypatch.setattr(helper, "_atspi", lambda: atspi)
    monkeypatch.setattr(helper, "_focused_identity", lambda: state.expected)
    monkeypatch.setattr(helper, "_focused_window_token", lambda: state.token)
    monkeypatch.setattr(
        helper, "_window_and_pointer", lambda: (*state.expected, *state.frame, 0, 0)
    )
    monkeypatch.setattr(helper, "sleep", lambda _s: None)
    monkeypatch.setattr(
        helper, "_key", lambda _c, _s, key, down: state.keys.append((key, down))
    )
    return state


@pytest.mark.parametrize(
    "rtl,width,sidebar", [(False, 1600, 0), (False, 900, 160), (True, 1200, 110)]
)
def test_search_and_menu_use_live_nodes_in_changed_layouts(
    ui: SimpleNamespace, rtl: bool, width: int, sidebar: int
) -> None:
    ui.frame = ui.window.bounds = (0, 0, width, 900)
    ui.menu.bounds = (width - 80 if rtl else sidebar + 14, 26, 28, 32)
    ui.search.bounds = (width - 450 if rtl else sidebar + 60, 30, 300, 40)
    if rtl:
        ui.menu.name, ui.search.name = "منوی اصلی", "جستجو"
    assert ui.helper._open_menu(ui.owner, EXPECTED)
    ui.helper._type_search_target(ui.owner, "/session", "علی Reza abc", EXPECTED)
    assert ui.menu.clicks == [1]
    assert ui.search.text == "علی Reza abc"
    assert ui.search.edits == ["علی ", "Reza", " abc"]
    assert ui.composer.edits == []
    assert [key for key, down in ui.keys if down] == [ui.helper.ESCAPE] * 2
    assert ui.owner.checks >= 8


def test_focus_search_never_edits_or_selects(ui: SimpleNamespace) -> None:
    ui.helper._focus_search(ui.owner, "/session", EXPECTED)
    assert "FOCUSED" in ui.search.states
    assert ui.search.text == "old query"
    assert ui.search.edits == ui.composer.edits == []
    assert [key for key, down in ui.keys if down] == [ui.helper.ESCAPE] * 2


@pytest.mark.parametrize("target", ["Do Not Open Telegram", "علی Reza"])
def test_search_text_uses_explicit_gi_interface_not_accessible_getter(
    ui: SimpleNamespace, target: str,
) -> None:
    # Real GI returns an Accessible proxy whose get_text() is the deprecated
    # zero-argument interface getter, not Text.get_text(start, end).
    read = ui.search.get_text
    ui.search.get_text = lambda: ui.search
    ui.helper._atspi().Text.get_text = lambda node, start, end: read(start, end)
    ui.helper._type_search_target(ui.owner, "/session", target, EXPECTED)
    assert ui.search.text == target
    assert ui.composer.edits == []
    assert ui.search.edits == [target[i:i + 4] for i in range(0, len(target), 4)]


def qt_profile(ui: SimpleNamespace) -> None:
    """Observed Qt root role/coordinates and non-editable Search wrappers."""
    ui.app.toolkit = "Qt"
    ui.window.role = "FILLER"
    ui.frame = (67, 32, 1600, 900)
    ui.search.role = "TEXT"
    ui.panel.add(Node("TEXT", "Search", set(NORMAL), ui.search.bounds))
    ui.panel.add(Node(
        "TEXT", "Search", {"ENABLED", "SENSITIVE", "EDITABLE"}, (0, 0, 0, 0)
    ))


def menu_rows(ui: SimpleNamespace) -> dict[str, Node]:
    container = ui.window.add(Node("PANEL", ""))
    return {
        label: container.add(Node(
            "BUTTON", label, set(NORMAL), (0, 200 + 40 * i, 274, 40),
            action_names=("setFocus",),
        ))
        for i, label in enumerate([
            "My Profile", "Calls", "Settings", "New Group", "New Channel", "Contacts"
        ])
    }


@pytest.mark.parametrize(
    "label", ["My Profile", "Calls", "Settings", "New Group", "New Channel"]
)
def test_visible_menu_row_is_selected_without_toggling_open_menu(
    ui: SimpleNamespace, label: str,
) -> None:
    qt_profile(ui)
    rows = menu_rows(ui)
    assert ui.helper._menu_destination(
        ui.owner, "/live", EXPECTED, ui.token, label.casefold()
    )
    assert ui.menu.clicks == []
    assert rows[label].clicks == [0]
    assert ui.keys == [(ord(" "), True), (ord(" "), False)]


def test_closed_menu_opens_once_then_selects_row(
    ui: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    qt_profile(ui)
    ui.menu.action_names = ("setFocus",)
    rows: dict[str, Node] = {}

    def send(_c: object, _s: str, key: int, down: bool) -> None:
        ui.keys.append((key, down))
        if key == ord(" ") and not down and not rows:
            rows.update(menu_rows(ui))

    monkeypatch.setattr(ui.helper, "_key", send)
    assert ui.helper._menu_destination(ui.owner, "/live", EXPECTED, ui.token, "calls")
    assert ui.menu.clicks == rows["Calls"].clicks == [0]
    assert ui.keys == [(ord(" "), True), (ord(" "), False)] * 2


def test_delayed_menu_rows_are_read_again_without_reopening(
    ui: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    qt_profile(ui)
    ui.menu.action_names = ("setFocus",)
    waits: list[float] = []

    def wait(seconds: float) -> None:
        if seconds == 0.1:
            waits.append(seconds)
            if len(waits) == 2:
                menu_rows(ui)

    monkeypatch.setattr(ui.helper, "sleep", wait)
    assert ui.helper._menu_destination(ui.owner, "/live", EXPECTED, ui.token, "calls")
    assert ui.menu.clicks == [0]
    assert waits == [0.1, 0.1]
    assert ui.keys == [(ord(" "), True), (ord(" "), False)] * 2


@pytest.mark.parametrize("change", ["cancel", "token"])
def test_menu_settle_never_continues_on_cancel_or_replacement(
    ui: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    qt_profile(ui)
    ui.menu.action_names = ("setFocus",)

    def wait(seconds: float) -> None:
        if seconds == 0.1:
            if change == "cancel":
                ui.owner.stopped = True
            else:
                ui.token = "replacement"

    monkeypatch.setattr(ui.helper, "sleep", wait)
    with pytest.raises((ControlUnavailable, OperationStopped)):
        ui.helper._menu_destination(ui.owner, "/live", EXPECTED, ui.token, "calls")
    assert ui.menu.clicks == [0]
    assert ui.keys == [(ord(" "), True), (ord(" "), False)]


def test_unprofiled_provider_does_not_toggle_without_visual_precheck(
    ui: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(ui.helper.sys, "argv", [
        "helper", EXPECTED[0], "42", "menu", "Calls",
    ])
    monkeypatch.setattr(ui.helper, "shared_session", lambda _d: (ui.owner, "/live"))
    assert ui.helper.main() == 0
    assert capsys.readouterr().out.splitlines()[-1] == "MENU_NEEDS_VISUAL"
    assert ui.menu.clicks == ui.keys == []


@pytest.mark.parametrize(
    "bad", [
        "single_label", "duplicate", "disabled", "changed_window", "cancelled",
        "hidden", "different_parent",
    ]
)
def test_menu_row_requires_independent_context_and_fresh_identity(
    ui: SimpleNamespace, bad: str,
) -> None:
    qt_profile(ui)
    rows = menu_rows(ui)
    if bad == "single_label":
        rows["Calls"].parent.children = [rows["Calls"]]
    elif bad == "duplicate":
        rows["Calls"].parent.add(Node(
            "BUTTON", "Calls", set(NORMAL), (0, 600, 200, 30)
        ))
    elif bad == "disabled":
        rows["Calls"].states.remove("ENABLED")
    elif bad == "changed_window":
        rows["Calls"].on_action = lambda: setattr(ui, "token", "replacement")
    elif bad == "cancelled":
        rows["Calls"].on_action = lambda: setattr(ui.owner, "stopped", True)
    elif bad == "hidden":
        rows["Calls"].states.remove("SHOWING")
    else:
        rows["Calls"].parent.children.remove(rows["Calls"])
        ui.window.add(Node("PANEL")).add(rows["Calls"])
    with pytest.raises((ControlUnavailable, OperationStopped)):
        ui.helper._menu_destination(ui.owner, "/live", EXPECTED, ui.token, "calls")
    assert ui.keys == []


@pytest.mark.parametrize(
    "label", ["My Profile", "Calls", "Settings", "New Group", "New Channel"]
)
def test_main_selects_semantic_menu_destination(
    ui: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], label: str,
) -> None:
    qt_profile(ui)
    rows = menu_rows(ui)
    monkeypatch.setattr(ui.helper.sys, "argv", [
        "helper", EXPECTED[0], "42", "menu", label,
    ])
    monkeypatch.setattr(ui.helper, "shared_session", lambda _d: (ui.owner, "/live"))
    assert ui.helper.main() == 0
    assert capsys.readouterr().out.splitlines()[-1] == "MENU_ITEM_DISPATCHED"
    assert ui.menu.clicks == []
    assert rows[label].clicks == [0]
    assert ui.keys == [(ord(" "), True), (ord(" "), False)]


def test_main_missing_menu_row_does_not_toggle_menu_or_claim_dispatch(
    ui: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    qt_profile(ui)
    rows = menu_rows(ui)
    rows["Calls"].parent.children.remove(rows["Calls"])
    monkeypatch.setattr(ui.helper.sys, "argv", [
        "helper", EXPECTED[0], "42", "menu", "Calls",
    ])
    monkeypatch.setattr(ui.helper, "shared_session", lambda _d: (ui.owner, "/live"))
    assert ui.helper.main() == 4
    assert capsys.readouterr().out.splitlines()[-1] == "MENU_ITEM_UNAVAILABLE"
    assert ui.menu.clicks == ui.keys == []


def test_main_opener_only_reports_no_destination_dispatch(
    ui: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    qt_profile(ui)
    ui.menu.action_names = ("setFocus",)
    monkeypatch.setattr(ui.helper.sys, "argv", [
        "helper", EXPECTED[0], "42", "menu", "Calls",
    ])
    monkeypatch.setattr(ui.helper, "shared_session", lambda _d: (ui.owner, "/live"))
    assert ui.helper.main() == 0
    assert capsys.readouterr().out.splitlines()[-1] == "MENU_CLICKED"
    assert ui.menu.clicks == [0]
    assert ui.keys == [(ord(" "), True), (ord(" "), False)]


def _break_opener(ui: SimpleNamespace, case: str) -> None:
    """One condition between closed-menu evidence and opener dispatch."""
    menu = ui.menu
    if case == "label_absent":
        menu.name = "Menu"
    elif case == "role_unsupported":
        menu.role = "LABEL"
    elif case == "not_usable":
        menu.states.discard("SHOWING")
    elif case == "ambiguous":
        ui.panel.add(Node("BUTTON", "Main menu", set(NORMAL), (14, 70, 28, 32)))
    elif case == "control_state":
        menu.states.discard("ENABLED")
    elif case == "control_bounds":
        menu.bounds = (1590, 26, 28, 32)
    elif case == "no_action":
        menu.action_names = ()
    elif case == "no_unique_action":
        menu.action_names = ("setFocus", "unknown")
    elif case == "opener_rejected":
        menu.action_names, menu.accepted = ("press",), False
    elif case == "focus_rejected":
        menu.action_names, menu.accepted = ("setFocus",), False
    elif case == "focus_not_observed":
        menu.action_names = ("setFocus",)
        menu.on_action = lambda: menu.states.discard("FOCUSED")
    elif case == "control_changed":
        menu.action_names = ("setFocus",)

        def replace() -> None:
            replacement = Node("BUTTON", "Main menu", set(menu.states), menu.bounds)
            replacement.parent = ui.panel
            ui.panel.children[0] = replacement

        menu.on_action = replace
    elif case == "window_changed_in_resolution":
        menu.action_names = ("setFocus",)
        menu.on_action = lambda: setattr(ui, "token", "replacement-window")


@pytest.mark.parametrize(
    "case,stages,code,last",
    [
        ("label_absent", [], 4, "CONTROL_UNAVAILABLE"),
        ("role_unsupported", [], 4, "CONTROL_UNAVAILABLE"),
        ("not_usable", [], 4, "CONTROL_UNAVAILABLE"),
        ("ambiguous", [], 4, "CONTROL_UNAVAILABLE"),
        ("control_state", [], 4, "CONTROL_UNAVAILABLE"),
        ("control_bounds", [], 4, "CONTROL_UNAVAILABLE"),
        ("no_action", ["opener_located", "opener_action_route"], 4,
         "CONTROL_UNAVAILABLE"),
        ("no_unique_action", ["opener_located", "opener_action_route"], 4,
         "CONTROL_UNAVAILABLE"),
        ("opener_rejected", ["opener_located", "opener_action_route"], 4,
         "CONTROL_UNAVAILABLE"),
        ("focus_rejected", ["opener_located", "opener_focus_route"], 4,
         "CONTROL_UNAVAILABLE"),
        ("focus_not_observed", ["opener_located", "opener_focus_route"], 4,
         "CONTROL_UNAVAILABLE"),
        ("control_changed", ["opener_located", "opener_focus_route"], 4,
         "CONTROL_UNAVAILABLE"),
        ("window_changed_in_resolution", ["opener_located", "opener_focus_route"],
         2, "TARGET_CHANGED"),
    ],
)
def test_opener_failure_trace_names_one_fixed_reason_and_sends_no_input(
    ui: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case: str, stages: list[str], code: int, last: str,
) -> None:
    qt_profile(ui)
    _break_opener(ui, case)
    monkeypatch.setenv("KYRIN_TELEGRAM_MENU_TRACE", "1")
    monkeypatch.setattr(ui.helper.sys, "argv", [
        "helper", EXPECTED[0], "42", "menu", "Settings",
    ])
    monkeypatch.setattr(ui.helper, "shared_session", lambda _d: (ui.owner, "/live"))
    assert ui.helper.main() == code
    lines = capsys.readouterr().out.splitlines()
    assert [line for line in lines if line.startswith("MENU_TRACE ")] == [
        f"MENU_TRACE {stage}"
        for stage in ["rows_absent_before_open", *stages, "failure_" + case]
    ]
    assert lines[-1] == last
    assert ui.keys == ui.search.edits == ui.composer.edits == []
    assert not any("Telegram" in line or "Main menu" in line for line in lines)


def test_opener_failure_reason_stays_silent_without_opt_in(
    ui: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    qt_profile(ui)
    _break_opener(ui, "label_absent")
    monkeypatch.delenv("KYRIN_TELEGRAM_MENU_TRACE", raising=False)
    monkeypatch.setattr(ui.helper.sys, "argv", [
        "helper", EXPECTED[0], "42", "menu", "Settings",
    ])
    monkeypatch.setattr(ui.helper, "shared_session", lambda _d: (ui.owner, "/live"))
    assert ui.helper.main() == 4
    lines = capsys.readouterr().out.splitlines()
    assert not any(line.startswith("MENU_TRACE") for line in lines)
    assert lines[-1] == "CONTROL_UNAVAILABLE"


def _run_menu_main(
    ui: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], *destination: str,
) -> tuple[int, list[str]]:
    monkeypatch.delenv("KYRIN_TELEGRAM_MENU_TRACE", raising=False)
    monkeypatch.setattr(ui.helper.sys, "argv", [
        "helper", EXPECTED[0], "42", "menu", *destination,
    ])
    monkeypatch.setattr(ui.helper, "shared_session", lambda _d: (ui.owner, "/live"))
    code = ui.helper.main()
    return code, capsys.readouterr().out.splitlines()


@pytest.mark.parametrize("shape", ["zero_actions", "no_action_interface"])
def test_actionless_qt_main_menu_reports_fixed_capability_marker(
    ui: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], shape: str,
) -> None:
    qt_profile(ui)
    ui.menu.action_names = ()
    if shape == "no_action_interface":
        ui.menu.get_action_iface = lambda: None
    code, lines = _run_menu_main(ui, monkeypatch, capsys, "Settings")
    assert code == 4
    assert lines[-2:] == ["MENU_ACTION_UNAVAILABLE", "CONTROL_UNAVAILABLE"]
    assert ui.keys == ui.menu.clicks == []
    assert ui.search.edits == ui.composer.edits == []
    assert not any("Telegram" in line or "Main menu" in line for line in lines)


@pytest.mark.parametrize("change,marker", [
    ("focus", "FOCUS_CHANGED"), ("target", "TARGET_CHANGED"),
])
def test_capability_marker_never_masks_identity_or_window_change(
    ui: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], change: str, marker: str,
) -> None:
    qt_profile(ui)
    ui.menu.action_names = ()
    interface = ui.menu.get_action_iface

    def observe_then_change() -> Any:
        # The window changes after the action read, before the final recheck.
        if change == "focus":
            ui.expected = ("org.example.Other.desktop", 7)
        else:
            ui.token = "replacement-window"
        return interface()

    ui.menu.get_action_iface = observe_then_change
    code, lines = _run_menu_main(ui, monkeypatch, capsys, "Settings")
    assert code == 2
    assert lines[-1] == marker
    assert "MENU_ACTION_UNAVAILABLE" not in lines
    assert ui.keys == ui.menu.clicks == []


@pytest.mark.parametrize(
    "case", [
        "unknown_action", "negative_count", "label_absent", "destination_row",
        "unprofiled_opener",
    ],
)
def test_other_unavailable_controls_keep_generic_classification(
    ui: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], case: str,
) -> None:
    destination: tuple[str, ...] = ("Settings",)
    if case != "unprofiled_opener":
        qt_profile(ui)
    if case == "unknown_action":
        ui.menu.action_names = ("show info",)
    elif case == "negative_count":
        ui.menu.action_names = ()
        ui.menu.get_n_actions = lambda: -1
    elif case == "label_absent":
        ui.menu.name = "Menu"
    elif case == "destination_row":
        menu_rows(ui)["Settings"].action_names = ()
    else:
        # Legacy open-only mode on a provider without the Qt local profile.
        ui.menu.action_names = ()
        destination = ()
    code, lines = _run_menu_main(ui, monkeypatch, capsys, *destination)
    assert code == 4
    assert lines[-1] == "CONTROL_UNAVAILABLE"
    assert "MENU_ACTION_UNAVAILABLE" not in lines
    assert ui.keys == ui.menu.clicks == []


def test_every_telegram_control_failure_has_a_fixed_trace_code() -> None:
    import ast

    from kyrin.actions.platforms import telegram_accessibility

    root = Path(telegram_accessibility.__file__).parent
    raised: set[str] = {"no unique supported action"}  # Shared action selector.
    traced: set[str] = set()
    for name in ("telegram_accessibility.py", "telegram_portal_helper.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            call = node.exc if isinstance(node, ast.Raise) else node
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
                continue
            messages = {
                item.value for item in ast.walk(call)
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            }
            if isinstance(node, ast.Raise) and call.func.id in {
                "ControlUnavailable", "MenuNotOpen", "MenuItemMissing",
                "MenuActionUnavailable",
            }:
                raised |= messages
            elif call.func.id == "_menu_trace":
                traced |= messages
    codes = telegram_accessibility.FAILURE_CODES
    assert raised and raised <= set(codes)
    assert all(code.isascii() and code.replace("_", "").isalpha()
               for code in codes.values())
    assert len(set(codes.values())) == len(codes)
    assert traced - {"failure_"} <= telegram_accessibility.MENU_TRACE_STAGES
    assert telegram_accessibility.failure_code(
        ControlUnavailable("private text")
    ) == "other"


def test_qt_telegram_semantic_controls_use_bound_local_frame(
    ui: SimpleNamespace,
) -> None:
    qt_profile(ui)
    assert ui.helper._open_menu(ui.owner, EXPECTED)
    ui.helper._type_search_target(
        ui.owner, "/session", "Do Not Open Telegram", EXPECTED
    )
    assert ui.menu.clicks == [1]
    assert ui.search.text == "Do Not Open Telegram"
    assert ui.composer.edits == []
    assert [key for key, down in ui.keys if down] == [ui.helper.ESCAPE] * 2


def test_qt_set_focus_menu_uses_one_guarded_space(ui: SimpleNamespace) -> None:
    qt_profile(ui)
    ui.menu.action_names = ("setFocus",)
    assert ui.helper._open_menu(ui.owner, EXPECTED, session="/live")
    assert ui.menu.clicks == [0]  # Focus is not an activation action.
    assert ui.keys == [(ord(" "), True), (ord(" "), False)]
    assert ui.search.edits == ui.composer.edits == []


def test_main_routes_real_qt_focus_only_menu(
    ui: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    qt_profile(ui)
    ui.menu.action_names = ("setFocus",)
    monkeypatch.setattr(ui.helper.sys, "argv", ["helper", EXPECTED[0], "42", "menu"])
    monkeypatch.setattr(ui.helper, "shared_session", lambda _d: (ui.owner, "/live"))
    assert ui.helper.main() == 0
    assert ui.menu.clicks == [0]
    assert ui.keys == [(ord(" "), True), (ord(" "), False)]


@pytest.mark.parametrize("args", [["saved"], ["view", "archive"], ["view", "contacts"]])
def test_main_never_finishes_shortcut_on_replacement_window(
    ui: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, args: list[str],
) -> None:
    monkeypatch.setattr(ui.helper.sys, "argv", ["helper", EXPECTED[0], "42", *args])
    monkeypatch.setattr(ui.helper, "shared_session", lambda _d: (ui.owner, "/live"))

    def send(_connection: object, _session: str, symbol: int, down: bool) -> None:
        ui.keys.append((symbol, down))
        if down and symbol == ui.helper.CONTROL:
            ui.token = "replacement-window"

    monkeypatch.setattr(ui.helper, "_key", send)
    assert ui.helper.main() == 2
    assert ui.keys == [(ui.helper.CONTROL, True), (ui.helper.CONTROL, False)]


@pytest.mark.parametrize(
    "change",
    ["cancel", "window", "token", "resize", "replace", "lost_focus", "rejected"],
)
def test_qt_focus_menu_never_activates_changed_target(
    ui: SimpleNamespace, change: str,
) -> None:
    qt_profile(ui)
    ui.menu.action_names = ("setFocus",)

    def changed() -> None:
        if change == "cancel":
            ui.owner.stopped = True
        elif change == "window":
            ui.expected = ("other.desktop", 8)
        elif change == "token":
            ui.token = "new-window"
        elif change == "resize":
            ui.frame = (67, 32, 1000, 900)
        elif change == "replace":
            replacement = Node(
                "BUTTON", "Main menu", set(ui.menu.states), ui.menu.bounds
            )
            replacement.parent = ui.panel
            ui.panel.children[0] = replacement
        elif change == "lost_focus":
            ui.menu.states.discard("FOCUSED")

    ui.menu.on_action = changed
    if change == "rejected":
        ui.menu.accepted = False
    error = OperationStopped if change == "cancel" else ControlUnavailable
    with pytest.raises(error):
        ui.helper._open_menu(ui.owner, EXPECTED, session="/live")
    assert ui.keys == ui.search.edits == ui.composer.edits == []


@pytest.mark.parametrize("names", [("setFocus", "unknown"), ("click", "press")])
def test_qt_ambiguous_menu_actions_never_fall_back_to_space(
    ui: SimpleNamespace, names: tuple[str, ...],
) -> None:
    qt_profile(ui)
    ui.menu.action_names = names
    with pytest.raises(ControlUnavailable):
        ui.helper._open_menu(ui.owner, EXPECTED, session="/live")
    assert ui.menu.clicks == ui.keys == []


def test_qt_explicit_activation_is_preferred_to_focus_route(
    ui: SimpleNamespace,
) -> None:
    qt_profile(ui)
    ui.menu.action_names = ("setFocus", "press")
    assert ui.helper._open_menu(ui.owner, EXPECTED, session="/live")
    assert ui.menu.clicks == [1] and ui.keys == []


@pytest.mark.parametrize("key", [ord("0"), ord("9"), ord("j")])
def test_shortcuts_recheck_window_between_modifier_and_key(
    ui: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, key: int,
) -> None:
    def send(_connection: object, _session: str, symbol: int, down: bool) -> None:
        ui.keys.append((symbol, down))
        if down and symbol == ui.helper.CONTROL:
            ui.token = "new-window"

    monkeypatch.setattr(ui.helper, "_key", send)
    with pytest.raises(ControlUnavailable):
        ui.helper._shortcut(ui.owner, "/live", EXPECTED, ui.token, key)
    assert ui.keys == [(ui.helper.CONTROL, True), (ui.helper.CONTROL, False)]


@pytest.mark.parametrize(
    "failure",
    ["unknown_provider", "gtk_provider", "inactive", "wrong_size", "wrong_origin",
     "wrong_pid", "other_active_window", "bad_ancestor"],
)
def test_qt_profile_never_infers_a_window_from_size_alone(
    ui: SimpleNamespace, failure: str,
) -> None:
    qt_profile(ui)
    if failure == "unknown_provider":
        ui.app.toolkit = ""
    elif failure == "gtk_provider":
        ui.app.toolkit = "GTK"
    elif failure == "inactive":
        ui.window.states.remove("ACTIVE")
    elif failure == "wrong_size":
        ui.window.bounds = (0, 0, 1200, 900)
    elif failure == "wrong_origin":
        ui.window.bounds = (1, 1, 1600, 900)
    elif failure == "wrong_pid":
        ui.window.pid = 9
    elif failure == "other_active_window":
        ui.app.add(Node("FRAME", "Another window", NORMAL | {"ACTIVE"}))
    elif failure == "bad_ancestor":
        ui.panel.states.remove("SENSITIVE")
    with pytest.raises(ControlUnavailable):
        ui.helper._open_menu(ui.owner, EXPECTED)
    assert ui.menu.clicks == ui.search.edits == ui.keys == []


def test_qt_multiple_visible_editable_search_fields_are_ambiguous(
    ui: SimpleNamespace,
) -> None:
    qt_profile(ui)
    ui.panel.add(Node(
        "TEXT", "Search", NORMAL | {"EDITABLE"}, (500, 100, 200, 40)
    ))
    with pytest.raises(ControlUnavailable):
        ui.helper._type_search_target(ui.owner, "/session", "literal query", EXPECTED)
    assert ui.search.edits == ui.composer.edits == []


@pytest.mark.parametrize("profile", ["standard", "qt"])
@pytest.mark.parametrize(
    "change",
    [
        "field",
        "window",
        "token",
        "resize",
        "move",
        "ancestry",
        "replace",
        "contents",
        "hidden",
        "cancel",
    ],
)
def test_batch_stops_on_changed_identity_state_or_cancellation(
    ui: SimpleNamespace, change: str, profile: str,
) -> None:
    if profile == "qt":
        qt_profile(ui)
    def changed() -> None:
        if change == "field":
            ui.search.states.remove("FOCUSED")
            ui.composer.states.add("FOCUSED")
        elif change == "window":
            ui.expected = ("other.desktop", 11)
        elif change == "token":
            ui.token = "window-8"  # Same app/PID, different window.
        elif change == "resize":
            ui.frame = (0, 0, 1200, 900)
        elif change == "move":
            ui.search.bounds = (200, 40, 300, 40)
        elif change == "ancestry":
            ui.panel.name = "Another panel"
        elif change == "replace":
            replacement = Node(
                "ENTRY", "Search", set(ui.search.states), ui.search.bounds
            )
            replacement.parent = ui.panel
            ui.panel.children[1] = replacement
        elif change == "contents":
            ui.search.text = "someone else's query"
        elif change == "hidden":
            ui.search.states.remove("SHOWING")
        else:
            ui.owner.stopped = True

    ui.search.on_edit = changed
    error = OperationStopped if change == "cancel" else ControlUnavailable
    with pytest.raises(error):
        ui.helper._type_search_target(ui.owner, "/session", "Alice Jones", EXPECTED)
    assert ui.search.edits == ["Alic"]
    assert ui.composer.edits == []
    assert not any(key == 0xFF0D for key, _down in ui.keys)


@pytest.mark.parametrize(
    "bad",
    [
        "missing",
        "duplicate",
        "password",
        "defunct",
        "disabled",
        "dialog",
        "second_window",
    ],
)
def test_unsafe_search_never_clears_or_types(ui: SimpleNamespace, bad: str) -> None:
    if bad == "missing":
        ui.search.name = ""
    elif bad == "duplicate":
        ui.panel.add(Node("ENTRY", "Search", NORMAL | {"EDITABLE"}))
    elif bad == "password":
        ui.search.role = "PASSWORD_TEXT"
    elif bad == "defunct":
        ui.search.states.add("DEFUNCT")
    elif bad == "disabled":
        ui.search.states.remove("ENABLED")
    elif bad == "dialog":
        ui.panel.role = "DIALOG"
    else:
        ui.app.add(Node("FRAME", "Telegram", NORMAL | {"ACTIVE"}))
    with pytest.raises(ControlUnavailable):
        ui.helper._type_search_target(ui.owner, "/session", "Alice", EXPECTED)
    assert ui.search.text == "old query"
    assert ui.search.edits == ui.composer.edits == []


def test_focus_change_inside_insert_cannot_redirect_text(ui: SimpleNamespace) -> None:
    # The fake transport switches focus during the first object-directed insert.
    ui.search.on_edit = lambda: ui.search.states.discard("FOCUSED")
    with pytest.raises(ControlUnavailable):
        ui.helper._type_search_target(ui.owner, "/session", "Alice Jones", EXPECTED)
    assert ui.search.text == "Alic"
    assert ui.composer.text == "old query"


def test_menu_without_live_evidence_never_clicks_fixed_position(
    ui: SimpleNamespace,
) -> None:
    ui.menu.name = "Back"
    with pytest.raises(ControlUnavailable):
        ui.helper._open_menu(ui.owner, EXPECTED)
    assert ui.menu.clicks == []
    assert ui.keys == []


def test_search_transport_rejection_is_not_success(ui: SimpleNamespace) -> None:
    ui.search.accepted = False
    with pytest.raises(ControlUnavailable):
        ui.helper._type_search_target(ui.owner, "/session", "Alice", EXPECTED)
    assert ui.search.edits == []


@pytest.mark.parametrize("mode", ["menu", "search"])
def test_initial_window_token_cannot_be_replaced_after_consent(
    ui: SimpleNamespace, mode: str
) -> None:
    ui.token = "window-after-consent"
    with pytest.raises(ControlUnavailable):
        if mode == "menu":
            ui.helper._open_menu(
                ui.owner, EXPECTED, window_token="window-before-consent"
            )
        else:
            ui.helper._type_search_target(
                ui.owner,
                "/session",
                "Alice",
                EXPECTED,
                window_token="window-before-consent",
            )
    assert ui.search.text == "old query"
    assert ui.search.edits == ui.menu.clicks == ui.keys == []


def test_revocation_during_field_read_prevents_next_insert(ui: SimpleNamespace) -> None:
    original = ui.search.get_text

    def revoke(start: int, end: int) -> str:
        ui.owner.stopped = True
        value = original(start, end)
        assert isinstance(value, str)
        return value

    ui.search.get_text = revoke
    with pytest.raises(OperationStopped):
        ui.helper._type_search_target(ui.owner, "/session", "Alice", EXPECTED)
    assert ui.search.edits == ui.composer.edits == []


def test_executor_keeps_shared_broker_across_all_search_batches(
    ui: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess
    from threading import Event, Thread

    from kyrin.actions.desktop_input import DesktopInputBroker
    from kyrin.actions.models import ActionKey, ActionRequest, ActionResult
    from kyrin.actions.platforms import telegram
    from kyrin.commands.models import CommandIntent, CommandKind
    from tests.actions.test_telegram_saved_messages import Delegate, Verifier

    broker = DesktopInputBroker()
    started, resume = Event(), Event()
    results: list[ActionResult] = []
    competing_text: list[str] = []
    errors: list[BaseException] = []

    def pause_after_batch() -> None:
        started.set()
        assert resume.wait(3)

    def transport(args: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert args[4] == "search"
        ui.helper._type_search_target(ui.owner, "/session", args[5], EXPECTED)
        return subprocess.CompletedProcess(args, 0, "SEARCH_TYPED", "")

    ui.search.on_edit = pause_after_batch
    monkeypatch.setattr(telegram, "run_process", transport)
    executor = telegram.TelegramSavedMessagesExecutor(
        Delegate(),
        telegram_desktop_id=EXPECTED[0],
        identity_reader=lambda: EXPECTED,
        verifier=Verifier(),
        remember_pointer=True,
        input_broker=broker,
        token_reader=lambda: "window-1",
    )
    request = ActionRequest(
        ActionKey(0, 1), CommandIntent(CommandKind.TELEGRAM_SEARCH, "Alice Jones")
    )

    def run() -> None:
        try:
            results.append(executor.execute(request))
        except BaseException as exc:
            errors.append(exc)

    worker = Thread(target=run, daemon=True)
    competitor = Thread(
        target=lambda: broker.run(lambda: competing_text.append(ui.search.text)),
        daemon=True,
    )
    worker.start()
    try:
        assert started.wait(3)
        competitor.start()
        with broker._condition:
            assert broker._condition.wait_for(lambda: len(broker._waiting) == 1, 3)
        assert competing_text == []
        assert ui.search.text == "Alic"
    finally:
        resume.set()
        worker.join(3)
        if competitor.ident is not None:
            competitor.join(3)
    assert not worker.is_alive() and not competitor.is_alive()
    assert errors == []
    assert len(results) == 1
    assert competing_text == ["Alice Jones"]
    broker.close()


@pytest.mark.parametrize(
    "args", [["menu"], ["search", "Alice"], ["focus-search"], ["saved"],
             ["view", "archive"], ["view", "contacts"], ["escape"]],
)
def test_shared_session_acquisition_cannot_rebind_the_initial_window(
    ui: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    args: list[str],
) -> None:
    from kyrin.app.permission_token import save_opaque_token

    path = tmp_path / "control.token"
    save_opaque_token(path, "old")
    helper = ui.helper
    monkeypatch.setattr(helper, "CONTROL_TOKEN_PATH", path)
    monkeypatch.setattr(helper.sys, "argv", ["helper", EXPECTED[0], "42", *args])
    calls: list[str] = []

    class Bus:
        def call_sync(self, *values: Any) -> None:
            calls.append(values[3])

    def acquire(_devices: int) -> tuple[SimpleNamespace, str]:
        ui.token = "other-window-same-process"
        return SimpleNamespace(check=lambda **kwargs: None, close=lambda: None), "/live"

    monkeypatch.setattr(helper, "shared_session", acquire)
    assert helper.main() == 2
    assert calls == []
    assert ui.search.text == "old query"
    assert ui.search.edits == ui.menu.clicks == ui.keys == []
