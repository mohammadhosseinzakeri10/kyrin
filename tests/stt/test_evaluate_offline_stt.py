"""A local benchmark must score final text and release every STT session."""

import csv
import wave
from collections.abc import Sequence
from pathlib import Path

import pytest

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.stt.capabilities import SpeechToTextCapabilities
from kyrin.stt.device import ComputeDevice, SpeechToTextOptions
from kyrin.stt.evaluation import (
    CorpusItem,
    edit_distance,
    evaluate_item,
    load_corpus,
    normalize_text,
    summarize,
)
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate

FORMAT = AudioFormat(16000, 1, AudioSampleFormat.INT16)


class FakeSession:
    input_format = FORMAT
    compute_device = ComputeDevice.CPU
    supports_partial_updates = True

    def __init__(self) -> None:
        self.chunks = 0
        self.closed = False

    def accept_audio(self, chunk: AudioData) -> Sequence[TranscriptUpdate]:
        assert chunk.audio_format == FORMAT
        self.chunks += 1
        if self.chunks == 1:
            return (TranscriptUpdate(0, "تلگرام", TranscriptStatus.PARTIAL, "fa"),)
        if self.chunks == 2:
            return (
                TranscriptUpdate(0, "تلگرام را باز کن", TranscriptStatus.FINAL, "fa"),
            )
        return ()

    def finish(self) -> Sequence[TranscriptUpdate]:
        return ()

    def close(self) -> None:
        self.closed = True


class FakeEngine:
    capabilities = SpeechToTextCapabilities(
        frozenset({ComputeDevice.CPU}), frozenset({"fa"}), True, False
    )

    def __init__(self) -> None:
        self.session = FakeSession()
        self.options: SpeechToTextOptions | None = None

    def open_session(self, options: SpeechToTextOptions) -> FakeSession:
        self.options = options
        return self.session

    def close(self) -> None:
        pass


def write_wav(path: Path, *, channels: int = 1, sample_rate: int = 16000) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(bytes(sample_rate * channels * 2 // 25))


def test_manifest_and_generic_stream_scoring(tmp_path: Path) -> None:
    audio_path = tmp_path / "sample.wav"
    write_wav(audio_path)
    manifest = tmp_path / "corpus.csv"
    with manifest.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(("id", "path", "language", "reference"))
        writer.writerow(("fa-1", audio_path.name, "fa", "تلگرام را باز کن."))

    item = load_corpus(manifest)[0]
    engine = FakeEngine()
    result = evaluate_item(engine, item, realtime=False)

    assert result.transcript == "تلگرام را باز کن"
    assert result.cer == 0
    assert result.first_partial_seconds is not None
    assert result.first_final_seconds is not None
    assert result.audio_seconds > 0
    assert engine.session.closed
    assert engine.options is not None and engine.options.language_hint == "fa"
    summary = summarize((result,))
    assert summary["cer"] == 0
    assert summary["files"] == 1


def test_normalization_and_edit_distance_are_explicit() -> None:
    assert normalize_text("  كايرين‌، باز كُن! ") == "کایرین باز کُن"
    assert edit_distance("abc", "adc") == 1
    assert edit_distance("", "abc") == 3


def test_wav_rate_is_converted_to_engine_format(tmp_path: Path) -> None:
    path = tmp_path / "wideband.wav"
    write_wav(path, sample_rate=48000)
    engine = FakeEngine()

    result = evaluate_item(
        engine,
        load_item(path),
        realtime=False,
    )

    assert result.cer == 0
    assert result.audio_seconds == pytest.approx(0.04, abs=0.002)
    assert engine.session.closed


def load_item(path: Path) -> CorpusItem:
    manifest = path.parent / "corpus.csv"
    manifest.write_text(
        f"id,path,language,reference\nfa-1,{path.name},fa,تلگرام را باز کن\n",
        encoding="utf-8",
    )
    return load_corpus(manifest)[0]


def test_invalid_wav_rejects_before_opening_stt_session(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    write_wav(path, channels=2)
    manifest = tmp_path / "corpus.csv"
    manifest.write_text(
        "id,path,language,reference\nfa-1,stereo.wav,fa,تلگرام\n",
        encoding="utf-8",
    )
    engine = FakeEngine()

    with pytest.raises(ValueError, match="mono 16-bit PCM"):
        evaluate_item(engine, load_corpus(manifest)[0], realtime=False)
    assert engine.options is None


def test_manifest_rejects_missing_audio_and_unscorable_reference(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "corpus.csv"
    manifest.write_text(
        "id,path,language,reference\nfa-1,missing.wav,fa,تلگرام\n",
        encoding="utf-8",
    )
    with pytest.raises(FileNotFoundError, match="audio file is missing"):
        load_corpus(manifest)
    write_wav(tmp_path / "sample.wav")
    manifest.write_text(
        "id,path,language,reference\nfa-1,sample.wav,fa,!!!\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no scorable text"):
        load_corpus(manifest)
