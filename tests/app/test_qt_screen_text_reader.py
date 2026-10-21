"""The Qt screen/OCR bridge remains read-only and rejects stale observations."""

# ruff: noqa: E402

from collections.abc import Callable
from pathlib import Path
from threading import Event, current_thread, main_thread
from time import monotonic, sleep
from typing import cast

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, Signal  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kyrin.app.qt.ocr_setup import installed_ocr_engine, selected_ocr_engine
from kyrin.app.qt.screen_access import ScreenAccess
from kyrin.app.qt.screen_access_page import ScreenAccessPage
from kyrin.app.qt.screen_text_reader import (
    ScreenTextReader,
    _chat_list_png,
    _crop_png,
    _left_menu_png,
)
from kyrin.app.qt.translations import UiTranslations
from kyrin.app.settings import OcrSelection
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
        self.remembered = False
        self.image: IdentifiedWindowImage | None = _IMAGE

    def capture(self, callback: Callable[[IdentifiedWindowImage | None], None]) -> None:
        callback(self.image)

    def revoke(self) -> None:
        self.granted = False
        self.changed.emit(False)


class FakeOcr:
    def __init__(
        self,
        wait: Event | None = None,
        *,
        expected_language: str = "eng",
        expected_image: bytes = _IMAGE.image,
    ) -> None:
        self.wait = wait
        self.expected_language = expected_language
        self.expected_image = expected_image
        self.started = Event()
        self.used_worker = False

    @property
    def capabilities(self) -> OcrCapabilities:
        return OcrCapabilities(
            frozenset({OcrDevice.CPU}), frozenset({"eng", "fas"})
        )

    def recognize(self, image: bytes, options: OcrOptions) -> OcrResult:
        self.used_worker = current_thread() is not main_thread()
        self.started.set()
        if self.wait is not None:
            assert self.wait.wait(2)
        assert image == self.expected_image
        assert options.language == self.expected_language
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


def _valid_png() -> bytes:
    image = QImage(1000, 800, QImage.Format.Format_RGB888)
    image.fill(0x202020)
    output = QByteArray()
    buffer = QBuffer(output)
    assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    return bytes(output)


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


def test_one_read_can_override_default_ocr_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(monkeypatch)
    access = FakeAccess()
    engine = FakeOcr(expected_language="fas+eng")
    reader = ScreenTextReader(
        cast(ScreenAccess, access),
        engine,
        lambda: (_IMAGE.platform_app_id, _IMAGE.process_id),
        OcrOptions("eng"),
    )
    results: list[IdentifiedWindowText] = []
    reader.completed.connect(results.append)
    try:
        assert reader.supported_languages == frozenset({"eng", "fas"})
        assert reader.read(OcrOptions("fas+eng"))
        _until(app, lambda: bool(results))
        assert engine.used_worker
    finally:
        reader.close()


def test_single_language_engine_becomes_default_after_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app(monkeypatch)

    class SpanishOcr(FakeOcr):
        @property
        def capabilities(self) -> OcrCapabilities:
            return OcrCapabilities(
                frozenset({OcrDevice.CPU}), frozenset({"spa"})
            )

    reader = ScreenTextReader(
        cast(ScreenAccess, FakeAccess()), FakeOcr(),
        lambda: (_IMAGE.platform_app_id, _IMAGE.process_id), OcrOptions("eng"),
    )
    try:
        reader.set_engine(SpanishOcr(expected_language="spa"))
        assert reader.default_language == "spa"
    finally:
        reader.close()


def test_menu_region_ocr_keeps_full_window_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(monkeypatch)
    image = _valid_png()
    cropped = _left_menu_png(image)
    assert cropped is not None
    access = FakeAccess()
    access.image = IdentifiedWindowImage(
        _IMAGE.platform_app_id, _IMAGE.process_id, image
    )
    engine = FakeOcr(expected_image=cropped)
    reader = ScreenTextReader(
        cast(ScreenAccess, access),
        engine,
        lambda: (_IMAGE.platform_app_id, _IMAGE.process_id),
        OcrOptions("eng"),
    )
    results: list[IdentifiedWindowText] = []
    reader.completed.connect(results.append)
    try:
        assert reader.read(region="left_menu")
        _until(app, lambda: bool(results))
        assert results[0].image_size == (1000, 800)
        assert engine.used_worker
    finally:
        reader.close()


def test_settings_region_ocr_restores_window_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(monkeypatch)
    image = _valid_png()
    cropped = _crop_png(image, "settings_pane")
    assert cropped is not None
    cropped_image, left = cropped
    access = FakeAccess()
    access.image = IdentifiedWindowImage(
        _IMAGE.platform_app_id, _IMAGE.process_id, image
    )
    reader = ScreenTextReader(
        cast(ScreenAccess, access),
        FakeOcr(expected_image=cropped_image),
        lambda: (_IMAGE.platform_app_id, _IMAGE.process_id),
        OcrOptions("eng"),
    )
    results: list[IdentifiedWindowText] = []
    reader.completed.connect(results.append)
    try:
        assert reader.read(region="settings_pane")
        _until(app, lambda: bool(results))
        assert results[0].image_size == (1000, 800)
        assert results[0].result.spans[0].box.left == left + 1
    finally:
        reader.close()


