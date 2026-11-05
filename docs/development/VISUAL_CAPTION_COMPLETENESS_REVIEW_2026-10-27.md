# Visual caption completeness review — 2026-10-27

The owner requested a second audit of the delivered caption work and implementation
of any remaining gaps. The earlier matrix covered supported kinds and ordinary
lifecycle transitions, but did not fully cover event ordering, independent notices,
asynchronous chat-selection work or the final GNOME delivery queue. This review
supersedes its completeness assessment without replacing its historical evidence.

## Reproduced gaps and corrections

| Gap | Corrected behavior |
| --- | --- |
| A streaming final/response arrived before VAD pause | The final seals its segment. A later pause cannot replace the ready reply/question with Transcribing. A genuinely new utterance still shows transcription progress. |
| Duplicate final or late partial for a sealed segment | It cannot reopen understanding after the result; a newer segment/stream remains accepted. |
| Inference started before VAD pause | Actual model progress is shown after the final instead of being suppressed by the old speaking flag. |
| Old selection expiry/prompt followed a newer conversation decision | Decision identity prevents the stale selection message from replacing the newer reply. An answer consumed by the existing selection flow may still complete its original action. |
| Voice/file warnings replaced the actual action/reply | The shared router appends the latest auxiliary notice to the primary caption and retains its actual state. A playback failure does not change an action's confirmed result into failure. Power confirmation retains its priority. |
| Busy file rejection emitted while holding the importer lock | Rejection signals now emit outside the lock, allowing Qt slots to read busy state without deadlocking. Rejecting a second file preserves the first file's pending completion. Stale completions cannot change window feedback. |
| Cancellation/outcomes hid standby or capture recovery | Captions retain current standby/recovery/shutdown guidance alongside the action outcome. Closing a file removes guidance inviting speech into ended capture. |
| Pending GNOME messages replayed obsolete phases | The worker keeps one latest pending caption, refreshes it after capability probing, and coalesces updates during an in-flight call. |
| A built-in chat question was encoded as a free conversation message | The producer supplies reviewed English/Persian alternatives. The visual presenter selects its own language; text/voice follow theirs. Original model replies have no alternatives and remain verbatim. |
| Selection completion and result paging bypassed the main executor-start wrapper | Optional start observers report the actual selection/paging worker boundary. Paging says Loading more chat choices for the original target; it returns to a choice prompt when a page is ready. |

The corrections fall into eight related areas: transcript ordering, stale dialogue
results, auxiliary notices, import delivery, concurrent lifecycle information,
desktop delivery, built-in localization and asynchronous selection progress.
Nineteen regression cases were unsuccessful before correction in five
captured batches. Expanded language cases and additional UI/protection tests then
cover the corrected behavior, not just the existence of enum mappings.

## Design and authority boundaries

`VisualStatusController` remains an observer of authorized runtime/capture/action
events. It records final transcript identity separately from the latest partial
and latest actual command/response decision. A new utterance resets the waiting
state without reopening a sealed transcript. The stale-result guard does not
discard a real action's result merely because the user has spoken its selection
answer using a later segment ID.

`VisualPresentationRouter.publish_notice` preserves primary activity/result text
and state while appending a local warning. A subsequent real presentation clears
that notice; repeated warnings do not repeatedly append themselves. The diagnostic
controller has the equivalent playback-error behavior, including a single standby
footer that file closure can remove. No raw backend exception
text is copied into the character caption.

`ResponseRequest.message_translations` is an optional immutable tuple of reviewed
local message alternatives. The existing Telegram selection producer supplies it;
the presenter selects it using the same supported-language rules as other built-in
messages. Genuine model replies keep an empty catalog and preserve their original
text and attributed language. This adds no translator, provider or dependency.

`TelegramChatSelection` adds optional observation callbacks at the start of its
existing selection/navigation workers. It retains its original permission,
cancellation, evidence, target, numbering, deadline and completion logic. The
callbacks cannot grant consent or issue a click. Existing input-session and broker
ownership remain intact.

