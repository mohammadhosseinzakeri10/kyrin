"""An imported file reuses the normal session without concurrent mic ownership."""

import time
import wave
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import cast

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from kyrin.app.controller import ApplicationState
from kyrin.app.events import CommandDeviceReported
from kyrin.app.qt.audio_file_import import AudioFileImport, AudioImportResult
from kyrin.app.settings import AppSettings, SttSelection


def test_import_stops_microphone_then_restores_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    events: list[str] = []
    selected = tmp_path / "speech.wav"
    with wave.open(str(selected), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * 320)

    class Controller:
        def status(self) -> object:
            return type("Status", (), {"state": ApplicationState.RUNNING})()

        def commands_active(self) -> bool:
            return True

        def request_stop(self) -> None:
            events.append("stop")

        def wait_until_stopped(self, timeout_s: float) -> bool:
            events.append("wait")
            return True

        def start(self, settings: AppSettings) -> None:
            events.append("restart")

        def set_commands_active(self, active: bool) -> None:
            events.append(f"active:{active}")

    class Factory:
        def for_audio_file(
            self,
            path: Path,
            *,
            on_command_device: Callable[[CommandDeviceReported], None] | None = None,
        ) -> Factory:
            assert path == selected
            return self

        @contextmanager
        def __call__(self, settings: AppSettings):  # type: ignore[no-untyped-def]
            events.append("open-file-session")
            yield type("Session", (), {"run": lambda self: events.append("run")})()

    importer = AudioFileImport(cast("object", Controller()), cast("object", Factory()))  # type: ignore[arg-type]
    results: list[AudioImportResult] = []
    importer.finished.connect(results.append)
    settings = AppSettings(stt=SttSelection("fake", tmp_path / "model", "en"))
    assert importer.submit(selected, settings)
    deadline = time.monotonic() + 2
    while not results and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert len(results) == 1
    assert results[0].error is None and results[0].command_device is None
    assert importer.result_is_current(results[0])
    assert events == [
        "stop",
        "wait",
        "open-file-session",
        "run",
        "restart",
        "active:True",
    ]


def test_busy_rejection_emits_outside_the_importer_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kyrin.app.controller import ApplicationController
    from kyrin.app.platforms.ubuntu import UbuntuSessionFactory

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    importer = AudioFileImport(
        ApplicationController(lambda _: pytest.fail("must not open a session")),
        cast(UbuntuSessionFactory, object()),
    )
    importer._busy = True
    lock_available: list[bool] = []

    def inspect_lock(result: AudioImportResult) -> None:
        # Qt delivers a same-thread signal immediately. A real window slot
        # reads .busy here and would deadlock if emit still held this lock.
        acquired = importer._lock.acquire(blocking=False)
        lock_available.append(acquired)
        if acquired:
            importer._lock.release()

    importer.finished.connect(inspect_lock)
    monkeypatch.setattr(
        "kyrin.app.qt.audio_file_import.validate_audio_file", lambda _: None
    )
    try:
        assert not importer.submit(
            tmp_path / "unused.wav",
            AppSettings(stt=SttSelection("fake", tmp_path, "en")),
        )
        assert lock_available == [True]
    finally:
        importer._busy = False
        importer.deleteLater()
        app.processEvents()


def test_device_observation_requires_active_uncancelled_file_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kyrin.app.controller import ApplicationController
    from kyrin.app.platforms.ubuntu import UbuntuSessionFactory
    from kyrin.runtime.voice_control import VoiceMode, VoiceModeChanged

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])

    class Session:
        def voice_mode_state(self) -> VoiceModeChanged:
            return VoiceModeChanged(VoiceMode.ACTIVE, session_id="file-session")

        def stop(self) -> None:
            pass

    # Only inspect ownership: this test never submits a file or opens adapters.
    importer = AudioFileImport(
        ApplicationController(lambda _: pytest.fail("must not open a session")),
        cast(UbuntuSessionFactory, object()),
    )
    try:
        assert not importer.event_belongs_to_session("file-session")
        importer._session = Session()
        assert not importer.event_belongs_to_session("file-session")
        importer._busy = True
        assert importer.event_belongs_to_session("file-session")
        assert not importer.event_belongs_to_session("")
        assert not importer.event_belongs_to_session("old-file-session")
        importer.cancel()
        assert not importer.event_belongs_to_session("file-session")
        importer._cancelled.clear()
        importer._session = None
        assert not importer.event_belongs_to_session("file-session")
    finally:
        importer.deleteLater()
        app.processEvents()


def test_fast_file_completion_preserves_final_device_report_until_gui_delivery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections.abc import Iterator

    from kyrin.app.controller import ApplicationController, RuntimeSession
    from kyrin.app.events import CommandDeviceReported
    from kyrin.app.platforms.ubuntu import UbuntuSessionFactory
    from kyrin.commands.ollama_device import CommandDeviceReport, InferenceState
    from kyrin.stt.device import DevicePreference

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    selected = tmp_path / "speech.wav"
    with wave.open(str(selected), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * 320)
    event = CommandDeviceReported(
        CommandDeviceReport(
            "test:latest", DevicePreference.AUTO, InferenceState.COMPLETED
        ),
        "completed-file",
        tmp_path,
    )
    callback: Callable[[CommandDeviceReported], None] | None = None

    class Session:
        def run(self) -> None:
            if callback is not None:
                callback(event)

        def stop(self) -> None:
            pass

    class Factory:
        def for_audio_file(
            self,
            path: Path,
            *,
            on_command_device: Callable[[CommandDeviceReported], None] | None = None,
        ) -> Factory:
            nonlocal callback
            callback = on_command_device
            return self

        @contextmanager
        def __call__(self, settings: AppSettings) -> Iterator[RuntimeSession]:
            yield Session()

    controller = ApplicationController(
        lambda _: pytest.fail("must not start microphone")
    )
    importer = AudioFileImport(controller, cast(UbuntuSessionFactory, Factory()))
    results: list[AudioImportResult] = []
    importer.finished.connect(results.append)
    settings = AppSettings(
        listening_enabled=False, stt=SttSelection("fake", tmp_path, "en")
    )
    try:
        assert importer.submit(selected, settings)
        deadline = time.monotonic() + 3
        # Let the entire file session end before processing any Qt signals.
        while importer.busy and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not importer.busy
        assert not results
        while not results and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert len(results) == 1
        assert results[0].command_device == event
        assert importer.result_is_current(results[0])
        importer.cancel()
        assert not importer.result_is_current(results[0])
        assert importer.result_is_current(results[0], allow_cancelled=True)
        assert not importer.result_is_current(
            AudioImportResult(job_id="old-import"), allow_cancelled=True
        )
    finally:
        importer.cancel()
        importer.deleteLater()
        app.processEvents()
