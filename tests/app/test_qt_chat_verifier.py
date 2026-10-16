"""The action worker cannot read a Qt-owned screen grant directly."""

# ruff: noqa: E402

from collections.abc import Callable
from threading import Thread, current_thread, main_thread
from time import monotonic, sleep
from typing import cast

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QObject, Signal  # noqa: E402
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
        self.last_options: OcrOptions | None = None

    def read(self, options: OcrOptions | None = None) -> bool:
        self.last_options = options
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
        lambda: verifier.find_search_result("telegram.desktop", 123, "Alice")
        is not None,
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
