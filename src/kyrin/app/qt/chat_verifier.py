"""Let an action worker request one Qt-owned, identity-bound OCR verification."""

from dataclasses import dataclass, field
from threading import Event

from PySide6.QtCore import QObject, QThread, Signal, Slot

from kyrin.actions.telegram_verification import saved_messages_header_visible
from kyrin.app.qt.screen_access import ScreenAccess
from kyrin.app.qt.screen_text_reader import ScreenTextReader
from kyrin.vision.text_reader import IdentifiedWindowText


@dataclass(slots=True)
class _Request:
    app_id: str | None
    pid: int | None
    finished: Event = field(default_factory=Event)
    result: bool = False


class QtChatVerifier(QObject):
    """Block only the action worker; all screen access remains on Qt's thread."""

    requested = Signal(object)

    def __init__(
        self,
        access: ScreenAccess,
        reader: ScreenTextReader,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._access = access
        self._reader = reader
        self._pending: _Request | None = None
        self.requested.connect(self._start)
        reader.completed.connect(self._completed)
        reader.failed.connect(self._failed)
        access.changed.connect(self._access_changed)

    def ready(self) -> bool:
        """Require current screen permission before requesting keyboard input."""
        return self._ask(_Request(None, None), timeout_s=2)

    def verify(self, app_id: str, pid: int) -> bool:
        """Return false for an uncertain, stale, or missing chat header."""
        return self._ask(_Request(app_id, pid), timeout_s=18)

    def _ask(self, request: _Request, *, timeout_s: float) -> bool:
        if QThread.currentThread() == self.thread():
            return False
        self.requested.emit(request)
        if not request.finished.wait(timeout_s):
            request.finished.set()
            return False
        return request.result

    @Slot(object)
    def _start(self, request: object) -> None:
        if not isinstance(request, _Request) or request.finished.is_set():
            return
        available = (
            self._access.granted
            and self._reader.available
            and not self._reader.busy
            and self._pending is None
        )
        if request.app_id is None:
            request.result = available
            request.finished.set()
            return
        if not available or request.pid is None:
            request.finished.set()
            return
        self._pending = request
        if not self._reader.read() and self._pending is request:
            self._finish(False)

    def _completed(self, observation: object) -> None:
        pending = self._pending
        if pending is None:
            return
        valid = isinstance(observation, IdentifiedWindowText) and (
            pending.app_id is not None
            and pending.pid is not None
            and saved_messages_header_visible(observation, pending.app_id, pending.pid)
        )
        self._finish(valid)

    def _failed(self, _reason: str) -> None:
        self._finish(False)

    def _access_changed(self, granted: bool) -> None:
        if not granted:
            self._finish(False)

    def _finish(self, result: bool) -> None:
        pending = self._pending
        self._pending = None
        if pending is not None:
            pending.result = result and not pending.finished.is_set()
            pending.finished.set()
