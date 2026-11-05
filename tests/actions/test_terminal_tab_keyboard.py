"""Fixed chord through the actual guarded helper; no native input or GI runtime."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from kyrin.actions.platforms import desktop_control
from kyrin.operations import OperationStopped
from tests.actions.test_desktop_semantic_control import semantic as semantic
from tests.actions.test_ptyxis_menu import tab_scene as tab_scene


@pytest.fixture
def keyboard_scene(
    tab_scene: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> SimpleNamespace:
    t = tab_scene
    path = Path(desktop_control.__file__).with_name("terminal_tab_helper.py")
    spec = importlib.util.spec_from_file_location("terminal_tab_keyboard_test", path)
    assert spec is not None and spec.loader is not None
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    monkeypatch.setattr(helper, "_atspi", lambda: t.scene.atspi)
    monkeypatch.setattr(helper, "_focused_identity", t.scene.helper._focused_identity)
    monkeypatch.setattr(helper, "_focused_window_token", lambda: t.scene.token[0])
    monkeypatch.setattr(
        helper, "_window_and_pointer", t.scene.helper._window_and_pointer
    )
    monkeypatch.setattr(helper, "monotonic", lambda: t.scene.now[0])
    monkeypatch.setattr(t.scene.atspi.StateType, "MODAL", "MODAL", raising=False)
    monkeypatch.setattr(
        helper.GLib, "Variant", lambda _signature, value: value, raising=False
    )
    monkeypatch.setattr(
        helper.Gio, "DBusCallFlags", SimpleNamespace(NONE=0), raising=False
    )
    calls: list[tuple[int, bool]] = []

    def raw_call(*args: object) -> None:
        assert args[3] == "NotifyKeyboardKeysym"
        payload = args[4]
        assert isinstance(payload, tuple)
        assert payload[:2] == ("/session/test", {})
        calls.append((payload[2], bool(payload[3])))

    t.scene.owner.connection = SimpleNamespace(call_sync=raw_call)
    t.scene.owner.operation = SimpleNamespace(remaining=lambda: 8.0)
    return SimpleNamespace(
        original=t,
        helper=helper,
        calls=calls,
        run=lambda: helper._tab(t.observation, t.scene.owner, "/session/test"),
    )


def test_only_reviewed_chord_no_menu_action_or_free_text(
    keyboard_scene: SimpleNamespace,
) -> None:
    t = keyboard_scene
    assert t.run() == "TAB_ITEM:ACTION_DISPATCHED"
    assert t.calls == [
        (0xFFE3, True),
        (0xFFE1, True),
        (0x74, True),
        (0x74, False),
        (0xFFE1, False),
        (0xFFE3, False),
    ]
    assert t.original.toggle.calls == [] and t.original.tab.calls == []
    assert t.original.scene.owner.events.count(True) == 6


@pytest.mark.parametrize(
    "case",
    ["token", "identity", "expired", "modal", "open", "disabled", "config", "conflict"],
)
def test_invalid_context_sends_no_keys(
    keyboard_scene: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    t, original = keyboard_scene, keyboard_scene.original
    if case == "token":
        original.scene.token[0] = "another-same-process-window"
    elif case == "identity":
        monkeypatch.setattr(
            t.helper, "_focused_identity", lambda: ("other.desktop", 42)
        )
    elif case == "expired":
        original.scene.now[0] = 110.0
    elif case == "modal":
        original.scene.window.states.add("MODAL")
    elif case == "open":
        original.open_menu()
    elif case == "disabled":
        original.toggle.states.remove("SENSITIVE")
    elif case == "config":
        original.mapping["new-tab"] = "<ctrl>d"
    else:
        original.mapping["new-window"] = "<ctrl><shift>t"
    assert t.run() != "TAB_ITEM:ACTION_DISPATCHED"
    assert t.calls == [] and not original.toggle.calls


@pytest.mark.parametrize("case", ["token", "config", "frame", "disable", "cancel"])
def test_authorization_and_target_rechecked_before_each_press(
    keyboard_scene: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    t, original = keyboard_scene, keyboard_scene.original
    checks = []

    def check(*, input_event: bool = False) -> None:
        if input_event:
            checks.append(True)
            if len(checks) == 2:
                if case == "token":
                    original.scene.token[0] = "changed"
                elif case == "config":
                    original.mapping["new-tab"] = "<ctrl>d"
                elif case == "frame":
                    monkeypatch.setattr(
                        t.helper,
                        "_window_and_pointer",
                        lambda: (
                            "org.gnome.Ptyxis.desktop",
                            42,
                            11,
                            20,
                            800,
                            600,
                            0,
                            0,
                        ),
                    )
                elif case == "disable":
                    original.toggle.states.remove("SENSITIVE")
                else:
                    raise OperationStopped("owner cancelled")

    monkeypatch.setattr(original.scene.owner, "check", check)
    if case == "cancel":
        with pytest.raises(OperationStopped):
            t.run()
    else:
        assert t.run() != "TAB_ITEM:ACTION_DISPATCHED"
    assert t.calls == [(0xFFE3, True), (0xFFE3, False)]


def test_unknown_press_reply_still_releases_its_modifier(
    keyboard_scene: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = keyboard_scene
    raw = t.original.scene.owner.connection.call_sync

    def lost_reply(*args: object) -> None:
        raw(*args)
        if len(t.calls) == 1:
            raise RuntimeError("reply lost after input")

    monkeypatch.setattr(t.original.scene.owner.connection, "call_sync", lost_reply)
    assert t.run() == "TAB_ITEM:ACTION_UNCONFIRMED"
    assert t.calls == [(0xFFE3, True), (0xFFE3, False)]


def test_failed_release_requires_owner_session_cleanup(
    keyboard_scene: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = keyboard_scene
    raw = t.original.scene.owner.connection.call_sync

    def lost_release(*args: object) -> None:
        raw(*args)
        if len(t.calls) == 4:
            raise RuntimeError("release reply lost")

    monkeypatch.setattr(t.original.scene.owner.connection, "call_sync", lost_release)
    with pytest.raises(OperationStopped, match="release unconfirmed"):
        t.run()


def test_missing_live_keyboard_never_starts_setup(
    keyboard_scene: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = keyboard_scene
    monkeypatch.setattr(
        t.helper.sys,
        "argv",
        ["terminal_tab_helper.py", t.original.observation.to_json()],
    )
    monkeypatch.setattr(
        t.helper, "probe_gnome", lambda *_a, **_k: SimpleNamespace(ready=True)
    )
    requested = []
    monkeypatch.setattr(
        t.helper, "shared_session", lambda devices: requested.append(devices)
    )
    assert t.helper.main() == 3 and requested == [1]
    assert t.calls == []


def test_persistent_cancellation_propagates_to_owner_device_cleanup(
    keyboard_scene: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = keyboard_scene
    checks = []

    def check(*, input_event: bool = False) -> None:
        if input_event:
            checks.append(True)
            if len(checks) >= 2:
                raise OperationStopped("generation cancelled")

    monkeypatch.setattr(t.original.scene.owner, "check", check)
    with pytest.raises(OperationStopped):
        t.run()
    # The helper cannot authorize releases after cancellation. Propagating the
    # stop invokes the existing owner's mandatory session/device teardown.
    assert t.calls == [(0xFFE3, True)]
