"""Replay public L04 text cases through current interpreters without actions.

The catalog, focus and clock are synthetic. No action gate, executor, personal
settings, desktop discovery, microphone or model download is used. Optional
model runs use the production Ollama adapter and an owned loopback server.
"""

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter
from typing import Any
from unittest.mock import patch

from kyrin.commands import coordinator as coordinator_module
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.interpreter import CommandInterpreter
from kyrin.commands.model_interpreter import ModelAssistedInterpreter
from kyrin.commands.models import (
    CommandContext,
    CommandEvent,
    CommandIntent,
    CommandPlanResolution,
    CommandResolution,
    ResponseRequest,
)
from kyrin.commands.ollama_engine import CommandModelError, OllamaCommandEngine
from kyrin.commands.ollama_server import LocalOllamaServer
from kyrin.commands.recovery_candidates import PhoneticCandidateGenerator
from kyrin.commands.speech_recovery import (
    SpeechCommandRecovery,
    SpeechRecoveryInterpreter,
)
from kyrin.commands.understanding import (
    ConfirmationDecision,
    UnderstandingInput,
    UnderstandingResult,
)
from kyrin.desktop.app_catalog import InstalledApp
from kyrin.desktop.spoken_app_names import CatalogSpokenAppResolver
from kyrin.desktop.window_presence import WindowPresence
from kyrin.runtime.voice_control import control_phrase
from kyrin.stt.device import DevicePreference
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from kyrin.system_power.flow import recognized_power_request

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "datasets/commands/l04_cases.jsonl"
STORE = ROOT / "models/local/by-model/command-understanding/ollama"


class FixedCatalog:
    """Only benchmark applications, including a command-like application name."""

    apps = (
        InstalledApp("telegram.desktop", "Telegram"),
        InstalledApp("browser.desktop", "Browser"),
        InstalledApp("school.desktop", "School"),
        InstalledApp("terminal.desktop", "Terminal"),
    )

    def list_apps(self) -> tuple[InstalledApp, ...]:
        return self.apps

    def find_app(self, platform_id: str) -> InstalledApp | None:
        return next((app for app in self.apps if app.platform_id == platform_id), None)


class FixedPresence:
    def __init__(self, count: int) -> None:
        self.windows = count

    def observe(self, app_id: str) -> WindowPresence:
        return WindowPresence.OPEN if self.windows else WindowPresence.CLOSED

    def count(self, app_id: str) -> int:
        return self.windows


def fixture(
    window_count: int | None = None,
) -> tuple[CatalogSpokenAppResolver, DemoCommandInterpreter]:
    names = CatalogSpokenAppResolver(
        FixedCatalog(),
        {
            "telegram.desktop": "telegram",
            "browser.desktop": "browser",
            "school.desktop": "school",
            "terminal.desktop": "terminal",
        },
        {"telegram": ("تلگرام",), "browser": ("مرورگر",)},
    )
    rules = DemoCommandInterpreter(
        names,
        allowed_window_apps=frozenset({"telegram", "browser", "school", "terminal"}),
        allowed_close_apps=frozenset({"telegram", "browser", "school", "terminal"}),
        allowed_scroll_apps=frozenset({"telegram", "browser", "school"}),
        control_any_focused_app=True,
        window_presence=FixedPresence(window_count)
        if window_count is not None
        else None,
        terminal_app_id="terminal",
    )
    return names, rules


def intent_record(intent: CommandIntent) -> dict[str, object]:
    result: dict[str, object] = {"kind": intent.kind.value, "target": intent.target}
    for field in (
        "app",
        "window_index",
        "scroll_steps",
        "scroll_area",
        "control_state",
    ):
        value = getattr(intent, field)
        if value is not None:
            result[field] = value
    if intent.chat_scope != "search":
        result["chat_scope"] = intent.chat_scope
    return result


@dataclass(frozen=True)
class Case:
    id: str
    group: str
    split: str
    category: str
    language: str
    origin: str
    turns: tuple[dict[str, Any], ...]
    expected: dict[str, Any]
    model_probe: bool
    turn_references: tuple[dict[str, Any], ...] = ()


