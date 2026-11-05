# KYRIN open work queue

Current audit: 2026-11-04, working tree at `ebbf4da7d08babe11dd80dfeb5aca502c19c353f`.
This is the single shared queue for Codex and Claude Code, not a project history.
Audit inspection was static only. Prior 3,811-test gate evidence was matched to
513 current code/configuration files; no new tests, inference or live checks ran.

## Shared workflow

- When the owner names an ID, read this file, locate that task, then load only
  its relevant contracts, implementation, direct callers and tests. Start with
  [project context](../PROJECT_CONTEXT.md) and [agent policy](../AGENTS.md).
- Inspect the live working tree before editing; preserve all owner changes.
  Reconfirm the finding against current code and explain the proposed change
  and required verification. This queue alone does not authorize implementation.
  Implement only when separately authorized by the owner.
- Follow existing permission, security, privacy and test rules. Use the same
  stable ID in both agents; never create a competing queue or silently replace
  another agent's edits. Re-read the file immediately before updating it.
- Evidence must meet every acceptance criterion. Code written is not completion.
  A test not run, or run against uncertain source, is not a pass. Label static,
  deterministic and owner-live evidence separately. Behavior changes require
  focused regressions and the existing full quality gate.
- Keep partial/blocked tasks in place with remaining work or a short blocker;
  preserve their IDs and owner notes. Owner-live requirements remain open until
  the owner supplies observations and they have been assessed.
- Remove a task's entire entry and index row only after all its criteria have
  supporting evidence. Do not accumulate completed history here or move it into
  PROJECT_CONTEXT.md. Update authoritative references only when their behavior
  or invariant changes, under normal policy and separate authorization.
- Never renumber surviving IDs. Add genuinely new work with a new stable ID.
  When the final open task is verified and removed, leave this existing file
  **empty, exactly zero bytes**; do not delete it or remove unverified work.

Statuses: ORANGE = correction/completion remains; RED = missing agreed V1 work;
GRAY = verification/owner decision remains. GREEN work is excluded.
No missing agreed V1 implementation was established as RED in this audit.
Portable installers, non-GNOME adapters, arbitrary automation and enabling
unapproved document models are not inferred V1 requirements.

## Task index

| ID | Priority | Status | Open deliverable | Dependencies |
| --- | --- | --- | --- | --- |
| KYR-002 | P1 | GRAY | Owner-verify Telegram same-PID replacement rejection | Owner run |
| KYR-003 | P1 | ORANGE | Reconcile misleading power/input lifecycle summaries | None |
| KYR-005 | P1 | ORANGE | Accept the corrected Telegram menu transition | KYR-002 |
| KYR-006 | P1 | GRAY | Establish L01 live stability and first-wake acceptance | Owner run |
| KYR-007 | P1 | GRAY | Close remaining L04 safety/lifecycle boundaries | KYR-002, KYR-006 |
| KYR-008 | P2 | GRAY | Close residual L04 functional acceptance | KYR-005; final closure KYR-007 |
| KYR-009 | P2 | GRAY | Decide and measure an English V1 quality/resource baseline | Owner criteria; live timing KYR-006 |
| KYR-010 | P2 | GRAY | Validate native capture geometry and protected regions | Owner-supported setup |
| KYR-011 | P2 | GRAY | Verify remembered input after a real OS restart | KYR-003; owner run |
| KYR-012 | P2 | GRAY | Accept current captions and independent language/voice output | Owner run |

## KYR-002 — Retain Telegram window identity through postconditions

**Status:** GRAY · **Priority:** P1 · **Verification:** owner live (deterministic done).

**Finding:** Corrected in the working tree (uncommitted, 2026-11-04). Each
Telegram operation binds the window token focused at its start; selection and
paging bind the token of the capture that showed their rows. Helpers receive it
as a final `window=` argument and reject any other window before input; scrolls
carry `WindowObservation` evidence; every OCR read rejects captures from another
or untokened window (`same_operation_window`); postconditions bracket identity
and token. No destination window transition is accepted. Deterministic evidence:
same-PID replacement after a helper, during and around a postcondition read, at
selection completion and before a scroll sends no input and never yields
CONFIRMED; stable navigation still confirms. Focused suites and the full gate
passed (3,849 tests, checkout-source provenance).

