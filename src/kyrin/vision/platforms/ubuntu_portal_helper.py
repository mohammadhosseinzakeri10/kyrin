# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""One-shot ScreenCast Portal → PipeWire → PNG; run with system Python.

This process owns the short-lived portal session and writes only PNG bytes to
stdout. All errors and a user-cancelled picker leave stdout empty.
"""

import os
import sys
from uuid import uuid4

import gi  # type: ignore[import-not-found]

gi.require_version("Gst", "1.0")
from gi.repository import Gio, GLib, Gst  # type: ignore[import-not-found] # noqa: E402

BUS = "org.freedesktop.portal.Desktop"
OBJECT = "/org/freedesktop/portal/desktop"
SCREENCAST = "org.freedesktop.portal.ScreenCast"
REQUEST = "org.freedesktop.portal.Request"


def _request(connection, method, arguments, timeout_ms):
    """Wait for the one matching request signal with a bounded GLib loop."""
    token = "kyrin_" + uuid4().hex
    sender = connection.get_unique_name().replace(":", "").replace(".", "_")
    path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
    loop = GLib.MainLoop()
    response = []
    timed_out = False

    def on_response(_connection, _sender, _path, _interface, _signal, parameters):
        response.append(parameters.unpack())
        loop.quit()

    subscription = connection.signal_subscribe(
        BUS, REQUEST, "Response", path, None, Gio.DBusSignalFlags.NONE, on_response
    )

    def on_timeout():
        nonlocal timed_out
        timed_out = True
        loop.quit()
        return GLib.SOURCE_REMOVE

    timeout_id = GLib.timeout_add(timeout_ms, on_timeout)
    try:
        options = dict(arguments[-1])
        options["handle_token"] = GLib.Variant("s", token)
        parameters = GLib.Variant(
            "(" + ("o" if method in ("SelectSources", "Start") else "")
            + ("s" if method == "Start" else "")
            + "a{sv})",
            (*arguments[:-1], options),
        )
        returned = connection.call_sync(
            BUS,
            OBJECT,
            SCREENCAST,
            method,
            parameters,
            GLib.VariantType.new("(o)"),
            Gio.DBusCallFlags.NONE,
            timeout_ms,
            None,
        )
        if returned.unpack()[0] != path:
            raise RuntimeError("Portal returned a different request path")
        loop.run()
        if not response or response[0][0] != 0:
            return None
        return response[0][1]
    finally:
        if not timed_out:
            GLib.source_remove(timeout_id)
        connection.signal_unsubscribe(subscription)


def _one_png(pipewire_fd, node_id):
    Gst.init(None)
    pipeline = Gst.parse_launch(
        f"pipewiresrc fd={pipewire_fd} path={node_id} do-timestamp=true "
        "num-buffers=1 ! videoconvert ! pngenc ! appsink name=out sync=false"
    )
    sink = pipeline.get_by_name("out")
    if sink is None:
        raise RuntimeError("GStreamer image sink is unavailable")
    try:
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("PipeWire stream could not start")
        sample = sink.emit("try-pull-sample", 8 * Gst.SECOND)
        if sample is None:
            raise RuntimeError("No image was received from PipeWire")
        buffer = sample.get_buffer()
        success, mapping = buffer.map(Gst.MapFlags.READ)
        if not success:
            raise RuntimeError("Image buffer is not readable")
        try:
            return bytes(mapping.data)
        finally:
            buffer.unmap(mapping)
    finally:
        pipeline.set_state(Gst.State.NULL)


def main():
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    session = None
    try:
        created = _request(
            connection,
            "CreateSession",
            ({"session_handle_token": GLib.Variant("s", "kyrin_" + uuid4().hex)},),
            8000,
        )
        if created is None:
            return 1
        session = created["session_handle"]
        selected = _request(
            connection,
            "SelectSources",
            (
                session,
                {
                    "types": GLib.Variant("u", 2),
                    "multiple": GLib.Variant("b", False),
                },
            ),
            8000,
        )
        if selected is None:
            return 1
        started = _request(connection, "Start", (session, "", {}), 30000)
        if started is None or len(started["streams"]) != 1:
            return 1
        node_id, source_properties = started["streams"][0]
        if source_properties.get("source_type") != 2:
            return 1
        result, file_descriptors = connection.call_with_unix_fd_list_sync(
            BUS,
            OBJECT,
            SCREENCAST,
            "OpenPipeWireRemote",
            GLib.Variant("(oa{sv})", (session, {})),
            GLib.VariantType.new("(h)"),
            Gio.DBusCallFlags.NONE,
            8000,
            None,
            None,
        )
        pipewire_fd = file_descriptors.get(result.unpack()[0])
        try:
            image = _one_png(pipewire_fd, node_id)
        finally:
            os.close(pipewire_fd)
        if not image.startswith(b"\x89PNG\r\n\x1a\n") or len(image) > 32 * 1024 * 1024:
            return 1
        sys.stdout.buffer.write(image)
        return 0
    finally:
        if session is not None:
            try:
                connection.call_sync(
                    BUS,
                    session,
                    "org.freedesktop.portal.Session",
                    "Close",
                    None,
                    None,
                    Gio.DBusCallFlags.NONE,
                    3000,
                    None,
                )
            except GLib.Error:
                pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GLib.Error, RuntimeError, KeyError, IndexError, TypeError) as exc:
        print(f"Screen capture unavailable: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