def load_cases(path: Path) -> tuple[Case, ...]:
    cases: list[Case] = []
    ids: set[str] = set()
    groups: dict[str, str] = {}
    reference_path = path.with_name("l04_turn_references.jsonl")
    references = (
        {
            row["case_id"]: tuple(row["turns"])
            for row in (
                json.loads(line) for line in reference_path.read_text().splitlines()
            )
        }
        if reference_path.exists()
        else {}
    )
    for line in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        turns = tuple(item.pop("turns"))
        case = Case(**item, turns=turns, turn_references=references.get(item["id"], ()))
        if len(turns) > 1 and len(case.turn_references) != len(turns):
            raise ValueError("multi-turn case requires explicit turn references")
        for reference in case.turn_references:
            if reference["response_policy"] not in {"none", "allow", "require"}:
                raise ValueError("unknown turn response policy")
            score(reference["actual"], reference["actual"])
        if case.id in ids or not case.turns:
            raise ValueError("duplicate case ID or empty conversation")
        ids.add(case.id)
        if case.split not in {"development", "audit"}:
            raise ValueError("unknown split")
        if groups.setdefault(case.group, case.split) != case.split:
            raise ValueError("related case group leaks across splits")
        if case.expected["route"] not in {"command", "no_command", "control", "power"}:
            raise ValueError("unknown expected route")
        if (case.expected["route"] == "command") != bool(case.expected.get("intents")):
            raise ValueError("command reference must contain exact intents")
        for turn in case.turns:
            if not isinstance(turn["text"], str):
                raise ValueError("input text must be a string")
            TranscriptStatus(turn.get("status", "final"))
        cases.append(case)
    return tuple(cases)


def score(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, bool]:
    correct = expected == actual
    predicted_action = actual["route"] in {"command", "control", "power"}
    return {
        "correct": correct,
        "correct_command": correct and expected["route"] == "command",
        "missed_command": expected["route"] == "command" and not correct,
        "wrong_action_proposal": predicted_action and not correct,
        "false_action_on_noncommand": (
            expected["route"] == "no_command" and predicted_action
        ),
    }


class RecordingModel:
    """Keep raw model meaning separate from the interpreter's final proposal."""

    def __init__(self, engine: OllamaCommandEngine) -> None:
        self.engine = engine
        self.calls: list[dict[str, object]] = []

    def understand(
        self, source: UnderstandingInput, *, context: CommandContext
    ) -> UnderstandingResult:
        started = perf_counter()
        try:
            result = self.engine.understand(source, context=context)
        except CommandModelError as exc:
            causes: list[str] = []
            cause: BaseException | None = exc
            while cause is not None:
                causes.append(f"{type(cause).__name__}: {cause}")
                cause = cause.__cause__
            self.calls.append(
                {
                    "error": str(exc),
                    "error_category": exc.category,
                    "causes": causes,
                    "seconds": perf_counter() - started,
                }
            )
            raise
        self.calls.append(
            {
                "status": result.status.value,
                "candidates": [
                    [
                        {
                            "operation": step.operation.value,
                            "target": step.target_phrase,
                            "app": step.app_phrase,
                            "polarity": step.polarity.value,
                        }
                        for step in candidate.steps
                    ]
                    for candidate in result.candidates
                ],
                "seconds": perf_counter() - started,
            }
        )
        return result

    def classify_confirmation(
        self, source: UnderstandingInput, *, question: str
    ) -> ConfirmationDecision:
        return self.engine.classify_confirmation(source, question=question)


def model_disagrees(call: dict[str, object], expected: dict[str, Any]) -> bool:
    """Audit recorded READY meanings, never send a reference into inference.

    This projection compares operations and supplied names, not execution or
    UI identity. Missing model fields remain subject to production validation.
    """
    if call.get("status") != "ready":
        return False
    if expected["route"] != "command":
        return True
    candidates = call.get("candidates")
    if not isinstance(candidates, list):
        return False
    wanted = expected.get("intents", [])
    for candidate in candidates:
        if not isinstance(candidate, list) or len(candidate) != len(wanted):
            return True
        for step, intent in zip(candidate, wanted, strict=True):
            if not isinstance(step, dict) or step["operation"] != intent["kind"]:
                return True
            for field, reference in (
                ("target", intent["target"]),
                ("app", intent.get("app", "")),
            ):
                value = step.get(field)
                if (
                    value is not None
                    and str(value).casefold() != str(reference).casefold()
                ):
                    return True
    return False


def turn_score(
    expected: dict[str, Any],
    actual: dict[str, Any],
    responses: list[str],
    policy: str,
    model_calls: Sequence[dict[str, object]],
) -> dict[str, bool]:
    result = score(expected, actual)
    clarification = any(
        response not in {"conversation", "ready_for_command"} for response in responses
    )
    wanted = expected.get("intents", [])
    proposed = actual.get("intents", [])
    result.update(
        wrong_destination=bool(
            wanted
            and proposed
            and len(wanted) == len(proposed)
            and [i["kind"] for i in wanted] == [i["kind"] for i in proposed]
            and any(
                any(
                    left.get(key) != right.get(key)
                    for key in ("target", "app", "window_index")
                )
                for left, right in zip(wanted, proposed, strict=True)
            )
        ),
        no_proposal=actual["route"] == "no_command",
        clarification=clarification,
        conversational_reply="conversation" in responses,
        repeat_request="repeat_command" in responses,
        unexpected_clarification=clarification and policy == "none",
        missing_clarification=not clarification and policy == "require",
        model_error=any("error" in call for call in model_calls),
        model_proposal_disagrees=any(
            model_disagrees(call, expected) for call in model_calls
        ),
    )
    return result


