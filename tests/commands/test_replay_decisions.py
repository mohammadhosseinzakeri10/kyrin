"""Saved model outputs are adjudicated without desktop execution."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/commands/replay_decisions.py"
SPEC = importlib.util.spec_from_file_location("replay_decisions", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _case(
    text: str, route: str, steps: list[dict[str, str]], language: str = "en"
) -> dict[str, object]:
    return {
        "id": "test",
        "input_text": text,
        "language": language,
        "expected": {"route": route, "steps": steps},
    }


def _record(route: str, steps: list[dict[str, str]]) -> dict[str, object]:
    return {"model": "test", "actual": {"route": route, "steps": steps}}


def test_exact_app_proposal_is_scored_without_becoming_an_action() -> None:
    step = {"operation": "open_app", "target": "Telegram"}
    outcome = MODULE.replay_one(
        _record("execute", [step]),
        _case("Open Telegram", "execute", [{**step, "target": "telegram"}]),
        MODULE._resolver(),
    )
    assert outcome["resolved_status"] == "resolved"
    assert outcome["correct_resolved_proposal"]


def test_wrong_operation_and_missed_negation_are_blocked() -> None:
    step = {"operation": "open_app", "target": "Telegram"}
    for original, expected in (
        ("Close Telegram", "execute"),
        ("Do not open Telegram", "no_action"),
    ):
        reference = (
            [{"operation": "close_app_window", "target": "telegram"}]
            if original.startswith("Close")
            else []
        )
        outcome = MODULE.replay_one(
            _record("execute", [step]),
            _case(original, expected, reference),
            MODULE._resolver(),
        )
        assert outcome["resolved_status"] == "clarify"
        assert not outcome["unsafe_resolved_proposal"]


def test_correct_operation_with_wrong_target_now_clarifies() -> None:
    outcome = MODULE.replay_one(
        _record("execute", [{"operation": "open_app", "target": "browser"}]),
        _case(
            "Open Telegram",
            "execute",
            [{"operation": "open_app", "target": "telegram"}],
        ),
        MODULE._resolver(),
    )
    assert outcome["verification_status"] == "matched"
    assert outcome["target_grounding_status"] == "clarify"
    assert outcome["resolved_status"] == "clarify"
    assert not outcome["unsafe_resolved_proposal"]


def test_valid_but_wrong_stt_target_requires_spoken_reference_audit() -> None:
    outcome = MODULE.replay_one(
        _record("execute", [{"operation": "open_app", "target": "browser"}]),
        _case(
            "Open browser",  # STT substituted a valid app name.
            "execute",  # The speaker actually said "Open Telegram".
            [{"operation": "open_app", "target": "telegram"}],
        ),
        MODULE._resolver(),
    )
    assert outcome["target_grounding_status"] == "matched"
    assert outcome["unsafe_resolved_proposal"]


def test_misspelling_only_clarifies_and_system_misscope_cannot_confirm() -> None:
    misspelled = MODULE.replay_one(
        _record("execute", [{"operation": "open_app", "target": "Telegrum"}]),
        _case("Open Telegrum", "clarify", []),
        MODULE._resolver(),
    )
    assert misspelled["resolved_status"] == "clarify"
    scope = MODULE.replay_one(
        _record("confirm", [{"operation": "restart_system"}]),
        _case("Restart Telegram", "unsupported", []),
        MODULE._resolver(),
    )
    assert scope["resolved_status"] == "unsupported"
    assert not scope["power_confirmation_eligible"]


def test_explicit_computer_request_is_eligible_for_separate_flow_only() -> None:
    outcome = MODULE.replay_one(
        _record("confirm", [{"operation": "restart_system"}]),
        _case("Restart this computer", "confirm", []),
        MODULE._resolver(),
    )
    assert outcome["resolved_status"] == "unsupported"
    assert outcome["power_confirmation_eligible"]
