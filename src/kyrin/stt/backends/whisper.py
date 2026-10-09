"""Turn-aware, replaceable Whisper STT backend using local whisper.cpp."""

from collections.abc import Callable, Sequence
from pathlib import Path
from threading import Lock

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.stt.backends.whisper_server import WhisperCppServer, WhisperResult
from kyrin.stt.capabilities import SpeechToTextCapabilities
from kyrin.stt.device import ComputeDevice, DevicePreference, SpeechToTextOptions
from kyrin.stt.errors import DeviceUnavailableError, SpeechToTextError
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate

_FORMAT = AudioFormat(16_000, 1, AudioSampleFormat.INT16)


def _byte_count(seconds: float) -> int:
    """Keep every configured audio boundary aligned to an INT16 sample."""
    return int(seconds * _FORMAT.sample_rate) * _FORMAT.bytes_per_frame


class WhisperSession:
    """Keep listening across turns; only a confirmed pause seals a transcript."""

    input_format = _FORMAT
    supports_partial_updates = True

    def __init__(
        self,
        infer: Callable[[bytes, str], str | WhisperResult],
        language: str,
        on_close: Callable[[], None],
        *,
        compute_device: ComputeDevice = ComputeDevice.CPU,
        partial_after_seconds: float = 1.5,
        partial_every_seconds: float = 2.5,
        preview_window_seconds: float = 8.0,
        maximum_turn_seconds: float = 30.0,
    ) -> None:
        if not 0 < partial_after_seconds <= partial_every_seconds:
            raise ValueError("partial interval must be positive and ordered")
        if not 0 < preview_window_seconds <= maximum_turn_seconds:
            raise ValueError("preview window must fit within the maximum turn")
        self._infer = infer
        self._language = language
        self._on_close = on_close
        self.compute_device = compute_device
        self._partial_after = _byte_count(partial_after_seconds)
        self._partial_every = _byte_count(partial_every_seconds)
        self._preview_window = _byte_count(preview_window_seconds)
        self._maximum_turn = _byte_count(maximum_turn_seconds)
        self._pre_roll = bytearray()
        self._turn = bytearray()
        self._active = False
        self._too_long = False
        self._next_partial = self._partial_after
        self._last_partial: str | None = None
        self._segment_id = 0
        self._finished = False
        self._closed = False

    def _require_open(self) -> None:
        if self._closed:
            raise SpeechToTextError("Whisper session is closed")
        if self._finished:
            raise SpeechToTextError("Whisper session has finished")

    def _transcribe(self, pcm: bytes) -> WhisperResult:
        try:
            result = self._infer(pcm, self._language)
            if isinstance(result, WhisperResult):
                return WhisperResult(result.text.strip(), result.language)
            return WhisperResult(result.strip(), self._language)
        except (OSError, ValueError, RuntimeError) as exc:
            raise SpeechToTextError("Whisper could not transcribe audio") from exc

    def accept_audio(self, chunk: AudioData) -> Sequence[TranscriptUpdate]:
        self._require_open()
        if chunk.audio_format != self.input_format:
            raise SpeechToTextError("audio format does not match Whisper session")
        if not chunk.data:
            return ()
        self._pre_roll.extend(chunk.data)
        del self._pre_roll[: -_byte_count(0.5)]
        if not self._active:
            return ()
        remaining = self._maximum_turn - len(self._turn)
        self._turn.extend(chunk.data[:remaining])
        if len(chunk.data) > remaining:
            self._too_long = True
        if self._too_long or len(self._turn) < self._next_partial:
            return ()
        self._next_partial = len(self._turn) + self._partial_every
        result = self._transcribe(bytes(self._turn[-self._preview_window :]))
        text = result.text
        if not text or text == self._last_partial:
            return ()
        self._last_partial = text
        return (
            TranscriptUpdate(
                self._segment_id, text, TranscriptStatus.PARTIAL, result.language
            ),
        )

    def start_turn(self) -> Sequence[TranscriptUpdate]:
        self._require_open()
        if not self._active:
            self._active = True
            self._turn = self._pre_roll.copy()
            self._too_long = False
            # Preroll preserves the speech onset but is not elapsed speech time.
            self._next_partial = len(self._turn) + self._partial_after
            self._last_partial = None
        return ()

    def end_turn(self) -> Sequence[TranscriptUpdate]:
        self._require_open()
        if not self._active:
            return ()
        self._active = False
        # A turn beyond the bounded Whisper context is never executed from
        # its incomplete preview. Empty final text retracts that preview.
        transcription = (
            WhisperResult("", None)
            if self._too_long
            else self._transcribe(bytes(self._turn))
        )
        text = transcription.text
        result: tuple[TranscriptUpdate, ...] = ()
        if text or self._last_partial is not None:
            result = (
                TranscriptUpdate(
                    self._segment_id,
                    text,
                    TranscriptStatus.FINAL,
                    transcription.language,
                ),
            )
        self._segment_id += 1
        self._turn.clear()
        self._last_partial = None
        self._pre_roll.clear()
        return result

    def finish(self) -> Sequence[TranscriptUpdate]:
        self._require_open()
        result = self.end_turn()
        self._finished = True
        return result

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._turn.clear()
        self._pre_roll.clear()
        self._on_close()


class WhisperEngine:
    """Load a locally supplied Whisper model once, without downloading it."""

    def __init__(
        self,
        server_path: str | Path,
        model_path: str | Path,
        *,
        language: str = "en",
        threads: int = 4,
        compute_device: ComputeDevice = ComputeDevice.CPU,
    ) -> None:
        language = language.strip().lower()
        if not language:
            raise ValueError("language must not be empty")
        self._language = language
        self._compute_device = compute_device
        self._server: WhisperCppServer | None = WhisperCppServer(
            server_path, model_path, threads=threads, compute_device=compute_device
        )
        self._lock = Lock()
        self._active_sessions = 0
        self.capabilities = SpeechToTextCapabilities(
            supported_devices=frozenset({compute_device}),
            supported_languages=None if language == "auto" else frozenset({language}),
            supports_partial_updates=True,
            supports_language_detection=language == "auto",
        )

    def open_session(self, options: SpeechToTextOptions) -> WhisperSession:
        if (
            options.device is DevicePreference.GPU
            and self._compute_device is not ComputeDevice.GPU
        ):
            raise DeviceUnavailableError("this Whisper session is running on CPU")
        if (
            options.device is DevicePreference.CPU
            and self._compute_device is not ComputeDevice.CPU
        ):
            raise DeviceUnavailableError("this Whisper session is running on GPU")
        if options.language_hint is not None:
            if options.language_hint.strip().lower() != self._language:
                raise SpeechToTextError(
                    f"Whisper engine language is {self._language}, not "
                    f"{options.language_hint}"
                )
        with self._lock:
            if self._server is None:
                raise SpeechToTextError("Whisper engine is closed")
            self._active_sessions += 1
            server = self._server
            infer: Callable[[bytes, str], str | WhisperResult] = (
                (lambda pcm, _language: server.transcribe_auto(pcm))
                if self._language == "auto"
                else server.transcribe
            )
        return WhisperSession(
            infer,
            self._language,
            self._session_closed,
            compute_device=self._compute_device,
        )

    def _session_closed(self) -> None:
        with self._lock:
            self._active_sessions -= 1

    def close(self) -> None:
        with self._lock:
            if self._active_sessions:
                raise SpeechToTextError("close Whisper sessions before the engine")
            server = self._server
            self._server = None
        if server is not None:
            server.close()
