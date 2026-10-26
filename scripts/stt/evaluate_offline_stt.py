"""Evaluate one local STT model on labeled WAV files without desktop actions.

The scoring functions in kyrin.stt.evaluation accept any SpeechToTextEngine.
The CLI never downloads models or audio files.
"""

import argparse
import json
import resource
import wave
from pathlib import Path
from time import monotonic

from kyrin.stt.backends.omnilingual import OmnilingualEngine
from kyrin.stt.backends.vosk import VoskEngine
from kyrin.stt.backends.whisper import WhisperEngine
from kyrin.stt.contracts import SpeechToTextEngine
from kyrin.stt.device import ComputeDevice, DevicePreference
from kyrin.stt.errors import SpeechToTextError
from kyrin.stt.evaluation import evaluate_item, load_corpus, summarize


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--model-path", required=True, type=Path)
    parser.add_argument(
        "--backend", choices=("vosk", "whisper", "omnilingual"), default="vosk"
    )
    parser.add_argument("--model-language", required=True)
    parser.add_argument("--whisper-server", type=Path)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--case-id", action="append", help="evaluate only these IDs")
    parser.add_argument(
        "--output", type=Path, help="new JSON report; never overwritten"
    )
    parser.add_argument(
        "--runtime-python",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "local-data/kyrin/runtimes/stt/omnilingual-asr/bin/python",
        help="isolated Python runtime used by Omnilingual ASR",
    )
    parser.add_argument("--chunk-ms", type=int, default=20)
    parser.add_argument("--device", choices=list(DevicePreference), default="auto")
    parser.add_argument(
        "--unpaced", action="store_true", help="process faster than realtime"
    )
    args = parser.parse_args(argv)
    if args.chunk_ms <= 0 or args.threads <= 0:
        parser.error("--chunk-ms and --threads must be positive")
    if args.backend == "whisper" and args.whisper_server is None:
        parser.error("Whisper requires --whisper-server")
    if args.backend == "vosk" and args.device == "gpu":
        parser.error("Vosk is CPU-only")
    if args.backend == "vosk" and args.model_language == "auto":
        parser.error("Vosk requires a fixed language")
    if args.output is not None and args.output.exists():
        parser.error("report already exists")
    try:
        corpus = load_corpus(args.manifest)
        if args.case_id:
            wanted = set(args.case_id)
            missing = wanted - {item.id for item in corpus}
            if missing:
                raise ValueError(f"unknown case IDs: {', '.join(sorted(missing))}")
            corpus = tuple(item for item in corpus if item.id in wanted)
        if args.model_language != "auto" and any(
            item.language != args.model_language for item in corpus
        ):
            raise ValueError("fixed model language must match every selected case")
        loading_started = monotonic()
        engine: SpeechToTextEngine
        if args.backend == "vosk":
            engine = VoskEngine(args.model_path, language=args.model_language)
        elif args.backend == "whisper":
            assert args.whisper_server is not None
            engine = WhisperEngine(
                args.whisper_server,
                args.model_path,
                language=args.model_language,
                threads=args.threads,
                compute_device=ComputeDevice(
                    "gpu" if args.device == "gpu" else "cpu"
                ),
            )
        else:
            engine = OmnilingualEngine(
                args.runtime_python,
                args.model_path,
                language=args.model_language,
                device=DevicePreference(args.device),
            )
        model_load_seconds = monotonic() - loading_started
        try:
            results = tuple(
                evaluate_item(
                    engine,
                    item,
                    chunk_ms=args.chunk_ms,
                    realtime=not args.unpaced,
                    device=DevicePreference(args.device),
                    engine_language=args.model_language,
                )
                for item in corpus
            )
        finally:
            engine.close()
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        wave.Error,
        SpeechToTextError,
    ) as exc:
        parser.exit(2, f"Evaluation input error: {exc}\n")
    report = summarize(results)
    report.update(
        {
            "backend": args.backend,
            "model": str(args.model_path.resolve()),
            "model_language": args.model_language,
            "requested_device": args.device,
            "model_load_seconds": model_load_seconds,
            "peak_child_rss_mib": round(
                resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024, 1
            ),
        }
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as target:
            json.dump(report, target, ensure_ascii=False, indent=2)
            target.write("\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
