"""The evaluation boundary must not inflate success or hide wrong targets."""

import json
from pathlib import Path

import pytest

from kyrin.commands.interpreter import NotACommand
from kyrin.commands.models import CommandContext, PendingCommandClarification
from scripts.commands.evaluate_l04_baseline import (
    CORPUS,
    Case,
    evaluate,
    fixture,
    load_cases,
    replay_case,
    score,
)


def test_checkpoint_resumes_only_whole_cases_with_identical_inputs(
    tmp_path: Path,
) -> None:
    from dataclasses import replace
    from unittest.mock import patch

    cases = load_cases(CORPUS)[:2]
    path = tmp_path / "checkpoint.json"
    original = evaluate(cases, None, None, checkpoint=path)
    with patch(
        "scripts.commands.evaluate_l04_baseline.replay_case",
        side_effect=AssertionError("completed cases must not rerun"),
    ):
        resumed = evaluate(cases, None, None, checkpoint=path)
    assert all(item["reused_completed_case"] for item in resumed)
    assert [item["actual"] for item in original] == [item["actual"] for item in resumed]
    with pytest.raises(ValueError, match="checkpoint"):
        evaluate(cases, None, None, recovery=True, checkpoint=path)
    altered = (replace(cases[0], expected={"route": "no_command"}), cases[1])
    with pytest.raises(ValueError, match="checkpoint"):
        evaluate(altered, None, None, checkpoint=path)


def test_wrong_target_and_operation_count_as_false_proposals() -> None:
    reference = {
        "route": "command",
        "intents": [{"kind": "open_app", "target": "telegram"}],
    }
    wrong_target = {
        "route": "command",
        "intents": [{"kind": "open_app", "target": "school"}],
    }
    result = score(reference, wrong_target)
    assert not result["correct"]
    assert result["wrong_action_proposal"]
    assert result["missed_command"]
    assert not result["false_action_on_noncommand"]
    assert score({"route": "no_command"}, wrong_target)["false_action_on_noncommand"]


def test_partial_preview_is_never_scored_as_final_command() -> None:
    case = next(case for case in load_cases(CORPUS) if case.id == "partial-positive")
    _, rules = fixture()
    result = replay_case(case, rules)
    assert result["actual"] == {"route": "no_command"}
    assert result["score"]["correct"]


@pytest.mark.parametrize(
    "case_id", ["more-expired", "more-other-app", "late-final", "duplicate-final"]
)
def test_context_and_segment_boundaries_are_replayed(case_id: str) -> None:
    case = next(case for case in load_cases(CORPUS) if case.id == case_id)
    _, rules = fixture()
    assert replay_case(case, rules)["actual"] == {"route": "no_command"}


def test_corpus_is_english_first_public_and_grouped() -> None:
    cases = load_cases(CORPUS)
    assert len(cases) == 158
    assert {case.language for case in cases} == {"en"}
    assert all(case.origin == "designed_text_not_audio" for case in cases)
    assert sum(case.model_probe for case in cases) == 16
    for group in {case.group for case in cases}:
        assert len({case.split for case in cases if case.group == group}) == 1


def test_loader_rejects_related_examples_crossing_splits(tmp_path: Path) -> None:
    row = json.loads(CORPUS.read_text().splitlines()[0])
    other = {
        **row,
        "id": "other",
        "split": "audit" if row["split"] == "development" else "development",
    }
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps(row) + "\n" + json.dumps(other) + "\n")
    with pytest.raises(ValueError, match="leaks across splits"):
        load_cases(path)


def test_expected_reference_is_not_fed_to_interpreter() -> None:
    class Capture:
        def interpret(
            self,
            text: str,
            *,
            language: str | None,
            context: CommandContext,
            pending: PendingCommandClarification | None,
        ) -> NotACommand:
            assert text == "some public input"
            return NotACommand()

    case = Case(
        "isolated",
        "isolated",
        "development",
        "ordinary",
        "en",
        "designed_text_not_audio",
        ({"text": "some public input"},),
        {
            "route": "command",
            "intents": [{"kind": "open_app", "target": "SECRET_REFERENCE"}],
        },
        False,
    )
    # The deliberately wrong reference must affect only scoring.
    result = replay_case(case, Capture())
    assert result["actual"] == {"route": "no_command"}
    assert result["score"]["missed_command"]


