"""Bounded E45 synthetic-text benchmark, with production guards and inert actions.

Run as a module. No microphone, desktop discovery, personal settings or downloads.
The only servers started are owned LocalOllamaServer instances.
"""

import argparse
import json
import math
import os
import signal
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator, Sequence
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime
from http.client import HTTPException
from math import ceil
from pathlib import Path
from threading import Event, Thread
from time import monotonic, perf_counter_ns
from typing import Any, cast
from unittest.mock import patch
from urllib.request import urlopen
from uuid import uuid4

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest, ActionResult
from kyrin.commands.model_interpreter import ModelAssistedInterpreter
from kyrin.commands.models import CommandContext, CommandEvent, CommandKind
from kyrin.commands.ollama_device import (
    CommandDeviceReport,
    DeviceObservation,
    running_device,
)
from kyrin.commands.ollama_engine import (
    CommandModelError,
    CommandTokenBudget,
    OllamaCommandEngine,
    _post_json,
)
from kyrin.commands.ollama_server import LocalOllamaServer
from kyrin.commands.recovery_candidates import PhoneticCandidateGenerator
from kyrin.commands.speech_recovery import (
    SpeechCommandRecovery,
    SpeechRecoveryInterpreter,
)
from kyrin.commands.token_budget import OllamaTokenCounter, local_tokenizer
from kyrin.commands.understanding import UnderstandingInput
from kyrin.model_resources import ModelResources
from kyrin.operations import Operation, OperationStopped, activate, run_process
from kyrin.runtime.command_runtime import dispatch_command_action
from kyrin.stt.device import DevicePreference
from kyrin.stt.transcript import TranscriptUpdate
from kyrin.timing import TimingEvent, TimingScope, timing_scope
from scripts.commands.evaluate_l04_baseline import (
    Case,
    RecordingModel,
    fixture,
    load_cases,
    replay_case,
)
from scripts.commands.evaluation_contract import (
    ROOT,
    environment_snapshot,
    file_hash,
    fingerprint,
    group_key,
    read_json,
    source_snapshot,
    validate_plan,
    write_new,
)

SCHEMA = 1
VERSION = "1"
STORE = ROOT / "models/local/by-model/command-understanding/ollama"


def json_default(value: object) -> object:
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    raise TypeError(f"unsupported benchmark field: {type(value).__name__}")


def get_json(url: str) -> Any:
    with urlopen(url, timeout=3) as response:
        return json.load(response)


def request_kind(payload: dict[str, object]) -> str:
    if payload.get("_debug_render_only") is True:
        return "render"
    if payload.get("keep_alive") == 0:
        return "cleanup"
    return "inference"


