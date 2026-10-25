"""Private system-Python owner of one D-Bus connection and live input session."""

from __future__ import annotations

import importlib
import io
import os
import select
import socket
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from threading import Event, Thread
from typing import Any
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from kyrin.actions.platforms.helper_lifecycle import (  # noqa: E402
    INPUT_CHECK,
    SESSION_PROVIDER,
)
from kyrin.actions.platforms.input_session import BUILD, HELPERS, Wire  # noqa: E402
from kyrin.actions.platforms.portal_input import PortalInputSession  # noqa: E402
from kyrin.app.permission_token import permission_token_path  # noqa: E402
from kyrin.operations import Operation, OperationStopped, activate  # noqa: E402


class GioPortalBackend:
    def __init__(self) -> None:
        from gi.repository import Gio, GLib  # type: ignore[import-not-found]

        self.Gio, self.GLib = Gio, GLib
        self.connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.closed = False
        self.session_path: str | None = None
        self.subscription: int | None = None
        self.owner = self._owner()
        self.app_id: str | None = None
        from kyrin.app.platforms.xdg_startup import DESKTOP_FILE_ID

        # Register this same D-Bus peer before its first portal method.
        # A missing/retired Registry leaves identity detection to the portal.
        try:
            self.connection.call_sync(
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.host.portal.Registry",
                "Register",
                GLib.Variant("(sa{sv})", (DESKTOP_FILE_ID, {})),
                None,
                Gio.DBusCallFlags.NONE,
                1000,
                None,
            )
            self.app_id = DESKTOP_FILE_ID
        except GLib.Error:
            pass
        self.version = self._property("version")
        self.available = self._property("AvailableDeviceTypes")

    def diagnostics(self) -> dict[str, Any]:
        return {
            "portal_version": self.version,
            "sender": self.connection.get_unique_name(),
            "app_id": self.app_id,
        }

    def _owner(self) -> str:
        return str(
            self.connection.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "GetNameOwner",
                self.GLib.Variant("(s)", ("org.freedesktop.portal.Desktop",)),
                None,
                self.Gio.DBusCallFlags.NONE,
                1000,
                None,
            ).unpack()[0]
        )

    def _property(self, name: str) -> int:
        return int(
            self.connection.call_sync(
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.DBus.Properties",
                "Get",
                self.GLib.Variant(
                    "(ss)", ("org.freedesktop.portal.RemoteDesktop", name)
                ),
                None,
                self.Gio.DBusCallFlags.NONE,
                1000,
                None,
            ).unpack()[0]
        )

    def options(self, devices: int, token: str | None) -> dict[str, Any]:
        options = {"types": self.GLib.Variant("u", devices)}
        if self.version >= 2:
            options["persist_mode"] = self.GLib.Variant("u", 2)
            if token is not None:
                options["restore_token"] = self.GLib.Variant("s", token)
        return options

    def request(self, method: str, args: tuple[Any, ...]) -> dict[str, Any] | None:
        from kyrin.actions.platforms.telegram_portal_helper import _request

        if method == "CreateSession":
            options = dict(args[0])
            options["session_handle_token"] = self.GLib.Variant(
                "s", "kyrin_" + uuid4().hex
            )
            args = (options,)
        return _request(
            self.connection, method, args, 30000 if method == "Start" else 8000
        )

    def watch(self, session: str) -> None:
        self.closed = False
        self.session_path = session
        self.subscription = self.connection.signal_subscribe(
            "org.freedesktop.portal.Desktop",
            "org.freedesktop.portal.Session",
            "Closed",
            session,
            None,
            self.Gio.DBusSignalFlags.NONE,
            self._closed,
        )

    def _closed(self, _connection: Any, _sender: str, path: str, *_args: Any) -> None:
        if path == self.session_path:
            self.closed = True

    def alive(self, session: str) -> bool:
        context = self.GLib.MainContext.default()
        while context.pending():
            context.iteration(False)
        return (
            session == self.session_path
            and not self.closed
            and not self.connection.is_closed()
            and self._owner() == self.owner
        )

    def close(self, session: str) -> None:
        if self.session_path == session:
            self.session_path = None
        try:
            self.connection.call_sync(
                "org.freedesktop.portal.Desktop",
                session,
                "org.freedesktop.portal.Session",
                "Close",
                None,
                None,
                self.Gio.DBusCallFlags.NONE,
                200,
                None,
            )
        except self.GLib.Error:
            pass
        if self.subscription is not None:
            self.connection.signal_unsubscribe(self.subscription)
            self.subscription = None


