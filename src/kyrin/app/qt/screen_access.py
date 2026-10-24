"""Qt-owned access to the optional GNOME capture extension."""

import json
from collections.abc import Callable
from struct import unpack_from
from typing import cast

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtDBus import QDBusConnection, QDBusMessage, QDBusPendingCallWatcher

from kyrin.app.permission_token import (
    new_token,
    permission_token_path,
    read_token,
    save_token,
)
from kyrin.backend_protocol import BackendStatus, bus_status, transport_status
from kyrin.operations import current_operation, remaining
from kyrin.vision.capture_geometry import CaptureGeometry
from kyrin.vision.screen_capture import IdentifiedWindowImage

SERVICE_NAME = "org.kyrin.Desktop"
_SHELL_SERVICE = "org.gnome.Shell"
_OBJECT_PATH = "/org/kyrin/WindowCapturePrototype"
_INTERFACE = "org.kyrin.WindowCapturePrototype"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_MAX_IMAGE_BYTES = 16 * 1024 * 1024


class ScreenAccess(QObject):
    """Own the bus name and issue image requests from the same Qt connection."""

    changed = Signal(bool)
    error = Signal(str)

    def __init__(
        self, parent: QObject | None = None, *, allow_legacy_capture: bool = False
    ) -> None:
        super().__init__(parent)
        self._bus = QDBusConnection.sessionBus()
        self._owned = self._bus.isConnected() and self._bus.registerService(
            SERVICE_NAME
        )
        self._granted = False
        self._pending = False
        self._closed = False
        self._generation = 0
        self._token_path = permission_token_path("screen")
        self._allow_legacy_capture = allow_legacy_capture
        self.backend_status = BackendStatus(False, "not_probed")

    @property
    def remembered(self) -> bool:
        return read_token(self._token_path) is not None

    @property
    def available(self) -> bool:
        return self._owned and self.backend_status.ready

    @property
    def transport_available(self) -> bool:
        """Name ownership permits a probe, but does not prove backend readiness."""
        return self._owned

    @property
    def granted(self) -> bool:
        return self._granted

    def _call(
        self,
        member: str,
        timeout_ms: int,
        done: Callable[[QDBusMessage], None],
        token: str | None = None,
    ) -> None:
        message = QDBusMessage.createMethodCall(
            _SHELL_SERVICE, _OBJECT_PATH, _INTERFACE, member
        )
        if token is not None:
            message.setArguments([token])
        watcher = QDBusPendingCallWatcher(
            self._bus.asyncCall(
                message, max(1, int(remaining(timeout_ms / 1000) * 1000))
            ),
            self,
        )

        def finished(completed: QDBusPendingCallWatcher) -> None:
            try:
                done(completed.reply())
            finally:
                completed.deleteLater()

        watcher.finished.connect(finished)

    @staticmethod
    def _boolean_reply(reply: QDBusMessage) -> bool:
        arguments = reply.arguments()
        return reply.type() != QDBusMessage.MessageType.ErrorMessage and (
            len(arguments) == 1 and type(arguments[0]) is bool and arguments[0]
        )

    def _probe(self, required: set[str], done: Callable[[bool], None]) -> None:
        generation = self._generation
        operation = current_operation()

        def attempt(index: int) -> None:
            if (
                self._closed
                or generation != self._generation
                or (operation is not None and operation.stopped)
            ):
                done(False)
                return

            def received(reply: QDBusMessage) -> None:
                if (
                    self._closed
                    or generation != self._generation
                    or (operation is not None and operation.stopped)
                ):
                    done(False)
                    return
                status = (
                    transport_status(reply.errorName())
                    if reply.type() == QDBusMessage.MessageType.ErrorMessage
                    else bus_status(reply.arguments(), required)
                )
                self.backend_status = status
                if (
                    status.reason in {"service_unavailable", "service_timeout"}
                    and index < 2
                ):
                    QTimer.singleShot(50, self, lambda: attempt(index + 1))
                    return
                legacy = (
                    self._allow_legacy_capture and status.reason == "handshake_missing"
                )
                if not status.ready and not legacy:
                    self._granted = False
                    self.changed.emit(False)
                    self.error.emit("Screen backend: " + status.reason)
                done(status.ready or legacy)

            timeout_ms = (
                max(1, int(operation.remaining(0.5) * 1000))
                if operation is not None
                else 500
            )
            self._call("GetCapabilities", timeout_ms, received)

        attempt(0)

    def request_session(self) -> None:
        if not self._owned:
            self.error.emit("KYRIN could not own its screen-access session name.")
            return
        if self._closed or self._pending or self._granted:
            return
        self._pending = True
        generation = self._generation
        operation = current_operation()

        def ready(supported: bool) -> None:
            if self._closed or generation != self._generation:
                return
            if not supported:
                self._pending = False
                return
            token = read_token(self._token_path)
            if token is None:
                token = new_token()
                try:
                    save_token(self._token_path, token)
                except OSError:
                    self._pending = False
                    self.error.emit(
                        "Could not remember the screen permission on this device."
                    )
                    return
            timeout_ms = (
                max(1, int(operation.remaining(25) * 1000))
                if operation is not None
                else 25000
            )
            self._call("RequestPersistentSession", timeout_ms, done, token)

        def done(reply: QDBusMessage) -> None:
            if self._closed or generation != self._generation:
                return
            self._pending = False
            granted = self._boolean_reply(reply) and not (
                operation is not None and operation.stopped
            )
            self._granted = granted
            self.changed.emit(granted)
            if not granted:
                if reply.type() != QDBusMessage.MessageType.ErrorMessage:
                    try:
                        self._token_path.unlink(missing_ok=True)
                    except OSError:
                        self.error.emit("Could not remove the screen permission token.")
                self.error.emit("Screen access was denied or is unavailable.")

        required = {"RequestPersistentSession", "RevokeSession", "CaptureActiveWindow"}
        if not self._allow_legacy_capture:
            required.add("capture-geometry-v1")
        self._probe(required, ready)

    def revoke(self) -> None:
        was_granted = self._granted
        was_pending = self._pending
        had_token = self.remembered
        self._generation += 1
        self._pending = False
        self._granted = False
        self.changed.emit(False)
        try:
            self._token_path.unlink(missing_ok=True)
            self._token_path.with_name("screen-grant.sha256").unlink(missing_ok=True)
        except OSError:
            self.error.emit("Could not remove the remembered screen permission.")
        if self._owned and (was_granted or was_pending or had_token):
            self._call("RevokeSession", 3000, lambda _reply: None)

    def capture(self, done: Callable[[IdentifiedWindowImage | None], None]) -> None:
        """Capture on demand; never block the Qt event loop or save an image."""
        if not self._granted or not self._owned:
            done(None)
            return
        generation = self._generation
        operation = current_operation()

        def received(reply: QDBusMessage) -> None:
            if (
                self._closed
                or generation != self._generation
                or (operation is not None and operation.stopped)
            ):
                done(None)
                return
            if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                done(None)
                return
            arguments = reply.arguments()
            if len(arguments) != 12 and not (
                self._allow_legacy_capture and len(arguments) in {3, 11}
            ):
                self.error.emit("Screen backend: legacy_capture_disabled")
                done(None)
                return
            app_id, pid = arguments[:2]
            raw_image = arguments[-1]
            geometry = arguments[2:10] if len(arguments) >= 11 else None
            try:
                image = bytes(cast("bytes | bytearray", raw_image))
                if (
                    not isinstance(app_id, str)
                    or not app_id
                    or app_id.startswith("window:")
                    or type(pid) is not int
                    or pid <= 0
                    or not image.startswith(_PNG_MAGIC)
                    or len(image) > _MAX_IMAGE_BYTES
                ):
                    done(None)
                    return
                if geometry is not None and any(
                    type(value) is not int for value in geometry
                ):
                    done(None)
                    return
                capture_rect = tuple(geometry[:4]) if geometry is not None else None
                frame_rect = tuple(geometry[4:]) if geometry is not None else None
                explicit = None
                if len(arguments) == 12:
                    if not isinstance(arguments[10], str) or len(image) < 24:
                        done(None)
                        return
                    metadata = json.loads(arguments[10])
                    if not isinstance(metadata, dict) or image[12:16] != b"IHDR":
                        done(None)
                        return
                    if (
                        metadata.get("coordinate_space") != "logical_desktop"
                        or metadata.get("image_coordinate_space") != "source_png_pixels"
                        or metadata.get("mapping_source") != "gnome-buffer-actor-v1"
                    ):
                        # An older producer guessed symmetric shadow padding.
                        # Its identical D-Bus signature does not prove this map.
                        done(None)
                        return
                    image_size = unpack_from(">II", image, 16)
                    assert capture_rect is not None and frame_rect is not None
                    explicit = CaptureGeometry(
                        "logical_desktop",
                        metadata["monitor_id"],
                        capture_rect,
                        image_size,
                        metadata["scale_x"],
                        metadata["scale_y"],
                        tuple(metadata["padding"]),
                        (0, 0),
                        (1, 1),
                        metadata["window_token"],
                        metadata["capture_id"],
                        metadata["captured_at"],
                        frame_rect,
                    )
                done(
                    IdentifiedWindowImage(
                        app_id,
                        pid,
                        image,
                        capture_rect,
                        frame_rect,
                        explicit,
                    )
                )
            except TypeError, ValueError, KeyError, json.JSONDecodeError:
                done(None)

        def ready(supported: bool) -> None:
            if supported:
                timeout_ms = (
                    max(1, int(operation.remaining(10) * 1000))
                    if operation is not None
                    else 10000
                )
                self._call("CaptureActiveWindow", timeout_ms, received)
            else:
                done(None)

        required = {"CaptureActiveWindow"}
        if not self._allow_legacy_capture:
            required.add("capture-geometry-v1")
        self._probe(required, ready)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._generation += 1
        self._granted = False
        if self._owned:
            self._bus.unregisterService(SERVICE_NAME)
            self._owned = False