class Recorder:
    def __init__(self, max_calls: int, deadline: float, stopped: Event) -> None:
        self.max_calls, self.deadline, self.stopped = max_calls, deadline, stopped
        self.total_calls = 0
        self.row: dict[str, Any] = {}

    def check(self) -> None:
        if self.stopped.is_set() or monotonic() >= self.deadline:
            raise OperationStopped("benchmark stopped or wall budget exhausted")
        if self.total_calls >= self.max_calls:
            raise OperationStopped("benchmark inference attempt budget exhausted")

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        start = perf_counter_ns()
        try:
            yield
        finally:
            end = perf_counter_ns()
            self.row.setdefault("stages", []).append(
                {
                    "name": name,
                    "start_ns": start,
                    "end_ns": end,
                    "ms": (end - start) / 1e6,
                }
            )

    def transport(self, url: str, payload: dict[str, object], timeout: float) -> object:
        kind = request_kind(payload)
        if kind != "cleanup":
            self.check()
        if kind == "inference":
            self.total_calls += 1
        request: dict[str, Any] = {
            "kind": kind,
            "endpoint": url.rsplit("/", 1)[-1],
            "request_sha256": fingerprint(payload),
            "start_ns": perf_counter_ns(),
        }
        self.row.setdefault("requests", []).append(request)
        try:
            with self.stage(kind):
                result = _post_json(url, payload, timeout)
            if isinstance(result, dict):
                request["response"] = {
                    key: result.get(key)
                    for key in (
                        "model",
                        "done",
                        "done_reason",
                        "created_at",
                        "total_duration",
                        "load_duration",
                        "prompt_eval_duration",
                        "eval_duration",
                        "prompt_eval_count",
                        "eval_count",
                    )
                }
                if kind == "inference":
                    # Retain the actual wire response, including invalid JSON text.
                    # This tool accepts public synthetic text and writes locally.
                    request["raw_response"] = result
                    request["fresh_complete"] = (
                        result.get("model") == payload.get("model")
                        and result.get("done") is True
                        and result.get("done_reason") not in {"load", "unload"}
                        and type(result.get("eval_count")) is int
                        and result["eval_count"] > 0
                    )
            return result
        except (OSError, ValueError, RuntimeError, HTTPException) as error:
            request["error"] = type(error).__name__
            raise
        finally:
            request["end_ns"] = perf_counter_ns()

    def probe(self, url: str, model: str, timeout: float) -> DeviceObservation:
        with self.stage("device_observation"):
            return running_device(url, model, timeout)

    def tokenize(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        with self.stage("tokenize"):
            return run_process(*args, **kwargs)


class MeasuredEngine(OllamaCommandEngine):
    def __init__(
        self,
        url: str,
        profile: dict[str, Any],
        recorder: Recorder,
        *,
        resources: ModelResources | None = None,
    ) -> None:
        self.recorder = recorder
        model = profile["model"]["tag"]
        counter = OllamaTokenCounter(url, model, STORE, recorder.transport)
        self.url = url
        super().__init__(
            url,
            model,
            DevicePreference(profile["requested_device"]),
            transport=recorder.transport,
            device_probe=recorder.probe,
            on_device_report=self.report,
            resources=resources if resources is not None else ModelResources(),
            model_store=STORE,
            token_counter=counter,
            token_budget=CommandTokenBudget(
                profile["context_tokens"],
                profile["output_tokens"],
                profile["safety_tokens"],
            ),
        )

    def report(self, report: CommandDeviceReport) -> None:
        self.recorder.row.setdefault("device_reports", []).append(asdict(report))

    def _pack(self, payload: dict[str, object], text: str) -> None:
        with self.recorder.stage("prepare_pack"):
            super()._pack(payload, text)


class InertExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def execute(self, request: ActionRequest) -> ActionResult:
        self.calls.append(
            {"key": asdict(request.key), "intent": asdict(request.intent)}
        )
        return ActionResult(
            request.key,
            ActionOutcome.UNKNOWN,
            error_code="benchmark_inert_no_desktop_effect",
        )


def product_case(
    case: Case,
    engine: OllamaCommandEngine,
    *,
    transcripts: Sequence[TranscriptUpdate] | None = None,
) -> dict[str, Any]:
    names, rules = fixture(case.turns[0].get("window_count"))
    recovery = SpeechCommandRecovery(
        PhoneticCandidateGenerator(
            names,
            allowed_apps=frozenset({"telegram", "browser", "school", "terminal"}),
            chat_apps=frozenset({"telegram"}),
        ),
        rules,
    )
    recorder = RecordingModel(engine)
    assisted = ModelAssistedInterpreter(
        rules,
        recorder,
        names,
        allowed_apps=frozenset({"telegram", "browser", "school"}),
        supported_chat_apps=frozenset({"telegram"}),
        action_review=rules.review_model_action,
        recovery_review=recovery.review,
        allow_visible_control=case.turns[0].get("visible_control_enabled", False),
    )
    interpreter = SpeechRecoveryInterpreter(assisted, recovery)
    allowed = frozenset({"telegram", "browser", "school", "terminal"})
    gate = ActionGate(
        ActionPolicy(
            allowed_apps=allowed,
            allowed_chat_apps=frozenset({"telegram"}),
            allowed_window_apps=allowed,
            allowed_close_apps=allowed,
            allowed_scroll_apps=allowed,
            allow_focused_scroll=True,
            allow_focused_control=True,
            supported_kinds=frozenset(CommandKind),
        )
    )
    executor = InertExecutor()
    outputs: list[object] = []
    guards: list[dict[str, Any]] = []
    turn_index = 0

    def audit(stage: str, call: Callable[..., Any]) -> Callable[..., Any]:
        def review(*args: Any, **kwargs: Any) -> Any:
            decision = call(*args, **kwargs)
            guards.append(
                {
                    "stage": stage,
                    "turn_index": turn_index,
                    "outcome": type(decision).__name__,
                    "decision": asdict(decision) if decision is not None else None,
                }
            )
            return decision

        return review

    assisted._recovery_review = audit("independent_recovery", recovery.review)
    assisted._action_review = audit("action_review", rules.review_model_action)

    def dispatch(events: Sequence[CommandEvent]) -> None:
        nonlocal turn_index
        for event in events:
            outputs.extend(
                asdict(item) for item in dispatch_command_action(event, gate, executor)
            )
        turn_index += 1

    with ExitStack() as stack:
        for name, owner, method in (
            ("operation", assisted._operations, "verify"),
            ("target_resolution", assisted._targets, "resolve"),
            ("target_grounding", assisted._grounder, "verify"),
        ):
            stack.enter_context(
                patch.object(
                    owner, method, side_effect=audit(name, getattr(owner, method))
                )
            )
        result = replay_case(
            case, interpreter, recorder, on_events=dispatch, transcripts=transcripts
        )
    result["guard_decisions"] = guards
    result["gate_outputs"] = outputs
    result["executor_calls"] = executor.calls
    return result


def adapter_case(case: Case, engine: OllamaCommandEngine) -> dict[str, Any]:
    # Deliberately bypass rules, while retaining all adapter budgets and device guards.
    results = []
    for turn in case.turns:
        result = engine.understand(
            UnderstandingInput(turn["text"], case.language),
            context=CommandContext(
                observed_active_app=turn.get("active_app"),
                visible_control_enabled=turn.get("visible_control_enabled", False),
            ),
        )
        results.append(asdict(result))
    return {"meanings": results, "quality_scope": "raw meanings; no final intent score"}


def _process_memory(roots: set[int]) -> list[dict[str, object]]:
    processes: dict[int, tuple[int, str]] = {}
    for path in Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = path.read_text().rsplit(")", 1)[1].split()
            processes[int(path.parent.name)] = (int(fields[1]), fields[19])
        except OSError, ValueError, IndexError:
            continue
    owned = set(roots)
    while (
        children := {pid for pid, (parent, _) in processes.items() if parent in owned}
        - owned
    ):
        owned |= children
    rows = []
    for pid in sorted(owned & processes.keys()):
        row: dict[str, object] = {
            "pid": pid,
            "start_ticks": processes[pid][1],
            "rss_bytes": None,
            "pss_bytes": None,
        }
        try:
            for line in Path(f"/proc/{pid}/smaps_rollup").read_text().splitlines():
                if line.startswith(("Rss:", "Pss:")):
                    field = "rss_bytes" if line.startswith("Rss:") else "pss_bytes"
                    row[field] = int(line.split()[1]) * 1024
        except OSError, ValueError:
            row["unknown_reason"] = "process exited or smaps inaccessible"
        rows.append(row)
    return rows


def _query(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=2, check=False
        )
        return result.stdout if result.returncode == 0 else None
    except OSError, subprocess.SubprocessError:
        return None


def memory_sample(roots: set[int]) -> dict[str, object]:
    rows = _process_memory(roots.copy())
    owned = {row["pid"] for row in rows}
    gpu = _query(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ]
    )
    total = _query(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"]
    )
    vram: int | None = None
    device: list[int] | None = None
    try:
        if gpu is not None:
            vram = sum(
                int(line.split(",")[1]) * 1024**2
                for line in gpu.splitlines()
                if int(line.split(",")[0]) in owned
            )
        if total is not None:
            device = [int(line.strip()) * 1024**2 for line in total.splitlines()]
    except ValueError, IndexError:
        vram = None
        device = None
    return {
        "at_ns": perf_counter_ns(),
        "processes": rows,
        "process_vram_bytes": vram,
        "device_vram_bytes": device,
        "unknown_reason": "probe inaccessible" if vram is None else None,
    }


