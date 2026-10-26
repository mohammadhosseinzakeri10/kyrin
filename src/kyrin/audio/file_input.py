"""Decode a local audio file as a finite PCM stream."""

import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from threading import Event

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat

SUPPORTED_AUDIO_SUFFIXES = frozenset({".wav", ".mp3", ".m4a", ".ogg"})
FILE_AUDIO_FORMAT = AudioFormat(16000, 1, AudioSampleFormat.INT16)
MAX_AUDIO_BYTES = 512 * 1024 * 1024


def validate_audio_file(path: Path) -> Path:
    """Accept one existing local file; never interpret its name as a command."""
    if not path.is_absolute() or path.suffix.casefold() not in SUPPORTED_AUDIO_SUFFIXES:
        raise ValueError("Choose a local WAV, MP3, M4A, or OGG audio file")
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.stat().st_size > MAX_AUDIO_BYTES:
        raise ValueError("Audio file exceeds the 512 MB limit")
    if shutil.which("ffmpeg") is None:
        raise FileNotFoundError("ffmpeg is required for WAV, MP3, M4A, and OGG input")
    return path


class AudioFileInput:
    """Decode one file to PCM without a real-time playback delay.

    The same STT and command runtime used by microphone input consumes these
    chunks. The source never copies the original or writes decoded audio.
    """

    audio_format = FILE_AUDIO_FORMAT

    def __init__(self, path: Path, *, chunk_ms: int = 100) -> None:
        self.path = validate_audio_file(path)
        if chunk_ms <= 0:
            raise ValueError("chunk_ms must be positive")
        self._frames_per_chunk = round(FILE_AUDIO_FORMAT.sample_rate * chunk_ms / 1000)
        self._stopped = Event()
        self._process: subprocess.Popen[bytes] | None = None

    def capture(self) -> Iterator[AudioData]:
        process = subprocess.Popen(
            [
                "ffmpeg", "-nostdin", "-v", "error", "-i", str(self.path),
                "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le",
                "-acodec", "pcm_s16le", "pipe:1",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._process = process
        assert process.stdout is not None
        frames = 0
        try:
            while not self._stopped.is_set():
                data = process.stdout.read(self._frames_per_chunk * 2)
                if not data:
                    break
                if len(data) % 2:
                    raise ValueError("Decoded audio has an incomplete PCM frame")
                frames += len(data) // 2
                yield AudioData(data, FILE_AUDIO_FORMAT)
            if not self._stopped.is_set() and process.wait(timeout=5) != 0:
                raise ValueError("The audio file could not be decoded")
            if not self._stopped.is_set() and frames == 0:
                raise ValueError("The audio file contains no decodable sound")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            process.stdout.close()
            self._process = None

    def stop_capture(self) -> None:
        self._stopped.set()
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
