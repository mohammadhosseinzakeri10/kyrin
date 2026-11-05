# Documentation-migration tools

Standard-library Python tools for the KYRIN documentation migration. They are
outside `src/`, `tests/` and `scripts/`, so they are not part of the package,
the runtime wheel or the quality gate. The source distribution includes these tools.

Run from the repository root with Python 3.14+. Write operational output only
to the Git-ignored `local-data/doc-migration/` directory or outside the
repository; the tools refuse output paths that would enter their own
inventory.

| Tool | Purpose |
| --- | --- |
| `inventory.py snapshot` | Record tracked, modified, deleted and untracked non-ignored paths with type, size, mode, mtime and SHA-256. Symbolic links are recorded, never followed. |
| `inventory.py compare` | Compare two snapshots against `--allow` globs; exit 1 on any change outside the allowlist. |
| `inventory.py backup` / `verify-backup` | Create a new `0700` source-and-Git backup (not a system backup) and re-verify content, modes, symlink targets, `.git` digest, `git fsck` and status. |
| `inventory.py check-existing-backup` | Read-only comparison of an older backup with a snapshot. |
| `inventory.py privacy-scan` | Heuristic rule counts and line numbers for Markdown files. Every file stays `unreviewed`; matched text is not stored. |
| `inventory.py package-scope` | Static approximation of sdist inclusion; runs no build or packaging hook. |
| `inventory.py restore-plan` | Read-only recovery plan. No restoration is implemented. |
| `inventory.py manifest` | Migration manifest for Markdown documents. |
| `check_links.py` | Relative links, anchors, references and images; ignores code blocks and inline code; warns on absolute paths. |
| `context_budget.py` | Static size indicators only; not token consumption or skill activation. |
| `selftest.py` | Synthetic tests in temporary directories. |

```bash
python3 tools/doc-migration/selftest.py
python3 tools/doc-migration/check_links.py --root .
```
