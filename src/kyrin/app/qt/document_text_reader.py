"""Read a granted window with a document model, separate from action OCR."""

from collections.abc import Callable
from dataclasses import dataclass
from threading import Thread

from PySide6.QtCore import QObject, Signal

from kyrin.app.qt.screen_access import ScreenAccess
from kyrin.vision.ocr.backends.document import (
    DocumentOcrEngine,
    DocumentOcrGpuMemoryError,
    DocumentOcrTimeoutError,
)
from kyrin.vision.ocr.backends.tesseract import OcrUnavailableError
from kyrin.vision.ocr.contracts import OcrDevice, OcrDevicePreference
from kyrin.vision.screen_capture import IdentifiedWindowImage

DocumentEngineFactory = Callable[[str], DocumentOcrEngine | None]
WindowIdentityReader = Callable[[], tuple[str, int] | None]


@dataclass(frozen=True)
class DocumentObservation:
    app_id: str
    process_id: int
    backend: str
    text: str
    device: OcrDevice


class _WorkerEvents(QObject):
    completed = Signal(int, object)
    failed = Signal(int, str)


class DocumentTextReader(QObject):
    """Experimental text-only reads cannot feed click or Telegram verification."""

    completed = Signal(object)
    failed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(
        self,
        access: ScreenAccess,
        engine_factory: DocumentEngineFactory,
        identity_reader: WindowIdentityReader,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._access = access
        self._engine_factory = engine_factory
        self._identity_reader = identity_reader
        self._busy = False
        self._generation = 0
        self._closed = False
        self._events = _WorkerEvents()
        self._events.completed.connect(self._completed)
        self._events.failed.connect(self._failed)
        access.changed.connect(self._access_changed)

    @property
    def busy(self) -> bool:
        return self._busy

    def read(
        self, backend: str, device: OcrDevicePreference = OcrDevicePreference.AUTO
    ) -> bool:
        if self._closed or self._busy:
            return False
        if not self._access.granted:
            self.failed.emit("access_off")
            return False
        engine = self._engine_factory(backend)
        if engine is None:
            self.failed.emit("ocr_unavailable")
            return False
        self._busy = True
        self.busy_changed.emit(True)
        generation = self._generation
        self._access.capture(
            lambda image: self._captured(generation, image, engine, device)
        )
        return True

    def _captured(
        self,
        generation: int,
        image: IdentifiedWindowImage | None,
        engine: DocumentOcrEngine,
        device: OcrDevicePreference,
    ) -> None:
        if self._closed or generation != self._generation:
            return
        if image is None:
            self._finish()
            self.failed.emit("capture_unavailable")
            return
        events = self._events

        def work() -> None:
            try:
                result = engine.read_text(image.image, device)
                if self._identity_reader() != (
                    image.platform_app_id,
                    image.process_id,
                ):
                    events.failed.emit(generation, "window_changed")
                    return
                events.completed.emit(
                    generation,
                    DocumentObservation(
                        image.platform_app_id,
                        image.process_id,
                        engine.backend,
                        result.text,
                        result.device,
                    ),
                )
            except DocumentOcrTimeoutError:
                events.failed.emit(generation, "ocr_timeout")
            except DocumentOcrGpuMemoryError:
                events.failed.emit(generation, "gpu_memory")
            except OcrUnavailableError:
                events.failed.emit(generation, "gpu_unavailable")
            except Exception:
                # Contain failures from the optional model and identity providers.
                events.failed.emit(generation, "ocr_failed")

        Thread(target=work, name="kyrin-document-ocr", daemon=True).start()

    def _completed(self, generation: int, observation: object) -> None:
        if self._closed or generation != self._generation:
            return
        self._finish()
        self.completed.emit(observation)

    def _failed(self, generation: int, reason: str) -> None:
        if self._closed or generation != self._generation:
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
