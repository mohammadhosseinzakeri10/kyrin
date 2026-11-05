# Telegram integration audit — 2026-10-30

## Addendum 2026-11-05: Main menu action depends on Telegram screen-reader setting

Owner-live evidence on Telegram Desktop 7.3.5 (Qt accessibility 6.11.2) with GNOME
session toolkit accessibility enabled for a pilot (`toolkit-accessibility=true`,
AT-SPI `IsEnabled=true`, `ScreenReaderEnabled=false`). Read-only probes report
roles, states and action counts only; no probe activates a control.

| State | Main menu node | Opt-in KYRIN trace | Outcome |
|---|---|---|---|
| Before | one `button`, VISIBLE/SHOWING/ENABLED/SENSITIVE, not FOCUSABLE; Action interface with zero actions | `opener_located`, `opener_action_route`, `failure_no_action` | `failed (telegram_accessibility_unavailable)`; no input sent |
| After | same node also FOCUSABLE; exactly one action, `setFocus` | `opener_focus_route`, `opener_dispatched`, `rows_not_ready`, `destination_verified`, `destination_dispatched` | Settings `confirmed`; owner saw Settings open |

Intervention between the two states: the owner found Telegram's internal
setting "Disable screen reader mode" ON, turned it OFF, then fully quit and
relaunched Telegram through its ordinary launcher. A blue screen-reader banner
then reappeared in Telegram.

- CONFIRMED: the before/after node states, traces and outcomes above. In the
  before state `action_index` returned `None` and `_activate_control` failed
  closed ([telegram_portal_helper.py](../../src/kyrin/actions/platforms/telegram_portal_helper.py));
  the focus-only route requires exactly one `setFocus` action. This is the
  intended contract, not a routing defect.
- SUPPORTED inference: the Telegram setting governs whether this node exposes
  `setFocus`. The setting change and the restart were applied together, so the
  observations are not an isolated experiment.
- UNVERIFIED: the internal Telegram/Qt mechanism (for example widget focus
  policy); whether the earlier unexplained blue banner was this same indicator;
  any package-update cause. Navigation failures predate the observed executable
  timestamp.
- Back after Settings returned `dispatched_unverified` although the owner saw it
  succeed. This is by design: Back/Cancel sends one Escape, which has no generic
  destination postcondition (`_open_telegram_setting` in
  [telegram.py](../../src/kyrin/actions/platforms/telegram.py)).
- The single successful `helper_ms=3048` is one observation, not a baseline. No
  authoritative Telegram menu latency target exists to compare against.
- Later the same day, three fresh ordinary launches and one launch after
  re-login reproduced the success. The re-login run lacks a menu trace because
  GNOME autostart had already started KYRIN without tracing; the traced launch
  only activated that instance through `SingleInstanceGuard` and exited 0.
- Owner-approved unavailable guidance: only the before-state shape (unique valid
  Qt Main menu, no Action interface or zero actions) now yields
  `MENU_ACTION_UNAVAILABLE` → `telegram_menu_action_unavailable`, a hedged
  message about the Telegram option. It is still a fail-closed `FAILED` with no
  input. All other accessibility failures keep
  `telegram_accessibility_unavailable`.
- Owner live acceptance of that guidance:
  - With the option OFF, Settings returned `confirmed`.
  - With the option ON and Telegram relaunched, the probe reproduced the
    actionless node, the command returned
    `failed (telegram_menu_action_unavailable)`, and a screenshot showed the
    message in the app.
  - After the option was restored and Telegram relaunched, the probe showed
    sole `setFocus` again.
  - The owner then adopted the prerequisite policy and closed KYR-004; see the
    [navigation design](TELEGRAM_CHAT_NAVIGATION_DESIGN.md).