class MemorySampler:
    def __init__(self, path: Path, roots: set[int], interval_ms: int) -> None:
        self.path, self.roots = path, roots
        self.interval = interval_ms / 1000
        self.attempt: str | None = None
        self.error: str | None = None
        self.samples = 0
        self.stop = Event()
        self.thread = Thread(target=self.run, name="benchmark-memory")

    def run(self) -> None:
        try:
            with self.path.open("x") as output:
                while not self.stop.is_set():
                    attempt = self.attempt
                    start = perf_counter_ns()
                    row = memory_sample(self.roots)
                    row.update(
                        schema_version=SCHEMA,
                        attempt_id=attempt,
                        sample_started_ns=start,
                        sample_finished_ns=perf_counter_ns(),
                        crossed_attempt_boundary=attempt != self.attempt,
                        unit="bytes",
                    )
                    output.write(json.dumps(row) + "\n")
                    output.flush()
                    self.samples += 1
                    self.stop.wait(self.interval)
        except (OSError, ValueError) as error:
            self.error = f"{type(error).__name__}: {error}"


def summarize(rows: list[dict[str, Any]]) -> dict[str, object]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["phase"] == "baseline":
            groups[row["group_key"]].append(row)
    result = {}
    for key, items in groups.items():
        metrics: dict[str, list[float]] = defaultdict(list)
        for row in items:
            # Completion and quality are reported separately. Failed attempts persist.
            if row["status"] != "completed":
                continue
            metrics["case_ms"].append(row["elapsed_ms"])
            for name in {stage["name"] for stage in row["stages"]}:
                metrics[name].append(
                    sum(stage["ms"] for stage in row["stages"] if stage["name"] == name)
                )
        stats = {}
        for metric, values in metrics.items():
            values.sort()
            n = len(values)
            stats[metric] = {
                "valid_count": n,
                "mean_ms": sum(values) / n,
                "min_ms": values[0],
                "max_ms": values[-1],
                "p50_ms": values[ceil(n * 0.50) - 1] if n >= 20 else None,
                "p95_ms": values[ceil(n * 0.95) - 1] if n >= 20 else None,
            }
        result[key] = {
            "profile": items[0]["profile_id"],
            "level": items[0]["level"],
            "temperature": items[0]["temperature"],
            "placement": items[0]["placement"],
            "attempts": len(items),
            "statuses": dict(Counter(row["status"] for row in items)),
            "fresh_complete_inferences": sum(
                row["fresh_complete_inferences"] for row in items
            ),
            "metrics": stats,
        }
    return {
        "schema_version": SCHEMA,
        "groups": result,
        "all_attempts": len(rows),
        "performance_acceptance": None,
    }


