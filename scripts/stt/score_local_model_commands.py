"""Score STT reports against verified spoken commands without executing actions.

This uses the bounded demo interpreter as a diagnostic. Its proposals are not
the full live desktop path, and an abstention is not a correct command.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from kyrin.stt.evaluation import CorpusItem
from scripts.stt.compare_language_candidates import (
    interpret_without_action,
    load_verified_links,
    score_proposal,
    verified_expectation,
)

ROOT = Path(__file__).resolve().parents[2]

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument(
        "--verified-links",
        type=Path,
        default=ROOT / "datasets/commands/verified_speech_links.jsonl",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    output = args.output or args.summary.parent / "decision-summary.json"
    if output.exists():
        parser.error("decision report already exists")
    try:
        summary = json.loads(args.summary.read_text(encoding="utf-8"))
        links = load_verified_links(args.verified_links)
        rows = []
        for model in summary["rows"]:
            if model["status"] != "completed":
                continue
            candidate = model["model"]
            language = model["language"]
            detail = args.summary.parent / f"{candidate}-{language}.json"
            report = json.loads(detail.read_text(encoding="utf-8"))
            counts: Counter[str] = Counter()
            cases = []
            for result in report["results"]:
                item = CorpusItem(
                    result["id"], Path(), result["language"], result["reference"]
                )
                if item.id not in links:
                    continue
                expected = verified_expectation(item, links)
                decision = interpret_without_action(
                    result["transcript"], item.language
                )
                score = score_proposal(decision, expected)
                counts[score] += 1
                cases.append(
                    {
                        "id": item.id,
                        "transcript": result["transcript"],
                        "score": score,
                        "proposal": decision,
                    }
                )
            rows.append(
                {
                    "model": candidate,
                    "language": language,
                    "verified_cases": len(cases),
                    "counts": dict(counts),
                    "cases": cases,
                }
            )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Decision scoring error: {exc}\n")
    with output.open("x", encoding="utf-8") as target:
        json.dump(
            {
                "method": "bounded demo interpreter; proposal only; no actions",
                "source_summary": str(args.summary.resolve()),
                "rows": rows,
            },
            target,
            ensure_ascii=False,
            indent=2,
        )
        target.write("\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
