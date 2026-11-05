#!/usr/bin/env python3
"""Inventory, snapshot, comparison, backup and read-only planning tools.

Subcommands:
  snapshot               Record every tracked and untracked (non-ignored) path.
  compare                Compare two snapshots against a write allowlist.
  backup                 Copy the snapshot scope and .git to a new private
                         directory without following symbolic links.
  verify-backup          Re-hash a backup against its snapshot.
  check-existing-backup  Read-only comparison of an older backup.
  privacy-scan           Heuristic flags for Markdown files; never certifies
                         a file as public-safe.
  package-scope          Static approximation of source-distribution
                         inclusion from MANIFEST.in and pyproject.toml.
  restore-plan           Read-only plan; this tool performs no restoration.
  manifest               Build the migration manifest for Markdown files.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import sys
import tomllib
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    Entry,
    MigrationToolError,
    content_identity,
    describe_path,
    ensure_output_outside_inventory,
    git_bytes,
    git_paths,
    git_returncode,
    git_text,
    is_within,
    load_json,
    matches_any,
    persian_ratio,
    read_text,
    sha256_bytes,
    sha256_regular_file,
    split_nul,
    utc_now,
    write_json,
)

SNAPSHOT_FORMAT = "kyrin-doc-migration-snapshot/1"
BACKUP_STATEMENT = (
    "Source-and-Git backup: tracked, modified and untracked non-ignored paths "
    "plus the complete .git directory. Git-ignored paths are excluded. This is "
    "not a system backup."
)


# --------------------------------------------------------------------------
# Snapshot
# --------------------------------------------------------------------------


def parse_porcelain(data: bytes) -> list[dict[str, str]]:
    tokens = split_nul(data)
    entries: list[dict[str, str]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        record = {"xy": token[:2], "path": token[3:]}
        index += 1
        if record["xy"][0] in "RC" and index < len(tokens):
            record["orig_path"] = tokens[index]
            index += 1
        entries.append(record)
    return entries


def status_key(entries: list[dict[str, str]]) -> list[tuple[str, str, str]]:
    return sorted(
        (item["xy"], item["path"], item.get("orig_path", "")) for item in entries
    )


def empty_directories(root: Path) -> list[str]:
    with_empty = git_paths(
        root, "ls-files", "-z", "-o", "--exclude-standard", "--directory"
    )
    without_empty = set(
        git_paths(
            root,
            "ls-files",
            "-z",
            "-o",
            "--exclude-standard",
            "--directory",
            "--no-empty-directory",
        )
    )
    return sorted(
        path.rstrip("/")
        for path in with_empty
        if path.endswith("/") and path not in without_empty
    )


def take_snapshot(root: Path, label: str) -> dict[str, Any]:
    root = root.resolve()
    tracked = git_paths(root, "ls-files", "-z")
    untracked = git_paths(root, "ls-files", "-z", "-o", "--exclude-standard")
    deleted = set(git_paths(root, "ls-files", "-z", "-d"))
    status = parse_porcelain(
        git_bytes(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    )
    status_by_path = {item["path"]: item["xy"] for item in status}
    branch = git_text(root, "symbolic-ref", "-q", "HEAD", check=False)
    origin_ref = git_text(
        root, "rev-parse", "-q", "--verify", "refs/remotes/origin/main", check=False
    )
    origin_paths: set[str] = set()
    if origin_ref:
        origin_paths = set(
            git_paths(root, "ls-tree", "-r", "-z", "--name-only", origin_ref)
        )
    ignored_top = sorted(
        {
            path.split("/", 1)[0]
            for path in git_paths(
                root,
                "ls-files",
                "-z",
                "-o",
                "-i",
                "--exclude-standard",
                "--directory",
            )
        }
    )
    entries: dict[str, Entry] = {}
    for path in tracked:
        entry = describe_path(root / path)
        if path in deleted:
            entry["git_state"] = "tracked-deleted"
        elif path in status_by_path:
            entry["git_state"] = "tracked-modified"
            entry["git_xy"] = status_by_path[path]
        else:
            entry["git_state"] = "tracked-clean"
        entry["in_local_origin_main_ref"] = path in origin_paths
        entries[path] = entry
    for path in untracked:
        entry = describe_path(root / path)
        entry["git_state"] = "untracked"
        entry["in_local_origin_main_ref"] = path in origin_paths
        entries[path] = entry
    counts: dict[str, int] = {}
    for entry in entries.values():
        counts[entry["git_state"]] = counts.get(entry["git_state"], 0) + 1
    return {
        "format": SNAPSHOT_FORMAT,
        "label": label,
        "created_utc": utc_now(),
        "root": str(root),
        "branch_ref": branch or "DETACHED",
        "head": git_text(root, "rev-parse", "HEAD", check=False),
        "local_origin_main_ref": origin_ref or None,
        "publication_note": (
            "in_local_origin_main_ref reflects only the locally stored "
            "refs/remotes/origin/main; actual remote availability is unverified."
        ),
        "counts": counts,
        "status_porcelain": status,
        "empty_directories": empty_directories(root),
        "ignored_top_level_excluded": ignored_top,
        "entries": entries,
    }


def command_snapshot(arguments: argparse.Namespace) -> int:
    root = Path(arguments.root).resolve()
    output = Path(arguments.output).resolve()
    ensure_output_outside_inventory(root, output)
    snapshot = take_snapshot(root, arguments.label)
    write_json(output, snapshot)
    print(f"snapshot {arguments.label}: {snapshot['counts']} -> {output}")
    return 0


# --------------------------------------------------------------------------
# Compare
# --------------------------------------------------------------------------


def diff_snapshots(
    before: dict[str, Any], after: dict[str, Any], allow: Sequence[str]
) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    metadata_only: list[str] = []
    before_entries: dict[str, Entry] = before["entries"]
    after_entries: dict[str, Entry] = after["entries"]
    for path in sorted(set(before_entries) | set(after_entries)):
        old = before_entries.get(path, {"type": "absent"})
        new = after_entries.get(path, {"type": "absent"})
        if content_identity(old) == content_identity(new):
            if old.get("git_state") != new.get("git_state"):
                changes.append(
                    {
                        "path": path,
                        "kind": "git-state",
                        "before": old.get("git_state"),
                        "after": new.get("git_state"),
                        "allowed": matches_any(path, allow),
                    }
                )
            elif old.get("mtime_ns") != new.get("mtime_ns"):
                metadata_only.append(path)
            continue
        if old["type"] == "absent":
            kind = "added"
        elif new["type"] == "absent":
            kind = "removed"
        elif old["type"] != new["type"]:
            kind = "type-changed"
        elif old.get("sha256") != new.get("sha256"):
            kind = "content-changed"
        else:
            kind = "mode-changed"
        changes.append(
            {"path": path, "kind": kind, "allowed": matches_any(path, allow)}
        )
    header_changes = [
        key
        for key in ("branch_ref", "head", "local_origin_main_ref")
        if before.get(key) != after.get(key)
    ]
    empty_before = set(before.get("empty_directories", []))
    empty_after = set(after.get("empty_directories", []))
    empty_changes = sorted(
        path for path in empty_before ^ empty_after if not matches_any(path, allow)
    )
    unallowed = [change for change in changes if not change["allowed"]]
    return {
        "before": before["label"],
        "after": after["label"],
        "allow": list(allow),
        "changes": changes,
        "unallowed_changes": unallowed,
        "metadata_only_mtime_changes": metadata_only,
        "header_changes": header_changes,
        "empty_directory_changes_outside_allowlist": empty_changes,
        "passed": not unallowed and not header_changes and not empty_changes,
    }


def command_compare(arguments: argparse.Namespace) -> int:
    report = diff_snapshots(
        load_json(Path(arguments.before)),
        load_json(Path(arguments.after)),
        arguments.allow,
    )
    if arguments.output:
        write_json(Path(arguments.output), report)
    print(
        f"compare {report['before']} -> {report['after']}: "
        f"{len(report['changes'])} change(s), "
        f"{len(report['unallowed_changes'])} outside allowlist, "
        f"header changes {report['header_changes']}, "
        f"mtime-only {len(report['metadata_only_mtime_changes'])}"
    )
    for change in report["unallowed_changes"]:
        print(f"  UNALLOWED {change['kind']}: {change['path']!r}")
    return 0 if report["passed"] else 1


# --------------------------------------------------------------------------
# Safe path handling and backup
# --------------------------------------------------------------------------


def safe_join(base: Path, relative: str) -> Path:
    """Join without traversing a symbolic link in any parent component."""
    parts = Path(relative).parts
    if Path(relative).is_absolute() or ".." in parts:
        raise MigrationToolError(f"unsafe relative path: {relative!r}")
    current = base
    for part in parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise MigrationToolError(f"symbolic link in parent path: {current}")
    return base / relative


def walk_no_follow(base: Path) -> Iterator[tuple[str, Entry]]:
    for directory, subdirectories, files in os.walk(base, followlinks=False):
        current = Path(directory)
        for name in sorted(subdirectories + files):
            path = current / name
            yield path.relative_to(base).as_posix(), describe_path(path)


def tree_digest(base: Path) -> dict[str, Any]:
    listing = sorted(
        (relative, content_identity(entry))
        for relative, entry in walk_no_follow(base)
        if entry["type"] != "directory"
    )
    digest = sha256_bytes(repr(listing).encode("utf-8", "surrogateescape"))
    return {"objects": len(listing), "sha256": digest}


def git_refs(git_dir: Path) -> str:
    return git_text(
        git_dir.parent,
        f"--git-dir={git_dir}",
        "for-each-ref",
        "--format=%(refname) %(objectname)",
    )


def copy_entry(source: Path, destination: Path, expected: Entry) -> None:
    current = describe_path(source)
    if content_identity(current) != content_identity(expected):
        raise MigrationToolError(f"source changed after snapshot: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if expected["type"] == "symlink":
        os.symlink(os.readlink(source), destination)
    else:
        shutil.copy2(source, destination, follow_symlinks=False)
    copied = describe_path(destination)
    if content_identity(copied) != content_identity(expected):
        raise MigrationToolError(f"copy mismatch: {destination}")


def copy_directory_modes(root: Path, tree: Path, relatives: set[str]) -> None:
    for relative in sorted(relatives, key=lambda item: item.count("/"), reverse=True):
        source = root / relative
        if source.is_dir() and not source.is_symlink():
            shutil.copystat(source, tree / relative, follow_symlinks=False)


def write_checksums(path: Path, entries: dict[str, Entry]) -> None:
    lines: list[str] = []
    for relative, entry in sorted(entries.items()):
        if entry["type"] != "file":
            continue
        name = relative
        prefix = ""
        if "\\" in name or "\n" in name or "\r" in name:
            prefix = "\\"
            name = name.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
        lines.append(f"{prefix}{entry['sha256']}  {name}")
    path.write_text("\n".join(lines) + "\n", errors="surrogateescape")


def create_backup(root: Path, snapshot_path: Path, destination: Path) -> dict[str, Any]:
    root = root.resolve()
    destination = destination.absolute()
    snapshot = load_json(snapshot_path)
    if Path(snapshot["root"]) != root:
        raise MigrationToolError("snapshot root does not match --root")
    if destination.exists() or destination.is_symlink():
        raise MigrationToolError(f"destination already exists: {destination}")
    if is_within(destination, root):
        raise MigrationToolError("backup destination must be outside the repository")
    if not destination.parent.is_dir():
        raise MigrationToolError(f"parent directory missing: {destination.parent}")
    os.mkdir(destination, 0o700)
    os.chmod(destination, 0o700)
    tree = destination / "tree"
    os.mkdir(tree, 0o700)
    entries: dict[str, Entry] = snapshot["entries"]
    directories: set[str] = set()
    copied = 0
    for relative, entry in sorted(entries.items()):
        if entry["type"] not in {"file", "symlink"}:
            continue
        copy_entry(safe_join(root, relative), safe_join(tree, relative), entry)
        copied += 1
        parent = Path(relative).parent
        while parent != Path("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    for relative in snapshot.get("empty_directories", []):
        (tree / relative).mkdir(parents=True, exist_ok=True)
        directories.add(relative)
    copy_directory_modes(root, tree, directories)
    source_git = root / ".git"
    if not source_git.is_dir() or source_git.is_symlink():
        raise MigrationToolError(".git is not a plain directory; refusing")
    shutil.copytree(source_git, tree / ".git", symlinks=True)
    source_digest = tree_digest(source_git)
    backup_digest = tree_digest(tree / ".git")
    if source_digest != backup_digest:
        raise MigrationToolError(".git changed during copy or copy mismatch")
    write_checksums(destination / "SHA256SUMS", entries)
    shutil.copy2(snapshot_path, destination / "snapshot.json")
    manifest = {
        "created_utc": utc_now(),
        "statement": BACKUP_STATEMENT,
        "source_root": str(root),
        "snapshot_label": snapshot["label"],
        "snapshot_sha256": sha256_regular_file(snapshot_path),
        "branch_ref": snapshot["branch_ref"],
        "head": snapshot["head"],
        "copied_objects": copied,
        "symlinks": sum(1 for e in entries.values() if e["type"] == "symlink"),
        "tracked_deleted_not_present": sorted(
            path for path, e in entries.items() if e["git_state"] == "tracked-deleted"
        ),
        "empty_directories": snapshot.get("empty_directories", []),
        "excluded_git_ignored_top_level": snapshot["ignored_top_level_excluded"],
        "git_dir_digest": backup_digest,
        "git_refs_sha256": sha256_bytes(git_refs(tree / ".git").encode()),
    }
    write_json(destination / "backup-manifest.json", manifest)
    return manifest


def command_backup(arguments: argparse.Namespace) -> int:
    manifest = create_backup(
        Path(arguments.root), Path(arguments.snapshot), Path(arguments.destination)
    )
    print(
        f"backup created: {manifest['copied_objects']} objects, "
        f".git objects {manifest['git_dir_digest']['objects']}"
    )
    return 0


def verify_backup(destination: Path, root: Path | None) -> dict[str, Any]:
    destination = destination.absolute()
    manifest = load_json(destination / "backup-manifest.json")
    snapshot = load_json(destination / "snapshot.json")
    tree = destination / "tree"
    problems: list[str] = []
    if stat.S_IMODE(os.lstat(destination).st_mode) != 0o700:
        problems.append("backup root permissions are not 0700")
    if (
        sha256_regular_file(destination / "snapshot.json")
        != manifest["snapshot_sha256"]
    ):
        problems.append("snapshot.json hash differs from backup manifest")
    entries: dict[str, Entry] = snapshot["entries"]
    expected_paths: set[str] = {".git"}
    checked = 0
    for relative, entry in sorted(entries.items()):
        target = safe_join(tree, relative)
        observed = describe_path(target)
        if entry["type"] == "missing":
            if observed["type"] != "missing":
                problems.append(f"deleted path present in backup: {relative!r}")
            continue
        if content_identity(observed) != content_identity(entry):
            problems.append(f"content mismatch: {relative!r}")
        checked += 1
        expected_paths.add(relative)
        parent = Path(relative).parent
        while parent != Path("."):
            expected_paths.add(parent.as_posix())
            parent = parent.parent
    for relative in snapshot.get("empty_directories", []):
        expected_paths.add(relative)
        parent = Path(relative).parent
        while parent != Path("."):
            expected_paths.add(parent.as_posix())
            parent = parent.parent
        if not (tree / relative).is_dir():
            problems.append(f"empty directory missing: {relative!r}")
    for relative, _ in walk_no_follow(tree):
        if relative.startswith(".git/") or relative in expected_paths:
            continue
        problems.append(f"unexpected extra path: {relative!r}")
    if tree_digest(tree / ".git") != manifest["git_dir_digest"]:
        problems.append(".git digest differs from backup manifest")
    git_dir = tree / ".git"
    if git_returncode(git_dir, "fsck", "--no-progress", "--full") != 0:
        problems.append("git fsck failed on backup .git")
    head = git_text(destination, f"--git-dir={git_dir}", "rev-parse", "HEAD")
    branch = git_text(
        destination, f"--git-dir={git_dir}", "symbolic-ref", "-q", "HEAD", check=False
    )
    if head != snapshot["head"] or (branch or "DETACHED") != snapshot["branch_ref"]:
        problems.append("backup HEAD or branch differs from snapshot")
    if sha256_bytes(git_refs(git_dir).encode()) != manifest["git_refs_sha256"]:
        problems.append("backup refs differ from manifest")
    backup_status = parse_porcelain(
        git_bytes(
            destination,
            f"--git-dir={git_dir}",
            f"--work-tree={tree}",
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        )
    )
    if status_key(backup_status) != status_key(snapshot["status_porcelain"]):
        problems.append("git status of backup differs from snapshot status")
    source_comparison: dict[str, int] | None = None
    if root is not None:
        same = differs = 0
        for relative, entry in entries.items():
            if entry["type"] not in {"file", "symlink"}:
                continue
            observed = describe_path(root / relative)
            if content_identity(observed) == content_identity(entry):
                same += 1
            else:
                differs += 1
        source_comparison = {"identical_now": same, "changed_since_snapshot": differs}
    return {
        "verified_utc": utc_now(),
        "checked_objects": checked,
        "problems": problems,
        "source_comparison": source_comparison,
        "passed": not problems,
    }


def command_verify_backup(arguments: argparse.Namespace) -> int:
    destination = Path(arguments.destination)
    report = verify_backup(
        destination, Path(arguments.root) if arguments.root else None
    )
    lines = [
        f"verified_utc: {report['verified_utc']}",
        f"checked_objects: {report['checked_objects']}",
        f"source_comparison: {report['source_comparison']}",
        f"passed: {report['passed']}",
        *[f"problem: {problem}" for problem in report["problems"]],
    ]
    (destination / "VERIFY.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:4] + lines[4:24]))
    return 0 if report["passed"] else 1


def command_check_existing_backup(arguments: argparse.Namespace) -> int:
    snapshot = load_json(Path(arguments.snapshot))
    backup_root = Path(arguments.backup)
    counts = {"identical": 0, "differs": 0, "missing": 0, "unsafe": 0}
    differing: list[str] = []
    for relative, entry in sorted(snapshot["entries"].items()):
        if entry["type"] not in {"file", "symlink"}:
            continue
        try:
            observed = describe_path(safe_join(backup_root, relative))
        except MigrationToolError:
            counts["unsafe"] += 1
            continue
        if observed["type"] == "missing":
            counts["missing"] += 1
            differing.append(relative)
        elif content_identity(observed) == content_identity(entry):
            counts["identical"] += 1
        else:
            counts["differs"] += 1
            differing.append(relative)
    report = {
        "backup": str(backup_root),
        "snapshot": snapshot["label"],
        "counts": counts,
        "differing_or_missing_paths": differing,
        "note": "Read-only comparison of inventory paths only; nothing modified.",
    }
    if arguments.output:
        write_json(Path(arguments.output), report)
    print(f"existing backup {backup_root}: {counts}")
    return 0


# --------------------------------------------------------------------------
# Privacy scan
# --------------------------------------------------------------------------

PRIVACY_RULES: dict[str, tuple[str, str, re.Pattern[str]]] = {
    "P01": ("absolute-mnt-path", "internal", re.compile(r"/mnt/")),
    "P02": ("absolute-home-path", "sensitive", re.compile(r"/home/|~/\.")),
    "P03": ("local-data-reference", "internal", re.compile(r"local-data/")),
    "P04": (
        "email-address",
        "sensitive",
        re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ),
    "P05": (
        "phone-like-number",
        "sensitive",
        re.compile(r"(?<![\w.])(?:\+\d[\d -]{7,14}\d|09\d{9})(?![\w.])"),
    ),
    "P06": ("long-hex-value", "internal", re.compile(r"\b[0-9a-fA-F]{40,}\b")),
    "P07": (
        "credential-word",
        "sensitive",
        re.compile(
            r"(?i)\b(password|passwd|api[_-]?key|secret[_-]?key|bearer|"
            r"access[_-]?token|auth[_-]?token|private[_-]?key)\b"
        ),
    ),
    "P08": ("owner-report-word", "internal", re.compile(r"(?i)\bowner\b|مالک")),
    "P09": (
        "chat-or-contact-context",
        "internal",
        re.compile(r"(?i)saved messages|chat title|contact name|عنوان گفتگو"),
    ),
}
PATH_SIGNALS = {
    "dated": re.compile(r"20\d\d-\d\d-\d\d"),
    "prompt": re.compile(r"(?i)prompt"),
    "handoff": re.compile(r"(?i)handoff"),
    "review-or-audit": re.compile(r"(?i)review|audit"),
    "acceptance": re.compile(r"(?i)acceptance"),
    "next-steps": re.compile(r"(?i)next_steps"),
    "persian-suffix": re.compile(r"_FA\.md$"),
}
MAX_LINE_REFERENCES = 20


def scan_markdown(path: Path) -> dict[str, Any]:
    text = read_text(path)
    rules: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule_id, (_, _, pattern) in PRIVACY_RULES.items():
            found = len(pattern.findall(line))
            if not found:
                continue
            record = rules.setdefault(rule_id, {"count": 0, "lines": []})
            record["count"] += found
            if len(record["lines"]) < MAX_LINE_REFERENCES:
                record["lines"].append(line_number)
    return {
        "bytes": len(text.encode()),
        "lines": text.count("\n"),
        "persian_ratio": persian_ratio(text),
        "rules": rules,
    }


def suggest_category(rules: dict[str, Any], signals: list[str]) -> str:
    severities = {PRIVACY_RULES[rule_id][1] for rule_id in rules}
    if "sensitive" in severities:
        return "sensitive-candidate"
    if severities or set(signals) - {"persian-suffix"}:
        return "internal-candidate"
    return "no-heuristic-flags"


def privacy_report(root: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for relative, entry in sorted(snapshot["entries"].items()):
        if entry["type"] != "file" or not relative.endswith(".md"):
            continue
        scan = scan_markdown(root / relative)
        signals = [
            name for name, pattern in PATH_SIGNALS.items() if pattern.search(relative)
        ]
        files.append(
            {
                "path": relative,
                "git_state": entry["git_state"],
                "in_local_origin_main_ref": entry["in_local_origin_main_ref"],
                "classification": "unreviewed",
                "suggested_category": suggest_category(scan["rules"], signals),
                "path_signals": signals,
                **scan,
            }
        )
    summary: dict[str, int] = {}
    for item in files:
        summary[item["suggested_category"]] = (
            summary.get(item["suggested_category"], 0) + 1
        )
    return {
        "created_utc": utc_now(),
        "snapshot": snapshot["label"],
        "policy": (
            "Heuristic flags only. Every file remains 'unreviewed'; no file is "
            "certified public-safe. Matched text is not stored."
        ),
        "rules": {
            rule_id: {"name": name, "severity": severity}
            for rule_id, (name, severity, _) in PRIVACY_RULES.items()
        },
        "summary": summary,
        "files": files,
    }


def command_privacy_scan(arguments: argparse.Namespace) -> int:
    root = Path(arguments.root).resolve()
    output = Path(arguments.output).resolve()
    ensure_output_outside_inventory(root, output)
    report = privacy_report(root, load_json(Path(arguments.snapshot)))
    write_json(output, report)
    print(f"privacy scan: {len(report['files'])} Markdown files, {report['summary']}")
    return 0


# --------------------------------------------------------------------------
# Static package scope
# --------------------------------------------------------------------------


def glob_regex(pattern: str) -> str:
    result = ""
    for character in pattern:
        if character == "*":
            result += "[^/]*"
        elif character == "?":
            result += "[^/]"
        else:
            result += re.escape(character)
    return result


def manifest_matcher(command: str, words: list[str]) -> list[re.Pattern[str]]:
    if command in {"include", "exclude"}:
        return [re.compile(glob_regex(word) + r"\Z") for word in words]
    if command in {"global-include", "global-exclude"}:
        return [re.compile(r"(?:.*/)?" + glob_regex(word) + r"\Z") for word in words]
    if command in {"recursive-include", "recursive-exclude"}:
        directory, *patterns = words
        prefix = re.escape(directory.rstrip("/")) + "/(?:.*/)?"
        return [re.compile(prefix + glob_regex(word) + r"\Z") for word in patterns]
    if command in {"graft", "prune"}:
        return [re.compile(re.escape(word.rstrip("/")) + r"/.*\Z") for word in words]
    raise MigrationToolError(f"unsupported MANIFEST.in command: {command}")


def package_defaults(root: Path, candidates: set[str]) -> set[str]:
    configuration = tomllib.loads((root / "pyproject.toml").read_text())
    tool = configuration.get("tool", {}).get("setuptools", {})
    where = tool.get("packages", {}).get("find", {}).get("where", ["."])
    package_data: dict[str, list[str]] = tool.get("package-data", {})
    project = configuration.get("project", {})
    defaults = {"pyproject.toml", "MANIFEST.in", "setup.py", "setup.cfg"}
    readme = project.get("readme")
    if isinstance(readme, dict):
        readme = readme.get("file")
    if isinstance(readme, str):
        defaults.add(readme)
    for pattern in project.get("license-files", []):
        defaults.update(p for p in candidates if re.fullmatch(glob_regex(pattern), p))
    for base in where:
        prefix = base.rstrip("/") + "/"
        defaults.update(
            p for p in candidates if p.startswith(prefix) and p.endswith(".py")
        )
        for package, patterns in package_data.items():
            package_path = prefix + package.replace(".", "/") + "/"
            for pattern in patterns:
                regex = re.compile(
                    re.escape(package_path) + glob_regex(pattern) + r"\Z"
                )
                defaults.update(p for p in candidates if regex.match(p))
    return defaults & candidates


def evaluate_manifest(
    root: Path, candidates: set[str], template: str
) -> tuple[set[str], list[str]]:
    included = package_defaults(root, candidates)
    applied: list[str] = []
    for raw in template.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        command, *words = line.split()
        patterns = manifest_matcher(command, words)
        matched = {p for p in candidates if any(r.match(p) for r in patterns)}
        if command in {"include", "global-include", "recursive-include", "graft"}:
            included |= matched
        else:
            included -= matched
        applied.append(line)
    return included, applied


def command_package_scope(arguments: argparse.Namespace) -> int:
    root = Path(arguments.root).resolve()
    output = Path(arguments.output).resolve()
    ensure_output_outside_inventory(root, output)
    snapshot = load_json(Path(arguments.snapshot))
    candidates = {
        path for path, entry in snapshot["entries"].items() if entry["type"] == "file"
    }
    ignored_on_disk = set(
        git_paths(root, "ls-files", "-z", "-o", "-i", "--exclude-standard")
    )
    candidates |= ignored_on_disk
    included, applied = evaluate_manifest(
        root, candidates, (root / "MANIFEST.in").read_text()
    )
    privacy: dict[str, str] = {}
    if arguments.privacy:
        privacy = {
            item["path"]: item["suggested_category"]
            for item in load_json(Path(arguments.privacy))["files"]
        }
    markdown = sorted(path for path in included if path.endswith(".md"))
    by_category: dict[str, int] = {}
    for path in markdown:
        category = privacy.get(path, "not-scanned")
        by_category[category] = by_category.get(category, 0) + 1
    report: dict[str, Any] = {
        "created_utc": utc_now(),
        "method": (
            "Static approximation from MANIFEST.in and pyproject.toml. No build, "
            "setup.py or packaging hook was executed. Setuptools internals and "
            "dynamic hooks are not evaluated."
        ),
        "applied_manifest_lines": applied,
        "included_files": len(included),
        "included_ignored_on_disk": sorted(included & ignored_on_disk),
        "included_untracked": sorted(
            p
            for p in included
            if snapshot["entries"].get(p, {}).get("git_state") == "untracked"
        ),
        "included_markdown": markdown,
        "included_markdown_by_privacy_suggestion": by_category,
        "tools_doc_migration_included": sorted(
            p for p in included if p.startswith("tools/")
        ),
        "local_data_included": sorted(
            p for p in included if p.startswith("local-data/")
        ),
    }
    write_json(output, report)
    print(
        f"package scope (static): {report['included_files']} files, "
        f"{len(markdown)} Markdown, {by_category}, "
        f"tools/ included {len(report['tools_doc_migration_included'])}, "
        f"local-data included {len(report['local_data_included'])}, "
        f"ignored-on-disk included {len(report['included_ignored_on_disk'])}"
    )
    return 0


# --------------------------------------------------------------------------
# Read-only restore plan
# --------------------------------------------------------------------------


def build_restore_plan(
    root: Path,
    before: dict[str, Any],
    after: dict[str, Any],
    pre_images: Path | None,
) -> dict[str, Any]:
    actions: list[dict[str, str]] = []
    for path in sorted(set(before["entries"]) | set(after["entries"])):
        old = before["entries"].get(path, {"type": "absent"})
        new = after["entries"].get(path, {"type": "absent"})
        if content_identity(old) == content_identity(new):
            continue
        current = describe_path(root / path)
        expected_now = new if new["type"] != "absent" else {"type": "missing"}
        if content_identity(current) != content_identity(expected_now):
            action = "refuse-changed-after-phase"
        elif old["type"] in {"absent", "missing"}:
            action = "would-quarantine-created-path"
        elif pre_images is None:
            action = "blocked-no-pre-image-directory"
        else:
            image = describe_path(pre_images / path)
            if content_identity(image) != content_identity(old):
                action = "blocked-pre-image-missing-or-mismatched"
            else:
                action = "would-restore-pre-image"
        actions.append({"path": path, "action": action})
    return {
        "mode": "read-only plan; this tool implements no restoration",
        "before": before["label"],
        "after": after["label"],
        "actions": actions,
    }


def command_restore_plan(arguments: argparse.Namespace) -> int:
    plan = build_restore_plan(
        Path(arguments.root).resolve(),
        load_json(Path(arguments.before)),
        load_json(Path(arguments.after)),
        Path(arguments.pre_images) if arguments.pre_images else None,
    )
    if arguments.output:
        write_json(Path(arguments.output), plan)
    print(f"restore plan (read-only): {len(plan['actions'])} action(s)")
    for action in plan["actions"]:
        print(f"  {action['action']}: {action['path']!r}")
    return 0


# --------------------------------------------------------------------------
# Migration manifest
# --------------------------------------------------------------------------

PROTECTED_PATTERNS = [
    "src/**",
    "tests/**",
    "datasets/**",
    "integrations/**",
    "assets/**",
    "scripts/**",
    "pyproject.toml",
    "MANIFEST.in",
    ".github/**",
    "models/**",
    "docs/stt/*PROMPTS_FA.md",
]


def command_manifest(arguments: argparse.Namespace) -> int:
    root = Path(arguments.root).resolve()
    output = Path(arguments.output).resolve()
    ensure_output_outside_inventory(root, output)
    snapshot = load_json(Path(arguments.snapshot))
    privacy = load_json(Path(arguments.privacy))
    documents = []
    for item in privacy["files"]:
        entry = snapshot["entries"][item["path"]]
        documents.append(
            {
                "path": item["path"],
                "git_state": item["git_state"],
                "in_local_origin_main_ref": item["in_local_origin_main_ref"],
                "bytes": item["bytes"],
                "lines": item["lines"],
                "persian_ratio": item["persian_ratio"],
                "path_signals": item["path_signals"],
                "privacy_classification": "unreviewed",
                "privacy_suggestion": item["suggested_category"],
                "protected": matches_any(item["path"], PROTECTED_PATTERNS),
                "doc_class": "unclassified",
                "action": "undecided",
                "destination": None,
                "phase": None,
                "source_sha256": entry["sha256"],
                "result_sha256": None,
                "status": "baseline",
            }
        )
    write_json(
        output,
        {
            "format": "kyrin-doc-migration-manifest/1",
            "created_utc": utc_now(),
            "baseline_snapshot": snapshot["label"],
            "branch_ref": snapshot["branch_ref"],
            "head": snapshot["head"],
            "protected_patterns": PROTECTED_PATTERNS,
            "documents": documents,
        },
    )
    print(f"manifest: {len(documents)} Markdown documents -> {output}")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--root", default=".")
    snapshot.add_argument("--label", required=True)
    snapshot.add_argument("--output", required=True)
    snapshot.set_defaults(handler=command_snapshot)

    compare = sub.add_parser("compare")
    compare.add_argument("--before", required=True)
    compare.add_argument("--after", required=True)
    compare.add_argument("--allow", action="append", default=[])
    compare.add_argument("--output")
    compare.set_defaults(handler=command_compare)

    backup = sub.add_parser("backup")
    backup.add_argument("--root", default=".")
    backup.add_argument("--snapshot", required=True)
    backup.add_argument("--destination", required=True)
    backup.set_defaults(handler=command_backup)

    verify = sub.add_parser("verify-backup")
    verify.add_argument("--destination", required=True)
    verify.add_argument("--root")
    verify.set_defaults(handler=command_verify_backup)

    existing = sub.add_parser("check-existing-backup")
    existing.add_argument("--backup", required=True)
    existing.add_argument("--snapshot", required=True)
    existing.add_argument("--output")
    existing.set_defaults(handler=command_check_existing_backup)

    privacy = sub.add_parser("privacy-scan")
    privacy.add_argument("--root", default=".")
    privacy.add_argument("--snapshot", required=True)
    privacy.add_argument("--output", required=True)
    privacy.set_defaults(handler=command_privacy_scan)

    package = sub.add_parser("package-scope")
    package.add_argument("--root", default=".")
    package.add_argument("--snapshot", required=True)
    package.add_argument("--privacy")
    package.add_argument("--output", required=True)
    package.set_defaults(handler=command_package_scope)

    restore = sub.add_parser("restore-plan")
    restore.add_argument("--root", default=".")
    restore.add_argument("--before", required=True)
    restore.add_argument("--after", required=True)
    restore.add_argument("--pre-images")
    restore.add_argument("--output")
    restore.set_defaults(handler=command_restore_plan)

    manifest = sub.add_parser("manifest")
    manifest.add_argument("--root", default=".")
    manifest.add_argument("--snapshot", required=True)
    manifest.add_argument("--privacy", required=True)
    manifest.add_argument("--output", required=True)
    manifest.set_defaults(handler=command_manifest)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        result: int = arguments.handler(arguments)
    except MigrationToolError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return result


if __name__ == "__main__":
    raise SystemExit(main())
