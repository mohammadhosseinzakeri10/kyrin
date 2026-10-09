"""Bridge Qt's asynchronous screen grant to replaceable, offline OCR."""

from collections.abc import Callable
from struct import unpack_from
from threading import Thread

from PySide6.QtCore import QObject, Signal

from kyrin.app.qt.screen_access import ScreenAccess
from kyrin.vision.ocr.contracts import OcrEngine, OcrOptions
from kyrin.vision.screen_capture import IdentifiedWindowImage
from kyrin.vision.text_reader import IdentifiedWindowText

WindowIdentityReader = Callable[[], tuple[str, int] | None]


def _png_size(image: bytes) -> tuple[int, int] | None:
    if len(image) < 24 or image[12:16] != b"IHDR":
        return None
    width, height = unpack_from(">II", image, 16)
    if not (0 < width <= 20000 and 0 < height <= 20000):
        return None
    return width, height


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
        self._busy = False
        self._generation = 0
        self._closed = False
        self._events = _WorkerEvents(self)
        self._events.completed.connect(self._completed)
        self._events.failed.connect(self._failed)
        access.changed.connect(self._access_changed)

    @property
    def available(self) -> bool:
        return self._engine is not None

    @property
    def busy(self) -> bool:
        return self._busy

    def read(self) -> bool:
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
        self._access.capture(lambda image: self._captured(generation, image))
        return True

    def _captured(self, generation: int, image: IdentifiedWindowImage | None) -> None:
        if generation != self._generation or self._closed:
            self._finish()
            return
        if image is None:
            self._finish()
            self.failed.emit("capture_unavailable")
            return
        engine = self._engine
        assert engine is not None

        def work() -> None:
            try:
                result = engine.recognize(image.image, self._options)
                identity = self._identity_reader()
                if identity != (image.platform_app_id, image.process_id):
                    self._events.failed.emit(generation, "window_changed")
                    return
                observation = IdentifiedWindowText(
                    image.platform_app_id,
                    image.process_id,
                    result,
                    _png_size(image.image),
                )
                self._events.completed.emit(generation, observation)
            except Exception:
                # This boundary also contains failures from future OCR plugins.
                self._events.failed.emit(generation, "ocr_failed")

        Thread(target=work, name="kyrin-screen-ocr", daemon=True).start()

    def _completed(self, generation: int, observation: object) -> None:
        self._finish()
        if generation == self._generation and not self._closed:
            self.completed.emit(observation)

    def _failed(self, generation: int, reason: str) -> None:
        self._finish()
        if generation == self._generation and not self._closed:
            self.failed.emit(reason)

    def _access_changed(self, granted: bool) -> None:
        if not granted:
            self._generation += 1
            if self._busy:
                self.failed.emit("access_off")

    def _finish(self) -> None:
        if self._busy:
            self._busy = False
            self.busy_changed.emit(False)

    def close(self) -> None:
        self._closed = True
        self._generation += 1
