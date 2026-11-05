# English-primary V1 completeness review

Reviewed: 2026-10-27. This reviews the accepted language-maintenance scope
against source, tests and documentation rather than assuming the earlier
delivery covered every detail. Three remaining gaps were found and corrected.
No further implementation gap was identified within this reviewed scope.
Real speech/model and live desktop acceptance remain separate.

## Gaps corrected

1. **Regional request language in confirmations.** Qt and native GNOME close
   dialogs treated `fa_IR` and case/whitespace variants as English. They now
   normalize the label for presentation consistently with the response layer.
   English and unsupported-language fallback remain English. Targets, explicit
   approval, cancellation, deadlines and single-use decisions are unchanged.
2. **Voice-preview sample language.** A configured `fa-IR` voice started with
   an English sample. The sample now follows the voice's primary language,
   independently of interface language. Custom preview text survives interface
   changes, and the original configured route label is passed to preview.
3. **Language-specific evaluation results.** Documentation required separate
   language metrics but the generic STT evaluator only emitted aggregate totals.
   New reports now include `by_language` with weighted CER/WER and reference,
   edit and file counts. The old overall totals and raw per-item results remain
   unchanged. Source locale labels remain distinct; no stored reports or
   references are rewritten. A small shared metrics helper prevents the overall
   and language formulas from diverging.

## Coverage against the accepted direction

| Requirement | Implementation/evidence | Status |
| --- | --- | --- |
| English-primary V1 with preserved choices | English defaults; saved Persian/system/imported UI preferences retained; existing UI language-change integration tests inspected | Covered |
| Independent UI, speech, response and visual languages | Event-language response selection, fixed-language status captions, regional request dialogs and voice-specific preview samples | Covered within current supported catalogs |
| Complete English built-in messages | All 86 response catalog keys present in both languages; formatting placeholders match; question/notice/outcome tests retained | Covered |
| Original target text and Persian compatibility | Mixed-script dialogue/action tests, unchanged grammar/data and retained negation checks | Covered at the transcript/software boundary |
| English technical entry/reference documentation | Current policy, command, setup, architecture, evaluation and quality references; Persian teaching/history retained | Covered |
| Separate English/Persian evaluation evidence | `by_language` weighted metrics, mixed/single-language and regional-label tests; original results retained | Implemented |
| Avoid unnecessary replacement architecture | Existing catalogs, presenter, voice routes and execution boundaries retained; no dependencies added | Covered |
| English acoustic quality, accents, actual playback and native rendering | No new microphone/model/speaker/desktop session was run | Still requires separate live/model acceptance |

This is not a claim of universal English command understanding, reliable
mixed-script STT/pronunciation or zero remaining defects. The changes complete
the reviewed language-maintenance work, not general product acceptance.

## Verification

- The expanded regression set reproduced 19 relevant failures before the fixes;
  77 existing/control cases passed in that same run.
- After correction, all 173 focused confirmation, TTS, evaluation and language
  tests passed in 3.52 seconds. The expanded coverage adds 66 cases relative to
  the prior implementation.
- The unchanged full checker passed syntax, Ruff, strict mypy on 453 files and
  all 3282 tests in 86.10 seconds, without failures or skips. Source provenance
  matched this checkout. No production files changed during the run.
- A concurrent addition to `tests/audio/test_live_speech_cli_visual.py` and two
  documentation files appeared during that run. Both tests in that file passed
  separately afterward; global Ruff and strict mypy were rerun successfully on
  the latest 454 files. Those two tests are not added to the full-suite count.
- A subsequent concurrent visual-status/scenario update was also preserved.
  All 523 response, Qt-window, runtime and CLI-visual regression tests passed
  in 9.17 seconds afterward, with no source/test/integration drift during that
  focused run. Global Ruff and strict mypy still passed on 454 files. This
  post-gate verification is recorded separately rather than attributed to the
  earlier full-suite snapshot.
- The global lint error recorded by the earlier delivery was already corrected
  outside this task before this review. Earlier failed logs are preserved.

Evidence is under ignored `local-data/english-v1/completion-review/`: baseline
copies, before-fix and focused logs, catalog audit, full-check logs/provenance,
before/after hashes, drift details and the separate concurrent-test result.
The post-gate focused log and its own before/after hashes record the later
visual-status verification.
The earlier [delivery record](ENGLISH_V1_LANGUAGE_HANDOFF.md) remains historical.

No installed extension files, user settings, models, permissions, tokens,
recordings or corpus fixtures were changed. The native dialog change is source
plus a mocked GJS test, not an installed/live GNOME validation. No model or
dependency was downloaded; no commit or push was made.
