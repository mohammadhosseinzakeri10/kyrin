"""Local model discovery and the isolated worker's file-only inputs."""

import io
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import pytest

from kyrin.stt.backends.omnilingual import (
    CHECKPOINT_BYTES,
    MODEL_NAMES,
    TOKENIZER_NAME,
    _Worker,
    model_files,
)
from kyrin.stt.backends.omnilingual_worker import _cards, _wav
from kyrin.stt.errors import SpeechToTextError


def _model_folder(root: Path, name: str) -> Path:
    folder = root / name
    folder.mkdir()
    (folder / (name.replace("_", "-") + ".pt")).touch()
    (folder / (name.replace("_", "-") + ".pt")).write_bytes(b"test")
    with (folder / (name.replace("_", "-") + ".pt")).open("r+b") as stream:
        stream.truncate(CHECKPOINT_BYTES[name])
    (folder / TOKENIZER_NAME).write_bytes(b"x" * 91481)
    return folder


def test_all_downloaded_variants_have_distinct_model_names(tmp_path: Path) -> None:
    assert len(MODEL_NAMES) == 6
    for name in MODEL_NAMES:
        folder = _model_folder(tmp_path, name)
        checkpoint, tokenizer = model_files(folder)
        assert checkpoint.stat().st_size == CHECKPOINT_BYTES[name]
        assert tokenizer.parent == folder


def test_incomplete_checkpoint_is_rejected(tmp_path: Path) -> None:
    name = MODEL_NAMES[0]
    folder = _model_folder(tmp_path, name)
    checkpoint = folder / (name.replace("_", "-") + ".pt")
    with checkpoint.open("r+b") as stream:
        stream.truncate(100)
    with pytest.raises(ValueError, match="incomplete"):
        model_files(folder)


def test_worker_cards_use_local_files(tmp_path: Path) -> None:
    folder = _model_folder(tmp_path, "omniASR_CTC_300M_v2")
    cards = tmp_path / "cards"
    cards.mkdir()
    assert _cards(folder, cards) == "kyrin_omniASR_CTC_300M_v2"
    card = (cards / "kyrin_omnilingual.yaml").read_text()
    assert (folder / "omniASR-CTC-300M-v2.pt").as_uri() in card
    assert (folder / TOKENIZER_NAME).as_uri() in card
    assert "https://" not in card


def test_worker_wraps_pcm_as_16_khz_mono_wav() -> None:
    pcm = b"\x01\x00\x02\x00"
    with wave.open(io.BytesIO(_wav(pcm)), "rb") as stream:
        assert stream.getframerate() == 16_000
        assert stream.getnchannels() == 1
        assert stream.getsampwidth() == 2
        assert stream.readframes(2) == pcm


def test_worker_times_out_on_partial_reply_and_stops_owned_process() -> None:
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            (
                'import sys,time;sys.stdout.write("{\\"status\\":");'
                "sys.stdout.flush();time.sleep(30)"
            ),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    worker = object.__new__(_Worker)
    worker._process = process
    worker._log = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
    worker._read_buffer = b""
    try:
        with pytest.raises(SpeechToTextError, match="timed out"):
            worker._receive(0.1)
    finally:
        worker.close()

    assert process.poll() is not None


def test_worker_reads_complete_buffered_replies() -> None:
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            (
                'import sys;sys.stdout.write("{\\"status\\":\\"ready\\"}\\n"'
                '+"{\\"status\\":\\"ok\\",\\"text\\":\\"hello\\"}\\n")'
            ),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    worker = object.__new__(_Worker)
    worker._process = process
    worker._log = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
    worker._read_buffer = b""
    try:
        assert worker._receive(1) == {"status": "ready"}
        assert worker._receive(1) == {"status": "ok", "text": "hello"}
    finally:
        worker.close()
