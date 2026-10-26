"""Compare the same labeled WAV via direct STT and KYRIN's live VAD/STT path.

Both passes are paced at recorded speed. No microphone or desktop action is
used. Model load happens once before the passes; JSON reports contain text.
"""

import argparse
import json
import wave
from pathlib import Path

from kyrin.audio.activity.silero_vad import SileroVad
from kyrin.stt.backends.omnilingual import OmnilingualEngine
from kyrin.stt.backends.vosk import VoskEngine
from kyrin.stt.backends.whisper import WhisperEngine
from kyrin.stt.contracts import SpeechToTextEngine
from kyrin.stt.device import ComputeDevice, DevicePreference, SpeechToTextOptions
from kyrin.stt.errors import SpeechToTextError
from kyrin.stt.evaluation import load_corpus
from kyrin.stt.path_comparison import compare_item


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--backend", choices=("whisper", "vosk", "omnilingual"), required=True
    )
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--language", required=True, help="engine language or auto")
    parser.add_argument("--whisper-server", type=Path)
    parser.add_argument(
        "--runtime-python",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "local-data/kyrin/runtimes/stt/omnilingual-asr/bin/python",
    )
    parser.add_argument("--device", choices=("cpu", "gpu"), default="cpu")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--chunk-ms", type=int, default=20)
    parser.add_argument("--pause-confirm-ms", type=int, default=384)
    parser.add_argument(
        "--case-id", action="append", help="limit to one or more manifest IDs"
    )
    parser.add_argument("--output", type=Path, help="new JSON file; never overwritten")
    args = parser.parse_args(argv)
    if args.threads <= 0 or args.chunk_ms <= 0 or args.pause_confirm_ms <= 0:
        parser.error("threads, chunk-ms, and pause-confirm-ms must be positive")
    if args.backend == "whisper" and args.whisper_server is None:
        parser.error("Whisper requires --whisper-server")
    if args.backend == "vosk" and args.device != "cpu":
        parser.error("Vosk comparison is CPU-only")
    if args.backend == "vosk" and args.language == "auto":
        parser.error("Vosk requires a fixed model language")
    if args.output is not None and args.output.exists():
        parser.error("report already exists")
    try:
        cases = load_corpus(args.manifest)
        if args.case_id:
            wanted = set(args.case_id)
            missing = wanted - {case.id for case in cases}
            if missing:
                parser.error(f"unknown case IDs: {', '.join(sorted(missing))}")
            cases = tuple(case for case in cases if case.id in wanted)
        engine: SpeechToTextEngine
        if args.backend == "whisper":
            engine = WhisperEngine(
                args.whisper_server,
                args.model_path,
                language=args.language,
                threads=args.threads,
                compute_device=ComputeDevice(args.device),
            )
        elif args.backend == "vosk":
            engine = VoskEngine(args.model_path, language=args.language)
        else:
            engine = OmnilingualEngine(
                args.runtime_python,
                args.model_path,
                language=args.language,
                device=DevicePreference(args.device),
            )
        try:
            options = SpeechToTextOptions(
                device=DevicePreference(args.device), language_hint=args.language
            )
            results = [
                compare_item(
                    engine,
                    SileroVad,
                    case,
                    options=options,
                    chunk_ms=args.chunk_ms,
                    pause_confirm_ms=args.pause_confirm_ms,
                )
                for case in cases
            ]
        finally:
            engine.close()
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        wave.Error,
        SpeechToTextError,
    ) as exc:
        parser.exit(2, f"Comparison input error: {exc}\n")
    report = {
        "backend": args.backend,
        "model": str(args.model_path),
        "device": args.device,
        "engine_language": args.language,
        "pause_confirm_ms": args.pause_confirm_ms,
        "results": results,
    }
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as target:
            json.dump(report, target, ensure_ascii=False, indent=2)
            target.write("\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
