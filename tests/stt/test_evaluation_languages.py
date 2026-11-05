"""Mixed-language totals must not hide the English acceptance measurements."""

from dataclasses import asdict, replace

import pytest

from kyrin.stt.evaluation import (
    EvaluationResult,
    edit_distance,
    normalize_text,
    summarize,
)


def result(
    case_id: str, language: str, reference: str, transcript: str
) -> EvaluationResult:
    expected, actual = normalize_text(reference), normalize_text(transcript)
    edits = edit_distance(expected, actual)
    word_edits = edit_distance(expected.split(), actual.split())
    return EvaluationResult(
        case_id,
        language,
        reference,
        transcript,
        len(expected),
        edits,
        edits / len(expected),
        len(expected.split()),
        word_edits,
        word_edits / len(expected.split()),
        1.0,
        None,
        0.5,
        1.0,
        "cpu",
    )


def test_mixed_report_exposes_weighted_language_scores_without_changing_totals() -> (
    None
):
    rows = (
        result("en-1", "en", "go", "go"),
        result("en-2", "en", "open app", "open map"),
        result("fa-1", "fa", "باز کن", "باز"),
    )
    report = summarize(rows)
    groups = report.get("by_language")
    assert isinstance(groups, dict)
    assert groups["en"] == {
        "files": 2,
        "reference_characters": 10,
        "edit_distance": 2,
        "cer": 0.2,
        "reference_words": 3,
        "word_edit_distance": 1,
        "wer": 1 / 3,
    }
    assert groups["fa"] == {
        "files": 1,
        "reference_characters": 6,
        "edit_distance": 3,
        "cer": 0.5,
        "reference_words": 2,
        "word_edit_distance": 1,
        "wer": 0.5,
    }
    assert report["files"] == 3
    assert report["cer"] == 5 / 16
    assert report["wer"] == 2 / 5
    assert report["results"] == [asdict(row) for row in rows]


def test_single_language_group_matches_existing_top_level_metrics() -> None:
    report = summarize((result("en-1", "en", "open app", "open map"),))
    groups = report.get("by_language")
    assert isinstance(groups, dict)
    assert groups == {
        "en": {k: v for k, v in report.items() if k not in {"results", "by_language"}}
    }


def test_report_retains_distinct_source_locale_labels_and_original_references() -> None:
    english = result("en-1", "en", "Open APP.", "open app")
    regional = replace(english, id="en-us-1", language="en-US")
    report = summarize((english, regional))
    groups = report.get("by_language")
    assert isinstance(groups, dict)
    assert set(groups) == {"en", "en-US"}
    assert report["results"] == [asdict(english), asdict(regional)]


def test_empty_report_is_still_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        summarize(())
