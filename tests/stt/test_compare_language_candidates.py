"""Restricted language scores must remain diagnostics, never authorization."""

from pathlib import Path

import pytest

from kyrin.stt.evaluation import CorpusItem
from scripts.stt.compare_language_candidates import (
    inspect_item,
    interpret_without_action,
    restricted_winner,
    score_proposal,
)


def test_restricted_winner_does_not_use_reference_language() -> None:
    winner, score, margin = restricted_winner(
        {"el": 0.35, "en": 0.06, "fa": 0.02}, ("en", "fa")
    )
    assert winner == "en"
    assert score == pytest.approx(0.06)
    assert margin == pytest.approx(0.04)


def test_missing_candidate_probability_is_rejected() -> None:
    with pytest.raises(ValueError, match="missing"):
        restricted_winner({"en": 0.5}, ("en", "fa"))


def test_nonfinite_probability_is_rejected() -> None:
    with pytest.raises(ValueError, match="finite"):
        restricted_winner({"en": float("nan"), "fa": 0.2}, ("en", "fa"))


def test_wrong_language_decoding_cannot_be_scored_as_correct_action() -> None:
    expected = {
        "route": "execute",
        "steps": [{"operation": "open_app", "target": "browser"}],
    }
    assert (
        score_proposal(interpret_without_action("Open Telegram", "en"), expected)
        == "unsafe_action"
    )
    assert (
        score_proposal(interpret_without_action("مرورگر را باز کن", "fa"), expected)
        == "correct_action"
    )


def test_negated_reference_distinguishes_abstention_from_unsafe_action() -> None:
    expected = {
        "route": "no_action",
        "steps": [
            {"operation": "open_app", "target": "telegram", "polarity": "negated"}
        ],
    }
    assert (
        score_proposal(interpret_without_action("unreadable text", "en"), expected)
        == "no_action_or_abstention"
    )
    assert (
        score_proposal(interpret_without_action("Open Telegram", "en"), expected)
        == "unsafe_action"
    )


def test_same_hints_are_sent_to_every_decode_without_using_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []

    class FakeServer:
        def _request_inference(
            self,
            pcm: bytes,
            language: str,
            response_format: str,
            hints: tuple[str, ...],
        ) -> dict[str, object]:
            calls.append((language, hints))
            return {
                "text": "Open Telegram",
                "language": "english",
                "language_probabilities": {"en": 0.8, "fa": 0.1},
            }

        def transcribe(
            self, pcm: bytes, language: str, *, hints: tuple[str, ...]
        ) -> str:
            calls.append((language, hints))
            return "Open Telegram"

    monkeypatch.setattr(
        "scripts.stt.compare_language_candidates.read_pcm16_mono", lambda _: b"audio"
    )
    item = CorpusItem("one", Path("unused.wav"), "en", "Open Telegram")
    expected = {
        "route": "execute",
        "steps": [{"operation": "open_app", "target": "telegram"}],
    }
    report = inspect_item(
        FakeServer(), item, expected, ("en", "fa"), ("مرورگر", "تلگرام")
    )
    assert calls == [
        ("auto", ("مرورگر", "تلگرام")),
        ("en", ("مرورگر", "تلگرام")),
        ("fa", ("مرورگر", "تلگرام")),
    ]
    assert report["auto"]["proposal_score"] == "correct_action"
