"""Spoken references must stay independent of STT and model outputs."""

import importlib.util
from pathlib import Path

import pytest

from kyrin.stt.evaluation import CorpusItem

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/commands/audit_speech_replay.py"
SPEC = importlib.util.spec_from_file_location("audit_speech_replay", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _fixture(
    *, spoken: str = "Open Telegram", heard: str = "Open browser"
) -> tuple[
    list[dict[str, object]],
    tuple[CorpusItem, ...],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    expected = {
        "route": "execute",
        "steps": [{"operation": "open_app", "target": "telegram"}],
    }
    return (
        [
            {
                "case_id": "speech-01",
                "recording_id": "clip-01",
                "spoken_reference": spoken,
                "expected": expected,
            }
        ],
        (CorpusItem("clip-01", Path("unused.wav"), "en", "Open Telegram"),),
        [
            {
                "id": "speech-01",
                "input_kind": "stt_text",
                "input_text": heard,
                "language": "en",
                "expected": expected,
            }
        ],
        [
            {
                "case_id": "speech-01",
                "model": "local-model",
                "expected_route": "execute",
                "resolved_status": "resolved",
                "correct_resolved_proposal": False,
                "unsafe_resolved_proposal": True,
            }
        ],
    )


def test_valid_but_wrong_stt_app_is_counted_against_spoken_reference() -> None:
    links, clips, cases, decisions = _fixture()
    report = MODULE.audit(links, clips, cases, decisions)
    assert report["models"] == {"local-model": {"unsafe_action": 1}}
    assert report["items"][0]["stt_character_error_rate"] > 0
    assert report["items"][0]["reference"] == "Open Telegram"
    assert report["items"][0]["stt_text"] == "Open browser"


def test_reference_or_expected_label_drift_is_rejected() -> None:
    links, clips, cases, decisions = _fixture()
    links[0]["spoken_reference"] = "Open browser"
    with pytest.raises(ValueError, match="provenance"):
        MODULE.audit(links, clips, cases, decisions)
    links[0]["spoken_reference"] = "Open Telegram"
    cases[0]["expected"] = {"route": "no_action", "steps": []}
    with pytest.raises(ValueError, match="expected label"):
        MODULE.audit(links, clips, cases, decisions)


def test_missing_or_inconsistent_model_decisions_are_rejected() -> None:
    links, clips, cases, decisions = _fixture()
    bad = [dict(decisions[0], unsafe_resolved_proposal=False)]
    with pytest.raises(ValueError, match="inconsistent"):
        MODULE.audit(links, clips, cases, bad)
    with pytest.raises(ValueError, match="duplicate"):
        MODULE.audit(links, clips, cases, decisions * 2)
