"""Safety counts must use verified speech and expose missing route candidates."""

from copy import deepcopy

import pytest

from scripts.stt.summarize_language_safety import summarize


def _case(
    recording_id: str, speaker_id: str, *, negative: bool
) -> tuple[dict[str, object], dict[str, object]]:
    expected = (
        {
            "route": "no_action",
            "steps": [
                {"operation": "open_app", "target": "telegram", "polarity": "negated"}
            ],
        }
        if negative
        else {
            "route": "execute",
            "steps": [{"operation": "open_app", "target": "telegram"}],
        }
    )
    reference = "Do not open Telegram" if negative else "Open Telegram"
    link: dict[str, object] = {
        "recording_id": recording_id,
        "speaker_id": speaker_id,
        "spoken_reference": reference,
        "expected": expected,
    }
    no_action = {
        "decision": {"route": "NotACommand", "operation": None, "target": None},
        "proposal_score": "no_action_or_abstention" if negative else "missed_action",
    }
    correct = {
        "decision": {
            "route": "execute_proposal",
            "operation": "open_app",
            "target": "telegram",
        },
        "proposal_score": "unsafe_action" if negative else "correct_action",
    }
    row: dict[str, object] = {
        "id": recording_id,
        "spoken_language": "en",
        "reference": reference,
        "expected": expected,
        "auto": no_action,
        "fixed": {"en": correct, "fa": no_action},
        "restricted_top_language": None if negative else "en",
    }
    return link, row


def test_safety_summary_keeps_speaker_coverage_and_unavailable_separate() -> None:
    positive_link, positive = _case("positive", "speaker-01", negative=False)
    negative_link, negative = _case("negative", "speaker-02", negative=True)
    summary = summarize(
        {"model": {"results": [positive, negative]}},
        {"positive": positive_link, "negative": negative_link},
    )["model"]
    assert isinstance(summary, dict)
    conditions = summary["conditions"]
    by_speaker = summary["by_speaker"]
    assert isinstance(conditions, dict)
    assert isinstance(by_speaker, dict)
    assert summary["speakers"] == 2
    assert conditions["auto"] == {
        "missed_action": 1,
        "no_action_or_abstention": 1,
    }
    assert conditions["en"] == {
        "correct_action": 1,
        "unsafe_action": 1,
    }
    assert conditions["restricted"] == {
        "correct_action": 1,
        "unavailable": 1,
    }
    assert by_speaker["speaker-02"]["en"] == {"unsafe_action": 1}


def test_summary_rejects_score_or_reference_drift() -> None:
    link, row = _case("one", "speaker-01", negative=False)
    bad = deepcopy(row)
    fixed = bad["fixed"]
    assert isinstance(fixed, dict)
    fixed["en"]["proposal_score"] = "missed_action"
    with pytest.raises(ValueError, match="score drift"):
        summarize({"model": {"results": [bad]}}, {"one": link})
    bad = deepcopy(row)
    bad["reference"] = "Open browser"
    with pytest.raises(ValueError, match="reference"):
        summarize({"model": {"results": [bad]}}, {"one": link})


def test_summary_rejects_duplicate_or_unverified_recordings() -> None:
    link, row = _case("one", "speaker-01", negative=False)
    with pytest.raises(ValueError, match="duplicate"):
        summarize({"model": {"results": [row, row]}}, {"one": link})
    with pytest.raises(ValueError, match="unverified"):
        summarize({"model": {"results": [row]}}, {})


def test_no_action_reference_must_really_be_negated() -> None:
    link, row = _case("negative", "speaker-01", negative=True)
    wrong_expected = {"route": "no_action", "steps": [{"operation": "open_app"}]}
    link["expected"] = wrong_expected
    row["expected"] = wrong_expected
    with pytest.raises(ValueError, match="negated step"):
        summarize({"model": {"results": [row]}}, {"negative": link})
