"""Audit saved STT-to-command proposals against verified spoken references.

No microphone, local model, action gate, or desktop executor is invoked. The
links and audio manifests establish the spoken reference independently of the
STT text that the model saw. Output stays in a Git-ignored local report.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from kyrin.stt.evaluation import CorpusItem, edit_distance, load_corpus, normalize_text

ROOT = Path(__file__).resolve().parents[2]
LINKS = ROOT / "datasets/commands/verified_speech_links.jsonl"
STATUSES = {"resolved", "clarify", "no_action", "unsupported", "invalid_model_output"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{number} must contain a JSON object")
        rows.append(value)
    if not rows:
        raise ValueError(f"{path} has no records")
    return rows


def _unique(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"every record requires a nonempty {key}")
        if value in indexed:
            raise ValueError(f"duplicate {key}: {value}")
        indexed[value] = row
    return indexed


def audit(
    links: list[dict[str, Any]],
    clips: tuple[CorpusItem, ...],
    cases: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> dict[str, object]:
    by_case = _unique(cases, "id")
    by_link = _unique(links, "case_id")
    by_clip = {item.id: item for item in clips}
    if len(by_clip) != len(clips):
        raise ValueError("audio manifests contain duplicate clip IDs")
    prepared: dict[str, dict[str, object]] = {}
    for case_id, link in by_link.items():
        case = by_case.get(case_id)
        recording_id = link.get("recording_id")
        if not isinstance(recording_id, str):
            raise ValueError(f"missing recording ID for {case_id}")
        clip = by_clip.get(recording_id)
        if case is None or clip is None:
            raise ValueError(f"missing STT case or recorded clip for {case_id}")
        reference = link.get("spoken_reference")
        transcript = case.get("input_text")
        if (
            not isinstance(reference, str)
            or not normalize_text(reference)
            or normalize_text(reference) != normalize_text(clip.reference)
            or case.get("language") != clip.language
            or case.get("input_kind") != "stt_text"
            or not isinstance(transcript, str)
            or case.get("expected") != link.get("expected")
        ):
            raise ValueError(f"speech provenance or expected label differs: {case_id}")
        normalized_reference = normalize_text(reference)
        prepared[case_id] = {
            "recording_id": clip.id,
            "reference": reference,
            "stt_text": transcript,
            "language": clip.language,
            "stt_character_error_rate": edit_distance(
                normalized_reference, normalize_text(transcript)
            )
            / len(normalized_reference),
            "expected_route": link["expected"]["route"],
        }

    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for decision in decisions:
        decision_case_id = decision.get("case_id")
        model = decision.get("model")
        if (
            not isinstance(decision_case_id, str)
            or decision_case_id not in prepared
            or not isinstance(model, str)
            or not model
        ):
            raise ValueError("decision has an unknown case or model")
        key = (model, decision_case_id)
        if key in seen:
            raise ValueError(f"duplicate model/case decision: {key}")
        seen.add(key)
        entry = prepared[decision_case_id]
        status = decision.get("resolved_status")
        correct = decision.get("correct_resolved_proposal")
        unsafe = decision.get("unsafe_resolved_proposal")
        if (
            status not in STATUSES
            or not isinstance(correct, bool)
            or not isinstance(unsafe, bool)
            or decision.get("expected_route") != entry["expected_route"]
            or (status == "resolved") != (correct or unsafe)
            or (correct and unsafe)
        ):
            raise ValueError(f"inconsistent decision for {key}")
        expected_route = entry["expected_route"]
        classification = (
            "unsafe_action"
            if unsafe
            else "correct_action"
            if correct
            else "missed_action"
            if expected_route == "execute"
            else "correct_no_action"
            if expected_route == "no_action" and status == "no_action"
            else "non_action_or_uncertain"
        )
        counts[model][classification] += 1
        rows.append(
            {
                "model": model,
                "case_id": decision_case_id,
                **entry,
                "decision_status": status,
                "classification": classification,
            }
        )
    for model in counts:
        missing = set(prepared) - {case_id for name, case_id in seen if name == model}
        if missing:
            raise ValueError(f"missing decisions for {model}: {sorted(missing)}")
    return {
        "recordings": len(prepared),
        "models": {model: dict(total) for model, total in sorted(counts.items())},
        "items": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--links", type=Path, default=LINKS)
    parser.add_argument("--case-file", type=Path, required=True)
    parser.add_argument("--decision-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    try:
        clips = tuple(
            item for manifest in args.manifest for item in load_corpus(manifest)
        )
        report = audit(
            read_jsonl(args.links),
            clips,
            read_jsonl(args.case_file),
            read_jsonl(args.decision_report),
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps(report["models"], ensure_ascii=False))
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
