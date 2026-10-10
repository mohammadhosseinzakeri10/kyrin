"""Offline, CPU-only Vosk adapter for one configured language model."""

import importlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from threading import Lock
from typing import Protocol, cast

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.stt.capabilities import SpeechToTextCapabilities
from kyrin.stt.device import ComputeDevice, DevicePreference, SpeechToTextOptions
from kyrin.stt.errors import DeviceUnavailableError, SpeechToTextError
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


class _VoskRecognizer(Protocol):
    def AcceptWaveform(self, data: bytes) -> bool: ...

    def PartialResult(self) -> str: ...

    def Result(self) -> str: ...

    def FinalResult(self) -> str: ...


def _result_text(payload: str, key: str) -> str:
    try:
        result = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise SpeechToTextError("Vosk returned invalid JSON") from exc
    if not isinstance(result, dict) or not isinstance(result.get(key), str):
        raise SpeechToTextError(f"Vosk result is missing a text field: {key}")
    return cast(str, result[key]).strip()


class VoskSession:
    """Keep one recognizer alive across speech pauses and ordered PCM chunks."""

    supports_partial_updates = True
    compute_device = ComputeDevice.CPU

    def __init__(
        self,
        recognizer: _VoskRecognizer,
        input_format: AudioFormat,
        language: str,
        on_close: Callable[[], None],
    ) -> None:
        self._recognizer: _VoskRecognizer | None = recognizer
        self.input_format = input_format
        self._language = language
        self._on_close = on_close
        self._segment_id = 0
        self._last_partial: str | None = None
        self._finished = False

    def _require_open(self) -> _VoskRecognizer:
        if self._recognizer is None:
            raise SpeechToTextError("Vosk session is closed")
        if self._finished:
            raise SpeechToTextError("Vosk session has finished")
        return self._recognizer

    def accept_audio(self, chunk: AudioData) -> Sequence[TranscriptUpdate]:
        recognizer = self._require_open()
        if chunk.audio_format != self.input_format:
            raise SpeechToTextError("audio format does not match Vosk session")
        if not chunk.data:
            return ()
        try:
            endpoint = recognizer.AcceptWaveform(chunk.data)
            payload = recognizer.Result() if endpoint else recognizer.PartialResult()
        except Exception as exc:  # Vosk's Python API raises plain Exception.
            raise SpeechToTextError("Vosk could not process audio") from exc

        if endpoint:
            text = _result_text(payload, "text")
            update = self._final_update(text)
            return (update,) if update is not None else ()

        text = _result_text(payload, "partial")
        if not text or text == self._last_partial:
            return ()
        self._last_partial = text
        return (
            TranscriptUpdate(
                self._segment_id, text, TranscriptStatus.PARTIAL, self._language
            ),
        )

    def _final_update(self, text: str) -> TranscriptUpdate | None:
        update = None
        if text or self._last_partial is not None:
            update = TranscriptUpdate(
                self._segment_id, text, TranscriptStatus.FINAL, self._language
            )
        self._segment_id += 1
        self._last_partial = None
        return update

    def finish(self) -> Sequence[TranscriptUpdate]:
        recognizer = self._require_open()
        try:
            payload = recognizer.FinalResult()
        except Exception as exc:  # Vosk's Python API raises plain Exception.
            raise SpeechToTextError("Vosk could not finish the stream") from exc
        text = _result_text(payload, "text")
        update = self._final_update(text)
        self._finished = True
        return (update,) if update is not None else ()

    def close(self) -> None:
        if self._recognizer is None:
            return
        self._recognizer = None
        self._on_close()


class VoskEngine:
    """Load a local Vosk model without downloading or bundling it."""

    def __init__(
        self, model_path: str | Path, *, language: str, sample_rate: int = 16000
    ) -> None:
        path = Path(model_path).expanduser()
        if not path.is_dir():
            raise FileNotFoundError(f"Vosk model directory does not exist: {path}")
        language = language.strip().lower()
        if not language:
            raise ValueError("language must not be empty")
        self._input_format = AudioFormat(sample_rate, 1, AudioSampleFormat.INT16)
        self._language = language
        self.capabilities = SpeechToTextCapabilities(
            supported_devices=frozenset({ComputeDevice.CPU}),
            supported_languages=frozenset({language}),
            supports_partial_updates=True,
            supports_language_detection=False,
        )
        try:
            vosk = importlib.import_module("vosk")
        except (ImportError, OSError) as exc:
            raise SpeechToTextError(
                "Vosk is not installed; install the optional stt-vosk dependency"
            ) from exc
        try:
            self._model: object | None = vosk.Model(str(path))
        except Exception as exc:  # Vosk's Python API raises plain Exception.
            raise SpeechToTextError(f"Vosk could not load model: {path}") from exc
        self._vosk = vosk
        self._lock = Lock()
        self._active_sessions = 0

    def open_session(self, options: SpeechToTextOptions) -> VoskSession:
        if options.vocabulary_hints:
            raise SpeechToTextError(
                "this Vosk adapter does not support vocabulary hints"
            )
        if options.device is DevicePreference.GPU:
            raise DeviceUnavailableError("this Vosk adapter supports CPU only")
        if options.language_hint is not None:
            hint = options.language_hint.strip().lower()
            if hint != self._language:
                raise SpeechToTextError(
                    f"Vosk model language is {self._language}, not {hint}"
                )
        with self._lock:
            if self._model is None:
                raise SpeechToTextError("Vosk engine is closed")
            try:
                recognizer = cast(
                    _VoskRecognizer,
                    self._vosk.KaldiRecognizer(
                        self._model, self._input_format.sample_rate
                    ),
                )
            except Exception as exc:  # Vosk's Python API raises plain Exception.
                raise SpeechToTextError("Vosk could not open a session") from exc
            self._active_sessions += 1
        return VoskSession(
            recognizer, self._input_format, self._language, self._session_closed
        )

    def _session_closed(self) -> None:
        with self._lock:
            self._active_sessions -= 1

    def close(self) -> None:
        with self._lock:
            if self._active_sessions:
                raise SpeechToTextError("close Vosk sessions before the engine")
            self._model = None
