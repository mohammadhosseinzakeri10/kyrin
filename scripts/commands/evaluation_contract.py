"""E03 plans and read-only provenance; never start a model or desktop session."""

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import cast

import kyrin
from kyrin.app.settings_store import linux_settings_path
from kyrin.commands.ollama_device import ModelPlacement
from kyrin.commands.ollama_models import ollama_model_stores

ROOT = Path(__file__).resolve().parents[2]
TOOL_VERSION = "1"
DEFAULT_PLAN = ROOT / "datasets/commands/evaluation/plan.v1.json"
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def fingerprint(value: object) -> str:
    """Canonical JSON identity, independent of indentation and dictionary order."""
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object(value: object, fields: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != set(fields.split()):
        raise ValueError(f"missing or unknown fields; expected {fields}")
    return cast(dict[str, object], value)


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected nonempty string")
    return value


def _choice(value: object, choices: str) -> str:
    result = _text(value)
    if result not in choices.split():
        raise ValueError(f"expected one of {choices}")
    return result


def _integer(value: object, minimum: int = 1) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"expected integer >= {minimum}")
    return value


def _digest(value: object) -> str:
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise ValueError("expected SHA256 hex digest")
    return value


def _strings(value: object, *, unique: bool = True) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("expected nonempty string list")
    result = [_text(item) for item in value]
    if unique and len(result) != len(set(result)):
        raise ValueError("duplicate list entries")
    return result


def _relative(value: object) -> Path:
    path = Path(_text(value))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("expected portable repository-relative path")
    return path


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique)


def validate_profile(value: object) -> dict[str, object]:
    row = _object(
        value,
        "id status model requested_device expected_placements "
        "context_tokens output_tokens safety_tokens confirmation_tokens "
        "generation deadline_seconds hardware composition",
    )
    _text(row["id"])
    status = _choice(row["status"], "proposed ready missing_prerequisite")
    model = _object(row["model"], "tag artifact_sha256 runtime runtime_version")
    _text(model["tag"])
    _choice(model["runtime"], "ollama")
    for key in ("artifact_sha256", "runtime_version"):
        if model[key] is not None:
            (_digest if key == "artifact_sha256" else _text)(model[key])
        elif status == "ready":
            raise ValueError("ready profile needs artifact and runtime identity")
    device = _choice(row["requested_device"], "cpu gpu auto")
    placements = _strings(row["expected_placements"])
    allowed = {
        "cpu": {ModelPlacement.CPU.value},
        "gpu": {
            ModelPlacement.GPU.value,
            ModelPlacement.MIXED.value,
            ModelPlacement.GPU_PARTICIPATION.value,
        },
        "auto": {item.value for item in ModelPlacement},
    }[device]
    if set(placements) != allowed:
        raise ValueError("placements must preserve the existing device policy")
    context = _integer(row["context_tokens"])
    output = _integer(row["output_tokens"])
    safety = _integer(row["safety_tokens"], 0)
    confirmation = _integer(row["confirmation_tokens"])
    if confirmation != 64:
        raise ValueError("confirmation tokens differ from production adapter budget")
    if context <= max(output, confirmation) + safety:
        raise ValueError("context does not cover output and safety tokens")
    generation = _object(
        row["generation"],
        "temperature think truncate shift keep_alive cleanup_keep_alive",
    )
    temperature = generation["temperature"]
    if (
        type(temperature) not in (int, float)
        or not math.isfinite(cast(float, temperature))
        or temperature != 0
    ):
        raise ValueError("product baseline temperature must be zero")
    for key in ("think", "truncate", "shift"):
        if generation[key] is not False:
            raise ValueError(f"product baseline requires {key}=false")
    if generation["keep_alive"] != "30s" or (
        type(generation["cleanup_keep_alive"]) is not int
        or generation["cleanup_keep_alive"] != 0
    ):
        raise ValueError("product baseline must retain per-request cleanup")
    deadline = _integer(row["deadline_seconds"])
    if deadline != (120 if device == "cpu" else 60):
        raise ValueError("deadline differs from production adapter budget")
    hardware = _object(row["hardware"], "cpu ram_bytes gpu vram_bytes")
    for key, item in hardware.items():
        if item is not None:
            (_integer if key.endswith("_bytes") else _text)(item)
    composition = _object(row["composition"], "stt tts silence shared_resources")
    if type(composition["silence"]) is not bool:
        raise ValueError("silence must be a boolean")
    _choice(composition["shared_resources"], "serialized_model_resources")
    for key in ("stt", "tts"):
        component = _object(
            composition[key], "backend artifact requested_device activity residency"
        )
        for field in ("backend", "artifact", "requested_device"):
            if component[field] is not None:
                _text(component[field])
        if component["requested_device"] is not None:
            _choice(component["requested_device"], "cpu gpu auto")
        _choice(component["activity"], "off idle file text live")
        _choice(component["residency"], "absent session per_call unknown")
        if component["activity"] != "off" and any(
            component[field] is None
            for field in ("backend", "artifact", "requested_device")
        ):
            if status == "ready":
                raise ValueError("ready composition needs component identities")
    return row


