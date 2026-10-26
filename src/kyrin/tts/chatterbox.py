"""Offline adapter for complete Chatterbox Multilingual V2/V3 packages."""

from __future__ import annotations

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

if TYPE_CHECKING:
    from kyrin.tts.models import TtsSelection
    from kyrin.tts.runtime import LocalTtsModel


class ChatterboxAdapter:
    key = "chatterbox"
    label = "Chatterbox Multilingual V2/V3 (local)"

    def inspect(self, folder: Path) -> LocalTtsModel | None:
        if not (folder / "ve.pt").exists() or not (folder / "s3gen.pt").exists():
            return None
        from kyrin.tts.runtime import LocalTtsModel

        required = (
            "ve.pt",
            "s3gen.pt",
            "grapheme_mtl_merged_expanded_v1.json",
            "conds.pt",
        )
        for name in required:
            path = folder / name
            if not path.is_file() or path.is_symlink():
                raise ValueError(f"Chatterbox package is missing {name}")
        choices = (
            folder / "t3_mtl23ls_v3.safetensors",
            folder / "t3_mtl23ls_v2.safetensors",
        )
        checkpoint = next(
            (path for path in choices if path.is_file() and not path.is_symlink()),
            None,
        )
        if checkpoint is None:
            raise ValueError("Chatterbox package is missing V2/V3 T3 weights")
        return LocalTtsModel(self.key, checkpoint)

    def validate(self, selection: TtsSelection, model: LocalTtsModel) -> None:
        if selection.voice != "0":
            raise ValueError("Chatterbox built-in voice uses speaker 0")
        if selection.speed != 1.0:
            raise ValueError("Chatterbox does not support speaking-speed adjustment")
        isolated = isolated_runtime_python(self.key)
        if isolated is not None:
            probe_isolated_runtime(isolated, self.key, selection.device.value)
            return
        if util.find_spec("chatterbox") is None:
            raise ValueError("Chatterbox runtime is not installed")
        if selection.device is DevicePreference.GPU and not self._gpu_available():
            raise ValueError("Chatterbox GPU runtime is unavailable")

    @staticmethod
    def _gpu_available() -> bool:
        try:
            torch = import_module("torch")
        except ImportError:
            return False
        return bool(torch.cuda.is_available() or torch.backends.mps.is_available())

    def provider(self, selection: TtsSelection) -> str:
        if isolated_runtime_python(self.key) is not None:
            return (
                "cpu"
                if selection.device is DevicePreference.CPU
                else ("gpu" if selection.device is DevicePreference.GPU else "auto")
            )
        if selection.device is DevicePreference.CPU:
            return "cpu"
        if not self._gpu_available():
            return "cpu"
        torch = import_module("torch")
        return "cuda" if torch.cuda.is_available() else "mps"

    def load(self, model: LocalTtsModel, folder: Path, provider: str) -> Any:
        isolated = isolated_runtime_python(self.key)
        if isolated is not None:
            return IsolatedTtsWorker(isolated, self.key, folder, provider)
        chatterbox = import_module("chatterbox.mtl_tts")
        version = "v3" if "_v3." in model.model_file.name else "v2"
        # from_local never asks a model hub to download missing weights.
        return chatterbox.ChatterboxMultilingualTTS.from_local(
            folder, provider, t3_model=version
        )

    def generate(
        self, loaded: Any, text: str, voice: str, speed: float, language: str
    ) -> tuple[Any, int]:
        if isinstance(loaded, IsolatedTtsWorker):
            return loaded.generate(text, voice, speed, language)
        primary = language.split("-", maxsplit=1)[0]
        if primary not in loaded.get_supported_languages():
            raise SpeechSynthesisError(f"Chatterbox does not support {primary}")
        waveform = loaded.generate(text, language_id=primary)
        return waveform.squeeze().detach().cpu().numpy(), loaded.sr
