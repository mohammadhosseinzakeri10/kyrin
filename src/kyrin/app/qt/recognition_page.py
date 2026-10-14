"""Speech-recognition settings and in-memory command diagnostics."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QWidget,
)

from kyrin.app.qt.page_layout import settings_page_layout
from kyrin.stt.device import DevicePreference


class RecognitionPage(QWidget):
    def __init__(self, label: Callable[[str], QLabel]) -> None:
        super().__init__()
        layout = settings_page_layout(
            self, label, "recognition_heading", "recognition_caption"
        )
        form = QFormLayout()
        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Vosk", "vosk")
        self.backend_combo.addItem("Whisper", "whisper")
        self.backend_combo.setAccessibleName("Speech recognition engine")
        form.addRow(label("backend"), self.backend_combo)

        model_row = QHBoxLayout()
        self.model_path = QLineEdit()
        self.model_path.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.model_path.setAccessibleName("Speech model path")
        model_row.addWidget(self.model_path)
        self.browse_button = QPushButton()
        model_row.addWidget(self.browse_button)
        form.addRow(label("model"), model_row)

        self.language_edit = QLineEdit("en")
        self.language_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.language_edit.setAccessibleName("Speech language code")
        form.addRow(label("speech_language"), self.language_edit)
        self.wake_aliases_edit = QLineEdit()
        self.wake_aliases_edit.setAccessibleName("KYRIN wake word alternatives")
        form.addRow(label("wake_aliases"), self.wake_aliases_edit)
        self.device_combo = QComboBox()
        self.device_combo.addItem("", DevicePreference.AUTO.value)
        self.device_combo.addItem("", DevicePreference.CPU.value)
        self.device_combo.addItem("", DevicePreference.GPU.value)
        self.device_combo.setAccessibleName("Speech processing device")
        form.addRow(label("device"), self.device_combo)
        layout.addLayout(form)
        speech_language_help = label("speech_language_help")
        speech_language_help.setWordWrap(True)
        layout.addWidget(speech_language_help)
        self.active_device_label = QLabel()
        self.active_device_label.setTextFormat(Qt.TextFormat.PlainText)
        self.active_device_label.setObjectName("Info")
        layout.addWidget(self.active_device_label)
        self.action_label = QLabel()
        self.action_label.setTextFormat(Qt.TextFormat.PlainText)
        self.action_label.setObjectName("Info")
        layout.addWidget(self.action_label)
        self.diagnostics_heading = QLabel()
        self.diagnostics_heading.setObjectName("Info")
        layout.addWidget(self.diagnostics_heading)
        self.diagnostics_output = QPlainTextEdit()
        self.diagnostics_output.setMinimumHeight(180)
        self.diagnostics_output.setReadOnly(True)
        self.diagnostics_output.setMaximumBlockCount(40)
        self.diagnostics_output.setAccessibleName("Speech command diagnostics")
        layout.addWidget(self.diagnostics_output)
        self.clear_diagnostics_button = QPushButton()
        self.clear_diagnostics_button.clicked.connect(self.diagnostics_output.clear)
        layout.addWidget(self.clear_diagnostics_button)
        layout.addStretch()
