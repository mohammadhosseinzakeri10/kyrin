#!/usr/bin/env python3
"""Static context-size indicators for agent instructions and documentation.

Reports deterministic measurements only: bytes, characters, lines, headings
and Persian-letter ratio. It does not measure model token consumption,
instruction loading or skill activation; those require runtime evidence.
An optional rough token figure is labeled approximate and must not be used
as evidence of actual consumption or savings.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    git_paths,
    persian_ratio,
    read_text,
    utc_now,
    write_json,
)

HEADING = re.compile(r"^#{1,6}\s", re.MULTILINE)
REPOSITORY_INSTRUCTION_FILES = ["AGENTS.md", "CLAUDE.md", "AGENTS.override.md"]
ROUGH_CHARACTERS_PER_TOKEN = 4


def measure(path: Path, rough_tokens: bool) -> dict[str, Any]:
    text = read_text(path)
    result: dict[str, Any] = {
        "bytes": path.stat().st_size,
        "characters": len(text),
        "lines": text.count("\n"),
        "headings": len(HEADING.findall(text)),
        "persian_ratio": persian_ratio(text),
    }
    if rough_tokens:
        result["rough_token_estimate_approximate_only"] = (
            len(text) // ROUGH_CHARACTERS_PER_TOKEN
        )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--output")
    parser.add_argument(
        "--global-instructions",
        action="append",
        default=[],
        help="Read-only size measurement of a user-global instruction file.",
    )
    parser.add_argument("--rough-token-estimate", action="store_true")
    parser.add_argument("--top", type=int, default=15)
    arguments = parser.parse_args(argv)
    root = Path(arguments.root).resolve()

    repository = {
        name: measure(root / name, arguments.rough_token_estimate)
        for name in REPOSITORY_INSTRUCTION_FILES
        if (root / name).is_file()
    }
    global_files = {
        name: measure(Path(name).expanduser(), arguments.rough_token_estimate)
        for name in arguments.global_instructions
        if Path(name).expanduser().is_file()
    }
    referenced: dict[str, Any] = {}
    if (root / "PROJECT_CONTEXT.md").is_file():
        referenced["PROJECT_CONTEXT.md"] = measure(
            root / "PROJECT_CONTEXT.md", arguments.rough_token_estimate
        )
    markdown = sorted(
        git_paths(root, "ls-files", "-z", "-co", "--exclude-standard", "--", "*.md")
    )
    documents = {
        path: measure(root / path, False)
        for path in markdown
        if (root / path).is_file()
    }
    by_directory: dict[str, dict[str, int]] = {}
    for path, values in documents.items():
        directory = path.rsplit("/", 1)[0] if "/" in path else "."
        bucket = by_directory.setdefault(directory, {"files": 0, "bytes": 0})
        bucket["files"] += 1
        bucket["bytes"] += values["bytes"]
    language = {"persian_majority": 0, "mixed": 0, "english_majority": 0}
    language_bytes = dict.fromkeys(language, 0)
    for values in documents.values():
        ratio = values["persian_ratio"]
        key = (
            "persian_majority"
            if ratio >= 0.5
            else "mixed"
            if ratio >= 0.05
            else "english_majority"
        )
        language[key] += 1
        language_bytes[key] += values["bytes"]
    largest = sorted(documents.items(), key=lambda item: -item[1]["bytes"])
    report = {
        "created_utc": utc_now(),
        "method": (
            "Static file measurements only; not model token consumption, "
            "instruction loading or skill activation."
        ),
        "repository_instruction_files": repository,
        "user_global_instruction_files_read_only": global_files,
        "instruction_referenced_files": referenced,
        "markdown_totals": {
            "files": len(documents),
            "bytes": sum(v["bytes"] for v in documents.values()),
            "language_files": language,
            "language_bytes": language_bytes,
        },
        "by_directory": dict(sorted(by_directory.items())),
        "largest": [
            {"path": path, **values} for path, values in largest[: arguments.top]
        ],
    }
    if arguments.output:
        write_json(Path(arguments.output), report)
    print(json.dumps({k: report[k] for k in list(report)[2:6]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
