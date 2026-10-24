"""The action worker cannot read a Qt-owned screen grant directly."""

# ruff: noqa: E402

from collections.abc import Callable
from threading import Thread, current_thread, main_thread
from time import monotonic, sleep
from typing import cast

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QObject, QTimer, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kyrin.actions.telegram_verification import ChatSearchMatch
from kyrin.app.qt.chat_verifier import QtChatVerifier
from kyrin.app.qt.screen_access import ScreenAccess
from kyrin.app.qt.screen_text_reader import ScreenTextReader
from kyrin.vision.ocr.contracts import (
    OcrDevice,
    OcrOptions,
    OcrResult,
    RecognizedText,
    TextBox,
)
from kyrin.vision.text_reader import IdentifiedWindowText


class Access(QObject):
    changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.granted = True
        self.available = True
        self.remembered = False
        self.request_count = 0

    def request_session(self) -> None:
        self.request_count += 1


class Reader(QObject):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, observation: IdentifiedWindowText) -> None:
        super().__init__()
        self.available = True
        self.busy = False
        self.observation = observation
        self.read_on_ui_thread = False
        self.supported_languages = frozenset({"eng", "fas"})
        self.default_language = "eng"
        self.last_options: OcrOptions | None = None
        self.last_region: str | None = None

    def read(
        self, options: OcrOptions | None = None, *, region: str | None = None
    ) -> bool:
        self.last_options = options
        self.last_region = region
        self.read_on_ui_thread = current_thread() is main_thread()
        self.completed.emit(self.observation)
        return True


def _observation() -> IdentifiedWindowText:
    return IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(
            (
                RecognizedText("Saved", TextBox(700, 40, 60, 24), 0.9),
                RecognizedText("Messages", TextBox(767, 40, 105, 24), 0.9),
            ),
            "eng",
            OcrDevice.CPU,
            "fake",
        ),
        (1600, 900),
    )


def _call_from_worker(app: QApplication, work: Callable[[], bool]) -> bool:
    values: list[bool] = []
    thread = Thread(target=lambda: values.append(work()))
    thread.start()
    deadline = monotonic() + 3
    while thread.is_alive() and monotonic() < deadline:
        app.processEvents()
        sleep(0.005)
    thread.join(timeout=0.1)
    assert not thread.is_alive()
    return values[0]


def test_verifier_uses_ui_thread_and_requires_current_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    access = Access()
    reader = Reader(_observation())
    verifier = QtChatVerifier(
        cast(ScreenAccess, access), cast(ScreenTextReader, reader)
    )
    assert _call_from_worker(app, verifier.ready)
    assert _call_from_worker(app, lambda: verifier.verify("telegram.desktop", 123))
    assert reader.read_on_ui_thread
    assert not _call_from_worker(app, lambda: verifier.verify("telegram.desktop", 999))
    access.granted = False
    access.changed.emit(False)
    assert not _call_from_worker(app, verifier.ready)
    assert not _call_from_worker(app, lambda: verifier.verify("telegram.desktop", 123))


def test_ready_restores_remembered_screen_session_before_chat_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    access = Access()
    access.granted = False
    access.remembered = True
    verifier = QtChatVerifier(
        cast(ScreenAccess, access), cast(ScreenTextReader, Reader(_observation()))
    )

    def grant() -> None:
        access.granted = True
        access.changed.emit(True)

    QTimer.singleShot(25, grant)
    assert _call_from_worker(app, verifier.ready)
    assert access.request_count == 1


def test_search_result_is_only_returned_for_unique_left_pane_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    access = Access()
    reader = Reader(
        IdentifiedWindowText(
            "telegram.desktop",
            123,
            OcrResult(
                (
                    RecognizedText("Alice", TextBox(70, 45, 90, 13), 0.91),
                    RecognizedText("Alice", TextBox(70, 92, 90, 13), 0.91),
                ),
                "eng",
                OcrDevice.CPU,
                "fake",
            ),
            (1600, 900),
        )
    )
    verifier = QtChatVerifier(
        cast(ScreenAccess, access), cast(ScreenTextReader, reader)
    )
    result: list[ChatSearchMatch | None] = []

    def work() -> bool:
        result.append(verifier.find_search_result("telegram.desktop", 123, "Alice"))
        return True

    assert _call_from_worker(app, work)
    assert result[0] is not None
    assert result[0].top == 92
    assert _call_from_worker(
        app,
        lambda: verifier.find_search_result("telegram.desktop", 123, "Bob") is None,
    )


