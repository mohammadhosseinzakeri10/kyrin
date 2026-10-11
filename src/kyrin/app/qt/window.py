"""English-first desktop shell over the independent application controller."""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QColor, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from kyrin.actions.models import ActionFeedback, ActionNotice
from kyrin.app.app_permissions import AppPickerCatalog
from kyrin.app.controller import ApplicationController, ApplicationState
from kyrin.app.events import ApplicationEvent, SttDeviceReady
from kyrin.app.model_library import InstalledModel, ModelLibrary
from kyrin.app.platforms.xdg_startup import DesktopRegistrationError
from kyrin.app.qt.actions_page import DesktopActionsPage
from kyrin.app.qt.branding import LOGO_PATH
from kyrin.app.qt.command_model_page import CommandModelPage
from kyrin.app.qt.dashboard import CosmicDashboard
from kyrin.app.qt.model_library_page import ModelLibraryPage
from kyrin.app.qt.screen_access import ScreenAccess
from kyrin.app.qt.screen_access_page import ScreenAccessPage
from kyrin.app.qt.screen_text_reader import ScreenTextReader
from kyrin.app.qt.translations import (
    TranslationError,
    UiPreferences,
    UiTranslations,
)
from kyrin.app.settings import AppSettings, SttSelection
from kyrin.app.settings_store import SettingsError
from kyrin.audio.microphone.devices import MicrophoneResolver
from kyrin.audio.microphone.errors import MicrophoneError
from kyrin.commands.models import (
    CommandPlanResolution,
    CommandResolution,
    ResponseRequest,
)
from kyrin.responses.presenter import PresentedResponse
from kyrin.stt.device import ComputeDevice, DevicePreference
from kyrin.stt.errors import DeviceUnavailableError
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from kyrin.system_power.flow import PowerAction, PowerPrompt, PowerStage