def replay_case(
    case: Case,
    interpreter: CommandInterpreter,
    recorder: RecordingModel | None = None,
) -> dict[str, Any]:
    coordinator = CommandCoordinator(interpreter)
    actual: dict[str, Any] = {"route": "no_command"}
    responses: list[str] = []
    trace: list[dict[str, Any]] = []
    for index, turn in enumerate(case.turns):
        text = turn["text"]
        status = TranscriptStatus(turn.get("status", "final"))
        final = status is TranscriptStatus.FINAL
        control = control_phrase(text, active=True) if final else None
        power = recognized_power_request(text) if final else None
        call_offset = len(recorder.calls) if recorder else 0
        events: Sequence[CommandEvent] = ()
        responses = []
        if control is not None:
            actual = {"route": "control", "value": control.value}
        elif power is not None:
            actual = {"route": "power", "value": power.value}
        else:
            with patch(
                "kyrin.commands.coordinator.monotonic", return_value=turn.get("at", 0)
            ):
                events = coordinator.observe(
                    TranscriptUpdate(
                        turn.get("segment", index), text, status, case.language
                    ),
                    observed_active_app=turn.get("active_app"),
                    observed_scroll_app=turn.get("scroll_app"),
                )
            intents: list[CommandIntent] = []
            for event in events:
                if isinstance(event, CommandResolution) and event.intent is not None:
                    intents.append(event.intent)
                elif isinstance(event, CommandPlanResolution):
                    intents.extend(event.plan.steps)
                elif isinstance(event, ResponseRequest):
                    responses.append(event.kind.value)
            actual = (
                {"route": "command", "intents": [intent_record(i) for i in intents]}
                if intents
                else {"route": "no_command"}
            )
        # References are read only after interpretation; never added to input/context.
        reference: dict[str, Any] = (
            case.turn_references[index]
            if case.turn_references
            else {"actual": case.expected, "response_policy": "allow"}
        )
        calls = recorder.calls[call_offset:] if recorder else []
        metrics = turn_score(
            reference["actual"], actual, responses, reference["response_policy"], calls
        )
        metrics["wrong_clarification"] = (
            "responses" in reference and responses != reference["responses"]
        )
        trace.append(
            {
                "turn_index": index,
                "input": dict(turn),
                "expected": reference,
                "actual": actual,
                "responses": list(responses),
                "events": [
                    {"type": type(e).__name__, "data": asdict(e)} for e in events
                ],
                "model_calls": calls,
                "score": metrics,
            }
        )
    return {
        "case_id": case.id,
        "group": case.group,
        "split": case.split,
        "category": case.category,
        "language": case.language,
        "origin": case.origin,
        "expected": case.expected,
        "actual": actual,
        "responses": responses,
        "score": score(case.expected, actual),
        "turns": trace,
    }


