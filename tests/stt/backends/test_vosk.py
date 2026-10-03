"""The optional Vosk adapter preserves the common streaming STT contract."""

import importlib
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.stt.backends.vosk import VoskEngine
from kyrin.stt.contracts import SpeechToTextEngine
from kyrin.stt.device import ComputeDevice, DevicePreference, SpeechToTextOptions
from kyrin.stt.errors import DeviceUnavailableError, SpeechToTextError
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


class FakeModel:
    def __init__(self, path: str) -> None:
        self.path = path


class FakeRecognizer:
    def __init__(self, model: FakeModel, sample_rate: int) -> None:
        assert model.path
        assert sample_rate == 16000
        self.partial = ""
        self.result = "open Telegram"

    def AcceptWaveform(self, data: bytes) -> bool:
        if data == b"\x02\x00":
            return True
        if data == b"\x01\x00":
            self.partial = "open"
        elif data == b"\x03\x00":
            self.partial = "go"
        elif data == b"\x04\x00":
            self.partial = "repeat"
        return False

    def PartialResult(self) -> str:
        return json.dumps({"partial": self.partial})

    def Result(self) -> str:
        return json.dumps({"text": self.result})

    def FinalResult(self) -> str:
        return json.dumps({"text": "go home"})


def engine_with_fake_vosk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> VoskEngine:
    module = ModuleType("vosk")
    module.__dict__["Model"] = FakeModel
    module.__dict__["KaldiRecognizer"] = FakeRecognizer
    monkeypatch.setitem(sys.modules, "vosk", module)
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    return VoskEngine(model_dir, language="fa")


def chunk(value: int, audio_format: AudioFormat) -> AudioData:
    return AudioData(bytes((value, 0)), audio_format)


def test_partials_are_revised_and_final_segments_keep_their_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = engine_with_fake_vosk(tmp_path, monkeypatch)
    session = engine.open_session(SpeechToTextOptions())
    audio_format = session.input_format

    assert audio_format == AudioFormat(16000, 1, AudioSampleFormat.INT16)
    assert session.compute_device is ComputeDevice.CPU
    assert session.supports_partial_updates
    assert session.accept_audio(chunk(0, audio_format)) == ()
    assert session.accept_audio(chunk(1, audio_format)) == (
        TranscriptUpdate(0, "open", TranscriptStatus.PARTIAL, "fa"),
    )
    assert session.accept_audio(chunk(1, audio_format)) == ()
    assert session.accept_audio(chunk(2, audio_format)) == (
        TranscriptUpdate(0, "open Telegram", TranscriptStatus.FINAL, "fa"),
    )
    assert session.accept_audio(chunk(3, audio_format)) == (
        TranscriptUpdate(1, "go", TranscriptStatus.PARTIAL, "fa"),
    )
    assert session.finish() == (
        TranscriptUpdate(1, "go home", TranscriptStatus.FINAL, "fa"),
    )
    with pytest.raises(SpeechToTextError, match="finished"):
        session.accept_audio(chunk(0, audio_format))
    session.close()
    engine.close()


def test_cpu_language_and_model_capabilities_are_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine: SpeechToTextEngine = engine_with_fake_vosk(tmp_path, monkeypatch)
    assert engine.capabilities.supported_devices == frozenset({ComputeDevice.CPU})
    assert engine.capabilities.supported_languages == frozenset({"fa"})
    assert engine.capabilities.supports_partial_updates
    assert not engine.capabilities.supports_language_detection

    with pytest.raises(DeviceUnavailableError, match="CPU only"):
        engine.open_session(SpeechToTextOptions(device=DevicePreference.GPU))
    with pytest.raises(SpeechToTextError, match="language is fa"):
        engine.open_session(SpeechToTextOptions(language_hint="en"))
    session = engine.open_session(
        SpeechToTextOptions(device=DevicePreference.CPU, language_hint="fa")
    )
    session.close()
    engine.close()


def test_format_and_lifecycle_errors_do_not_silently_change_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = engine_with_fake_vosk(tmp_path, monkeypatch)
    session = engine.open_session(SpeechToTextOptions())
    with pytest.raises(SpeechToTextError, match="format"):
        session.accept_audio(chunk(1, AudioFormat(8000, 1, AudioSampleFormat.INT16)))
    with pytest.raises(SpeechToTextError, match="sessions"):
        engine.close()
    session.close()
    session.close()
    with pytest.raises(SpeechToTextError, match="closed"):
        session.accept_audio(chunk(1, session.input_format))
    engine.close()
    with pytest.raises(SpeechToTextError, match="closed"):
        engine.open_session(SpeechToTextOptions())


def test_missing_model_is_reported_before_loading_vosk(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="model directory"):
        VoskEngine(tmp_path / "missing", language="fa")


def test_missing_optional_dependency_has_a_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()

    def missing_vosk(name: str) -> ModuleType:
        assert name == "vosk"
        raise ModuleNotFoundError("vosk")

    with monkeypatch.context() as patch:
        patch.setattr(importlib, "import_module", missing_vosk)
        with pytest.raises(SpeechToTextError, match="optional stt-vosk"):
            VoskEngine(model_dir, language="fa")


def test_empty_final_retracts_a_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = engine_with_fake_vosk(tmp_path, monkeypatch)
    session = engine.open_session(SpeechToTextOptions())
    recognizer = session._recognizer
    assert isinstance(recognizer, FakeRecognizer)
    session.accept_audio(chunk(4, session.input_format))
    recognizer.result = ""
    assert session.accept_audio(chunk(2, session.input_format)) == (
        TranscriptUpdate(0, "", TranscriptStatus.FINAL, "fa"),
    )
    session.close()
    engine.close()