The GNOME sink still uses its existing asynchronous worker and capability handshake.
Only pending presentation delivery changes; it adds no per-frame work, model call,
timer loop or thread. One display call already submitted to D-Bus cannot be recalled.
This review does not claim measured native latency or cross-process ordering.

## Verification

The final complete checker passed:

| Check | Result |
| --- | --- |
| Syntax | Passed |
| Global Ruff | Passed |
| Strict mypy | Passed on 456 files |
| Full pytest | 3313 passed in 86.36 seconds |
| Imported source | This checkout's `src/kyrin` |
| Source/test/integration/configuration drift | None across 476 files during the final run |
| Existing movement | All 11 source, Git HEAD and installed asset hashes matched |
| Local links in the five affected reference/index documents | Resolved |

This review adds 28 test cases; the full count also includes other repository work.
The maintained input-session regressions ran as part of the full suite:
`tests/actions/test_input_session.py`, `tests/actions/test_input_session_bus.py`,
`tests/app/test_qt_window.py`, `tests/app/test_qt_input_access.py` and
`tests/app/test_permission_token.py`. Earlier focused checks passed 761 related
tests before the supplementary language/notice expansion; the final focused
caption/selection/delivery check passed all 46 cases after it.

Raw evidence is under `local-data/visual-caption-review-2026-10-27/`:

- `before.txt`: speech ordering, stale selection, notice and busy-lock regressions.
- `more-before.txt`: standby, capture-recovery and closed-file guidance regressions.
- `transport-before.txt`: obsolete pending/during-handshake/in-flight delivery cases.
- `selection-before.txt`: visual-language and actual worker-start gaps.
- `standby-notice-before.txt`: repeated diagnostic warnings and ended-file guidance.
- `full-check/`: initial full run; all tests passed, but three test-only typing
  issues were reported. Their raw logs are preserved.
- `final-check/`: successful 3312-test check before the supplementary standby notice
  case; its original snapshot and logs remain intact.
- `verified-check/`: final source-provenance, syntax, lint, type and full-test results.
- `verified-before.json`, `verified-after.json`, `verified-drift.json`: unchanged
  file hashes during that final check.

The new selection tests use fake completions/navigation and wait for their actual
worker boundaries. Delivery tests use an inert thread and fake subprocess/handshake
functions; no GNOME D-Bus method is invoked. Import tests demonstrate same-thread
Qt signal reentrancy without hanging the test or opening audio hardware. The full
checker isolates HOME/XDG and uses private services for input regressions.

All eleven source and installed mascot animation/SVG/style assets are checked
against the original baseline and Git HEAD. The existing movement remains selected.
No installed extension, permission/token, personal setting or model changed; no
dependency installation, commit or push was performed.

## Remaining acceptance work

No additional software gap was identified in the reviewed current producer,
controller, Qt and transport paths after the corrections. This is bounded by the
supported scenarios and deterministic evidence; it is not a guarantee about every
possible future backend or timing pattern.

Live acceptance remains open. Restart the Python application normally and check:

1. Startup, standby, repeated Start listening, actual speech/final/reply, Stop
   listening and full microphone off as separate transitions.
2. A clarification, a real approved operation and its observed result; check that
   unverified input/launch acceptance does not claim confirmed success.
3. Chat choice, another visible results page, a valid number and cancellation;
   compare the caption with what the application is actually doing.
4. File success/error/cancellation, including rejecting another file during work;
   check that the original file outcome and resumed live state remain accurate.
5. Safe power preview and cancellation, with unrelated speech/status events;
   existing explicit approval remains required for any real system action.
6. Readability and response timing in the owner's GNOME session. Mock delivery
   and matching asset hashes do not establish native rendering quality.

These steps were not executed on the owner's microphone, speaker or desktop in
this review. The unchanged extension does not require reinstalling or restarting
GNOME Shell for these Python caption changes.

See the [current visual contract](../desktop/VISUAL_STATUS.md) and the
[original scenario matrix](VISUAL_CAPTION_SCENARIOS_2026-10-27.md).
