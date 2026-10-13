"""Qwen3-TTS CustomVoice is loaded from a complete local folder only."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kyrin.app.settings import TtsLanguageRoute, TtsSelection
from kyrin.responses.speech import SpeechSynthesisError
from kyrin.stt.device import DevicePreference
from kyrin.tts.qwen import QwenCustomVoiceAdapter
from kyrin.tts.runtime import ConfiguredSpeechSynthesizer, inspect_tts_model


def _package(folder: Path) -> Path:
    folder.mkdir()
    (folder / "config.json").write_text(
        json.dumps({"model_type": "qwen3_tts", "tts_model_type": "custom_voice"}),
        encoding="utf-8",
    )
    for name in (
        "model.safetensors",
        "generation_config.json",
        "preprocessor_config.json",
        "tokenizer_config.json",
        "merges.txt",
        "vocab.json",
    ):
        (folder / name).write_bytes(b"fixture")
    (folder / "speech_tokenizer").mkdir()
    for name in (
        "config.json",
        "configuration.json",
        "model.safetensors",
        "preprocessor_config.json",
    ):
        (folder / "speech_tokenizer" / name).write_bytes(b"fixture")
    return folder


def test_qwen_package_requires_complete_local_files(tmp_path: Path) -> None:
    folder = _package(tmp_path / "qwen")
    assert inspect_tts_model(folder).family == "qwen3tts"
    (folder / "speech_tokenizer" / "config.json").unlink()
    with pytest.raises(ValueError, match="speech_tokenizer/config.json"):
        inspect_tts_model(folder)


def test_qwen_rejects_base_checkpoint_without_custom_voice(tmp_path: Path) -> None:
    folder = _package(tmp_path / "qwen")
    (folder / "config.json").write_text(
        json.dumps({"model_type": "qwen3_tts", "tts_model_type": "base"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="CustomVoice"):
        inspect_tts_model(folder)


def test_qwen_rejects_incomplete_or_invalid_package(tmp_path: Path) -> None:
    folder = _package(tmp_path / "qwen")
    (folder / "speech_tokenizer" / "model.safetensors").unlink()
    with pytest.raises(ValueError, match="speech_tokenizer/model.safetensors"):
        inspect_tts_model(folder)
    (folder / "config.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="configuration"):
        inspect_tts_model(folder)


def test_qwen_uses_offline_loading_and_selected_speaker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kyrin.tts import qwen as tts_qwen
    from kyrin.tts import runtime as tts_runtime

    folder = _package(tmp_path / "qwen")
    calls: list[object] = []

    class FakeModel:
        def generate_custom_voice(
            self, **kwargs: object
        ) -> tuple[list[list[float]], int]:
            calls.append(kwargs)
            return [[0.1]], 24000

    fake_qwen = SimpleNamespace(
        Qwen3TTSModel=SimpleNamespace(
            from_pretrained=lambda path, **kwargs: (
                calls.append((path, kwargs)) or FakeModel()
            )
        )
    )
    fake_torch = SimpleNamespace(float32="float32", float16="float16")
    monkeypatch.setattr(tts_qwen, "isolated_runtime_python", lambda _: None)
    monkeypatch.setattr(tts_qwen.util, "find_spec", lambda _: object())
    monkeypatch.setattr(
        tts_qwen,
        "import_module",
        lambda name: fake_torch if name == "torch" else fake_qwen,
    )
    monkeypatch.setattr(
        tts_runtime,
        "import_module",
        lambda _: SimpleNamespace(play=lambda *args, **kwargs: calls.append("played")),
    )
    choice = TtsSelection("qwen3tts", folder, "5", 1.0, DevicePreference.CPU)
    ConfiguredSpeechSynthesizer(
        TtsSelection(), (TtsLanguageRoute("de", choice),)
    ).speak("Guten Tag", "de-DE")
    assert calls[0] == (
        str(folder),
        {
            "device_map": "cpu",
            "dtype": "float32",
            "attn_implementation": "sdpa",
            "local_files_only": True,
        },
    )
    assert calls[1] == {"text": "Guten Tag", "language": "German", "speaker": "Ryan"}
    assert calls[2] == "played"


def test_qwen_requires_tempo_tool_for_speed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kyrin.tts import qwen as tts_qwen

    folder = _package(tmp_path / "qwen")
    adapter = QwenCustomVoiceAdapter()
    model = inspect_tts_model(folder)
    monkeypatch.setattr(tts_qwen, "tempo_available", lambda: False)
    with pytest.raises(ValueError, match="FFmpeg"):
        adapter.validate(TtsSelection("qwen3tts", folder, "0", 0.75), model)
    with pytest.raises(ValueError, match="speaker"):
        adapter.validate(TtsSelection("qwen3tts", folder, "9", 1.0), model)


def test_qwen_gpu_load_rejects_silent_cpu_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kyrin.tts import qwen as tts_qwen

    folder = _package(tmp_path / "qwen")
    monkeypatch.setattr(tts_qwen, "isolated_runtime_python", lambda _: None)
    monkeypatch.setattr(
        tts_qwen,
        "import_module",
        lambda name: (
            SimpleNamespace(
                float32="float32",
                bfloat16="bfloat16",
                cuda=SimpleNamespace(is_bf16_supported=lambda: True),
            )
            if name == "torch"
            else SimpleNamespace(
                Qwen3TTSModel=SimpleNamespace(
                    from_pretrained=lambda *args, **kwargs: SimpleNamespace(
                        device="cpu"
                    )
                )
            )
        ),
    )
    with pytest.raises(SpeechSynthesisError, match="did not load"):
        QwenCustomVoiceAdapter().load(inspect_tts_model(folder), folder, "cuda:0")


def test_qwen_gpu_uses_bf16_when_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kyrin.tts import qwen as tts_qwen

    folder = _package(tmp_path / "qwen")
    captured: dict[str, object] = {}

    def fake_load(path: str, **kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(device="cuda:0")

    fake_torch = SimpleNamespace(
        float32="float32",
        bfloat16="bfloat16",
        cuda=SimpleNamespace(is_bf16_supported=lambda: True),
    )
    monkeypatch.setattr(tts_qwen, "isolated_runtime_python", lambda _: None)
    monkeypatch.setattr(
        tts_qwen,
        "import_module",
        lambda name: (
            fake_torch
            if name == "torch"
            else SimpleNamespace(
                Qwen3TTSModel=SimpleNamespace(from_pretrained=fake_load)
            )
        ),
    )
    QwenCustomVoiceAdapter().load(inspect_tts_model(folder), folder, "cuda:0")
    assert captured["device_map"] == "cuda:0"
    assert captured["dtype"] == "bfloat16"


def test_qwen_gpu_uses_fp32_without_bf16(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kyrin.tts import qwen as tts_qwen

    folder = _package(tmp_path / "qwen")
    captured: dict[str, object] = {}

    def fake_load(path: str, **kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(device="cuda:0")

    fake_torch = SimpleNamespace(
        float32="float32",
        cuda=SimpleNamespace(is_bf16_supported=lambda: False),
    )
    monkeypatch.setattr(tts_qwen, "isolated_runtime_python", lambda _: None)
    monkeypatch.setattr(
        tts_qwen,
        "import_module",
        lambda name: (
            fake_torch
            if name == "torch"
            else SimpleNamespace(
                Qwen3TTSModel=SimpleNamespace(from_pretrained=fake_load)
            )
        ),
    )
    QwenCustomVoiceAdapter().load(inspect_tts_model(folder), folder, "cuda:0")
    assert captured["dtype"] == "float32"
