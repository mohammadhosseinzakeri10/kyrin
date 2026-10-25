"""Asynchronous explicit settings setup for the application input owner."""

from threading import Event, Thread

from PySide6.QtCore import QObject, Signal

from kyrin.actions.platforms.input_session import InputSessionService
from kyrin.operations import OperationStopped, budget


class InputSetupJob(QObject):
    finished = Signal(object)

    def __init__(
        self, service: InputSessionService, capability: str, parent: QObject
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.capability = capability
        self.cancelled = Event()
        self.destroyed.connect(self.cancelled.set)
        self._worker = Thread(target=self._run, name="kyrin-input-setup", daemon=True)

    def start(self) -> None:
        self._worker.start()

    def _run(self) -> None:
        try:
            with budget(45, cancelled=self.cancelled.is_set) as operation:
                result = self.service.prepare(self.capability)
                operation.remaining()
        except OSError, ValueError, OperationStopped:
            result = {"state": "disconnected", "devices": 0}
        try:
            self.finished.emit(result)
        except RuntimeError:
            # The parent Qt object may already have been destroyed on exit.
            self.cancelled.set()

    def kill(self) -> None:
        self.cancelled.set()
        self.service.disconnect()
