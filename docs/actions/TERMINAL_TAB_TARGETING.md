# Targeted Terminal tabs

## Current routes and native evidence

The owner confirms exactly one tab in the same healthy window after manually
opening Main Menu, with menu/minimize clicks still working. Accept only that
bounded manual-menu route. The earlier blocked trial's menu had closed after
New Top was misrecognized and before the second correct New tab; the owner
confirms this, so containment was appropriate. No open-state defect is inferred.

Ordinary launch uses the installed `Exec=ptyxis`, `DBusActivatable=true` entry.
`--standalone --new-window` starts a new instance ignoring existing instances,
as documented in installed ptyxis(1). It isolates process state for diagnosis;
it is the same app and does not grant KYRIN extra authority. Earlier instance
damage and its cause remain unresolved. A special launcher is not a final product
requirement.

An optional `terminal_tab_keyboard` grant now prepares automatic tab creation
without opening a popup. Granular settings leave it off by default; existing
trust-all semantics remain. App-open and desktop-control grants are still needed.
The new system-Python helper accepts only an original bounded window observation,
requires a live keyboard device and rejects other apps, modal/ambiguous frames,
open Main Menu, changed token/PID/bounds/structure, expiry and unsupported or
conflicting shortcut configuration. The unique existing new-tab setting must
still be Ctrl+Shift+T; no owner binding is modified or turned into arbitrary keys.

For each of three fixed key presses, the helper checks current owner authorization,
then configuration and exact target before dispatch. Releases run in reverse order
for only its own keys, including uncertain press delivery. Cancellation or unknown
release propagates to the existing owner teardown rather than retaining modifiers.
Output is dispatched-unverified, never an assertion that a tab appeared. There is
no action retry, automatic portal preparation or popup/MRU fallback. The required
helper capability is `terminal-tab-keyboard-v1` (2026-10-29 build).

Desktop Actions shows keyboard readiness separately. Explicitly enabling this
feature may require one owner-approved setup to add keyboard to the selected
device union; pointer-only users retain their existing device requests. Normal
Quit and startup restoration preserve the established token/consent contract.
Telegram keyboard consent alone is not the new capability grant. Selecting and
setting it up is owner work; no personal preference or OS consent was changed by
the assistant. Eighteen fixed-helper cases and the complete 3671-test gate pass,
including persistence, revocation, cancellation and literal popup containment.
Automatic keyboard creation and its native persistence are not yet accepted.

## Menu activation containment

An earlier native trial reported unresponsive mouse controls after launching
KYRIN or attempting a tab operation. A later startup-only observation in a
healthy standalone terminal did not reproduce the behavior. Its cause and
broader native coverage remain open.

Automatic activation of Ptyxis Main Menu is blocked, including a generic click
on that verified control. The semantic route requires a valid, already open
menu and an independently verified tab item. A closed menu fails with guidance.
The separately granted keyboard route does not use the menu. Deterministic
tests cover both the literal-control guard and the restricted keyboard route.

## Intended targeting and earlier evidence

Current native prerequisite (2026-10-29): original Ptyxis windows have unresponsive
mouse controls despite working typing. Esc and minimize/restore do not recover
them; an owner-created standalone instance has working controls. This is instance
isolation, not root-cause identification or a repair. Preserve existing jobs and
windows; native tab acceptance remains open until a healthy target is inspected.

Two owner-run traces now corroborate valid exported menu items in the healthy
instance, with exactly one independent tab-binding match and matching fresh
Main Menu ancestry. The original window remains stable. These read-only traces
invoke no Action. Their twenty-five-second wait is a maximum and they finish
early on a match. The subsequent native creation attempt fails; those read-only
observations do not prove the activation path is healthy. Original windows remain
unrepaired and preserved.

The owner-approved behavior is scoped to the installed, permitted Ptyxis
Terminal binding. It does not add generic browser tabs or arbitrary shortcuts.

With desktop-control permission enabled, exact `New tab`, `Create new tab` and
`Create a new tab` have two paths:

| Independent observation | Decision |
| --- | --- |
| A fresh focused Ptyxis window matches the observed Terminal app | Bind `NEW_APP_TAB` to that exact window observation. |
| Terminal is not independently focused | Show its numbered windows, retain the tab request, and ask which window should receive it. |
| A number answers that tab picker | Continue `NEW_APP_TAB` in that original displayed window. |
| Cancel, expired choice, changed membership/identity, missing permission | Do not create a tab. |

The picker continuation has a unique generation and a thirty-second limit.
`ShowAppWindowsForTab` snapshots original window objects, stable tokens and PIDs;
`ActivateAppWindowForTab` checks complete membership and consumes the selection
before activation. Python waits for the exact returned token and PID. The ensuing
ten-second execution observation retains the original action key, cancellation
context and input-broker ownership. Another window of the same app or PID cannot
replace it. Normal picker selection retains its existing behavior.

Execution keeps `NEW_APP_TAB` as an explicit semantic operation. The dedicated
`ptyxis-tab` helper now requires an already-open accessible Main Menu. GTK exports
its ordinary menu items with empty names, so this operation identifies the tab
Action through its independently advertised `keyshortcuts` and the owner's
unchanged `org.gnome.Ptyxis.Shortcuts` new-tab setting. The schema binding must
be enabled and unique, and exactly one valid MENU_ITEM inside Main Menu must
advertise it. Both the schema and full structural target are rechecked before
invocation. No keyboard input is sent.

