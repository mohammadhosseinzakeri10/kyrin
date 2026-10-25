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
        return 2

    def get_action_name(self, index: int) -> str:
        return ["show info", "press"][index]

    def do_action(self, index: int) -> bool:
        self.clicks.append(index)
        return self.accepted


@dataclass
class Owner:
    stopped: bool = False
    checks: int = 0

    def check(self, *, input_event: bool = False) -> None:
        if self.stopped:
            raise OperationStopped("owner cancelled or permission revoked")
        self.checks += int(input_event)


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
    roles = ("FRAME", "WINDOW", "DIALOG", "BUTTON", "PUSH_BUTTON_MENU", "ENTRY", "TEXT")
    states = (*NORMAL, "ACTIVE", "FOCUSED", "EDITABLE", "DEFUNCT", "STALE", "INVALID")
    atspi = SimpleNamespace(
        Role=SimpleNamespace(**dict(zip(roles, roles, strict=True))),
        StateType=SimpleNamespace(**dict(zip(states, states, strict=True))),
        CoordType=SimpleNamespace(SCREEN="SCREEN"),
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
    ui: SimpleNamespace, change: str
) -> None:
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


@pytest.mark.parametrize("args", [["menu"], ["search", "Alice"], ["focus-search"]])
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

    def acquire(_devices: int):
        ui.token = "other-window-same-process"
        return SimpleNamespace(check=lambda **kwargs: None, close=lambda: None), "/live"

    monkeypatch.setattr(helper, "shared_session", acquire)
    assert helper.main() == 2
    assert calls == []
    assert ui.search.text == "old query"
    assert ui.search.edits == ui.menu.clicks == ui.keys == []
