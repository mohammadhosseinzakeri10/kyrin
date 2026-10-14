"""CPU/GPU views and asynchronous local imports for offline STT models."""

from pathlib import Path
from threading import Thread

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from kyrin.app.model_library import (
    InstalledModel,
    ModelLibrary,
    ModelLibraryError,
    vosk_language_hint,
)
from kyrin.app.qt.page_layout import scrollable_page_layout
from kyrin.app.qt.translations import UiTranslations
from kyrin.app.settings import SttSelection
from kyrin.stt.device import ComputeDevice, DevicePreference


class _ImportEvents(QObject):
    completed = Signal(object)
    failed = Signal(str)


class ModelLibraryPage(QWidget):
    """List model/device compatibility without claiming a GPU exists."""

    selected = Signal(object, object)

    def __init__(
        self,
        library: ModelLibrary | None,
        translations: UiTranslations,
        *,
        cpu_runtime_available: bool,
        gpu_runtime_available: bool,
        current_selection: SttSelection | None,
    ) -> None:
        super().__init__()
        self._library = library
        self._translations = translations
        self._cpu_runtime_available = cpu_runtime_available
        self._gpu_runtime_available = gpu_runtime_available
        self._current_selection = current_selection
        self._busy = False
        self._events = _ImportEvents(self)
        self._events.completed.connect(self._import_completed)
        self._events.failed.connect(self._import_failed)

        layout, self.scroll_area = scrollable_page_layout(self)
        self.title = QLabel()
        self.title.setObjectName("PageTitle")
        layout.addWidget(self.title)
        self.caption = QLabel()
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)

        import_row = QHBoxLayout()
        self.engine_label = QLabel()
        import_row.addWidget(self.engine_label)
        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Whisper", "whisper")
        self.backend_combo.addItem("Vosk", "vosk")
        self.backend_combo.setAccessibleName("Model engine to import")
        import_row.addWidget(self.backend_combo)
        self.language_label = QLabel()
        import_row.addWidget(self.language_label)
        self.language_edit = QLineEdit("auto")
        self.language_edit.setAccessibleName("Imported model language code")
        self.language_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        import_row.addWidget(self.language_edit)
        self.backend_combo.currentIndexChanged.connect(self._backend_changed)
        layout.addLayout(import_row)

        self.tabs = QTabWidget()
        self.tabs.setMinimumHeight(320)
        self.lists: list[QListWidget] = []
        self.import_buttons: dict[ComputeDevice, QPushButton] = {}
        for index in range(3):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            model_list = QListWidget()
            model_list.setAccessibleName("Installed speech models")
            model_list.itemDoubleClicked.connect(lambda item: self._use_selected())
            page_layout.addWidget(model_list)
            self.lists.append(model_list)
            if index:
                device = ComputeDevice.CPU if index == 1 else ComputeDevice.GPU
                button = QPushButton()
                button.clicked.connect(
                    lambda checked=False, selected=device: self._start_import(selected)
                )
                page_layout.addWidget(button)
                self.import_buttons[device] = button
            self.tabs.addTab(page, "")
        layout.addWidget(self.tabs)
        self.use_button = QPushButton()
        self.use_button.clicked.connect(self._use_selected)
        layout.addWidget(self.use_button)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.translate()
        self.refresh()

    def translate(self) -> None:
        t = self._translations.text
        self.title.setText(t("models_heading"))
        self.caption.setText(t("models_caption"))
        self.engine_label.setText(t("backend"))
        self.language_label.setText(t("speech_language"))
        for index, key in enumerate(("models_all", "models_cpu", "models_gpu")):
            self.tabs.setTabText(index, t(key))
        self.language_edit.setPlaceholderText(t("models_language"))
        self.import_buttons[ComputeDevice.CPU].setText(t("models_import_cpu"))
        self.import_buttons[ComputeDevice.GPU].setText(t("models_import_gpu"))
        self.use_button.setText(t("models_use"))
        self._fill_lists()

    def refresh(self) -> None:
        self._fill_lists()

    def _backend_changed(self) -> None:
        """Replace only the Whisper auto default when Vosk is chosen."""
        language = self.language_edit.text().strip()
        backend = self.backend_combo.currentData()
        if backend == "vosk" and language == "auto":
            self.language_edit.setText("en")

    def _models(self) -> tuple[InstalledModel, ...]:
        models = self._library.list_models() if self._library is not None else ()
        current = self._current_selection
        if current is not None and all(
            model.model_path != current.model_path for model in models
        ):
            devices = (
                frozenset({ComputeDevice.CPU})
                if current.backend == "vosk"
                else frozenset({ComputeDevice.CPU, ComputeDevice.GPU})
            )
            models = (
                *models,
                InstalledModel(
                    "external",
                    current.model_path.name,
                    current.backend,
                    current.language,
                    current.model_path,
                    devices,
                    "",
                ),
            )
        return models

    def _fill_lists(self) -> None:
        t = self._translations.text
        models = self._models()
        for index, model_list in enumerate(self.lists):
            model_list.clear()
            device = (
                None
                if index == 0
                else ComputeDevice.CPU
                if index == 1
                else ComputeDevice.GPU
            )
            for model in models:
                if device is not None and device not in model.devices:
                    continue
                names = "/".join(
                    item.value.upper()
                    for item in sorted(model.devices, key=lambda item: item.value)
                )
                label = (
                    f"{model.name} · {model.backend.title()} · "
                    f"{model.language} · {names}"
                )
                if model.model_id == "external":
                    label += f" · {t('models_external')}"
                if (
                    device is ComputeDevice.GPU
                    and model.backend == "whisper"
                    and not self._gpu_runtime_available
                ):
                    label += f" · {t('models_gpu_unavailable')}"
                entry = QListWidgetItem(label)
                entry.setData(Qt.ItemDataRole.UserRole, model)
                model_list.addItem(entry)
            if model_list.count() == 0:
                entry = QListWidgetItem(t("models_empty"))
                entry.setFlags(Qt.ItemFlag.NoItemFlags)
                model_list.addItem(entry)

    def _start_import(self, device: ComputeDevice) -> None:
        t = self._translations.text
        if self._library is None:
            self.status.setText(t("models_unavailable"))
            return
        if self._busy:
            return
        backend = self.backend_combo.currentData()
        if backend == "vosk" and device is ComputeDevice.GPU:
            self.status.setText(t("models_vosk_cpu"))
            return
        language = self.language_edit.text().strip()
        if not language or any(character.isspace() for character in language):
            self.status.setText(t("models_language_required"))
            return
        if backend == "vosk" and language == "auto":
            self.status.setText(t("vosk_language_required"))
            return
        if backend == "vosk":
            selected = QFileDialog.getExistingDirectory(self, t("vosk_directory"))
        else:
            selected, _ = QFileDialog.getOpenFileName(
                self, t("whisper_file"), "", "Whisper model (*.bin)"
            )
        if not selected:
            return
        source = Path(selected)
        if (
            backend == "vosk"
            and (hint := vosk_language_hint(source)) is not None
            and hint != language.lower().split("-")[0]
        ):
            self.status.setText(t("models_vosk_language_mismatch").format(hint=hint))
            return
        self._busy = True
        for button in self.import_buttons.values():
            button.setEnabled(False)
        self.status.setText(t("models_importing"))
        library = self._library

        def import_in_background() -> None:
            try:
                model = library.import_model(
                    source,
                    backend=backend,
                    language=language,
                    requested_device=device,
                )
            except ModelLibraryError as error:
                self._events.failed.emit(str(error))
            else:
                self._events.completed.emit(model)

        Thread(
            target=import_in_background, name="kyrin-model-import", daemon=True
        ).start()

    def _import_completed(self, model: InstalledModel) -> None:
        self._busy = False
        for button in self.import_buttons.values():
            button.setEnabled(True)
        self.refresh()
        if (
            model.backend == "whisper"
            and model.language != self.language_edit.text().strip()
        ):
            self.status.setText(self._translations.text("models_reused_language"))
        else:
            self.status.setText(self._translations.text("models_imported"))

    def _import_failed(self, message: str) -> None:
        self._busy = False
        for button in self.import_buttons.values():
            button.setEnabled(True)
        self.status.setText(message)

    def _use_selected(self) -> None:
        t = self._translations.text
        index = self.tabs.currentIndex()
        item = self.lists[index].currentItem()
        if item is None:
            self.status.setText(t("models_select_first"))
            return
        model = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(model, InstalledModel):
            self.status.setText(t("models_select_first"))
            return
        device = (
            DevicePreference.AUTO
            if index == 0
            else DevicePreference.CPU
            if index == 1
            else DevicePreference.GPU
        )
        if model.backend == "whisper":
            if device is DevicePreference.GPU and not self._gpu_runtime_available:
                self.status.setText(t("models_gpu_unavailable"))
                return
            if device is DevicePreference.CPU and not self._cpu_runtime_available:
                self.status.setText(t("models_cpu_unavailable"))
                return
        self.selected.emit(model, device)
        self.status.setText(t("models_selected"))

    def set_current_selection(self, selection: SttSelection | None) -> None:
        self._current_selection = selection
        self.refresh()