def test_all_turns_preserve_wrong_intermediate_proposal() -> None:
    from kyrin.commands.interpreter import ReadyCommand
    from kyrin.commands.models import CommandIntent, CommandKind
    from scripts.commands.evaluate_l04_baseline import summarize_turns

    class WrongThenQuiet:
        def interpret(
            self,
            text: str,
            *,
            language: str | None,
            context: CommandContext,
            pending: PendingCommandClarification | None,
        ) -> ReadyCommand | NotACommand:
            return (
                ReadyCommand(CommandIntent(CommandKind.OPEN_APP, "school"))
                if text == "first"
                else NotACommand()
            )

    expected = {"route": "no_command"}
    case = Case(
        "trace",
        "trace",
        "audit",
        "ordinary",
        "en",
        "designed_text_not_audio",
        ({"text": "first"}, {"text": "last"}),
        expected,
        False,
        ({"actual": expected, "response_policy": "none"},) * 2,
    )
    record = replay_case(case, WrongThenQuiet())
    assert record["score"]["correct"]  # historical last-turn metric is preserved
    assert record["turns"][0]["score"]["wrong_action_proposal"]
    assert record["turns"][0]["events"]
    assert summarize_turns([record])["wrong_action_proposal"] == 1


def test_historical_baseline_only_has_known_menu_and_preview_improvements() -> None:
    from copy import deepcopy

    from scripts.commands.evaluate_l04_baseline import summarize

    records = [
        replay_case(case, fixture(case.turns[0].get("window_count"))[1])
        for case in load_cases(CORPUS)
    ]
    frozen = json.loads(CORPUS.with_name("l04_baseline_summary.json").read_text())
    expected = deepcopy(frozen["rules"])
    # Three explicitly negated menu answers now dismiss the menu, as their
    # existing no-question references require. Keep the historical file intact
    # and account explicitly for the newly supported exact app-preview request.
    expected["total"]["asked_or_repeat"] -= 3
    expected["by_category"]["negation"]["asked_or_repeat"] -= 3
    expected["by_split"]["audit"]["asked_or_repeat"] -= 3
    preview = next(record for record in records
                   if record["case_id"] == "show-windows-clean")
    reference = next(case for case in load_cases(CORPUS)
                     if case.id == "show-windows-clean")
    assert preview["actual"] == reference.expected
    assert preview["responses"] == ["choose_window"]
    assert preview["turns"][0]["score"]["selection_ui_response"]
    for section in (
        expected["total"], expected["by_category"]["clean_command"],
        expected["by_split"]["development"],
    ):
        section["correct"] += 1
        section["correct_command"] += 1
        section["missed_command"] -= 1
    assert summarize(records) == expected
    assert sum(len(record["turns"]) for record in records) == 178


def test_destination_and_clarification_are_separate_metrics() -> None:
    from scripts.commands.evaluate_l04_baseline import turn_score

    expected = {
        "route": "command",
        "intents": [{"kind": "open_app", "target": "telegram"}],
    }
    actual = {"route": "command", "intents": [{"kind": "open_app", "target": "school"}]}
    result = turn_score(
        expected, actual, ["repeat_command"], "none", [{"error": "invalid"}]
    )
    assert result["wrong_destination"] and result["wrong_action_proposal"]
    assert result["unexpected_clarification"] and result["model_error"]


def test_decision_slots_are_scored_separately() -> None:
    from scripts.commands.evaluate_l04_baseline import turn_score

    def record(kind: str, target: str, **values: object) -> dict[str, object]:
        return {
            "route": "command",
            "intents": [{"kind": kind, "target": target, **values}],
        }

    result = turn_score(
        record("scroll_up", "browser", scroll_steps=2),
        record("scroll_down", "browser", scroll_steps=3),
        [],
        "none",
        [],
    )
    assert result["wrong_direction"] and result["wrong_scroll_amount"]
    assert not result["wrong_destination"]
    result = turn_score(
        record("visible_control", "Test option", control_state=True),
        record("visible_control", "Test option", control_state=False),
        [],
        "none",
        [],
    )
    assert result["wrong_state"] and not result["wrong_direction"]
    result = turn_score(
        record("telegram_search", "Do not open Telegram"),
        record("telegram_search", "Open Telegram"),
        [],
        "none",
        [],
    )
    assert result["wrong_payload"]
    result = turn_score(
        record("select_app_window", "browser", window_index=1),
        record("select_app_window", "browser", window_index=2),
        [],
        "none",
        [],
    )
    assert result["wrong_window_index"]


def test_audio_transcripts_must_match_frozen_text_before_interpretation() -> None:
    from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate

    case = load_cases(CORPUS)[0]
    _, rules = fixture()
    with pytest.raises(ValueError, match="frozen"):
        replay_case(case, rules, transcripts=())
    with pytest.raises(ValueError, match="frozen"):
        replay_case(
            case,
            rules,
            transcripts=(
                TranscriptUpdate(0, "different", TranscriptStatus.FINAL, "en"),
            ),
        )


def test_requested_window_chooser_is_ui_output_not_extra_semantic_question() -> None:
    from scripts.commands.evaluate_l04_baseline import turn_score

    command = {
        "route": "command",
        "intents": [{"kind": "show_all_windows", "target": "desktop"}],
    }
    result = turn_score(command, command, ["choose_window"], "none", [])
    assert result["correct"]
    assert not result["unexpected_clarification"]
    assert result["selection_ui_response"]
