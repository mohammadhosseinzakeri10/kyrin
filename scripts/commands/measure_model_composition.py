"""Bounded optional E45 composition; only existing consented WAV and inert playback."""

import argparse
import importlib
import json
import os
import sys
from copy import deepcopy
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from threading import Event, Thread
from time import monotonic, perf_counter_ns
from typing import Any, cast
from unittest.mock import patch

from kyrin.actions.models import ActionKey
from kyrin.commands.models import CommandContext
from kyrin.commands.ollama_device import running_device
from kyrin.commands.ollama_server import LocalOllamaServer
from kyrin.commands.understanding import UnderstandingInput
from kyrin.model_resources import ModelResources
from kyrin.operations import Operation, activate
from kyrin.stt.backends.whisper import WhisperEngine
from kyrin.stt.device import ComputeDevice, DevicePreference
from kyrin.stt.evaluation import CorpusItem, evaluate_item
from kyrin.stt.resources import ManagedSttEngine
from kyrin.timing import TimingEvent, TimingScope, timing_scope
from kyrin.tts.models import TtsSelection
from kyrin.tts.runtime import ConfiguredSpeechSynthesizer
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
    MemorySampler,
    Recorder,
    bind_runtime,
    cleanup_failed,
    get_json,
    json_default,
)


class SilentPlayback:
    def __init__(self) -> None:
        self.calls: list[dict[str, int]] = []

    def play(self, samples: Any, sample_rate: int, *, blocking: bool) -> None:
        self.calls.append({"samples": len(samples), "sample_rate": sample_rate})

    def wait(self) -> None:
        pass

    def stop(self) -> None:
        pass


def composition_selection(
    plan: dict[str, Any], inventory: dict[str, Any]
) -> tuple[dict[str, Any], Path, Path]:
    validate_plan(plan)
    profile = deepcopy(
        next(p for p in plan["profiles"] if p["id"] == "gpu-qwen9b-speech")
    )
    selections = inventory["environment"]["technical_selection"]["value"]
    paths: dict[str, Path] = {}
    for part, backend, device, activity, residency in (
        ("stt", "whisper", "gpu", "file", "session"),
        ("tts", "kokoro", "cpu", "text", "per_call"),
    ):
        component = profile["composition"][part]
        if any(
            component[key] != expected
            for key, expected in (
                ("backend", backend),
                ("requested_device", device),
                ("activity", activity),
                ("residency", residency),
            )
        ):
            raise ValueError("unsupported composition profile")
        artifact = component["artifact"]
        path = Path(selections[part]["model_path"])
        if artifact is None or Path(artifact).resolve() != path.resolve():
            raise ValueError("composition artifact differs from the plan")
        if not path.exists():
            raise ValueError("composition artifact is missing")
        paths[part] = path
    observed = environment_snapshot(STORE, ROOT / "nonexistent-benchmark-settings")
    available = {
        item["tag"]: item["manifest_sha256"]
        for item in cast(dict[str, Any], observed["models"])["value"]
    }
    model = profile["model"]
    if model["tag"] not in available or model["artifact_sha256"] not in {
        None,
        available[model["tag"]],
    }:
        raise ValueError("selected artifact is missing or changed since the plan")
    model["artifact_sha256"] = available[model["tag"]]
    return profile, paths["stt"], paths["tts"]


def require_command_success(row: dict[str, Any]) -> None:
    if (
        row["status"] != "completed"
        or cleanup_failed(row)
        or any(r["cleanup"] == "unconfirmed" for r in row["device_reports"])
    ):
        raise RuntimeError("composition command failed; stop subsequent workloads")


def condition_profile(profile: dict[str, Any], label: str) -> dict[str, Any]:
    bound = deepcopy(profile)
    composition = bound["composition"]
    alone = label == "command_alone"
    # Command inputs are synthetic text; STT is idle in these four intervals.
    composition["silence"] = True
    composition["stt"].update(
        activity="off" if alone else "idle",
        residency="absent" if alone else "session",
    )
    active_tts = label == "command_waiting_for_tts"
    composition["tts"].update(
        activity="text" if active_tts else "off",
        residency="per_call" if active_tts else "absent",
    )
    return bound


