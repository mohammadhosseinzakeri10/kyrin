"""Speaker-scoped captures must never overwrite the established corpus path."""

from pathlib import Path

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


def test_l04_prompts_require_speaker_and_stay_in_private_local_data() -> None:
    from scripts.stt.record_command_corpus import PROJECT_ROOT

    destination = recording_destination("l04-up", "speaker-eval-01")
    assert destination == (
        PROJECT_ROOT / "local-data/l04-recordings/speaker-eval-01/l04-up.wav"
    )
    assert prompt_catalog()["l04-up"][0] == "Scroll up."
    with pytest.raises(ValueError, match="L04 requires"):
        recording_destination("l04-up", None)
    with pytest.raises(ValueError, match="L04 requires"):
        recording_destination("l04-up", "../outside")


def test_l04_recording_refuses_before_importing_audio_runtime() -> None:
    from unittest.mock import patch

    from scripts.stt.record_command_corpus import main

    # The parser must reject missing consent before sounddevice/device discovery.
    with patch("builtins.__import__", wraps=__import__) as imports:
        with pytest.raises(SystemExit) as stopped:
            main(["--id", "l04-up", "--speaker-id", "speaker-eval-01", "--device", "0"])
    assert stopped.value.code == 2
    assert not any(call.args[0] == "sounddevice" for call in imports.call_args_list)


def test_l04_recording_metadata_does_not_invent_verified_words(tmp_path: Path) -> None:
    import json

    from scripts.stt.record_command_corpus import write_l04_reference

    audio = tmp_path / "l04-up.wav"
    audio.write_bytes(b"test fixture, not actual audio")
    write_l04_reference(audio, "l04-up", "speaker-eval-01", "Scroll up.")
    data = json.loads(audio.with_suffix(".reference.json").read_text())
    assert data["intended_prompt"] == "Scroll up."
    assert data["actually_spoken_reference"] is None
    assert data["expected_decision_independently_reviewed"] is None
    assert data["verified_by_speaker"] is False
    assert data["stt_runs"] == []
    with pytest.raises(FileExistsError):
        write_l04_reference(audio, "l04-up", "speaker-eval-01", "different")


def test_l04_retake_keeps_speaker_identity_and_original_file_separate() -> None:
    original = recording_destination("l04-up", "speaker-eval-01")
    retry = recording_destination("l04-up", "speaker-eval-01", take_id="take-02")
    assert retry.parent == original.parent / "take-02"
    assert retry != original
    with pytest.raises(ValueError, match="take ID"):
        recording_destination("l04-up", "speaker-eval-01", take_id="../other")
