"""Offline speech adapters and local model-package discovery."""

import logging
import re
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module, util
from pathlib import Path
from subprocess import SubprocessError
from threading import Lock, Thread
from typing import Any, Protocol

from kyrin.responses.speech import SpeechDispatcherSynthesizer, SpeechSynthesisError
from kyrin.stt.device import DevicePreference
from kyrin.tts.chatterbox import ChatterboxAdapter
from kyrin.tts.families import TTS_FAMILIES, TTS_FAMILY_BY_KEY, TtsFamily
from kyrin.tts.isolation import (
    IsolatedTtsWorker,
    isolated_runtime_python,
    probe_isolated_runtime,
)
from kyrin.tts.models import TtsLanguageRoute, TtsSelection
from kyrin.tts.qwen import QwenCustomVoiceAdapter


@dataclass(frozen=True, slots=True)
class LocalTtsModel:
    family: str
    model_file: Path


class TtsModelAdapter(Protocol):
    """Trusted, installed code for one model format; model folders contain data only."""

    key: str
    label: str

    def inspect(self, folder: Path) -> LocalTtsModel | None: ...

    def validate(self, selection: TtsSelection, model: LocalTtsModel) -> None: ...

    def provider(self, selection: TtsSelection) -> str: ...

    def load(self, model: LocalTtsModel, folder: Path, provider: str) -> Any: ...

    def generate(
        self, loaded: Any, text: str, voice: str, speed: float, language: str
    ) -> tuple[Any, int]: ...


_ADAPTERS: dict[str, TtsModelAdapter] = {}
_LOGGER = logging.getLogger(__name__)


def register_tts_adapter(adapter: TtsModelAdapter) -> None:
    """Register a packaged adapter; never import executable code from model folders."""
    if (
        re.fullmatch(r"[a-z][a-z0-9_-]*", adapter.key) is None
        or adapter.key in _ADAPTERS
        or adapter.key == "speech-dispatcher"
    ):
        raise ValueError("Duplicate or invalid TTS adapter key")
    _ADAPTERS[adapter.key] = adapter


def available_tts_adapters() -> tuple[TtsModelAdapter, ...]:
    return tuple(_ADAPTERS.values())


