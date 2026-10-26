"""Deterministic bounded same-audio ownership; no microphone or model."""

from threading import Event, Thread

import pytest

from kyrin.stt.audio_recovery import AudioRecoveryPolicy, RetainedAudio
from kyrin.stt.evidence import SpeechHypothesis


def test_same_pcm_single_attempt_and_release() -> None:
    seen: list[bytes] = []

    def infer(pcm: bytes) -> SpeechHypothesis:
        seen.append(pcm)
        return SpeechHypothesis("open Telegram", "fake", "same_audio_reprocess")

    owner = RetainedAudio(b"\x01\x00" * 4, infer, AudioRecoveryPolicy())
    assert owner.retained_bytes == 8
    assert owner.reprocess() is not None
    assert owner.attempts == 1 and owner.retained_bytes == 0
    assert owner.reprocess() is None
    assert seen == [b"\x01\x00" * 4]


def test_expired_or_cancelled_audio_is_never_reprocessed() -> None:
    clock = [0.0]

    def unexpected(pcm: bytes) -> None:
        pytest.fail("expired/cancelled audio must not enter inference")

    owner = RetainedAudio(
        b"\x00\x00",
        unexpected,
        AudioRecoveryPolicy(retention_seconds=1),
        clock=lambda: clock[0],
    )
    clock[0] = 2
    assert owner.reprocess() is None and owner.retained_bytes == 0
    owner = RetainedAudio(b"\x00\x00", unexpected, AudioRecoveryPolicy())
    owner.close()
    assert owner.reprocess() is None


def test_close_does_not_wait_for_native_inference_and_discards_late_result() -> None:
    started, release = Event(), Event()
    results: list[SpeechHypothesis | None] = []

    def infer(pcm: bytes) -> SpeechHypothesis:
        started.set()
        assert release.wait(2)
        return SpeechHypothesis("open Telegram", "fake", "same_audio_reprocess")

    owner = RetainedAudio(b"\x00\x00", infer, AudioRecoveryPolicy())
    thread = Thread(target=lambda: results.append(owner.reprocess()))
    thread.start()
    try:
        assert started.wait(1)
        owner.close()
        assert owner.retained_bytes == 0
    finally:
        release.set()
        thread.join(2)
    assert not thread.is_alive() and results == [None]


def test_whole_audio_must_fit_and_invalid_budgets_fail() -> None:
    with pytest.raises(ValueError, match="whole aligned"):
        RetainedAudio(b"1234", lambda pcm: None, AudioRecoveryPolicy(max_pcm_bytes=2))
    for options in (
        {"max_pcm_bytes": 3},
        {"retention_seconds": float("nan")},
        {"max_reprocess": -1},
    ):
        with pytest.raises(ValueError):
            AudioRecoveryPolicy(**options)
