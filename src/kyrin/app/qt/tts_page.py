"""Local, language-routed voice settings with no in-app model downloads."""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from kyrin.app.qt.page_layout import scrollable_page_layout
from kyrin.app.qt.translations import UiTranslations
from kyrin.app.settings import TtsLanguageRoute, TtsSelection
from kyrin.stt.device import DevicePreference
from kyrin.tts.kokoro_voices import kokoro_voice_options
from kyrin.tts.qwen import QWEN_SPEAKERS
from kyrin.tts.runtime import (
    available_tts_adapters,
    inspect_tts_model,
    validate_tts_selection,
)
from kyrin.tts.tempo import tempo_available


class _VoiceEditor(QWidget):
    """One language's model, speaker, and device controls."""

    def __init__(
        self,
        translations: UiTranslations,
        current: TtsSelection,
        *,
        language: str,
        model_root: Path,
        preview: Callable[[str, str, TtsSelection], bool] | None,
    ) -> None:
        super().__init__()
        self._translations = translations
        self._preview = preview
        self.language = language
        self.model_root = model_root
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.engine = QComboBox()
        for backend in (
            "speech-dispatcher",
            *(adapter.key for adapter in available_tts_adapters()),
        ):
            self.engine.addItem("", backend)
        if self.engine.findData(current.backend) < 0:
            self.engine.addItem(
                f"{current.backend} (adapter unavailable)", current.backend
            )
        self.engine.currentIndexChanged.connect(self._engine_changed)
        self.engine_label = QLabel()
        form.addRow(self.engine_label, self.engine)

        self.installed = QComboBox()
        self.installed.currentIndexChanged.connect(self._installed_changed)
        self.refresh = QPushButton(self._translations.text("tts_refresh"))
        self.refresh.setObjectName("TtsUtilityButton")
        self.refresh.setMinimumWidth(112)
        self.refresh.setFixedHeight(38)
        self.refresh.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.refresh.clicked.connect(self.refresh_installed)
        installed_row = QHBoxLayout()
        installed_row.addWidget(self.installed, 1)
        installed_row.addWidget(self.refresh)
        self.installed_label = QLabel()
        form.addRow(self.installed_label, installed_row)

        self.model_path = QLineEdit(str(current.model_path or ""))
        self.model_path.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.model_path.editingFinished.connect(self._detect_path)
        model_row = QHBoxLayout()
        model_row.addWidget(self.model_path)
        self.browse = QPushButton(self._translations.text("browse"))
        self.browse.setObjectName("TtsUtilityButton")
        self.browse.setMinimumWidth(112)
        self.browse.setFixedHeight(38)
        self.browse.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.browse.clicked.connect(self._browse)
        model_row.addWidget(self.browse)
        self.folder_label = QLabel()
        form.addRow(self.folder_label, model_row)

        self.voice = QComboBox()
        self.voice_label = QLabel()
        form.addRow(self.voice_label, self.voice)
        self.voice_number = QSpinBox()
        self.voice_number.setRange(0, 255)
        self.voice_number.setValue(
            int(current.voice) if current.voice.isdecimal() else 0
        )
        self.voice_number_label = QLabel("Speaker ID")
        form.addRow(self.voice_number_label, self.voice_number)
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.5, 1.5)
        self.speed.setSingleStep(0.05)
        self.speed.setDecimals(2)
        self.speed.setValue(current.speed)
        self.speed_label = QLabel()
        form.addRow(self.speed_label, self.speed)
        self.device = QComboBox()
        for option in DevicePreference:
            self.device.addItem("", option.value)
        self.device.setCurrentIndex(self.device.findData(current.device.value))
        self.device_label = QLabel()
        form.addRow(self.device_label, self.device)
        layout.addLayout(form)

        self.sample_label = QLabel()
        self.sample = QLineEdit(
            "سلام، من کایرین هستم." if language == "fa" else "Hello. This is KYRIN."
        )
        layout.addWidget(self.sample_label)
        layout.addWidget(self.sample)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.preview_button = QPushButton()
        self.preview_button.clicked.connect(self._test_current)
        layout.addWidget(self.preview_button)
        layout.addStretch()

        self.engine.setCurrentIndex(self.engine.findData(current.backend))
        self._engine_changed()
        self.refresh_installed()
        index = self.voice.findData(current.voice)
        if index >= 0:
            self.voice.setCurrentIndex(index)
        self.translate()

    def _engine_changed(self) -> None:
        selected = self.voice.currentData()
        backend = self.engine.currentData()
        named_kokoro = (
            kokoro_voice_options(Path(self.model_path.text().strip()), self.language)
            if backend == "kokoro"
            else ()
        )
        self._use_named_voice = backend in {
            "speech-dispatcher",
            "kitten",
            "chatterbox",
            "qwen3tts",
        } or bool(named_kokoro)
        # Model discovery must work from the default system-voice state too.
        self.voice.setVisible(self._use_named_voice)
        self.voice_label.setVisible(self._use_named_voice)
        self.voice_number.setVisible(not self._use_named_voice)
        self.voice_number_label.setVisible(not self._use_named_voice)
        self.speed.setEnabled(
            backend != "chatterbox" and (backend != "qwen3tts" or tempo_available())
        )
        if backend == "chatterbox" or (backend == "qwen3tts" and not tempo_available()):
            self.speed.setValue(1.0)
        self.voice.clear()
        if backend == "kitten":
            for index, name in enumerate(
                (
                    "expr-voice-2-m",
                    "expr-voice-2-f",
                    "expr-voice-3-m",
                    "expr-voice-3-f",
                    "expr-voice-4-m",
                    "expr-voice-4-f",
                    "expr-voice-5-m",
                    "expr-voice-5-f",
                )
            ):
                self.voice.addItem(name, str(index))
        elif backend == "chatterbox":
            self.voice.addItem("Built-in voice", "0")
        elif backend == "qwen3tts":
            for index, name in enumerate(QWEN_SPEAKERS):
                self.voice.addItem(name, str(index))
        elif named_kokoro:
            for speaker_id, label in named_kokoro:
                self.voice.addItem(label, speaker_id)
        else:
            for name in ("default", "male1", "male2", "female1", "female2"):
                self.voice.addItem(name, name)
        index = self.voice.findData(selected)
        if index >= 0:
            self.voice.setCurrentIndex(index)
        self.refresh_installed()

    def refresh_installed(self) -> None:
        self.installed.blockSignals(True)
        self.installed.clear()
        self.installed.addItem(self._translations.text("tts_select_installed"), None)
        if self.model_root.is_dir():
            for entry in sorted(self.model_root.iterdir()):
                if not entry.is_dir() or entry.is_symlink():
                    continue
                # Accept both existing flat installs and family/model folders.
                candidates = (entry, *sorted(entry.iterdir()))
                for folder in candidates:
                    if not folder.is_dir() or folder.is_symlink():
                        continue
                    try:
                        model = inspect_tts_model(folder)
                    except ValueError:
                        continue
                    label = folder.relative_to(self.model_root)
                    self.installed.addItem(f"{label} ({model.family})", str(folder))
        selected = self.installed.findData(self.model_path.text().strip())
        self.installed.setCurrentIndex(max(0, selected))
        self.installed.blockSignals(False)

    def _installed_changed(self) -> None:
        selected = self.installed.currentData()
        if isinstance(selected, str):
            self.model_path.setText(selected)
            self._detect_path()

    def _detect_path(self) -> None:
        path = self.model_path.text().strip()
        if not path:
            return
        try:
            family = inspect_tts_model(Path(path)).family
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        index = self.engine.findData(family)
        if self.engine.currentIndex() == index:
            self._engine_changed()
        else:
            self.engine.setCurrentIndex(index)
        self.status.clear()

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, self._translations.text("tts_select_folder"), str(self.model_root)
        )
        if folder:
            self.model_path.setText(folder)
            self._detect_path()

    def draft(self) -> TtsSelection:
        backend = self.engine.currentData()
        voice = (
            self.voice.currentData()
            if self._use_named_voice
            else str(self.voice_number.value())
        )
        return TtsSelection(
            backend=backend,
            model_path=(
                Path(self.model_path.text().strip())
                if backend != "speech-dispatcher"
                else None
            ),
            voice=voice,
            speed=self.speed.value(),
            device=DevicePreference(self.device.currentData()),
        )

    def selection(self) -> TtsSelection:
        selected = self.draft()
        validate_tts_selection(selected)
        return selected

    def _test_current(self) -> None:
        if self._preview is None or not self.sample.text().strip():
            self.status.setText(self._translations.text("tts_preview_unavailable"))
            return
        try:
            selected = self.draft()
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        if self._preview(self.sample.text().strip(), self.language, selected):
            self.status.setText(self._translations.text("tts_preview_started"))
        else:
            self.status.setText(self._translations.text("tts_preview_unavailable"))

    def translate(self) -> None:
        t = self._translations.text
        self.engine_label.setText(t("tts_engine"))
        self.installed_label.setText(t("tts_installed"))
        self.folder_label.setText(t("tts_folder"))
        self.voice_label.setText(t("tts_voice"))
        self.speed_label.setText(t("tts_speed"))
        self.device_label.setText(t("tts_device"))
        self.sample_label.setText(t("tts_sample_text"))
        self.engine.setItemText(0, t("tts_system"))
        for adapter in available_tts_adapters():
            self.engine.setItemText(self.engine.findData(adapter.key), adapter.label)
        self.browse.setText(t("browse"))
        self.refresh.setText(t("tts_refresh"))
        self.installed.setItemText(0, t("tts_select_installed"))
        self.preview_button.setText(t("tts_preview"))
        for index, key in enumerate(("auto", "cpu", "gpu")):
            self.device.setItemText(index, t(key))


