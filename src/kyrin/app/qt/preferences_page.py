"""Interface language and login-startup controls."""

from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from kyrin.app.qt.page_layout import settings_page_layout


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
        self.dashboard_renderer_combo.addItem("GPU", "gpu")
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
        self.review_memory_button = QPushButton()
        layout.addWidget(self.review_memory_button)
        self.clear_memory_button = QPushButton()
        layout.addWidget(self.clear_memory_button)
        layout.addStretch()
