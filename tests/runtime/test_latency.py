"""Action latency includes STT and the result without storing speech content."""

from kyrin.actions.models import ActionFeedback, ActionKey, ActionOutcome
from kyrin.audio.activity.speech_activity_monitor import (
    SpeechActivityFrame,
    SpeechState,
    SpeechTransition,
)
from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.commands.models import CommandIntent, CommandKind, ResponseChannel
from kyrin.runtime.latency import SpeechActionLatency
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


def test_speech_action_latency_correlates_final_segment_with_result() -> None:
    times = iter((1_000_000_000, 2_000_000_000, 2_250_000_000))
    tracker = SpeechActionLatency(lambda: next(times))
    frame = SpeechActivityFrame(
        AudioData(b"\0\0", AudioFormat(16000, 1, AudioSampleFormat.INT16)),
        True,
        SpeechState.SPEAKING,
        SpeechTransition.STARTED,
    )
    assert tracker.observe(frame) is None
    assert (
        tracker.observe(TranscriptUpdate(4, "Open Telegram", TranscriptStatus.FINAL))
        is None
    )
    intent = CommandIntent(CommandKind.OPEN_APP, "telegram")
    feedback = ActionFeedback(
        ActionKey(0, 4), intent, ActionOutcome.CONFIRMED, ResponseChannel.TEXT_ONLY
    )
    sample = tracker.observe(feedback)
    assert sample is not None
    assert sample.speech_to_final_ms == 1000
    assert sample.final_to_result_ms == 250
    assert sample.speech_to_result_ms == 1250
    assert tracker.observe(feedback) is None
