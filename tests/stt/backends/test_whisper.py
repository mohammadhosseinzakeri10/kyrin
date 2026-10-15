"""A turn-aware Whisper session never authorizes provisional text."""

import pytest

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.stt.backends.whisper import WhisperEngine, WhisperSession
from kyrin.stt.backends.whisper_server import WhisperResult
from kyrin.stt.device import ComputeDevice, DevicePreference, SpeechToTextOptions
from kyrin.stt.errors import DeviceUnavailableError, SpeechToTextError
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate

FORMAT = AudioFormat(16_000, 1, AudioSampleFormat.INT16)


def audio(seconds: float) -> AudioData:
    return AudioData(bytes(round(seconds * 32_000)), FORMAT)


def test_partial_is_replaced_by_final_and_listening_continues() -> None:
    responses = iter(["Open Telegram", "Do not open Telegram", "Open Chrome"])
    calls: list[int] = []
    closed: list[bool] = []

    def infer(pcm: bytes, language: str) -> str:
        assert language == "en"
        calls.append(len(pcm))
        return next(responses)

    session = WhisperSession(infer, "en", lambda: closed.append(True))
    session.accept_audio(audio(0.2))
    session.start_turn()
    partial = session.accept_audio(audio(1.5))
    assert len(partial) == 1
    assert partial[0].status is TranscriptStatus.PARTIAL
    assert partial[0].text == "Open Telegram"
    final = session.end_turn()
    assert len(final) == 1
    assert final[0].status is TranscriptStatus.FINAL
    assert final[0].text == "Do not open Telegram"
    assert final[0].segment_id == partial[0].segment_id

    session.accept_audio(audio(0.2))
    session.start_turn()
    second = session.end_turn()
    assert second[0].segment_id == 1
    assert second[0].text == "Open Chrome"
    assert len(calls) == 3
    assert session.finish() == ()
    session.close()
    session.close()
    assert closed == [True]


def test_overlong_turn_retracts_partial_and_never_executes_truncated_text() -> None:
    calls = 0

    def infer(pcm: bytes, language: str) -> str:
        nonlocal calls
        calls += 1
        return "Open Telegram"

    session = WhisperSession(
        infer,
        "en",
        lambda: None,
        maximum_turn_seconds=2,
        preview_window_seconds=2,
    )
    session.start_turn()
    assert session.accept_audio(audio(1.5))[0].status is TranscriptStatus.PARTIAL
    session.accept_audio(audio(1))
    final = session.end_turn()
    assert final[0].text == ""
    assert final[0].status is TranscriptStatus.FINAL
    assert calls == 1


def test_preroll_does_not_trigger_a_wasted_preview_for_short_speech() -> None:
    calls: list[int] = []

    def infer(pcm: bytes, language: str) -> str:
        calls.append(len(pcm))
        return "Open Telegram"

    session = WhisperSession(infer, "en", lambda: None)
    session.accept_audio(audio(0.5))
    session.start_turn()
    assert session.accept_audio(audio(1.2)) == ()
    assert calls == []
    assert session.end_turn()[0].text == "Open Telegram"
    assert len(calls) == 1


def test_wrong_format_and_closed_session_fail_explicitly() -> None:
    session = WhisperSession(lambda pcm, language: "", "en", lambda: None)
    wrong = AudioData(bytes(160), AudioFormat(8000, 1, AudioSampleFormat.INT16))
    with pytest.raises(SpeechToTextError, match="format"):
        session.accept_audio(wrong)
    session.close()
    with pytest.raises(SpeechToTextError, match="closed"):
        session.start_turn()


