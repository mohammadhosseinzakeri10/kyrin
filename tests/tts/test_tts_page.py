"""The TTS settings page discovers local packages without importing them."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

from kyrin.app.qt.translations import UiTranslations  # noqa: E402
from kyrin.app.qt.tts_page import TtsPage, _VoiceEditor  # noqa: E402
from kyrin.app.settings import TtsSelection  # noqa: E402


def test_local_models_are_listed_and_selected_without_copying(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "tts"
    root.mkdir()
    complete = root / "kitten-en"
    complete.mkdir()
    for name in ("model.int8.onnx", "voices.bin", "tokens.txt"):
        (complete / name).write_bytes(b"fixture")
    (complete / "espeak-ng-data").mkdir()
    incomplete = root / "broken"
    incomplete.mkdir()

    page = TtsPage(UiTranslations(tmp_path), TtsSelection(), model_root=root)
    assert page.engine.currentData() == "speech-dispatcher"
    assert page._editors["en"].browse.isEnabled()
    assert page.installed.isEnabled()
    assert page._editors["en"].refresh.text() == "Refresh"
    assert page._editors["en"].browse.text() == "Browse…"
    assert page._editors["en"].refresh.minimumWidth() >= 112
    assert page._editors["en"].browse.minimumWidth() >= 112
    assert page._editors["en"].refresh.height() == 38
    assert page._editors["en"].browse.height() == 38
    page.refresh_installed()
    assert page.installed.count() == 2
    page.installed.setCurrentIndex(1)
    assert page.model_path.text() == str(complete)
    assert page.engine.currentData() == "kitten"
    assert page.has_unsaved_changes(TtsSelection())
    assert incomplete.is_dir()
    page.close()
    assert app is not None


def test_refresh_and_browse_buttons_update_local_model_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "tts"
    root.mkdir()
    page = TtsPage(UiTranslations(tmp_path), TtsSelection(), model_root=root)
    assert page.installed.count() == 1
    folder = root / "kitten-en"
    kitten_files = ("model.int8.onnx", "voices.bin", "tokens.txt")
    folder.mkdir()
    for name in kitten_files:
        (folder / name).write_bytes(b"fixture")
    (folder / "espeak-ng-data").mkdir()
    page._editors["en"].refresh.click()
    assert page.installed.count() == 2
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(folder),
    )
    page._editors["en"].browse.click()
    assert page.model_path.text() == str(folder)
    assert page.engine.currentData() == "kitten"
    page.close()
    assert app is not None


def test_family_folder_lists_each_kokoro_model_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "tts"
    family = root / "kokoro"
    for name in ("kokoro-multi-lang-v1_0", "kokoro-multi-lang-v1_1"):
        folder = family / name
        folder.mkdir(parents=True)
        for filename in ("model.onnx", "voices.bin", "tokens.txt", "lexicon-us-en.txt"):
            (folder / filename).write_bytes(b"fixture")
        (folder / "espeak-ng-data").mkdir()

    page = TtsPage(UiTranslations(tmp_path), TtsSelection(), model_root=root)
    assert page.installed.count() == 3
    assert "kokoro/kokoro-multi-lang-v1_0" in page.installed.itemText(1)
    assert "kokoro/kokoro-multi-lang-v1_1" in page.installed.itemText(2)
    page.installed.setCurrentIndex(1)
    assert page.model_path.text() == str(family / "kokoro-multi-lang-v1_0")
    assert page.engine.currentData() == "kokoro"
    page.close()
    assert app is not None


def test_kokoro_voice_names_keep_their_speaker_ids_when_switching_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "tts"
    family = root / "kokoro"
    for name in ("kokoro-multi-lang-v1_0", "kokoro-multi-lang-v1_1"):
        folder = family / name
        folder.mkdir(parents=True)
        for filename in ("model.onnx", "voices.bin", "tokens.txt", "lexicon-us-en.txt"):
            (folder / filename).write_bytes(b"fixture")
        (folder / "espeak-ng-data").mkdir()

    first = family / "kokoro-multi-lang-v1_0"
    page = TtsPage(
        UiTranslations(tmp_path),
        TtsSelection(backend="kokoro", model_path=first, voice="20"),
        model_root=root,
    )
    editor = page._editors["en"]
    assert editor.voice_number.isHidden()
    assert not editor.voice.isHidden()
    assert editor.voice.currentData() == "20"
    assert "bf_alice" in editor.voice.currentText()
    editor.voice.setCurrentIndex(editor.voice.findData("3"))
    assert editor.draft().voice == "3"
    assert "af_heart" in editor.voice.currentText()

    second = family / "kokoro-multi-lang-v1_1"
    editor.installed.setCurrentIndex(editor.installed.findData(str(second)))
    assert editor.voice.count() == 3
    assert "af_maple" in editor.voice.itemText(0)
    assert editor.draft().voice == "0"
    page.close()
    assert app is not None


def test_unknown_kokoro_package_keeps_numeric_speaker_control(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    folder = tmp_path / "kokoro-custom"
    folder.mkdir()
    for filename in ("model.onnx", "voices.bin", "tokens.txt", "lexicon-us-en.txt"):
        (folder / filename).write_bytes(b"fixture")
    (folder / "espeak-ng-data").mkdir()
    page = TtsPage(
        UiTranslations(tmp_path),
        TtsSelection(backend="kokoro", model_path=folder, voice="7"),
        model_root=tmp_path,
    )
    editor = page._editors["en"]
    assert editor.voice.isHidden()
    assert not editor.voice_number.isHidden()
    assert editor.draft().voice == "7"
    page.close()
    assert app is not None


def test_language_voice_can_be_added_without_changing_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    page = TtsPage(UiTranslations(tmp_path), TtsSelection(), model_root=tmp_path)
    page.add_language("fa")
    assert page.tabs.count() == 2
    assert page.selection() == TtsSelection()
    assert page.language_routes()[0].language == "fa"
    assert page.has_unsaved_changes(TtsSelection())
    page.close()
    assert app is not None


def test_persian_piper_package_appears_in_language_tab(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    folder = tmp_path / "vits-piper-fa_IR-gyro-medium"
    folder.mkdir()
    (folder / "fa_IR-gyro-medium.onnx").write_bytes(b"fixture")
    (folder / "tokens.txt").write_bytes(b"fixture")
    (folder / "espeak-ng-data").mkdir()
    page = TtsPage(UiTranslations(tmp_path), TtsSelection(), model_root=tmp_path)
    page.add_language("fa")
    editor = page.tabs.currentWidget()
    assert isinstance(editor, _VoiceEditor)
    editor.engine.setCurrentIndex(editor.engine.findData("vits"))
    assert editor.installed.count() == 2
    editor.installed.setCurrentIndex(1)
    assert editor.model_path.text() == str(folder)
    page.close()
    assert app is not None


def test_selecting_local_model_detects_engine_without_manual_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    folder = tmp_path / "kokoro-multi-lang-v1_1"
    folder.mkdir()
    for name in ("model.onnx", "tokens.txt", "voices.bin", "lexicon-us-en.txt"):
        (folder / name).write_bytes(b"fixture")
    (folder / "espeak-ng-data").mkdir()
    page = TtsPage(UiTranslations(tmp_path), TtsSelection(), model_root=tmp_path)
    page.installed.setCurrentIndex(1)
    assert page.engine.currentData() == "kokoro"
    assert page.model_path.text() == str(folder)
    page.close()
    assert app is not None


def test_chatterbox_folder_sets_supported_voice_controls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    folder = tmp_path / "chatterbox-multilingual"
    folder.mkdir()
    for name in (
        "ve.pt",
        "s3gen.pt",
        "grapheme_mtl_merged_expanded_v1.json",
        "conds.pt",
        "t3_mtl23ls_v3.safetensors",
    ):
        (folder / name).write_bytes(b"fixture")
    page = TtsPage(UiTranslations(tmp_path), TtsSelection(), model_root=tmp_path)
    page.installed.setCurrentIndex(1)
    assert page.engine.currentData() == "chatterbox"
    assert page._editors["en"].draft().speed == 1.0
    assert page._editors["en"].draft().voice == "0"
    assert not page.speed.isEnabled()
    page.close()
    assert app is not None


def test_qwen_speed_control_uses_available_tempo_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kyrin.app.qt import tts_page

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setattr(tts_page, "tempo_available", lambda: True)
    app = QApplication.instance() or QApplication([])
    page = TtsPage(UiTranslations(tmp_path), TtsSelection(), model_root=tmp_path)
    page.engine.setCurrentIndex(page.engine.findData("qwen3tts"))
    page.model_path.setText(str(tmp_path))
    assert page.speed.isEnabled()
    page.speed.setValue(1.25)
    assert page._editors["en"].draft().speed == 1.25
    page.close()
    assert app is not None


def test_preview_uses_current_speed_without_saving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    saved = TtsSelection()
    requests: list[tuple[str, str, TtsSelection]] = []

    def preview(text: str, language: str, selection: TtsSelection) -> bool:
        requests.append((text, language, selection))
        return True

    page = TtsPage(
        UiTranslations(tmp_path),
        saved,
        model_root=tmp_path,
        preview=preview,
    )
    page.speed.setValue(1.3)
    page.preview_button.click()
    assert requests[0][0:2] == ("Hello. This is KYRIN.", "en")
    assert requests[0][2].speed == 1.3
    assert saved.speed == 0.75
    page.close()
    assert app is not None