def validate_attempt(row: dict[str, Any]) -> None:
    if type(row.get("schema_version")) is not int or row["schema_version"] != SCHEMA:
        raise ValueError("incompatible attempt schema")
    if row.get("status") not in {"completed", "failed", "model_error"}:
        raise ValueError("unfinished attempt cannot enter summaries")
    elapsed = row.get("elapsed_ms")
    if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool):
        raise ValueError("invalid attempt time in milliseconds")
    if not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("invalid attempt time in milliseconds")
    if group_key(row["binding"]) != row["group_key"]:
        raise ValueError("attempt group identity mismatch")
    count = sum(req.get("fresh_complete", False) for req in row["requests"])
    if count != row["fresh_complete_inferences"]:
        raise ValueError("fresh inference evidence mismatch")


def cleanup_failed(row: dict[str, Any]) -> bool:
    for request in row["requests"]:
        if request["kind"] == "cleanup":
            response = request.get("response", {})
            if (
                response.get("done") is not True
                or response.get("done_reason") != "unload"
                or response.get("model") != row["model"]
            ):
                return True
    return False


def bind_runtime(profile: dict[str, Any], runtime: str) -> None:
    """Resolve unknown versions while preserving explicitly pinned versions."""
    expected = profile["model"]["runtime_version"]
    if expected is not None and expected != runtime:
        raise ValueError("runtime changed since the plan")
    profile["model"]["runtime_version"] = runtime


