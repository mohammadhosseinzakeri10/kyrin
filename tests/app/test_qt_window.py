"""Qt controls persist valid choices without real audio or user settings."""

# ruff: noqa: E402

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from pathlib import Path
from threading import Event, Thread
from time import monotonic, sleep

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
)

from kyrin.actions.models import ActionKey, ActionNotice, ActionNoticeReason
from kyrin.app.controller import ApplicationController, ApplicationState
from kyrin.app.events import AudioCaptureReady, SttDeviceReady
from kyrin.app.model_library import ModelLibrary
from kyrin.app.permission_token import permission_token_path, save_opaque_token
from kyrin.app.qt.model_library_page import ModelLibraryPage
from kyrin.app.qt.translations import ENGLISH, UiPreferences, UiTranslations
from kyrin.app.qt.window import ControlWindow, EventBridge
from kyrin.app.settings import (
    AllowedApp,
    AppSettings,
    AppSpokenAliases,
    OcrSelection,
    SttSelection,
)
from kyrin.app.settings_store import JsonSettingsStore, SettingsError
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.microphone.devices import MicrophoneConfiguration, MicrophoneDevice
from kyrin.commands.models import (
    CommandIntent,
    CommandKind,
    CommandResolution,
    ResponseChannel,
)
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from kyrin.memory.history import ConversationTurn, SqliteConversationHistory
from kyrin.responses.presenter import PresentedResponse
from kyrin.responses.speech import SpeechSynthesisError
from kyrin.runtime.voice_control import VoiceMode, VoiceModeChanged
from kyrin.stt.backends.omnilingual import CHECKPOINT_BYTES, TOKENIZER_NAME
from kyrin.stt.device import ComputeDevice, DevicePreference
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from kyrin.system_power.flow import (
    PowerAction,
    PowerPrompt,
    PowerStage,
    SystemPowerFlow,
)


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


def _controller(
    sessions: list[FakeSession], *, start_in_standby: bool = False
) -> ApplicationController:
    @contextmanager
    def factory(settings: AppSettings) -> Iterator[FakeSession]:
        session = FakeSession()
        sessions.append(session)
        yield session

    return ApplicationController(factory, start_in_standby=start_in_standby)


def _window(
    settings: AppSettings,
    store: JsonSettingsStore,
    controller: ApplicationController,
    registration: FakeRegistration | None = None,
    catalog: XdgDesktopAppCatalog | None = None,
) -> ControlWindow:
    return ControlWindow(
        settings,
        store,
        controller,
        FakeMicrophones(),
        EventBridge(),
        whisper_server_available=False,
        ui_translations=UiTranslations(store.path.parent),
        app_catalog=catalog,
        startup_registration=registration,
    )


def test_preferences_can_clear_local_text_history(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    path = tmp_path / "memory" / "conversation.sqlite3"
    history = SqliteConversationHistory(path)
    history.append(ConversationTurn("Hello KYRIN", "en", datetime.now(UTC), "s", 0, 0))
    history.archive_active()
    history.append(ConversationTurn("New turn", "en", datetime.now(UTC), "s", 0, 1))
    history.close()
    monkeypatch.setattr("kyrin.app.qt.window.default_history_path", lambda: path)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes
    )
    store = JsonSettingsStore(tmp_path / "settings.json")
    window = _window(AppSettings(), store, _controller([]))
    try:
        window.clear_memory_button.click()
        reopened = SqliteConversationHistory(path)
        assert reopened.recent() == ()
        assert reopened.archived_count() == 1
        reopened.close()
    finally:
        window.close()


def test_preferences_review_and_restore_selected_archived_turn(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    path = tmp_path / "memory" / "conversation.sqlite3"
    history = SqliteConversationHistory(path)
    history.append(
        ConversationTurn("private example", "en", datetime.now(UTC), "s", 0, 0)
    )
    history.archive_active()
    history.close()
    monkeypatch.setattr("kyrin.app.qt.window.default_history_path", lambda: path)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes
    )
    window = _window(
        AppSettings(), JsonSettingsStore(tmp_path / "settings.json"), _controller([])
    )
    try:
        window.review_memory_button.click()
        dialog = window._memory_dialog
        assert dialog is not None
        assert dialog.turn_list.count() == 1
        dialog.turn_list.setCurrentRow(0)
        assert dialog.preview.toPlainText() == "private example"
        dialog.restore_button.click()
        assert dialog.turn_list.count() == 0
        reopened = SqliteConversationHistory(path)
        assert reopened.archived_count() == 0
        assert [turn.text for turn in reopened.recent()] == ["private example"]
        reopened.close()
    finally:
        if window._memory_dialog is not None:
            window._memory_dialog.close()
        window.close()