class TtsPage(QWidget):
    """Default voice plus independently selectable language-specific voices."""

    def __init__(
        self,
        translations: UiTranslations,
        current: TtsSelection,
        *,
        model_root: Path,
        routes: tuple[TtsLanguageRoute, ...] = (),
        enabled: bool = True,
        preview: Callable[[str, str, TtsSelection], bool] | None = None,
    ) -> None:
        super().__init__()
        self._translations = translations
        self.model_root = model_root
        self._preview = preview
        layout, self.scroll_area = scrollable_page_layout(self)
        self.title = QLabel()
        self.title.setObjectName("PageTitle")
        layout.addWidget(self.title)
        self.caption = QLabel()
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)
        self.enabled_checkbox = QCheckBox()
        self.enabled_checkbox.setChecked(enabled)
        layout.addWidget(self.enabled_checkbox)
        self.tabs = QTabWidget()
        self.tabs.setMinimumHeight(500)
        layout.addWidget(self.tabs)
        self._editors: dict[str, _VoiceEditor] = {}
        self._add_editor("en", current, label="Default / English")
        for route in routes:
            self._add_editor(route.language, route.selection)
        row = QHBoxLayout()
        self.add_button = QPushButton()
        self.add_button.clicked.connect(self._ask_language)
        row.addWidget(self.add_button)
        self.remove_button = QPushButton()
        self.remove_button.clicked.connect(self._remove_current)
        row.addWidget(self.remove_button)
        layout.addLayout(row)
        # Keep the original controls available to callers of the settings page.
        primary = self._editors["en"]
        self.engine = primary.engine
        self.installed = primary.installed
        self.model_path = primary.model_path
        self.voice = primary.voice
        self.speed = primary.speed
        self.device = primary.device
        self.status = primary.status
        self.preview_button = primary.preview_button
        self.translate()

    def _add_editor(
        self, language: str, selection: TtsSelection, *, label: str | None = None
    ) -> None:
        editor = _VoiceEditor(
            self._translations,
            selection,
            language=language,
            model_root=self.model_root,
            preview=self._preview,
        )
        self._editors[language] = editor
        self.tabs.addTab(editor, label or language)

    def _ask_language(self) -> None:
        language, ok = QInputDialog.getText(
            self,
            self._translations.text("tts_add_language"),
            self._translations.text("tts_language_code"),
        )
        if ok:
            try:
                self.add_language(language.strip())
            except ValueError as exc:
                self.status.setText(str(exc))

    def add_language(self, language: str) -> None:
        TtsLanguageRoute(language, TtsSelection())
        if language == "en" or language in self._editors:
            raise ValueError("This TTS language already has a voice")
        self._add_editor(language, TtsSelection())
        self.tabs.setCurrentWidget(self._editors[language])

    def _remove_current(self) -> None:
        index = self.tabs.currentIndex()
        if index <= 0:
            return
        editor = self.tabs.widget(index)
        assert isinstance(editor, _VoiceEditor)
        del self._editors[editor.language]
        self.tabs.removeTab(index)
        editor.deleteLater()

    def refresh_installed(self) -> None:
        self._editors["en"].refresh_installed()

    def selection(self) -> TtsSelection:
        return self._editors["en"].selection()

    def voice_enabled(self) -> bool:
        return self.enabled_checkbox.isChecked()

    def language_routes(self) -> tuple[TtsLanguageRoute, ...]:
        return tuple(
            TtsLanguageRoute(language, editor.selection())
            for language, editor in self._editors.items()
            if language != "en"
        )

    def has_unsaved_changes(
        self,
        current: TtsSelection,
        routes: tuple[TtsLanguageRoute, ...] = (),
        enabled: bool = True,
    ) -> bool:
        try:
            return (
                self.voice_enabled() != enabled
                or self._editors["en"].draft() != current
                or tuple(
                    TtsLanguageRoute(language, editor.draft())
                    for language, editor in self._editors.items()
                    if language != "en"
                )
                != routes
            )
        except ValueError, RuntimeError:
            return True

    def translate(self) -> None:
        t = self._translations.text
        self.title.setText(t("tts_heading"))
        self.caption.setText(t("tts_caption"))
        self.enabled_checkbox.setText(t("tts_enabled"))
        self.add_button.setText(t("tts_add_language"))
        self.remove_button.setText(t("tts_remove_language"))
        for editor in self._editors.values():
            editor.translate()
