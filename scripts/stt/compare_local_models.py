"""Compare local Whisper and Omnilingual checkpoints on the same labeled WAVs.

Each model/language pair runs in its own process. No microphone, downloads,
command executor, or desktop action is involved. Reports contain speech text.
"""

import argparse
import csv
import json
import os
import signal
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread
from typing import Any

from kyrin.stt.backends.omnilingual import MODEL_NAMES, model_files
from kyrin.stt.evaluation import CorpusItem, load_corpus

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFESTS = (
    ROOT / "datasets/stt/manifest.csv",
    ROOT / "datasets/stt/manifest.multilingual.csv",
    ROOT / "datasets/stt/manifest.safety.csv",
)
WHISPER_NAME = "whisper-small"
CANDIDATES = (WHISPER_NAME, *MODEL_NAMES)


def available_memory_bytes() -> int | None:
    """Read Linux MemAvailable; unknown availability must not authorize a large run."""
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def cpu_memory_requirement(checkpoint_bytes: int) -> int:
    """Conservative admission estimate, not a measurement of model peak RAM."""
    return round(checkpoint_bytes * 2.5) + 4 * 1024**3


def available_gpu_memory_bytes() -> int | None:
    """Read the first CUDA GPU's free memory without loading a model."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return int(result.stdout.splitlines()[0].strip()) * 1024**2
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None
    return None


def gpu_memory_requirement(checkpoint_bytes: int) -> int:
    """Conservative CUDA admission estimate, not measured peak VRAM."""
    return round(checkpoint_bytes * 1.4) + 2 * 1024**3


def gpu_used_mib() -> int | None:
    """Read total use on the first GPU; other applications are included."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return int(result.stdout.splitlines()[0].strip())
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None
    return None


def run_one(
    command: list[str], timeout_seconds: int, *, monitor_gpu: bool = False
) -> tuple[int, str, int | None, int | None]:
    baseline_gpu_mib = gpu_used_mib() if monitor_gpu else None
    observed_gpu_mib: list[int] = []
    monitor_stop = Event()

    def sample_gpu() -> None:
        while not monitor_stop.is_set():
            used = gpu_used_mib()
            if used is not None:
                observed_gpu_mib.append(used)
            monitor_stop.wait(0.25)

    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    monitor = Thread(target=sample_gpu, daemon=True) if monitor_gpu else None
    if monitor is not None:
        monitor.start()
    try:
        try:
            _, errors = process.communicate(timeout=timeout_seconds)
            code = process.returncode
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            _, errors = process.communicate()
            code = 124
    finally:
        monitor_stop.set()
        if monitor is not None:
            monitor.join(timeout=6)
    peak_gpu_mib = max(observed_gpu_mib, default=baseline_gpu_mib)
    return code, errors.decode(errors="replace")[-2000:], baseline_gpu_mib, peak_gpu_mib


