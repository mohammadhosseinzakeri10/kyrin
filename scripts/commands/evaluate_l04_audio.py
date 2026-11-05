"""Replay the eight consented L04 WAVs with existing local models and inert actions."""

import argparse
import json
import signal
from dataclasses import asdict, replace
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Any
from unittest.mock import patch

from kyrin.audio.audio_data import AudioData
from kyrin.commands.models import CommandContext
from kyrin.commands.ollama_server import LocalOllamaServer
from kyrin.commands.understanding import UnderstandingInput
from kyrin.model_resources import ModelResources
from kyrin.operations import Operation, activate
from kyrin.stt.backends.whisper import WhisperEngine
from kyrin.stt.contracts import TurnAwareSpeechToTextSession
from kyrin.stt.device import ComputeDevice, SpeechToTextOptions
from kyrin.stt.errors import SpeechToTextError
from kyrin.stt.resources import ManagedSttEngine
from scripts.commands.evaluate_l04_baseline import Case
from scripts.commands.evaluation_contract import (
    ROOT,
    environment_snapshot,
    file_hash,
    fingerprint,
    read_json,
    source_snapshot,
    validate_plan,
    write_new,
)
from scripts.commands.measure_command_models import (
    STORE,
    MeasuredEngine,
    Recorder,
    bind_runtime,
    cleanup_failed,
    get_json,
    json_default,
    product_case,
)
from scripts.stt.compare_language_candidates import read_pcm16_mono


def load_audio_cases(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(s) for s in path.read_text().splitlines()]
    if not rows or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("audio IDs must be unique and nonempty")
    historical = (
        path.resolve() == (ROOT / "datasets/commands/l04_audio_cases.jsonl").resolve()
    )
    for row in rows:
        if file_hash(ROOT / row["audio_path"]) != row["sha256"]:
            raise ValueError("consented audio changed")
        if not historical:
            proof_path = (ROOT / row["reference_proof"]).resolve()
            if not proof_path.is_relative_to((ROOT / "local-data").resolve()):
                raise ValueError("new audio reference must remain private")
            proof = json.loads(proof_path.read_text())
            if (
                proof.get("verified_by_speaker") is not True
                or proof.get("actually_spoken_reference") != row["spoken_reference"]
                or proof.get("audio_sha256") != row["sha256"]
            ):
                raise ValueError("new audio requires a speaker-verified reference")
    return rows


