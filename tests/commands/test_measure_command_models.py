"""Benchmark failures and preparation must never masquerade as fresh inference."""

import json
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Any
from unittest.mock import patch

import pytest

from kyrin.operations import OperationStopped
from scripts.commands.evaluate_l04_baseline import CORPUS, load_cases
from scripts.commands.measure_command_models import (
    MemorySampler,
    Recorder,
    bind_runtime,
    cleanup_failed,
    json_default,
    pilot_schedule,
    product_case,
    request_kind,
    run,
    summarize,
)


def test_only_fresh_complete_generation_counts_and_failures_consume_budget() -> None:
    recorder = Recorder(2, monotonic() + 100, Event())
    response = {"model": "test:1", "done": True, "eval_count": 4}
    with patch(
        "scripts.commands.measure_command_models._post_json", return_value=response
    ):
        recorder.transport(
            "http://127.0.0.1:1/api/chat",
            {"model": "test:1", "_debug_render_only": True},
            1,
        )
        assert recorder.total_calls == 0
        recorder.transport("http://127.0.0.1:1/api/chat", {"model": "test:1"}, 1)
    assert recorder.total_calls == 1
    assert recorder.row["requests"][1]["fresh_complete"]
    with patch(
        "scripts.commands.measure_command_models._post_json", side_effect=TimeoutError
    ):
        with pytest.raises(TimeoutError):
            recorder.transport("http://127.0.0.1:1/api/chat", {"model": "test:1"}, 1)
    assert recorder.total_calls == 2
    with pytest.raises(OperationStopped):
        recorder.transport("http://127.0.0.1:1/api/chat", {}, 1)
    # Cleanup is still permitted after exhaustion, with its independent product timeout.
    with patch("scripts.commands.measure_command_models._post_json", return_value={}):
        recorder.transport("http://127.0.0.1:1/api/generate", {"keep_alive": 0}, 3)


@pytest.mark.parametrize(
    "response",
    [
        {"model": "other", "done": True, "eval_count": 4},
        {"model": "test:1", "done": False, "eval_count": 4},
        {"model": "test:1", "done": True, "eval_count": True},
        {"model": "test:1", "done": True, "eval_count": 0},
        {"model": "test:1", "done": True, "eval_count": 4, "done_reason": "load"},
    ],
)
def test_incomplete_or_wrong_model_response_is_not_fresh(
    response: dict[str, Any],
) -> None:
    recorder = Recorder(1, monotonic() + 100, Event())
    with patch(
        "scripts.commands.measure_command_models._post_json", return_value=response
    ):
        recorder.transport("http://127.0.0.1:1/api/chat", {"model": "test:1"}, 1)
    assert not recorder.row["requests"][0]["fresh_complete"]


def test_rules_can_reach_real_gate_only_through_inert_executor() -> None:
    # A rule-resolved command has no runtime request at all.
    with patch("kyrin.commands.ollama_engine.OllamaCommandEngine") as engine:
        case = next(case for case in load_cases(CORPUS) if case.id == "open-clean")
        result = product_case(case, engine)
    engine.understand.assert_not_called()
    assert result["score"]["correct"]
    assert len(result["executor_calls"]) == 1
    assert result["gate_outputs"][0]["outcome"] == "unknown"


def test_summary_keeps_failures_and_does_not_invent_percentiles() -> None:
    rows = []
    for status in ["completed"] * 19 + ["failed", "model_error"]:
        rows.append(
            {
                "phase": "baseline",
                "group_key": "same",
                "status": status,
                "profile_id": "gpu",
                "level": "adapter",
                "temperature": "cold",
                "placement": "gpu",
                "elapsed_ms": 100,
                "stages": [],
                "fresh_complete_inferences": int(status == "completed"),
            }
        )
    result: Any = summarize(rows)
    group = result["groups"]["same"]
    assert group["attempts"] == 21
    assert group["metrics"]["case_ms"]["valid_count"] == 19
    assert group["metrics"]["case_ms"]["p95_ms"] is None
    rows.append(dict(rows[0]))
    result = summarize(rows)
    assert result["groups"]["same"]["metrics"]["case_ms"]["p95_ms"] == 100


