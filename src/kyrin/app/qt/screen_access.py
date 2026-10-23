"""Qt-owned access to the optional GNOME capture extension."""

from collections.abc import Callable
from typing import cast

from PySide6.QtCore import QObject, Signal
from PySide6.QtDBus import QDBusConnection, QDBusMessage, QDBusPendingCallWatcher

from kyrin.app.permission_token import (
    new_token,
    permission_token_path,
    read_token,
    save_token,
)
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

    def __init__(self, parent: QObject | None = None) -> None:
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

    @property
    def remembered(self) -> bool:
        return read_token(self._token_path) is not None

    @property
    def available(self) -> bool:
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
            self._bus.asyncCall(message, timeout_ms), self
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

    def request_session(self) -> None:
        if not self._owned:
            self.error.emit("KYRIN could not own its screen-access session name.")
            return
        if self._pending or self._granted:
            return
        token = read_token(self._token_path)
        if token is None:
            token = new_token()
            try:
                save_token(self._token_path, token)
            except OSError:
                self.error.emit(
                    "Could not remember the screen permission on this device."
                )
                return
        self._pending = True
        generation = self._generation

        def done(reply: QDBusMessage) -> None:
            if self._closed or generation != self._generation:
                return
            self._pending = False
            granted = self._boolean_reply(reply)
            self._granted = granted
            self.changed.emit(granted)
            if not granted:
                try:
                    self._token_path.unlink(missing_ok=True)
                except OSError:
                    self.error.emit("Could not remove the screen permission token.")
                self.error.emit("Screen access was denied or is unavailable.")

        self._call("RequestPersistentSession", 25000, done, token)

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

        def received(reply: QDBusMessage) -> None:
            if self._closed or generation != self._generation:
                done(None)
                return
            if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                done(None)
                return
            arguments = reply.arguments()
            if len(arguments) not in {3, 11}:
                done(None)
                return
            app_id, pid = arguments[:2]
            raw_image = arguments[-1]
            geometry = arguments[2:10] if len(arguments) == 11 else None
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
                done(
                    IdentifiedWindowImage(
                        app_id,
                        pid,
                        image,
                        capture_rect,
                        frame_rect,
                    )
                )
            except TypeError, ValueError:
                done(None)

        self._call("CaptureActiveWindow", 10000, received)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._generation += 1
        self._granted = False
        if self._owned:
            self._bus.unregisterService(SERVICE_NAME)
            self._owned = False
