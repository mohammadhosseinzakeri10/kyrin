"""Session-only GNOME screen permission control."""

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from kyrin.app.qt.screen_access import ScreenAccess
from kyrin.app.qt.screen_text_reader import ScreenTextReader
from kyrin.app.qt.translations import UiTranslations
from kyrin.vision.text_reader import IdentifiedWindowText


class ScreenAccessPage(QWidget):
    def __init__(
        self,
        access: ScreenAccess | None,
        translations: UiTranslations,
        reader: ScreenTextReader | None = None,
    ) -> None:
        super().__init__()
        self._access = access
        self._reader = reader
        self._translations = translations
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 25, 20, 20)
        self.heading = QLabel()
        self.heading.setObjectName("PageTitle")
        layout.addWidget(self.heading)
        self.caption = QLabel()
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)
        layout.addSpacing(24)
        self.enabled_checkbox = QCheckBox()
        self.enabled_checkbox.setAccessibleName("Screen access for this session")
        layout.addWidget(self.enabled_checkbox)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setObjectName("Info")
        layout.addWidget(self.status)
        layout.addSpacing(20)
        self.read_button = QPushButton()
        self.read_button.clicked.connect(self._read)
        layout.addWidget(self.read_button)
        self.read_status = QLabel()
        self.read_status.setWordWrap(True)
        self.read_status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.read_status)
        self.read_output = QPlainTextEdit()
        self.read_output.setReadOnly(True)
        self.read_output.setMaximumBlockCount(40)
        layout.addWidget(self.read_output)
        layout.addStretch()
        self.enabled_checkbox.toggled.connect(self._toggled)
        if access is not None:
            access.changed.connect(self._changed)
            access.error.connect(self._error)
        if reader is not None:
            reader.completed.connect(self._read_completed)
            reader.failed.connect(self._read_failed)
            reader.busy_changed.connect(self._read_busy_changed)
        self.translate()
        self.enabled_checkbox.setEnabled(access is not None and access.available)
        self._changed(access.granted if access is not None else False)

    def translate(self) -> None:
        text = self._translations.text
        self.heading.setText(text("screen_heading"))
        self.caption.setText(text("screen_caption"))
        self.enabled_checkbox.setText(text("screen_enable"))
        self.read_button.setText(text("screen_read"))
        if self._reader is None or not self._reader.available:
            self.read_status.setText(text("screen_ocr_unavailable"))
        elif not self.read_output.toPlainText():
            self.read_status.setText(text("screen_read_hint"))
        if self._access is None or not self._access.available:
            self.status.setText(text("screen_unavailable"))
        elif self._access.granted:
            self.status.setText(text("screen_active"))
        else:
            self.status.setText(text("screen_off"))

    def _toggled(self, enabled: bool) -> None:
        access = self._access
        if access is None:
            return
        if enabled:
            self.enabled_checkbox.setEnabled(False)
            self.status.setText(self._translations.text("screen_waiting"))
            access.request_session()
        else:
            access.revoke()

    def _changed(self, granted: bool) -> None:
        with QSignalBlocker(self.enabled_checkbox):
            self.enabled_checkbox.setChecked(granted)
        self.enabled_checkbox.setEnabled(
            self._access is not None and self._access.available
        )
        self.status.setText(
            self._translations.text("screen_active" if granted else "screen_off")
            if self._access is not None and self._access.available
            else self._translations.text("screen_unavailable")
        )
        self._update_read_button()
        if not granted:
            self.read_output.clear()
            if self._reader is not None and self._reader.available:
                self.read_status.setText(self._translations.text("screen_off"))

    def _error(self, message: str) -> None:
        self._changed(False)
        self.status.setText(message)

    def _read(self) -> None:
        reader = self._reader
        if reader is None:
            return
        self.read_output.clear()
        self.read_status.setText(self._translations.text("screen_reading"))
        reader.read()

    def _read_completed(self, observation: object) -> None:
        if not isinstance(observation, IdentifiedWindowText):
            self._read_failed("ocr_failed")
            return
        text = " ".join(span.text for span in observation.result.spans)
        if not text:
            self.read_status.setText(self._translations.text("screen_no_text"))
            return
        self.read_output.setPlainText(text[:2000])
        status_key = (
            "screen_read_truncated" if len(text) > 2000 else "screen_read_result"
        )
        self.read_status.setText(
            self._translations.text(status_key).format(
                app_id=observation.platform_app_id,
                pid=observation.process_id,
            )
        )

    def _read_failed(self, reason: str) -> None:
        self.read_output.clear()
        key = {
            "access_off": "screen_off",
            "ocr_unavailable": "screen_ocr_unavailable",
            "capture_unavailable": "screen_capture_unavailable",
            "window_changed": "screen_window_changed",
            "ocr_failed": "screen_ocr_failed",
        }.get(reason, "screen_ocr_failed")
        self.read_status.setText(self._translations.text(key))

    def _read_busy_changed(self, _busy: bool) -> None:
        self._update_read_button()

    def _update_read_button(self) -> None:
        reader = self._reader
        self.read_button.setEnabled(
            self._access is not None
            and self._access.granted
            and reader is not None
            and reader.available
            and not reader.busy
        )