def test_visible_chat_choice_uses_current_list_without_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    reader = Reader(
        IdentifiedWindowText(
            "telegram.desktop",
            123,
            OcrResult(
                (
                    RecognizedText("Search", TextBox(60, 45, 70, 16), 0.90),
                    RecognizedText("My", TextBox(70, 200, 25, 18), 0.92),
                    RecognizedText("Mother", TextBox(100, 200, 65, 18), 0.91),
                    RecognizedText("8:12", TextBox(455, 200, 42, 16), 0.82),
                    RecognizedText("Hello", TextBox(70, 227, 60, 15), 0.88),
                ),
                "eng",
                OcrDevice.CPU,
                "fake",
            ),
            (1600, 900),
        )
    )
    verifier = QtChatVerifier(
        cast(ScreenAccess, Access()), cast(ScreenTextReader, reader)
    )
    assert _call_from_worker(
        app,
        lambda: (
            (
                choices := verifier.find_visible_chat_choices(
                    "telegram.desktop", 123, "My Mother"
                )
            )
            is not None
            and choices.source == "visible"
        ),
    )
    assert reader.read_on_ui_thread
    assert reader.last_region == "left_chat_list_fast"


def test_visible_chat_retries_magnified_ocr_after_uncertain_fast_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])

    class TwoReads(Reader):
        def __init__(self) -> None:
            super().__init__(_observation())
            self.regions: list[str | None] = []

        def read(
            self, options: OcrOptions | None = None, *, region: str | None = None
        ) -> bool:
            self.regions.append(region)
            if region == "left_chat_list":
                self.observation = IdentifiedWindowText(
                    "telegram.desktop",
                    123,
                    OcrResult(
                        (
                            RecognizedText("Spotify", TextBox(88, 935, 44, 13), 0.86),
                            RecognizedText(
                                "Downloader", TextBox(136, 935, 76, 10), 0.96
                            ),
                            RecognizedText("10/6/26", TextBox(606, 936, 45, 9), 0.96),
                            RecognizedText("Preview", TextBox(92, 959, 60, 10), 0.96),
                        ),
                        "eng",
                        OcrDevice.CPU,
                        "fake",
                    ),
                    (1853, 1048),
                )
            return super().read(options, region=region)

    reader = TwoReads()
    verifier = QtChatVerifier(
        cast(ScreenAccess, Access()), cast(ScreenTextReader, reader)
    )
    assert _call_from_worker(
        app,
        lambda: (
            verifier.find_visible_chat_choices(
                "telegram.desktop", 123, "Spotify Downloader"
            )
            is not None
        ),
    )
    assert reader.regions == ["left_chat_list_fast", "left_chat_list"]
    assert reader.last_options == OcrOptions("eng+fas", layout="block")


def test_misheard_matin_uses_full_read_before_focused_ocr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sparse pass can retain the row's date when the block pass loses it."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(
            (
                RecognizedText("matin", TextBox(66, 872, 33, 22), 0.94),
                RecognizedText("10/3/26", TextBox(606, 880, 45, 9), 0.96),
                RecognizedText("fragment", TextBox(545, 842, 12, 9), 0.78),
                RecognizedText("unreadable", TextBox(68, 904, 70, 9), 0.29),
            ),
            "eng",
            OcrDevice.CPU,
            "fake",
        ),
        (1853, 1048),
    )
    reader = Reader(observation)
    verifier = QtChatVerifier(
        cast(ScreenAccess, Access()), cast(ScreenTextReader, reader)
    )
    choices = _call_from_worker(
        app,
        lambda: verifier.find_visible_chat_choices("telegram.desktop", 123, "martin"),
    )
    assert choices is not None
    assert choices.grounded_titles == ("matin",)
    assert reader.last_region == "left_chat_list_fast"


def test_visible_chat_starts_bilingual_for_romanized_persian_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])

    class BilingualReads(Reader):
        def __init__(self) -> None:
            super().__init__(_observation())
            self.reads: list[tuple[str | None, str | None]] = []

        def read(
            self, options: OcrOptions | None = None, *, region: str | None = None
        ) -> bool:
            self.reads.append((region, options.language if options else None))
            if options is not None and options.language == "eng+fas":
                self.observation = IdentifiedWindowText(
                    "telegram.desktop",
                    123,
                    OcrResult(
                        (
                            RecognizedText(
                                "ابوالفضل عبادی", TextBox(70, 200, 130, 18), 0.95
                            ),
                            RecognizedText("8:12", TextBox(455, 200, 42, 16), 0.9),
                            RecognizedText("Hello", TextBox(70, 227, 60, 15), 0.9),
                        ),
                        "eng+fas",
                        OcrDevice.CPU,
                        "fake",
                    ),
                    (1600, 900),
                )
            return super().read(options, region=region)

    reader = BilingualReads()
    verifier = QtChatVerifier(
        cast(ScreenAccess, Access()), cast(ScreenTextReader, reader)
    )
    choices = _call_from_worker(
        app,
        lambda: verifier.find_visible_chat_choices(
            "telegram.desktop", 123, "a bullfazle a body"
        ),
    )
    assert choices is not None
    assert choices.grounded_titles == ("ابوالفضل عبادی",)
    assert reader.reads == [("left_chat_list_fast", "eng+fas")]


