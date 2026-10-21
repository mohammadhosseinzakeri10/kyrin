"""Let an action worker request one Qt-owned, identity-bound OCR verification."""

from dataclasses import dataclass, field
from threading import Event

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from kyrin.actions.telegram_verification import (
    ChatSearchChoices,
    ChatSearchMatch,
    assess_visible_chat_choices,
    chat_header_visible,
    search_choices,
    telegram_left_label,
    telegram_menu_item,
    telegram_search_query_visible,
    telegram_settings_header,
    telegram_settings_item,
    telegram_view_title_visible,
    unique_search_result,
)
from kyrin.actions.visible_chat_grounding import suggest_visible_chat_choices
from kyrin.app.qt.screen_access import ScreenAccess
from kyrin.app.qt.screen_text_reader import ScreenTextReader
from kyrin.vision.ocr.contracts import OcrOptions
from kyrin.vision.text_reader import IdentifiedWindowText
from kyrin.vision.text_targets import find_exact_phrases, find_literal_phrases


@dataclass(slots=True)
class _Request:
    app_id: str | None
    pid: int | None
    target: str | None = None
    search: bool = False
    choices: bool = False
    visible_choices: bool = False
    visible_focused: bool = False
    visible_bilingual: bool = False
    left_label: bool = False
    menu: bool = False
    settings_item: bool = False
    settings_header: bool = False
    view_title: bool = False
    search_query: bool = False
    finished: Event = field(default_factory=Event)
    result: bool | str | ChatSearchMatch | ChatSearchChoices | None = None


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
        self._pending_ready: _Request | None = None
        self._last_choice_status = "not_requested"
        self.requested.connect(self._start)
        reader.completed.connect(self._completed)
        reader.failed.connect(self._failed)
        access.changed.connect(self._access_changed)

    def ready(self) -> bool:
        """Require current screen permission before requesting keyboard input."""
        return self._ask(_Request(None, None), timeout_s=6) is True

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

    def find_visible_chat_choices(
        self, app_id: str, pid: int, target: str
    ) -> ChatSearchChoices | None:
        self._last_choice_status = "pending"
        result = self._ask(
            _Request(app_id, pid, target, choices=True, visible_choices=True),
            timeout_s=18,
        )
        if self._last_choice_status == "pending":
            self._last_choice_status = "timeout"
        return result if isinstance(result, ChatSearchChoices) else None

    def choice_status(self) -> str:
        """A content-free reason for the latest search-choice read."""
        return self._last_choice_status

    def find_left_label(
        self, app_id: str, pid: int, label: str, *, menu: bool = False
    ) -> ChatSearchMatch | None:
        result = self._ask(
            _Request(app_id, pid, label, left_label=True, menu=menu),
            timeout_s=18,
        )
        return result if isinstance(result, ChatSearchMatch) else None

    def find_settings_item(
        self, app_id: str, pid: int, label: str
    ) -> ChatSearchMatch | None:
        result = self._ask(
            _Request(app_id, pid, label, settings_item=True), timeout_s=18
        )
        return result if isinstance(result, ChatSearchMatch) else None

    def settings_page_header(self, app_id: str, pid: int) -> str | None:
        result = self._ask(
            _Request(app_id, pid, settings_header=True), timeout_s=18
        )
        return result if isinstance(result, str) else None

    def has_view_title(self, app_id: str, pid: int, title: str) -> bool:
        return self._ask(
            _Request(app_id, pid, title, view_title=True), timeout_s=18
        ) is True

    def has_search_query(self, app_id: str, pid: int, query: str) -> bool:
        return self._ask(
            _Request(app_id, pid, query, search_query=True), timeout_s=18
        ) is True

    def _ask(
        self, request: _Request, *, timeout_s: float
    ) -> bool | str | ChatSearchMatch | ChatSearchChoices | None:
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
            if available:
                request.result = True
                request.finished.set()
            elif (
                not self._access.granted
                and self._access.available
                and self._access.remembered
                and self._pending_ready is None
            ):
                self._pending_ready = request
                QTimer.singleShot(5000, lambda: self._finish_ready(request, False))
                self._access.request_session()
            else:
                request.result = False
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
        if request.menu:
            started = self._reader.read(language, region="left_menu")
        elif request.settings_header:
            started = self._reader.read(language, region="settings_header")
        elif request.settings_item or (
            request.view_title and request.target == "Settings"
        ):
            started = self._reader.read(language, region="settings_pane")
        else:
            started = (
                self._reader.read() if language is None else self._reader.read(language)
            )
        if not started and self._pending is request:
            self._finish(False)

    def _completed(self, observation: object) -> None:
        pending = self._pending
        if pending is None:
            return
        result: bool | str | ChatSearchMatch | ChatSearchChoices | None = None
        if (
            isinstance(observation, IdentifiedWindowText)
            and pending.app_id is not None
            and pending.pid is not None
            and (pending.target is not None or pending.settings_header)
        ):
            if pending.settings_header:
                result = telegram_settings_header(
                    observation, pending.app_id, pending.pid
                )
            elif pending.settings_item:
                assert pending.target is not None
                result = telegram_settings_item(
                    observation, pending.app_id, pending.pid, pending.target
                )
            elif pending.search_query:
                assert pending.target is not None
                result = telegram_search_query_visible(
                    observation, pending.app_id, pending.pid, pending.target
                )
            elif pending.view_title:
                assert pending.target is not None
                result = telegram_view_title_visible(
                    observation, pending.app_id, pending.pid, pending.target
                )
            elif pending.left_label:
                assert pending.target is not None
                result = (
                    telegram_menu_item(
                        observation, pending.app_id, pending.pid, pending.target
                    )
                    if pending.menu
                    else telegram_left_label(
                        observation, pending.app_id, pending.pid, pending.target
                    )
                )
            elif pending.choices:
                assert pending.target is not None
                visible_status: str | None = None
                if pending.visible_choices:
                    assessment = assess_visible_chat_choices(
                        observation, pending.app_id, pending.pid, pending.target
                    )
                    result = assessment.choices
                    visible_status = assessment.status
                    if visible_status not in {
                        "search_field_active", "window_changed"
                    } and (pending.visible_focused or result is not None):
                        suggestions = suggest_visible_chat_choices(
                            observation, pending.app_id, pending.pid, pending.target
                        )
                        if suggestions is not None and (
                            result is None or len(suggestions.local_results) > 1
                        ):
                            result = suggestions
                            visible_status = (
                                f"grounded_local_{len(result.local_results)}"
                            )
                else:
                    result = search_choices(
                        observation, pending.app_id, pending.pid, pending.target
                    )
                matches = (
                    find_literal_phrases(
                        observation.result,
                        pending.target,
                        allow_joined_words=True,
                    )
                    if pending.visible_choices
                    else find_exact_phrases(observation.result, pending.target)
                )
                size = observation.image_size or (0, 0)
                positions = (
                    "_".join(
                        f"{match.box.left}-{match.box.top}-"
                        f"{round(100 * (match.lowest_confidence or 0))}"
                        for match in matches[:6]
                    )
                    or "none"
                )
                detail = (
                    f"matches_{len(matches)}_size_{size[0]}x{size[1]}_at_{positions}"
                )
                self._last_choice_status = (
                    f"{visible_status}_{detail}"
                    if visible_status is not None
                    else (
                        f"classified_local_{len(result.local_results)}_"
                        f"global_{len(result.global_results)}_{detail}"
                        if isinstance(result, ChatSearchChoices)
                        else f"unclassified_{detail}"
                    )
                )
                if (
                    pending.visible_choices
                    and result is None
                    and visible_status not in {"search_field_active", "window_changed"}
                ):
                    target_is_persian = any(
                        "\u0600" <= char <= "\u06ff" for char in pending.target
                    )
                    if not pending.visible_focused:
                        pending.visible_focused = True
                        language = "fas+eng" if target_is_persian else "eng"
                    elif (
                        not pending.visible_bilingual
                        and not target_is_persian
                        and {"fas", "eng"}.issubset(
                            self._reader.supported_languages
                        )
                    ):
                        pending.visible_bilingual = True
                        language = "fas+eng"
                    else:
                        language = None
                    if language is not None and self._reader.read(
                        OcrOptions(language, layout="block"),
                        region="left_chat_list",
                    ):
                        return
            elif pending.search:
                assert pending.target is not None
                result = unique_search_result(
                    observation, pending.app_id, pending.pid, pending.target
                )
            else:
                assert pending.target is not None
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
        pending_ready = self._pending_ready
        if pending_ready is not None:
            self._finish_ready(
                pending_ready,
                granted and self._reader.available and not self._reader.busy,
            )
        if not granted:
            self._finish(False)

    def _finish_ready(self, request: _Request, ready: bool) -> None:
        if self._pending_ready is not request:
            return
        self._pending_ready = None
        if not request.finished.is_set():
            request.result = ready
            request.finished.set()

    def _finish(
        self, result: bool | str | ChatSearchMatch | ChatSearchChoices | None
    ) -> None:
        pending = self._pending
        self._pending = None
        if pending is not None:
            pending.result = result if not pending.finished.is_set() else None
            pending.finished.set()
