"""Synthetic portal/Shell on a private bus; never connects to a real desktop."""

import json
import os
import subprocess
import sys
from pathlib import Path
from threading import Thread
from time import monotonic, sleep

from gi.repository import Gio, GLib  # type: ignore[import-not-found]

PORTAL = "org.freedesktop.portal.Desktop"
ROOT = "/org/freedesktop/portal/desktop"
REMOTE = "org.freedesktop.portal.RemoteDesktop"
SHELL_PATH = "/org/kyrin/ActiveApp"
SHELL = "org.kyrin.ActiveApp"


def client() -> None:
    from kyrin.actions.platforms.input_session import INPUT_SESSIONS
    from kyrin.app.permissions import PermissionPolicy
    from kyrin.app.settings import AppSettings

    INPUT_SESSIONS.configure(
        PermissionPolicy(
            AppSettings(
                action_execution_enabled=True,
                allow_desktop_scroll=True,
            )
        )
    )
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def shell(method: str, payload: object = None) -> None:
        connection.call_sync(
            "org.gnome.Shell",
            SHELL_PATH,
            SHELL,
            method,
            payload,
            None,
            Gio.DBusCallFlags.NONE,
            2000,
            None,
        )

    prepared = INPUT_SESSIONS.prepare("desktop_scroll")
    assert prepared["state"] == "ready" and not prepared["persistent"]
    assert prepared["sender"].startswith(":")
    assert prepared["owner_pid"] > 0
    assert prepared["portal_version"] == 2
    assert prepared["app_id"] == (
        "local.kyrin.KYRIN" if os.environ.get("KYRIN_TEST_REGISTRY") else None
    )
    for app, pid in (("one.desktop", 11), ("two.desktop", 22)):
        shell("SetTarget", GLib.Variant("(su)", (app, pid)))
        for _ in range(5):
            result = INPUT_SESSIONS.run(
                [
                    "/usr/bin/python3",
                    "desktop_scroll_helper.py",
                    app,
                    str(pid),
                    "down",
                    "1",
                    "center",
                    "desktop-scroll",
                ],
                timeout=5,
            )
            assert result.returncode == 0, (result.stdout, result.stderr)
            assert "SCROLL_DISPATCHED" in result.stdout
    stale = INPUT_SESSIONS.run(
        [
            "python",
            "desktop_scroll_helper.py",
            "one.desktop",
            "11",
            "down",
            "1",
            "center",
            "desktop-scroll",
        ],
        timeout=5,
    )
    assert stale.returncode == 2
    ready = INPUT_SESSIONS.status()
    assert ready["starts"] == 1
    assert ready["sender"] == prepared["sender"]
    assert ready["owner_pid"] == prepared["owner_pid"]
    shell("Disconnect")
    # The method reply and the owner's asynchronous Closed signal race.
    deadline = monotonic() + 2
    status = INPUT_SESSIONS.status()
    while status["state"] != "disconnected" and monotonic() < deadline:
        sleep(0.01)
        status = INPUT_SESSIONS.status()
    assert status["state"] == "disconnected", status
    missing = INPUT_SESSIONS.run(
        [
            "python",
            "desktop_scroll_helper.py",
            "two.desktop",
            "22",
            "down",
            "1",
            "center",
            "desktop-scroll",
        ],
        timeout=5,
    )
    assert missing.returncode == 3
    INPUT_SESSIONS.disconnect()


