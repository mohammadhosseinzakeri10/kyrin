"""Playback tempo changes duration without shifting a voiced tone."""

import numpy as np
import pytest

from kyrin.tts.tempo import adjust_tempo, tempo_available


@pytest.mark.skipif(not tempo_available(), reason="FFmpeg is not installed")
def test_tempo_changes_duration_and_preserves_pitch() -> None:
    rate = 24000
    time = np.arange(rate, dtype=np.float32) / rate
    tone = (0.2 * np.sin(2 * np.pi * 440 * time)).astype(np.float32)
    faster = adjust_tempo(tone, rate, 1.25)
    assert 0.7 * rate < len(faster) < 0.9 * rate
    middle = faster[len(faster) // 4 : 3 * len(faster) // 4]
    spectrum = np.abs(np.fft.rfft(middle))
    peak_hz = np.fft.rfftfreq(len(middle), 1 / rate)[np.argmax(spectrum)]
    assert 430 < peak_hz < 450


def test_tempo_one_returns_audio_unchanged() -> None:
    audio = np.array([0.1, -0.2], dtype=np.float32)
    np.testing.assert_array_equal(adjust_tempo(audio, 24000, 1.0), audio)
