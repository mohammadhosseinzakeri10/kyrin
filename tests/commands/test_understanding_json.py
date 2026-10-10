"""Malformed or internally contradictory model JSON cannot become a proposal."""

import pytest

from kyrin.commands.understanding import (
    RequestedOperation,
    UncertaintyKind,
    UnderstandingStatus,
)
from kyrin.commands.understanding_json import decode_model_response


def test_execute_preserves_spoken_target_and_order() -> None:
    result = decode_model_response(
        {
            "route": "execute",
            "steps": [
                {"operation": "open_app", "target": "Telegram"},
                {"operation": "open_chat", "target": "Ali", "app": "Telegram"},
            ],
        }
    )
    assert result.status is UnderstandingStatus.READY
    assert result.candidates[0].steps[0].target_phrase == "Telegram"
    assert result.candidates[0].steps[1].app_phrase == "Telegram"


def test_redundant_app_field_is_discarded_only_when_it_matches_target() -> None:
    result = decode_model_response(
        {
            "route": "execute",
            "steps": [
                {"operation": "open_app", "target": "Telegram", "app": "telegram"}
            ],
        }
    )
    assert result.candidates[0].steps[0].app_phrase is None


def test_negation_and_clarification_remain_non_executable() -> None:
    negative = decode_model_response(
        {
            "route": "no_action",
            "steps": [
                {"operation": "open_app", "target": "Telegram", "polarity": "negated"}
            ],
        }
    )
    assert negative.status is UnderstandingStatus.NEGATED
    ambiguous = decode_model_response(
        {"route": "clarify", "steps": [], "uncertainty": "target"}
    )
    assert ambiguous.uncertainties == frozenset({UncertaintyKind.TARGET})
    assert (
        decode_model_response({"route": "no_action", "steps": []}).status
        is UnderstandingStatus.NOT_COMMAND
    )


def test_system_confirmation_is_only_a_proposal() -> None:
    result = decode_model_response(
        {"route": "confirm", "steps": [{"operation": "restart_system"}]}
    )
    assert result.candidates[0].steps[0].operation is RequestedOperation.RESTART_SYSTEM


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"route": [], "steps": []},
        {"route": "execute", "steps": []},
        {
            "route": "execute",
            "steps": [{"operation": "open_app", "target": "Telegram"}],
            "uncertainty": "target",
        },
        {
            "route": "execute",
            "steps": [
                {"operation": "open_app", "target": "Telegram", "polarity": "negated"}
            ],
        },
        {"route": "execute", "steps": [{"operation": "restart_system"}]},
        {
            "route": "confirm",
            "steps": [{"operation": "restart_system", "target": "Telegram"}],
        },
        {
            "route": "confirm",
            "steps": [
                {"operation": "restart_system"},
                {"operation": "power_off_system"},
            ],
        },
        {
            "route": "no_action",
            "steps": [{"operation": "open_app", "target": "Telegram"}],
        },
        {
            "route": "unsupported",
            "steps": [{"operation": "open_app", "target": "Telegram"}],
        },
        {
            "route": "execute",
            "steps": [
                {"operation": "open_app", "target": "Telegram", "app": "WhatsApp"}
            ],
        },
        {
            "route": "execute",
            "steps": [{"operation": "open_app", "target": "Telegram"}] * 4,
        },
    ],
)
def test_invalid_responses_fail_closed(payload: object) -> None:
    with pytest.raises(ValueError):
        decode_model_response(payload)
