"""Chatterbox package and offline runtime integration contracts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from kyrin.app.settings import TtsLanguageRoute, TtsSelection
from kyrin.stt.device import DevicePreference
from kyrin.tts.chatterbox import ChatterboxAdapter
from kyrin.tts.runtime import ConfiguredSpeechSynthesizer, inspect_tts_model


def _package(folder: Path) -> Path:
    folder.mkdir()
    for name in (
        "ve.pt",
        "s3gen.pt",
        "grapheme_mtl_merged_expanded_v1.json",
        "conds.pt",
        "t3_mtl23ls_v3.safetensors",
    ):
        (folder / name).write_bytes(b"fixture")
    return folder


def test_chatterbox_package_is_recognized_without_loading(tmp_path: Path) -> None:
    folder = _package(tmp_path / "voice")
    assert inspect_tts_model(folder).family == "chatterbox"
    (folder / "conds.pt").unlink()
    with pytest.raises(ValueError, match="conds.pt"):
        inspect_tts_model(folder)


def test_chatterbox_uses_local_weights_and_spoken_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kyrin.tts import chatterbox as tts_chatterbox
    from kyrin.tts import runtime as tts_runtime

    folder = _package(tmp_path / "voice")
    calls: list[object] = []

    class Waveform:
        def squeeze(self) -> Waveform:
            return self

        def detach(self) -> Waveform:
            return self

        def cpu(self) -> Waveform:
            return self

        def numpy(self) -> list[float]:
            return [0.1]

    class FakeModel:
        sr = 24000

        def get_supported_languages(self) -> dict[str, str]:
            return {"fr": "French"}

        def generate(self, text: str, *, language_id: str) -> Waveform:
            calls.append((text, language_id))
            return Waveform()

    fake_class = SimpleNamespace(
        from_local=lambda path, provider, *, t3_model: (
            calls.append((path, provider, t3_model)) or FakeModel()
        )
    )
    monkeypatch.setattr(tts_chatterbox, "isolated_runtime_python", lambda _: None)
    monkeypatch.setattr(tts_chatterbox.util, "find_spec", lambda _: object())
    monkeypatch.setattr(
        tts_chatterbox,
        "import_module",
        lambda name: SimpleNamespace(ChatterboxMultilingualTTS=fake_class),
    )
    monkeypatch.setattr(
        tts_runtime,
        "import_module",
        lambda name: SimpleNamespace(
            play=lambda samples, rate, *, blocking: calls.append((samples, rate)),
            wait=lambda: None,
        ),
    )
    selection = TtsSelection("chatterbox", folder, "0", 1.0, DevicePreference.CPU)
    ConfiguredSpeechSynthesizer(
        TtsSelection(), (TtsLanguageRoute("fr", selection),)
    ).speak("Bonjour", "fr-CA")
    assert calls == [
        (folder, "cpu", "v3"),
        ("Bonjour", "fr"),
        ([0.1], 24000),
    ]


def test_chatterbox_rejects_unsupported_speed_and_voice(tmp_path: Path) -> None:
    folder = _package(tmp_path / "voice")
    adapter = ChatterboxAdapter()
    model = inspect_tts_model(folder)
    with pytest.raises(ValueError, match="speed"):
        adapter.validate(TtsSelection("chatterbox", folder, "0", 0.75), model)
    with pytest.raises(ValueError, match="speaker 0"):
        adapter.validate(TtsSelection("chatterbox", folder, "1", 1.0), model)
