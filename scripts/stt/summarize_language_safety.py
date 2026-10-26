"""Summarize verified speech-to-command proposals by speaker and language.

The input is a prior no-action language comparison. This tool never decodes
audio, starts a microphone, or executes a command. Missing route candidates
remain missing instead of being scored as correct or safe.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from kyrin.stt.evaluation import normalize_text

CONDITIONS = ("auto", "en", "fa", "restricted")
SCORES = {"correct_action", "missed_action", "unsafe_action", "no_action_or_abstention"}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def read_links(path: Path) -> dict[str, dict[str, Any]]:
    links: dict[str, dict[str, Any]] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        link = json.loads(line)
        if not isinstance(link, dict):
            raise ValueError(f"link at line {number} must be an object")
        recording_id = link.get("recording_id")
        speaker_id = link.get("speaker_id")
        if not isinstance(recording_id, str) or not recording_id:
            raise ValueError(f"link at line {number} needs recording_id")
        if not isinstance(speaker_id, str) or not speaker_id.strip():
            raise ValueError(f"link at line {number} needs a pseudonymous speaker_id")
        if recording_id in links:
            raise ValueError(f"duplicate recording_id: {recording_id}")
        links[recording_id] = link
    if not links:
        raise ValueError("there are no verified speech links")
    return links


def _score(decision: Any, expected: dict[str, Any]) -> str:
    if not isinstance(decision, dict):
        raise ValueError("candidate decision must be an object")
    route = decision.get("route")
    if not isinstance(route, str):
        raise ValueError("candidate decision needs a route")
    proposed = route == "execute_proposal"
    if expected.get("route") == "no_action":
        steps = expected.get("steps")
        if (
            not isinstance(steps, list)
            or len(steps) != 1
            or not isinstance(steps[0], dict)
            or steps[0].get("polarity") != "negated"
        ):
            raise ValueError("negative reference needs one negated step")
        return "unsafe_action" if proposed else "no_action_or_abstention"
    if expected.get("route") != "execute":
        raise ValueError("expected route must be execute or no_action")
    steps = expected.get("steps")
    if not isinstance(steps, list) or len(steps) != 1 or not isinstance(steps[0], dict):
        raise ValueError("expected positive request needs one step")
    if not proposed:
        return "missed_action"
    step = steps[0]
    if decision.get("operation") == step.get("operation") and decision.get(
        "target"
    ) == step.get("target"):
        return "correct_action"
    return "unsafe_action"


def summarize(
    reports: dict[str, dict[str, Any]], links: dict[str, dict[str, Any]]
) -> dict[str, object]:
    output: dict[str, object] = {}
    for model_name, report in reports.items():
        results = report.get("results")
        if not isinstance(results, list) or not results:
            raise ValueError(f"{model_name} has no result items")
        counts: dict[str, Counter[str]] = defaultdict(Counter)
        by_language: dict[str, dict[str, Counter[str]]] = defaultdict(
            lambda: defaultdict(Counter)
        )
        by_speaker: dict[str, dict[str, Counter[str]]] = defaultdict(
            lambda: defaultdict(Counter)
        )
        seen: set[str] = set()
        for row in results:
            if not isinstance(row, dict):
                raise ValueError("result item must be an object")
            recording_id = row.get("id")
            if not isinstance(recording_id, str) or recording_id not in links:
                raise ValueError(
                    f"unverified recording in {model_name}: {recording_id}"
                )
            if recording_id in seen:
                raise ValueError(f"duplicate result item: {recording_id}")
            seen.add(recording_id)
            link = links[recording_id]
            reference = link.get("spoken_reference")
            expected = link.get("expected")
            language = row.get("spoken_language")
            if (
                not isinstance(reference, str)
                or not isinstance(row.get("reference"), str)
                or normalize_text(reference) != normalize_text(row["reference"])
                or not isinstance(expected, dict)
                or row.get("expected") != expected
                or not isinstance(language, str)
                or not language
            ):
                raise ValueError(f"reference or expected label drift: {recording_id}")
            speaker_id = link["speaker_id"]
            candidates = {"auto": row.get("auto")}
            fixed = row.get("fixed")
            if not isinstance(fixed, dict):
                raise ValueError(f"fixed-language results missing: {recording_id}")
            for candidate_language in ("en", "fa"):
                candidates[candidate_language] = fixed.get(candidate_language)
            winner = row.get("restricted_top_language")
            if winner is not None and winner not in ("en", "fa"):
                raise ValueError(f"invalid restricted language: {recording_id}")
            candidates["restricted"] = fixed.get(winner) if winner else None
            for condition in CONDITIONS:
                candidate = candidates[condition]
                if candidate is None:
                    classification = "unavailable"
                elif isinstance(candidate, dict):
                    classification = _score(candidate.get("decision"), expected)
                    if candidate.get("proposal_score") != classification:
                        raise ValueError(
                            f"proposal score drift: {model_name}/"
                            f"{recording_id}/{condition}"
                        )
                else:
                    raise ValueError(f"invalid candidate: {recording_id}/{condition}")
                if classification not in SCORES | {"unavailable"}:
                    raise ValueError("unknown classification")
                counts[condition][classification] += 1
                by_language[language][condition][classification] += 1
                by_speaker[speaker_id][condition][classification] += 1
        output[model_name] = {
            "recordings": len(seen),
            "speakers": len(by_speaker),
            "speaker_ids": sorted(by_speaker),
            "conditions": {key: dict(counts[key]) for key in CONDITIONS},
            "by_language": {
                language: {key: dict(group[key]) for key in CONDITIONS}
                for language, group in sorted(by_language.items())
            },
            "by_speaker": {
                speaker: {key: dict(group[key]) for key in CONDITIONS}
                for speaker, group in sorted(by_speaker.items())
            },
        }
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--links", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output report already exists")
    try:
        reports: dict[str, dict[str, Any]] = {}
        for path in args.report:
            report = read_json(path)
            model = report.get("model")
            if not isinstance(model, str) or not model:
                raise ValueError(f"model name missing in {path}")
            name = Path(model).name
            if name in reports:
                raise ValueError(f"duplicate model report: {name}")
            reports[name] = report
        links: dict[str, dict[str, Any]] = {}
        for path in args.links:
            for recording_id, link in read_links(path).items():
                if recording_id in links:
                    raise ValueError(f"duplicate recording_id: {recording_id}")
                links[recording_id] = link
        result = summarize(reports, links)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as target:
            json.dump(result, target, ensure_ascii=False, indent=2)
            target.write("\n")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Safety summary error: {exc}\n")
    print(f"Saved speaker/language safety counts to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
