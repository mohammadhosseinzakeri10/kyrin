---
name: kyrin-engineering-workflow
description: KYRIN change and investigation workflow. Use before editing KYRIN source, tests, scripts, GNOME Shell integrations or project configuration; when continuing existing uncommitted work; when planning a multi-file feature; or when investigating a failing test or an STT/audio, GNOME window/geometry/target, desktop-input, permission or remembered-consent problem. Covers work preservation, task-scoped discovery, proportional planning, evidence-based debugging, verification and result reporting. Not for read-only questions, code explanations, documentation-only edits, or comment and typo fixes.
---

# KYRIN engineering workflow

`AGENTS.md` is the policy and wins on any conflict; this file is the
procedure. Follow the steps in order, scaled to the size of the task.

## 1. Preserve existing work (always first)

- Run `git status --porcelain=v1` before the first edit. The working tree
  normally holds a large amount of uncommitted and untracked owner work.
  Every change you did not make is the owner's, including existing
  deletions.
- Before editing a file that is already modified, read `git diff -- <path>`
  and build on the current content. Never restore it to `HEAD`, regenerate
  it, or reformat unrelated parts.
- No staging, commit, stash, reset, restore, clean, checkout of paths, or
  deletion without an explicit instruction for that exact action.
- Large or risky edit: save a pre-image first (`cp -p` plus `sha256sum`
  into a Git-ignored `local-data/<task>/preimages/` directory). Multi-file
  sweeps: `tools/doc-migration/inventory.py snapshot` before and
  `inventory.py compare` after (see `tools/doc-migration/README.md`). Allow
  each new directory itself as well as its contents (`--allow dir --allow
  'dir/**'`), and judge the result by the exit code, not the summary line.
- Stop and report when a file changes underneath you, a backup or hash check
  fails, or the needed change falls outside the requested scope.
- Private material stays in Git-ignored `local-data/`. Never copy its
  contents, tokens, recordings or workstation paths into tracked files.

## 2. Scope the context

- Locate the subsystem in the "Current state by subsystem" table of
  `PROJECT_CONTEXT.md` (subsystem -> code -> reference). Tests mirror
  packages: `src/kyrin/<pkg>/` <-> `tests/<pkg>/`.
- Search first (`rg`), then read the target module, its contract or
  interface, direct callers and its tests. Follow imports when behavior
  depends on them; do not stop at the first plausible file.
- Do not read the whole repository, `local-data/` archives, models,
  datasets, dated reports under `docs/development/` or `REVIEW.md` unless the
  task is about them.
- Read a safety contract only when the change touches it. The numbered
  "Architectural invariants" in `PROJECT_CONTEXT.md` are authoritative; the
  last column below is only a reminder. When an English reference says its
  Persian `_FA.md` original governs, the original and the code win; report
  any difference.

| Change touches | Read first | Reminder (invariant) |
| --- | --- | --- |
| ActionGate, permissions, any desktop action | `docs/actions/ACTION_GATE.md`, `docs/actions/CONTROL_POLICY.md`, `docs/actions/PERSISTENT_PERMISSIONS.md` | Every action passes the gate and permission model (4, 5) |
| Command understanding, model proposals, recovery | `docs/commands/SEMANTIC_UNDERSTANDING_CONTRACT.md`, DR-0002 | Understanding proposes, execution authorizes (4) |
| Input session, Qt startup/shutdown, settings, token storage, packaging | `docs/actions/SHARED_INPUT_SESSION_FA.md` (governing; regression and live steps), `docs/actions/SHARED_INPUT_SESSION.md`, DR-0003 | Remembered consent, `AGENTS.md` section 15 (5, 6) |
| Window or control targeting, geometry, GNOME extension | `docs/actions/CONTROL_POLICY.md`, `docs/desktop/ACTIVE_APP_OBSERVATION.md`, `docs/desktop/BACKEND_PROTOCOL.md` | Targets re-resolved before input; stale or ambiguous evidence rejects; no guessed coordinates (7) |
| Deadlines, cancellation, late results | `docs/actions/DESKTOP_OPERATION_LIFECYCLE.md`, DR-0004 | Inherited deadline and cancellation generation (3, 8) |
| Action outcomes | `docs/actions/ACTION_POSTCONDITIONS.md` | Dispatch is not a verified effect; `unknown` is never retried automatically (9) |
| Audio or STT | `docs/architecture/OVERVIEW.md`, `src/kyrin/stt/contracts.py` | Acquisition separate from processing; replaceable engines; only final transcripts act (1, 2, 3) |
| Language surfaces | `docs/LANGUAGE_POLICY.md` | Independent surfaces; literal targets never translated (10) |