The original app-open and desktop-control grants are checked separately; numbered
selection also requires window-control permission. The existing shared input owner
checks authorization/cancellation before each Action. The helper requires the new
`ptyxis-tab-v1` capability. Original token/PID, deadline and generation remain
bound through selection and execution. There is no OCR, coordinate, MRU, New
Terminal, guessed-label or positional fallback. Generic literal visible-control
verification still requires an observed full name; it does not acquire this
operation-specific semantic authority. Unknown or conflicting bindings fail closed.
The current menu-scope label is the independently observed English Main Menu;
other UI locales or unsupported shortcut encodings are not established compatible.

Read-only inspection of installed Ptyxis 50.1 found a visible `New Terminal`
button but no visible `New Tab` item in the closed menu. The installed UI resource
binds that menu item to `win.new-tab`. The [upstream 50.1 source](https://gitlab.gnome.org/chergert/ptyxis/-/blob/50.1/src/ptyxis-window.c)
also shows that the `New Terminal` action can open a window while Control is held.
That button is therefore unsuitable as a substitute for the requested operation.
The existing `ptyxis --tab` sole-window path remains for compositions without
targeted desktop control; its count restriction is preserved.

Voice selection is the continuation tested here. Clicking a preview focuses
the window using the existing picker; a fresh `New tab` can then address that
focused window. Clicking alone does not authorize a hidden tab continuation.

Deterministic tests cover focused binding, numbered continuation, duplicate
numbers, negation/quotation, STT mismatches, partials, standby cancellation,
expiry, changed window membership/tokens/PIDs, grants and existing control-engine
revalidation. Native tab creation remains owner acceptance work; an
`DISPATCHED_UNVERIFIED` result is not proof that the tab appeared.

## GTK4 accessibility correction after native failure

The first targeted native batch reaches `NEW_APP_TAB`, but Main Menu is rejected
as ambiguous. Read-only inspection and an owner-run focused diagnostic establish
two related layers: a no-action button wrapper and its sole same-named toggle
child with a click action, sharing exact window-relative bounds. They represent
one menu widget. The resolver collapses only that verified nested pair; siblings,
different bounds, actionable wrappers, uncertain roles/actions and independent
duplicate names remain rejected. The child retains all ancestor validity.

The owner diagnostic also reports ENABLED absent on all 49 nodes, with zero valid
controls. Installed GTK 4.22.4 maps its DISABLED state to absence of SENSITIVE;
it does not publish ENABLED in that state builder. See the
[GTK source](https://gitlab.gnome.org/GNOME/gtk/-/blob/4.22.4/gtk/a11y/gtkatspicontext.c)
and [AT-SPI state definitions](https://docs.gtk.org/atspi2/enum.StateType.html).
The compatibility profile requires matching window/application provider metadata,
GTK major version 4 and the same process. It requires sensitivity, visibility,
showing, valid ancestry and a unique supported semantic action. Missing ENABLED
never authorizes a coordinate fallback. Unknown providers retain the original
ENABLED requirement. Fresh helper checks reject disabling, stale state, changed
focus, identity or structural evidence before action invocation.

Two original regressions fail before and pass after; 23 new tests cover the
profile, structural ambiguity and the complete inert tab-adapter/inventory/control/
helper route. The full gate passes 3615 tests, strict mypy on 475 files, syntax
and Ruff. No model call, acoustic improvement or native tab creation is credited.
The already-loaded extension has both tab-picker methods; this Python correction
requires a normal Quit/source restart, with no extension reinstall or Setup.

The subsequent owner read-only probe corroborates the provider profile and one
valid Main Menu with a unique click action; five of six named controls are valid.
It observes Main Menu unchecked and no New Tab, so it samples the closed menu.
This supports the locator correction, not open-menu or tab execution acceptance.
No further code change is made from that snapshot; the next step is the bounded
native focused/numbered retest after normal Quit/source restart.


## Follow-up: unnamed menu items and semantic identity

The subsequent native failures reach the tab operation and open Main Menu but
cannot find a literal New Tab name. Open-menu inspection confirms empty names and
labelled-by relations on ordinary MENU_ITEM objects, while their click Actions
and keyshortcuts exist. The owner also demonstrates that open state uses
EXPANDED/PRESSED rather than CHECKED alone. The state read is corrected and the
semantic operation above replaces the literal tab-item lookup. No general
visible-label guard is relaxed.

Read-only native metadata and the saved schema agree on the unique tab binding.
Twenty-eight dedicated semantic cases, two step-diagnostic cases and the complete
inert broker/adapter/client/helper route pass. Two older tests with a fabricated
named New Tab item are replaced with this observed shape. The final full gate is
3643 tests, strict mypy on 477 files, syntax and Ruff. The native creation retest
remains pending; the last read-only locator watch did not verify an executable tab
and is not credited as success.
## Fresh ancestry after cache refresh

One additional regression reproduces a queue retaining an empty menu label read
before the node refresh, while subsequent matching sees its actual Main Menu name.
Traversal now reads role/name after validity refresh and updates that node's
ancestry entry. All ancestor validity and target revalidation still apply. The
regression fails before and passes after; 252 focused checks and the complete
syntax/Ruff/strict mypy gate (477 files) plus 3644 tests pass in 89.30 seconds.
This correction is not proven to cause or resolve the current native failure.
