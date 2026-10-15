"""Compare direct STT with the real VAD/STT pipeline on one labeled WAV."""

import wave
from collections.abc import Callable, Iterator, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event
from time import monotonic
from typing import cast

from kyrin.audio.activity.speech_activity_monitor import (
    SpeechActivityFrame,
    SpeechTransition,
)
from kyrin.audio.activity.voice_activity_detector import VoiceActivityDetector
from kyrin.audio.audio_backlog import BacklogNotice
from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.live_speech_pipeline import LiveSpeechPipeline
from kyrin.audio.sample_rate_converter import SampleRateConverter
from kyrin.stt.contracts import SpeechToTextEngine, TurnAwareSpeechToTextSession
from kyrin.stt.device import SpeechToTextOptions
from kyrin.stt.evaluation import CorpusItem, edit_distance, normalize_text
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


class WavReplayInput:
    """Replay a WAV at its original rate without opening microphone hardware."""

    def __init__(self, path: Path, *, chunk_ms: int = 20) -> None:
        if chunk_ms <= 0:
            raise ValueError("chunk_ms must be positive")
        with wave.open(str(path), "rb") as audio:
            if (
                audio.getcomptype() != "NONE"
                or audio.getnchannels() != 1
                or audio.getsampwidth() != 2
            ):
                raise ValueError("WAV must be uncompressed mono 16-bit PCM")
            self.format = AudioFormat(audio.getframerate(), 1, AudioSampleFormat.INT16)
        self.path = path
        self.frames_per_chunk = max(1, round(self.format.sample_rate * chunk_ms / 1000))
        self._stop = Event()

    def capture(self) -> Iterator[AudioData]:
        started = monotonic()
        frames_sent = 0
        with wave.open(str(self.path), "rb") as audio:
            while not self._stop.is_set():
                data = audio.readframes(self.frames_per_chunk)
                if not data:
                    return
                frames_sent += len(data) // self.format.bytes_per_frame
                next_chunk_delay = max(
                    0.0, started + frames_sent / self.format.sample_rate - monotonic()
                )
                if self._stop.wait(next_chunk_delay):
                    return
                yield AudioData(data, self.format)

    def stop_capture(self) -> None:
        self._stop.set()


@dataclass(frozen=True, slots=True)
class PathResult:
    transcript: str
    final_languages: tuple[str, ...]
    final_seconds: float | None
    final_offset_from_audio_end_seconds: float | None
    elapsed_seconds: float
    elapsed_over_audio_seconds: float
    edit_distance: int
    cer: float
    speech_starts: int = 0
    speech_pauses: int = 0
    backlog_notices: int = 0


def _result(
    item: CorpusItem,
    updates: list[TranscriptUpdate],
    *,
    final_seconds: float | None,
    elapsed_seconds: float,
    audio_seconds: float,
    speech_starts: int = 0,
    speech_pauses: int = 0,
    backlog_notices: int = 0,
) -> PathResult:
    transcript = " ".join(
        update.text.strip()
        for update in updates
        if update.status is TranscriptStatus.FINAL and update.text.strip()
    )
    final_languages = tuple(
        dict.fromkeys(
            update.language
            for update in updates
            if update.status is TranscriptStatus.FINAL and update.language is not None
        )
    )
    reference = normalize_text(item.reference)
    distance = edit_distance(reference, normalize_text(transcript))
    return PathResult(
        transcript=transcript,
        final_languages=final_languages,
        final_seconds=final_seconds,
        final_offset_from_audio_end_seconds=(
            final_seconds - audio_seconds if final_seconds is not None else None
        ),
        elapsed_seconds=elapsed_seconds,
        elapsed_over_audio_seconds=max(0.0, elapsed_seconds - audio_seconds),
        edit_distance=distance,
        cer=distance / len(reference),
        speech_starts=speech_starts,
        speech_pauses=speech_pauses,
        backlog_notices=backlog_notices,
    )


def compare_item(
    engine: SpeechToTextEngine,
    detector_factory: Callable[[], VoiceActivityDetector],
    item: CorpusItem,
    *,
    options: SpeechToTextOptions,
    chunk_ms: int = 20,
    pause_confirm_ms: int = 384,
) -> dict[str, object]:
    """Run two paced passes over the same file; never interpret or execute text.

    A factory gives each live pass fresh VAD state. Model load is outside this
    function, so both passes use the same already-loaded STT engine.
    """
    direct_source = WavReplayInput(item.path, chunk_ms=chunk_ms)
    with wave.open(str(item.path), "rb") as audio:
        audio_seconds = audio.getnframes() / audio.getframerate()
    session = engine.open_session(options)
    direct_updates: list[TranscriptUpdate] = []
    direct_final: float | None = None
    direct_started = monotonic()

    def observe(updates: Sequence[TranscriptUpdate]) -> None:
        nonlocal direct_final
        direct_updates.extend(updates)
        if direct_final is None and any(
            update.status is TranscriptStatus.FINAL for update in updates
        ):
            direct_final = monotonic() - direct_started

    try:
        converter = SampleRateConverter(
            direct_source.format, session.input_format.sample_rate
        )
        if converter.output_format != session.input_format:
            raise ValueError("WAV cannot be converted to STT input format")
        if isinstance(session, TurnAwareSpeechToTextSession):
            observe(cast(TurnAwareSpeechToTextSession, session).start_turn())
        for chunk in converter.convert(direct_source.capture()):
            observe(session.accept_audio(chunk))
        if isinstance(session, TurnAwareSpeechToTextSession):
            observe(cast(TurnAwareSpeechToTextSession, session).end_turn())
        observe(session.finish())
        direct_elapsed = monotonic() - direct_started
    finally:
        session.close()
    direct = _result(
        item,
        direct_updates,
        final_seconds=direct_final,
        elapsed_seconds=direct_elapsed,
        audio_seconds=audio_seconds,
    )

    live_source = WavReplayInput(item.path, chunk_ms=chunk_ms)
    pipeline = LiveSpeechPipeline(
        live_source,
        live_source.format,
        detector_factory(),
        engine,
        options=options,
        pause_confirm_ms=pause_confirm_ms,
    )
    live_updates: list[TranscriptUpdate] = []
    live_final: float | None = None
    starts = pauses = backlogs = 0
    live_started = monotonic()
    with pipeline.open() as events:
        for event in events:
            if isinstance(event, TranscriptUpdate):
                live_updates.append(event)
                if live_final is None and event.status is TranscriptStatus.FINAL:
                    live_final = monotonic() - live_started
            elif isinstance(event, SpeechActivityFrame):
                starts += event.transition is SpeechTransition.STARTED
                pauses += event.transition is SpeechTransition.PAUSED
            elif isinstance(event, BacklogNotice):
                backlogs += 1
    live_elapsed = monotonic() - live_started
    live = _result(
        item,
        live_updates,
        final_seconds=live_final,
        elapsed_seconds=live_elapsed,
        audio_seconds=audio_seconds,
        speech_starts=starts,
        speech_pauses=pauses,
        backlog_notices=backlogs,
    )
    return {
        "id": item.id,
        "language": item.language,
        "reference": item.reference,
        "audio_seconds": audio_seconds,
        "direct": asdict(direct),
        "live": asdict(live),
    }
