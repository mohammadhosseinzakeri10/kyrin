"""Qt controls persist valid choices without real audio or user settings."""

# ruff: noqa: E402

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread
from time import monotonic, sleep

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kyrin.app.controller import ApplicationController, ApplicationState
from kyrin.app.qt.translations import ENGLISH, UiTranslations
from kyrin.app.qt.window import ControlWindow, EventBridge
from kyrin.app.settings import AppSettings, SttSelection
from kyrin.app.settings_store import JsonSettingsStore, SettingsError
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.microphone.devices import MicrophoneConfiguration, MicrophoneDevice
from kyrin.commands.models import ResponseChannel
from kyrin.responses.presenter import PresentedResponse
from kyrin.stt.device import DevicePreference


class FakeMicrophones:
    def list_inputs(self) -> tuple[MicrophoneDevice, ...]:
        return (MicrophoneDevice("usb-mic", "USB microphone", 2),)

    def resolve(self, key: str | None) -> MicrophoneConfiguration:
        return MicrophoneConfiguration(
            2, AudioFormat(16000, 1, AudioSampleFormat.INT16), 320
        )


class FakeRegistration:
    def __init__(self) -> None:
        self.active = False

    def enabled(self) -> bool:
        return self.active

    def set_enabled(self, enabled: bool) -> None:
        self.active = enabled


class FakeSession:
    def __init__(self) -> None:
        self.running = Event()
        self.stopped = Event()

    def run(self) -> None:
        self.running.set()
        assert self.stopped.wait(2)

    def stop(self) -> None:
        self.stopped.set()


@pytest.fixture
def application(monkeypatch: pytest.MonkeyPatch) -> QApplication:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def _pump_until(application: QApplication, predicate: Callable[[], bool]) -> None:
    deadline = monotonic() + 2
    while monotonic() < deadline:
        application.processEvents()
        if predicate():
            return
        sleep(0.01)
    pytest.fail("Qt status did not advance before timeout")


def _controller(sessions: list[FakeSession]) -> ApplicationController:
    @contextmanager
    def factory(settings: AppSettings) -> Iterator[FakeSession]:
        session = FakeSession()
        sessions.append(session)
        yield session

    return ApplicationController(factory)


def _window(
    settings: AppSettings,
    store: JsonSettingsStore,
    controller: ApplicationController,
    registration: FakeRegistration | None = None,
) -> ControlWindow:
    return ControlWindow(
        settings,
        store,
        controller,
        FakeMicrophones(),
        EventBridge(),
        whisper_server_available=False,
        ui_translations=UiTranslations(store.path.parent),
        startup_registration=registration,
    )