class _SherpaAdapter:
    def __init__(self, family: TtsFamily) -> None:
        self.family = family
        self.key = family.key
        self.label = family.label

    def inspect(self, folder: Path) -> LocalTtsModel | None:
        family = self.family
        voices = folder / "voices.bin"
        named = folder.name.startswith(family.folder_prefixes)
        legacy_kitten = (
            family.key == "kitten"
            and voices.is_file()
            and not any(
                folder.name.startswith(item.folder_prefixes) for item in TTS_FAMILIES
            )
            and not list(folder.glob("lexicon*.txt"))
        )
        legacy_kokoro = (
            family.key == "kokoro"
            and voices.is_file()
            and bool(list(folder.glob("lexicon*.txt")))
            and not any(
                folder.name.startswith(item.folder_prefixes) for item in TTS_FAMILIES
            )
        )
        if not (named or legacy_kitten or legacy_kokoro):
            return None
        models = tuple(
            path
            for path in folder.glob("*.onnx")
            if path.is_file() and not path.is_symlink()
        )
        if len(models) != 1:
            raise ValueError("TTS model folder needs exactly one ONNX model file")
        if (
            not (folder / "tokens.txt").is_file()
            or (folder / "tokens.txt").is_symlink()
        ):
            raise ValueError("TTS model is missing tokens.txt")
        data_dir = folder / "espeak-ng-data"
        if not data_dir.is_dir() or data_dir.is_symlink():
            raise ValueError("TTS model is missing espeak-ng-data")
        if family.needs_voices and (not voices.is_file() or voices.is_symlink()):
            raise ValueError(f"{family.key} is missing voices.bin")
        if family.needs_lexicon and not any(
            path.is_file() and not path.is_symlink()
            for path in folder.glob("lexicon*.txt")
        ):
            raise ValueError("Kokoro is missing a lexicon file")
        return LocalTtsModel(family.key, models[0])

    def validate(self, selection: TtsSelection, model: LocalTtsModel) -> None:
        if (
            not selection.voice.isdecimal()
            or int(selection.voice) > self.family.max_voice
        ):
            raise ValueError("Selected TTS speaker is unavailable")
        if util.find_spec("sherpa_onnx") is None:
            raise ValueError("Local TTS runtime is not installed (sherpa-onnx)")
        if selection.device is DevicePreference.GPU:
            isolated = isolated_runtime_python("sherpa-gpu")
            if isolated is not None:
                probe_isolated_runtime(isolated, self.key, "gpu")
            elif not _cuda_available():
                raise ValueError("TTS GPU runtime is unavailable; install CUDA support")

    def provider(self, selection: TtsSelection) -> str:
        isolated = isolated_runtime_python("sherpa-gpu")
        if selection.device is DevicePreference.GPU and isolated is not None:
            return "gpu"
        if selection.device is DevicePreference.AUTO and isolated is not None:
            try:
                probe_isolated_runtime(isolated, self.key, "gpu")
            except ValueError:
                pass
            else:
                return "gpu"
        use_gpu = selection.device is DevicePreference.GPU or (
            selection.device is DevicePreference.AUTO and _cuda_available()
        )
        return "cuda" if use_gpu else "cpu"

    def load(self, model: LocalTtsModel, folder: Path, provider: str) -> Any:
        if provider == "gpu":
            isolated = isolated_runtime_python("sherpa-gpu")
            if isolated is None:
                raise SpeechSynthesisError("TTS GPU runtime is unavailable")
            return IsolatedTtsWorker(isolated, self.key, folder, provider)
        sherpa = import_module("sherpa_onnx")
        config = sherpa.OfflineTtsConfig(
            model=sherpa.OfflineTtsModelConfig(
                **_family_config(sherpa, model, folder),
                provider=provider,
                num_threads=2,
            )
        )
        if not config.validate():
            raise SpeechSynthesisError("Local TTS model configuration is invalid")
        return sherpa.OfflineTts(config)

    def generate(
        self, loaded: Any, text: str, voice: str, speed: float, language: str
    ) -> tuple[Any, int]:
        if isinstance(loaded, IsolatedTtsWorker):
            return loaded.generate(text, voice, speed, language)
        speaker_count = getattr(loaded, "num_speakers", None)
        if speaker_count is not None and int(voice) >= speaker_count:
            raise SpeechSynthesisError("Selected TTS voice is unavailable")
        audio = loaded.generate(text=text, sid=int(voice), speed=speed)
        return audio.samples, audio.sample_rate


def _family_config(sherpa: Any, model: LocalTtsModel, folder: Path) -> dict[str, Any]:
    family = TTS_FAMILY_BY_KEY[model.family]
    options = {
        "model": str(model.model_file),
        "tokens": str(folder / "tokens.txt"),
        "data_dir": str(folder / "espeak-ng-data"),
    }
    if family.needs_voices:
        options["voices"] = str(folder / "voices.bin")
    if family.needs_lexicon:
        lexicons = sorted(
            path
            for path in folder.glob("lexicon*.txt")
            if path.is_file() and not path.is_symlink()
        )
        options["lexicon"] = ",".join(str(path) for path in lexicons)
    return {family.key: getattr(sherpa, family.sherpa_config)(**options)}


def inspect_tts_model(folder: Path) -> LocalTtsModel:
    """Recognize supported extracted packages without loading their weights."""
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("Select an extracted local TTS model directory")
    for adapter in available_tts_adapters():
        model = adapter.inspect(folder)
        if model is not None:
            if model.family != adapter.key:
                raise ValueError("TTS adapter returned a mismatched family")
            return model
    raise ValueError("Unsupported TTS package family")


def kitten_model_file(folder: Path) -> Path:
    """Backward-compatible validation for local Kitten packages."""
    found = inspect_tts_model(folder)
    if found.family != "kitten":
        raise ValueError("Select a Kitten model directory")
    return found.model_file


def _cuda_available() -> bool:
    try:
        sherpa = import_module("sherpa_onnx")
        module_file = getattr(sherpa, "__file__", None)
        provider = (
            Path(module_file).parent / "lib/libonnxruntime_providers_cuda.so"
            if module_file
            else None
        )
        return bool(
            provider
            and "cuda" in getattr(sherpa, "__version__", "")
            and provider.is_file()
        )
    except ImportError, OSError:
        return False


