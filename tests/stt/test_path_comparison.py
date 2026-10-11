"""The comparison must expose VAD loss instead of masking it as STT failure."""

import wave
from pathlib import Path

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.stt.device import ComputeDevice, SpeechToTextOptions
from kyrin.stt.evaluation import CorpusItem
from kyrin.stt.path_comparison import WavReplayInput, compare_item
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate

FORMAT = AudioFormat(16_000, 1, AudioSampleFormat.INT16)


class AlwaysSilentDetector:
    input_format = FORMAT
    frames_per_window = 512

    def detect(self, window: AudioData) -> bool:
        return False

    def reset(self) -> None:
        pass


class TurnSession:
    input_format = FORMAT
    compute_device = ComputeDevice.CPU
    supports_partial_updates = False

    def __init__(self) -> None:
        self.active = False
        self.seen = False

    def start_turn(self) -> tuple[TranscriptUpdate, ...]:
        self.active = True
        return ()

    def accept_audio(self, chunk: AudioData) -> tuple[TranscriptUpdate, ...]:
        self.seen |= self.active and bool(chunk.data)
        return ()

    def end_turn(self) -> tuple[TranscriptUpdate, ...]:
        self.active = False
        return (
            (TranscriptUpdate(0, "Open Telegram", TranscriptStatus.FINAL),)
            if self.seen
            else ()
        )

    def finish(self) -> tuple[TranscriptUpdate, ...]:
        return self.end_turn() if self.active else ()

    def close(self) -> None:
        pass


class Engine:
    def open_session(self, options: SpeechToTextOptions) -> TurnSession:
        return TurnSession()

    def close(self) -> None:
        pass


def test_same_wav_distinguishes_direct_stt_from_vad_rejection(tmp_path: Path) -> None:
    path = tmp_path / "spoken.wav"
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(b"\x01\x00" * 6_400)
    report = compare_item(
        Engine(),
        AlwaysSilentDetector,
        CorpusItem("case", path, "en", "Open Telegram"),
        options=SpeechToTextOptions(language_hint="en"),
    )
    assert report["direct"]["transcript"] == "Open Telegram"
    assert report["direct"]["cer"] == 0
    assert report["live"]["transcript"] == ""
    assert report["live"]["speech_starts"] == 0
    assert report["live"]["cer"] == 1


def test_replay_input_rejects_invalid_format(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(b"\x00\x00" * 4)
    try:
        WavReplayInput(path)
    except ValueError as exc:
        assert "mono" in str(exc)
    else:
        raise AssertionError("stereo input must be rejected")
