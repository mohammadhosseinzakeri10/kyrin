# English-primary V1 language delivery

**Follow-up:** The [completeness review](ENGLISH_V1_LANGUAGE_REVIEW.md) corrected
three remaining locale/preview/evaluation gaps and obtained a green full gate.
Its evidence supersedes the overall lint-failure status below. The earlier
results remain preserved as the original delivery record.

Reviewed: 2026-10-27. The owner authorized the English-primary direction while
retaining the existing Persian interface, bounded grammar and original data.
Implementation and deterministic verification for this language-maintenance
scope are complete. General English speech accuracy and live L01/L04 acceptance
are not established by this work.

## Changes

- Added the [language policy](../LANGUAGE_POLICY.md): English is the primary
  V1 development/command/acceptance language. Persian speech compatibility
  remains experimental, while the existing Persian UI stays selectable.
- Added current English guides for [commands](../commands/USER_COMMAND_GUIDE.md),
  the [quality gate](QUALITY_GATE.md) and
  [offline STT evaluation](../stt/STT_EVALUATION.md). Updated the public entry,
  setup, architecture, UI, response and corpus references to link them.
- Corrected the numbered-window status prompt in
  `src/kyrin/responses/visual_status.py` to follow the configured visual language
  instead of the action event's language. English captions stay English after
  a Persian command; Persian captions likewise retain their selected language.
- Added 70 deterministic language cases in
  `tests/responses/test_language_contract.py` and
  `tests/app/test_ui_language_contract.py`.
- Linked the maintenance policy from AGENTS section 11 and recorded the
  accepted direction and evidence in `PROJECT_CONTEXT.md`.

English UI defaults already existed. No migration or new language framework
was necessary. Speech responses continue to prefer a supported event language,
then session language, then English; they are not forced into the UI language.
Literal targets retain their original script. No grammar, translation catalog,
recording, reference fixture or historical Persian report was translated in bulk.

## Verification

| Check | Result |
| --- | --- |
| New language cases before the production correction | Six real visual-language failures; 64 cases passed |
| Focused response/UI/command/listening suite after correction | 565 passed in 3.09 seconds |
| Final full syntax check | Passed |
| Final full strict mypy | Passed on 452 files |
| Final full pytest | 3160 passed in 84.64 seconds |
| Scoped Ruff for both new test files and visual status | Passed |
| Final full Ruff | Failed: one unrelated long signature in `src/kyrin/app/qt/audio_file_import.py:67` |
| Final source provenance | Matched this checkout's `src/kyrin` |
| Final source/test/script drift | None; only this task's AGENTS/context documentation changed during the run |
| Local links in 13 new/updated entry/reference documents | Resolved |
| Python comments/docstrings in `src/` and `scripts/` | No Persian/Arabic-script prose requiring translation found |

The overall full gate remains unsuccessful because of the global lint result.
The unrelated signature was not edited by this task. Raw evidence is under
ignored `local-data/english-v1/final-check/`, with before/after snapshots and
`final-check-drift.json` beside it. The earlier full run is retained separately
under `full-check/`; it had 3158 passing tests, concurrent lint/type failures
and one unrelated test-file change during execution. Do not substitute its
results for the final run.

## What the tests establish

The tests cover English fresh-install defaults even on a Persian OS locale,
preserved saved selections, all current response-question and process-notice
kinds, English policy responses despite a Persian session fallback, all action
outcome languages, English/Persian negation and fixed visual-language prompts.
A transcript-to-coordinator-to-gate-to-fake-executor scenario preserves a
Persian chat target in an English dialogue. The actual response queue is
exercised with an inert synthesizer.

These checks do not open a microphone, load STT/command models, produce real
speaker output or act on the owner's desktop. They do not prove mixed-script
recognition or pronunciation. No settings, permission tokens, selected models,
installed extension, dependencies or downloads were changed; no commit or push
was made. Record real model/acoustic results separately by language under the
existing consent and evaluation contracts.
