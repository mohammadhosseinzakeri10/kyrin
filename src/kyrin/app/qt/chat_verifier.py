"""Let an action worker request one Qt-owned, identity-bound OCR verification."""

from dataclasses import dataclass, field
from threading import Event

from PySide6.QtCore import QObject, QThread, Signal, Slot

from kyrin.actions.telegram_verification import (
    ChatSearchChoices,
    ChatSearchMatch,
    chat_header_visible,
    search_choices,
    unique_search_result,
)
from kyrin.app.qt.screen_access import ScreenAccess
from kyrin.app.qt.screen_text_reader import ScreenTextReader
from kyrin.vision.ocr.contracts import OcrOptions
from kyrin.vision.text_reader import IdentifiedWindowText
from kyrin.vision.text_targets import find_exact_phrases


@dataclass(slots=True)
class _Request:
    app_id: str | None
    pid: int | None
    target: str | None = None
    search: bool = False
    choices: bool = False
    finished: Event = field(default_factory=Event)
    result: bool | ChatSearchMatch | ChatSearchChoices | None = None


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
        self._last_choice_status = "not_requested"
        self.requested.connect(self._start)
        reader.completed.connect(self._completed)
        reader.failed.connect(self._failed)
        access.changed.connect(self._access_changed)

    def ready(self) -> bool:
        """Require current screen permission before requesting keyboard input."""
        return self._ask(_Request(None, None), timeout_s=2) is True

    def verify(self, app_id: str, pid: int, target: str = "Saved Messages") -> bool:
        """Return false for an uncertain, stale, or missing chat header."""
        return self._ask(_Request(app_id, pid, target), timeout_s=18) is True

    def find_search_result(
        self, app_id: str, pid: int, target: str
    ) -> ChatSearchMatch | None:
        """Return one exact visible result without authorizing a click."""
        result = self._ask(_Request(app_id, pid, target, search=True), timeout_s=18)
        return result if isinstance(result, ChatSearchMatch) else None

    def find_search_choices(
        self, app_id: str, pid: int, target: str
    ) -> ChatSearchChoices | None:
        """Read local and numbered global rows without granting a click."""
        self._last_choice_status = "pending"
        result = self._ask(_Request(app_id, pid, target, choices=True), timeout_s=18)
        if self._last_choice_status == "pending":
            self._last_choice_status = "timeout"
        return result if isinstance(result, ChatSearchChoices) else None

    def choice_status(self) -> str:
        """A content-free reason for the latest search-choice read."""
        return self._last_choice_status

    def _ask(
        self, request: _Request, *, timeout_s: float
    ) -> bool | ChatSearchMatch | ChatSearchChoices | None:
        if QThread.currentThread() == self.thread():
            return None
        self.requested.emit(request)
        if not request.finished.wait(timeout_s):
            request.finished.set()
            return None
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
            if request.choices:
                self._last_choice_status = "unavailable"
            request.finished.set()
            return
        self._pending = request
        language = (
            OcrOptions("fas+eng")
            if request.target is not None
            and any("\u0600" <= char <= "\u06ff" for char in request.target)
            and {"fas", "eng"}.issubset(self._reader.supported_languages)
            else None
        )
        if (
            request.target is not None
            and any("\u0600" <= char <= "\u06ff" for char in request.target)
            and language is None
        ):
            self._finish(False)
            return
        started = (
            self._reader.read()
            if language is None
            else self._reader.read(language)
        )
        if not started and self._pending is request:
            self._finish(False)

    def _completed(self, observation: object) -> None:
        pending = self._pending
        if pending is None:
            return
        result: bool | ChatSearchMatch | ChatSearchChoices | None = None
        if (
            isinstance(observation, IdentifiedWindowText)
            and pending.app_id is not None
            and pending.pid is not None
            and pending.target is not None
        ):
            if pending.choices:
                result = search_choices(
                    observation, pending.app_id, pending.pid, pending.target
                )
                matches = find_exact_phrases(observation.result, pending.target)
                size = observation.image_size or (0, 0)
                positions = "_".join(
                    f"{match.box.left}-{match.box.top}-"
                    f"{round(100 * (match.lowest_confidence or 0))}"
                    for match in matches[:6]
                ) or "none"
                detail = (
                    f"matches_{len(matches)}_size_{size[0]}x{size[1]}_"
                    f"at_{positions}"
                )
                self._last_choice_status = (
                    f"classified_local_{len(result.local_results)}_"
                    f"global_{len(result.global_results)}_{detail}"
                    if isinstance(result, ChatSearchChoices)
                    else f"unclassified_{detail}"
                )
            elif pending.search:
                result = unique_search_result(
                    observation, pending.app_id, pending.pid, pending.target
                )
            else:
                result = chat_header_visible(
                    observation, pending.app_id, pending.pid, pending.target
                )
        self._finish(result)

    def _failed(self, _reason: str) -> None:
        if self._pending is not None and self._pending.choices:
            self._last_choice_status = {
                "access_off": "access_off",
                "capture_unavailable": "capture_unavailable",
                "window_changed": "window_changed",
                "ocr_failed": "ocr_failed",
            }.get(_reason, "read_failed")
        self._finish(False)

    def _access_changed(self, granted: bool) -> None:
        if not granted:
            self._finish(False)

    def _finish(
        self, result: bool | ChatSearchMatch | ChatSearchChoices | None
    ) -> None:
        pending = self._pending
        self._pending = None
        if pending is not None:
            pending.result = result if not pending.finished.is_set() else None
            pending.finished.set()
