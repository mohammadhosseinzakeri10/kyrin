"""Shared helpers for the KYRIN documentation-migration tools.

Standard library only. Paths are handled as POSIX strings relative to the
repository root; undecodable bytes are preserved with ``os.fsdecode``.
Symbolic links are never followed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

PERSIAN_CHARACTER = re.compile("[؀-ۿﭐ-﷿ﹰ-﻿]")
HASH_CHUNK = 1024 * 1024

Entry = dict[str, Any]


class MigrationToolError(RuntimeError):
    """A precondition, preservation or scope check failed."""


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_environment() -> dict[str, str]:
    """Environment for read-only Git calls that must not refresh the index."""
    environment = dict(os.environ)
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["LC_ALL"] = "C"
    return environment


def git_bytes(root: Path, *arguments: str, check: bool = True) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        env=git_environment(),
        check=False,
    )
    if check and result.returncode != 0:
        message = result.stderr.decode(errors="replace").strip()
        raise MigrationToolError(f"git {' '.join(arguments)} failed: {message}")
    return result.stdout


def git_returncode(git_dir: Path, *arguments: str) -> int:
    """Run a read-only Git command against an explicit Git directory."""
    result = subprocess.run(
        ["git", f"--git-dir={git_dir}", *arguments],
        capture_output=True,
        env=git_environment(),
        check=False,
    )
    return result.returncode


def git_text(root: Path, *arguments: str, check: bool = True) -> str:
    return git_bytes(root, *arguments, check=check).decode(errors="replace").strip()


def split_nul(data: bytes) -> list[str]:
    return [os.fsdecode(item) for item in data.split(b"\0") if item]


def git_paths(root: Path, *arguments: str) -> list[str]:
    return split_nul(git_bytes(root, *arguments))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_regular_file(path: Path) -> str:
    """Hash a regular file without following a final symbolic link."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    digest = hashlib.sha256()
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise MigrationToolError(f"not a regular file: {path}")
        while chunk := os.read(descriptor, HASH_CHUNK):
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def describe_path(path: Path) -> Entry:
    """Describe one filesystem object without following symbolic links."""
    try:
        status = os.lstat(path)
    except FileNotFoundError:
        return {"type": "missing"}
    mode = stat.S_IMODE(status.st_mode)
    if stat.S_ISLNK(status.st_mode):
        target = os.readlink(path)
        return {
            "type": "symlink",
            "target": target,
            "sha256": sha256_bytes(os.fsencode(target)),
            "mode": mode,
        }
    if stat.S_ISREG(status.st_mode):
        return {
            "type": "file",
            "size": status.st_size,
            "mode": mode,
            "mtime_ns": status.st_mtime_ns,
            "sha256": sha256_regular_file(path),
        }
    if stat.S_ISDIR(status.st_mode):
        return {"type": "directory", "mode": mode}
    return {"type": "other", "mode": mode}


def content_identity(entry: Entry) -> tuple[Any, ...]:
    """Fields that define preserved content: type, bytes or target, mode."""
    kind = entry.get("type")
    if kind == "file":
        return (kind, entry.get("sha256"), entry.get("size"), entry.get("mode"))
    if kind == "symlink":
        return (kind, entry.get("target"))
    return (kind,)


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def is_git_ignored(root: Path, path: Path) -> bool:
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    result = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "-q", "--no-index", relative],
        capture_output=True,
        env=git_environment(),
        check=False,
    )
    return result.returncode == 0


def ensure_output_outside_inventory(root: Path, output: Path) -> None:
    """Refuse an output location that would enter the repository inventory."""
    if not is_within(output, root):
        return
    if not is_git_ignored(root, output):
        raise MigrationToolError(
            f"output {output} is inside {root} but not Git-ignored; it would "
            "enter its own inventory"
        )


def matches_any(path: str, patterns: Sequence[str]) -> bool:
    pure = PurePosixPath(path)
    return any(pure.full_match(pattern) for pattern in patterns)


def persian_ratio(text: str) -> float:
    letters = sum(1 for character in text if character.isalpha())
    if letters == 0:
        return 0.0
    return round(len(PERSIAN_CHARACTER.findall(text)) / letters, 4)


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="replace")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def sorted_unique(values: Iterable[str]) -> list[str]:
    return sorted(set(values))