@pytest.mark.parametrize(
    ("languages", "expected"),
    [
        (frozenset({"spa"}), "spa"),
        (frozenset({"deu", "eng", "fas", "osd"}), "eng+deu+fas"),
    ],
)
def test_visible_chat_uses_selected_ocr_capabilities(
    monkeypatch: pytest.MonkeyPatch,
    languages: frozenset[str],
    expected: str,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    reader = Reader(
        IdentifiedWindowText(
            "telegram.desktop",
            123,
            OcrResult(
                (
                    RecognizedText("My Mother", TextBox(70, 200, 100, 18), 0.95),
                    RecognizedText("8:12", TextBox(455, 200, 42, 16), 0.9),
                    RecognizedText("Hello", TextBox(70, 227, 60, 15), 0.9),
                ),
                "eng",
                OcrDevice.CPU,
                "fake",
            ),
            (1600, 900),
        )
    )
    reader.supported_languages = languages
    verifier = QtChatVerifier(
        cast(ScreenAccess, Access()), cast(ScreenTextReader, reader)
    )
    _call_from_worker(
        app,
        lambda: verifier.find_visible_chat_choices(
            "telegram.desktop", 123, "My Mother"
        ),
    )
    assert reader.last_region == "left_chat_list_fast"
    assert reader.last_options == OcrOptions(expected)


def test_exact_visible_name_still_asks_when_another_title_sounds_similar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(
            (
                RecognizedText("matin", TextBox(70, 200, 80, 18), 0.95),
                RecognizedText("8:12", TextBox(455, 200, 42, 16), 0.9),
                RecognizedText("Hello", TextBox(70, 227, 60, 15), 0.9),
                RecognizedText("martin", TextBox(70, 280, 80, 18), 0.95),
                RecognizedText("8:15", TextBox(455, 280, 42, 16), 0.9),
                RecognizedText("Hello", TextBox(70, 307, 60, 15), 0.9),
            ),
            "eng",
            OcrDevice.CPU,
            "fake",
        ),
        (1600, 900),
    )
    verifier = QtChatVerifier(
        cast(ScreenAccess, Access()), cast(ScreenTextReader, Reader(observation))
    )
    choices = _call_from_worker(
        app,
        lambda: verifier.find_visible_chat_choices("telegram.desktop", 123, "martin"),
    )
    assert choices is not None
    assert choices.grounded_titles == ("matin", "martin")


def test_menu_verification_requests_left_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    reader = Reader(_observation())
    verifier = QtChatVerifier(
        cast(ScreenAccess, Access()), cast(ScreenTextReader, reader)
    )
    assert _call_from_worker(
        app,
        lambda: (
            verifier.find_left_label("telegram.desktop", 123, "Settings", menu=True)
            is None
        ),
    )
    assert reader.last_region == "left_menu"


def test_generic_visible_control_reads_full_focused_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    reader = Reader(
        IdentifiedWindowText(
            "example.desktop",
            42,
            OcrResult(
                (RecognizedText("Advanced", TextBox(60, 220, 90, 18), 0.95),),
                "eng",
                OcrDevice.CPU,
                "fake",
            ),
            (800, 600),
        )
    )
    verifier = QtChatVerifier(
        cast(ScreenAccess, Access()), cast(ScreenTextReader, reader)
    )
    result = _call_from_worker(
        app,
        lambda: verifier.find_visible_control("example.desktop", 42, "advanced"),
    )
    assert result is not None
    assert (result.left, result.top) == (60, 220)
    assert reader.last_region is None
    assert reader.last_options == OcrOptions("eng")
    assert _call_from_worker(
        app,
        lambda: verifier.find_visible_control("example.desktop", 42, "تنظیمات"),
    ) is None
    assert reader.last_options == OcrOptions("eng+fas")


def test_settings_verification_requests_center_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    reader = Reader(_observation())
    verifier = QtChatVerifier(
        cast(ScreenAccess, Access()), cast(ScreenTextReader, reader)
    )
    assert _call_from_worker(
        app,
        lambda: (
            verifier.find_settings_item("telegram.desktop", 123, "My Account") is None
        ),
    )
    assert reader.last_region == "settings_pane"
    assert not _call_from_worker(
        app, lambda: verifier.has_view_title("telegram.desktop", 123, "Settings")
    )
    assert reader.last_region == "settings_pane"


