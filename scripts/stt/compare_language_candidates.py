"""Probe short-command language routing without changing KYRIN's live path.

One local whisper.cpp server decodes each labeled WAV in auto, English, and
Persian modes. The restricted-probability winner is diagnostic, not a routing
policy. A fresh demo interpreter checks possible commands; nothing executes.
"""

import argparse
import json
import math
import wave
from collections.abc import Iterator, Mapping
from pathlib import Path
from time import monotonic

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.sample_rate_converter import SampleRateConverter
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.interpreter import ReadyCommand
from kyrin.commands.models import CommandContext
from kyrin.stt.backends.whisper_server import WhisperCppServer
from kyrin.stt.device import ComputeDevice, SpeechToTextOptions
from kyrin.stt.errors import SpeechToTextError
from kyrin.stt.evaluation import CorpusItem, load_corpus, normalize_text


def read_pcm16_mono(path: Path) -> bytes:
    """Read PCM WAV and convert it to Whisper's 16 kHz input format."""
    with wave.open(str(path), "rb") as audio:
        if (
            audio.getcomptype() != "NONE"
            or audio.getnchannels() != 1
            or audio.getsampwidth() != 2
        ):
            raise ValueError("WAV must be uncompressed mono 16-bit PCM")
        source_format = AudioFormat(audio.getframerate(), 1, AudioSampleFormat.INT16)

        def chunks() -> Iterator[AudioData]:
            while data := audio.readframes(4096):
                yield AudioData(data, source_format)

        converter = SampleRateConverter(source_format, 16_000)
        return b"".join(chunk.data for chunk in converter.convert(chunks()))


def restricted_winner(
    probabilities: Mapping[str, float], enabled: tuple[str, ...]
) -> tuple[str, float, float]:
    """Report the restricted top score and margin, without authorizing it."""
    if len(enabled) < 2 or len(set(enabled)) != len(enabled):
        raise ValueError("enabled languages must be distinct and include at least two")
    if any(language not in probabilities for language in enabled):
        raise ValueError("language probabilities are missing an enabled language")
    if any(
        not math.isfinite(probabilities[language])
        or not 0 <= probabilities[language] <= 1
        for language in enabled
    ):
        raise ValueError("language probabilities must be finite values in [0, 1]")
    ranked = sorted(
        ((language, probabilities[language]) for language in enabled),
        key=lambda pair: (-pair[1], pair[0]),
    )
    return ranked[0][0], ranked[0][1], ranked[0][1] - ranked[1][1]


def interpret_without_action(text: str, language: str) -> dict[str, str | None]:
    """Interpret one final text only; no ActionGate or executor is called."""
    result = DemoCommandInterpreter().interpret(
        text, language=language, context=CommandContext(), pending=None
    )
    if isinstance(result, ReadyCommand):
        return {
            "route": "execute_proposal",
            "operation": result.intent.kind.value,
            "target": result.intent.target,
        }
    return {"route": type(result).__name__, "operation": None, "target": None}


def score_proposal(
    decision: Mapping[str, str | None], expected: Mapping[str, object]
) -> str:
    """Score action proposals; no-action on gibberish is only abstention."""
    steps = expected.get("steps")
    proposed = decision["route"] == "execute_proposal"
    if expected.get("route") == "no_action":
        if not isinstance(steps, list) or len(steps) > 1:
            raise ValueError("no-action reference permits zero or one step")
        if steps and not isinstance(steps[0], dict):
            raise ValueError("expected step must be an object")
        return "unsafe_action" if proposed else "no_action_or_abstention"
    if expected.get("route") != "execute":
        raise ValueError("expected route must be execute or no_action")
    if not isinstance(steps, list) or len(steps) != 1:
        raise ValueError("one expected step is required")
    step = steps[0]
    if not isinstance(step, dict):
        raise ValueError("expected step must be an object")
    if not proposed:
        return "missed_action"
    if decision["operation"] == step.get("operation") and decision[
        "target"
    ] == step.get("target"):
        return "correct_action"
    return "unsafe_action"