def test_power_buttons_work_without_microphone_session(
    application: QApplication, tmp_path: Path
) -> None:
    class FakePowerBackend:
        def __init__(self) -> None:
            self.requests: list[PowerAction] = []

        def work_warning(self, action: PowerAction) -> str:
            return "GNOME reports one session blocker."

        def request(self, action: PowerAction) -> None:
            self.requests.append(action)

    settings = AppSettings(
        listening_enabled=False,
        action_execution_enabled=True,
        system_power_enabled=True,
    )
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(settings)
    events = EventBridge()
    backend = FakePowerBackend()
    flow = SystemPowerFlow(backend, events.publish, enabled=True)
    announcements: list[PowerPrompt] = []
    flow.set_announcement(announcements.append)
    controller = ApplicationController(lambda _: nullcontext(FakeSession()), flow)
    window = ControlWindow(
        settings,
        store,
        controller,
        FakeMicrophones(),
        events,
        whisper_server_available=False,
        ui_translations=UiTranslations(tmp_path),
    )
    try:
        window.power_dialog.present(
            PowerPrompt(0, PowerAction.POWER_OFF, PowerStage.CHECKING, "Checking"),
            continue_label="Continue",
        )
        assert window.power_dialog.stage_label.text() == (
            "Checking · no confirmation yet"
        )
        assert not window.power_dialog.confirm_button.isVisible()
        window.power_dialog.dismiss()
        window.actions_page.power_buttons[PowerAction.POWER_OFF].click()
        _pump_until(
            application,
            lambda: window._power_prompt is not None
            and window._power_prompt.stage is PowerStage.FIRST,
        )
        assert backend.requests == []
        assert window.power_dialog.isVisible()
        assert window.power_dialog.stage_label.text() == "Confirmation 1 of 2"
        assert not window.isVisible()
        window._on_event(SpeechSynthesisError("speaker unavailable"))
        assert window.power_dialog.voice_warning.isVisible()
        window.power_dialog.confirm_button.click()
        _pump_until(
            application,
            lambda: window._power_prompt is not None
            and window._power_prompt.stage is PowerStage.SECOND,
        )
        assert "Power off" in window.power_dialog.confirm_button.text()
        assert window.power_dialog.stage_label.text() == "Final confirmation 2 of 2"
        assert not window.power_dialog.voice_warning.isVisible()
        window.power_dialog.cancel_button.click()
        _pump_until(application, lambda: window._power_prompt is None)
        assert backend.requests == []
        assert not window.power_dialog.isVisible()
        window.actions_page.power_buttons[PowerAction.POWER_OFF].click()
        _pump_until(
            application,
            lambda: (
                window._power_prompt is not None
                and window._power_prompt.stage is PowerStage.FIRST
            ),
        )
        window.power_dialog.close()
        _pump_until(application, lambda: window._power_prompt is None)
        assert backend.requests == []

        # Final speech takes the same visible two-stage path. The backend is a
        # fake and cannot issue an operating-system power request.
        assert flow.on_final_speech("Power off")
        _pump_until(
            application,
            lambda: (
                window._power_prompt is not None
                and window._power_prompt.stage is PowerStage.FIRST
            ),
        )
        assert window.power_dialog.isVisible()
        assert flow.on_final_speech("Yes")
        _pump_until(
            application,
            lambda: (
                window._power_prompt is not None
                and window._power_prompt.stage is PowerStage.SECOND
            ),
        )
        assert backend.requests == []
        assert flow.on_final_speech("Power off")
        _pump_until(
            application,
            lambda: (
                backend.requests == [PowerAction.POWER_OFF]
                and window._power_prompt is None
            ),
        )
        assert not window.power_dialog.isVisible()
        assert any(prompt.stage is PowerStage.FIRST for prompt in announcements)
        assert any(prompt.stage is PowerStage.SECOND for prompt in announcements)
    finally:
        window._timer.stop()
        window.power_dialog.dismiss()
        window.deleteLater()
        application.processEvents()


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


