"""Integration tests for the bundled, offline VAD engine."""

import socket

import numpy as np
import pytest

from kyrin.audio.activity.silero_vad import SileroVad
from kyrin.audio.activity.voice_activity_detector import VoiceActivityDetector
from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.audio_framer import AudioFramer


def silence() -> AudioData:
    return AudioData(bytes(512 * 2), SileroVad.input_format)


def test_silero_runs_offline_and_classifies_silence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_connection(*args: object, **kwargs: object) -> None:
        raise AssertionError("VAD tried to access the network")

    with monkeypatch.context() as patch:
        patch.setattr(socket.socket, "connect", reject_connection)
        detector = SileroVad()
        assert detector.detect(silence()) is False


def test_silero_accepts_framer_windows_and_reset_restores_state() -> None:
    detector = SileroVad()
    signal = np.full(1024, 400, dtype=np.int16)
    chunk = AudioData(signal.tobytes(), detector.input_format)
    windows = list(
        AudioFramer(detector.input_format, detector.frames_per_window).frame([chunk])
    )

    assert len(windows) == 2
    first_result = detector.detect(windows[0])
    assert np.any(detector._context)
    detector.detect(windows[1])
    detector.reset()
    assert not np.any(detector._context)
    assert not np.any(detector._state)
    assert detector.detect(windows[0]) == first_result


def test_silero_rejects_incompatible_and_partial_windows() -> None:
    detector = SileroVad()
    wrong_format = AudioFormat(8000, 1, AudioSampleFormat.INT16)

    with pytest.raises(ValueError, match="16000 Hz"):
        detector.detect(AudioData(bytes(1024), wrong_format))
    with pytest.raises(ValueError, match="512 samples"):
        detector.detect(AudioData(bytes(1022), detector.input_format))


@pytest.mark.parametrize("threshold", [float("nan"), -0.1, 0.0, 1.0, 1.1])
def test_silero_rejects_invalid_threshold(threshold: float) -> None:
    with pytest.raises(ValueError, match="threshold"):
        SileroVad(threshold)


def test_vad_contract_accepts_other_engines() -> None:
    class ConstantVad:
        input_format = SileroVad.input_format
        frames_per_window = 512

        def detect(self, window: AudioData) -> bool:
            return True

        def reset(self) -> None:
            pass

    def classify(detector: VoiceActivityDetector, window: AudioData) -> bool:
        return detector.detect(window)

    silero: VoiceActivityDetector = SileroVad()
    assert classify(ConstantVad(), silence()) is True
    assert classify(silero, silence()) is False