def validate_plan(value: object, root: Path = ROOT) -> dict[str, object]:
    plan = _object(value, "schema_version tool_version profiles corpus protocol memory")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise ValueError("unsupported plan schema")
    if plan["tool_version"] != TOOL_VERSION:
        raise ValueError("incompatible tool version")
    profiles = plan["profiles"]
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("profiles must be a nonempty list")
    validated = [validate_profile(row) for row in profiles]
    ids = [row["id"] for row in validated]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate profile ID")
    corpus = _object(
        plan["corpus"], "path sha256 references_path references_sha256 case_ids"
    )
    for key, digest_key in (
        ("path", "sha256"),
        ("references_path", "references_sha256"),
    ):
        path = root / _relative(corpus[key])
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("corpus escapes repository")
        if file_hash(path) != _digest(corpus[digest_key]):
            raise ValueError(f"changed corpus/reference: {key}")
    case_ids = _strings(corpus["case_ids"])
    # Reuse the existing corpus/turn-reference validator; never run its evaluator.
    from scripts.commands.evaluate_l04_baseline import load_cases

    path = root / _relative(corpus["path"])
    if (root / _relative(corpus["references_path"])) != path.with_name(
        "l04_turn_references.jsonl"
    ):
        raise ValueError("reference path differs from the corpus loader contract")
    known = {case.id for case in load_cases(path)}
    if not set(case_ids) <= known:
        raise ValueError("unknown case ID")
    protocol = _object(
        plan["protocol"],
        "profile_order levels repetitions pilot_attempts "
        "max_attempts max_seconds min_percentile_samples reuse "
        "temperature service_state executor",
    )
    if not set(_strings(protocol["profile_order"])) <= set(ids):
        raise ValueError("unknown scheduled profile")
    if set(_strings(protocol["levels"])) != {"adapter", "product_text"}:
        raise ValueError("baseline levels must distinguish adapter and product_text")
    for key in ("repetitions", "pilot_attempts", "max_attempts", "max_seconds"):
        _integer(protocol[key])
    if _integer(protocol["min_percentile_samples"]) != 20:
        raise ValueError("percentiles require at least 20 valid samples")
    _choice(protocol["reuse"], "fresh_only")
    _choice(protocol["temperature"], "unknown cold warm")
    _choice(protocol["service_state"], "unknown started existing")
    _choice(protocol["executor"], "inert")
    memory = _object(plan["memory"], "unit interval_ms scope measures")
    _choice(memory["unit"], "bytes")
    _integer(memory["interval_ms"])
    _choice(memory["scope"], "owned_process_tree_and_device")
    if set(_strings(memory["measures"])) != {
        "rss",
        "pss",
        "process_vram",
        "device_vram",
        "idle_residency",
    }:
        raise ValueError("memory measurement domains are incomplete")
    return plan