def test_engine_respects_device_and_releases_preloaded_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[bool] = []

    class FakeServer:
        def __init__(
            self,
            server: str,
            model: str,
            *,
            threads: int,
            compute_device: ComputeDevice,
        ) -> None:
            assert (server, model, threads, compute_device) == (
                "server",
                "model",
                2,
                ComputeDevice.CPU,
            )

        def transcribe(self, pcm: bytes, language: str) -> str:
            return "Open Telegram"

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr("kyrin.stt.backends.whisper.WhisperCppServer", FakeServer)
    engine = WhisperEngine("server", "model", threads=2)
    with pytest.raises(DeviceUnavailableError):
        engine.open_session(SpeechToTextOptions(device=DevicePreference.GPU))
    with pytest.raises(SpeechToTextError, match="language"):
        engine.open_session(SpeechToTextOptions(language_hint="fa"))
    session = engine.open_session(SpeechToTextOptions(language_hint="en"))
    with pytest.raises(SpeechToTextError, match="sessions"):
        engine.close()
    session.close()
    engine.close()
    engine.close()
    assert closed == [True]


def test_cancel_active_inference_stops_owned_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[bool] = []

    class FakeServer:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def transcribe(self, pcm: bytes, language: str) -> str:
            return ""

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr("kyrin.stt.backends.whisper.WhisperCppServer", FakeServer)
    engine = WhisperEngine("server", "model")
    session = engine.open_session(SpeechToTextOptions())

    engine.cancel_pending_inference()
    session.close()
    engine.close()

    assert closed == [True]


def test_gpu_engine_reports_gpu_and_rejects_cpu_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeServer:
        def __init__(self, *args: object, **kwargs: object) -> None:
            assert kwargs["compute_device"] is ComputeDevice.GPU

        def transcribe(self, pcm: bytes, language: str) -> str:
            return "Open Telegram"

        def close(self) -> None:
            pass

    monkeypatch.setattr("kyrin.stt.backends.whisper.WhisperCppServer", FakeServer)
    engine = WhisperEngine("server", "model", compute_device=ComputeDevice.GPU)
    assert engine.capabilities.supported_devices == frozenset({ComputeDevice.GPU})
    with pytest.raises(DeviceUnavailableError, match="running on GPU"):
        engine.open_session(SpeechToTextOptions(device=DevicePreference.CPU))
    session = engine.open_session(SpeechToTextOptions(device=DevicePreference.GPU))
    assert session.compute_device is ComputeDevice.GPU
    session.close()
    engine.close()


def test_auto_language_uses_detected_code_on_final_transcript() -> None:
    session = WhisperSession(
        lambda pcm, language: WhisperResult("تلگرام را باز کن", "fa"),
        "auto",
        lambda: None,
    )
    session.start_turn()
    result = session.end_turn()
    assert result == (
        TranscriptUpdate(0, "تلگرام را باز کن", TranscriptStatus.FINAL, "fa"),
    )


def test_auto_engine_uses_multilingual_server_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeServer:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def transcribe_auto(self, pcm: bytes) -> WhisperResult:
            return WhisperResult("Open Telegram", "en")

        def close(self) -> None:
            pass

    monkeypatch.setattr("kyrin.stt.backends.whisper.WhisperCppServer", FakeServer)
    engine = WhisperEngine("server", "model", language="auto")
    assert engine.capabilities.supports_language_detection
    session = engine.open_session(SpeechToTextOptions(language_hint="auto"))
    session.start_turn()
    assert session.end_turn()[0].language == "en"
    session.close()
    engine.close()


def test_whisper_session_passes_optional_hints_without_changing_other_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []

    class FakeServer:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def transcribe(
            self, pcm: bytes, language: str, *, hints: tuple[str, ...] = ()
        ) -> str:
            calls.append((language, hints))
            return "مرورگر را باز نکن"

        def close(self) -> None:
            pass

    monkeypatch.setattr("kyrin.stt.backends.whisper.WhisperCppServer", FakeServer)
    engine = WhisperEngine("server", "model", language="fa")
    assert engine.capabilities.supports_vocabulary_hints
    for hints in (("مرورگر",), ()):
        session = engine.open_session(SpeechToTextOptions(vocabulary_hints=hints))
        session.start_turn()
        assert session.end_turn()[0].text == "مرورگر را باز نکن"
        session.close()
    engine.close()
    assert calls == [("fa", ("مرورگر",)), ("fa", ())]