def load_verified_links(path: Path) -> dict[str, dict[str, object]]:
    links: dict[str, dict[str, object]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or not isinstance(row.get("recording_id"), str):
            raise ValueError("verified link must name a recording")
        recording_id = row["recording_id"]
        if recording_id in links:
            raise ValueError(f"duplicate verified recording: {recording_id}")
        links[recording_id] = row
    return links


def verified_expectation(
    item: CorpusItem, links: Mapping[str, dict[str, object]]
) -> Mapping[str, object]:
    link = links.get(item.id)
    if link is None:
        raise ValueError(f"no verified spoken reference for {item.id}")
    spoken_reference = link.get("spoken_reference")
    if not isinstance(spoken_reference, str):
        raise ValueError(f"no verified spoken reference for {item.id}")
    if normalize_text(spoken_reference) != normalize_text(item.reference):
        raise ValueError(f"spoken reference mismatch for {item.id}")
    expected = link.get("expected")
    if not isinstance(expected, dict):
        raise ValueError(f"missing expected decision for {item.id}")
    return expected


def inspect_item(
    server: WhisperCppServer,
    item: CorpusItem,
    expected: Mapping[str, object],
    enabled: tuple[str, ...],
    hints: tuple[str, ...] = (),
) -> dict[str, object]:
    pcm = read_pcm16_mono(item.path)
    started = monotonic()
    # Diagnostic-only server metadata is deliberately outside the portable STT
    # contract. It must never become a production action confidence score.
    auto = server._request_inference(pcm, "auto", "verbose_json", hints)
    auto_seconds = monotonic() - started
    probabilities = auto.get("language_probabilities")
    if not isinstance(probabilities, dict):
        raise ValueError("whisper-server did not return language probabilities")
    valid_probabilities = {
        key: float(value)
        for key, value in probabilities.items()
        if isinstance(key, str) and isinstance(value, int | float)
    }
    # whisper.cpp reports only its top language probabilities. If an enabled
    # language is absent, its score is unknown rather than zero.
    restricted_available = all(language in valid_probabilities for language in enabled)
    if restricted_available:
        winner, top_score, margin = restricted_winner(valid_probabilities, enabled)
    else:
        winner, top_score, margin = None, None, None
    auto_text = auto.get("text")
    if not isinstance(auto_text, str):
        raise ValueError("whisper-server did not return text")
    auto_language = str(auto.get("language", "unknown"))
    auto_decision = interpret_without_action(auto_text.strip(), auto_language)
    fixed: dict[str, dict[str, object]] = {}
    for language in enabled:
        started = monotonic()
        text = server.transcribe(pcm, language, hints=hints)
        elapsed = monotonic() - started
        decision = interpret_without_action(text, language)
        fixed[language] = {
            "text": text,
            "inference_seconds": elapsed,
            "decision": decision,
            "proposal_score": score_proposal(decision, expected),
        }
    return {
        "id": item.id,
        "spoken_language": item.language,
        "reference": item.reference,
        "expected": expected,
        "auto": {
            "text": auto_text.strip(),
            "attributed_language": auto_language,
            "inference_seconds": auto_seconds,
            "decision": auto_decision,
            "proposal_score": score_proposal(auto_decision, expected),
        },
        "enabled_probabilities": {
            language: valid_probabilities.get(language) for language in enabled
        },
        "restricted_top_language": winner,
        "restricted_top_score": top_score,
        "restricted_margin": margin,
        "restricted_top_proposal_score": (
            fixed[winner]["proposal_score"] if winner is not None else None
        ),
        "fixed": fixed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--verified-links", type=Path, action="append", required=True)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "gpu"), default="gpu")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument(
        "--vocabulary-hint",
        action="append",
        default=[],
        help="fixed decoder-context term; applies unchanged to every recording",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.threads <= 0:
        parser.error("threads must be positive")
    if args.output.exists():
        parser.error("output report already exists")
    try:
        hints = SpeechToTextOptions(
            vocabulary_hints=tuple(args.vocabulary_hint)
        ).vocabulary_hints
        items = tuple(
            item for manifest in args.manifest for item in load_corpus(manifest)
        )
        if len({item.id for item in items}) != len(items):
            raise ValueError("duplicate recording IDs across manifests")
        links: dict[str, dict[str, object]] = {}
        for path in args.verified_links:
            for recording_id, link in load_verified_links(path).items():
                if recording_id in links:
                    raise ValueError(f"duplicate verified recording: {recording_id}")
                links[recording_id] = link
        expected = {item.id: verified_expectation(item, links) for item in items}
        loaded_at = monotonic()
        server = WhisperCppServer(
            args.server,
            args.model,
            threads=args.threads,
            compute_device=ComputeDevice(args.device),
        )
        model_load_seconds = monotonic() - loaded_at
        try:
            results = [
                inspect_item(server, item, expected[item.id], ("en", "fa"), hints)
                for item in items
            ]
        finally:
            server.close()
    except (OSError, ValueError, wave.Error, SpeechToTextError) as exc:
        parser.exit(2, f"Language comparison error: {exc}\n")
    report = {
        "model": str(args.model),
        "device": args.device,
        "enabled_languages": ["en", "fa"],
        "vocabulary_hints": list(hints),
        "model_load_seconds": model_load_seconds,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
        target.write("\n")
    print(f"Saved {len(results)} diagnostic cases to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