def run(plan_path: Path, inventory_path: Path, output: Path, seconds: int) -> None:
    if not output.resolve().is_relative_to((ROOT / "local-data").resolve()):
        raise ValueError("output must stay under project local-data")
    if not 1 <= seconds <= 120:
        raise ValueError("composition budget must be 1..120 seconds")
    plan = cast(dict[str, Any], read_json(plan_path))
    inventory = cast(dict[str, Any], read_json(inventory_path))
    profile, stt_model, tts_model = composition_selection(plan, inventory)
    audio = json.loads(
        (ROOT / "datasets/commands/l04_audio_cases.jsonl").read_text().splitlines()[0]
    )
    audio_path = ROOT / audio["audio_path"]
    if file_hash(audio_path) != audio["sha256"]:
        raise ValueError("audio differs from its reference")
    output.mkdir(parents=True, exist_ok=False)
    source = source_snapshot()
    started = monotonic()
    runtime_version: str | None = None
    write_new(output / "plan.json", plan)
    write_new(output / "source-before.json", source)
    write_new(
        output / "protocol.json",
        {
            "schema_version": 1,
            "max_seconds": seconds,
            "max_command_calls": 4,
            "audio_id": audio["id"],
            "audio_sha256": audio["sha256"],
            "stt_device": "gpu",
            "tts_device": "cpu",
            "tts_voice": "0",
            "tts_speed": 1.0,
            "wav_pacing": "unpaced",
            "microphone": False,
            "playback": "inert",
            "script_sha256": file_hash(Path(__file__)),
            "plan_sha256": fingerprint(plan),
            "inventory_sha256": fingerprint(inventory),
            "component_content_identity": "local artifacts; weights not rehashed",
        },
    )
    stopped = Event()
    recorder = Recorder(4, monotonic() + seconds, stopped)
    resources = ModelResources()
    sampler = MemorySampler(output / "memory.jsonl", {os.getpid()}, 100)
    sampler.thread.start()
    results: list[dict[str, Any]] = []
    stt: ManagedSttEngine | None = None
    synth: ConfiguredSpeechSynthesizer | None = None
    try:
        with LocalOllamaServer(STORE, profile["model"]["tag"]) as url:
            runtime_version = get_json(url + "/api/version")["version"]
            bind_runtime(profile, runtime_version)
            engine = MeasuredEngine(url, profile, recorder)
            engine._resources = resources

            def command(label: str) -> None:
                bound = condition_profile(profile, label)
                row: dict[str, Any] = {
                    "model": profile["model"]["tag"],
                    "condition": label,
                    "profile": bound,
                    "profile_sha256": fingerprint(bound),
                    "stages": [],
                    "requests": [],
                    "device_reports": [],
                }
                recorder.row = row
                sampler.attempt = label
                start = perf_counter_ns()
                stamps: list[TimingEvent] = []
                try:
                    with (
                        activate(
                            Operation(recorder.deadline, cancelled=stopped.is_set)
                        ),
                        timing_scope(
                            TimingScope(
                                output.name, ActionKey(0, len(results)), stamps.append
                            )
                        ),
                        patch(
                            "kyrin.commands.token_budget.run_process", recorder.tokenize
                        ),
                    ):
                        row["meaning"] = asdict(
                            engine.understand(
                                UnderstandingInput("Open Telegram", "en"),
                                context=CommandContext(),
                            )
                        )
                    row["status"] = "completed"
                except (OSError, ValueError, RuntimeError) as error:
                    row.update(
                        status="failed", error=f"{type(error).__name__}: {error}"
                    )
                row["elapsed_ms"] = (perf_counter_ns() - start) / 1e6
                row["timing"] = [asdict(e) for e in stamps]
                row["post_cleanup"] = asdict(
                    running_device(url, profile["model"]["tag"], 3)
                )
                results.append(row)
                require_command_success(row)

            command("command_alone")
            stamps: list[TimingEvent] = []
            start = perf_counter_ns()
            with (
                activate(Operation(recorder.deadline, cancelled=stopped.is_set)),
                timing_scope(TimingScope(output.name, ActionKey(1, 0), stamps.append)),
            ):
                stt = ManagedSttEngine(
                    lambda: WhisperEngine(
                        ROOT / ".venv/bin/whisper-server-gpu",
                        stt_model,
                        language="en",
                        compute_device=ComputeDevice.GPU,
                    ),
                    resources,
                    f"stt:whisper:{stt_model}:gpu",
                )
            results.append(
                {
                    "condition": "stt_load",
                    "elapsed_ms": (perf_counter_ns() - start) / 1e6,
                    "timing": [asdict(e) for e in stamps],
                }
            )
            command("stt_resident_idle")
            with activate(Operation(recorder.deadline, cancelled=stopped.is_set)):
                result = evaluate_item(
                    stt,
                    CorpusItem(
                        audio["id"], audio_path, "en", audio["spoken_reference"]
                    ),
                    realtime=False,
                    device=DevicePreference.GPU,
                )
            results.append({"condition": "stt_file", "result": asdict(result)})
            command("stt_resident_after_file")
            silent = SilentPlayback()
            original_import = importlib.import_module

            def safe_import(name: str) -> Any:
                return silent if name == "sounddevice" else original_import(name)

            synth = ConfiguredSpeechSynthesizer(
                TtsSelection(
                    backend="kokoro",
                    model_path=tts_model,
                    voice="0",
                    speed=1.0,
                    device=DevicePreference.CPU,
                ),
                resources=resources,
            )
            from kyrin.tts import runtime as tts_runtime

            adapter = tts_runtime._ADAPTERS["kokoro"]
            original_generate = adapter.generate
            generating = Event()

            def generate(*args: Any, **kwargs: Any) -> tuple[Any, int]:
                generating.set()
                return original_generate(*args, **kwargs)

            tts_stamps: list[TimingEvent] = []
            errors: list[str] = []

            def speak() -> None:
                try:
                    with (
                        activate(
                            Operation(recorder.deadline, cancelled=stopped.is_set)
                        ),
                        timing_scope(
                            TimingScope(output.name, ActionKey(2, 0), tts_stamps.append)
                        ),
                    ):
                        assert synth is not None
                        synth.speak("This is a safe benchmark.", "en")
                except (OSError, ValueError, RuntimeError) as error:
                    errors.append(f"{type(error).__name__}: {error}")
                    generating.set()

            with (
                patch("kyrin.tts.runtime.import_module", safe_import),
                patch.object(adapter, "generate", generate),
            ):
                thread = Thread(target=speak)
                thread.start()
                try:
                    if not generating.wait(
                        min(30, max(0, recorder.deadline - monotonic()))
                    ):
                        stopped.set()
                    command("command_waiting_for_tts")
                finally:
                    # Keep ownership and inert playback until native synthesis
                    # exits, including a failed queued command.
                    stopped.set()
                    thread.join()
                    results.append(
                        {
                            "condition": "tts_text",
                            "playback": silent.calls,
                            "errors": errors,
                            "timing": [asdict(e) for e in tts_stamps],
                        }
                    )
    except (OSError, ValueError, RuntimeError) as error:
        results.append(
            {
                "condition": "composition_error",
                "error": f"{type(error).__name__}: {error}",
            }
        )
    finally:
        for label, resource in (("tts_close", synth), ("stt_close", stt)):
            if resource is not None:
                try:
                    released = resource.close()
                    results.append({"condition": label, "released": released})
                except (OSError, ValueError, RuntimeError) as error:
                    results.append(
                        {
                            "condition": label,
                            "error": f"{type(error).__name__}: {error}",
                        }
                    )
        sampler.stop.set()
        sampler.thread.join()
        after = source_snapshot()
        try:
            sherpa_version: str | None = version("sherpa-onnx")
        except PackageNotFoundError:
            sherpa_version = None
        write_new(
            output / "run.json",
            {
                "schema_version": 1,
                "results": json.loads(json.dumps(results, default=json_default)),
                "source_unchanged": source["sha256"] == after["sha256"],
                "source_after": after,
                "command_inferences": recorder.total_calls,
                "elapsed_seconds": monotonic() - started,
                "deadline_overrun_seconds": max(0, monotonic() - recorder.deadline),
                "deadline_scope": (
                    "cooperative; native in-process inference must finish"
                ),
                "memory_sampler_error": sampler.error,
                "memory_samples": sampler.samples,
                "python": sys.version,
                "ollama_version": runtime_version,
                "bound_profile": profile,
                "sherpa_onnx_version": sherpa_version,
            },
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--seconds", type=int, default=120)
    a = p.parse_args()
    run(a.plan, a.inventory, a.output, a.seconds)