def serve(wire: Wire, backend: Any) -> None:
    session = PortalInputSession(backend, permission_token_path("desktop-input"))
    provider = SESSION_PROVIDER.set(session)
    try:
        while True:
            message = wire.receive(0.05)
            if message is None:
                session.status()  # Drain Closed signals even between actions.
                continue
            request_id = message["id"]
            if message.get("build") != BUILD or message.get("protocol_version") != 1:
                raise ValueError("incompatible input protocol")
            operation = Operation(float(message["deadline"]))

            def check(
                operation: Operation = operation, request_id: str = request_id
            ) -> None:
                operation.remaining()
                wire.send({"id": request_id, "checkpoint": True})
                while True:
                    reply = wire.receive(min(0.02, operation.remaining()))
                    if reply is not None:
                        if (
                            reply.get("id") != request_id
                            or reply.get("authorized") is not True
                        ):
                            raise OperationStopped("input owner revoked request")
                        break
                operation.remaining()

            output, errors = io.StringIO(), io.StringIO()
            code = 0
            checkpoint = INPUT_CHECK.set(check)
            try:
                with (
                    activate(operation),
                    redirect_stdout(output),
                    redirect_stderr(errors),
                ):
                    command = message["command"]
                    if command == "prepare":
                        session.prepare(int(message["devices"]), check)
                    elif command == "execute":
                        name = message["helper"]
                        if name not in HELPERS:
                            raise ValueError("unknown input helper")
                        if session.acquire(HELPERS[name][1]) is None:
                            print("CONTROL_SETUP_REQUIRED")
                            code = 3
                        else:
                            module = importlib.import_module(
                                "kyrin.actions.platforms." + name.removesuffix(".py")
                            )
                            sys.argv = [name, *message["args"]]
                            code = module.main()
                    elif command != "status":
                        raise ValueError("unknown input command")
                operation.remaining()
            except OperationStopped:
                # Never allow a late completion or stuck modifier to outlive
                # this request. Closing the portal releases its input devices.
                session.close()
                raise
            except (
                OSError,
                RuntimeError,
                ValueError,
                KeyError,
                TypeError,
                backend.GLib.Error,
            ):
                session.close()
                code = 1
                errors.write("Input session failed; explicit setup required")
            finally:
                INPUT_CHECK.reset(checkpoint)
            diagnostics: dict[str, Any] = {}
            if hasattr(backend, "diagnostics"):
                diagnostics = backend.diagnostics()
            wire.send(
                {
                    "id": request_id,
                    "code": code,
                    "stdout": output.getvalue(),
                    "stderr": errors.getvalue(),
                    **session.status(),
                    "build": BUILD,
                    "protocol_version": 1,
                    "capabilities": ["shared-input-session-v1"],
                    "owner_pid": os.getpid(),
                    **diagnostics,
                }
            )
    finally:
        SESSION_PROVIDER.reset(provider)
        session.close()


def main() -> None:
    # The inherited channel is the sole owner lease. Parent death/close gives
    # EOF; even SIGKILL releases this process's D-Bus sender and portal session.
    channel = socket.socket(fileno=int(sys.argv[1]))
    channel.settimeout(0.2)

    def watch_owner() -> None:
        while True:
            try:
                if select.select([channel], [], [], 0.05)[0]:
                    if not channel.recv(1, socket.MSG_PEEK):
                        os._exit(0)
            except OSError:
                return
            Event().wait(0.05)

    Thread(target=watch_owner, name="input-owner-lease", daemon=True).start()
    try:
        serve(Wire(channel), GioPortalBackend())
    finally:
        channel.close()


if __name__ == "__main__":
    try:
        main()
    except OSError, RuntimeError, ValueError, KeyError, TypeError:
        os._exit(1)
