"""Score any streaming STT engine on a labeled local WAV corpus."""

import csv
import unicodedata
import wave
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from time import monotonic, sleep

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.sample_rate_converter import SampleRateConverter
from kyrin.stt.contracts import SpeechToTextEngine, TurnAwareSpeechToTextSession
from kyrin.stt.device import DevicePreference, SpeechToTextOptions
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


@dataclass(frozen=True, slots=True)
class CorpusItem:
    id: str
    path: Path
    language: str
    reference: str


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    id: str
    language: str
    reference: str
    transcript: str
    reference_characters: int
    edit_distance: int
    cer: float
    reference_words: int
    word_edit_distance: int
    wer: float
    audio_seconds: float
    first_partial_seconds: float | None
    first_final_seconds: float | None
    elapsed_seconds: float
    compute_device: str


def load_corpus(manifest: Path) -> tuple[CorpusItem, ...]:
    """Resolve relative WAV paths beside the manifest and reject empty records."""
    items: list[CorpusItem] = []
    seen_ids: set[str] = set()
    with manifest.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None or not {
            "id",
            "path",
            "language",
            "reference",
        }.issubset(reader.fieldnames):
            raise ValueError("manifest needs id,path,language,reference columns")
        for row_number, row in enumerate(reader, start=2):
            item_id = (row.get("id") or "").strip()
            audio_path = (row.get("path") or "").strip()
            language = (row.get("language") or "").strip().lower()
            reference = (row.get("reference") or "").strip()
            if not all((item_id, audio_path, language, reference)):
                raise ValueError(f"manifest row {row_number} has an empty field")
            if not normalize_text(reference):
                raise ValueError(f"manifest row {row_number} has no scorable text")
            if item_id in seen_ids:
                raise ValueError(f"duplicate corpus id: {item_id}")
            seen_ids.add(item_id)
            path = Path(audio_path)
            if not path.is_absolute():
                path = manifest.parent / path
            if not path.is_file():
                raise FileNotFoundError(f"audio file is missing: {path}")
            items.append(CorpusItem(item_id, path, language, reference))
    if not items:
        raise ValueError("manifest has no audio records")
    return tuple(items)


def normalize_text(text: str) -> str:
    """Apply one transparent normalization before character scoring."""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    text = "".join(
        " " if unicodedata.category(char).startswith("P") else char for char in text
    )
    return " ".join(text.split())


def edit_distance[T](left: Sequence[T], right: Sequence[T]) -> int:
    """Count insertions, deletions, and substitutions with bounded memory."""
    if len(right) > len(left):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def evaluate_item(
    engine: SpeechToTextEngine,
    item: CorpusItem,
    *,
    chunk_ms: int = 20,
    realtime: bool = True,
    device: DevicePreference = DevicePreference.AUTO,
    engine_language: str | None = None,
) -> EvaluationResult:
    """Stream one WAV in order and score only sealed final transcript segments."""
    if chunk_ms <= 0:
        raise ValueError("chunk_ms must be positive")
    with wave.open(str(item.path), "rb") as audio:
        if (
            audio.getcomptype() != "NONE"
            or audio.getnchannels() != 1
            or audio.getsampwidth() != 2
        ):
            raise ValueError(f"WAV must be uncompressed mono 16-bit PCM: {item.path}")
        source_format = AudioFormat(audio.getframerate(), 1, AudioSampleFormat.INT16)
        frames_per_chunk = max(1, round(source_format.sample_rate * chunk_ms / 1000))

        def source_chunks() -> Iterator[AudioData]:
            while data := audio.readframes(frames_per_chunk):
                yield AudioData(data, source_format)

        session = engine.open_session(
            SpeechToTextOptions(
                device=device,
                language_hint=(
                    engine_language if engine_language is not None else item.language
                ),
            )
        )
        try:
            converter = SampleRateConverter(
                source_format, session.input_format.sample_rate
            )
            if converter.output_format != session.input_format:
                raise ValueError("WAV cannot be converted to STT input format")
            started = monotonic()
            audio_seconds = 0.0
            first_partial: float | None = None
            first_final: float | None = None
            final_segments: list[str] = []

            def observe(updates: Sequence[TranscriptUpdate]) -> None:
                nonlocal first_partial, first_final
                observed_at = monotonic() - started
                for update in updates:
                    if update.status is TranscriptStatus.PARTIAL:
                        if first_partial is None and update.text.strip():
                            first_partial = observed_at
                    elif update.status is TranscriptStatus.FINAL:
                        if first_final is None:
                            first_final = observed_at
                        if update.text.strip():
                            final_segments.append(update.text.strip())

            if isinstance(session, TurnAwareSpeechToTextSession):
                observe(session.start_turn())

            for chunk in converter.convert(source_chunks()):
                audio_seconds += (
                    len(chunk.data)
                    / chunk.audio_format.bytes_per_frame
                    / chunk.audio_format.sample_rate
                )
                if realtime:
                    sleep(max(0.0, started + audio_seconds - monotonic()))
                observe(session.accept_audio(chunk))
            if isinstance(session, TurnAwareSpeechToTextSession):
                observe(session.end_turn())
            observe(session.finish())
            elapsed = monotonic() - started
            transcript = " ".join(final_segments)
            reference = normalize_text(item.reference)
            normalized_transcript = normalize_text(transcript)
            distance = edit_distance(reference, normalized_transcript)
            reference_words = reference.split()
            word_distance = edit_distance(
                reference_words, normalized_transcript.split()
            )
            return EvaluationResult(
                id=item.id,
                language=item.language,
                reference=item.reference,
                transcript=transcript,
                reference_characters=len(reference),
                edit_distance=distance,
                cer=distance / len(reference),
                reference_words=len(reference_words),
                word_edit_distance=word_distance,
                wer=word_distance / len(reference_words),
                audio_seconds=audio_seconds,
                first_partial_seconds=first_partial,
                first_final_seconds=first_final,
                elapsed_seconds=elapsed,
                compute_device=session.compute_device.value,
            )
        finally:
            session.close()


def summarize(results: tuple[EvaluationResult, ...]) -> dict[str, object]:
    """Weight each file by reference characters instead of averaging percents."""
    if not results:
        raise ValueError("results must not be empty")
    characters = sum(result.reference_characters for result in results)
    edits = sum(result.edit_distance for result in results)
    words = sum(result.reference_words for result in results)
    word_edits = sum(result.word_edit_distance for result in results)
    return {
        "files": len(results),
        "reference_characters": characters,
        "edit_distance": edits,
        "cer": edits / characters,
        "reference_words": words,
        "word_edit_distance": word_edits,
        "wer": word_edits / words,
        "results": [asdict(result) for result in results],
    }
