"""Bridge Qt's asynchronous screen grant to replaceable, offline OCR."""

from collections.abc import Callable
from struct import unpack_from
from threading import Thread
from typing import Literal

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, Signal
from PySide6.QtGui import QImage

from kyrin.app.qt.screen_access import ScreenAccess
from kyrin.vision.ocr.contracts import (
    OcrEngine,
    OcrOptions,
    OcrResult,
    RecognizedText,
    TextBox,
)
from kyrin.vision.screen_capture import IdentifiedWindowImage
from kyrin.vision.text_reader import IdentifiedWindowText

WindowIdentityReader = Callable[[], tuple[str, int] | None]
ReadRegion = Literal[
    "left_menu", "left_chat_list", "left_chat_list_fast", "chat_header",
    "settings_pane", "settings_header"
] | None


def _png_size(image: bytes) -> tuple[int, int] | None:
    if len(image) < 24 or image[12:16] != b"IHDR":
        return None
    width, height = unpack_from(">II", image, 16)
    if not (0 < width <= 20000 and 0 < height <= 20000):
        return None
    return width, height


def _crop_png(image: bytes, region: ReadRegion) -> tuple[bytes, int] | None:
    """Return a focused OCR image and its horizontal window offset."""
    source = QImage.fromData(image)
    if source.isNull() or source.width() < 300 or source.height() < 300:
        return None
    if region == "left_menu":
        left, width, height = 0, int(source.width() * 0.3), int(source.height() * 0.65)
    elif region == "left_chat_list_fast":
        left, width, height = 0, int(source.width() * 0.36), source.height()
    elif region == "chat_header":
        left = int(source.width() * 0.3)
        width, height = source.width() - left, int(source.height() * 0.2)
    elif region == "settings_pane":
        width = min(source.width(), max(430, int(source.width() * 0.23)))
        left, height = (source.width() - width) // 2, int(source.height() * 0.85)
    elif region == "settings_header":
        width = min(source.width(), 350)
        left, height = (source.width() - width) // 2, int(source.height() * 0.85)
    else:
        return None
    cropped = source.copy(left, 0, max(1, width), max(1, height)).convertToFormat(
        QImage.Format.Format_RGB888
    )
    output = QByteArray()
    buffer = QBuffer(output)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        return None
    try:
        if not cropped.save(buffer, "PNG"):  # type: ignore[call-overload]
            return None
        return bytes(output.data()), left
    finally:
        buffer.close()


def _chat_list_png(image: bytes) -> bytes | None:
    """Magnify Telegram's narrow chat column for short and low rows."""
    source = QImage.fromData(image)
    if source.isNull() or source.width() < 300 or source.height() < 300:
        return None
    width = min(source.width(), int(source.width() * 0.36))
    cropped = source.copy(0, 0, width, source.height()).scaled(
        width * 2, source.height() * 2
    ).convertToFormat(QImage.Format.Format_RGB888)
    output = QByteArray()
    buffer = QBuffer(output)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        return None
    try:
        if not cropped.save(buffer, "PNG"):  # type: ignore[call-overload]
            return None
        return bytes(output.data())
    finally:
        buffer.close()


def _left_menu_png(image: bytes) -> bytes | None:
    """Keep the existing menu-only image helper for its callers."""
    cropped = _crop_png(image, "left_menu")
    return cropped[0] if cropped is not None else None


