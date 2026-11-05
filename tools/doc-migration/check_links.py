#!/usr/bin/env python3
"""Deterministic Markdown link checker (standard library only).

Checks inline links, images, angle-bracket destinations and reference
definitions. Fenced code blocks (``` and ~~~) and inline code spans are
ignored. External URLs are not fetched. Absolute filesystem destinations are
reported as warnings because they do not resolve in another checkout.
Anchors use GitHub-style heading slugs; anchor problems are warnings unless
``--strict-anchors`` is given.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import git_paths, read_text, utc_now, write_json  # noqa: E402

SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
REFERENCE_DEFINITION = re.compile(r"^ {0,3}\[([^\]]+)\]:\s*(<[^>]*>|\S+)")
HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
HTML_ANCHOR = re.compile(r"""<a\s[^>]*(?:id|name)\s*=\s*["']([^"']+)["']""")
LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?$")


@dataclass
class Link:
    source: str
    line: int
    destination: str


@dataclass
class Report:
    checked_files: int = 0
    relative_links: int = 0
    anchors_checked: int = 0
    broken: list[dict[str, Any]] = field(default_factory=list)
    anchor_problems: list[dict[str, Any]] = field(default_factory=list)
    absolute_path_warnings: list[dict[str, Any]] = field(default_factory=list)


def strip_inline_code(line: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(line):
        if line[index] != "`":
            result.append(line[index])
            index += 1
            continue
        run = len(line[index:]) - len(line[index:].lstrip("`"))
        ticks = "`" * run
        end = line.find(ticks, index + run)
        if end == -1:
            result.append(ticks)
            index += run
            continue
        result.append(" " * (end + run - index))
        index = end + run
    return "".join(result)


def prose_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield (line number, text) outside fenced code blocks."""
    fence: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        match = FENCE.match(line)
        if fence is None and match:
            fence = match.group(1)
            continue
        if fence is not None:
            stripped = line.strip()
            if stripped.startswith(fence[0] * len(fence)) and not stripped.strip(
                fence[0]
            ):
                fence = None
            continue
        yield number, strip_inline_code(line)


def parse_destination(line: str, start: int) -> str | None:
    """Parse a link destination after '](' at index ``start``."""
    while start < len(line) and line[start] == " ":
        start += 1
    if start < len(line) and line[start] == "<":
        end = line.find(">", start)
        return None if end == -1 else line[start + 1 : end]
    depth = 0
    index = start
    while index < len(line):
        character = line[index]
        if character == "\\":
            index += 2
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            if depth == 0:
                break
            depth -= 1
        elif character in " \t" and depth == 0:
            break
        index += 1
    destination = line[start:index]
    return destination or None


def extract_links(source: str, text: str) -> list[Link]:
    links: list[Link] = []
    for number, line in prose_lines(text):
        definition = REFERENCE_DEFINITION.match(line)
        if definition:
            destination = definition.group(2).strip("<>")
            links.append(Link(source, number, destination))
            continue
        index = line.find("](")
        while index != -1:
            destination = parse_destination(line, index + 2)
            if destination is not None:
                links.append(Link(source, number, destination))
            index = line.find("](", index + 2)
    return links


def github_slug(heading: str) -> str:
    text = re.sub(r"<[^>]+>", "", heading)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.replace("`", "").lower()
    kept = []
    for character in text:
        category = unicodedata.category(character)
        if character in " -_" or category[0] in {"L", "N", "M"}:
            kept.append(character)
    return "".join(kept).replace(" ", "-")


def anchors_for(text: str) -> set[str]:
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for _, line in prose_lines(text):
        for match in HTML_ANCHOR.finditer(line):
            anchors.add(match.group(1))
        heading = HEADING.match(line)
        if not heading:
            continue
        slug = github_slug(heading.group(2))
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors


def check_files(root: Path, files: Sequence[str], strict_anchors: bool) -> Report:
    report = Report()
    anchor_cache: dict[Path, set[str]] = {}

    def anchors(path: Path) -> set[str]:
        if path not in anchor_cache:
            anchor_cache[path] = anchors_for(read_text(path))
        return anchor_cache[path]

    for relative in files:
        source = root / relative
        if not source.is_file():
            continue
        report.checked_files += 1
        for link in extract_links(relative, read_text(source)):
            destination = link.destination
            if SCHEME.match(destination):
                continue
            location = {"source": link.source, "line": link.line, "link": destination}
            path_part, _, fragment = destination.partition("#")
            path_part = unquote(path_part)
            if path_part.startswith("/"):
                report.absolute_path_warnings.append(location)
                continue
            if path_part:
                report.relative_links += 1
                target = (source.parent / path_part).resolve()
                if not target.exists():
                    trimmed = LINE_SUFFIX.sub("", path_part)
                    target = (source.parent / trimmed).resolve()
                if not target.exists():
                    report.broken.append(location)
                    continue
            else:
                target = source.resolve()
            if fragment and target.suffix.lower() == ".md" and target.is_file():
                report.anchors_checked += 1
                if unquote(fragment).lower() not in {
                    a.lower() for a in anchors(target)
                }:
                    report.anchor_problems.append(location)
    if strict_anchors:
        report.broken.extend(report.anchor_problems)
    return report


def default_files(root: Path) -> list[str]:
    return sorted(
        git_paths(root, "ls-files", "-z", "-co", "--exclude-standard", "--", "*.md")
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--output")
    parser.add_argument("--strict-anchors", action="store_true")
    parser.add_argument("files", nargs="*")
    arguments = parser.parse_args(argv)
    root = Path(arguments.root).resolve()
    files = arguments.files or default_files(root)
    report = check_files(root, files, arguments.strict_anchors)
    summary = {
        "created_utc": utc_now(),
        "checked_files": report.checked_files,
        "relative_links": report.relative_links,
        "broken": len(report.broken),
        "anchors_checked": report.anchors_checked,
        "anchor_problems": len(report.anchor_problems),
        "absolute_path_warnings": len(report.absolute_path_warnings),
    }
    if arguments.output:
        write_json(
            Path(arguments.output),
            {
                **summary,
                "broken_links": report.broken,
                "anchor_problem_links": report.anchor_problems,
                "absolute_path_links": report.absolute_path_warnings,
            },
        )
    print(" ".join(f"{key}={value}" for key, value in summary.items()))
    for item in report.broken[:50]:
        print(f"  BROKEN {item['source']}:{item['line']} -> {item['link']}")
    return 1 if report.broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