def summarize(records: Sequence[dict[str, Any]]) -> dict[str, object]:
    def counts(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
        totals: Counter[str] = Counter(cases=len(rows))
        for row in rows:
            totals["command_cases"] += row["expected"]["route"] == "command"
            totals["noncommand_cases"] += row["expected"]["route"] == "no_command"
            totals["asked_or_repeat"] += bool(row["responses"])
            for name, value in row["score"].items():
                totals[name] += value
        return dict(totals)

    return {
        "total": counts(records),
        "by_category": {
            category: counts([r for r in records if r["category"] == category])
            for category in sorted({r["category"] for r in records})
        },
        "by_split": {
            split: counts([r for r in records if r["split"] == split])
            for split in sorted({r["split"] for r in records})
        },
    }


def summarize_turns(records: Sequence[dict[str, Any]]) -> dict[str, object]:
    totals: Counter[str] = Counter()
    for record in records:
        for turn in record["turns"]:
            totals["turns"] += 1
            totals["command_turns"] += turn["expected"]["actual"]["route"] == "command"
            totals["model_calls"] += len(turn["model_calls"])
            totals["model_errors"] += sum("error" in c for c in turn["model_calls"])
            for key, value in turn["score"].items():
                totals[key] += value
    return dict(totals)


def evaluate(
    cases: Sequence[Case],
    model: str | None,
    url: str | None,
    *,
    recovery: bool = False,
    checkpoint: Path | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    signature = checkpoint_signature(cases, model, recovery)
    saved: dict[str, dict[str, Any]] = {}
    if checkpoint is not None and checkpoint.exists():
        document = json.loads(checkpoint.read_text())
        if document["signature"] != signature:
            raise ValueError("checkpoint source, cases, references or model changed")
        saved = document["records"]
    for case in cases:
        if case.id in saved:
            record = dict(saved[case.id], reused_completed_case=True)
            records.append(record)
            print(case.id, "reused completed case", flush=True)
            continue
        names, rules = fixture(case.turns[0].get("window_count"))
        recorder = None
        recovery_path = (
            SpeechCommandRecovery(
                PhoneticCandidateGenerator(
                    names,
                    allowed_apps=frozenset(
                        {"telegram", "browser", "school", "terminal"}
                    ),
                    chat_apps=frozenset({"telegram"}),
                ),
                rules,
            )
            if recovery
            else None
        )
        interpreter: CommandInterpreter = rules
        if model is not None:
            assert url is not None
            recorder = RecordingModel(
                OllamaCommandEngine(
                    url,
                    model,
                    DevicePreference.CPU,
                    model_store=STORE,
                )
            )
            interpreter = ModelAssistedInterpreter(
                rules,
                recorder,
                names,
                allowed_apps=frozenset({"telegram", "browser", "school"}),
                supported_chat_apps=frozenset({"telegram"}),
                action_review=rules.review_model_action,
                recovery_review=recovery_path.review if recovery_path else None,
            )
        if recovery_path is not None:
            interpreter = SpeechRecoveryInterpreter(interpreter, recovery_path)
        started = perf_counter()
        record = replay_case(case, interpreter, recorder)
        record["wall_seconds"] = perf_counter() - started
        record["model_calls"] = recorder.calls if recorder else []
        records.append(record)
        if checkpoint is not None:
            saved[case.id] = record
            write_checkpoint(checkpoint, signature, saved)
        print(case.id, record["actual"]["route"], flush=True)
    return records


def checkpoint_signature(
    cases: Sequence[Case], model: str | None, recovery: bool
) -> str:
    """References are evaluator metadata only; never forwarded to an interpreter."""
    digest = hashlib.sha256()
    sources = [Path(__file__), *sorted((ROOT / "src").rglob("*.py"))]
    sources += sorted((STORE / "manifests").rglob("*")) if model else []
    for path in sources:
        if path.is_file():
            digest.update(str(path.relative_to(ROOT)).encode())
            digest.update(path.read_bytes())
    digest.update(
        json.dumps(
            {
                "schema": 1,
                "cases": [asdict(case) for case in cases],
                "model": model,
                "recovery": recovery,
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    )
    return digest.hexdigest()


def write_checkpoint(
    path: Path, signature: str, records: dict[str, dict[str, Any]]
) -> None:
    """Replace atomically after each whole case; interrupted cases are rerun."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as output:
        temporary = Path(output.name)
        try:
            json.dump(
                {"signature": signature, "records": records},
                output,
                ensure_ascii=False,
                indent=2,
            )
            output.flush()
            os.fsync(output.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=CORPUS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", choices=("qwen3.5:9b", "gemma4:12b"))
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--recovery", action="store_true")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        help="resume completed cases with identical source and references",
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    cases = load_cases(args.cases)
    if args.probe_only:
        cases = tuple(case for case in cases if case.model_probe)
    if args.model:
        with LocalOllamaServer(STORE, args.model) as url:
            records = evaluate(
                cases,
                args.model,
                url,
                recovery=args.recovery,
                checkpoint=args.checkpoint,
            )
    else:
        records = evaluate(
            cases, None, None, recovery=args.recovery, checkpoint=args.checkpoint
        )
    document = {
        "schema": 2,
        "model": args.model or "rules",
        "recovery": args.recovery,
        "device": "cpu",
        "corpus_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        "turn_reference_sha256": (
            hashlib.sha256(
                args.cases.with_name("l04_turn_references.jsonl").read_bytes()
            ).hexdigest()
            if args.cases.with_name("l04_turn_references.jsonl").exists()
            else None
        ),
        "historical_metric": "summary scores only the last turn; all_turns is separate",
        "source_file": str(Path(coordinator_module.__file__).resolve()),
        "boundary": (
            "coordinator proposals plus pure listening/power recognizers; no execution"
        ),
        "timing_scope": "offline replay only; no STT, audio, desktop or live latency",
        "checkpoint": str(args.checkpoint) if args.checkpoint else None,
        "reused_completed_cases": sum(
            bool(r.get("reused_completed_case")) for r in records
        ),
        "summary": summarize(records),
        "all_turns": summarize_turns(records),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(document, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps(document["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