def _window_coordinates(result: OcrResult, left: int, scale: int = 1) -> OcrResult:
    if left == 0 and scale == 1:
        return result
    return OcrResult(
        tuple(
            RecognizedText(
                span.text,
                TextBox(
                    span.box.left // scale + left,
                    span.box.top // scale,
                    max(1, span.box.width // scale),
                    max(1, span.box.height // scale),
                ),
                span.confidence,
            )
            for span in result.spans
        ),
        result.language,
        result.device,
        result.engine_id,
    )


class _WorkerEvents(QObject):
    completed = Signal(int, object)
    failed = Signal(int, str)


class ScreenTextReader(QObject):
    """Read one granted window; a result describes a snapshot, not an action."""

    completed = Signal(object)
    failed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(
        self,
        access: ScreenAccess,
        engine: OcrEngine | None,
        identity_reader: WindowIdentityReader,
        options: OcrOptions,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._access = access
        self._engine = engine
        self._identity_reader = identity_reader
        self._options = options
        self._select_supported_default()
        self._busy = False
        self._generation = 0
        self._closed = False
        # A worker may finish after this reader closes. Keep its signal source
        # alive in the worker rather than letting Qt delete it with this parent.
        self._events = _WorkerEvents()
        self._events.completed.connect(self._completed)
        self._events.failed.connect(self._failed)
        access.changed.connect(self._access_changed)

    @property
    def available(self) -> bool:
        return self._engine is not None

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def supported_languages(self) -> frozenset[str]:
        return (
            self._engine.capabilities.supported_languages
            if self._engine is not None
            else frozenset()
        )

    @property
    def default_language(self) -> str:
        return self._options.language

    def set_engine(self, engine: OcrEngine | None) -> None:
        """Switch after saving settings; discard any result from the old engine."""
        self._generation += 1
        self._engine = engine
        self._select_supported_default()
        self._finish()
        self.busy_changed.emit(self._busy)

    def _select_supported_default(self) -> None:
        if self._engine is None:
            return
        available = self._engine.capabilities.supported_languages
        if set(self._options.language.split("+")).issubset(available):
            return
        text_languages = sorted(available.difference({"osd", "equ"}))
        if text_languages:
            self._options = OcrOptions(
                text_languages[0], self._options.device, self._options.layout
            )

    def read(
        self, options: OcrOptions | None = None, *, region: ReadRegion = None
    ) -> bool:
        """Start at most one read; never ask for access implicitly."""
        if self._closed or self._busy:
            return False
        if not self._access.granted:
            self.failed.emit("access_off")
            return False
        if self._engine is None:
            self.failed.emit("ocr_unavailable")
            return False
        self._busy = True
        self.busy_changed.emit(True)
        generation = self._generation
        selected_options = options or self._options
        self._access.capture(
            lambda image: self._captured(generation, image, selected_options, region)
        )
        return True

    def _captured(
        self,
        generation: int,
        image: IdentifiedWindowImage | None,
        selected_options: OcrOptions,
        region: ReadRegion,
    ) -> None:
        if generation != self._generation or self._closed:
            return
        if image is None:
            self._finish()
            self.failed.emit("capture_unavailable")
            return
        engine = self._engine
        assert engine is not None
        events = self._events
        original_size = _png_size(image.image)
        scale = 2 if region == "left_chat_list" else 1
        if region == "left_chat_list":
            focused = _chat_list_png(image.image)
            cropped = (focused, 0) if focused is not None else None
        else:
            cropped = _crop_png(image.image, region) if region is not None else None
        if region is not None and cropped is None:
            self._finish()
            self.failed.emit("capture_unavailable")
            return
        ocr_image, left_offset = cropped if cropped is not None else (image.image, 0)

        def work() -> None:
            try:
                result = _window_coordinates(
                    engine.recognize(ocr_image, selected_options), left_offset, scale
                )
                identity = self._identity_reader()
                if identity != (image.platform_app_id, image.process_id):
                    events.failed.emit(generation, "window_changed")
                    return
                observation = IdentifiedWindowText(
                    image.platform_app_id,
                    image.process_id,
                    result,
                    original_size,
                )
                events.completed.emit(generation, observation)
            except Exception:
                # This boundary also contains failures from future OCR plugins.
                events.failed.emit(generation, "ocr_failed")

        Thread(target=work, name="kyrin-screen-ocr", daemon=True).start()

    def _completed(self, generation: int, observation: object) -> None:
        if generation != self._generation or self._closed:
            return
        self._finish()
        self.completed.emit(observation)

    def _failed(self, generation: int, reason: str) -> None:
        if generation != self._generation or self._closed:
            return
        self._finish()
        self.failed.emit(reason)

    def _access_changed(self, granted: bool) -> None:
        if not granted:
            self._generation += 1
            if self._busy:
                self.failed.emit("access_off")
            self._finish()

    def _finish(self) -> None:
        if self._busy:
            self._busy = False
            self.busy_changed.emit(False)

    def close(self) -> None:
        self._closed = True
        self._generation += 1
        self._finish()