def test_cleanup_failure_without_device_report_still_stops_run() -> None:
    assert cleanup_failed({"model": "test:1", "requests": [{"kind": "cleanup"}]})
    assert not cleanup_failed(
        {
            "model": "test:1",
            "requests": [
                {
                    "kind": "cleanup",
                    "response": {
                        "model": "test:1",
                        "done": True,
                        "done_reason": "unload",
                    },
                }
            ],
        }
    )
    assert request_kind({"keep_alive": 0}) == "cleanup"


def test_wall_budget_and_cancellation_stop_before_network() -> None:
    stop = Event()
    for recorder in [
        Recorder(10, monotonic() - 1, Event()),
        Recorder(10, monotonic() + 1, stop),
    ]:
        stop.set()
        with patch("scripts.commands.measure_command_models._post_json") as call:
            with pytest.raises(OperationStopped):
                recorder.transport("http://127.0.0.1:1/api/chat", {}, 1)
        call.assert_not_called()


def test_raw_meaning_uncertainties_survive_json_output() -> None:
    result = json.loads(
        json.dumps(
            {"uncertainties": frozenset({"speech", "target"})}, default=json_default
        )
    )
    assert result == {"uncertainties": ["speech", "target"]}
    with pytest.raises(TypeError, match="unsupported"):
        json.dumps({"unknown": object()}, default=json_default)


def test_pinned_runtime_cannot_be_silently_replaced() -> None:
    profile: dict[str, Any] = {"model": {"runtime_version": "0.31.1"}}
    with pytest.raises(ValueError, match="runtime changed"):
        bind_runtime(profile, "0.32.0")
    assert profile["model"]["runtime_version"] == "0.31.1"
    profile["model"]["runtime_version"] = None
    bind_runtime(profile, "0.31.1")
    assert profile["model"]["runtime_version"] == "0.31.1"


def test_pilot_uses_requested_count_and_both_inputs() -> None:
    cases = load_cases(CORPUS)
    schedule = pilot_schedule(cases, 4)
    assert len(schedule) == 4
    assert [case.category for case in schedule][1::2] == ["negation", "negation"]
    assert schedule[0] == schedule[2] == cases[0]


def test_insufficient_pilot_is_rejected_before_creating_output(tmp_path: Path) -> None:
    from scripts.commands.evaluation_contract import DEFAULT_PLAN

    plan = json.loads(DEFAULT_PLAN.read_text())
    plan["protocol"]["pilot_attempts"] = 1
    output = tmp_path / "run"
    with pytest.raises(ValueError, match="positive/negative"):
        run(plan, output)
    assert not output.exists()


def test_sampler_failure_is_observable_to_run_metadata(tmp_path: Path) -> None:
    sampler = MemorySampler(tmp_path / "missing" / "memory.jsonl", set(), 100)
    sampler.thread.start()
    sampler.thread.join(2)
    assert not sampler.thread.is_alive()
    assert sampler.error is not None and "FileNotFoundError" in sampler.error
    assert sampler.samples == 0


def test_sample_keeps_starting_owner_when_probe_crosses_boundary(
    tmp_path: Path,
) -> None:
    sampler = MemorySampler(tmp_path / "memory.jsonl", set(), 100)
    sampler.attempt = "first"

    def sample(_roots: set[int]) -> dict[str, object]:
        sampler.attempt = "next"
        sampler.stop.set()
        return {"at_ns": 1, "processes": []}

    with patch("scripts.commands.measure_command_models.memory_sample", sample):
        sampler.run()
    row = json.loads(sampler.path.read_text())
    assert row["attempt_id"] == "first"
    assert row["crossed_attempt_boundary"]
    assert row["sample_started_ns"] <= row["sample_finished_ns"]