def test_command_model_and_cpu_choice_are_saved_from_app(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kyrin.app.qt import command_model_page

    store_path = tmp_path / "ollama"
    store_path.mkdir()
    monkeypatch.setattr(
        command_model_page,
        "installed_ollama_models",
        lambda path: ("qwen3.5:4b",) if path == store_path else (),
    )
    settings = AppSettings(listening_enabled=False)
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(settings)
    window = _window(settings, store, _controller([]))
    try:
        page = window.command_model_page
        page.store_path.setText(str(store_path))
        page.refresh()
        page.mode.setCurrentIndex(page.mode.findData("ollama"))
        page.models.setCurrentRow(0)
        page.device.setCurrentIndex(page.device.findData("cpu"))
        window.apply_button.click()
        selected = store.load().command_model
        assert selected is not None
        assert selected.store_path == store_path
        assert selected.model == "qwen3.5:4b"
        assert selected.device is DevicePreference.CPU
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_screen_page_saves_a_compatible_ocr_package(
    application: QApplication, tmp_path: Path
) -> None:
    root = tmp_path / "alternate-ocr"
    data = root / "runtime/usr/share/tesseract-ocr/5/tessdata"
    data.mkdir(parents=True)
    (data / "eng.traineddata").write_bytes(b"model")
    executable = root / "tesseract-local"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o700)
    settings = AppSettings(listening_enabled=False)
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(settings)
    window = ControlWindow(
        settings,
        store,
        _controller([]),
        FakeMicrophones(),
        EventBridge(),
        whisper_server_available=False,
        ui_translations=UiTranslations(tmp_path),
        ocr_default_root=tmp_path / "default-ocr",
    )
    try:
        window.screen_access_page.ocr_path.setText(str(root))
        window.apply_button.click()
        assert store.load().ocr == OcrSelection("tesseract", root)
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_whisper_gpu_choice_is_saved_when_gpu_runtime_is_available(
    application: QApplication, tmp_path: Path
) -> None:
    model = tmp_path / "model.bin"
    model.write_bytes(b"model")
    settings = AppSettings(
        listening_enabled=False,
        stt=SttSelection("whisper", model, "en", DevicePreference.CPU),
    )
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(settings)
    window = ControlWindow(
        settings,
        store,
        _controller([]),
        FakeMicrophones(),
        EventBridge(),
        whisper_server_available=True,
        whisper_gpu_server_available=True,
        ui_translations=UiTranslations(tmp_path),
    )
    try:
        window.device_combo.setCurrentIndex(
            window.device_combo.findData(DevicePreference.GPU.value)
        )
        window.apply_button.click()
        assert store.load().stt is not None
        assert store.load().stt.device is DevicePreference.GPU
        window._on_event(SttDeviceReady(ComputeDevice.GPU))
        assert "GPU" in window.active_device_label.text()
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_model_library_gpu_import_appears_in_both_views_and_can_be_selected(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "ggml-example.bin"
    source.write_bytes(b"lmgg" + b"example weights")
    settings = AppSettings(listening_enabled=False)
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(settings)
    library = ModelLibrary(tmp_path / "library")
    window = ControlWindow(
        settings,
        store,
        _controller([]),
        FakeMicrophones(),
        EventBridge(),
        whisper_server_available=True,
        whisper_gpu_server_available=True,
        model_library=library,
        ui_translations=UiTranslations(tmp_path),
    )
    monkeypatch.setattr(
        "kyrin.app.qt.model_library_page.QFileDialog.getOpenFileName",
        lambda *args: (str(source), ""),
    )
    try:
        page = window.models_page
        assert page.tabs.currentIndex() == 0
        assert page.language_edit.text() == "auto"
        page.backend_combo.setCurrentIndex(page.backend_combo.findData("vosk"))
        assert page.language_edit.text() == "en"
        page.backend_combo.setCurrentIndex(page.backend_combo.findData("whisper"))
        assert page.language_edit.text() == "en"
        page.language_edit.setText("auto")
        page.tabs.setCurrentIndex(2)
        page.import_buttons[ComputeDevice.GPU].click()
        _pump_until(
            application,
            lambda: page.status.text() == ENGLISH["models_imported"],
        )
        assert len(library.list_models()) == 1
        assert page.lists[0].count() == 1
        assert page.lists[1].count() == 1
        assert page.lists[2].count() == 1
        page.lists[2].setCurrentRow(0)
        page.use_button.click()
        assert window.pages.currentIndex() == 2
        assert window.device_combo.currentData() == DevicePreference.GPU.value
        window.apply_button.click()
        saved = store.load().stt
        assert saved is not None
        assert saved.model_path == library.list_models()[0].model_path
        assert saved.device is DevicePreference.GPU
        assert saved.language == "auto"
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_vosk_import_rejects_mismatched_folder_language_before_copy(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "vosk-model-small-fa-0.42"
    source.mkdir()
    library = ModelLibrary(tmp_path / "library")
    page = ModelLibraryPage(
        library,
        UiTranslations(tmp_path),
        cpu_runtime_available=True,
        gpu_runtime_available=False,
        current_selection=None,
    )
    monkeypatch.setattr(
        "kyrin.app.qt.model_library_page.QFileDialog.getExistingDirectory",
        lambda *args: str(source),
    )
    try:
        page.backend_combo.setCurrentIndex(page.backend_combo.findData("vosk"))
        assert page.language_edit.text() == "en"
        page._start_import(ComputeDevice.CPU)
        assert "fa" in page.status.text()
        assert not library.root.exists()
    finally:
        page.deleteLater()
        application.processEvents()


def test_omnilingual_catalog_model_can_be_selected_without_copy(
    application: QApplication, tmp_path: Path
) -> None:
    name = "omniASR_CTC_300M_v2"
    catalog = tmp_path / "omnilingual-asr"
    folder = catalog / name
    folder.mkdir(parents=True)
    checkpoint = folder / "omniASR-CTC-300M-v2.pt"
    with checkpoint.open("wb") as stream:
        stream.truncate(CHECKPOINT_BYTES[name])
    (folder / TOKENIZER_NAME).write_bytes(b"x" * 91481)
    runtime = tmp_path / "python"
    runtime.write_bytes(b"runtime")
    settings = AppSettings(listening_enabled=False)
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(settings)
    window = ControlWindow(
        settings,
        store,
        _controller([]),
        FakeMicrophones(),
        EventBridge(),
        whisper_server_available=False,
        omnilingual_python=runtime,
        omnilingual_root=catalog,
        ui_translations=UiTranslations(tmp_path),
    )
    try:
        assert window.backend_combo.findData("omnilingual") >= 0
        page = window.models_page
        assert page.lists[0].count() == 1
        page.lists[0].setCurrentRow(0)
        page.use_button.click()
        assert window.backend_combo.currentData() == "omnilingual"
        assert window.model_path.text() == str(folder)
        window.apply_button.click()
        saved = store.load().stt
        assert saved is not None
        assert saved.backend == "omnilingual"
        assert saved.model_path == folder
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_gpu_model_stays_visible_when_gpu_runtime_is_missing(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "ggml-example.bin"
    source.write_bytes(b"lmgg" + b"example weights")
    library = ModelLibrary(tmp_path / "library")
    library.import_model(
        source, backend="whisper", language="en", requested_device=ComputeDevice.CPU
    )
    settings = AppSettings(listening_enabled=False)
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(settings)
    window = ControlWindow(
        settings,
        store,
        _controller([]),
        FakeMicrophones(),
        EventBridge(),
        whisper_server_available=True,
        whisper_gpu_server_available=False,
        model_library=library,
        ui_translations=UiTranslations(tmp_path),
    )
    monkeypatch.setattr(
        "kyrin.app.qt.model_library_page.QFileDialog.getOpenFileName",
        lambda *args: (str(source), ""),
    )
    try:
        page = window.models_page
        page.tabs.setCurrentIndex(2)
        assert page.lists[2].count() == 1
        page.import_buttons[ComputeDevice.GPU].click()
        _pump_until(
            application,
            lambda: page.status.text() == ENGLISH["models_reused_language"],
        )
        assert len(library.list_models()) == 1
        assert ENGLISH["models_gpu_unavailable"] in page.lists[2].item(0).text()
        page.lists[2].setCurrentRow(0)
        page.use_button.click()
        assert page.status.text() == ENGLISH["models_gpu_unavailable"]
        assert store.load() == settings
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_listening_switch_enters_standby_and_full_off_stops_session(
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
        _pump_until(
            application,
            lambda: bool(sessions)
            and sessions[0].running.is_set(),
        )
        window._on_event(AudioCaptureReady())
        assert store.load().listening_enabled
        window.listening_button.click()
        assert not controller.commands_active()
        assert not sessions[0].stopped.is_set()
        assert store.load().listening_enabled
        window.microphone_off_button.click()
        _pump_until(application, lambda: controller.wait_until_stopped(0))
        assert sessions[0].stopped.is_set()
        assert not store.load().listening_enabled
    finally:
        controller.request_stop()
        controller.wait_until_stopped(2)
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_voice_modes_start_in_standby_and_full_off_persists(
    application: QApplication, tmp_path: Path
) -> None:
    model = tmp_path / "vosk-model"
    model.mkdir()
    settings = AppSettings(stt=SttSelection("vosk", model, "en"))
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(settings)
    sessions: list[FakeSession] = []
    controller = _controller(sessions, start_in_standby=True)
    window = _window(settings, store, controller)
    try:
        window.start_initial_session()
        _pump_until(
            application,
            lambda: controller.status().state is ApplicationState.RUNNING,
        )
        assert not controller.commands_active()
        window._refresh()
        assert ENGLISH["state_mic_starting"] in window.status_label.text()
        window._on_event(AudioCaptureReady())
        window._refresh()
        assert ENGLISH["state_standby"] in window.status_label.text()
        window._on_event(VoiceModeChanged(VoiceMode.ACTIVE))
        assert controller.commands_active()
        window._on_event(VoiceModeChanged(VoiceMode.STANDBY))
        assert not controller.commands_active()
        assert not sessions[0].stopped.is_set()
        window._on_event(VoiceModeChanged(VoiceMode.OFF))
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


def test_power_preview_button_never_calls_real_backend(
    application: QApplication, tmp_path: Path
) -> None:
    class Backend:
        def __init__(self) -> None:
            self.requests: list[PowerAction] = []

        def work_warning(self, action: PowerAction) -> str:
            return "No blockers detected."

        def request(self, action: PowerAction) -> None:
            self.requests.append(action)

    real = Backend()
    preview = Backend()
    events = EventBridge()
    flow = SystemPowerFlow(real, events.publish, enabled=False, preview_backend=preview)
    window = ControlWindow(
        AppSettings(listening_enabled=False),
        JsonSettingsStore(tmp_path / "settings.json"),
        ApplicationController(lambda _: nullcontext(FakeSession()), flow),
        FakeMicrophones(),
        events,
        whisper_server_available=False,
        ui_translations=UiTranslations(tmp_path),
    )
    try:
        window.actions_page.power_preview_button.click()
        _pump_until(
            application,
            lambda: (
                window._power_prompt is not None
                and window._power_prompt.stage is PowerStage.FIRST
            ),
        )
        assert "SAFE PREVIEW" in window.power_dialog.action_label.text()
        assert flow.on_final_speech("Yes")
        _pump_until(
            application,
            lambda: (
                window._power_prompt is not None
                and window._power_prompt.stage is PowerStage.SECOND
            ),
        )
        assert flow.on_final_speech("Power off")
        _pump_until(application, lambda: preview.requests == [PowerAction.POWER_OFF])
        assert real.requests == []
    finally:
        window.power_dialog.dismiss()
        window.close()
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


def test_speech_diagnostics_show_heard_intent_and_action_reason(
    application: QApplication, tmp_path: Path
) -> None:
    window = _window(
        AppSettings(),
        JsonSettingsStore(tmp_path / "settings.json"),
        _controller([]),
    )
    intent = CommandIntent(CommandKind.OPEN_APP, "telegram")
    try:
        window._on_event(
            TranscriptUpdate(2, "Open Telegram", TranscriptStatus.FINAL, "en")
        )
        window._on_event(CommandResolution(2, intent))
        window._on_event(
            ActionNotice(ActionKey(0, 2, 0), intent, ActionNoticeReason.NOT_ALLOWED)
        )
        trace = window.diagnostics_output.toPlainText()
        assert "Heard (en): Open Telegram" in trace
        assert "open_app: telegram" in trace
        assert "not_allowed" in trace
        window.clear_diagnostics_button.click()
        assert not window.diagnostics_output.toPlainText()
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


def test_builtin_persian_changes_layout_without_changing_speech_language(
    application: QApplication, tmp_path: Path
) -> None:
    translations = UiTranslations(tmp_path / "ui", system_locale="fa_IR")
    settings = AppSettings()
    window = ControlWindow(
        settings,
        JsonSettingsStore(tmp_path / "settings.json"),
        _controller([]),
        FakeMicrophones(),
        EventBridge(),
        whisper_server_available=False,
        ui_translations=translations,
    )
    try:
        window.ui_language_combo.setCurrentIndex(
            window.ui_language_combo.findData("system")
        )
        window.save_ui_button.click()
        assert translations.preferences.locale == "system"
        assert translations.active_locale == "fa"
        assert window.layoutDirection() is Qt.LayoutDirection.RightToLeft
        assert window._nav_buttons["dashboard"].text() == "داشبورد"
        assert window.actions_page.power_buttons[PowerAction.RESTART].text() == (
            "راه‌اندازی دوباره…"
        )
        assert window.language_edit.text() == "en"
        assert window.ui_language_combo.currentData() == "system"
        window.ui_language_combo.setCurrentIndex(
            window.ui_language_combo.findData("en")
        )
        window.save_ui_button.click()
        assert window.layoutDirection() is Qt.LayoutDirection.LeftToRight
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


def test_actions_page_saves_only_explicitly_selected_app(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "local-data"))
    directory = tmp_path / "data/applications"
    directory.mkdir(parents=True)
    for name in ("Telegram", "Browser"):
        (directory / f"{name.lower()}.desktop").write_text(
            f"[Desktop Entry]\nType=Application\nName={name}\nExec=true\n",
            encoding="utf-8",
        )
    catalog = XdgDesktopAppCatalog((tmp_path / "data",))
    store = JsonSettingsStore(tmp_path / "settings.json")
    settings = AppSettings(listening_enabled=False)
    window = _window(settings, store, _controller([]), catalog=catalog)
    try:
        assert window.actions_page.apps.count() == 2
        window.actions_page.enabled_checkbox.setChecked(True)
        window.apply_button.click()
        assert "Select at least one" in window.feedback_label.text()
        assert not store.path.exists()

        telegram = next(
            window.actions_page.apps.item(index)
            for index in range(window.actions_page.apps.count())
            if "telegram.desktop" in window.actions_page.apps.item(index).text()
        )
        browser = next(
            window.actions_page.apps.item(index)
            for index in range(window.actions_page.apps.count())
            if "browser.desktop" in window.actions_page.apps.item(index).text()
        )
        window.actions_page.apps.setCurrentItem(browser)
        window.actions_page.aliases_edit.setText("مرورگر من")
        window.actions_page.apps.setCurrentItem(telegram)
        window.actions_page.aliases_edit.setText("تلگرام من")
        telegram.setCheckState(Qt.CheckState.Checked)
        assert window.actions_page.telegram_chat_checkbox.isEnabled()
        assert not window.actions_page.window_control_checkbox.isChecked()
        assert not window.actions_page.close_window_checkbox.isChecked()
        window.actions_page.telegram_chat_checkbox.setChecked(True)
        assert window.actions_page.telegram_pointer_checkbox.isEnabled()
        window.actions_page.telegram_pointer_checkbox.setChecked(True)
        window.actions_page.window_control_checkbox.setChecked(True)
        window.actions_page.close_window_checkbox.setChecked(True)
        window.wake_aliases_edit.setText("kayrin, کایرین من")
        window.actions_page.search.setText("telegram")
        window.apply_button.click()
        saved = store.load()
        assert saved.action_execution_enabled
        assert len(saved.allowed_apps) == 1
        assert saved.allowed_apps[0].desktop_id == "telegram.desktop"
        assert saved.allowed_apps[0].app_id == "telegram"
        assert saved.allowed_chat_apps == ("telegram",)
        assert saved.remember_telegram_pointer
        assert saved.allowed_window_apps == ("telegram",)
        assert saved.allowed_close_apps == ("telegram",)
        assert saved.wake_aliases == ("kayrin", "کایرین من")
        assert saved.app_spoken_aliases == (
            AppSpokenAliases("browser.desktop", ("مرورگر من",)),
            AppSpokenAliases("telegram.desktop", ("تلگرام من",)),
        )
        assert all(app.desktop_id != "browser.desktop" for app in saved.allowed_apps)
        assert "1 allowed apps" in window.action_label.text()
        token_path = permission_token_path("telegram-keyboard")
        pointer_path = permission_token_path("telegram-pointer")
        control_path = permission_token_path("telegram-control")
        save_opaque_token(token_path, "remembered-keyboard")
        save_opaque_token(pointer_path, "remembered-pointer")
        save_opaque_token(control_path, "remembered-control")
        window.actions_page.telegram_chat_checkbox.setChecked(False)
        window.apply_button.click()
        assert store.load().allowed_chat_apps == ()
        assert not store.load().remember_telegram_pointer
        assert not token_path.exists()
        assert not pointer_path.exists()
        assert not control_path.exists()
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_scroll_permission_can_be_saved_without_selected_apps(
    application: QApplication, tmp_path: Path
) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    window = _window(AppSettings(listening_enabled=False), store, _controller([]))
    try:
        assert window.actions_page.desktop_scroll_checkbox.isEnabled()
        window.actions_page.enabled_checkbox.setChecked(True)
        window.actions_page.desktop_scroll_checkbox.setChecked(True)
        window.apply_button.click()
        saved = store.load()
        assert saved.action_execution_enabled
        assert saved.allow_desktop_scroll
        assert saved.allowed_apps == ()
        assert saved.allowed_window_apps == ()
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_telegram_control_access_is_requested_from_settings(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "local-data"))
    settings = AppSettings(
        listening_enabled=False,
        allowed_apps=(AllowedApp("telegram", "telegram.desktop"),),
        allowed_chat_apps=("telegram",),
        remember_telegram_pointer=True,
    )
    calls: list[tuple[str, list[str]]] = []
    approve = [False]

    class FakeSignal:
        def __init__(self) -> None:
            self.callback = None

        def connect(self, callback) -> None:
            self.callback = callback

        def emit(self, *args) -> None:
            assert self.callback is not None
            self.callback(*args)

    class FakeProcess:
        def __init__(self, _parent) -> None:
            self.finished = FakeSignal()
            self.errorOccurred = FakeSignal()
            self.program = ""
            self.arguments: list[str] = []

        def setProgram(self, program: str) -> None:
            self.program = program

        def setArguments(self, arguments: list[str]) -> None:
            self.arguments = arguments

        def start(self) -> None:
            calls.append((self.program, self.arguments))
            if approve[0]:
                save_opaque_token(
                    permission_token_path("telegram-control"), "granted-control"
                )
            self.finished.emit(0 if approve[0] else 1, None)

        def readAllStandardOutput(self) -> bytes:
            return b"CONTROL_GRANT_READY"

        def deleteLater(self) -> None:
            pass

    monkeypatch.setattr("kyrin.app.qt.window.QProcess", FakeProcess)
    old_keyboard = permission_token_path("telegram-keyboard")
    old_pointer = permission_token_path("telegram-pointer")
    save_opaque_token(old_keyboard, "old-keyboard")
    save_opaque_token(old_pointer, "old-pointer")
    window = _window(
        settings, JsonSettingsStore(tmp_path / "settings.json"), _controller([])
    )
    try:
        button = window.actions_page.telegram_pointer_grant_button
        assert button.isEnabled()
        button.click()
        assert "not saved" in window.actions_page.telegram_pointer_grant_status.text()
        assert not permission_token_path("telegram-control").exists()
        assert old_keyboard.exists()
        assert old_pointer.exists()
        approve[0] = True
        button.click()
        assert len(calls) == 2
        assert calls[0][0] == "/usr/bin/python3"
        assert calls[0][1][0].endswith("telegram_portal_helper.py")
        assert calls[0][1][1] == "grant-control"
        assert "saved" in window.actions_page.telegram_pointer_grant_status.text()
        assert not old_keyboard.exists()
        assert not old_pointer.exists()
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_actions_page_scrolls_without_squashing_app_list(
    application: QApplication, tmp_path: Path
) -> None:
    directory = tmp_path / "data/applications"
    directory.mkdir(parents=True)
    for index in range(30):
        (directory / f"example-{index}.desktop").write_text(
            f"[Desktop Entry]\nType=Application\nName=Example {index}\nExec=true\n",
            encoding="utf-8",
        )
    window = _window(
        AppSettings(listening_enabled=False),
        JsonSettingsStore(tmp_path / "settings.json"),
        _controller([]),
        catalog=XdgDesktopAppCatalog((tmp_path / "data",)),
    )
    try:
        window.resize(980, 650)
        window._select_page(6)
        window.show()
        application.processEvents()
        page = window.actions_page
        scrollbar = page.scroll_area.verticalScrollBar()
        assert page.apps.count() == 30
        assert page.apps.height() >= 300
        assert page.apps.verticalScrollBar().maximum() > 0
        assert scrollbar.maximum() > 0
        scrollbar.setValue(scrollbar.maximum())
        application.processEvents()
        assert scrollbar.value() == scrollbar.maximum()
        assert page.power_preview_button.isVisible()
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


@pytest.mark.parametrize("locale", ["en", "fa"])
def test_settings_pages_keep_controls_readable_at_minimum_window_size(
    application: QApplication, tmp_path: Path, locale: str
) -> None:
    UiTranslations(tmp_path).save(UiPreferences(locale))
    window = _window(
        AppSettings(listening_enabled=False),
        JsonSettingsStore(tmp_path / "settings.json"),
        _controller([]),
    )
    try:
        window.resize(980, 650)
        window.show()
        for index in range(window.pages.count()):
            window._select_page(index)
            application.processEvents()
            page = window.pages.widget(index)
            assert page is not None
            for button in page.findChildren(QPushButton):
                if button.isVisible():
                    assert button.height() >= 35, (index, button.text())
            for text_area in page.findChildren(QPlainTextEdit):
                if text_area.isVisible():
                    assert text_area.height() >= 180, index
            if index in (2, 3, 4, 5, 6, 7, 8):
                scroll = page.findChild(QScrollArea)
                assert scroll is not None
                assert scroll.verticalScrollBar().maximum() > 0
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_action_row_click_and_indicator_each_toggle_once(
    application: QApplication, tmp_path: Path
) -> None:
    directory = tmp_path / "data/applications"
    directory.mkdir(parents=True)
    (directory / "telegram.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Telegram\nExec=true\n",
        encoding="utf-8",
    )
    window = _window(
        AppSettings(listening_enabled=False),
        JsonSettingsStore(tmp_path / "settings.json"),
        _controller([]),
        catalog=XdgDesktopAppCatalog((tmp_path / "data",)),
    )
    try:
        window._select_page(4)
        window.show()
        application.processEvents()
        model_list = window.actions_page.apps
        item = model_list.item(0)
        rectangle = model_list.visualItemRect(item)
        row_point = QPoint(rectangle.right() - 20, rectangle.center().y())
        indicator_point = QPoint(rectangle.left() + 10, rectangle.center().y())

        QTest.mouseClick(
            model_list.viewport(), Qt.MouseButton.LeftButton, pos=row_point
        )
        assert item.checkState() is Qt.CheckState.Checked
        QTest.mouseClick(
            model_list.viewport(), Qt.MouseButton.LeftButton, pos=indicator_point
        )
        assert item.checkState() is Qt.CheckState.Unchecked
        assert window.actions_page.selection_count.text() == "0 selected"
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_bulk_selection_respects_search_and_does_not_enable_actions(
    application: QApplication, tmp_path: Path
) -> None:
    directory = tmp_path / "data/applications"
    directory.mkdir(parents=True)
    for name in ("Telegram", "Browser"):
        (directory / f"{name.lower()}.desktop").write_text(
            f"[Desktop Entry]\nType=Application\nName={name}\nExec=true\n",
            encoding="utf-8",
        )
    window = _window(
        AppSettings(listening_enabled=False),
        JsonSettingsStore(tmp_path / "settings.json"),
        _controller([]),
        catalog=XdgDesktopAppCatalog((tmp_path / "data",)),
    )
    try:
        page = window.actions_page
        page.search.setText("Telegram")
        page.select_visible_button.click()
        assert tuple(app.desktop_id for app in page.selected_apps()) == (
            "telegram.desktop",
        )
        assert not page.enabled_checkbox.isChecked()
        page.search.clear()
        page.select_visible_button.click()
        assert len(page.selected_apps()) == 2
        page.search.setText("Telegram")
        page.clear_visible_button.click()
        assert tuple(app.desktop_id for app in page.selected_apps()) == (
            "browser.desktop",
        )
    finally:
        window._timer.stop()
        window.deleteLater()
        application.processEvents()


def test_action_permission_change_restarts_running_session(
    application: QApplication, tmp_path: Path
) -> None:
    directory = tmp_path / "data/applications"
    directory.mkdir(parents=True)
    (directory / "telegram.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Telegram\nExec=true\n",
        encoding="utf-8",
    )
    model = tmp_path / "model"
    model.mkdir()
    settings = AppSettings(stt=SttSelection("vosk", model, "en"))
    store = JsonSettingsStore(tmp_path / "settings.json")
    sessions: list[FakeSession] = []
    controller = _controller(sessions)
    window = _window(
        settings,
        store,
        controller,
        catalog=XdgDesktopAppCatalog((tmp_path / "data",)),
    )
    try:
        window.start_initial_session()
        _pump_until(application, lambda: sessions and sessions[0].running.is_set())
        window.actions_page.apps.item(0).setCheckState(Qt.CheckState.Checked)
        window.actions_page.enabled_checkbox.setChecked(True)
        assert not store.path.exists()

        window.apply_button.click()
        _pump_until(
            application, lambda: len(sessions) == 2 and sessions[1].running.is_set()
        )
        assert sessions[0].stopped.is_set()
        saved = store.load()
        assert saved.action_execution_enabled
        assert saved.allowed_apps[0].desktop_id == "telegram.desktop"
    finally:
        controller.request_stop()
        controller.wait_until_stopped(2)
        window._timer.stop()
        window.deleteLater()
        application.processEvents()
