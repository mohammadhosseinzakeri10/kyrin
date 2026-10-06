"""Evaluate a local Vosk model on a labeled WAV corpus without microphone access.

The scoring functions in kyrin.stt.evaluation accept any SpeechToTextEngine.
This CLI currently loads Vosk and never downloads models or audio files.
"""

import argparse
import json
import wave
from pathlib import Path
from time import monotonic

from kyrin.stt.backends.vosk import VoskEngine
from kyrin.stt.device import DevicePreference
from kyrin.stt.errors import SpeechToTextError
from kyrin.stt.evaluation import evaluate_item, load_corpus, summarize


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--model-path", required=True, type=Path)
    parser.add_argument("--model-language", required=True)
    parser.add_argument("--chunk-ms", type=int, default=20)
    parser.add_argument("--device", choices=list(DevicePreference), default="auto")
    parser.add_argument(
        "--unpaced", action="store_true", help="process faster than realtime"
    )
    args = parser.parse_args(argv)
    if args.chunk_ms <= 0:
        parser.error("--chunk-ms must be positive")
    try:
        corpus = load_corpus(args.manifest)
        loading_started = monotonic()
        engine = VoskEngine(args.model_path, language=args.model_language)
        model_load_seconds = monotonic() - loading_started
        try:
            results = tuple(
                evaluate_item(
                    engine,
                    item,
                    chunk_ms=args.chunk_ms,
                    realtime=not args.unpaced,
                    device=DevicePreference(args.device),
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
    report["model_load_seconds"] = model_load_seconds
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
