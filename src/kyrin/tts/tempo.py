"""Optional pitch-preserving playback speed for engines without native speed."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any

import numpy as np

from kyrin.responses.speech import SpeechSynthesisError

_MAX_AUDIO_BYTES = 16 * 1024 * 1024


def tempo_available() -> bool:
    return shutil.which("ffmpeg") is not None


def adjust_tempo(samples: Any, sample_rate: int, speed: float) -> np.ndarray:
    """Change duration without changing pitch; keep audio in memory only."""
    audio = np.asarray(samples, dtype="<f4").reshape(-1)
    if not 0 < audio.nbytes <= _MAX_AUDIO_BYTES or sample_rate <= 0:
        raise SpeechSynthesisError("TTS audio is empty or too large")
    if speed == 1.0:
        return audio
    if not 0.5 <= speed <= 1.5:
        raise SpeechSynthesisError("TTS speed must be between 0.5 and 1.5")
    binary = shutil.which("ffmpeg")
    if binary is None:
        raise SpeechSynthesisError("FFmpeg is required for Qwen3-TTS speed control")
    try:
        result = subprocess.run(
            [
                binary, "-nostdin", "-hide_banner", "-loglevel", "error",
                "-f", "f32le", "-ar", str(sample_rate), "-ac", "1",
                "-i", "pipe:0", "-filter:a", f"atempo={speed:.2f}",
                "-f", "f32le", "-ar", str(sample_rate), "-ac", "1", "pipe:1",
            ],
            input=audio.tobytes(),
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SpeechSynthesisError("Could not adjust TTS speed") from exc
    if result.returncode != 0 or not 0 < len(result.stdout) <= _MAX_AUDIO_BYTES:
        raise SpeechSynthesisError("Could not adjust TTS speed")
    return np.frombuffer(result.stdout, dtype="<f4").copy()