Two prerequisites are distinct and both were present in the successful run:
session toolkit accessibility (exports application trees) and Telegram's own
screen-reader setting (affected this node's action). Neither is RemoteDesktop
portal consent, input-session readiness, or `ScreenReaderEnabled`. KYRIN does
not change either setting. Session-wide accessibility also lets other
authorized local accessibility clients read application UI. Stability across
launches and re-login was later accepted and the policy decided (2026-11-05,
bullets above).

## Latest continuation: native retry fails; production locator verified separately

The owner repeats Profile twice and Calls once with correct final intents. All
three fail as `telegram_menu_uncertain`; the owner sees no destination selected.
Final-text completion times are 5058, 5106 and 4784 ms; these three failed attempts
are not a latency distribution. Back is dispatched_unverified without a separately
confirmed effect. Later Stop presenting and unrelated speech remain separate from
this navigation evidence. End diagnostics show GUI-requested standby, not an exact
voice Stop, empty queues/no reported worker failure, 5172 matching chunks, backlog
high 544 ms and twelve OCR/zero COMMAND resource calls. This is an end-state view,
not a whole-session loss guarantee or new model benchmark.

The owner then runs a read-only probe through the actual production `_LiveControl`.
Main menu, My Profile and Calls verify on all three samples with a stable original
window and sole setFocus action. Each constructor-plus-explicit-resolution sample
takes 707–828 ms. This proves the locator works on the manually opened menu, not
that automatic opening-to-selection succeeds. A later assistant metadata-only
attempt reports Telegram not foreground and is excluded from timing comparison.

Correct the common execution sequence: attempt semantic menu navigation before
OCR. When semantic rows are absent, only the independently recognized Qt profile
may open its verified menu directly; an unprofiled provider returns
`MENU_NEEDS_VISUAL` without input and retains visual read-before-toggle. After
one opener input, make at most four fresh, guarded row observations with 100 ms
between reads. No input is retried. Missing evidence uses the existing stable OCR
fallback, stopping on its first absent read; a present row still needs agreement
between observations. A blank fallback now costs one menu OCR read rather than
the former initial read plus three absent reads. Destination postconditions stay
independent and unchanged.

Remove redundant complete traversals, retaining Shell identity/token/frame checks
on both sides of the initial inventory and every resolution. Full object/ancestry/
bounds/uniqueness/state checks remain before focus/explicit activation and after
focus before Space. Cancellation/input-generation checks remain immediately before
input. No identity, permission, confirmation or lifecycle guard is dropped.

Opt-in `KYRIN_TELEGRAM_MENU_TRACE=1` forwards only fixed menu-stage/result markers
and helper duration to stderr. It never forwards arguments, target text, arbitrary
helper stderr, transcripts, chat names or window tokens. The owner launch redirects
stderr into ignored local storage; diagnostic mode is per-process, not a preference
change. This makes a future failure distinguishable without another blind batch.

The installed automatic-transition failure's sole cause remains unproven. Bounded
late-row tests reproduce a race in the old single-read sequence. Separately, the
[upstream AbstractButton implementation](https://github.com/desktop-app/lib_ui/blob/master/ui/abstract_button.cpp)
can reach clicked through setDown on an Over-state release and also explicitly
from keyReleaseEvent. A hover-dependent double activation is an investigation
hypothesis, not an attested installed-binary defect. The next owner protocol moves
the pointer away and separates closed-menu from pre-opened-menu navigation.
No Telegram binary, personal setting or coordinate fallback is changed.

All 240 related and 3811 complete tests pass (96.19 s), along with syntax/Ruff/
strict mypy (482 files). Six controlled previous-source regressions fail before
and pass after; one old visual-read ordering assertion was updated for the intended
semantic-first sequence. Frozen 158-case/178-turn rules/recovery results/references
are unchanged. No fresh model/audio/assistant native input is credited. Native
effects and actual speed remain owner-pending. Private evidence/source bindings:
`local-data/l04-phases-09-12/owner-telegram-menu-retry-20261030/`.

## Continuation: menu opener is not destination dispatch

The later owner run reports that Profile and Calls only open the hamburger menu.
The exact recognized intents are already correct. Preserve that native failure;
the previous Settings/Privacy acceptance does not cover these destinations.
The owner's read-only probe exposes seven visible button rows with exact labels
and sole `setFocus` actions. A subsequent metadata-only check finds all seven
valid through their ancestors and sharing one parent. Hidden native menu-item
duplicates are not evidence for activating a visible row. Neither probe sends
input, captures the screen or changes accessibility preferences.

The common menu route can now resolve an exact semantic destination when the
existing stable OCR route cannot identify it. Require a unique visible, enabled
row and at least two known menu anchors under the same parent. Resolve its live
structural identity inside the independently bound process/window; focus and
activate through the same checked mechanism as the menu button. Read the menu
first, open it at most once if no menu rows exist, and never toggle it when rows
exist but the destination is missing. Unknown/duplicate/hidden/disabled rows,
changed windows and cancellation do not authorize activation. No fixed position,
window-local-to-screen conversion, Enter, guessed label or arbitrary model key
sequence is added. Existing capture-bound OCR fallback remains separate.

`MENU_ITEM_DISPATCHED` means the actual destination received input; it still
needs the existing independent destination postcondition to become `confirmed`.
`MENU_CLICKED` alone means only the opener received input. If no independently
verified row follows, the complete command is failed with
`telegram_menu_uncertain`, rather than presented as destination dispatch.

This is a shared path for the supported Profile, Calls, Settings, New Group and
New Channel entries, not five coordinate scripts. New Group/Channel remain entry
navigation only. The supported label catalog defines scope, not a screen layout.
Saved Messages/Archive/Contacts retain their existing guarded shortcut routes.
Native Profile/Calls effects still await a fresh owner run; automated control
activation is not native acceptance. Private evidence and source bindings:
`local-data/l04-phases-09-12/owner-telegram-menu-items-20261030/`.

## Architecture direction within the current scope

Use the existing separation: utterance/model supplies a typed intent; live
observation grounds its target; a platform adapter performs a bounded action;
an independent observation checks the postcondition. Permissions, cancellation,
generation, deadlines, input ownership and original window identity constrain
every action. A model proposal is not evidence that a control exists or that
execution succeeded. The same contracts already serve generic visible controls,
window selection and application adapters.

Prefer native semantic interfaces where this installed provider exposes usable
objects. Existing visual evidence can supply a fallback under its own confidence,
capture and identity guards; coordinates from a current verified observation are
different from hardcoded positions. Provider-specific metadata (for example Qt
button focus versus GTK actions) belongs in adapters. Reliable support for every
application cannot be inferred from this correction. A general free desktop
planner or replacement model is outside stages 9–12 and is not introduced here.

Earlier native result: the owner confirms Settings and Privacy and Security
open as requested. Preserve Settings confirmed and Privacy dispatched_unverified.
Accept only those navigation effects, not every view/setting or a separately
instrumented menu activation branch. The owner subsequently also accepts Archive
variants and successful Back attempts; one correct Back final is still missed.
No setting values are changed and ordinary-launch activation remains open.

## Scope and observed failure

The owner supplies correctly recognized Settings and Privacy commands, both
rejected as `telegram_accessibility_unavailable`. A later intended Settings
utterance is transcribed as Sitting and remains a literal contextual label;
Settings is not open, so it does not execute. No guessed alias is added.

Read-only inspection of the real Main menu button finds one Action, `setFocus`,
with valid visible/enabled states. It does not advertise press/click. The former
generic action selector therefore rejects this button. This prerequisite is
shared by all destinations that open the main menu, not only Settings/Privacy.
The original helper exception trace is absent; this establishes the observed
capability mismatch without assigning every past rejection the same sole cause.

## Bounded common correction

Keep explicit, uniquely advertised activation actions as the preferred path.
Only the independently bound Qt/window-local Main menu profile with exactly one
`setFocus` action may use a keyboard path. Invoke that focus action, require the
same live object to report FOCUSED, recheck Shell desktop ID/PID/original window
token/frame and input lifetime, then send one Space press/release. No Enter,
arbitrary shortcut, coordinate conversion, retry or unknown-action fallback is
allowed. Changing/ambiguous controls, rejected focus, cancellation and revocation
remain blockers. SetFocus is never itself classified as clicking.

The [upstream button implementation](https://github.com/desktop-app/lib_ui/blob/master/ui/abstract_button.cpp)
handles Space press/release as button activation. That is implementation evidence,
not proof of the installed build's native effect. A dispatched key is not a
confirmed open menu. Existing independent OCR menu anchors, stable target reads,
capture geometry and destination postconditions still authorize subsequent clicks.

The original window token is now also retained for Saved Messages, Archive,
Contacts and Escape. Shortcuts recheck identity/lifetime before Ctrl and before
the destination key. A window change between them suppresses the destination key
and releases the owned modifier. Existing shared input ownership, no-setup action
behavior, persisted consent, model/device and personal preferences are unchanged.

## Route audit

| Route | Shared prerequisites and reviewed behavior | Evidence boundary |
| --- | --- | --- |
| Saved Messages | Fixed Ctrl+0; original token and per-press checks; fresh header verification | Prior bounded owner effect accepted; new guards tested inertly |
| Archive / Contacts | Fixed Ctrl+9 / Ctrl+J; original token; bounded heading reads | Bounded owner effects accepted |
| Settings / Profile / Calls / New Group / New Channel | Shared semantic menu-row activation with independent sibling anchors when stable OCR is missing; existing capture-bound OCR path and destination reads retained | Every view route tested inertly; new Profile/Calls effects await owner; creation screens are navigation only |
| Settings sections | Exact known section/visible label, verified Settings context, stable row, bounded scroll/back and title reads | All 12 navigational section keys tested; default scale remains blocked |
| Focus-only search | Unique visible editable object and original window binding; no text | Locator verified; standalone visual focus remains unaccepted |
| Literal search | Object-directed edit, explicit GI Text read, prefix agreement, four-character UTF-8 batches | Exact owner query accepted; Unicode/current-build generalization not inferred |
| Named-chat / visible-list selection | No Enter/message send; independent local/global scope, stable rows/headers, selection expiry/cancel and ownership | Existing regressions retained; general named-chat native coverage remains open |
| Result/settings clicks | Region evidence, current capture/token/frame/pointer checks; no click after changed target | Existing geometry/focus/cancel suite retained; no pointer expansion in this patch |
| Lifecycle / permissions | Commands cannot set up input, disabled/unavailable input rejects; one input owner; durable consent untouched | Existing isolated regression suite and full gate; no owner settings changed |

## Regression and acceptance limits

Eight exact original-behavior failures are reproduced through the actual helper
entry point: focus-only Main menu activation, three shortcut changes after Ctrl,
and four shared-session window replacements. Three related acquisition cases
already reject correctly. Additional cases cover focus rejection/loss, replaced
objects, resize, cancellation, ambiguous actions, direct-action preference, and
all view/settings routes. Initial new-helper API/fixture mismatches are retained
separately from this controlled before/after evidence.

No native action is performed by the assistant. The subsequent owner observation
accepts bounded Settings/Privacy; other untested routes remain open. Ordinary Telegram launch still needs
an accessibility decision; the temporary owner-launched bridge is not a permanent
settings change. STT Sitting, raw model behavior, backend dispatch and native
effect remain separate. The accepted literal search and earlier desktop bundles
must not be repeated merely because this audit exists.

Private raw evidence and source bindings are under
`local-data/l04-phases-09-12/owner-telegram-audit-20261030/`.
