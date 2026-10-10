"""Semantic proposals must not become executable by construction."""

import json
from pathlib import Path

import pytest

from kyrin.commands.understanding import (
    MeaningStep,
    Polarity,
    ProposedMeaning,
    RequestedOperation,
    UncertaintyKind,
    UnderstandingInput,
    UnderstandingResult,
    UnderstandingStatus,
)

CORPUS = (
    Path(__file__).resolve().parents[2]
    / "datasets"
    / "commands"
    / "semantic_cases.jsonl"
)


def test_ready_meaning_rejects_negation_and_uncertainty() -> None:
    negative = ProposedMeaning(
        (
            MeaningStep(
                RequestedOperation.OPEN_APP, "Telegram", polarity=Polarity.NEGATED
            ),
        )
    )
    with pytest.raises(ValueError, match="negated or uncertain"):
        UnderstandingResult(UnderstandingStatus.READY, (negative,))
    assert (
        UnderstandingResult(UnderstandingStatus.NEGATED, (negative,)).status
        is UnderstandingStatus.NEGATED
    )

    positive = ProposedMeaning((MeaningStep(RequestedOperation.OPEN_APP, "Telegram"),))
    with pytest.raises(ValueError, match="unambiguous"):
        UnderstandingResult(
            UnderstandingStatus.READY,
            (positive,),
            frozenset({UncertaintyKind.TARGET}),
        )
    with pytest.raises(ValueError, match="known negative"):
        UnderstandingResult(UnderstandingStatus.NEGATED, (positive,))


def test_proposals_keep_spoken_names_and_do_not_require_canonical_ids() -> None:
    source = UnderstandingInput("Öffne Telegrum", "de")
    proposal = ProposedMeaning((MeaningStep(RequestedOperation.OPEN_APP, "Telegrum"),))
    result = UnderstandingResult(
        UnderstandingStatus.AMBIGUOUS,
        (proposal,),
        frozenset({UncertaintyKind.TARGET}),
    )
    assert source.text == "Öffne Telegrum"
    assert result.candidates[0].steps[0].target_phrase == "Telegrum"


def test_blank_final_transcript_can_be_classified_as_no_command() -> None:
    source = UnderstandingInput("  ")
    result = UnderstandingResult(UnderstandingStatus.NOT_COMMAND)
    assert source.text == "  "
    assert result.candidates == ()


def test_system_and_chat_targets_are_distinct() -> None:
    assert MeaningStep(RequestedOperation.RESTART_SYSTEM).target_phrase is None
    assert MeaningStep(RequestedOperation.OPEN_CHAT, "Ali").app_phrase is None
    with pytest.raises(ValueError, match="application target"):
        MeaningStep(RequestedOperation.RESTART_SYSTEM, "Telegram")
    with pytest.raises(ValueError, match="only valid for a chat"):
        MeaningStep(RequestedOperation.OPEN_APP, "Telegram", app_phrase="WhatsApp")


def test_reference_corpus_is_labeled_and_covers_critical_decisions() -> None:
    cases = [json.loads(line) for line in CORPUS.read_text().splitlines()]
    assert len({case["id"] for case in cases}) == len(cases)
    assert {case["language"] for case in cases} >= {"en", "fa", "de"}
    assert {case["origin"] for case in cases} == {
        "owner_verified",
        "owner_reported",
        "designed",
    }

    routes = {case["expected"]["route"] for case in cases}
    assert routes == {"execute", "clarify", "confirm", "no_action", "unsupported"}
    for case in cases:
        assert case["input_text"].strip()
        if case.get("scoreable") is False:
            assert case["exclusion_reason"].strip()
        assert case["input_kind"] in {
            "spoken_reference",
            "reported_phrase",
            "stt_text",
            "text_example",
        }
        expected = case["expected"]
        assert isinstance(expected["steps"], list)
        for step in expected["steps"]:
            assert step["operation"] in RequestedOperation
            assert step.get("polarity", "affirmative") in Polarity
        if expected["route"] in {"execute", "confirm"}:
            assert expected["steps"]
            assert all(
                step.get("polarity", "affirmative") == "affirmative"
                for step in expected["steps"]
            )
        if expected["route"] == "no_action":
            assert all(
                step.get("polarity") != "affirmative" for step in expected["steps"]
            )


def test_corpus_does_not_claim_designed_examples_are_recordings() -> None:
    cases = [json.loads(line) for line in CORPUS.read_text().splitlines()]
    assert all(
        case["input_kind"] == "text_example"
        for case in cases
        if case["origin"] == "designed"
    )
    assert all("audio_path" not in case for case in cases)
