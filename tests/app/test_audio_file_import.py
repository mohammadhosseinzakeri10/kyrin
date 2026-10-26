"""An imported file reuses the normal session without concurrent mic ownership."""

import time
import wave
from contextlib import contextmanager
from pathlib import Path
from typing import cast

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from kyrin.app.controller import ApplicationState
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
        def for_audio_file(self, path: Path) -> Factory:
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
    assert results == [AudioImportResult()]
    assert events == [
        "stop", "wait", "open-file-session", "run", "restart", "active:True"
    ]
