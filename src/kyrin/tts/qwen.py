"""Offline Qwen3-TTS CustomVoice adapter for complete local checkpoints."""

from __future__ import annotations

import json
from importlib import import_module, util
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kyrin.responses.speech import SpeechSynthesisError
from kyrin.stt.device import DevicePreference
from kyrin.tts.isolation import (
    IsolatedTtsWorker,
    isolated_runtime_python,
    probe_isolated_runtime,
)
from kyrin.tts.tempo import adjust_tempo, tempo_available

if TYPE_CHECKING:
    from kyrin.tts.models import TtsSelection
    from kyrin.tts.runtime import LocalTtsModel


QWEN_SPEAKERS = (
    "Vivian",
    "Serena",
    "Uncle_Fu",
    "Dylan",
    "Eric",
    "Ryan",
    "Aiden",
    "Ono_Anna",
    "Sohee",
)
_LANGUAGES = {
    "zh": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "ru": "Russian",
    "pt": "Portuguese",
    "es": "Spanish",
    "it": "Italian",
}


class QwenCustomVoiceAdapter:
    key = "qwen3tts"
    label = "Qwen3-TTS CustomVoice 0.6B/1.7B (local)"

    def inspect(self, folder: Path) -> LocalTtsModel | None:
        config_path = folder / "config.json"
        if not config_path.is_file() or config_path.is_symlink():
            return None
        try:
            if config_path.stat().st_size > 1024 * 1024:
                raise ValueError("Qwen TTS configuration is too large")
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid TTS model configuration") from exc
        if not isinstance(config, dict):
            raise ValueError("Invalid TTS model configuration")
        if config.get("model_type") != "qwen3_tts":
            return None
        if config.get("tts_model_type") != "custom_voice":
            raise ValueError("Only Qwen3-TTS CustomVoice packages are supported")
        from kyrin.tts.runtime import LocalTtsModel

        for name in (
            "model.safetensors",
            "generation_config.json",
            "preprocessor_config.json",
            "tokenizer_config.json",
            "merges.txt",
            "vocab.json",
            "speech_tokenizer/config.json",
            "speech_tokenizer/configuration.json",
            "speech_tokenizer/model.safetensors",
            "speech_tokenizer/preprocessor_config.json",
        ):
            path = folder / name
            if not path.is_file() or path.is_symlink():
                raise ValueError(f"Qwen3-TTS package is missing {name}")
        return LocalTtsModel(self.key, folder / "model.safetensors")

    def validate(self, selection: TtsSelection, model: LocalTtsModel) -> None:
        if int(selection.voice) >= len(QWEN_SPEAKERS):
            raise ValueError("Selected Qwen3-TTS speaker is unavailable")
        if selection.speed != 1.0 and not tempo_available():
            raise ValueError("FFmpeg is required for Qwen3-TTS speed control")
        isolated = isolated_runtime_python(self.key)
        if isolated is not None:
            probe_isolated_runtime(isolated, self.key, selection.device.value)
            return
        if util.find_spec("qwen_tts") is None:
            raise ValueError("Qwen3-TTS runtime is not installed")
        if selection.device is DevicePreference.GPU and not self._gpu_available():
            raise ValueError("Qwen3-TTS GPU runtime is unavailable")

    @staticmethod
    def _gpu_available() -> bool:
        try:
            return bool(import_module("torch").cuda.is_available())
        except ImportError:
            return False

    def provider(self, selection: TtsSelection) -> str:
        if isolated_runtime_python(self.key) is not None:
            return (
                "cpu"
                if selection.device is DevicePreference.CPU
                else ("gpu" if selection.device is DevicePreference.GPU else "auto")
            )
        if selection.device is DevicePreference.GPU:
            if not self._gpu_available():
                raise SpeechSynthesisError("Qwen3-TTS GPU runtime is unavailable")
            return "cuda:0"
        if selection.device is DevicePreference.CPU or not self._gpu_available():
            return "cpu"
        return "cuda:0"

    def load(self, model: LocalTtsModel, folder: Path, provider: str) -> Any:
        isolated = isolated_runtime_python(self.key)
        if isolated is not None:
            return IsolatedTtsWorker(isolated, self.key, folder, provider)
        torch = import_module("torch")
        qwen = import_module("qwen_tts")
        # FP16 can produce invalid sampling values on some GPU/runtime pairs.
        # BF16 is preferred where supported; FP32 is the safe older-GPU path.
        dtype = torch.float32
        if provider.startswith("cuda") and torch.cuda.is_bf16_supported():
            dtype = torch.bfloat16
        loaded = qwen.Qwen3TTSModel.from_pretrained(
            str(folder),
            device_map=provider,
            dtype=dtype,
            attn_implementation="sdpa",
            local_files_only=True,
        )
        if provider.startswith("cuda") and not str(
            getattr(loaded, "device", "")
        ).startswith("cuda"):
            raise SpeechSynthesisError("Qwen3-TTS did not load on the selected GPU")
        return loaded

    def generate(
        self, loaded: Any, text: str, voice: str, speed: float, language: str
    ) -> tuple[Any, int]:
        if isinstance(loaded, IsolatedTtsWorker):
            return loaded.generate(text, voice, speed, language)
        primary = language.split("-", maxsplit=1)[0]
        target_language = _LANGUAGES.get(primary)
        if target_language is None:
            raise SpeechSynthesisError(f"Qwen3-TTS does not support {primary}")
        wavs, sample_rate = loaded.generate_custom_voice(
            text=text, language=target_language, speaker=QWEN_SPEAKERS[int(voice)]
        )
        return adjust_tempo(wavs[0], sample_rate, speed), sample_rate
