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
        self.import_language_button = QPushButton()
        form.addRow("", self.import_language_button)
        layout.addLayout(form)
        layout.addWidget(label("language_help"))
        self.save_ui_button = QPushButton()
        layout.addWidget(self.save_ui_button)
        layout.addSpacing(24)
        self.startup_checkbox = QCheckBox()
        layout.addWidget(self.startup_checkbox)
        self.save_startup_button = QPushButton()
        layout.addWidget(self.save_startup_button)
        layout.addSpacing(24)
        layout.addWidget(label("conversation_memory_heading"))
        layout.addWidget(label("conversation_memory_caption"))
        self.review_memory_button = QPushButton()
        layout.addWidget(self.review_memory_button)
        self.clear_memory_button = QPushButton()
        layout.addWidget(self.clear_memory_button)
        layout.addStretch()
