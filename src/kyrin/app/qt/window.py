"""English-first desktop shell over the independent application controller."""

import sqlite3
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QObject, QProcess, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from kyrin.actions.models import ActionFeedback, ActionNotice
from kyrin.actions.platforms.desktop_scroll import SCROLL_HELPER
from kyrin.actions.platforms.telegram import TELEGRAM_PORTAL_HELPER
from kyrin.app.app_permissions import AppPickerCatalog
from kyrin.app.controller import ApplicationController, ApplicationState
from kyrin.app.events import ApplicationEvent, AudioCaptureReady, SttDeviceReady
from kyrin.app.model_library import InstalledModel, ModelLibrary
from kyrin.app.permission_token import permission_token_path, read_opaque_token
from kyrin.app.platforms.xdg_startup import DesktopRegistrationError
from kyrin.app.qt.actions_page import DesktopActionsPage
from kyrin.app.qt.archived_memory_dialog import ArchivedMemoryDialog
from kyrin.app.qt.audio_page import AudioPage
from kyrin.app.qt.branding import LOGO_PATH
from kyrin.app.qt.command_model_page import CommandModelPage
from kyrin.app.qt.dashboard_page import DashboardPage
from kyrin.app.qt.model_library_page import ModelLibraryPage
from kyrin.app.qt.ocr_setup import selected_ocr_engine
from kyrin.app.qt.power_dialog import PowerConfirmationDialog
from kyrin.app.qt.preferences_page import PreferencesPage
from kyrin.app.qt.recognition_page import RecognitionPage
from kyrin.app.qt.screen_access import ScreenAccess
from kyrin.app.qt.screen_access_page import ScreenAccessPage
from kyrin.app.qt.screen_text_reader import ScreenTextReader
from kyrin.app.qt.theme import CONTROL_WINDOW_STYLE
from kyrin.app.qt.translations import (
    TranslationError,
    UiPreferences,
    UiTranslations,
)
from kyrin.app.qt.tts_page import TtsPage
from kyrin.app.settings import AppSettings, SttSelection, TtsLanguageRoute, TtsSelection
from kyrin.app.settings_store import SettingsError
from kyrin.audio.microphone.devices import MicrophoneResolver
from kyrin.audio.microphone.errors import MicrophoneError
from kyrin.commands.models import (
    CommandPlanResolution,
    CommandResolution,
    ResponseRequest,
)
from kyrin.memory.history import SqliteConversationHistory, default_history_path
from kyrin.responses.presenter import PresentedResponse
from kyrin.responses.speech import SpeechSynthesisError
from kyrin.runtime.latency import SpeechActionLatency
from kyrin.runtime.speech_sessions import SpeechSessionEnded
from kyrin.runtime.voice_control import VoiceMode, VoiceModeChanged
from kyrin.stt.device import ComputeDevice, DevicePreference
from kyrin.stt.errors import DeviceUnavailableError, SpeechToTextError
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from kyrin.system_power.flow import PowerAction, PowerPrompt, PowerStage


class SettingsStore(Protocol):
    def save(self, settings: AppSettings) -> None: ...


class StartupRegistration(Protocol):
    def enabled(self) -> bool: ...

    def set_enabled(self, enabled: bool) -> None: ...


class EventBridge(QObject):
    """Queue runtime-thread events onto Qt's GUI thread."""

    received = Signal(object)

    def publish(self, event: ApplicationEvent) -> None:
        self.received.emit(event)


_STATE_KEYS = {
    ApplicationState.STOPPED: "state_stopped",
    ApplicationState.PAUSED: "state_paused",
    ApplicationState.SETUP_REQUIRED: "state_setup",
    ApplicationState.STARTING: "state_starting",
    ApplicationState.RUNNING: "state_running",
    ApplicationState.STOPPING: "state_stopping",
    ApplicationState.ERROR: "state_error",
}


def _friendly_error(error: Exception, text: Callable[[str], str]) -> str:
    if isinstance(error, DeviceUnavailableError):
        return text("error_device")
    if isinstance(error, SpeechToTextError):
        return str(error)
    if isinstance(error, MicrophoneError):
        return text("error_microphone")
    if isinstance(error, FileNotFoundError):
        return text("error_file")
    if isinstance(error, SettingsError):
        return text("error_settings")
    if isinstance(error, (ValueError, RuntimeError)):
        return str(error)
    return f"{text('error_generic')}: {type(error).__name__}"