**References:** [telegram.py](../src/kyrin/actions/platforms/telegram.py), [telegram_portal_helper.py](../src/kyrin/actions/platforms/telegram_portal_helper.py);
[src/kyrin/actions/telegram_verification.py](../src/kyrin/actions/telegram_verification.py);
[src/kyrin/app/qt/chat_verifier.py](../src/kyrin/app/qt/chat_verifier.py);
[test_telegram_saved_messages.py](../tests/actions/test_telegram_saved_messages.py), [test_telegram_portal_focus.py](../tests/actions/test_telegram_portal_focus.py), [test_telegram_verification.py](../tests/actions/test_telegram_verification.py), [test_qt_chat_verifier.py](../tests/app/test_qt_chat_verifier.py);
[postconditions](actions/ACTION_POSTCONDITIONS.md).

**Next action / work:** Owner runs one benign same-PID replacement case on the
current build and reports content-free outcome codes. Use an AT-SPI-free route
(Saved Messages, Archive or Contacts shortcuts): the first live attempt used
Open Settings, which stopped earlier as `telegram_accessibility_unavailable`
(an accessibility prerequisite since resolved) and is no replacement evidence
either way.
**Dependencies / decision:** None beyond the owner run. Any legitimate destination
window transition found live needs an explicit owner decision; none is approved.
**Acceptance (remaining):** Owner observes that a benign Telegram navigation
interrupted by a same-process replacement window sends no further input and is
not reported CONFIRMED, and that the same navigation without replacement still
confirms. No automatic retry, renewed age or consent change.
**Skills:** `kyrin-engineering-workflow`, `kyrin-live-acceptance`.

## KYR-003 — Reconcile power and input lifecycle summaries

**Status:** ORANGE · **Priority:** P1 · **Verification:** static; deterministic evidence review.

**Finding:** PROJECT_CONTEXT describes real power actions as two-step, and the
semantic contract also promises two confirmations. Production
`SystemPowerFlow.start` instead uses stored permission and
`_start_authorized`; two-stage confirmation belongs to preview/legacy.
The lifecycle note still requires setup after app restart. Conversely,
PROJECT_CONTEXT invariant 6 and DR-0003 say microphone shutdown closes input,
while Qt/factory cleanup keeps the app-owned input session. These discrepancies
can mislead safety reviews and future fixes.

**References:** [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md);
[docs/commands/SEMANTIC_UNDERSTANDING_CONTRACT.md](commands/SEMANTIC_UNDERSTANDING_CONTRACT.md);
[docs/actions/DESKTOP_OPERATION_LIFECYCLE.md](actions/DESKTOP_OPERATION_LIFECYCLE.md);
[docs/decisions/DR-0003-persistent-permissions-and-remembered-input-consent.md](decisions/DR-0003-persistent-permissions-and-remembered-input-consent.md);
[src/kyrin/system_power/flow.py](../src/kyrin/system_power/flow.py), [window.py](../src/kyrin/app/qt/window.py), [ubuntu.py](../src/kyrin/app/platforms/ubuntu.py);
[tests/system_power/test_persistent_consent.py](../tests/system_power/test_persistent_consent.py), [tests/app/test_qt_window.py](../tests/app/test_qt_window.py);
[current power contract](actions/SYSTEM_POWER_ACTIONS.md) and
[governing input contract](actions/SHARED_INPUT_SESSION_FA.md).

**Next action / work:** Correct only current claims after checking the cited
contracts; preserve labeled history and preview semantics.
**Dependencies / decision:** No behavior change is authorized by this task;
refer any actual policy conflict to the owner.
**Acceptance:** Current summaries consistently distinguish saved power consent,
OS dialogs, inert preview, app restart restore, microphone shutdown, normal exit
and explicit revocation. No code/permission behavior changes. Relative links
resolve and each corrected claim cites current implementation/evidence.
**Skill:** `kyrin-technical-writing`.

## KYR-005 — Accept the corrected Telegram menu transition

**Status:** ORANGE · **Priority:** P1 · **Verification:** owner live; static/deterministic if corrected.

**Finding:** Owner Profile/Calls commands previously failed as
`telegram_menu_uncertain`. The latest semantic-first opener/settle sequence
has source-matched deterministic evidence, but its native transition remains
unaccepted. The locator succeeding on a manually opened menu is a narrower
result. Hover/double activation is an unproven hypothesis.

**References:** [latest continuation](actions/TELEGRAM_INTEGRATION_AUDIT_2026-10-30.md);
[telegram.py](../src/kyrin/actions/platforms/telegram.py), [telegram_portal_helper.py](../src/kyrin/actions/platforms/telegram_portal_helper.py), [telegram_accessibility.py](../src/kyrin/actions/platforms/telegram_accessibility.py);
[test_telegram_live_controls.py](../tests/actions/test_telegram_live_controls.py), [test_telegram_saved_messages.py](../tests/actions/test_telegram_saved_messages.py);
[docs/development/L04_PHASES_09_12_OWNER_ACCEPTANCE_FA.md](development/L04_PHASES_09_12_OWNER_ACCEPTANCE_FA.md) §12-f.

