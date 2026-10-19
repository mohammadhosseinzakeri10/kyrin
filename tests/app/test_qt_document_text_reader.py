"""Document OCR is a separate, read-only Qt path with stale-result rejection."""

from collections.abc import Callable
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from typing import cast

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kyrin.app.qt.document_text_reader import (  # noqa: E402
    DocumentObservation,
    DocumentTextReader,
)
from kyrin.app.qt.screen_access import ScreenAccess  # noqa: E402
from kyrin.app.qt.screen_access_page import ScreenAccessPage  # noqa: E402
from kyrin.app.qt.translations import UiTranslations  # noqa: E402
from kyrin.vision.ocr.backends.document import (  # noqa: E402
    DocumentOcrEngine,
    DocumentOcrTimeoutError,
)
from kyrin.vision.screen_capture import IdentifiedWindowImage  # noqa: E402


class FakeAccess(QObject):
    changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.granted = True

    def capture(self, callback: Callable[[IdentifiedWindowImage | None], None]) -> None:
        callback(
            IdentifiedWindowImage("telegram.desktop", 123, b"\x89PNG\r\n\x1a\npng")
        )


class FakeEngine:
    backend = "surya"

    def __init__(self, gate: Event) -> None:
        self.gate = gate

    def read_text(self, image: bytes) -> str:
        assert image == b"\x89PNG\r\n\x1a\npng"
        assert self.gate.wait(2)
        return "Open Telegram"


class TimeoutEngine:
    backend = "dots"

    def read_text(self, image: bytes) -> str:
        raise DocumentOcrTimeoutError("Document OCR process exceeded four minutes")


def _until(app: QApplication, predicate: Callable[[], bool]) -> None:
    deadline = monotonic() + 3
    while monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        sleep(0.01)
    pytest.fail("document read did not finish")


def test_document_reader_rejects_revoked_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    access = FakeAccess()
    gate = Event()
    reader = DocumentTextReader(
        cast(ScreenAccess, access),
        lambda _backend: cast(DocumentOcrEngine, FakeEngine(gate)),
        lambda: ("telegram.desktop", 123),
    )
    completed: list[DocumentObservation] = []
    failures: list[str] = []
    reader.completed.connect(completed.append)
    reader.failed.connect(failures.append)
    assert reader.read("surya")
    access.granted = False
    access.changed.emit(False)
    gate.set()
    _until(app, lambda: bool(failures))
    assert failures == ["access_off"]
    assert not completed
    reader.close()


def test_document_reader_requires_same_active_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    access = FakeAccess()
    gate = Event()
    reader = DocumentTextReader(
        cast(ScreenAccess, access),
        lambda _backend: cast(DocumentOcrEngine, FakeEngine(gate)),
        lambda: ("other.desktop", 456),
    )
    completed: list[DocumentObservation] = []
    failures: list[str] = []
    reader.completed.connect(completed.append)
    reader.failed.connect(failures.append)
    assert reader.read("surya")
    gate.set()
    _until(app, lambda: bool(failures))
    assert failures == ["window_changed"]
    assert not completed
    reader.close()


def test_document_reader_emits_text_only_for_the_same_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    access = FakeAccess()
    gate = Event()
    reader = DocumentTextReader(
        cast(ScreenAccess, access),
        lambda _backend: cast(DocumentOcrEngine, FakeEngine(gate)),
        lambda: ("telegram.desktop", 123),
    )
    completed: list[DocumentObservation] = []
    reader.completed.connect(completed.append)
    assert reader.read("surya")
    gate.set()
    _until(app, lambda: bool(completed))
    assert completed == [
        DocumentObservation("telegram.desktop", 123, "surya", "Open Telegram")
    ]
    assert not reader.busy
    reader.close()


def test_document_reader_reports_model_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    access = FakeAccess()
    reader = DocumentTextReader(
        cast(ScreenAccess, access),
        lambda _backend: cast(DocumentOcrEngine, TimeoutEngine()),
        lambda: ("telegram.desktop", 123),
    )
    failures: list[str] = []
    reader.failed.connect(failures.append)
    assert reader.read("dots")
    _until(app, lambda: bool(failures))
    assert failures == ["ocr_timeout"]
    assert not reader.busy
    reader.close()


def test_page_lists_complete_document_models_separately(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    assert app is not None
    models = tmp_path / "models"
    runtimes = tmp_path / "runtimes"
    for _backend, folder, runtime, weights in (
        ("surya", "surya/surya-ocr-2", "document-vlm5", ("model.safetensors",)),
        ("glm", "glm-ocr/bf16", "document-vlm5", ("model.safetensors",)),
        (
            "dots",
            "dots-mocr/model",
            "document-dots",
            (
                "model-00001-of-00002.safetensors",
                "model-00002-of-00002.safetensors",
                "model.safetensors.index.json",
                "modeling_dots_ocr.py",
            ),
        ),
    ):
        model = models / folder
        model.mkdir(parents=True)
        for name in ("config.json", *weights):
            (model / name).write_bytes(b"ready")
        python = runtimes / runtime / "bin/python"
        python.parent.mkdir(parents=True, exist_ok=True)
        python.write_text("#!/bin/sh\n", encoding="utf-8")
        python.chmod(0o700)
    page = ScreenAccessPage(
        None,
        UiTranslations(tmp_path),
        ocr_candidates_root=models,
        document_runtimes_root=runtimes,
    )
    assert [page.document_backend.itemData(i) for i in range(3)] == [
        "surya",
        "glm",
        "dots",
    ]
    assert not page.document_button.isEnabled()
    page.close()


def test_screen_page_clears_each_read_result_independently(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    assert app is not None
    translations = UiTranslations(tmp_path)
    page = ScreenAccessPage(None, translations)
    try:
        page.read_output.setPlainText("screen result")
        page.document_output.setPlainText("document result")
        page.clear_read_button.click()
        assert not page.read_output.toPlainText()
        assert page.document_output.toPlainText() == "document result"
        assert page.read_status.text() == translations.text("screen_read_hint")
        page.clear_document_button.click()
        assert not page.document_output.toPlainText()
        assert page.document_status.text() == translations.text(
            "screen_document_ready"
        )
        page._read_busy_changed(True)
        page._document_busy_changed(True)
        assert not page.clear_read_button.isEnabled()
        assert not page.clear_document_button.isEnabled()
        page._read_busy_changed(False)
        page._document_busy_changed(False)
        assert page.clear_read_button.isEnabled()
        assert page.clear_document_button.isEnabled()
    finally:
        page.close()


def test_document_empty_result_identifies_model_and_captured_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    assert app is not None
    page = ScreenAccessPage(None, UiTranslations(tmp_path))
    try:
        page._document_completed(
            DocumentObservation("kyrin.desktop", 123, "surya", "")
        )
        assert "surya" in page.document_status.text()
        assert "kyrin.desktop" in page.document_status.text()
        assert not page.document_output.toPlainText()
    finally:
        page.close()


def test_document_page_shows_elapsed_time_and_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    assert app is not None
    page = ScreenAccessPage(None, UiTranslations(tmp_path))
    try:
        page.document_backend.addItem("dots.mocr", "dots")
        page._document_busy_changed(True)
        assert page._document_timer.isActive()
        assert "dots" in page.document_status.text()
        assert "0 seconds" in page.document_status.text()
        assert not page.document_backend.isEnabled()
        page._document_busy_changed(False)
        assert not page._document_timer.isActive()
        assert page.document_backend.isEnabled()
        page._document_failed("ocr_timeout")
        assert "4 minutes" in page.document_status.text()
    finally:
        page.close()