def group_key(value: object) -> str:
    """Strict pooling identity. Different keys require an explicit comparison."""
    row = _object(
        value,
        "schema_version tool_version plan_sha256 profile_sha256 "
        "source_sha256 environment_sha256 corpus_sha256 references_sha256 "
        "case_order level temperature service_state placement reuse",
    )
    if type(row["schema_version"]) is not int or row["schema_version"] != 1:
        raise ValueError("unsupported group schema")
    if row["tool_version"] != TOOL_VERSION:
        raise ValueError("incompatible tool version")
    for key in row:
        if key.endswith("_sha256"):
            _digest(row[key])
    _strings(row["case_order"], unique=False)
    _choice(row["level"], "adapter product_text audio_file live_speech")
    _choice(row["temperature"], "cold warm unknown")
    _choice(row["service_state"], "unknown started existing")
    _choice(row["placement"], " ".join(item.value for item in ModelPlacement))
    _choice(row["reuse"], "fresh cached resumed")
    return fingerprint(row)


def source_snapshot(root: Path = ROOT) -> dict[str, object]:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=root).decode()

    before = git("status", "--porcelain")
    first_head = git("rev-parse", "HEAD").strip()
    paths = sorted(
        set(
            git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split(
                "\0"
            )
        )
        - {""}
    )
    files = {
        name: file_hash(root / name) if (root / name).is_file() else None
        for name in paths
    }
    head = git("rev-parse", "HEAD").strip()
    after = git("status", "--porcelain")
    # Re-read hashes too: content can change without changing porcelain status.
    stable = (
        before == after
        and first_head == head
        and all(
            digest == (file_hash(root / name) if (root / name).is_file() else None)
            for name, digest in files.items()
        )
    )
    return {
        "head": head,
        "status": after,
        "files": files,
        "sha256": fingerprint({"head": head, "files": files}),
        "stable_during_capture": stable,
    }


def _fact(value: object, source: str, reason: str = "observed") -> dict[str, object]:
    return {"value": value, "source": source, "reason": reason}


def _command(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=10, check=False
        )
    except OSError, subprocess.SubprocessError:
        return None
    return (result.stdout + result.stderr).strip() if result.returncode == 0 else None