def pilot_schedule(cases: Sequence[Case], attempts: int) -> list[Case]:
    negative = next((case for case in cases if case.category == "negation"), cases[-1])
    return [[cases[0], negative][index % 2] for index in range(attempts)]


def run(
    plan: dict[str, Any],
    output: Path,
    *,
    pilot_only: bool = False,
    levels: Sequence[str] | None = None,
) -> None:
    validate_plan(plan)
    selected_levels = list(levels) if levels is not None else plan["protocol"]["levels"]
    if (
        not selected_levels
        or len(selected_levels) != len(set(selected_levels))
        or not set(selected_levels) <= set(plan["protocol"]["levels"])
    ):
        raise ValueError("selected levels must be a nonempty subset of the plan")
    profile_count = len(plan["protocol"]["profile_order"])
    pilot_count = plan["protocol"]["pilot_attempts"]
    if pilot_count < 2 * profile_count:
        raise ValueError("pilot needs positive/negative attempts for each profile")
    output.mkdir(parents=True, exist_ok=False)
    source = source_snapshot()
    write_new(output / "source-before.json", source)
    write_new(output / "plan.json", plan)
    stopped = Event()
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    protocol = plan["protocol"]
    started = monotonic()
    recorder = Recorder(
        protocol["max_attempts"], started + protocol["max_seconds"], stopped
    )
    profiles = {profile["id"]: profile for profile in plan["profiles"]}
    for name in protocol["profile_order"]:
        if any(
            profiles[name]["composition"][part]["activity"] != "off"
            for part in ("stt", "tts")
        ):
            raise ValueError("use a separately bound audio composition run")
    cases_by_id = {case.id: case for case in load_cases(ROOT / plan["corpus"]["path"])}
    cases = [cases_by_id[name] for name in plan["corpus"]["case_ids"]]
    inventory = environment_snapshot(STORE, ROOT / "nonexistent-benchmark-settings")
    model_fact = cast(dict[str, Any], inventory["models"])
    available = {item["tag"]: item["manifest_sha256"] for item in model_fact["value"]}
    for name in protocol["profile_order"]:
        selected = profiles[name]["model"]
        if selected["tag"] not in available or selected["artifact_sha256"] not in {
            None,
            available[selected["tag"]],
        }:
            raise ValueError("selected artifact is missing or changed since the plan")
    inventory["runtime_environment"] = {
        key: os.environ.get(key)
        for key in (
            "OLLAMA_NUM_PARALLEL",
            "OLLAMA_MAX_LOADED_MODELS",
            "OLLAMA_FLASH_ATTENTION",
            "OLLAMA_CONTEXT_LENGTH",
            "OLLAMA_KV_CACHE_TYPE",
            "CUDA_VISIBLE_DEVICES",
            "OMP_NUM_THREADS",
        )
    }
    tokenizer = local_tokenizer()
    inventory["tokenizer"] = {
        "path": str(tokenizer),
        "sha256": file_hash(tokenizer) if tokenizer else None,
    }
    write_new(output / "inventory.json", inventory)
    metadata: dict[str, Any] = {
        "schema_version": SCHEMA,
        "tool_version": VERSION,
        "run_id": output.name,
        "started_utc": datetime.now(UTC).isoformat(),
        "command": sys.argv,
        "source_sha256": source["sha256"],
        "environment_sha256": fingerprint(inventory),
        "profiles": {},
        "boundary": "synchronous understanding + real gate; no live workers/audio",
        "pilot_only": pilot_only,
        "selected_levels": selected_levels,
    }
    rows: list[dict[str, Any]] = []
    sampler = MemorySampler(
        output / "memory.jsonl", {os.getpid()}, plan["memory"]["interval_ms"]
    )
    sampler.thread.start()
    original_popen = subprocess.Popen
    try:
        for profile_index, profile_id in enumerate(protocol["profile_order"]):
            recorder.check()
            profile = deepcopy(profiles[profile_id])
            model = profile["model"]["tag"]
            profile["model"]["artifact_sha256"] = available[model]
            server = LocalOllamaServer(STORE, model)

            def logged_popen(*args: Any, **kwargs: Any) -> Any:
                command = args[0] if args else kwargs.get("args", ())
                if (
                    len(command) > 1
                    and Path(command[0]).name == "ollama"
                    and command[1] == "serve"
                ):
                    kwargs.update(stdout=server_log, stderr=server_log)
                return original_popen(*args, **kwargs)

            server_started_ns = perf_counter_ns()
            with (
                (output / f"server-{profile_id}.log").open("ab") as server_log,
                patch("kyrin.commands.ollama_server.subprocess.Popen", logged_popen),
                server as url,
            ):
                assert server._process is not None
                server_ready_ns = perf_counter_ns()
                sampler.roots.add(server._process.pid)
                runtime = get_json(url + "/api/version")["version"]
                bind_runtime(profile, runtime)
                profile["status"] = "ready"
                metadata["profiles"][profile_id] = {
                    "profile": profile,
                    "runtime": runtime,
                    "server_pid": server._process.pid,
                    "server_started_ns": server_started_ns,
                    "server_ready_ns": server_ready_ns,
                    "server_startup_ms": (server_ready_ns - server_started_ns) / 1e6,
                }
                engine = MeasuredEngine(url, profile, recorder)
                count = pilot_count // profile_count + int(
                    profile_index < pilot_count % profile_count
                )
                schedule = [
                    ("pilot", "adapter", case, index)
                    for index, case in enumerate(pilot_schedule(cases, count))
                ]
                if not pilot_only:
                    schedule += [
                        ("baseline", level, case, repetition)
                        for level in selected_levels
                        for repetition in range(protocol["repetitions"])
                        for case in cases
                    ]
                for phase, level, case, repetition in schedule:
                    recorder.check()
                    identity = uuid4().hex
                    sampler.attempt = identity
                    row: dict[str, Any] = {
                        "schema_version": SCHEMA,
                        "attempt_id": identity,
                        "run_id": output.name,
                        "profile_id": profile_id,
                        "model": model,
                        "case_id": case.id,
                        "phase": phase,
                        "level": level,
                        "repetition": repetition,
                        "reuse": "fresh",
                        "status": "running",
                        "stages": [],
                        "requests": [],
                        "device_reports": [],
                    }
                    recorder.row = row
                    pre = running_device(url, model, 3)
                    row["residency_before_adapter"] = asdict(pre)
                    row["temperature"] = (
                        "cold" if pre.presence.value == "not_loaded" else "unknown"
                    )
                    # A previous unload may still be pending even if /api/ps
                    # lists the runner. Presence alone cannot certify warmth.
                    timing: list[TimingEvent] = []
                    begin = perf_counter_ns()
                    row["start_ns"] = begin
                    try:
                        with (
                            activate(
                                Operation(recorder.deadline, cancelled=stopped.is_set)
                            ),
                            timing_scope(
                                TimingScope(
                                    output.name, ActionKey(0, len(rows)), timing.append
                                )
                            ),
                            patch(
                                "kyrin.commands.token_budget.run_process",
                                recorder.tokenize,
                            ),
                        ):
                            row["result"] = (
                                adapter_case(case, engine)
                                if level == "adapter"
                                else product_case(case, engine)
                            )
                        result = row["result"]
                        row["status"] = (
                            "model_error"
                            if level == "product_text"
                            and any(
                                turn["score"]["model_error"] for turn in result["turns"]
                            )
                            else "completed"
                        )
                    except (
                        CommandModelError,
                        OperationStopped,
                        OSError,
                        ValueError,
                        RuntimeError,
                    ) as error:
                        row["status"] = "failed"
                        row["error"] = {
                            "type": type(error).__name__,
                            "message": str(error),
                            "category": getattr(error, "category", None),
                        }
                    row["end_ns"] = perf_counter_ns()
                    row["elapsed_ms"] = (row["end_ns"] - begin) / 1e6
                    row["timing"] = [asdict(event) for event in timing]
                    row["fresh_complete_inferences"] = sum(
                        req.get("fresh_complete", False) for req in row["requests"]
                    )
                    row["placement"] = (
                        row["device_reports"][-1]["observation"]["placement"]
                        if row["device_reports"]
                        else "unknown"
                    )
                    row["post_cleanup"] = asdict(running_device(url, model, 3))
                    binding = {
                        "schema_version": 1,
                        "tool_version": "1",
                        "plan_sha256": fingerprint(plan),
                        "profile_sha256": fingerprint(profile),
                        "source_sha256": source["sha256"],
                        "environment_sha256": fingerprint(inventory),
                        "corpus_sha256": plan["corpus"]["sha256"],
                        "references_sha256": plan["corpus"]["references_sha256"],
                        "case_order": plan["corpus"]["case_ids"],
                        "level": level,
                        "temperature": row["temperature"],
                        "service_state": "started",
                        "placement": row["placement"],
                        "reuse": "fresh",
                    }
                    row["group_key"] = group_key(binding)
                    row["binding"] = binding
                    row["server_returncode"] = server._process.poll()
                    validate_attempt(row)
                    rows.append(row)
                    with (output / "attempts.jsonl").open("a") as raw:
                        raw.write(
                            json.dumps(row, ensure_ascii=False, default=json_default)
                            + "\n"
                        )
                    print(
                        json.dumps(
                            {
                                key: row[key]
                                for key in (
                                    "profile_id",
                                    "case_id",
                                    "level",
                                    "phase",
                                    "status",
                                    "elapsed_ms",
                                    "fresh_complete_inferences",
                                    "placement",
                                )
                            }
                        ),
                        flush=True,
                    )
                    if cleanup_failed(row) or any(
                        report["cleanup"] == "unconfirmed"
                        for report in row["device_reports"]
                    ):
                        raise OperationStopped("cleanup unconfirmed; stop this run")
                sampler.roots.discard(server._process.pid)
    except (OperationStopped, CommandModelError, OSError, ValueError) as error:
        metadata["stop_reason"] = f"{type(error).__name__}: {error}"
    finally:
        sampler.attempt = None
        sampler.stop.set()
        sampler.thread.join()
        metadata.update(
            elapsed_seconds=monotonic() - started,
            inference_attempts=recorder.total_calls,
            memory_sampler_error=sampler.error,
            memory_samples=sampler.samples,
            source_after=source_snapshot(),
        )
        metadata["source_unchanged"] = (
            source["sha256"] == metadata["source_after"]["sha256"]
        )
        write_new(output / "run.json", metadata)
        write_new(output / "summary.json", summarize(rows))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pilot-only", action="store_true")
    parser.add_argument(
        "--level",
        action="append",
        choices=("adapter", "product_text"),
        help="execute only a named plan level; output remains a fresh separate run",
    )
    args = parser.parse_args()
    plan = validate_plan(read_json(args.plan))
    if not args.output.resolve().is_relative_to((ROOT / "local-data").resolve()):
        parser.error("output must remain in project local-data")
    if local_tokenizer() is None:
        parser.error("set KYRIN_COMMAND_TOKENIZER to the existing local executable")
    run(plan, args.output, pilot_only=args.pilot_only, levels=args.level)


if __name__ == "__main__":
    main()