def test_raw_invalid_model_text_is_preserved_as_evidence() -> None:
    recorder = Recorder(1, monotonic() + 100, Event())
    response = {
        "model": "test:1",
        "done": True,
        "eval_count": 8,
        "response": '{"route":"execute","steps":[]}',
    }
    with patch(
        "scripts.commands.measure_command_models._post_json", return_value=response
    ):
        recorder.transport("http://127.0.0.1:1/api/generate", {"model": "test:1"}, 1)
    assert recorder.row["requests"][0]["raw_response"] == response
    assert recorder.row["requests"][0]["fresh_complete"]
    # Fresh runtime generation is distinct from a valid semantic contract.


@pytest.mark.parametrize("scoped", [True, False])
def test_scope_proposal_and_independent_recovery_are_audited_separately(
    scoped: bool,
) -> None:
    from unittest.mock import MagicMock

    from kyrin.commands.ollama_engine import OllamaCommandEngine
    from kyrin.commands.understanding import (
        MeaningStep,
        ProposedMeaning,
        RequestedOperation,
        UnderstandingResult,
        UnderstandingStatus,
    )

    engine = MagicMock(spec=OllamaCommandEngine)
    step = (
        MeaningStep(RequestedOperation.SHOW_APP_WINDOWS, "Telegram")
        if scoped
        else MeaningStep(RequestedOperation.SHOW_ALL_WINDOWS)
    )
    engine.understand.return_value = UnderstandingResult(
        UnderstandingStatus.READY, (ProposedMeaning((step,)),)
    )
    case = next(c for c in load_cases(CORPUS) if c.id == "show-windows-clean")
    # Exercise fallback auditing even though this clear form now has a rule.
    # Keep the historical input and reference unchanged.
    from kyrin.commands.interpreter import UnrecognizedCommand
    from scripts.commands.evaluate_l04_baseline import fixture

    names, rules = fixture(2)
    with (
        patch("scripts.commands.measure_command_models.fixture",
              return_value=(names, rules)),
        patch.object(rules, "interpret", return_value=UnrecognizedCommand()),
    ):
        result = product_case(case, engine)
    assert result["turns"][0]["model_calls"][0]["status"] == "ready"
    assert result["turns"][0]["score"]["correct"] is scoped
    recovery = [
        g for g in result["guard_decisions"] if g["stage"] == "independent_recovery"
    ]
    assert recovery[0]["outcome"] == (
        "ReadyCommand" if scoped else "UnrecognizedCommand"
    )
    assert bool(result["executor_calls"]) is scoped


def test_selected_levels_are_validated_before_creating_output(tmp_path: Path) -> None:
    from scripts.commands.evaluation_contract import DEFAULT_PLAN

    plan = json.loads(DEFAULT_PLAN.read_text())
    for levels in ([], ["audio_file"], ["adapter", "adapter"]):
        with pytest.raises(ValueError, match="selected levels"):
            run(plan, tmp_path / "uncreated", levels=levels)
        assert not (tmp_path / "uncreated").exists()


def test_state_fixture_capability_is_input_but_reference_never_is() -> None:
    from dataclasses import replace
    from unittest.mock import MagicMock

    from kyrin.commands.ollama_engine import OllamaCommandEngine
    from kyrin.commands.understanding import UnderstandingResult, UnderstandingStatus
    from scripts.commands.measure_command_models import adapter_case

    case = next(c for c in load_cases(CORPUS) if c.id == "visible-clean-clean")
    case = replace(
        case,
        turns=(
            {
                "text": "Enable Test option",
                "scroll_app": "browser",
                "visible_control_enabled": True,
            },
        ),
        expected={
            "route": "command",
            "intents": [
                {
                    "kind": "visible_control",
                    "target": "Test option",
                    "control_state": False,
                }
            ],
        },
        turn_references=(),
    )
    engine = MagicMock(spec=OllamaCommandEngine)
    engine.understand.return_value = UnderstandingResult(
        UnderstandingStatus.NOT_COMMAND
    )
    adapter_case(case, engine)
    assert engine.understand.call_args.kwargs["context"].visible_control_enabled is True
    assert engine.understand.call_args.args[0].text == "Enable Test option"
    engine.reset_mock()
    result = product_case(case, engine)
    engine.understand.assert_not_called()
    assert result["actual"]["intents"][0]["control_state"] is True
    assert result["turns"][0]["score"]["wrong_state"]