def validate_tts_selection(selection: TtsSelection) -> None:
    """Reject unavailable engines and mismatched model packages before saving."""
    if selection.backend == "speech-dispatcher":
        try:
            SpeechDispatcherSynthesizer()
        except SpeechSynthesisError as exc:
            raise ValueError(str(exc)) from exc
        return
    if selection.backend not in _ADAPTERS:
        raise ValueError(f"TTS adapter is unavailable: {selection.backend}")
    assert selection.model_path is not None
    model = inspect_tts_model(selection.model_path)
    if model.family != selection.backend:
        raise ValueError(f"Selected model is {model.family}, not {selection.backend}")
    _ADAPTERS[selection.backend].validate(selection, model)


class ConfiguredSpeechSynthesizer:
    """Route response languages to installed model families behind one contract."""

    def __init__(
        self,
        selection: TtsSelection,
        routes: tuple[TtsLanguageRoute, ...] = (),
    ) -> None:
        self._selection = selection
        self._routes = routes
        self._lock = Lock()
        self._models_lock = Lock()
        self._configuration_version = 0
        self._retire_requested = False
        self._closed = False
        self._active_worker: IsolatedTtsWorker | None = None
        self._playback_lock = Lock()
        self._playback_generation = 0
        self._active_playback: Any | None = None
        # Keep two commonly used language voices warm without retaining every model.
        self._loaded: OrderedDict[tuple[str, Path, str], Any] = OrderedDict()

    def configure(
        self,
        selection: TtsSelection,
        routes: tuple[TtsLanguageRoute, ...] = (),
    ) -> None:
        with self._lock:
            if self._closed:
                raise SpeechSynthesisError("TTS synthesizer is closed")
            if selection == self._selection and routes == self._routes:
                return
            self._selection = selection
            self._routes = routes
            self._configuration_version += 1
            self._retire_requested = True
        self.interrupt()
        Thread(
            target=self._retire_cached_models,
            name="kyrin-tts-release",
            daemon=True,
        ).start()

    def close(self) -> bool:
        """Stop isolated inference and release models if no CPU call is stuck.

        Return false when in-process generation still owns the model lock. The
        model must remain alive until that call ends; process exit reclaims it.
        """
        with self._lock:
            self._closed = True
            self._configuration_version += 1
            self._retire_requested = True
            active_worker = self._active_worker
        self.interrupt()
        try:
            if active_worker is not None:
                active_worker.close()
        finally:
            if not self._models_lock.acquire(timeout=2):
                _LOGGER.warning(
                    "TTS generation did not stop before shutdown; "
                    "the process will reclaim its model memory"
                )
                released = False
            else:
                try:
                    self._retire_cached_models_locked()
                finally:
                    self._models_lock.release()
                released = True
        return released

    def _retire_cached_models(self) -> None:
        with self._models_lock:
            self._retire_cached_models_locked()

    def _retire_cached_models_locked(self) -> None:
        with self._lock:
            if not self._retire_requested:
                return
            self._retire_requested = False
        retired = tuple(self._loaded.values())
        self._loaded.clear()
        for model in retired:
            close = getattr(model, "close", None)
            if callable(close):
                try:
                    close()
                except (OSError, RuntimeError, SubprocessError) as exc:
                    _LOGGER.warning("Could not release retired TTS model: %s", exc)

    def speak(self, text: str, language: str) -> None:
        self.speak_if_current(text, language, lambda: True)

    def speak_if_current(
        self, text: str, language: str, is_current: Callable[[], bool]
    ) -> None:
        """Discard a stage prompt if its dialog changed before playback starts."""
        if not text.strip():
            return
        with self._playback_lock:
            generation = self._playback_generation
        with self._lock:
            selection = self._selection
            routes = self._routes
            configuration_version = self._configuration_version
        normalized = language.replace("_", "-").casefold()
        selected_route = next(
            (route for route in routes if route.language.casefold() == normalized), None
        )
        if selected_route is None:
            primary = normalized.split("-", maxsplit=1)[0]
            selected_route = next(
                (route for route in routes if route.language.casefold() == primary),
                None,
            )
        if selected_route is not None:
            selection = selected_route.selection
        elif (
            not normalized.startswith("en") and selection.backend != "speech-dispatcher"
        ):
            # The selected English model must not pronounce unrelated languages.
            selection = TtsSelection(speed=selection.speed)
        if selection.backend == "speech-dispatcher":
            if not is_current():
                return
            SpeechDispatcherSynthesizer(
                rate=round((selection.speed - 1.0) * 100),
                timeout_s=25,
                voice_type=selection.voice,
            ).speak(text, language)
            return
        self._speak_model(
            text,
            selection,
            normalized,
            is_current=is_current,
            generation=generation,
            configuration_version=configuration_version,
        )

    def interrupt(self) -> None:
        """Invalidate pending model audio and stop playback already in progress."""
        with self._playback_lock:
            self._playback_generation += 1
            playback = self._active_playback
            if playback is not None:
                try:
                    playback.stop()
                except Exception:
                    pass

    def speak_preview(
        self, text: str, language: str, selection: TtsSelection
    ) -> None:
        """Play one draft selection without changing the saved voice routes."""
        if not text.strip():
            return
        if selection.backend == "speech-dispatcher":
            SpeechDispatcherSynthesizer(
                rate=round((selection.speed - 1.0) * 100),
                timeout_s=25,
                voice_type=selection.voice,
            ).speak(text, language)
            return
        self._speak_model(text, selection, language.replace("_", "-").casefold())

    def _speak_model(
        self,
        text: str,
        selection: TtsSelection,
        language: str,
        *,
        is_current: Callable[[], bool] = lambda: True,
        generation: int | None = None,
        configuration_version: int | None = None,
    ) -> None:
        assert selection.model_path is not None
        if generation is None:
            with self._playback_lock:
                generation = self._playback_generation
        try:
            validate_tts_selection(selection)
            adapter = _ADAPTERS[selection.backend]
            provider = adapter.provider(selection)
            key = (selection.backend, selection.model_path, provider)
            with self._models_lock:
                self._retire_cached_models_locked()
                if configuration_version is not None:
                    with self._lock:
                        if (
                            self._closed
                            or configuration_version != self._configuration_version
                        ):
                            return
                else:
                    with self._lock:
                        if self._closed:
                            raise SpeechSynthesisError("TTS synthesizer is closed")
                if key not in self._loaded:
                    folder = selection.model_path
                    model = inspect_tts_model(folder)
                    self._loaded[key] = adapter.load(model, folder, provider)
                    if len(self._loaded) > 2:
                        _, retired = self._loaded.popitem(last=False)
                        close = getattr(retired, "close", None)
                        if callable(close):
                            close()
                self._loaded.move_to_end(key)
                tts = self._loaded[key]
                with self._lock:
                    if self._closed:
                        return
                    self._active_worker = (
                        tts if isinstance(tts, IsolatedTtsWorker) else None
                    )
                try:
                    samples, sample_rate = adapter.generate(
                        tts, text, selection.voice, selection.speed, language
                    )
                except (SpeechSynthesisError, RuntimeError, ValueError):
                    # A CUDA assertion leaves the worker's CUDA context unusable.
                    self._loaded.pop(key, None)
                    close = getattr(tts, "close", None)
                    if callable(close):
                        close()
                    raise
                finally:
                    with self._lock:
                        if self._active_worker is tts:
                            self._active_worker = None
            if len(samples) == 0:
                raise SpeechSynthesisError("Local TTS model produced no audio")
            try:
                with self._playback_lock:
                    if generation != self._playback_generation or not is_current():
                        return
                    playback = import_module("sounddevice")
                    playback.play(samples, sample_rate, blocking=False)
                    self._active_playback = playback
                try:
                    playback.wait()
                finally:
                    with self._playback_lock:
                        if self._active_playback is playback:
                            self._active_playback = None
            except Exception as exc:
                if generation != self._playback_generation:
                    return
                raise SpeechSynthesisError("Audio output is unavailable") from exc
        except ValueError as exc:
            # Keep selection errors actionable in the Voice Output preview.
            raise SpeechSynthesisError(str(exc)) from exc
        except (ImportError, OSError, RuntimeError) as exc:
            if isinstance(exc, SpeechSynthesisError):
                raise
            raise SpeechSynthesisError("Local TTS playback failed") from exc


for _family in TTS_FAMILIES:
    register_tts_adapter(_SherpaAdapter(_family))

register_tts_adapter(ChatterboxAdapter())
register_tts_adapter(QwenCustomVoiceAdapter())