**Next action / work:** Prepare the existing closed-menu versus pre-opened-menu
owner protocol with loaded-code proof and fixed-marker-only diagnostics.
**Dependencies / decision:** After KYR-002 for final source acceptance; temporary
bridge may isolate the route; production uses the owner-accepted accessibility
prerequisite ([navigation design](actions/TELEGRAM_CHAT_NAVIGATION_DESIGN.md)).
**Acceptance:** Both Profile and Calls reach the requested destination from the
two stated menu conditions; opener-only dispatch is never destination success.
Assess actual effects separately from ActionOutcome; preserve failures/unknowns
and send no automatic retry. No call is placed. Any fix passes focused/full checks.
Do not repeat already accepted Settings/Privacy/Archive bundles.
**Skill:** `kyrin-live-acceptance`.

## KYR-006 — Establish L01 live stability and first-wake acceptance

**Status:** GRAY · **Priority:** P1 · **Verification:** owner live + source/evidence review.

**Finding:** Bounded queues, selected-engine standby, shutdown and resource
cancellation have deterministic coverage. The dedicated L01 pilot/long-run
acceptance remains pending, and DR-0010 leaves the first wake unverified.
Individual successful listening controls do not prove sustained stability.

**References:** [accept_l01.py](../scripts/audio/accept_l01.py), [l01_stability.py](../scripts/audio/l01_stability.py);
[tests/runtime/test_l01_acceptance.py](../tests/runtime/test_l01_acceptance.py);
[tests/audio/test_live_idle_backpressure.py](../tests/audio/test_live_idle_backpressure.py);
[live protocol](development/L01_LIVE_ACCEPTANCE_FA.md);
[listening decision](decisions/DR-0010-voice-listening-modes.md).

**Next action / work:** Prepare the existing inert-action pilot; assess it before
the documented long run. Do not launch capture or inference as an agent.
**Dependencies / decision:** Owner selects an already-installed configuration and
runs the checks; hardware disconnect is optional and must stay marked NOT RUN.
**Acceptance:** Assess complete stable-source reports for first wake, long silence
and speech onset, model wait, consecutive turns, TTS/AEC or guard fallback, explicit
controls, fresh session and cleanup. Required scenarios have owner observations;
no unexplained failures, dropped required transition evidence or leftover owned
workers. Exit code alone is insufficient; skipped required scenarios stay open.
**Skill:** `kyrin-live-acceptance`.

## KYR-007 — Close remaining L04 safety and lifecycle boundaries

**Status:** GRAY · **Priority:** P1 · **Verification:** deterministic + owner live.

**Finding:** Synthetic coverage and limited owner successes exist; the governing
B01–B18 matrix is not fully accepted. In particular, current-source same-app window
replacement, cancellation while understanding and stale completion across stop/
restart must not be inferred from successful ordinary navigation.

