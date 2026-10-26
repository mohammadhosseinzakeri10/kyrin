"""Microphone selection page; audio acquisition remains outside Qt."""

from collections.abc import Callable

from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QWidget

from kyrin.app.qt.page_layout import settings_page_layout


class AudioPage(QWidget):
    def __init__(self, label: Callable[[str], QLabel]) -> None:
        super().__init__()
        layout = settings_page_layout(self, label, "audio_heading", "audio_caption")
        form = QFormLayout()
        self.microphone_combo = QComboBox()
        self.microphone_combo.setAccessibleName("Input microphone")
        form.addRow(label("microphone"), self.microphone_combo)
        layout.addLayout(form)
        layout.addStretch()
