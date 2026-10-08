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
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from kyrin.app.app_permissions import AppPickerCatalog
from kyrin.app.controller import ApplicationController, ApplicationState
from kyrin.app.events import ApplicationEvent
from kyrin.app.platforms.xdg_startup import DesktopRegistrationError
from kyrin.app.qt.actions_page import DesktopActionsPage
from kyrin.app.qt.branding import LOGO_PATH
from kyrin.app.qt.dashboard import CosmicDashboard
from kyrin.app.qt.translations import (
    TranslationError,
    UiPreferences,
    UiTranslations,
)
from kyrin.app.settings import AppSettings, SttSelection
from kyrin.app.settings_store import SettingsError
from kyrin.audio.microphone.devices import MicrophoneResolver
from kyrin.audio.microphone.errors import MicrophoneError
from kyrin.responses.presenter import PresentedResponse
from kyrin.stt.device import DevicePreference
from kyrin.stt.errors import DeviceUnavailableError
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate

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
        ui_translations: UiTranslations,
        app_catalog: AppPickerCatalog | None = None,
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
        subtitle = QLabel("DESKTOP INTELLIGENCE")
        subtitle.setObjectName("Subtitle")
        side.addWidget(subtitle)
        side.addSpacing(34)
        self.pages = QStackedWidget()
        self._nav_buttons: dict[str, QPushButton] = {}
        for index, key in enumerate(
            ("dashboard", "audio", "recognition", "actions", "preferences")
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
        sidebar_footer = QLabel("KYRIN  /  V1 CONTROL CENTER")
        sidebar_footer.setWordWrap(True)
        side.addWidget(sidebar_footer)
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
        self.device_combo = QComboBox()
        self.device_combo.addItem("", DevicePreference.AUTO.value)
        self.device_combo.addItem("", DevicePreference.CPU.value)
        self.device_combo.addItem("", DevicePreference.GPU.value)
        self.device_combo.setAccessibleName("Speech processing device")
        speech_form.addRow(self._label("device"), self.device_combo)
        speech_layout.addLayout(speech_form)
        self.action_label = QLabel()
        self.action_label.setTextFormat(Qt.TextFormat.PlainText)
        self.action_label.setObjectName("Info")
        speech_layout.addWidget(self.action_label)
        speech_layout.addStretch()
        self.pages.addWidget(speech_page)

        self.actions_page = DesktopActionsPage(app_catalog, settings, ui_translations)
        self.pages.addWidget(self.actions_page)

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
        language = self._translations.preferences.locale.split("-", 1)[0]
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
        self.save_startup_button.setText(t("apply_startup"))
        for index, key in enumerate(("auto", "cpu", "gpu")):
            self.device_combo.setItemText(index, t(key))
        if self.microphone_combo.count():
            self.microphone_combo.setItemText(0, t("default_microphone"))
        self._update_action_label()

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
            if backend == "whisper" and not self._whisper_server_available:
                raise ValueError(self._translations.text("whisper_server_missing"))
            if device is DevicePreference.GPU:
                raise DeviceUnavailableError(
                    "Vosk and Whisper adapters currently support CPU only"
                )
            stt = SttSelection(backend, path, self.language_edit.text().strip(), device)
        key = self.microphone_combo.currentData()
        if key is not None:
            available = {item.key for item in self._microphones.list_inputs()}
            if key not in available:
                raise MicrophoneError("selected microphone is not available")
        selected_apps = self.actions_page.selected_apps()
        actions_enabled = self.actions_page.enabled_checkbox.isChecked()
        if actions_enabled and not selected_apps:
            raise ValueError(self._translations.text("action_select_one"))
        return replace(
            self._settings,
            microphone_device_key=key,
            stt=stt,
            action_execution_enabled=actions_enabled,
            allowed_apps=selected_apps,
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
            or self.actions_page.has_unsaved_changes(self._settings)
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
        self._update_action_label()
        self.feedback_label.setText(self._translations.text("saved"))
        self._start_current()

    def _start_current(self) -> None:
        assert self._settings is not None
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
        if isinstance(event, PresentedResponse):
            self.feedback_label.setText(event.text)
        elif (
            isinstance(event, TranscriptUpdate)
            and event.status is TranscriptStatus.FINAL
        ):
            self.feedback_label.setText(
                f"{self._translations.text('heard')}: {event.text}"
            )

    def _show_error(self, error: Exception) -> None:
        self.feedback_label.setText(_friendly_error(error, self._translations.text))

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
