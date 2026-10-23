"""Audio files enter the same PCM stream without copying the originals."""

import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from kyrin.audio.file_input import (
    FILE_AUDIO_FORMAT,
    AudioFileInput,
    validate_audio_file,
)


def _wave(path: Path) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * 1600)


@pytest.mark.parametrize(
    ("suffix", "codec"),
    [
        (".wav", None),
        (".mp3", None),
        (".m4a", None),
        (".ogg", "libvorbis"),
        (".ogg", "libopus"),
    ],
)
def test_audio_file_decodes_to_pipeline_format(
    tmp_path: Path, suffix: str, codec: str | None
) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    source = tmp_path / "source.wav"
    _wave(source)
    selected = tmp_path / f"voice{suffix}"
    if suffix == ".wav":
        source.rename(selected)
    else:
        command = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(source)]
        if codec is not None:
            command.extend(["-c:a", codec])
        subprocess.run([*command, str(selected)], check=True)
    chunks = list(AudioFileInput(selected).capture())
    assert chunks
    assert all(chunk.audio_format == FILE_AUDIO_FORMAT for chunk in chunks)
    assert selected.is_file()


def test_reject_unsupported_file(tmp_path: Path) -> None:
    invalid = tmp_path / "script.sh"
    invalid.write_text("echo no")
    with pytest.raises(ValueError, match="WAV, MP3, M4A, or OGG"):
        validate_audio_file(invalid)
