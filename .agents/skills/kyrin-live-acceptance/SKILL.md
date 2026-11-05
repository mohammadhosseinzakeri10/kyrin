---
name: kyrin-live-acceptance
description: Prepares owner-run KYRIN live acceptance checks on the real desktop (microphone and listening modes, GNOME extensions, desktop input and remembered consent, app, window and Telegram actions) and interprets the owner's live reports and diagnostics. Use when the next step can only be verified by the owner live, or when the owner sends live results. Not for code changes, debugging or deterministic tests (kyrin-engineering-workflow), or offline model and corpus measurement (kyrin-evaluation-integrity).
---

# KYRIN live acceptance

`AGENTS.md` is the policy and wins on any conflict. Live checks are run by the
owner, never by the agent: no microphone capture, desktop actions, Telegram
commands, portal setup, extension installation, logout or reboot. The agent
reads code and documents and prepares the handoff. A code fix found here goes
through `kyrin-engineering-workflow`; recording an accepted result in a
document goes through `kyrin-technical-writing`.

## 1. Pin what is under test

- Name the change, its files and the deterministic checks already run, with
  their real status (PASSED, FAILED, NOT RUN). A live check does not replace
  a missing deterministic test.
- Read the subsystem's governing live steps instead of rewriting them:
  desktop input and remembered consent `docs/actions/SHARED_INPUT_SESSION_FA.md`
  (troubleshooting order, guard tests, restart/reboot steps); listening and
  speech `docs/audio/LIVE_SPEECH_PIPELINE_FA.md`; extensions
  `docs/desktop/BACKEND_PROTOCOL.md`, `docs/desktop/VISUAL_STATUS.md`,
  `docs/GETTING_STARTED.md`; power actions `docs/actions/SYSTEM_POWER_ACTIONS.md`.
- Read current markers from the code at handoff time, never from an older
  handoff, because they change between versions: the first line returned by
  `listening_diagnostics()` in `src/kyrin/app/controller.py` and each
  `build_id` in `integrations/gnome-shell/*/extension.js`.

## 2. Prove the new code is loaded

Most failed live rounds were old code still running. Include the relevant
owner-run, read-only checks before the first test step:

- **Qt app.** Only one instance runs (`src/kyrin/app/qt/single_instance.py`),
  and the window close button only minimizes. The owner quits with **Quit
  KYRIN**, then starts from the repository root:
  `PYTHONPATH="$PWD/src" .venv/bin/python -m kyrin.app.qt.main`. The menu
  launcher runs `.venv/bin/kyrin-desktop`; confirm that the `.venv` editable
  install points at this checkout before relying on it. The diagnostics
  marker (button "Copy listening state report") must match the code.
- **GNOME extension.** The installed copy under
  `${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/` is separate
  from the repository. On Wayland, changed or newly installed extension code
  runs only after the owner signs out and back in; locking the screen or
  closing a terminal is not a new session. Proof is the loaded `build_id`, for
  example `gdbus call --session --dest org.gnome.Shell --object-path
  /org/kyrin/ActiveApp --method org.kyrin.ActiveApp.GetCapabilities`
  (`/org/kyrin/VisualStatus`, `org.kyrin.VisualStatus` for the status
  character). Install success or the file on disk proves nothing. A
  `build_id` is a contract release, not a file hash: when the code changed
  without a new `build_id`, also compare the Shell start time
  (`ps -o lstart= -C gnome-shell`) with the installed file's modification time.

## 3. Write the handoff

Write it to the owner in Persian with English identifiers, commands and UI
labels, in this order:

1. Preconditions: unsaved work closed in the target apps; only the
   capabilities the test needs enabled; system power left off unless it is the
   subject; synthetic targets (test windows, the local fixture, Saved
   Messages) instead of real contacts or documents.
2. The loaded-code checks from section 2, with the expected marker values.
3. Numbered steps, one action each: the exact phrase or click, then the
   expected visible result and expected `ActionOutcome` (`confirmed`,
   `launch_accepted`, `dispatched_unverified`, `unknown`, `failed`).
4. Failure branch: what to capture before restarting or retrying anything
   (diagnostics copy, the `Action result` line, status caption, whether TTS
   was speaking, recent settings changes), and a second capture when timing
   matters.
5. What to send back, and what not to send: no private message text, audio,
   screenshots with personal content, tokens or full logs with personal paths.

Never ask the owner to weaken a permission, grant an extra capability, delete
a restore token, or repeat an `unknown` action to get a pass. Revocation or
token removal is a step only when the test is about revocation.

## 4. Interpret the owner's report

- Check the loaded-code markers first. A failure on old code is
  INCONCLUSIVE for the change, not FAIL.
- Classify each step as PASS, FAIL, NOT RUN or INCONCLUSIVE. Separate what the
  owner observed from what you infer, and label hypotheses.
- An owner report is owner live evidence: it is not a deterministic test,
  not portable to other machines, apps, layouts or languages, and not a
  measured benchmark. `dispatched_unverified` is not a confirmed effect.
- One success does not close an OPEN area in `PROJECT_CONTEXT.md` or
  `docs/VALIDATION.md`; say exactly which scenario was accepted.
- Keep raw owner evidence in Git-ignored `local-data/`; tracked documents get
  only a public-safe summary (`SECURITY.md`, DR-0009).
- End with the next step: a code fix, another live round with the changes
  listed, or a documentation update for the accepted scenario.