def test_visible_list_region_magnifies_and_restores_window_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(monkeypatch)
    image = _valid_png()
    focused = _chat_list_png(image)
    assert focused is not None
    magnified = QImage.fromData(focused)
    assert (magnified.width(), magnified.height()) == (720, 1600)
    access = FakeAccess()
    access.image = IdentifiedWindowImage(
        _IMAGE.platform_app_id, _IMAGE.process_id, image
    )
    reader = ScreenTextReader(
        cast(ScreenAccess, access),
        FakeOcr(expected_image=focused),
        lambda: (_IMAGE.platform_app_id, _IMAGE.process_id),
        OcrOptions("eng"),
    )
    results: list[IdentifiedWindowText] = []
    reader.completed.connect(results.append)
    try:
        assert reader.read(OcrOptions("eng", layout="block"), region="left_chat_list")
        _until(app, lambda: bool(results))
        assert results[0].image_size == (1000, 800)
        assert results[0].result.spans[0].box.top == 1
        assert results[0].result.spans[0].box.width == 15
    finally:
        reader.close()


def test_fast_list_and_chat_header_crops_keep_window_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(monkeypatch)
    image = _valid_png()
    access = FakeAccess()
    access.image = IdentifiedWindowImage(
        _IMAGE.platform_app_id, _IMAGE.process_id, image
    )
    for region, expected_size, expected_left in (
        ("left_chat_list_fast", (360, 800), 0),
        ("chat_header", (700, 160), 300),
    ):
        focused = _crop_png(image, region)
        assert focused is not None
        assert QImage.fromData(focused[0]).size().toTuple() == expected_size
        reader = ScreenTextReader(
            cast(ScreenAccess, access),
            FakeOcr(expected_image=focused[0]),
            lambda: (_IMAGE.platform_app_id, _IMAGE.process_id),
            OcrOptions("eng"),
        )
        results: list[IdentifiedWindowText] = []
        reader.completed.connect(results.append)
        try:
            assert reader.read(region=region)
            _until(app, lambda results=results: bool(results))
            assert results[0].image_size == (1000, 800)
            assert results[0].result.spans[0].box.left == expected_left + 1
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


def test_engine_change_discards_old_result_and_uses_new_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(monkeypatch)
    access = FakeAccess()
    release = Event()
    old_engine = FakeOcr(release)
    new_engine = FakeOcr()
    reader = ScreenTextReader(
        cast(ScreenAccess, access),
        old_engine,
        lambda: (_IMAGE.platform_app_id, _IMAGE.process_id),
        OcrOptions("eng"),
    )
    results: list[object] = []
    reader.completed.connect(results.append)
    try:
        assert reader.read()
        assert old_engine.started.wait(1)
        reader.set_engine(new_engine)
        assert not reader.busy
        assert reader.read()
        _until(app, lambda: bool(results))
        assert new_engine.used_worker
        release.set()
        app.processEvents()
        assert len(results) == 1
    finally:
        release.set()
        reader.close()


def test_engine_becomes_available_without_reopening_screen_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _app(monkeypatch)
    access = FakeAccess()
    reader = ScreenTextReader(
        cast(ScreenAccess, access),
        None,
        lambda: (_IMAGE.platform_app_id, _IMAGE.process_id),
        OcrOptions("eng"),
    )
    page = ScreenAccessPage(
        cast(ScreenAccess, access), UiTranslations(tmp_path), reader
    )
    try:
        assert not page.read_button.isEnabled()
        reader.set_engine(FakeOcr())
        page.translate()
        assert page.read_button.isEnabled()
    finally:
        reader.close()
        page.deleteLater()


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
    assert selected_ocr_engine(None, root) is not None
    assert selected_ocr_engine(OcrSelection("tesseract", root), tmp_path) is not None
    assert selected_ocr_engine(OcrSelection("unknown", root), tmp_path) is None


def test_selected_tesseract_language_pack_uses_installed_executable(
    tmp_path: Path,
) -> None:
    root = tmp_path / "installed"
    root.mkdir()
    executable = root / "tesseract-local"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o700)
    tessdata = tmp_path / "best"
    tessdata.mkdir()
    for language in ("eng", "fas"):
        (tessdata / f"{language}.traineddata").write_bytes(b"model")

    engine = selected_ocr_engine(OcrSelection("tesseract", tessdata), root)

    assert engine is not None
    assert engine.capabilities.supported_languages == frozenset({"eng", "fas"})


def test_selected_single_language_tesseract_does_not_require_english(
    tmp_path: Path,
) -> None:
    root = tmp_path / "installed"
    root.mkdir()
    executable = root / "tesseract-local"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o700)
    tessdata = tmp_path / "spanish"
    tessdata.mkdir()
    (tessdata / "spa.traineddata").write_bytes(b"model")

    engine = selected_ocr_engine(OcrSelection("tesseract", tessdata), root)

    assert engine is not None
    assert engine.capabilities.supported_languages == frozenset({"spa"})