class ControlWindow(QWidget):
    """Edit a bounded first set of preferences; never run audio on the UI thread."""

    def __init__(
        self,
        settings: AppSettings | None,
        store: SettingsStore,
        controller: ApplicationController,
        microphones: MicrophoneResolver,
        events: EventBridge,
        *,
        whisper_server_available: bool,
        whisper_gpu_server_available: bool = False,
        omnilingual_python: Path | None = None,
        omnilingual_root: Path | None = None,
        model_library: ModelLibrary | None = None,
        suggested_command_store: Path | None = None,
        tts_model_root: Path | None = None,
        configure_tts: Callable[
            [TtsSelection, tuple[TtsLanguageRoute, ...], bool], None
        ]
        | None = None,
        preview_tts: Callable[[str, str, TtsSelection], bool] | None = None,
        ui_translations: UiTranslations,
        app_catalog: AppPickerCatalog | None = None,
        screen_access: ScreenAccess | None = None,
        screen_reader: ScreenTextReader | None = None,
        ocr_default_root: Path | None = None,
        startup_registration: StartupRegistration | None = None,
        load_error: SettingsError | None = None,
        startup_error: DesktopRegistrationError | None = None,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._store = store
        self._controller = controller
        self._microphones = microphones
        self._whisper_server_available = whisper_server_available
        self._whisper_gpu_server_available = whisper_gpu_server_available
        self._omnilingual_python = omnilingual_python
        self._active_stt_device: ComputeDevice | None = None
        self._audio_ready = False
        self._pending_settings: AppSettings | None = None
        self._pointer_grant_process: QProcess | None = None
        self._scroll_grant_process: QProcess | None = None
        self._quitting = False
        self._microphone_off_pending = False
        self._last_status_error: Exception | None = None
        self._translations = ui_translations
        self._startup_registration = startup_registration
        self._configure_tts = configure_tts
        self._screen_reader = screen_reader
        self._ocr_default_root = ocr_default_root
        self._labels: dict[str, QLabel] = {}
        self._action_latency = SpeechActionLatency()
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setMinimumSize(980, 650)
        self.resize(1200, 760)
        self.setObjectName("ControlWindow")
        self.setStyleSheet(CONTROL_WINDOW_STYLE)

        shell = QHBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 28, 20, 20)
        side.setSpacing(8)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        logo = QLabel()
        logo.setObjectName("BrandLogo")
        logo.setFixedSize(48, 48)
        logo.setPixmap(
            QPixmap(str(LOGO_PATH)).scaled(
                logo.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        logo.setAccessibleName("KYRIN logo")
        brand_row.addWidget(logo)
        brand = QLabel("KYRIN")
        brand.setObjectName("Brand")
        brand_row.addWidget(brand)
        brand_row.addStretch()
        side.addLayout(brand_row)
        self.subtitle = QLabel()
        self.subtitle.setObjectName("Subtitle")
        side.addWidget(self.subtitle)
        side.addSpacing(34)
        self.pages = QStackedWidget()
        self._nav_buttons: dict[str, QPushButton] = {}
        for index, key in enumerate(
            (
                "dashboard",
                "audio",
                "recognition",
                "models",
                "command_models",
                "tts",
                "actions",
                "screen",
                "preferences",
            )
        ):
            button = QPushButton()
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, page=index: self._select_page(page)
            )
            side.addWidget(button)
            self._nav_buttons[key] = button
        side.addStretch()
        self.sidebar_footer = QLabel()
        self.sidebar_footer.setWordWrap(True)
        side.addWidget(self.sidebar_footer)
        shell.addWidget(sidebar)

        content = QWidget()
        content.setObjectName("Content")
        root = QVBoxLayout(content)
        root.setContentsMargins(26, 22, 26, 24)
        root.setSpacing(14)
        self.status_label = QLabel()
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setObjectName("Status")
        self.status_label.setAccessibleName("KYRIN status")
        root.addWidget(self.status_label)
        root.addWidget(self.pages, 1)
        self.feedback_label = QLabel()
        self.feedback_label.setTextFormat(Qt.TextFormat.PlainText)
        self.feedback_label.setObjectName("Feedback")
        self.feedback_label.setWordWrap(True)
        root.addWidget(self.feedback_label)
        self._power_prompt: PowerPrompt | None = None
        self.power_dialog = PowerConfirmationDialog(
            self._controller.respond_to_system_action,
            lambda request_id: self._controller.respond_to_system_action(
                request_id, "cancel"
            ),
        )
        shell.addWidget(content, 1)

        self.dashboard_page = DashboardPage(self._label)
        self.cosmic_dashboard = self.dashboard_page.cosmic_dashboard
        self.welcome_label = self.dashboard_page.welcome_label
        self.welcome_caption_label = self.dashboard_page.welcome_caption_label
        self.scene_hint_label = self.dashboard_page.scene_hint_label
        self.pages.addWidget(self.dashboard_page)

        self.audio_page = AudioPage(self._label)
        self.microphone_combo = self.audio_page.microphone_combo
        self.pages.addWidget(self.audio_page)

        self.recognition_page = RecognitionPage(self._label)
        self.backend_combo = self.recognition_page.backend_combo
        self.model_path = self.recognition_page.model_path
        self.browse_button = self.recognition_page.browse_button
        self.browse_button.clicked.connect(self._browse_model)
        self.language_edit = self.recognition_page.language_edit
        self.wake_aliases_edit = self.recognition_page.wake_aliases_edit
        self.device_combo = self.recognition_page.device_combo
        self.active_device_label = self.recognition_page.active_device_label
        self.action_label = self.recognition_page.action_label
        self.diagnostics_heading = self.recognition_page.diagnostics_heading
        self.diagnostics_output = self.recognition_page.diagnostics_output
        self.clear_diagnostics_button = self.recognition_page.clear_diagnostics_button
        self.pages.addWidget(self.recognition_page)

        self.models_page = ModelLibraryPage(
            model_library,
            ui_translations,
            cpu_runtime_available=whisper_server_available,
            gpu_runtime_available=whisper_gpu_server_available,
            current_selection=settings.stt if settings is not None else None,
            omnilingual_root=omnilingual_root,
        )
        self.models_page.selected.connect(self._select_library_model)
        self.pages.addWidget(self.models_page)

        self.command_model_page = CommandModelPage(
            ui_translations,
            current=settings.command_model if settings is not None else None,
            suggested_store=suggested_command_store,
        )
        self.pages.addWidget(self.command_model_page)

        self.tts_page = TtsPage(
            ui_translations,
            settings.tts if settings is not None else TtsSelection(),
            model_root=tts_model_root or Path.home() / ".local/share/kyrin/models/tts",
            routes=settings.tts_languages if settings is not None else (),
            enabled=settings.tts_enabled if settings is not None else True,
            preview=preview_tts,
        )
        self.pages.addWidget(self.tts_page)

        self.actions_page = DesktopActionsPage(app_catalog, settings, ui_translations)
        self.actions_page.telegram_pointer_grant_button.clicked.connect(
            self._grant_telegram_pointer
        )
        self.actions_page.desktop_scroll_grant_button.clicked.connect(
            self._grant_desktop_scroll
        )
        for action, button in self.actions_page.power_buttons.items():
            button.clicked.connect(
                lambda checked=False, selected=action: self._start_power(selected)
            )
        self.actions_page.power_preview_button.clicked.connect(self._preview_power)
        self.pages.addWidget(self.actions_page)

        self.screen_access_page = ScreenAccessPage(
            screen_access,
            ui_translations,
            screen_reader,
            ocr_default_root=ocr_default_root,
            ocr_selection=settings.ocr if settings is not None else None,
        )
        self.pages.addWidget(self.screen_access_page)

        self.preferences_page = PreferencesPage(self._label)
        self.ui_language_combo = self.preferences_page.ui_language_combo
        self._fill_languages()
        self.import_language_button = self.preferences_page.import_language_button
        self.import_language_button.clicked.connect(self._import_language)
        self.save_ui_button = self.preferences_page.save_ui_button
        self.save_ui_button.clicked.connect(self._save_ui_preferences)
        self.startup_checkbox = self.preferences_page.startup_checkbox
        self.save_startup_button = self.preferences_page.save_startup_button
        self.save_startup_button.clicked.connect(self._save_startup)
        self.clear_memory_button = self.preferences_page.clear_memory_button
        self.clear_memory_button.clicked.connect(self._clear_conversation_memory)
        self.review_memory_button = self.preferences_page.review_memory_button
        self.review_memory_button.clicked.connect(self._review_conversation_memory)
        self._memory_dialog: ArchivedMemoryDialog | None = None
        self.pages.addWidget(self.preferences_page)

        buttons = QHBoxLayout()
        self.apply_button = QPushButton()
        self.apply_button.clicked.connect(self._apply)
        buttons.addWidget(self.apply_button)
        self.listening_button = QPushButton()
        self.listening_button.clicked.connect(self._toggle_listening)
        buttons.addWidget(self.listening_button)
        self.microphone_off_button = QPushButton()
        self.microphone_off_button.clicked.connect(self._turn_microphone_off)
        buttons.addWidget(self.microphone_off_button)
        self.quit_button = QPushButton()
        self.quit_button.clicked.connect(self._quit)
        buttons.addWidget(self.quit_button)
        root.addLayout(buttons)

        self._select_page(0)
        self._translate_ui()
        self._load_fields()
        if load_error is not None:
            self._show_error(load_error)
            self.apply_button.setEnabled(False)
            self.listening_button.setEnabled(False)
            self.microphone_off_button.setEnabled(False)
        elif self._translations.load_error is not None:
            self._show_error(self._translations.load_error)
        elif startup_error is not None:
            self._show_error(startup_error)
        events.received.connect(self._on_event)
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    def _label(self, key: str) -> QLabel:
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.PlainText)
        self._labels[key] = label
        return label

    def _select_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for button_index, button in enumerate(self._nav_buttons.values()):
            button.setChecked(button_index == index)

    def _fill_languages(self) -> None:
        current = self._translations.preferences.locale
        self.ui_language_combo.clear()
        for locale, name in self._translations.languages():
            self.ui_language_combo.addItem(name, locale)
        self.ui_language_combo.setCurrentIndex(
            max(0, self.ui_language_combo.findData(current))
        )

    def _translate_ui(self) -> None:
        t = self._translations.text
        language = self._translations.active_locale.split("-", 1)[0]
        self.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft
            if language in {"ar", "fa", "he", "ur"}
            else Qt.LayoutDirection.LeftToRight
        )
        for label in (
            self.welcome_label,
            self.welcome_caption_label,
            self.scene_hint_label,
        ):
            label.setLayoutDirection(self.layoutDirection())
        self.setWindowTitle(t("window_title"))
        self.subtitle.setText(t("branding_subtitle"))
        self.sidebar_footer.setText(t("branding_footer"))
        self.power_dialog.cancel_button.setText(t("cancel_button"))
        for key, button in self._nav_buttons.items():
            button.setText(t(key))
        for key, label in self._labels.items():
            label.setText(t(key))
        self.feedback_label.setText(t("feedback_default"))
        self.browse_button.setText(t("browse"))
        self.apply_button.setText(t("save"))
        self.quit_button.setText(t("quit"))
        self.microphone_off_button.setText(t("microphone_off"))
        self.import_language_button.setText(t("import_language"))
        self.save_ui_button.setText(t("save"))
        self.startup_checkbox.setText(t("start_at_login"))
        self.actions_page.translate()
        self.screen_access_page.translate()
        self.models_page.translate()
        self.command_model_page.translate()
        self.tts_page.translate()
        self.save_startup_button.setText(t("apply_startup"))
        self.clear_memory_button.setText(t("conversation_memory_clear"))
        self.review_memory_button.setText(t("conversation_memory_review"))
        for index, key in enumerate(("auto", "cpu", "gpu")):
            self.device_combo.setItemText(index, t(key))
        if self.microphone_combo.count():
            self.microphone_combo.setItemText(0, t("default_microphone"))
        self._update_action_label()
        self._update_active_device_label()
        self.diagnostics_heading.setText(t("diagnostics_heading"))
        self.clear_diagnostics_button.setText(t("diagnostics_clear"))

    def _update_active_device_label(self) -> None:
        t = self._translations.text
        device = self._active_stt_device
        self.active_device_label.setText(
            t("device_actual_pending")
            if device is None
            else f"{t('device_actual')}: {device.value.upper()}"
        )

    def _update_action_label(self) -> None:
        if self._settings is None:
            return
        t = self._translations.text
        action_state = (
            t("actions_on")
            if self._settings.action_execution_enabled
            else t("actions_off")
        )
        self.action_label.setText(
            f"{action_state} · {len(self._settings.allowed_apps)} {t('allowed_apps')}"
        )

    def _import_language(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self._translations.text("language_file"), "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            locale = self._translations.import_pack(Path(path))
        except TranslationError as error:
            self.feedback_label.setText(str(error))
            return
        self._fill_languages()
        self.ui_language_combo.setCurrentIndex(self.ui_language_combo.findData(locale))
        self.feedback_label.setText(self._translations.text("language_added"))

    def _save_ui_preferences(self) -> None:
        preferences = UiPreferences(locale=self.ui_language_combo.currentData())
        try:
            self._translations.save(preferences)
        except TranslationError as error:
            self.feedback_label.setText(str(error))
            return
        self._translate_ui()
        self._fill_languages()
        self._refresh()
        self.feedback_label.setText(self._translations.text("ui_saved"))

    def _save_startup(self) -> None:
        registration = self._startup_registration
        if registration is None or self._settings is None:
            self.feedback_label.setText(self._translations.text("startup_unavailable"))
            return
        enabled = self.startup_checkbox.isChecked()
        candidate = replace(self._settings, start_at_login=enabled)
        try:
            previous = registration.enabled()
            registration.set_enabled(enabled)
            self._store.save(candidate)
        except (DesktopRegistrationError, SettingsError) as error:
            if previous != enabled:
                try:
                    registration.set_enabled(previous)
                except DesktopRegistrationError as rollback_error:
                    self._show_error(rollback_error)
                    return
            self._show_error(error)
            return
        self._settings = candidate
        self.feedback_label.setText(self._translations.text("startup_saved"))

    def _clear_conversation_memory(self) -> None:
        t = self._translations.text
        if (
            QMessageBox.question(
                self,
                t("conversation_memory_clear_title"),
                t("conversation_memory_clear_question"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            history = SqliteConversationHistory(default_history_path())
            try:
                history.clear()
            finally:
                history.close()
        except OSError, ValueError, sqlite3.Error:
            self.feedback_label.setText(t("conversation_memory_unavailable"))
            return
        self.feedback_label.setText(t("conversation_memory_cleared"))

    def _review_conversation_memory(self) -> None:
        try:
            dialog = ArchivedMemoryDialog(
                default_history_path(), self._translations.text, self
            )
        except OSError, ValueError, sqlite3.Error:
            self.feedback_label.setText(
                self._translations.text("conversation_memory_unavailable")
            )
            return
        self._memory_dialog = dialog
        dialog.open()

    def start_initial_session(self) -> None:
        if self._settings is not None:
            self._start_current()

    def _load_fields(self) -> None:
        t = self._translations.text
        self.microphone_combo.clear()
        self.microphone_combo.addItem(t("default_microphone"), None)
        try:
            for device in self._microphones.list_inputs():
                self.microphone_combo.addItem(device.label, device.key)
        except MicrophoneError as error:
            self._show_error(error)
        settings = self._settings
        registration = self._startup_registration
        self.startup_checkbox.setEnabled(
            settings is not None and registration is not None
        )
        self.save_startup_button.setEnabled(
            settings is not None and registration is not None
        )
        if registration is not None:
            try:
                self.startup_checkbox.setChecked(registration.enabled())
            except DesktopRegistrationError as error:
                self.startup_checkbox.setEnabled(False)
                self.save_startup_button.setEnabled(False)
                self._show_error(error)
        if settings is None:
            return
        key = settings.microphone_device_key
        if key is not None and self.microphone_combo.findData(key) < 0:
            self.microphone_combo.addItem(t("missing_microphone"), key)
        self.microphone_combo.setCurrentIndex(
            max(0, self.microphone_combo.findData(key))
        )
        stt = settings.stt
        if stt is not None:
            self.backend_combo.setCurrentIndex(
                max(0, self.backend_combo.findData(stt.backend))
            )
            self.model_path.setText(str(stt.model_path))
            self.language_edit.setText(stt.language)
            self.device_combo.setCurrentIndex(
                max(0, self.device_combo.findData(stt.device.value))
            )
        self.wake_aliases_edit.setText(", ".join(settings.wake_aliases))
        self._update_action_label()

    def _browse_model(self) -> None:
        backend = self.backend_combo.currentData()
        if backend in ("vosk", "omnilingual"):
            title = (
                "omnilingual_directory"
                if backend == "omnilingual"
                else "vosk_directory"
            )
            path = QFileDialog.getExistingDirectory(
                self,
                self._translations.text(title),
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, self._translations.text("whisper_file")
            )
        if path:
            self.model_path.setText(path)

    def _select_library_model(
        self, model: InstalledModel, device: DevicePreference
    ) -> None:
        self.backend_combo.setCurrentIndex(self.backend_combo.findData(model.backend))
        self.model_path.setText(str(model.model_path))
        self.language_edit.setText(model.language)
        self.device_combo.setCurrentIndex(self.device_combo.findData(device.value))
        self._select_page(2)
        self.feedback_label.setText(self._translations.text("models_selected"))

    def _candidate_settings(self) -> AppSettings:
        assert self._settings is not None
        raw_path = self.model_path.text().strip()
        stt: SttSelection | None = None
        if raw_path:
            path = Path(raw_path)
            backend = self.backend_combo.currentData()
            device = DevicePreference(self.device_combo.currentData())
            if not path.is_absolute():
                raise ValueError(self._translations.text("path_absolute"))
            if backend == "vosk" and not path.is_dir():
                raise ValueError(self._translations.text("vosk_missing"))
            if backend == "whisper" and not path.is_file():
                raise ValueError(self._translations.text("whisper_missing"))
            if backend == "omnilingual":
                from kyrin.stt.backends.omnilingual import model_files

                model_files(path)
                if self._omnilingual_python is None:
                    raise ValueError(
                        self._translations.text("omnilingual_runtime_missing")
                    )
            if backend == "vosk" and device is DevicePreference.GPU:
                raise DeviceUnavailableError(self._translations.text("models_vosk_cpu"))
            if backend == "vosk" and self.language_edit.text().strip() == "auto":
                raise ValueError(self._translations.text("vosk_language_required"))
            if backend == "whisper":
                if (
                    device is DevicePreference.GPU
                    and not self._whisper_gpu_server_available
                ):
                    raise DeviceUnavailableError(
                        self._translations.text("models_gpu_unavailable")
                    )
                if (
                    device is DevicePreference.CPU
                    and not self._whisper_server_available
                ):
                    raise ValueError(self._translations.text("whisper_server_missing"))
                if device is DevicePreference.AUTO and not (
                    self._whisper_server_available or self._whisper_gpu_server_available
                ):
                    raise ValueError(self._translations.text("whisper_server_missing"))
            stt = SttSelection(backend, path, self.language_edit.text().strip(), device)
        key = self.microphone_combo.currentData()
        if key is not None:
            available = {item.key for item in self._microphones.list_inputs()}
            if key not in available:
                raise MicrophoneError(self._translations.text("error_microphone"))
        selected_apps = self.actions_page.selected_apps()
        ocr = self.screen_access_page.selection()
        if ocr is not None and (
            self._ocr_default_root is None
            or selected_ocr_engine(ocr, self._ocr_default_root) is None
        ):
            raise ValueError(self._translations.text("screen_ocr_unavailable"))
        actions_enabled = self.actions_page.enabled_checkbox.isChecked()
        if (
            actions_enabled
            and not selected_apps
            and not self.actions_page.system_power_checkbox.isChecked()
            and not self.actions_page.desktop_scroll_checkbox.isChecked()
        ):
            raise ValueError(self._translations.text("action_select_one"))
        return replace(
            self._settings,
            microphone_device_key=key,
            stt=stt,
            command_model=self.command_model_page.selection(),
            ocr=ocr,
            tts=self.tts_page.selection(),
            tts_languages=self.tts_page.language_routes(),
            tts_enabled=self.tts_page.voice_enabled(),
            action_execution_enabled=actions_enabled,
            system_power_enabled=self.actions_page.system_power_checkbox.isChecked(),
            allowed_apps=selected_apps,
            allowed_chat_apps=self.actions_page.selected_chat_apps(),
            remember_telegram_pointer=self.actions_page.remember_telegram_pointer(),
            allow_desktop_scroll=self.actions_page.allow_desktop_scroll(),
            allowed_window_apps=self.actions_page.selected_window_apps(),
            allowed_close_apps=self.actions_page.selected_close_apps(),
            app_spoken_aliases=self.actions_page.selected_spoken_aliases(),
            wake_aliases=tuple(
                alias.strip()
                for alias in self.wake_aliases_edit.text().split(",")
                if alias.strip()
            ),
        )

    def _has_unsaved_changes(self) -> bool:
        assert self._settings is not None
        stt = self._settings.stt
        return (
            self.microphone_combo.currentData() != self._settings.microphone_device_key
            or self.model_path.text().strip()
            != (str(stt.model_path) if stt is not None else "")
            or self.backend_combo.currentData()
            != (stt.backend if stt is not None else "vosk")
            or self.language_edit.text().strip()
            != (stt.language if stt is not None else "en")
            or self.device_combo.currentData()
            != (stt.device.value if stt is not None else DevicePreference.AUTO.value)
            or tuple(
                alias.strip()
                for alias in self.wake_aliases_edit.text().split(",")
                if alias.strip()
            )
            != self._settings.wake_aliases
            or self.actions_page.has_unsaved_changes(self._settings)
            or self.command_model_page.has_unsaved_changes(self._settings.command_model)
            or self.screen_access_page.has_unsaved_changes(self._settings.ocr)
            or self.tts_page.has_unsaved_changes(
                self._settings.tts,
                self._settings.tts_languages,
                self._settings.tts_enabled,
            )
        )

    def _grant_telegram_pointer(self) -> None:
        if self._pointer_grant_process is not None:
            return
        if (
            self._settings is None
            or "telegram" not in self._settings.allowed_chat_apps
            or not self._settings.remember_telegram_pointer
            or self.actions_page.has_unsaved_changes(self._settings)
        ):
            self.actions_page.telegram_pointer_grant_status.setText(
                self._translations.text("telegram_pointer_save_first")
            )
            return
        process = QProcess(self)
        process.setProgram("/usr/bin/python3")
        process.setArguments([str(TELEGRAM_PORTAL_HELPER), "grant-control"])
        process.finished.connect(
            lambda code, _status: self._finish_telegram_pointer_grant(process, code)
        )
        process.errorOccurred.connect(
            lambda _error: self._finish_telegram_pointer_grant(process, -1)
        )
        self._pointer_grant_process = process
        self.actions_page.telegram_pointer_grant_button.setEnabled(False)
        self.actions_page.telegram_pointer_grant_status.setText(
            self._translations.text("telegram_pointer_grant_running")
        )
        process.start()

    def _finish_telegram_pointer_grant(self, process: QProcess, code: int) -> None:
        if self._pointer_grant_process is not process:
            return
        ready = (
            code == 0
            and b"CONTROL_GRANT_READY" in bytes(process.readAllStandardOutput())  # type: ignore[call-overload]
            and read_opaque_token(permission_token_path("telegram-control"))
            is not None
        )
        if ready:
            for legacy_name in ("telegram-keyboard", "telegram-pointer"):
                try:
                    permission_token_path(legacy_name).unlink(missing_ok=True)
                except OSError:
                    pass
        self._pointer_grant_process = None
        process.deleteLater()
        self.actions_page.telegram_pointer_grant_button.setEnabled(
            self.actions_page.telegram_pointer_checkbox.isChecked()
        )
        self.actions_page.telegram_pointer_grant_status.setText(
            self._translations.text(
                "telegram_pointer_grant_done"
                if ready else "telegram_pointer_grant_failed"
            )
        )

    def _grant_desktop_scroll(self) -> None:
        if self._scroll_grant_process is not None:
            return
        if (
            self._settings is None
            or not self._settings.allow_desktop_scroll
            or self.actions_page.has_unsaved_changes(self._settings)
        ):
            self.actions_page.desktop_scroll_grant_status.setText(
                self._translations.text("desktop_scroll_save_first")
            )
            return
        process = QProcess(self)
        process.setProgram("/usr/bin/python3")
        process.setArguments([str(SCROLL_HELPER), "grant"])
        process.finished.connect(
            lambda code, _status: self._finish_desktop_scroll_grant(process, code)
        )
        process.errorOccurred.connect(
            lambda _error: self._finish_desktop_scroll_grant(process, -1)
        )
        self._scroll_grant_process = process
        self.actions_page.desktop_scroll_grant_button.setEnabled(False)
        self.actions_page.desktop_scroll_grant_status.setText(
            self._translations.text("desktop_scroll_running")
        )
        process.start()

    def _finish_desktop_scroll_grant(self, process: QProcess, code: int) -> None:
        if self._scroll_grant_process is not process:
            return
        ready = (
            code == 0
            and b"SCROLL_GRANT_READY" in bytes(process.readAllStandardOutput())  # type: ignore[call-overload]
            and read_opaque_token(permission_token_path("desktop-scroll")) is not None
        )
        self._scroll_grant_process = None
        process.deleteLater()
        self.actions_page.desktop_scroll_grant_button.setEnabled(
            self.actions_page.desktop_scroll_checkbox.isChecked()
        )
        self.actions_page.desktop_scroll_grant_status.setText(
            self._translations.text(
                "desktop_scroll_done" if ready else "desktop_scroll_failed"
            )
        )

    def _apply(self) -> None:
        try:
            candidate = self._candidate_settings()
        except (ValueError, MicrophoneError, DeviceUnavailableError) as error:
            self._show_error(error)
            return
        status = self._controller.status()
        if status.state in (ApplicationState.STARTING, ApplicationState.RUNNING):
            self._pending_settings = candidate
            self._controller.request_stop()
            self.feedback_label.setText(self._translations.text("stopping_old"))
            return
        if status.state is ApplicationState.STOPPING:
            self._show_error(RuntimeError(self._translations.text("wait_stop")))
            return
        self._save_and_start(candidate)

    def _save_and_start(self, candidate: AppSettings) -> None:
        try:
            self._store.save(candidate)
        except SettingsError as error:
            self._show_error(error)
            return
        if self._settings is not None and (
            "telegram" in self._settings.allowed_chat_apps
            and "telegram" not in candidate.allowed_chat_apps
        ):
            try:
                permission_token_path("telegram-keyboard").unlink(missing_ok=True)
                permission_token_path("telegram-control").unlink(missing_ok=True)
            except OSError as error:
                self._show_error(error)
        if self._settings is not None and (
            self._settings.remember_telegram_pointer
            and not candidate.remember_telegram_pointer
        ):
            try:
                permission_token_path("telegram-pointer").unlink(missing_ok=True)
                permission_token_path("telegram-control").unlink(missing_ok=True)
            except OSError as error:
                self._show_error(error)
        if self._settings is not None and (
            self._settings.allow_desktop_scroll
            and not candidate.allow_desktop_scroll
        ):
            try:
                permission_token_path("desktop-scroll").unlink(missing_ok=True)
            except OSError as error:
                self._show_error(error)
        self._settings = candidate
        self.actions_page.set_pointer_grant_ready(
            read_opaque_token(permission_token_path("telegram-control")) is not None
        )
        self.actions_page.set_scroll_grant_ready(
            read_opaque_token(permission_token_path("desktop-scroll")) is not None
        )
        if self._screen_reader is not None and self._ocr_default_root is not None:
            self._screen_reader.set_engine(
                selected_ocr_engine(candidate.ocr, self._ocr_default_root)
            )
            self.screen_access_page.translate()
        if self._configure_tts is not None:
            self._configure_tts(
                candidate.tts, candidate.tts_languages, candidate.tts_enabled
            )
        self.models_page.set_current_selection(candidate.stt)
        self._update_action_label()
        self.feedback_label.setText(self._translations.text("saved"))
        self._start_current()

    def _start_current(self) -> None:
        assert self._settings is not None
        self._active_stt_device = None
        self._audio_ready = False
        self._update_active_device_label()
        try:
            self._controller.start(self._settings)
        except RuntimeError as error:
            self._show_error(error)
        self._refresh()

    def _toggle_listening(self) -> None:
        if self._settings is None:
            return
        status = self._controller.status().state
        if status is ApplicationState.RUNNING:
            self._controller.set_commands_active(
                not self._controller.commands_active()
            )
        elif status not in (ApplicationState.STOPPING,):
            if self._has_unsaved_changes():
                self.feedback_label.setText(self._translations.text("save_first"))
                return
            if self._settings.stt is None:
                self.feedback_label.setText(self._translations.text("choose_model"))
                return
            candidate = replace(self._settings, listening_enabled=True)
            try:
                self._store.save(candidate)
            except SettingsError as error:
                self._show_error(error)
                return
            self._settings = candidate
            self._start_current()
            self._controller.set_commands_active(True)
        self._refresh()

    def _turn_microphone_off(self) -> None:
        if self._settings is None:
            return
        # Stop capture even if saving the preference fails.
        self._microphone_off_pending = True
        self._controller.request_stop()
        candidate = replace(self._settings, listening_enabled=False)
        try:
            self._store.save(candidate)
        except SettingsError as error:
            self._microphone_off_pending = False
            self._show_error(error)
            return
        self._settings = candidate
        self._refresh()
        self.feedback_label.setText(
            self._translations.text(
                "voice_off"
                if not self._microphone_off_pending
                else "voice_turning_off"
            )
        )

    def _refresh(self) -> None:
        self._controller.expire_system_action()
        status = self._controller.status()
        if (
            self._microphone_off_pending
            and status.state is ApplicationState.STOPPED
        ):
            self._microphone_off_pending = False
            self.feedback_label.setText(self._translations.text("voice_off"))
        state_key = _STATE_KEYS[status.state]
        if status.state is ApplicationState.RUNNING:
            if not self._audio_ready:
                state_key = "state_mic_starting"
            elif not self._controller.commands_active():
                state_key = "state_standby"
        elif (
            status.state is ApplicationState.STOPPED
            and self._settings is not None
            and not self._settings.listening_enabled
        ):
            state_key = "state_paused"
        state_text = self._translations.text(state_key)
        self.status_label.setText(f"{self._translations.text('status')}: {state_text}")
        if status.error is not None and status.error is not self._last_status_error:
            self._show_error(status.error)
            self._last_status_error = status.error
        if self._pending_settings is not None and self._controller.wait_until_stopped(
            0
        ):
            candidate = self._pending_settings
            self._pending_settings = None
            if status.error is not None:
                self.feedback_label.setText(
                    self._translations.text("previous_failed")
                    + " "
                    + _friendly_error(status.error, self._translations.text)
                )
            else:
                self._save_and_start(candidate)
        if self._quitting and self._controller.wait_until_stopped(0):
            application = QApplication.instance()
            if application is not None:
                application.quit()
        self.listening_button.setText(
            self._translations.text("stop")
            if status.state is ApplicationState.RUNNING
            and self._controller.commands_active()
            else self._translations.text("start")
        )
        if self._settings is not None:
            self.listening_button.setEnabled(
                not self._quitting
                and status.state not in (
                    ApplicationState.STOPPING, ApplicationState.STARTING
                )
                and (status.state is not ApplicationState.RUNNING or self._audio_ready)
            )
            self.microphone_off_button.setEnabled(
                not self._quitting
                and self._settings.listening_enabled
                and status.state is not ApplicationState.STOPPING
            )
            self.apply_button.setEnabled(not self._quitting)

    def _on_event(self, event: ApplicationEvent) -> None:
        t = self._translations.text
        if isinstance(event, VoiceModeChanged):
            if event.mode is VoiceMode.OFF:
                self._turn_microphone_off()
                return
            self._controller.set_commands_active(event.mode is VoiceMode.ACTIVE)
            self._refresh()
            self.feedback_label.setText(
                t(
                    "voice_started"
                    if event.mode is VoiceMode.ACTIVE
                    else "voice_standby"
                )
            )
            return
        if isinstance(event, AudioCaptureReady):
            self._audio_ready = True
            self._refresh()
            return
        if isinstance(event, SpeechSessionEnded):
            self._audio_ready = False
            self._refresh()
        latency = self._action_latency.observe(event)
        if latency is not None:
            speech = (
                f"{latency.speech_to_result_ms:.0f} ms"
                if latency.speech_to_result_ms is not None
                else "—"
            )
            self.diagnostics_output.appendPlainText(
                f"{t('diagnostics_latency')}: {speech} "
                f"({t('diagnostics_final_to_result')}: "
                f"{latency.final_to_result_ms:.0f} ms)"
            )
        if isinstance(event, PowerPrompt):
            self._power_prompt = (
                event
                if event.stage
                in (PowerStage.CHECKING, PowerStage.FIRST, PowerStage.SECOND)
                else None
            )
            if self._power_prompt is not None:
                self.power_dialog.present(event, continue_label=t("continue_button"))
            else:
                self.power_dialog.dismiss()
            self.feedback_label.setText(event.text)
        elif isinstance(event, SttDeviceReady):
            self._active_stt_device = event.device
            self._update_active_device_label()
        elif isinstance(event, PresentedResponse):
            self.feedback_label.setText(event.text)
        elif isinstance(event, SpeechSynthesisError):
            self.feedback_label.setText(str(event))
            self.power_dialog.show_voice_error()
        elif (
            isinstance(event, TranscriptUpdate)
            and event.status is TranscriptStatus.FINAL
        ):
            self.feedback_label.setText(f"{t('heard')}: {event.text}")
            self.diagnostics_output.appendPlainText(
                f"{t('heard')} ({event.language or '?'}): {event.text or '—'}"
            )
        elif isinstance(event, CommandResolution):
            decision = (
                t("diagnostics_no_command")
                if event.intent is None
                else f"{event.intent.kind.value}: {event.intent.target}"
            )
            self.diagnostics_output.appendPlainText(
                f"{t('diagnostics_decision')}: {decision}"
            )
        elif isinstance(event, CommandPlanResolution):
            steps = " → ".join(
                f"{step.kind.value}: {step.target}" for step in event.plan.steps
            )
            self.diagnostics_output.appendPlainText(
                f"{t('diagnostics_decision')}: {steps}"
            )
        elif isinstance(event, ResponseRequest):
            self.diagnostics_output.appendPlainText(
                f"{t('diagnostics_reason')}: {event.kind.value}"
            )
        elif isinstance(event, ActionNotice):
            self.diagnostics_output.appendPlainText(
                f"{t('diagnostics_reason')}: {event.reason.value}"
            )
        elif isinstance(event, ActionFeedback):
            detail = f" ({event.error_code})" if event.error_code else ""
            self.diagnostics_output.appendPlainText(
                f"{t('diagnostics_result')}: {event.outcome.value}{detail}"
            )

    def _show_error(self, error: Exception) -> None:
        self.feedback_label.setText(_friendly_error(error, self._translations.text))

    def _start_power(self, action: PowerAction) -> None:
        self._controller.request_system_action(action)

    def _preview_power(self) -> None:
        if not self._controller.preview_system_action(PowerAction.POWER_OFF):
            self.feedback_label.setText(
                self._translations.text("power_safe_preview_busy")
            )

    def _quit(self) -> None:
        if self._pending_settings is not None:
            self._pending_settings = None
        self._quitting = True
        if self._pointer_grant_process is not None:
            self._pointer_grant_process.kill()
        if self._scroll_grant_process is not None:
            self._scroll_grant_process.kill()
        self.power_dialog.dismiss()
        self._controller.request_stop()
        self._refresh()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quitting:
            event.accept()
            return
        event.ignore()
        self.showMinimized()
