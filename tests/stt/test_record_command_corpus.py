"""Speaker-scoped captures must never overwrite the established corpus path."""

import pytest

from scripts.stt.record_command_corpus import (
    DATA_ROOT,
    prompt_catalog,
    recording_destination,
)


def test_speaker_recording_uses_distinct_local_path() -> None:
    legacy = recording_destination("safety-en-01", None)
    second = recording_destination("safety-en-01", "speaker-02")
    assert legacy == DATA_ROOT / "recordings/safety-en-01.wav"
    assert second == DATA_ROOT / "recordings/speakers/speaker-02/safety-en-01.wav"
    assert legacy != second


def test_neutral_prompts_are_available_for_non_command_recordings() -> None:
    catalog = prompt_catalog()
    assert catalog["neutral-en-02"][0] == "Telegram is a messaging app."
    assert catalog["neutral-fa-02"][0] == "تلگرام یک برنامه پیام‌رسان است."


@pytest.mark.parametrize("speaker_id", ["../other", "speaker-02/../x", "owner name"])
def test_invalid_speaker_id_cannot_escape_recording_directory(speaker_id: str) -> None:
    with pytest.raises(ValueError, match="speaker ID"):
        recording_destination("safety-en-01", speaker_id)
