"""Clipboard and drag input accept one local audio file only."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QMimeData, QUrl

from kyrin.app.qt.audio_drop_zone import local_audio_path


def test_local_audio_mime(tmp_path: Path) -> None:
    path = tmp_path / "speech.ogg"
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    assert local_audio_path(mime) == path
    mime.setUrls([QUrl("https://example.com/speech.mp3")])
    assert local_audio_path(mime) is None


def test_gnome_file_clipboard_mime(tmp_path: Path) -> None:
    path = tmp_path / "speech.ogg"
    mime = QMimeData()
    mime.setData(
        "x-special/gnome-copied-files",
        f"copy\n{QUrl.fromLocalFile(str(path)).toString()}\n".encode(),
    )
    assert local_audio_path(mime) == path