def test_gpu_request_remains_visible_and_keeps_previous_settings(
    application: QApplication, tmp_path: Path
) -> None:
    model = tmp_path / "vosk-model"
    model.mkdir()
    settings = AppSettings(
        listening_enabled=False,
        stt=SttSelection("vosk", model, "en", DevicePreference.CPU),
    )
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(settings)
    window = _window(settings, store, _controller([]))
    try:
        assert window.device_combo.count() == 3
        window.device_combo.setCurrentIndex(
            window.device_combo.findData(DevicePreference.GPU.value)
        )
        window.apply_button.click()
        assert store.load() == settings
        assert "processor" in window.feedback_label.text()
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_listening_switch_persists_and_stops_real_controller_session(
    application: QApplication, tmp_path: Path
) -> None:
    model = tmp_path / "vosk-model"
    model.mkdir()
    settings = AppSettings(
        listening_enabled=False, stt=SttSelection("vosk", model, "en")
    )
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(settings)
    sessions: list[FakeSession] = []
    controller = _controller(sessions)
    window = _window(settings, store, controller)
    try:
        window.start_initial_session()
        assert controller.status().state is ApplicationState.PAUSED
        window.listening_button.click()
        _pump_until(application, lambda: sessions and sessions[0].running.is_set())
        assert store.load().listening_enabled
        window.listening_button.click()
        _pump_until(application, lambda: controller.wait_until_stopped(0))
        assert sessions[0].stopped.is_set()
        assert not store.load().listening_enabled
    finally:
        controller.request_stop()
        controller.wait_until_stopped(2)
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_applying_model_change_stops_old_session_before_restart(
    application: QApplication, tmp_path: Path
) -> None:
    first = tmp_path / "first-model"
    second = tmp_path / "second-model"
    first.mkdir()
    second.mkdir()
    settings = AppSettings(stt=SttSelection("vosk", first, "en"))
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(settings)
    sessions: list[FakeSession] = []
    controller = _controller(sessions)
    window = _window(settings, store, controller)
    try:
        window.start_initial_session()
        _pump_until(application, lambda: sessions and sessions[0].running.is_set())
        window.model_path.setText(str(second))
        window.apply_button.click()
        _pump_until(
            application,
            lambda: len(sessions) == 2 and sessions[1].running.is_set(),
        )
        assert sessions[0].stopped.is_set()
        assert store.load().stt == SttSelection("vosk", second, "en")
        assert controller.status().state is ApplicationState.RUNNING
    finally:
        controller.request_stop()
        controller.wait_until_stopped(2)
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_invalid_settings_file_cannot_be_overwritten_by_window(
    application: QApplication, tmp_path: Path
) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.path.write_text("{invalid", encoding="utf-8")
    contents = store.path.read_bytes()
    window = ControlWindow(
        None,
        store,
        _controller([]),
        FakeMicrophones(),
        EventBridge(),
        whisper_server_available=False,
        ui_translations=UiTranslations(tmp_path / "ui"),
        load_error=SettingsError("invalid JSON"),
    )
    try:
        assert not window.apply_button.isEnabled()
        assert not window.listening_button.isEnabled()
        assert store.path.read_bytes() == contents
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_close_minimizes_without_stopping_listening(
    application: QApplication, tmp_path: Path
) -> None:
    model = tmp_path / "vosk-model"
    model.mkdir()
    settings = AppSettings(stt=SttSelection("vosk", model, "en"))
    sessions: list[FakeSession] = []
    controller = _controller(sessions)
    window = _window(
        settings, JsonSettingsStore(tmp_path / "settings.json"), controller
    )
    try:
        window.show()
        window.start_initial_session()
        _pump_until(application, lambda: sessions and sessions[0].running.is_set())
        window.close()
        application.processEvents()
        assert window.isMinimized()
        assert not sessions[0].stopped.is_set()
    finally:
        controller.request_stop()
        controller.wait_until_stopped(2)
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_worker_response_reaches_window_on_gui_event_loop(
    application: QApplication, tmp_path: Path
) -> None:
    events = EventBridge()
    window = ControlWindow(
        AppSettings(),
        JsonSettingsStore(tmp_path / "settings.json"),
        _controller([]),
        FakeMicrophones(),
        events,
        whisper_server_available=False,
        ui_translations=UiTranslations(tmp_path / "ui"),
    )
    try:
        initial = window.feedback_label.text()
        response = PresentedResponse(
            None, None, "<b>Ready</b>", ResponseChannel.TEXT_ONLY, "en"
        )
        worker = Thread(target=lambda: events.publish(response))
        worker.start()
        worker.join(1)
        assert window.feedback_label.text() == initial
        _pump_until(application, lambda: window.feedback_label.text() == "<b>Ready</b>")
        assert window.feedback_label.textFormat() is Qt.TextFormat.PlainText
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_ui_language_change_preserves_unsaved_speech_fields(
    application: QApplication, tmp_path: Path
) -> None:
    translations = UiTranslations(tmp_path / "ui")
    pack = tmp_path / "fr.json"
    pack.write_text(
        json.dumps(
            {
                "locale": "fr",
                "name": "Français",
                "strings": dict(
                    ENGLISH,
                    dashboard="Tableau de bord",
                    actions_off="Actions désactivées",
                ),
            }
        ),
        encoding="utf-8",
    )
    translations.import_pack(pack)
    window = ControlWindow(
        AppSettings(),
        JsonSettingsStore(tmp_path / "settings.json"),
        _controller([]),
        FakeMicrophones(),
        EventBridge(),
        whisper_server_available=False,
        ui_translations=translations,
    )
    try:
        window.model_path.setText("/unsaved/model")
        window.ui_language_combo.setCurrentIndex(
            window.ui_language_combo.findData("fr")
        )
        window.save_ui_button.click()
        assert window._nav_buttons["dashboard"].text() == "Tableau de bord"
        assert "Actions désactivées" in window.action_label.text()
        assert window.model_path.text() == "/unsaved/model"
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_login_startup_toggle_updates_registration_and_saved_choice(
    application: QApplication, tmp_path: Path
) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    registration = FakeRegistration()
    window = _window(AppSettings(), store, _controller([]), registration)
    try:
        assert not window.startup_checkbox.isChecked()
        window.startup_checkbox.setChecked(True)
        window.save_startup_button.click()
        assert registration.enabled()
        assert store.load().start_at_login

        window.startup_checkbox.setChecked(False)
        window.save_startup_button.click()
        assert not registration.enabled()
        assert not store.load().start_at_login
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_failed_startup_save_restores_previous_registration(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    registration = FakeRegistration()
    window = _window(AppSettings(), store, _controller([]), registration)
    try:

        def fail_save(settings: AppSettings) -> None:
            raise SettingsError("disk full")

        monkeypatch.setattr(store, "save", fail_save)
        window.startup_checkbox.setChecked(True)
        window.save_startup_button.click()
        assert not registration.enabled()
        assert not store.path.exists()
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()
