"""The Qt screen/OCR bridge remains read-only and rejects stale observations."""

# ruff: noqa: E402

from collections.abc import Callable
from pathlib import Path
from threading import Event, current_thread, main_thread
from time import monotonic, sleep
from typing import cast

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kyrin.app.qt.ocr_setup import installed_ocr_engine
from kyrin.app.qt.screen_access import ScreenAccess
from kyrin.app.qt.screen_access_page import ScreenAccessPage
from kyrin.app.qt.screen_text_reader import ScreenTextReader
from kyrin.app.qt.translations import UiTranslations
from kyrin.vision.ocr.contracts import (
    OcrCapabilities,
    OcrDevice,
    OcrOptions,
    OcrResult,
    RecognizedText,
    TextBox,
)
from kyrin.vision.screen_capture import IdentifiedWindowImage
from kyrin.vision.text_reader import IdentifiedWindowText

_IMAGE = IdentifiedWindowImage(
    "local.kyrin.KYRIN.desktop", 321, b"\x89PNG\r\n\x1a\nimage"
)


class FakeAccess(QObject):
    changed = Signal(bool)
    error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.available = True
        self.granted = True
        self.image: IdentifiedWindowImage | None = _IMAGE

    def capture(self, callback: Callable[[IdentifiedWindowImage | None], None]) -> None:
        callback(self.image)

    def revoke(self) -> None:
        self.granted = False
        self.changed.emit(False)


class FakeOcr:
    def __init__(self, wait: Event | None = None) -> None:
        self.wait = wait
        self.started = Event()
        self.used_worker = False

    @property
    def capabilities(self) -> OcrCapabilities:
        return OcrCapabilities(frozenset({OcrDevice.CPU}), frozenset({"eng"}))

    def recognize(self, image: bytes, options: OcrOptions) -> OcrResult:
        self.used_worker = current_thread() is not main_thread()
        self.started.set()
        if self.wait is not None:
            assert self.wait.wait(2)
        assert image == _IMAGE.image
        assert options.language == "eng"
        return OcrResult(
            (RecognizedText("Telegram", TextBox(1, 2, 30, 10), 0.9),),
            "eng",
            OcrDevice.CPU,
            "fake",
        )


def _app(monkeypatch: pytest.MonkeyPatch) -> QApplication:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])


def _until(app: QApplication, predicate: Callable[[], bool]) -> None:
    deadline = monotonic() + 3
    while monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        sleep(0.01)
    pytest.fail("screen text result did not arrive")


def test_observation_runs_off_ui_thread_and_page_shows_plain_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _app(monkeypatch)
    access = FakeAccess()
    engine = FakeOcr()
    reader = ScreenTextReader(
        cast(ScreenAccess, access),
        engine,
        lambda: (_IMAGE.platform_app_id, _IMAGE.process_id),
        OcrOptions("eng"),
    )
    page = ScreenAccessPage(
        cast(ScreenAccess, access), UiTranslations(tmp_path), reader
    )
    results: list[IdentifiedWindowText] = []
    reader.completed.connect(results.append)
    try:
        page.read_button.click()
        _until(app, lambda: bool(results))
        assert engine.used_worker
        assert page.read_output.toPlainText() == "Telegram"
        assert _IMAGE.platform_app_id in page.read_status.text()
        access.revoke()
        assert page.read_output.toPlainText() == ""
        assert not page.read_button.isEnabled()
    finally:
        reader.close()
        page.deleteLater()


def test_focus_change_discards_recognized_text(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app(monkeypatch)
    access = FakeAccess()
    reader = ScreenTextReader(
        cast(ScreenAccess, access),
        FakeOcr(),
        lambda: ("another.desktop", 999),
        OcrOptions("eng"),
    )
    results: list[object] = []
    errors: list[str] = []
    reader.completed.connect(results.append)
    reader.failed.connect(errors.append)
    try:
        assert reader.read()
        _until(app, lambda: bool(errors))
        assert errors == ["window_changed"]
        assert results == []
    finally:
        reader.close()


def test_revocation_discards_late_ocr_result(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app(monkeypatch)
    access = FakeAccess()
    release = Event()
    engine = FakeOcr(release)
    reader = ScreenTextReader(
        cast(ScreenAccess, access),
        engine,
        lambda: (_IMAGE.platform_app_id, _IMAGE.process_id),
        OcrOptions("eng"),
    )
    results: list[object] = []
    errors: list[str] = []
    reader.completed.connect(results.append)
    reader.failed.connect(errors.append)
    try:
        assert reader.read()
        assert engine.started.wait(1)
        access.revoke()
        release.set()
        _until(app, lambda: not reader.busy)
        assert errors == ["access_off"]
        assert results == []
    finally:
        release.set()
        reader.close()


def test_only_installed_local_ocr_runtime_is_discovered(tmp_path: Path) -> None:
    root = tmp_path / "tesseract"
    assert installed_ocr_engine(root) is None
    data = root / "runtime/usr/share/tesseract-ocr/5/tessdata"
    data.mkdir(parents=True)
    (data / "eng.traineddata").write_bytes(b"model")
    executable = root / "tesseract-local"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o700)
    engine = installed_ocr_engine(root)
    assert engine is not None
    assert engine.capabilities.supported_languages == frozenset({"eng"})