**References:** [docs/development/L04_PHASES_09_12_OWNER_ACCEPTANCE_FA.md](development/L04_PHASES_09_12_OWNER_ACCEPTANCE_FA.md) §4;
[command_runtime.py](../src/kyrin/runtime/command_runtime.py), [command_worker.py](../src/kyrin/runtime/command_worker.py);
[test_plan_cancellation.py](../tests/runtime/test_plan_cancellation.py), [test_listening_state.py](../tests/runtime/test_listening_state.py);
[test_l04_content_boundaries.py](../tests/commands/test_l04_content_boundaries.py), [test_control_window_binding.py](../tests/commands/test_control_window_binding.py);
verified scroll/More window binding: [scroll contract](actions/CONTROL_POLICY.md#focused-scroll-and-more),
[test_scroll_window_binding.py](../tests/commands/test_scroll_window_binding.py), [test_desktop_scroll.py](../tests/actions/test_desktop_scroll.py), [test_desktop_scroll_helper.py](../tests/actions/test_desktop_scroll_helper.py);
[semantic contract](commands/SEMANTIC_UNDERSTANDING_CONTRACT.md).

**Next action / work:** Reconcile newest accepted rows, then hand off only remaining
boundaries using inert fixtures. Link KYR-002 replacement evidence and the verified
scroll/More binding above instead of repeating them.
**Dependencies / decision:** KYR-002 and KYR-006 for affected boundaries.
**Acceptance:** Every required boundary has assessed evidence at its proper level:
no action from partial/duplicate/negated/content speech; no old-window retargeting,
stale More, late cancelled action or post-restart replay; fresh work succeeds.
Already accepted rows remain credited. Record NOT RUN/INCONCLUSIVE explicitly;
never exercise real send/delete/payment/power operations in this matrix.
**Skill:** `kyrin-live-acceptance`.

## KYR-008 — Close residual L04 functional acceptance

**Status:** GRAY · **Priority:** P2 · **Verification:** owner live + acceptance reconciliation.

**Finding:** Later owner evidence accepts window operations/pickers, Terminal
bundles, selected chat navigation and consent restoration. It does not close the
entire A-family matrix. The remaining Telegram bundle includes creation-screen
entry, focus-only search and visible/global-result variants; supported route
coverage must be reconciled with the latest audit before another run.

**References:** [docs/development/L04_PHASES_09_12_OWNER_ACCEPTANCE_FA.md](development/L04_PHASES_09_12_OWNER_ACCEPTANCE_FA.md)
§3 and §12-s through §12-f;
[Telegram route audit](actions/TELEGRAM_INTEGRATION_AUDIT_2026-10-30.md);
[telegram.py](../src/kyrin/actions/platforms/telegram.py), [telegram_selection.py](../src/kyrin/actions/telegram_selection.py);
[test_telegram_saved_messages.py](../tests/actions/test_telegram_saved_messages.py), [test_telegram_selection.py](../tests/actions/test_telegram_selection.py), [test_telegram_selection_visual.py](../tests/actions/test_telegram_selection_visual.py).

**Next action / work:** Produce a small residual-row handoff from the existing
matrix; retain prior accepted rows rather than restarting all acceptance.
**Dependencies / decision:** KYR-005 for affected Telegram routes; final L04
closure also needs KYR-007 and assessed required language-quality evidence.
**Acceptance:** Each required functional row is tied to reviewed current-source
owner evidence, or an explicit owner-approved V1 scope decision. Same-name/global
selection preserves identity uncertainty and cancellation; search does not select
or send. Group/channel tests enter screens only, never create anything. Untested
or merely dispatched effects remain open; no claim of universal app support.
**Skill:** `kyrin-live-acceptance`.

## KYR-009 — Decide and measure the English V1 quality/resource baseline

**Status:** GRAY · **Priority:** P2 · **Verification:** owner decision + deterministic evaluation + owner live.

**Finding:** Recovery thresholds are experimental, real English speech coverage
is limited, and accuracy/latency/resource acceptance thresholds are undefined.
Designed text results and serialized model admission do not establish acoustic
quality, native latency or RAM/VRAM peaks for the chosen configuration.

**References:** [language policy](LANGUAGE_POLICY.md);
[recovery limits](commands/L04_RECOVERY_POLICY.md);
[resource policy](app/MODEL_RESOURCE_POLICY.md);
[scripts/stt/evaluate_offline_stt.py](../scripts/stt/evaluate_offline_stt.py);
[evaluate_l04_audio.py](../scripts/commands/evaluate_l04_audio.py), [measure_model_composition.py](../scripts/commands/measure_model_composition.py);
[tests/commands/test_l04_audio_evaluation.py](../tests/commands/test_l04_audio_evaluation.py), [tests/stt/test_evaluation_languages.py](../tests/stt/test_evaluation_languages.py).

**Next action / work:** Agree a bounded English acceptance slice and measurable
criteria before an explicitly authorized run using existing evaluators.
**Dependencies / decision:** Owner chooses target configuration, required cases,
quality/latency/resource limits and any new recording consent. Use KYR-006 for
live stability; no download/model swap or threshold tuning is implied.
**Acceptance:** Freeze independent references and code/model identity; report
sample/speaker limits, transcription and exact operation/target/direction errors,
false proposals, clarification, separate latency boundaries and observed device/
resource measurements. Keep designed text, human audio and live results separate.
Assess against owner-approved criteria; preserve misses and unresolved criteria.
Do not tune on the held-out slice or claim accent generalization.
**Skills:** `kyrin-evaluation-integrity`, `kyrin-live-acceptance`.

## KYR-010 — Validate native capture geometry and protected regions

**Status:** GRAY · **Priority:** P2 · **Verification:** owner live + existing deterministic evidence.

**Finding:** Real-image deterministic tests cover scale/origin/crop transformations
and region validation, but the capture prototype explicitly leaves live mixed-DPI,
Wayland/XWayland and current protected-region behavior unverified. Old one-image
capture/grant acceptance does not establish these later contracts.

**References:** [capture contract](vision/GNOME_ACTIVE_WINDOW_CAPTURE_PROTOTYPE.md);
[integrations/gnome-shell/window-capture-prototype@kyrin.local/extension.js](../integrations/gnome-shell/window-capture-prototype@kyrin.local/extension.js);
[src/kyrin/vision/capture_geometry.py](../src/kyrin/vision/capture_geometry.py);
[tests/app/test_gnome_geometry_pipeline.py](../tests/app/test_gnome_geometry_pipeline.py);
[tests/actions/test_capture_geometry_flow.py](../tests/actions/test_capture_geometry_flow.py).

**Next action / work:** Prepare synthetic corner/center targets and region-change
checks on the owner's available supported setup, with loaded-extension proof.
**Dependencies / decision:** Owner defines the V1-supported display/session set;
unavailable combinations remain explicitly unverified, not automatically passed.
**Acceptance:** For every claimed configuration, observed targets map correctly;
changed protected pixels, moved/replaced windows, expired captures and revocation
reject input; unrelated changes follow the region contract. No double transform,
guessed geometry or private screenshot retention. Report exact tested coverage.
**Skill:** `kyrin-live-acceptance`.

## KYR-011 — Verify remembered input across a real OS restart

**Status:** GRAY · **Priority:** P2 · **Verification:** owner live + metadata review.

**Finding:** Token rotation, revocation and startup races are tested, and owner
Quit/relaunch cycles were accepted. The latest owner summary explicitly says this
does not prove persistence across an OS reboot.

**References:** [governing input contract](actions/SHARED_INPUT_SESSION_FA.md);
[input_session.py](../src/kyrin/actions/platforms/input_session.py), [input_session_owner.py](../src/kyrin/actions/platforms/input_session_owner.py);
[src/kyrin/app/qt/window.py](../src/kyrin/app/qt/window.py);
[test_input_session.py](../tests/actions/test_input_session.py), [test_input_session_bus.py](../tests/actions/test_input_session_bus.py);
[tests/app/test_qt_window.py](../tests/app/test_qt_window.py);
[docs/development/L04_PHASES_09_12_OWNER_ACCEPTANCE_FA.md](development/L04_PHASES_09_12_OWNER_ACCEPTANCE_FA.md) opening status.

**Next action / work:** Prepare one controlled owner restart handoff, preserving
saved consent and recording only content-free session/persistence metadata.
**Dependencies / decision:** KYR-003 clarifies lifecycle wording; owner chooses
the restart time. Do not delete a token or revoke access merely to make a test pass.
**Acceptance:** On the stated supported portal, saved enabled capabilities restore
asynchronously once without setup; selected benign input works. Status/commands
never loop setup; unavailable/rejected OS persistence is visible and truthfully
assessed. Preserve accepted app-relaunch evidence and existing tokens/permissions;
unobserved reboot behavior remains open.
**Skill:** `kyrin-live-acceptance`.

## KYR-012 — Accept captions and independent language/voice output

**Status:** GRAY · **Priority:** P2 · **Verification:** owner live + existing deterministic evidence.

**Finding:** Caption ordering/localization fixes and independent language routing
are source-matched test-covered. PROJECT_CONTEXT still marks recent native caption
completeness unverified; inert voice tests do not prove installed pronunciation,
playback or native GNOME delivery.

**References:** [caption review](development/VISUAL_CAPTION_COMPLETENESS_REVIEW_2026-10-27.md);
[response language](responses/RESPONSE_LANGUAGE.md);
[presenter.py](../src/kyrin/responses/presenter.py), [visual_status.py](../src/kyrin/responses/visual_status.py), [gnome_status.py](../src/kyrin/responses/gnome_status.py);
[src/kyrin/tts/runtime.py](../src/kyrin/tts/runtime.py);
[test_visual_scenarios.py](../tests/responses/test_visual_scenarios.py), [test_language_contract.py](../tests/responses/test_language_contract.py);
[tests/app/test_ui_language_contract.py](../tests/app/test_ui_language_contract.py).

**Next action / work:** Prepare one bounded current-build native round using
already-installed voices and synthetic targets, reusing KYR-006 TTS observations.
**Dependencies / decision:** Owner chooses supported voice/language routes; an
absent optional voice is not a failed command or a new install requirement.
**Acceptance:** Question/execution/result/standby/off and auxiliary-error captions
stay truthful through delayed events; newer decisions are not overwritten.
UI/STT/response/status/voice settings stay independent, delayed responses retain
their language, literal mixed-script targets remain intact, and configured speech
is actually heard. Unavailable routes are reported explicitly without translation
or a success claim; record only the assessed configuration.
**Skill:** `kyrin-live-acceptance`.