_STYLE = """
QWidget#ControlWindow, QWidget#Content { background: #080b18; color: #e9eeff; }
QFrame#Sidebar { background: #0d1225; border-right: 1px solid #222b48; }
QLabel { color: #c0cbe9; font-size: 14px; }
QLabel#Brand { color: #d7c9ff; font-size: 26px; font-weight: 800; letter-spacing: 3px; }
QLabel#Subtitle { color: #8194bb; font-size: 10px; letter-spacing: 2px; }
QLabel#Welcome { color: #f6f2ff; font-family: 'Lato'; font-size: 47px;
                 font-weight: 900; letter-spacing: 2px; }
QLabel#WelcomeCaption { color: #e4e9ff; font-family: 'Lato'; font-size: 19px;
                        font-weight: 500; letter-spacing: 1px; }
QLabel#SceneHint { color: #a9bcef; font-family: 'Lato'; font-size: 13px;
                   font-weight: 600; letter-spacing: 2px; }
QLabel#PageTitle { color: #eff1ff; font-size: 28px; font-weight: 700; }
QLabel#Status { color: #89e8d4; padding: 8px 12px; background: #132437;
                border: 1px solid #244e5c; border-radius: 10px; }
QLabel#Feedback { color: #d7dbfa; padding: 12px 15px; background: #161c35;
                  border: 1px solid #29345a; border-radius: 10px; }
QLabel#Info { color: #aebae0; margin-top: 18px; }
QLabel#CosmicDashboard { background: #080c1b; border: 1px solid #283050; }
QWidget#HeroCopy { background: transparent; }
QPushButton { background: #27305a; color: #f2f4ff; border: 1px solid #435389;
              border-radius: 9px; padding: 10px 15px; font-weight: 600; }
QPushButton:hover { background: #364479; border-color: #847cff; }
QPushButton:disabled { color: #7883a4; background: #1b2137; border-color: #333b56; }
QPushButton#NavButton { text-align: left; background: transparent; border: 0;
                        color: #aab8de; padding: 13px 15px; }
QPushButton#NavButton:hover { background: #1c2545; }
QPushButton#NavButton:checked { background: #293666; color: #f7f3ff;
                                border-left: 3px solid #a389ff; }
QComboBox, QLineEdit { background: #151d35; color: #f2f4ff;
                       border: 1px solid #3b496f; border-radius: 7px;
                       min-height: 34px; padding: 3px 8px; }
QComboBox QAbstractItemView { background: #18213d; color: #f2f4ff; }
QTabWidget::pane { background: #111a31; border: 1px solid #3b496f;
                   border-radius: 8px; }
QTabBar::tab { background: #1b2746; color: #b9c8eb;
               border: 1px solid #3b496f; border-bottom: 0;
               padding: 9px 16px; margin-right: 4px; }
QTabBar::tab:selected { background: #344b84; color: #ffffff;
                        border-color: #9275ff; }
QTabBar::tab:hover:!selected { background: #293960; }
QCheckBox { color: #e2e9ff; spacing: 10px; padding: 7px 2px; }
QListWidget { background: #111a31; color: #e7edff;
              border: 1px solid #3b496f; border-radius: 8px;
              font-size: 13px; padding: 5px; }
QListWidget::item { padding: 5px 8px; border-radius: 5px; }
QListWidget::item:hover { background: #24345a; }
QListWidget::item:selected { background: #344b84; color: #ffffff; }
QListWidget::indicator { width: 15px; height: 15px; border-radius: 3px; }
QListWidget::indicator:unchecked { background: #1b2a49; border: 1px solid #7890bf; }
QListWidget::indicator:checked { background: #8d73ff; border: 1px solid #d6caff; }
"""


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
        model_library: ModelLibrary | None = None,
        suggested_command_store: Path | None = None,
        ui_translations: UiTranslations,
        app_catalog: AppPickerCatalog | None = None,
        screen_access: ScreenAccess | None = None,
        screen_reader: ScreenTextReader | None = None,
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
        self._active_stt_device: ComputeDevice | None = None
        self._pending_settings: AppSettings | None = None
        self._quitting = False
        self._last_status_error: Exception | None = None
        self._translations = ui_translations
        self._startup_registration = startup_registration
        self._labels: dict[str, QLabel] = {}
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setMinimumSize(980, 650)
        self.resize(1200, 760)
        self.setObjectName("ControlWindow")
        self.setStyleSheet(_STYLE)

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
        self.power_panel = QFrame()
        self.power_panel.setObjectName("Feedback")
        power_layout = QVBoxLayout(self.power_panel)
        self.power_prompt_label = QLabel()
        self.power_prompt_label.setTextFormat(Qt.TextFormat.PlainText)
        self.power_prompt_label.setWordWrap(True)
        power_layout.addWidget(self.power_prompt_label)
        power_buttons = QHBoxLayout()
        self.power_continue_button = QPushButton()
        self.power_continue_button.clicked.connect(self._confirm_power)
        power_buttons.addWidget(self.power_continue_button)
        self.power_cancel_button = QPushButton()
        self.power_cancel_button.clicked.connect(self._cancel_power)
        power_buttons.addWidget(self.power_cancel_button)
        power_layout.addLayout(power_buttons)
        self.power_panel.hide()
        root.addWidget(self.power_panel)
        shell.addWidget(content, 1)

        dashboard_page = QWidget()
        dashboard_layout = QVBoxLayout(dashboard_page)
        dashboard_layout.setContentsMargins(0, 0, 0, 0)
        self.cosmic_dashboard = CosmicDashboard()
        self.cosmic_dashboard.setObjectName("CosmicDashboard")
        self.cosmic_dashboard.setMinimumSize(600, 440)
        self.cosmic_dashboard.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        hero_layout = QHBoxLayout(self.cosmic_dashboard)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.addStretch(6)
        hero_copy = QWidget(self.cosmic_dashboard)
        hero_copy.setObjectName("HeroCopy")
        hero_copy_layout = QVBoxLayout(hero_copy)
        hero_copy_layout.setContentsMargins(0, 36, 52, 36)
        hero_copy_layout.addStretch()
        self.welcome_label = self._label("welcome")
        self.welcome_label.setObjectName("Welcome")
        self.welcome_label.setWordWrap(True)
        self.welcome_label.setAlignment(Qt.AlignmentFlag.AlignLeading)
        shadow = QGraphicsDropShadowEffect(self.welcome_label)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(1, 3, 13, 230))
        self.welcome_label.setGraphicsEffect(shadow)
        hero_copy_layout.addWidget(self.welcome_label)
        self.welcome_caption_label = self._label("welcome_caption")
        self.welcome_caption_label.setObjectName("WelcomeCaption")
        self.welcome_caption_label.setWordWrap(True)
        hero_copy_layout.addWidget(self.welcome_caption_label)
        hero_copy_layout.addSpacing(18)
        self.scene_hint_label = self._label("scene_hint")
        self.scene_hint_label.setObjectName("SceneHint")
        self.scene_hint_label.setWordWrap(True)
        hero_copy_layout.addWidget(self.scene_hint_label)
        hero_copy_layout.addStretch()
        hero_layout.addWidget(hero_copy, 5)
        dashboard_layout.addWidget(self.cosmic_dashboard, 1)
        self.pages.addWidget(dashboard_page)

        audio_page, audio_layout = self._page("audio_heading", "audio_caption")
        audio_form = QFormLayout()
        self.microphone_combo = QComboBox()
        self.microphone_combo.setAccessibleName("Input microphone")
        audio_form.addRow(self._label("microphone"), self.microphone_combo)
        audio_layout.addLayout(audio_form)
        audio_layout.addStretch()
        self.pages.addWidget(audio_page)

        speech_page, speech_layout = self._page(
            "recognition_heading", "recognition_caption"
        )
        speech_form = QFormLayout()
        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Vosk", "vosk")
        self.backend_combo.addItem("Whisper", "whisper")
        self.backend_combo.setAccessibleName("Speech recognition engine")
        speech_form.addRow(self._label("backend"), self.backend_combo)

        model_row = QHBoxLayout()
        self.model_path = QLineEdit()
        self.model_path.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.model_path.setAccessibleName("Speech model path")
        model_row.addWidget(self.model_path)
        browse = QPushButton()
        self.browse_button = browse
        browse.clicked.connect(self._browse_model)
        model_row.addWidget(browse)
        speech_form.addRow(self._label("model"), model_row)

        self.language_edit = QLineEdit("en")
        self.language_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.language_edit.setAccessibleName("Speech language code")
        speech_form.addRow(self._label("speech_language"), self.language_edit)
        self.wake_aliases_edit = QLineEdit()
        self.wake_aliases_edit.setAccessibleName("KYRIN wake word alternatives")
        speech_form.addRow(self._label("wake_aliases"), self.wake_aliases_edit)
        self.device_combo = QComboBox()
        self.device_combo.addItem("", DevicePreference.AUTO.value)
        self.device_combo.addItem("", DevicePreference.CPU.value)
        self.device_combo.addItem("", DevicePreference.GPU.value)
        self.device_combo.setAccessibleName("Speech processing device")
        speech_form.addRow(self._label("device"), self.device_combo)
        speech_layout.addLayout(speech_form)
        speech_layout.addWidget(self._label("speech_language_help"))
        self.active_device_label = QLabel()
        self.active_device_label.setTextFormat(Qt.TextFormat.PlainText)
        self.active_device_label.setObjectName("Info")
        speech_layout.addWidget(self.active_device_label)
        self.action_label = QLabel()
        self.action_label.setTextFormat(Qt.TextFormat.PlainText)
        self.action_label.setObjectName("Info")
        speech_layout.addWidget(self.action_label)
        self.diagnostics_heading = QLabel()
        self.diagnostics_heading.setObjectName("Info")
        speech_layout.addWidget(self.diagnostics_heading)
        self.diagnostics_output = QPlainTextEdit()
        self.diagnostics_output.setReadOnly(True)
        self.diagnostics_output.setMaximumBlockCount(40)
        self.diagnostics_output.setAccessibleName("Speech command diagnostics")
        speech_layout.addWidget(self.diagnostics_output)
        self.clear_diagnostics_button = QPushButton()
        self.clear_diagnostics_button.clicked.connect(self.diagnostics_output.clear)
        speech_layout.addWidget(self.clear_diagnostics_button)
        speech_layout.addStretch()
        self.pages.addWidget(speech_page)

        self.models_page = ModelLibraryPage(
            model_library,
            ui_translations,
            cpu_runtime_available=whisper_server_available,
            gpu_runtime_available=whisper_gpu_server_available,
            current_selection=settings.stt if settings is not None else None,
        )
        self.models_page.selected.connect(self._select_library_model)
        self.pages.addWidget(self.models_page)

        self.command_model_page = CommandModelPage(
            ui_translations,
            current=settings.command_model if settings is not None else None,
            suggested_store=suggested_command_store,
        )
        self.pages.addWidget(self.command_model_page)

        self.actions_page = DesktopActionsPage(app_catalog, settings, ui_translations)
        for action, button in self.actions_page.power_buttons.items():
            button.clicked.connect(
                lambda checked=False, selected=action: self._start_power(selected)
            )
        self.pages.addWidget(self.actions_page)

        self.screen_access_page = ScreenAccessPage(
            screen_access, ui_translations, screen_reader
        )
        self.pages.addWidget(self.screen_access_page)

        preferences_page, preferences_layout = self._page(
            "preferences_heading", "preferences_caption"
        )
        preferences_form = QFormLayout()
        self.ui_language_combo = QComboBox()
        self._fill_languages()
        preferences_form.addRow(
            self._label("interface_language"), self.ui_language_combo
        )
        self.import_language_button = QPushButton()
        self.import_language_button.clicked.connect(self._import_language)
        preferences_form.addRow("", self.import_language_button)
        preferences_layout.addLayout(preferences_form)
        preferences_layout.addWidget(self._label("language_help"))
        self.save_ui_button = QPushButton()
        self.save_ui_button.clicked.connect(self._save_ui_preferences)
        preferences_layout.addWidget(self.save_ui_button)
        preferences_layout.addSpacing(24)
        self.startup_checkbox = QCheckBox()
        preferences_layout.addWidget(self.startup_checkbox)
        self.save_startup_button = QPushButton()
        self.save_startup_button.clicked.connect(self._save_startup)
        preferences_layout.addWidget(self.save_startup_button)
        preferences_layout.addStretch()
        self.pages.addWidget(preferences_page)

        buttons = QHBoxLayout()
        self.apply_button = QPushButton()
        self.apply_button.clicked.connect(self._apply)
        buttons.addWidget(self.apply_button)
        self.listening_button = QPushButton()
        self.listening_button.clicked.connect(self._toggle_listening)
        buttons.addWidget(self.listening_button)
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

    def _page(self, heading: str, caption: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 25, 20, 20)
        title = self._label(heading)
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        layout.addWidget(self._label(caption))
        layout.addSpacing(24)
        return page, layout

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
        self.power_cancel_button.setText(t("cancel_button"))
        for key, button in self._nav_buttons.items():
            button.setText(t(key))
        for key, label in self._labels.items():
            label.setText(t(key))
        self.feedback_label.setText(t("feedback_default"))
        self.browse_button.setText(t("browse"))
        self.apply_button.setText(t("save"))
        self.quit_button.setText(t("quit"))
        self.import_language_button.setText(t("import_language"))
        self.save_ui_button.setText(t("save"))
        self.startup_checkbox.setText(t("start_at_login"))
        self.actions_page.translate()
        self.screen_access_page.translate()
        self.models_page.translate()
        self.command_model_page.translate()
        self.save_startup_button.setText(t("apply_startup"))
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
        if backend == "vosk":
            path = QFileDialog.getExistingDirectory(
                self, self._translations.text("vosk_directory")
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
            if backend == "vosk" and device is DevicePreference.GPU:
                raise DeviceUnavailableError(
                    self._translations.text("models_vosk_cpu")
                )
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
        actions_enabled = self.actions_page.enabled_checkbox.isChecked()
        if (
            actions_enabled
            and not selected_apps
            and not self.actions_page.system_power_checkbox.isChecked()
        ):
            raise ValueError(self._translations.text("action_select_one"))
        return replace(
            self._settings,
            microphone_device_key=key,
            stt=stt,
            command_model=self.command_model_page.selection(),
            action_execution_enabled=actions_enabled,
            system_power_enabled=self.actions_page.system_power_checkbox.isChecked(),
            allowed_apps=selected_apps,
            allowed_chat_apps=self.actions_page.selected_chat_apps(),
            allowed_window_apps=self.actions_page.selected_window_apps(),
            allowed_close_apps=self.actions_page.selected_close_apps(),
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
        self._settings = candidate
        self.models_page.set_current_selection(candidate.stt)
        self._update_action_label()
        self.feedback_label.setText(self._translations.text("saved"))
        self._start_current()

    def _start_current(self) -> None:
        assert self._settings is not None
        self._active_stt_device = None
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
        if status in (ApplicationState.RUNNING, ApplicationState.STARTING):
            candidate = replace(self._settings, listening_enabled=False)
            try:
                self._store.save(candidate)
            except SettingsError as error:
                self._show_error(error)
                return
            self._settings = candidate
            self._controller.request_stop()
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
        self._refresh()

    def _refresh(self) -> None:
        self._controller.expire_system_action()
        status = self._controller.status()
        state_text = (
            self._translations.text(_STATE_KEYS[ApplicationState.PAUSED])
            if status.state is ApplicationState.STOPPED
            and self._settings is not None
            and not self._settings.listening_enabled
            else self._translations.text(_STATE_KEYS[status.state])
        )
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
            if status.state in (ApplicationState.STARTING, ApplicationState.RUNNING)
            else self._translations.text("start")
        )
        if self._settings is not None:
            self.listening_button.setEnabled(
                not self._quitting and status.state is not ApplicationState.STOPPING
            )
            self.apply_button.setEnabled(not self._quitting)

    def _on_event(self, event: ApplicationEvent) -> None:
        t = self._translations.text
        if isinstance(event, PowerPrompt):
            self._power_prompt = (
                event if event.stage in (PowerStage.FIRST, PowerStage.SECOND) else None
            )
            self.power_panel.setVisible(self._power_prompt is not None)
            if self._power_prompt is not None:
                self.power_prompt_label.setText(event.text)
                self.power_continue_button.setText(
                    t("continue_button")
                    if event.stage is PowerStage.FIRST
                    else event.phrase or t("confirm_button")
                )
                self.showNormal()
                self.raise_()
                self.activateWindow()
            self.feedback_label.setText(event.text)
        elif isinstance(event, SttDeviceReady):
            self._active_stt_device = event.device
            self._update_active_device_label()
        elif isinstance(event, PresentedResponse):
            self.feedback_label.setText(event.text)
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

    def _confirm_power(self) -> None:
        prompt = self._power_prompt
        if prompt is not None:
            self._controller.respond_to_system_action(
                prompt.request_id,
                "continue" if prompt.stage is PowerStage.FIRST else prompt.phrase or "",
            )

    def _cancel_power(self) -> None:
        prompt = self._power_prompt
        if prompt is not None:
            self._controller.respond_to_system_action(prompt.request_id, "cancel")

    def _quit(self) -> None:
        if self._pending_settings is not None:
            self._pending_settings = None
        self._quitting = True
        self._controller.request_stop()
        self._refresh()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quitting:
            event.accept()
            return
        event.ignore()
        self.showMinimized()
