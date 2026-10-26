"""Small file drop and clipboard target under the control status bar."""

from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, QUrl, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeyEvent, QKeySequence
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QWidget

from kyrin.audio.file_input import SUPPORTED_AUDIO_SUFFIXES


def local_audio_path(mime: QMimeData) -> Path | None:
    """Extract exactly one supported local file URL from a Qt MIME object."""
    urls = mime.urls()
    if not urls and mime.hasFormat("x-special/gnome-copied-files"):
        raw = mime.data("x-special/gnome-copied-files").data()
        if len(raw) > 4096:
            return None
        lines = bytes(raw).decode("utf-8", errors="replace").splitlines()
        if len(lines) == 2 and lines[0] in {"copy", "cut"}:
            urls = [QUrl(lines[1])]
    if len(urls) != 1 or not urls[0].isLocalFile():
        return None
    path = Path(urls[0].toLocalFile())
    return path if path.suffix.casefold() in SUPPORTED_AUDIO_SUFFIXES else None


class AudioDropZone(QWidget):
    file_selected = Signal(object)
    invalid_input = Signal(str)
    browse_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AudioDropZone")
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 4, 10, 4)
        self.caption = QLabel("Drop WAV, MP3, M4A or OGG here")
        self.caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(self.caption, 1)
        self.paste_button = QPushButton("Paste file")
        self.paste_button.clicked.connect(self.paste_file)
        row.addWidget(self.paste_button)
        self.browse_button = QPushButton("Choose file…")
        self.browse_button.clicked.connect(self.browse_requested.emit)
        row.addWidget(self.browse_button)

    def paste_file(self) -> None:
        path = local_audio_path(QApplication.clipboard().mimeData())
        if path is None:
            self.invalid_input.emit("Copy one local WAV, MP3, M4A, or OGG file first")
        else:
            self.file_selected.emit(path)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_file()
            event.accept()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if local_audio_path(event.mimeData()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        path = local_audio_path(event.mimeData())
        if path is None:
            event.ignore()
            self.invalid_input.emit("Drop one local WAV, MP3, M4A, or OGG file")
            return
        event.acceptProposedAction()
        self.file_selected.emit(path)