def report_row(
    candidate: str, language: str, report: dict[str, Any]
) -> dict[str, object]:
    return {
        "model": candidate,
        "language": language,
        "status": "completed",
        "files": report["files"],
        "cer": report["cer"],
        "wer": report["wer"],
        "reference_characters": report["reference_characters"],
        "edit_distance": report["edit_distance"],
        "reference_words": report["reference_words"],
        "word_edit_distance": report["word_edit_distance"],
        "model_load_seconds": report["model_load_seconds"],
        "peak_child_rss_mib": report["peak_child_rss_mib"],
        "mean_elapsed_seconds": sum(
            float(item["elapsed_seconds"]) for item in report["results"]
        )
        / int(report["files"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, action="append")
    parser.add_argument("--include", choices=CANDIDATES, action="append")
    parser.add_argument("--device", choices=("cpu", "gpu"), default="cpu")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--whisper-model",
        type=Path,
        default=(
            ROOT
            / "models/local/by-model/stt/whisper.cpp/ggml-small/ggml-small.bin"
        ),
    )
    parser.add_argument(
        "--whisper-server",
        type=Path,
        default=ROOT / ".venv/bin/whisper-server",
    )
    parser.add_argument(
        "--omnilingual-root",
        type=Path,
        default=ROOT / "models/local/by-model/stt/omnilingual-asr",
    )
    parser.add_argument(
        "--runtime-python",
        type=Path,
        default=ROOT / "local-data/kyrin/runtimes/stt/omnilingual-asr/bin/python",
    )
    args = parser.parse_args(argv)
    if args.threads <= 0 or args.timeout_seconds <= 0:
        parser.error("threads and timeout must be positive")
    candidates = tuple(dict.fromkeys(args.include or CANDIDATES))
    manifests = tuple(args.manifest or DEFAULT_MANIFESTS)
    try:
        grouped: dict[str, list[CorpusItem]] = defaultdict(list)
        seen_ids: set[str] = set()
        for manifest in manifests:
            for item in load_corpus(manifest):
                if item.id in seen_ids:
                    raise ValueError(f"duplicate case ID across manifests: {item.id}")
                seen_ids.add(item.id)
                grouped[item.language].append(item)
        if WHISPER_NAME in candidates and (
            not args.whisper_model.is_file() or not args.whisper_server.is_file()
        ):
            raise FileNotFoundError("Whisper model or server is missing")
        for candidate in candidates:
            if candidate != WHISPER_NAME:
                model_files(args.omnilingual_root / candidate)
        if any(candidate != WHISPER_NAME for candidate in candidates):
            if not args.runtime_python.is_file():
                raise FileNotFoundError("Omnilingual runtime is missing")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    output_dir = args.output_dir or (
        ROOT
        / "datasets/stt/results"
        / f"local-model-comparison-{datetime.now(UTC):%Y%m%d-%H%M%S}"
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, object]] = []
    evaluator = Path(__file__).with_name("evaluate_offline_stt.py")
    language_manifests: dict[str, Path] = {}
    for language, cases in grouped.items():
        private_manifest = output_dir / f"cases-{language}.csv"
        with private_manifest.open("x", encoding="utf-8", newline="") as target:
            writer = csv.writer(target)
            writer.writerow(("id", "path", "language", "reference"))
            for item in cases:
                writer.writerow(
                    (item.id, str(item.path.resolve()), item.language, item.reference)
                )
        language_manifests[language] = private_manifest
    for candidate in candidates:
        model_path = (
            args.whisper_model
            if candidate == WHISPER_NAME
            else args.omnilingual_root / candidate
        )
        checkpoint = (
            model_path if candidate == WHISPER_NAME else model_files(model_path)[0]
        )
        for language in sorted(grouped):
            report_path = output_dir / f"{candidate}-{language}.json"
            free = (
                available_memory_bytes()
                if args.device == "cpu"
                else available_gpu_memory_bytes()
            )
            required = (
                cpu_memory_requirement(checkpoint.stat().st_size)
                if args.device == "cpu"
                else gpu_memory_requirement(checkpoint.stat().st_size)
            )
            if free is None or free < required:
                status = (
                    "skipped_memory" if args.device == "cpu" else "skipped_vram"
                )
                rows.append(
                    {
                        "model": candidate,
                        "language": language,
                        "status": status,
                        "available_mib": None if free is None else free // 1024**2,
                        "admission_estimate_mib": required // 1024**2,
                    }
                )
                print(f"{candidate} {language}: {status}", flush=True)
                continue
            command = [
                sys.executable,
                str(evaluator),
                "--backend",
                "whisper" if candidate == WHISPER_NAME else "omnilingual",
                "--model-path",
                str(model_path),
                "--model-language",
                language,
                "--device",
                args.device,
                "--threads",
                str(args.threads),
                "--unpaced",
                "--output",
                str(report_path),
                "--manifest",
                str(language_manifests[language]),
            ]
            if candidate == WHISPER_NAME:
                command.extend(("--whisper-server", str(args.whisper_server)))
            else:
                command.extend(("--runtime-python", str(args.runtime_python)))
            code, error, gpu_baseline, gpu_peak = run_one(
                command, args.timeout_seconds, monitor_gpu=args.device == "gpu"
            )
            if code == 0:
                report = json.loads(report_path.read_text(encoding="utf-8"))
                row = report_row(candidate, language, report)
                if args.device == "gpu":
                    row.update(
                        {
                            "gpu_total_used_before_mib": gpu_baseline,
                            "gpu_total_used_peak_mib": gpu_peak,
                            "gpu_used_delta_mib": (
                                max(0, gpu_peak - gpu_baseline)
                                if gpu_peak is not None and gpu_baseline is not None
                                else None
                            ),
                        }
                    )
                rows.append(row)
            else:
                rows.append(
                    {
                        "model": candidate,
                        "language": language,
                        "status": "timed_out" if code == 124 else "failed",
                        "exit_code": code,
                        "error": error,
                    }
                )
            print(f"{candidate} {language}: {rows[-1]['status']}", flush=True)
    summary = {
        "device": args.device,
        "manifests": [str(path.resolve()) for path in manifests],
        "output_dir": str(output_dir.resolve()),
        "memory_rule": (
            "CPU: 2.5 x checkpoint bytes + 4 GiB; "
            "GPU: 1.4 x checkpoint bytes + 2 GiB; estimates, not measured peaks"
        ),
        "rows": rows,
    }
    with (output_dir / "summary.json").open("x", encoding="utf-8") as target:
        json.dump(summary, target, ensure_ascii=False, indent=2)
        target.write("\n")
    print(output_dir / "summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