def test_settings_page_header_uses_narrow_center_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    reader = Reader(
        IdentifiedWindowText(
            "telegram.desktop",
            123,
            OcrResult(
                (RecognizedText("Advanced", TextBox(790, 86, 80, 16), 0.96),),
                "eng",
                OcrDevice.CPU,
                "fake",
            ),
            (1853, 1048),
        )
    )
    verifier = QtChatVerifier(
        cast(ScreenAccess, Access()), cast(ScreenTextReader, reader)
    )
    assert _call_from_worker(
        app,
        lambda: verifier.settings_page_header("telegram.desktop", 123) == "advanced",
    )
    assert reader.last_region == "settings_header"


def test_search_choices_keep_local_and_global_rows_separate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    reader = Reader(
        IdentifiedWindowText(
            "telegram.desktop",
            123,
            OcrResult(
                (
                    RecognizedText("Alice", TextBox(70, 45, 90, 13), 0.91),
                    RecognizedText("Alice", TextBox(70, 92, 90, 13), 0.91),
                    RecognizedText("Alice", TextBox(70, 182, 90, 13), 0.91),
                    RecognizedText("Alice", TextBox(70, 244, 90, 13), 0.91),
                ),
                "eng",
                OcrDevice.CPU,
                "fake",
            ),
            (1600, 900),
        )
    )
    verifier = QtChatVerifier(
        cast(ScreenAccess, Access()), cast(ScreenTextReader, reader)
    )
    choices = []

    def work() -> bool:
        choices.append(verifier.find_search_choices("telegram.desktop", 123, "alice"))
        return True

    assert _call_from_worker(app, work)
    assert choices[0] is not None
    assert choices[0].own_chat is not None
    assert choices[0].own_chat.top == 92
    assert tuple(row.top for row in choices[0].global_results) == (182, 244)
    assert verifier.choice_status().startswith(
        "classified_local_1_global_2_matches_4_size_1600x900_at_"
    )
    assert _call_from_worker(
        app,
        lambda: (
            verifier.find_search_result("telegram.desktop", 123, "Alice") is not None
        ),
    )


def test_persian_chat_uses_bilingual_ocr_only_when_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    access = Access()
    reader = Reader(_observation())
    verifier = QtChatVerifier(
        cast(ScreenAccess, access), cast(ScreenTextReader, reader)
    )

    def search() -> bool:
        result = verifier.find_search_result("telegram.desktop", 123, "دانشگاه")
        return result is not None

    assert not _call_from_worker(app, search)
    assert reader.last_options == OcrOptions("fas+eng")
    reader.supported_languages = frozenset({"eng"})
    reader.last_options = None
    assert not _call_from_worker(app, search)
    assert reader.last_options is None


def test_late_completion_never_starts_visible_ocr_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kyrin.app.qt.chat_verifier import _Request

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    access = Access()
    reader = Reader(_observation())
    calls: list[object] = []
    reader.read = lambda *args, **kwargs: calls.append(args) or True
    verifier = QtChatVerifier(
        cast(ScreenAccess, access), cast(ScreenTextReader, reader)
    )
    request = _Request(
        "telegram.desktop", 123, "Absent", choices=True, visible_choices=True
    )
    verifier._start(request)
    assert len(calls) == 1
    # The caller has already stopped waiting. A queued worker callback arrives.
    request.finished.set()
    verifier._completed(_observation())
    assert len(calls) == 1
    assert verifier._pending is None
    assert request.result is None
    assert app is not None


def test_caller_timeout_cancels_carried_budget_and_clears_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kyrin.app.qt.chat_verifier import _Request
    from kyrin.operations import current_operation

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    access = Access()
    reader = Reader(_observation())
    carried = []
    cancelled = []
    reader.read = lambda *args, **kwargs: carried.append(current_operation()) or True
    reader.cancel = lambda operation: cancelled.append(operation)
    verifier = QtChatVerifier(
        cast(ScreenAccess, access), cast(ScreenTextReader, reader)
    )
    request = _Request(
        "telegram.desktop", 123, "Absent", choices=True, visible_choices=True
    )
    assert not _call_from_worker(app, lambda: verifier._ask(request, timeout_s=0.05))
    app.processEvents()
    assert len(carried) == 1
    assert carried[0] is request.operation
    assert request.operation is not None and request.operation.stopped
    assert cancelled == [request.operation]
    assert verifier._pending is None
    verifier._completed(_observation())
    assert len(carried) == 1
