"""The saved voice preference is visible and editable in Voice Output."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from kyrin.app.qt.translations import UiTranslations  # noqa: E402
from kyrin.app.qt.tts_page import TtsPage  # noqa: E402
from kyrin.app.settings import TtsSelection  # noqa: E402


def test_voice_switch_tracks_unsaved_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    assert app is not None
    selection = TtsSelection()
    page = TtsPage(
        UiTranslations(tmp_path), selection, model_root=tmp_path, enabled=False
    )
    try:
        assert not page.voice_enabled()
        assert not page.has_unsaved_changes(selection, enabled=False)
        page.enabled_checkbox.setChecked(True)
        assert page.voice_enabled()
        assert page.has_unsaved_changes(selection, enabled=False)
    finally:
        page.close()
