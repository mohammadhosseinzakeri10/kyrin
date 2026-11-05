#!/usr/bin/env python3
"""Synthetic self-tests for the documentation-migration tools.

Every test runs in a fresh temporary directory with an isolated Git
configuration. No repository file is read or written.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_links  # noqa: E402
import inventory  # noqa: E402
from common import (  # noqa: E402
    MigrationToolError,
    content_identity,
    describe_path,
    ensure_output_outside_inventory,
    write_json,
)

GIT_ENVIRONMENT = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "selftest",
    "GIT_AUTHOR_EMAIL": "selftest@example.invalid",
    "GIT_COMMITTER_NAME": "selftest",
    "GIT_COMMITTER_EMAIL": "selftest@example.invalid",
}


def git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        env={**os.environ, **GIT_ENVIRONMENT},
    )


class TemporaryCase(unittest.TestCase):
    def setUp(self) -> None:
        self._previous = {key: os.environ.get(key) for key in GIT_ENVIRONMENT}
        os.environ.update(GIT_ENVIRONMENT)
        self.base = Path(tempfile.mkdtemp(prefix="kyrin-docmig-selftest-"))
        self.root = self.base / "repo"
        self.root.mkdir()

    def tearDown(self) -> None:
        for key, value in self._previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.base)

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path


class LinkCheckerTests(TemporaryCase):
    def check(self, strict: bool = False) -> check_links.Report:
        files = sorted(
            p.relative_to(self.root).as_posix() for p in self.root.rglob("*.md")
        )
        return check_links.check_files(self.root, files, strict)

    def test_relative_parent_and_anchor_links(self) -> None:
        self.write(
            "docs/a/target.md",
            "# Main Title\n## Repeated\n## Repeated\n## Persian عنوان\n",
        )
        self.write(
            "docs/b/source.md",
            "[ok](../a/target.md)\n[anchor](../a/target.md#main-title)\n"
            "[dup](../a/target.md#repeated-1)\n"
            "[fa](../a/target.md#persian-عنوان)\n"
            "[missing anchor](../a/target.md#absent)\n"
            '[self](#local)\n<a id="local"></a>\n',
        )
        report = self.check()
        self.assertEqual(report.broken, [])
        self.assertEqual(len(report.anchor_problems), 1)
        self.assertEqual(report.anchor_problems[0]["link"], "../a/target.md#absent")
        self.assertEqual(len(self.check(strict=True).broken), 1)

    def test_broken_link_and_code_is_ignored(self) -> None:
        self.write(
            "doc.md",
            "[gone](missing.md)\n"
            "```\n[in fence](fence-missing.md)\n```\n"
            "~~~~\n[tilde](tilde-missing.md)\n~~~~\n"
            "Inline `[code](code-missing.md)` text.\n"
            "Double ``[x](double-missing.md)`` span.\n",
        )
        report = self.check()
        self.assertEqual([b["link"] for b in report.broken], ["missing.md"])

    def test_encoding_angle_brackets_references_images_and_urls(self) -> None:
        self.write("dir with space/file name.md", "# T\n")
        self.write("img.png", "x")
        self.write(
            "doc.md",
            "[pct](dir%20with%20space/file%20name.md)\n"
            "[angle](<dir with space/file name.md>)\n"
            "![image](img.png)\n"
            "[ref]: dir%20with%20space/file%20name.md\n"
            "[web](https://example.invalid/x.md) [mail](mailto:a@example.invalid)\n"
            '[paren](dir%20with%20space/file%20name.md "title")\n',
        )
        report = self.check()
        self.assertEqual(report.broken, [])
        self.assertEqual(report.relative_links, 5)

    def test_absolute_and_line_suffix_links(self) -> None:
        self.write("code.py", "x = 1\n")
        self.write(
            "doc.md",
            "[abs](/mnt/somewhere/file.py:12)\n[line](code.py:1)\n"
            "[range](code.py:1-2)\n",
        )
        report = self.check()
        self.assertEqual(report.broken, [])
        self.assertEqual(len(report.absolute_path_warnings), 1)

    def test_moved_file_needs_stub_or_link_update(self) -> None:
        self.write("docs/old.md", "# Old\n")
        self.write("index.md", "[old](docs/old.md)\n")
        self.assertEqual(self.check().broken, [])
        (self.root / "docs/archive").mkdir()
        os.rename(self.root / "docs/old.md", self.root / "docs/archive/old.md")
        self.assertEqual(len(self.check().broken), 1)
        self.write("docs/old.md", "Moved to [archive](archive/old.md).\n")
        self.assertEqual(self.check().broken, [])


class SnapshotAndBackupTests(TemporaryCase):
    def build_repository(self) -> None:
        git(self.root, "init", "-q", "-b", "main")
        self.write(".gitignore", "ignored/\n*.log\n")
        self.write("plain.md", "plain\n")
        self.write("name with space.md", "space\n")
        self.write("فارسی.md", "persian name\n")
        self.write("to-delete.md", "delete me\n")
        script = self.write("run.sh", "#!/bin/sh\n")
        script.chmod(0o755)
        os.symlink("plain.md", self.root / "inside-link")
        self.outside = self.base / "outside-private"
        self.outside.mkdir()
        (self.outside / "secret.txt").write_text("must not be copied")
        os.symlink(str(self.outside), self.root / "outside-link")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "initial")
        (self.root / "to-delete.md").unlink()
        self.write("plain.md", "plain modified\n")
        self.write("untracked\nnewline.md", "newline name\n")
        self.write("ignored/private.md", "ignored\n")
        self.write("debug.log", "ignored\n")
        (self.root / "empty-dir").mkdir()

    def snapshot(self, label: str) -> dict[str, Any]:
        return inventory.take_snapshot(self.root, label)

    def save(self, snapshot: dict[str, Any], name: str) -> Path:
        path = self.base / f"{name}.json"
        write_json(path, snapshot)
        return path

    def test_snapshot_records_states_symlinks_and_unusual_names(self) -> None:
        self.build_repository()
        snapshot = self.snapshot("pre")
        entries = snapshot["entries"]
        self.assertEqual(entries["plain.md"]["git_state"], "tracked-modified")
        self.assertEqual(entries["to-delete.md"]["git_state"], "tracked-deleted")
        self.assertEqual(entries["to-delete.md"]["type"], "missing")
        self.assertEqual(entries["untracked\nnewline.md"]["git_state"], "untracked")
        self.assertIn("فارسی.md", entries)
        self.assertEqual(entries["outside-link"]["type"], "symlink")
        self.assertEqual(entries["outside-link"]["target"], str(self.outside))
        self.assertEqual(entries["run.sh"]["mode"], 0o755)
        self.assertNotIn("ignored/private.md", entries)
        self.assertNotIn("debug.log", entries)
        self.assertIn("empty-dir", snapshot["empty_directories"])

    def test_compare_flags_changes_outside_allowlist(self) -> None:
        self.build_repository()
        before = self.snapshot("before")
        self.write("tools/new.py", "x = 1\n")
        self.write("name with space.md", "changed\n")
        (self.root / "run.sh").chmod(0o700)
        os.unlink(self.root / "inside-link")
        os.symlink("فارسی.md", self.root / "inside-link")
        after = self.snapshot("after")
        report = inventory.diff_snapshots(before, after, ["tools/**"])
        kinds = {c["path"]: c["kind"] for c in report["unallowed_changes"]}
        self.assertEqual(kinds["name with space.md"], "content-changed")
        self.assertEqual(kinds["run.sh"], "mode-changed")
        self.assertEqual(kinds["inside-link"], "content-changed")
        self.assertNotIn("tools/new.py", kinds)
        self.assertFalse(report["passed"])
        clean = inventory.diff_snapshots(after, self.snapshot("again"), ["tools/**"])
        self.assertTrue(clean["passed"])

    def test_backup_preserves_content_modes_and_symlinks(self) -> None:
        self.build_repository()
        snapshot_path = self.save(self.snapshot("pre"), "pre")
        destination = self.base / "backups" / "b1"
        destination.parent.mkdir()
        inventory.create_backup(self.root, snapshot_path, destination)
        tree = destination / "tree"
        self.assertEqual(stat.S_IMODE(os.lstat(destination).st_mode), 0o700)
        self.assertTrue((tree / "outside-link").is_symlink())
        self.assertEqual(os.readlink(tree / "outside-link"), str(self.outside))
        self.assertFalse((tree / "secret.txt").exists())
        self.assertEqual(stat.S_IMODE((tree / "run.sh").stat().st_mode), 0o755)
        self.assertEqual((tree / "untracked\nnewline.md").read_text(), "newline name\n")
        self.assertFalse((tree / "ignored").exists())
        self.assertFalse((tree / "to-delete.md").exists())
        report = inventory.verify_backup(destination, self.root)
        self.assertTrue(report["passed"], report["problems"])
        (tree / "plain.md").write_text("tampered\n")
        self.assertFalse(inventory.verify_backup(destination, None)["passed"])

    def test_backup_refuses_existing_inside_or_changed_source(self) -> None:
        self.build_repository()
        snapshot_path = self.save(self.snapshot("pre"), "pre")
        existing = self.base / "existing"
        existing.mkdir()
        with self.assertRaises(MigrationToolError):
            inventory.create_backup(self.root, snapshot_path, existing)
        with self.assertRaises(MigrationToolError):
            inventory.create_backup(self.root, snapshot_path, self.root / "inner")
        self.write("plain.md", "changed after snapshot\n")
        with self.assertRaises(MigrationToolError):
            inventory.create_backup(self.root, snapshot_path, self.base / "b2")

    def test_output_inside_inventory_is_refused(self) -> None:
        self.build_repository()
        with self.assertRaises(MigrationToolError):
            ensure_output_outside_inventory(self.root, self.root / "report.json")
        ensure_output_outside_inventory(self.root, self.root / "ignored" / "r.json")
        ensure_output_outside_inventory(self.root, self.base / "outside.json")


class RestorePlanTests(TemporaryCase):
    def test_plan_is_read_only_and_refuses_newer_work(self) -> None:
        git(self.root, "init", "-q", "-b", "main")
        self.write("keep.md", "original\n")
        self.write("newer.md", "original\n")
        pre_images = self.base / "pre-images"
        pre_images.mkdir()
        shutil.copy2(self.root / "keep.md", pre_images / "keep.md")
        shutil.copy2(self.root / "newer.md", pre_images / "newer.md")
        before = inventory.take_snapshot(self.root, "before")
        self.write("keep.md", "phase output\n")
        self.write("newer.md", "phase output\n")
        self.write("created.md", "created by phase\n")
        after = inventory.take_snapshot(self.root, "after")
        self.write("newer.md", "owner edited after the phase\n")
        state = {
            p: describe_path(self.root / p)["sha256"]
            for p in ("keep.md", "newer.md", "created.md")
        }
        plan = inventory.build_restore_plan(self.root, before, after, pre_images)
        actions = {a["path"]: a["action"] for a in plan["actions"]}
        self.assertEqual(actions["keep.md"], "would-restore-pre-image")
        self.assertEqual(actions["newer.md"], "refuse-changed-after-phase")
        self.assertEqual(actions["created.md"], "would-quarantine-created-path")
        self.assertEqual(
            state,
            {p: describe_path(self.root / p)["sha256"] for p in state},
            "restore-plan must not modify files",
        )
        self.assertFalse(hasattr(inventory, "apply_restore"))
        self.simulate_recovery_in_sandbox(plan, before, pre_images)

    def simulate_recovery_in_sandbox(
        self, plan: dict[str, Any], before: dict[str, Any], pre_images: Path
    ) -> None:
        """Test-only recovery on a sandbox copy, never on a project tree."""
        sandbox = self.base / "sandbox"
        shutil.copytree(self.root, sandbox, symlinks=True)
        self.assertTrue(str(sandbox).startswith(tempfile.gettempdir()))
        quarantine = self.base / "quarantine"
        quarantine.mkdir()
        for action in plan["actions"]:
            path = action["path"]
            if action["action"] == "would-restore-pre-image":
                shutil.copy2(pre_images / path, sandbox / path, follow_symlinks=False)
            elif action["action"] == "would-quarantine-created-path":
                os.rename(sandbox / path, quarantine / path)
        self.assertEqual(
            content_identity(describe_path(sandbox / "keep.md")),
            content_identity(before["entries"]["keep.md"]),
        )
        self.assertEqual(
            (sandbox / "newer.md").read_text(), "owner edited after the phase\n"
        )
        self.assertFalse((sandbox / "created.md").exists())
        self.assertTrue((quarantine / "created.md").exists())


class PrivacyAndPackageTests(TemporaryCase):
    def test_privacy_defaults_to_unreviewed_without_storing_matches(self) -> None:
        git(self.root, "init", "-q", "-b", "main")
        self.write("clean.md", "# Architecture\nNeutral text.\n")
        self.write("contact.md", "Reach person.name@example.org today.\n")
        self.write("docs/HANDOFF_2026-10-30_FA.md", "Notes from local-data/x\n")
        snapshot = inventory.take_snapshot(self.root, "s")
        report = inventory.privacy_report(self.root, snapshot)
        by_path = {item["path"]: item for item in report["files"]}
        self.assertTrue(
            all(item["classification"] == "unreviewed" for item in report["files"])
        )
        self.assertEqual(
            by_path["clean.md"]["suggested_category"], "no-heuristic-flags"
        )
        self.assertEqual(
            by_path["contact.md"]["suggested_category"], "sensitive-candidate"
        )
        self.assertEqual(
            by_path["docs/HANDOFF_2026-10-30_FA.md"]["suggested_category"],
            "internal-candidate",
        )
        self.assertNotIn("person.name@example.org", repr(report))

    def test_static_manifest_evaluation(self) -> None:
        self.write(
            "pyproject.toml",
            '[project]\nreadme = "README.md"\nlicense-files = ["LICENSE"]\n'
            '[tool.setuptools.packages.find]\nwhere = ["src"]\n',
        )
        candidates = {
            "README.md",
            "LICENSE",
            "TOP.md",
            "docs/a.md",
            "docs/deep/b.md",
            "docs/c.txt",
            "tools/doc-migration/inventory.py",
            "local-data/doc-migration/STATUS.md",
            "src/pkg/__init__.py",
            "scripts/x.py",
            "datasets/stt/manifest.local.csv",
            "datasets/stt/manifest.template.csv",
        }
        template = (
            "include *.md LICENSE\nrecursive-include docs *.md\n"
            "recursive-include scripts *.py\nrecursive-include datasets *.csv\n"
            "recursive-exclude datasets/stt manifest*.csv\n"
            "include datasets/stt/manifest.template.csv\nprune local-data\n"
        )
        included, _ = inventory.evaluate_manifest(self.root, candidates, template)
        self.assertIn("TOP.md", included)
        self.assertIn("docs/deep/b.md", included)
        self.assertIn("src/pkg/__init__.py", included)
        self.assertIn("datasets/stt/manifest.template.csv", included)
        self.assertNotIn("datasets/stt/manifest.local.csv", included)
        self.assertNotIn("docs/c.txt", included)
        self.assertNotIn("tools/doc-migration/inventory.py", included)
        self.assertNotIn("local-data/doc-migration/STATUS.md", included)


if __name__ == "__main__":
    unittest.main(verbosity=2)
