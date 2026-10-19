"""User control for screen permission and a local OCR package."""

from pathlib import Path
from time import monotonic

from PySide6.QtCore import QSignalBlocker, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QWidget,
)

from kyrin.app.qt.document_text_reader import DocumentObservation, DocumentTextReader
from kyrin.app.qt.ocr_setup import PADDLE_CHOICES, PADDLE_VL_CHOICE
from kyrin.app.qt.page_layout import scrollable_page_layout
from kyrin.app.qt.screen_access import ScreenAccess
from kyrin.app.qt.screen_text_reader import ScreenTextReader
from kyrin.app.qt.translations import UiTranslations
from kyrin.app.settings import OcrSelection
from kyrin.vision.ocr.backends.document import document_model_ready
from kyrin.vision.ocr.backends.paddle import paddle_model_ready
from kyrin.vision.text_reader import IdentifiedWindowText


class ScreenAccessPage(QWidget):
    def __init__(
        self,
        access: ScreenAccess | None,
        translations: UiTranslations,
        reader: ScreenTextReader | None = None,
        *,
        ocr_default_root: Path | None = None,
        ocr_candidates_root: Path | None = None,
        paddle_python: Path | None = None,
        paddle_vl_python: Path | None = None,
        document_reader: DocumentTextReader | None = None,
        document_runtimes_root: Path | None = None,
        ocr_selection: OcrSelection | None = None,
    ) -> None:
        super().__init__()
        self._access = access
        self._reader = reader
        self._document_reader = document_reader
        self._translations = translations
        self._ocr_default_root = ocr_default_root
        self._document_started_at: float | None = None
        self._document_timer = QTimer(self)
        self._document_timer.setInterval(1000)
        self._document_timer.timeout.connect(self._update_document_progress)
        layout, self.scroll_area = scrollable_page_layout(self)
        self.heading = QLabel()
        self.heading.setObjectName("PageTitle")
        layout.addWidget(self.heading)
        self.caption = QLabel()
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)
        layout.addSpacing(24)
        self.enabled_checkbox = QCheckBox()
        self.enabled_checkbox.setAccessibleName("Remember screen access")
        layout.addWidget(self.enabled_checkbox)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setObjectName("Info")
        layout.addWidget(self.status)
        layout.addSpacing(20)
        self.ocr_label = QLabel()
        layout.addWidget(self.ocr_label)
        self.ocr_backend = QComboBox()
        self.ocr_backend.addItem(
            "Tesseract · installed (CPU)", ("tesseract", ocr_default_root)
        )
        if ocr_candidates_root is not None:
            for name, label in (
                ("fast", "Tesseract Fast · English + Persian (CPU)"),
                ("best", "Tesseract Best · English + Persian (CPU)"),
            ):
                tessdata = ocr_candidates_root / "tesseract" / name
                if all(
                    (tessdata / f"{code}.traineddata").is_file()
                    for code in ("eng", "fas")
                ):
                    self.ocr_backend.addItem(label, ("tesseract", tessdata))
            if paddle_python is not None:
                for backend, label, folder in PADDLE_CHOICES:
                    model = ocr_candidates_root / "paddleocr" / folder
                    if paddle_model_ready(backend, model, paddle_python):
                        self.ocr_backend.addItem(label, (backend, model))
            if paddle_vl_python is not None:
                backend, label, folder = PADDLE_VL_CHOICE
                model = ocr_candidates_root / "paddleocr" / folder
                if paddle_model_ready(backend, model, paddle_vl_python):
                    self.ocr_backend.addItem(label, (backend, model))
        if ocr_selection is not None:
            selected_data = (ocr_selection.backend, ocr_selection.model_path)
            index = next(
                (
                    item
                    for item in range(self.ocr_backend.count())
                    if self.ocr_backend.itemData(item) == selected_data
                ),
                -1,
            )
            if index < 0:
                label = (
                    "Custom Tesseract folder"
                    if ocr_selection.backend == "tesseract"
                    else f"{ocr_selection.backend} (unavailable)"
                )
                self.ocr_backend.addItem(
                    label, (ocr_selection.backend, ocr_selection.model_path)
                )
                index = self.ocr_backend.count() - 1
            self.ocr_backend.setCurrentIndex(index)
        self.ocr_backend.setAccessibleName("OCR engine")
        layout.addWidget(self.ocr_backend)
        ocr_row = QHBoxLayout()
        self.ocr_path = QLineEdit()
        self.ocr_path.setAccessibleName("Local OCR package folder")
        self.ocr_path.setText(
            str(ocr_selection.model_path)
            if ocr_selection is not None
            else str(ocr_default_root)
            if ocr_default_root is not None
            else ""
        )
        ocr_row.addWidget(self.ocr_path)
        self.ocr_backend.currentIndexChanged.connect(self._ocr_choice_changed)
        self.ocr_browse = QPushButton()
        self.ocr_browse.clicked.connect(self._browse_ocr)
        ocr_row.addWidget(self.ocr_browse)
        layout.addLayout(ocr_row)
        self.ocr_hint = QLabel()
        self.ocr_hint.setWordWrap(True)
        layout.addWidget(self.ocr_hint)
        layout.addSpacing(16)
        self.read_button = QPushButton()
        self.read_button.clicked.connect(self._read)
        layout.addWidget(self.read_button)
        self.read_status = QLabel()
        self.read_status.setWordWrap(True)
        self.read_status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.read_status)
        self.read_output = QPlainTextEdit()
        self.read_output.setMinimumHeight(180)
        self.read_output.setReadOnly(True)
        self.read_output.setMaximumBlockCount(40)
        layout.addWidget(self.read_output)
        self.clear_read_button = QPushButton()
        self.clear_read_button.clicked.connect(self._clear_read_output)
        layout.addWidget(self.clear_read_button)
        layout.addSpacing(20)
        self.document_heading = QLabel()
        layout.addWidget(self.document_heading)
        self.document_hint = QLabel()
        self.document_hint.setWordWrap(True)
        layout.addWidget(self.document_hint)
        self.document_backend = QComboBox()
        self.document_backend.setAccessibleName("Document OCR model")
        if ocr_candidates_root is not None and document_runtimes_root is not None:
            for backend, label in (
                ("surya", "Surya OCR 2"),
                ("glm", "GLM-OCR"),
                ("dots", "dots.mocr"),
            ):
                if document_model_ready(
                    backend, ocr_candidates_root, document_runtimes_root
                ):
                    self.document_backend.addItem(label, backend)
        layout.addWidget(self.document_backend)
        self.document_button = QPushButton()
        self.document_button.clicked.connect(self._read_document)
        layout.addWidget(self.document_button)
        self.document_status = QLabel()
        self.document_status.setWordWrap(True)
        self.document_status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.document_status)
        self.document_output = QPlainTextEdit()
        self.document_output.setReadOnly(True)
        self.document_output.setMinimumHeight(180)
        self.document_output.setMaximumBlockCount(100)
        layout.addWidget(self.document_output)
        self.clear_document_button = QPushButton()
        self.clear_document_button.clicked.connect(self._clear_document_output)
        layout.addWidget(self.clear_document_button)
        layout.addStretch()
        self.enabled_checkbox.toggled.connect(self._toggled)
        if access is not None:
            access.changed.connect(self._changed)
            access.error.connect(self._error)
        if reader is not None:
            reader.completed.connect(self._read_completed)
            reader.failed.connect(self._read_failed)
            reader.busy_changed.connect(self._read_busy_changed)
        if document_reader is not None:
            document_reader.completed.connect(self._document_completed)
            document_reader.failed.connect(self._document_failed)
            document_reader.busy_changed.connect(self._document_busy_changed)
        self.translate()
        self.enabled_checkbox.setEnabled(access is not None and access.available)
        self._changed(access.granted if access is not None else False)
        if access is not None and access.available and access.remembered:
            QTimer.singleShot(
                0, lambda: access.request_session() if access.remembered else None
            )

    def translate(self) -> None:
        text = self._translations.text
        self.heading.setText(text("screen_heading"))
        self.caption.setText(text("screen_caption"))
        self.enabled_checkbox.setText(text("screen_enable"))
        self.ocr_label.setText(text("screen_ocr_model"))
        self.ocr_browse.setText(text("screen_ocr_browse"))
        self.ocr_hint.setText(text("screen_ocr_hint"))
        self.read_button.setText(text("screen_read"))
        self.clear_read_button.setText(text("screen_read_clear"))
        self.document_heading.setText(text("screen_document_heading"))
        self.document_hint.setText(text("screen_document_hint"))
        self.document_button.setText(text("screen_document_read"))
        self.clear_document_button.setText(text("screen_document_clear"))
        if not self.document_output.toPlainText():
            self.document_status.setText(text("screen_document_ready"))
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

    def _browse_ocr(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, self._translations.text("screen_ocr_browse")
        )
        if directory:
            self.ocr_path.setText(directory)

    def _ocr_choice_changed(self, _index: int) -> None:
        _, path = self.ocr_backend.currentData()
        self.ocr_path.setText(str(path) if path is not None else "")

    def selection(self) -> OcrSelection | None:
        path = self.ocr_path.text().strip()
        if not path:
            return None
        selected = Path(path)
        backend, _ = self.ocr_backend.currentData()
        if (
            backend == "tesseract"
            and self._ocr_default_root is not None
            and selected == self._ocr_default_root
        ):
            return None
        return OcrSelection(backend, selected)

    def has_unsaved_changes(self, current: OcrSelection | None) -> bool:
        return self.selection() != current

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
        self._update_document_button()
        if not granted:
            self.read_output.clear()
            self.document_output.clear()
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

    def _clear_read_output(self) -> None:
        self.read_output.clear()
        self.read_status.setText(self._translations.text("screen_read_hint"))

    def _clear_document_output(self) -> None:
        self.document_output.clear()
        self.document_status.setText(self._translations.text("screen_document_ready"))

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
        self.clear_read_button.setEnabled(not _busy)

    def _read_document(self) -> None:
        reader = self._document_reader
        backend = self.document_backend.currentData()
        if reader is None or not isinstance(backend, str):
            return
        self.document_output.clear()
        self.document_status.setText(self._translations.text("screen_document_reading"))
        reader.read(backend)

    def _document_completed(self, observation: object) -> None:
        if not isinstance(observation, DocumentObservation):
            self._document_failed("ocr_failed")
            return
        if not observation.text.strip():
            self.document_status.setText(
                self._translations.text("screen_document_no_text").format(
                    backend=observation.backend,
                    app_id=observation.app_id,
                )
            )
            return
        self.document_output.setPlainText(observation.text[:8000])
        self.document_status.setText(
            self._translations.text("screen_document_result").format(
                backend=observation.backend,
                app_id=observation.app_id,
            )
        )

    def _document_failed(self, reason: str) -> None:
        self.document_output.clear()
        key = {
            "access_off": "screen_off",
            "ocr_unavailable": "screen_ocr_unavailable",
            "capture_unavailable": "screen_capture_unavailable",
            "window_changed": "screen_window_changed",
            "ocr_timeout": "screen_document_timeout",
        }.get(reason, "screen_ocr_failed")
        self.document_status.setText(self._translations.text(key))

    def _document_busy_changed(self, busy: bool) -> None:
        self._update_document_button()
        self.document_backend.setEnabled(not busy)
        self.clear_document_button.setEnabled(not busy)
        if busy:
            self._document_started_at = monotonic()
            self._document_timer.start()
            self._update_document_progress()
        else:
            self._document_timer.stop()
            self._document_started_at = None

    def _update_document_progress(self) -> None:
        if self._document_started_at is None:
            return
        backend = self.document_backend.currentData()
        self.document_status.setText(
            self._translations.text("screen_document_progress").format(
                backend=backend if isinstance(backend, str) else "OCR",
                seconds=int(monotonic() - self._document_started_at),
            )
        )

    def _update_document_button(self) -> None:
        self.document_button.setEnabled(
            self._access is not None
            and self._access.granted
            and self._document_reader is not None
            and not self._document_reader.busy
            and self.document_backend.count() > 0
        )

    def _update_read_button(self) -> None:
        reader = self._reader
        self.read_button.setEnabled(
            self._access is not None
            and self._access.granted
            and reader is not None
            and reader.available
            and not reader.busy
        )
