"""Interface language and login-startup controls."""

from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QWidget,
)

from kyrin.app.qt.page_layout import settings_page_layout
from kyrin.app.settings import AppSettings
from kyrin.memory.history import HistoryRetention


class PreferencesPage(QWidget):
    def __init__(self, label: Callable[[str], QLabel]) -> None:
        super().__init__()
        layout = settings_page_layout(
            self, label, "preferences_heading", "preferences_caption"
        )
        form = QFormLayout()
        self.ui_language_combo = QComboBox()
        form.addRow(label("interface_language"), self.ui_language_combo)
        self.dashboard_animation_checkbox = QCheckBox()
        form.addRow(label("dashboard_animation"), self.dashboard_animation_checkbox)
        self.dashboard_renderer_combo = QComboBox()
        self.dashboard_renderer_combo.addItem("CPU", "cpu")
        self.dashboard_renderer_combo.addItem("GPU Light", "gpu")
        self.dashboard_renderer_combo.addItem("GPU Medium", "gpu_medium")
        self.dashboard_renderer_combo.addItem("GPU Heavy", "gpu_heavy")
        form.addRow(label("dashboard_renderer"), self.dashboard_renderer_combo)
        self.import_language_button = QPushButton()
        form.addRow("", self.import_language_button)
        layout.addLayout(form)
        language_help = label("language_help")
        language_help.setWordWrap(True)
        layout.addWidget(language_help)
        self.save_ui_button = QPushButton()
        layout.addWidget(self.save_ui_button)
        layout.addSpacing(24)
        self.startup_checkbox = QCheckBox()
        layout.addWidget(self.startup_checkbox)
        self.save_startup_button = QPushButton()
        layout.addWidget(self.save_startup_button)
        layout.addSpacing(24)
        layout.addWidget(label("conversation_memory_heading"))
        memory_caption = label("conversation_memory_caption")
        memory_caption.setWordWrap(True)
        layout.addWidget(memory_caption)
        self.history_enabled_checkbox = QCheckBox()
        layout.addWidget(self.history_enabled_checkbox)
        retention_form = QFormLayout()
        self.retention_fields: dict[str, QSpinBox] = {}
        for field in (
            "active_max_turns",
            "active_max_age_days",
            "archived_max_turns",
            "archived_max_age_days",
        ):
            spin = QSpinBox()
            spin.setRange(0, 365000 if field.endswith("days") else 2147483647)
            self.retention_fields[field] = spin
            retention_form.addRow(label(f"history_{field}"), spin)
        layout.addLayout(retention_form)
        retention_help = label("history_retention_help")
        retention_help.setWordWrap(True)
        layout.addWidget(retention_help)
        self.review_memory_button = QPushButton()
        layout.addWidget(self.review_memory_button)
        self.archive_memory_button = QPushButton()
        layout.addWidget(self.archive_memory_button)
        self.clear_memory_button = QPushButton()
        layout.addWidget(self.clear_memory_button)
        self.clear_all_memory_button = QPushButton()
        layout.addWidget(self.clear_all_memory_button)
        layout.addStretch()

    def load_history(self, settings: AppSettings) -> None:
        self.history_enabled_checkbox.setChecked(settings.history_enabled)
        for field, spin in self.retention_fields.items():
            spin.setValue(getattr(settings.history_retention, field) or 0)

    def history_retention(self) -> HistoryRetention:
        return HistoryRetention(
            **{
                field: spin.value() or None
                for field, spin in self.retention_fields.items()
            }
        )
