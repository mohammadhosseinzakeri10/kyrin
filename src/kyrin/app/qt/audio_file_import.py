"""Run one imported audio file through the regular command session."""

from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock, Thread

from PySide6.QtCore import QObject, Signal

from kyrin.app.controller import ApplicationController, ApplicationState
from kyrin.app.platforms.ubuntu import UbuntuSessionFactory
from kyrin.app.settings import AppSettings
from kyrin.audio.audio_errors import AudioError
from kyrin.audio.file_input import validate_audio_file
from kyrin.audio.microphone.errors import MicrophoneError
from kyrin.stt.errors import SpeechToTextError


@dataclass(frozen=True, slots=True)
class AudioImportResult:
    error: str | None = None


class AudioFileImport(QObject):
    """Pause microphone ownership, process the file, then restore listening."""

    finished = Signal(object)

    def __init__(
        self,
        controller: ApplicationController,
        factory: UbuntuSessionFactory,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._factory = factory
        self._lock = Lock()
        self._busy = False
        self._cancelled = Event()
        self._session: object | None = None

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._busy

    def submit(self, path: Path, settings: AppSettings) -> bool:
        if settings.stt is None:
            self.finished.emit(AudioImportResult("Select an STT model first"))
            return False
        try:
            validate_audio_file(path)
        except (OSError, ValueError) as exc:
            self.finished.emit(AudioImportResult(str(exc)))
            return False
        with self._lock:
            if self._busy:
                self.finished.emit(
                    AudioImportResult("An audio file is already being processed")
                )
                return False
            self._busy = True
            self._cancelled.clear()
        Thread(
            target=self._run,
            args=(path, settings),
            name="kyrin-audio-file-import",
            daemon=True,
        ).start()
        return True

    def cancel(self) -> None:
        self._cancelled.set()
        with self._lock:
            session = self._session
        if session is not None:
            stop = getattr(session, "stop", None)
            if stop is not None:
                stop()

    def _run(self, path: Path, settings: AppSettings) -> None:
        was_listening = (
            settings.listening_enabled
            and self._controller.status().state
            in (ApplicationState.RUNNING, ApplicationState.STARTING)
        )
        commands_were_active = self._controller.commands_active()
        error: str | None = None
        try:
            self._controller.request_stop()
            if not self._controller.wait_until_stopped(30):
                raise RuntimeError("Microphone session did not stop before file import")
            previous_status = self._controller.status()
            if previous_status.state is ApplicationState.ERROR:
                raise RuntimeError(
                    f"Microphone cleanup failed: {previous_status.error}"
                )
            if self._cancelled.is_set():
                return
            with self._factory.for_audio_file(path)(settings) as session:
                with self._lock:
                    self._session = session
                if self._cancelled.is_set():
                    session.stop()
                    return
                session.run()
        except (
            OSError,
            ValueError,
            RuntimeError,
            AudioError,
            SpeechToTextError,
            MicrophoneError,
        ) as exc:
            error = str(exc)
        finally:
            with self._lock:
                self._session = None
            if was_listening and not self._cancelled.is_set():
                try:
                    self._controller.start(settings)
                    self._controller.set_commands_active(commands_were_active)
                except (OSError, ValueError, RuntimeError) as exc:
                    error = (
                        f"{error or 'Audio import ended'}; "
                        f"listening restart failed: {exc}"
                    )
            with self._lock:
                self._busy = False
            self.finished.emit(
                AudioImportResult(error or "Audio import cancelled")
                if self._cancelled.is_set()
                else AudioImportResult(error)
            )