Decision records are in `docs/decisions/`.

## 3. Plan proportionally

- Local, obvious change: no written plan; implement and verify.
- Multi-file or behavior change: before editing, state the goal, files,
  approach, risks and acceptance criteria (the tests that will prove it).
  Explain the key design decision to the owner in Persian (`AGENTS.md`
  sections 3 and 13).
- Stop for owner approval on any decision that "Decision authority" in
  `docs/development/ENGINEERING_PROTOCOL.md` assigns to the owner, and
  explain any new dependency before adding it (`AGENTS.md` section 9).
  Routine implementation proceeds without asking.
- Keep contracts separate from implementations, inject dependencies, and
  explain any move of responsibility between components.
- If the change makes a document inaccurate, updating it is part of the task;
  use the `kyrin-technical-writing` skill for that part.

## 4. Debug from evidence

- Record the observed symptom (exact error, log line or test id), the
  expected behavior, and which statements are facts and which are hypotheses.
- Reproduce with the smallest deterministic command, for example one pytest
  node id with `-x`. If reproduction needs the live desktop, microphone,
  Telegram, model inference or a GUI, do not run it: ask the owner for the
  observation or logs and mark the hypothesis UNVERIFIED.
- Test one hypothesis at a time and confirm it with evidence before changing
  code. If a change does not alter the evidence, revert your own attempt
  instead of stacking another guess.
- Fix the root cause and add a regression test that fails before the fix and
  passes after it, when the behavior is deterministic.
- Never weaken assertions, add skips or xfail, widen timeouts, catch broad
  exceptions, or relax a gate, permission, target or freshness check to make
  a symptom disappear.

## 5. Verify

Use `.venv/bin/python`, or `local-data/quality-venv/bin/python` on the
owner's machine. Always set `PYTHONPATH="$PWD/src"` for direct runs: an
editable install may point at another copy of `kyrin` (the quality venv
does), and `pyproject.toml` adds only `.` to the pytest path. Confirm with
`python -c 'import kyrin; print(kyrin.__file__)'` when in doubt.
`tests/conftest.py` isolates HOME, XDG, D-Bus and display variables for
each test.

```bash
PYTHONPATH="$PWD/src" .venv/bin/python -m pytest -q tests/<pkg>/test_<name>.py
.venv/bin/python -m ruff check <changed paths>
PYTHONPATH="$PWD/src" .venv/bin/python -m mypy <changed paths>
.venv/bin/python scripts/development/check.py --output-dir local-data/quality/<task>
```

- Run focused tests first, then the full gate (`check.py`, which validates
  source provenance) for any behavior change. Desktop input changes also
  need the regression files listed under "Desktop input regressions" in
  `docs/development/QUALITY_GATE.md`.
- Report each check as PASSED, FAILED, SKIPPED or NOT RUN, with the command
  and counts. Call a failure pre-existing only when it is shown to fail
  without your change; otherwise say its cause is not established.
- Deterministic tests do not establish live desktop, microphone, model or
  reboot behavior; name what still needs owner live acceptance.
- Finish with `git status --porcelain=v1` and confirm that only the intended
  files changed.

## 6. Report

Report to the owner in Persian with English identifiers: what changed (exact
files), why, check results with status, what is confirmed, hypothesized or
UNVERIFIED, and which decisions belong to the owner. Passing checks do not
authorize a commit, push or release (`docs/RELEASE_POLICY.md`).