def environment_snapshot(store: Path, settings_path: Path) -> dict[str, object]:
    """Whitelist technical facts; no transcript, permissions or settings dump."""
    facts: dict[str, object] = {}
    facts["python"] = _fact(sys.version, "sys.version of inventory interpreter")
    origin = Path(kyrin.__file__).resolve()
    if origin != (ROOT / "src/kyrin/__init__.py").resolve():
        raise ValueError("inventory imported kyrin from another checkout")
    facts["module_origin"] = _fact(str(origin), "kyrin.__file__")
    packages: dict[str, str | None] = {}
    for name in ("numpy", "onnxruntime", "sherpa-onnx", "PySide6_Essentials"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    facts["packages"] = _fact(
        packages,
        "importlib.metadata in inventory interpreter",
        "not proof of optional worker environment versions",
    )
    cpu = None
    ram = None
    try:
        cpu = next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            None,
        )
        ram = next(
            (
                int(line.split()[1]) * 1024
                for line in Path("/proc/meminfo").read_text().splitlines()
                if line.startswith("MemTotal:")
            ),
            None,
        )
    except OSError, ValueError:
        pass
    facts["cpu"] = _fact(cpu, "/proc/cpuinfo:model name", "unknown if inaccessible")
    facts["ram_bytes"] = _fact(ram, "/proc/meminfo:MemTotal KiB * 1024")
    gpu = _command(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    facts["gpu_query_mib"] = _fact(
        gpu,
        "nvidia-smi readonly query; memory in MiB",
        "unknown if command/driver inaccessible; not a peak",
    )
    gpu_names: list[str] = []
    for information in sorted(Path("/proc/driver/nvidia/gpus").glob("*/information")):
        try:
            gpu_names.extend(
                line.split(":", 1)[1].strip()
                for line in information.read_text().splitlines()
                if line.startswith("Model:")
            )
        except OSError:
            continue
    facts["gpu_names"] = _fact(
        gpu_names or None,
        "/proc/driver/nvidia/gpus/*/information:Model only",
        "hardware name is not evidence of usable CUDA or available VRAM",
    )
    runtime = _command(["ollama", "--version"])
    facts["ollama_cli_version"] = _fact(
        runtime, "ollama --version", "client only; private server version unobserved"
    )
    tokenizers = sorted(
        (ROOT / "local-data/kyrin/runtimes/command-understanding").glob(
            "llama.cpp-*/llama-*/llama-tokenize"
        )
    )
    binary = shutil.which("llama-tokenize")
    facts["tokenizer_candidates"] = _fact(
        ([binary] if binary else [])
        + [str(path.relative_to(ROOT)) for path in tokenizers],
        "PATH and project runtime directory; no tokenizer executed",
        "actual chosen binary/version must be bound by E45",
    )
    selected: dict[str, object] = {}
    try:
        raw_settings = read_json(settings_path)
        if not isinstance(raw_settings, dict):
            raise ValueError("settings must be an object")
        settings = cast(dict[str, object], raw_settings)
        for key in ("command_model", "stt", "tts"):
            raw = settings.get(key)
            if isinstance(raw, dict):
                selected[key] = {
                    field: raw.get(field)
                    for field in (
                        "backend",
                        "model",
                        "device",
                        "model_path",
                        "store_path",
                    )
                    if field in raw
                }
            else:
                selected[key] = None
    except OSError, ValueError, TypeError:
        selected = {key: None for key in ("command_model", "stt", "tts")}
    facts["technical_selection"] = _fact(
        selected,
        "settings whitelist only",
        "configuration is not observed runtime activity",
    )
    models = []
    for tag, location in ollama_model_stores(store).items():
        repository, revision = tag.rsplit(":", 1)
        parts = repository.split("/")
        namespace, name = parts if len(parts) == 2 else ("library", repository)
        manifests = list(
            (location / "manifests").glob(f"*/{namespace}/{name}/{revision}")
        )
        if len(manifests) != 1:
            continue
        manifest = manifests[0]
        document = cast(dict[str, object], read_json(manifest))
        layers = cast(list[dict[str, object]], document["layers"])
        models.append(
            {
                "tag": tag,
                "manifest_sha256": file_hash(manifest),
                "manifest_path": str(manifest.relative_to(ROOT)),
                "layers": [
                    {key: layer.get(key) for key in ("mediaType", "digest", "size")}
                    for layer in layers
                ],
            }
        )
    facts["models"] = _fact(
        models,
        "complete local stores and small manifest SHA256",
        "existing layer digests reused; weights never read or hashed",
    )
    facts["unmeasured"] = _fact(
        None,
        "E03 deliberately does not run models",
        "placement, activity, latency, peaks and cleanup residency unknown",
    )
    return facts


def write_new(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        output.write(
            json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="Write new local technical inventory; never overwrite",
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=ROOT / "models/local/by-model/command-understanding/ollama",
    )
    parser.add_argument("--settings", type=Path, default=linux_settings_path())
    args = parser.parse_args()
    try:
        plan = validate_plan(read_json(args.plan))
        if args.snapshot:
            if not args.snapshot.resolve().is_relative_to(
                (ROOT / "local-data").resolve()
            ):
                raise ValueError("local inventory must remain under project local-data")
            before = source_snapshot()
            environment = environment_snapshot(args.store, args.settings)
            after = source_snapshot()
            snapshot = {
                "schema_version": 1,
                "tool_version": TOOL_VERSION,
                "created_utc": datetime.now(UTC).isoformat(),
                "plan_sha256": fingerprint(plan),
                "source": after,
                "source_unchanged": before == after,
                "environment": environment,
                "environment_sha256": fingerprint(environment),
            }
            write_new(args.snapshot, snapshot)
            if before != after or not after["stable_during_capture"]:
                raise ValueError(
                    "concurrent source changes; snapshot is diagnostic only"
                )
        print(json.dumps({"valid": True, "plan_sha256": fingerprint(plan)}))
        return 0
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        subprocess.SubprocessError,
    ) as error:
        parser.exit(1, f"evaluation contract: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