def run(plan_path: Path, output: Path, audio_path: Path) -> None:
    plan: Any = validate_plan(read_json(plan_path))
    profile = plan["profiles"][0]
    rows = load_audio_cases(audio_path)
    output.mkdir(parents=True, exist_ok=False)
    source = source_snapshot()
    write_new(output / "source-before.json", source)
    write_new(output / "plan.json", plan)
    inventory: Any = environment_snapshot(STORE, ROOT / "nonexistent-audio-settings")
    manifests = {
        item["tag"]: item["manifest_sha256"] for item in inventory["models"]["value"]
    }
    if manifests.get(profile["model"]["tag"]) != profile["model"]["artifact_sha256"]:
        raise ValueError("audio evaluation model artifact changed")
    write_new(output / "inventory.json", inventory)
    stopped = Event()
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    recorder = Recorder(32, monotonic() + 600, stopped)
    records: list[dict[str, Any]] = []
    resources = ModelResources()
    stt: ManagedSttEngine | None = None
    session = None
    run_error: dict[str, str] | None = None
    whisper_server = ROOT / ".venv/bin/whisper-server-gpu"
    whisper_model = (
        ROOT / "models/local/by-model/stt/whisper.cpp/ggml-small/ggml-small.bin"
    )
    model_hash_before = file_hash(whisper_model) if whisper_model.is_file() else None
    session_options = SpeechToTextOptions(
        language_hint="en", emit_partials=False, include_evidence=True
    )
    try:
        stt = ManagedSttEngine(
            lambda: WhisperEngine(
                whisper_server,
                whisper_model,
                language="en",
                compute_device=ComputeDevice.GPU,
            ),
            resources,
            "l04-audio-whisper-gpu",
        )
        session = stt.open_session(session_options)
        assert isinstance(session, TurnAwareSpeechToTextSession)
        with LocalOllamaServer(STORE, profile["model"]["tag"]) as url:
            runtime = get_json(url + "/api/version")["version"]
            bind_runtime(profile, runtime)
            engine = MeasuredEngine(url, profile, recorder, resources=resources)
            for row in rows:
                recorder.check()
                record: dict[str, Any] = {
                    "model": profile["model"]["tag"],
                    "id": row["id"],
                    "audio_sha256": row["sha256"],
                    "speaker_id": row["speaker_id"],
                    "intended_prompt": row.get("intended_prompt"),
                    "spoken_reference": row["spoken_reference"],
                    "requests": [],
                    "stages": [],
                }
                recorder.row = record
                try:
                    with (
                        activate(
                            Operation(recorder.deadline, cancelled=stopped.is_set)
                        ),
                        patch(
                            "kyrin.commands.token_budget.run_process", recorder.tokenize
                        ),
                    ):
                        with recorder.stage("stt_file"):
                            session.start_turn()
                            session.accept_audio(
                                AudioData(
                                    read_pcm16_mono(ROOT / row["audio_path"]),
                                    session.input_format,
                                )
                            )
                            update = replace(session.end_turn()[0], segment_id=0)
                        record["stt_text"] = update.text
                        record["stt_evidence"] = (
                            asdict(update.evidence) if update.evidence else None
                        )
                        record["stt_device"] = session.compute_device.value
                        expected: dict[str, Any] = {"route": "no_command"}
                        if row["expected"]["route"] == "execute":
                            expected = {
                                "route": "command",
                                "intents": [
                                    {
                                        "kind": step["operation"],
                                        "target": step["target"],
                                    }
                                    for step in row["expected"]["steps"]
                                ],
                            }
                        case = Case(
                            row["id"],
                            row["id"],
                            "audit",
                            "historical_human_audio",
                            "en",
                            "authorized_human_audio",
                            ({"text": update.text, **row.get("fixture", {})},),
                            expected,
                            False,
                            ({"actual": expected, "response_policy": "none"},),
                        )
                        record["product"] = product_case(
                            case, engine, transcripts=(update,)
                        )
                        # Force a real adapter request even when rules solved the text.
                        with recorder.stage("adapter"):
                            record["adapter_meaning"] = asdict(
                                engine.understand(
                                    UnderstandingInput(
                                        update.text, "en", evidence=update.evidence
                                    ),
                                    context=CommandContext(),
                                )
                            )
                    record["status"] = "completed"
                except (
                    OSError,
                    ValueError,
                    RuntimeError,
                    IndexError,
                    SpeechToTextError,
                ) as error:
                    record["status"] = "failed"
                    record["error"] = {
                        "type": type(error).__name__,
                        "message": str(error),
                    }
                records.append(record)
                with (output / "records.jsonl").open("a") as f:
                    f.write(
                        json.dumps(record, ensure_ascii=False, default=json_default)
                        + "\n"
                    )
                print(row["id"], record["status"], flush=True)
                if cleanup_failed(record) or any(
                    report["cleanup"] == "unconfirmed"
                    for report in record.get("device_reports", [])
                ):
                    raise RuntimeError("cleanup unconfirmed; stop audio evaluation")
    except (OSError, ValueError, RuntimeError, SpeechToTextError) as error:
        run_error = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        try:
            if session is not None:
                session.close()
        finally:
            if stt is not None:
                stt.close()
        write_new(
            output / "run.json",
            {
                "source_after": source_snapshot(),
                "source_before_sha256": source["sha256"],
                "scope": (
                    "authorized file STT plus model and inert gate; not live microphone"
                ),
                "audio_manifest_sha256": file_hash(audio_path),
                "inventory_sha256": fingerprint(inventory),
                "bound_profile": profile,
                "bound_profile_scope": "command_model_inherited_from_text_plan",
                "stt_configuration": {
                    "backend": "whisper",
                    "engine_requested_device": "gpu",
                    "engine_was_initialized": stt is not None,
                    "session_options": asdict(session_options),
                    "observed_session_devices": sorted(
                        {r["stt_device"] for r in records if "stt_device" in r}
                    ),
                    "source": "unpaced_file",
                    "model": str(whisper_model.resolve()),
                    "model_sha256_before": model_hash_before,
                    "model_sha256_after": (
                        file_hash(whisper_model) if whisper_model.is_file() else None
                    ),
                },
                "inference_attempts": recorder.total_calls,
                "records": len(records),
                "run_error": run_error,
                "whisper_server": str(whisper_server.resolve()),
                "whisper_server_sha256": (
                    file_hash(whisper_server) if whisper_server.is_file() else None
                ),
                "stt_resources_after": resources.snapshot(),
                "resources_quiescent": resources.is_quiescent(),
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--audio-cases",
        type=Path,
        default=ROOT / "datasets/commands/l04_audio_cases.jsonl",
    )
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to((ROOT / "local-data").resolve()):
        parser.error("output must remain in project local-data")
    run(args.plan, args.output, args.audio_cases)


if __name__ == "__main__":
    main()
