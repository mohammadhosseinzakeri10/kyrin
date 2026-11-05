"""Select an installed local command model and its compute preference."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QWidget,
)

from kyrin.app.qt.page_layout import scrollable_page_layout
from kyrin.app.qt.translations import UiTranslations
from kyrin.app.settings import CommandModelSelection
from kyrin.commands.ollama_device import (
    CommandDeviceReport,
    InferenceState,
    ModelPresence,
)
from kyrin.commands.ollama_models import installed_ollama_models
from kyrin.stt.device import DevicePreference


class CommandModelPage(QWidget):
    """A disabled selection preserves the existing rule-based command route."""

    def __init__(
        self,
        translations: UiTranslations,
        *,
        current: CommandModelSelection | None,
        suggested_store: Path | None = None,
    ) -> None:
        super().__init__()
        self._translations = translations
        layout, self.scroll_area = scrollable_page_layout(self)
        self.title = QLabel()
        self.title.setObjectName("PageTitle")
        layout.addWidget(self.title)
        self.caption = QLabel()
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItem("", "rules")
        self.mode.addItem("", "ollama")
        self.engine_label = QLabel()
        form.addRow(self.engine_label, self.mode)
        store_row = QHBoxLayout()
        self.store_path = QLineEdit()
        self.store_path.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.store_path.setAccessibleName("Local Ollama model store")
        self.store_path.setText(
            str(current.store_path if current else suggested_store or "")
        )
        store_row.addWidget(self.store_path)
        self.browse = QPushButton()
        self.browse.clicked.connect(self._browse)
        store_row.addWidget(self.browse)
        self.store_label = QLabel()
        form.addRow(self.store_label, store_row)
        self.device = QComboBox()
        for preference in DevicePreference:
            self.device.addItem("", preference.value)
        self.device_label = QLabel()
        form.addRow(self.device_label, self.device)
        layout.addLayout(form)
        self.refresh_button = QPushButton()
        self.refresh_button.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_button)
        self.models = QListWidget()
        self.models.setMinimumHeight(240)
        self.models.setAccessibleName("Installed command understanding models")
        layout.addWidget(self.models)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.device_report: CommandDeviceReport | None = None
        self._completed_file = False
        self._device_report_empty = "command_device_not_run"
        self.observed_device = QLabel()
        self.observed_device.setWordWrap(True)
        self.observed_device.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.observed_device)
        if current is not None:
            self.mode.setCurrentIndex(1)
            self.device.setCurrentIndex(self.device.findData(current.device.value))
        self.translate()
        self.refresh()
        if current is not None:
            for index in range(self.models.count()):
                if (
                    self.models.item(index).data(Qt.ItemDataRole.UserRole)
                    == current.model
                ):
                    self.models.setCurrentRow(index)
                    break

        self.mode.currentIndexChanged.connect(self.clear_device_report)
        self.device.currentIndexChanged.connect(self.clear_device_report)
        self.store_path.textChanged.connect(self.clear_device_report)
        self.models.currentItemChanged.connect(self.clear_device_report)

    def clear_device_report(self, *_args: object) -> None:
        self.device_report = None
        self._completed_file = False
        self._device_report_empty = "command_device_not_run"
        self._show_device_report()

    def end_device_session(self) -> None:
        if self.device_report is not None:
            self.clear_device_report()
            self._device_report_empty = "command_device_session_ended"
            self._show_device_report()

    def set_device_report(
        self,
        report: CommandDeviceReport,
        store_path: Path,
        *,
        completed_file: bool = False,
    ) -> bool:
        item = self.models.currentItem()
        if (
            self.mode.currentData() != "ollama"
            or item is None
            or item.data(Qt.ItemDataRole.UserRole) != report.model
            or self.device.currentData() != report.requested.value
            or Path(self.store_path.text().strip()) != store_path
        ):
            return False
        self.device_report = report
        self._completed_file = completed_file
        self._show_device_report()
        return True

    def _show_device_report(self) -> None:
        t = self._translations.text
        report = self.device_report
        if report is None:
            text = t(self._device_report_empty)
        elif report.state is InferenceState.RUNNING:
            text = t("command_device_running")
        else:
            text = t("command_device_last").format(
                model="\u2068" + report.model + "\u2069",
                state=t("command_inference_" + report.state.value),
                placement=t(
                    "command_placement_"
                    + (
                        "not_loaded"
                        if report.observation.presence is ModelPresence.NOT_LOADED
                        else report.observation.placement.value
                    )
                ),
                presence=t("command_presence_" + report.residency.value),
                cleanup=t("command_cleanup_" + report.cleanup.value),
            )
        if report is not None and self._completed_file:
            text = t("command_device_file_ended") + "\n" + text
        self.observed_device.setText(text)

    def translate(self) -> None:
        t = self._translations.text
        self.title.setText(t("command_models_heading"))
        self.caption.setText(t("command_models_caption"))
        self.mode.setItemText(0, t("command_models_rules"))
        self.mode.setItemText(1, "Ollama")
        self.engine_label.setText(t("command_models_engine"))
        self.store_label.setText(t("command_models_store"))
        self.device_label.setText(t("command_models_device"))
        self.browse.setText(t("browse"))
        self.refresh_button.setText(t("command_models_refresh"))
        self._show_device_report()
        for index, key in enumerate(("auto", "cpu", "gpu")):
            self.device.setItemText(index, t(key))

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, self._translations.text("command_models_store_title")
        )
        if path:
            self.store_path.setText(path)
            self.refresh()

    def refresh(self) -> None:
        selected = self.models.currentItem()
        selected_name = (
            selected.data(Qt.ItemDataRole.UserRole) if selected is not None else None
        )
        self.models.clear()
        path = Path(self.store_path.text().strip())
        names = installed_ollama_models(path)
        for name in names:
            self.models.addItem(name)
            self.models.item(self.models.count() - 1).setData(
                Qt.ItemDataRole.UserRole, name
            )
        if selected_name in names:
            self.models.setCurrentRow(names.index(selected_name))
        self.status.setText(
            self._translations.text("command_models_found").format(count=len(names))
        )

    def selection(self) -> CommandModelSelection | None:
        if self.mode.currentData() == "rules":
            return None
        path = Path(self.store_path.text().strip())
        if not path.is_absolute():
            raise ValueError(self._translations.text("command_models_missing_store"))
        item = self.models.currentItem()
        name = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if not isinstance(name, str) or name not in installed_ollama_models(path):
            raise ValueError(self._translations.text("command_models_choose"))
        return CommandModelSelection(
            "ollama", name, path, DevicePreference(self.device.currentData())
        )

    def has_unsaved_changes(self, current: CommandModelSelection | None) -> bool:
        try:
            return self.selection() != current
        except ValueError:
            return True