def server() -> None:
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    for name in (PORTAL, "org.gnome.Shell"):
        connection.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "RequestName",
            GLib.Variant("(su)", (name, 0)),
            None,
            Gio.DBusCallFlags.NONE,
            2000,
            None,
        )
    portal_xml = """<node><interface name="org.freedesktop.portal.RemoteDesktop">
    <property name="version" type="u" access="read"/>
    <property name="AvailableDeviceTypes" type="u" access="read"/>
    <method name="CreateSession">
        <arg type="a{sv}" direction="in"/>
        <arg type="o" direction="out"/>
    </method>
    <method name="SelectDevices">
        <arg type="o" direction="in"/>
        <arg type="a{sv}" direction="in"/>
        <arg type="o" direction="out"/>
    </method>
    <method name="Start">
        <arg type="o" direction="in"/>
        <arg type="s" direction="in"/>
        <arg type="a{sv}" direction="in"/>
        <arg type="o" direction="out"/>
    </method>
    <method name="NotifyPointerMotion">
        <arg type="o" direction="in"/>
        <arg type="a{sv}" direction="in"/>
        <arg type="d" direction="in"/>
        <arg type="d" direction="in"/>
    </method>
    <method name="NotifyPointerAxis">
        <arg type="o" direction="in"/>
        <arg type="a{sv}" direction="in"/>
        <arg type="d" direction="in"/>
        <arg type="d" direction="in"/>
    </method>
    </interface></node>"""
    shell_xml = """<node><interface name="org.kyrin.ActiveApp">
    <method name="GetCapabilities">
        <arg type="s" direction="out"/>
    </method>
    <method name="GetActiveWindow">
        <arg type="s" direction="out"/>
        <arg type="u" direction="out"/>
    </method>
    <method name="GetActiveWindowToken">
        <arg type="s" direction="out"/>
    </method>
    <method name="GetActiveWindowAndPointer">
        <arg type="s" direction="out"/>
        <arg type="u" direction="out"/>
        <arg type="i" direction="out"/>
        <arg type="i" direction="out"/>
        <arg type="i" direction="out"/>
        <arg type="i" direction="out"/>
        <arg type="i" direction="out"/>
        <arg type="i" direction="out"/>
    </method>
    <method name="SetTarget">
        <arg type="s" direction="in"/>
        <arg type="u" direction="in"/>
    </method>
    <method name="Disconnect"/>
    </interface></node>"""
    registered: dict[str, str] = {}
    if os.environ.get("KYRIN_TEST_REGISTRY"):
        registry_xml = """<node><interface name="org.freedesktop.host.portal.Registry">
        <method name="Register"><arg type="s" direction="in"/>
        <arg type="a{sv}" direction="in"/></method></interface></node>"""

        def register(_c, sender, _path, _iface, _method, parameters, invocation):  # type: ignore[no-untyped-def]
            assert sender not in registered
            registered[sender] = parameters.unpack()[0]
            invocation.return_value(GLib.Variant("()", ()))

        connection.register_object(
            ROOT,
            Gio.DBusNodeInfo.new_for_xml(registry_xml).interfaces[0],
            register,
            None,
            None,
        )
    target = ["one.desktop", 11]
    pointer = [0, 0]
    sessions: set[str] = set()
    senders: set[str] = set()
    counts = {
        "CreateSession": 0,
        "SelectDevices": 0,
        "Start": 0,
        "NotifyPointerAxis": 0,
    }
    session_path = "/org/freedesktop/portal/desktop/session/fake/one"

    def respond(path: str, values: dict[str, object]) -> bool:
        connection.emit_signal(
            None,
            path,
            "org.freedesktop.portal.Request",
            "Response",
            GLib.Variant("(ua{sv})", (0, values)),
        )
        return False

    def remote(_c, sender, _path, _iface, method, parameters, invocation):  # type: ignore[no-untyped-def]
        args = parameters.unpack()
        if os.environ.get("KYRIN_TEST_REGISTRY"):
            assert registered.get(sender) == "local.kyrin.KYRIN"
        senders.add(sender)
        if method in counts:
            counts[method] += 1
        if method.startswith("Notify"):
            sessions.add(args[0])
            if method == "NotifyPointerMotion":
                pointer[:] = [round(pointer[0] + args[2]), round(pointer[1] + args[3])]
            invocation.return_value(GLib.Variant("()", ()))
            return
        token = args[-1]["handle_token"]
        path = ROOT + "/request/" + sender[1:].replace(".", "_") + "/" + token
        invocation.return_value(GLib.Variant("(o)", (path,)))
        values: dict[str, object] = {}
        if method == "CreateSession":
            assert args[-1]["session_handle_token"].startswith("kyrin_")
            assert len(args[-1]["session_handle_token"]) == 38
            values["session_handle"] = GLib.Variant("s", session_path)
        elif method == "Start":
            values["devices"] = GLib.Variant("u", 2)
        elif method == "SelectDevices":
            assert args[-1]["types"] == 2
        GLib.timeout_add(5, respond, path, values)

    def shell(_c, _sender, _path, _iface, method, parameters, invocation):  # type: ignore[no-untyped-def]
        if method == "SetTarget":
            target[:] = list(parameters.unpack())
            value = GLib.Variant("()", ())
        elif method == "Disconnect":
            connection.emit_signal(
                None,
                session_path,
                "org.freedesktop.portal.Session",
                "Closed",
                GLib.Variant("(a{sv})", ({},)),
            )
            value = GLib.Variant("()", ())
        elif method == "GetCapabilities":
            manifest = json.dumps(
                {
                    "protocol_version": 1,
                    "build_id": "synthetic-l03",
                    "capabilities": [
                        "GetActiveWindow",
                        "GetActiveWindowToken",
                        "GetActiveWindowAndPointer",
                    ],
                }
            )
            value = GLib.Variant("(s)", (manifest,))
        elif method == "GetActiveWindow":
            value = GLib.Variant("(su)", tuple(target))
        elif method == "GetActiveWindowToken":
            value = GLib.Variant("(s)", (str(target[0]),))
        else:
            value = GLib.Variant("(suiiiiii)", (*target, 0, 0, 1000, 800, *pointer))
        invocation.return_value(value)

    connection.register_object(
        ROOT,
        Gio.DBusNodeInfo.new_for_xml(portal_xml).interfaces[0],
        remote,
        lambda *_args: GLib.Variant("u", 2 if _args[-1] == "version" else 3),
        None,
    )
    connection.register_object(
        SHELL_PATH,
        Gio.DBusNodeInfo.new_for_xml(shell_xml).interfaces[0],
        shell,
        None,
        None,
    )
    loop = GLib.MainLoop()
    results = []

    def run_client() -> None:
        result = subprocess.run(
            [sys.executable, str(Path(__file__)), "client"],
            capture_output=True,
            text=True,
            timeout=45,
        )
        results.append(result)
        GLib.idle_add(loop.quit)

    Thread(target=run_client, daemon=True).start()
    GLib.timeout_add_seconds(50, loop.quit)
    loop.run()
    assert results, "client did not complete"
    assert results[0].returncode == 0, results[0].stderr
    assert counts == {
        "CreateSession": 1,
        "SelectDevices": 1,
        "Start": 1,
        "NotifyPointerAxis": 40,
    }, counts
    assert len(senders) == len(sessions) == 1, (senders, sessions)
    print(json.dumps({"counts": counts, "one_sender": True, "one_session": True}))


if __name__ == "__main__":
    client() if sys.argv[1:] == ["client"] else server()
