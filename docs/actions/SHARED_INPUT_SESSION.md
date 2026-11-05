# Shared live desktop-input session (L03)

This reference defines the public input-session contract. See
[DR-0003](../decisions/DR-0003-persistent-permissions-and-remembered-input-consent.md)
for the decision and its limits.

- **Status:** current contract. Identifiers checked in
  `src/kyrin/actions/platforms/input_session.py` (`BUILD =
  "desktop-input-owner-2026-10-25-l03"`), `input_session_owner.py`
  (`persist_mode` 2, capability `shared-input-session-v1`) and
  `src/kyrin/app/permission_token.py` (`permission_token_path`). Live portal
  acceptance after a real restart/reboot is not claimed by this document.

Four things are distinct: KYRIN's stored permission, the operating-system
consent, the restore token, and the live session. `PermissionPolicy` is the
authority for capability permission; OS pointer/keyboard access does not stand
in for the scroll, interface-control or Telegram permission.

## Durable requirement for future changes

After successful setup and a stored valid token, the user must not press the
scroll, click or Telegram setup buttons on every KYRIN run. Implementation may
change; this behavior must be kept. Requiring manual setup on each run is the
old, obsolete behavior.

- A normal exit closes only the live session; it does not delete the stored
  permission or token. This holds even when a setup worker's result is still in
  the UI event queue and arrives after the exit request. Explicit permission
  revocation plus save still removes the shared session and token, even if the
  worker result arrives later. A token already consumed with no valid
  replacement must never be reused; preserving access does not mean restoring a
  consumed token.
- Turning command execution off does not revoke the stored permission. Turning
  it on and saving, with a valid token, makes one non-blocking restore attempt.
  Saving other settings, the status timer or later commands must not repeat a
  failed attempt or a manual disconnect. A manual disconnect holds for the
  current run; turning command execution back on or starting the app anew may
  restore with a valid token.
- The requirement relies on real OS persistence. Refusal or revocation by the
  OS, a missing token and a failure to store it must remain distinguishable.
  Claiming access persists on every system, or bypassing OS consent, is not
  allowed.

## Ownership and setup

`InputSessionService` is owned by the application lifetime. A private process,
`input_session_owner.py`, runs under the system Python and holds the Gio
connection and one RemoteDesktop session. Only an inherited socketpair connects
the app and owner; no listening endpoint or reconnect identifier exists.
`DesktopInputBroker` still owns the FIFO for whole operations and nested handoff;
the transfer lock only prevents message interleaving and is not another command
queue.

Initial setup and manual repair use the settings buttons and require the same
capability to be selected. Scroll and pointer click need device bit 2; the
existing Telegram flow needs keyboard and pointer (bits 1 and 2). Each setup
button requests the union of devices needed by all selected input capabilities
in one session, replacing the previous session if needed. A session with enough
devices is not started again.

The optional `terminal_tab_keyboard` capability (fixed Terminal tab creation)
needs keyboard bit 1, its own permission and the desktop-control selection. It
is unselected by default in partial settings; Telegram keyboard permission alone
does not authorize it. After the new selection is saved, the existing desktop
click setup button prepares the union; adding the keyboard requirement may
require one new explicit OS consent. This is a one-time upgrade, not a return to
per-run setup. Earlier pointer-only selections still request only bit 2. The
tab-creation command never starts setup or a retry; a missing keyboard session
yields a clear error. Normal exit and startup restore keep and consume the same
rotated token. Implementation, limits and live acceptance are described in the
[terminal-tab targeting guide](TERMINAL_TAB_TARGETING.md).

### Startup restore

At application start, one automatic non-blocking restore is attempted when
command execution is enabled, at least one input capability has a stored
permission, and a readable, privately accessible shared token exists. The older
shared token works unchanged. A missing token, absent settings, revoked
permission or disabled command execution creates no initial portal request. The
selection and conditions are re-checked in the worker thread. The window and
microphone do not wait for the connection; setup state shows in settings, and
input commands are unavailable until the session is ready. Enabling command
execution and saving after startup runs the same single check.

The restore consumes and replaces the single-use token through the existing
path. If the OS rejects the token it may show a consent dialog. If no token is
issued, the current session works but the next run cannot restore
automatically. After an error or manual disconnect, the status timer and later
commands do not repeat restore; manual repair or the next run with a valid token
is required. A manual disconnect or exit before the worker starts also cancels
the scheduled startup attempt.

On the normal command path, a missing session or insufficient devices ends in
`CONTROL_SETUP_REQUIRED` and a specific executor error such as
`scroll_control_setup_required`. That path performs no CreateSession,
SelectDevices, Start or restore; even a valid token may open an OS dialog.

Settings state comes from the owner's real response: not prepared, preparing,
needs interaction, connected, busy, disconnected or unsupported. A missing token
does not invalidate a live authorized session. Token issuance and restart
recoverability are shown separately. The owner process id and Start count help
detect reuse; the counter restarts with a new owner process and is not
permission.

## Identity and token

Setup and sending use the same connection and the same D-Bus sender. Before the
first portal call the owner tries to register its connection in the Registry as
`local.kyrin.KYRIN`, which needs a matching desktop entry. If the Registry is
unsupported or registration is refused, identity is left to the portal and
`app_id=null` is reported; identity is never guessed. A portal restart
invalidates the session and the next setup builds a new owner.

With RemoteDesktop version 2, `persist_mode=2` and an existing token are sent
only during setup or startup restore; with version 1 persistence options are not
sent and the session may work without restore. `session_handle_token` is
random. The shared token is stored at `permission_token_path("desktop-input")`;
older separate tokens do not prove a live session and are not migrated
automatically.

The single-use token is taken from its location by atomic rename before
SelectDevices, so a failure or crash cannot reuse it. The replacement token is
written to a temporary file and atomically replaced. A missing replacement or a
failed store does not by itself revoke consent for the current session.
Revoking the capability closes the owner and deletes the shared token; deleting
KYRIN's token does not delete other applications' OS permissions.

## Target, cancellation and failure

A valid session only permits using the input tool. PID, application, window id,
focus, geometry, accessibility evidence and each request's deadline are
rechecked in the existing paths; for scroll, the window id is also checked
between pulses. The shared session validates no coordinates or earlier target.

Each message carries a random id and an absolute operation deadline. Before any
Notify call or accessibility change, the owner sends a checkpoint for that
request; the app checks budget, generation and the capability permission. An ACK
is only the dispatch boundary of that event; the next event needs a fresh
checkpoint. Disconnect/cancel are ordered with ACK under a state lock. An event
already approved and in flight may have arrived: cancellation does not recall
it, and rollback or atomic focus-check-plus-dispatch across two processes is not
claimed.

The budget includes broker and transport waiting. On cancellation, expiry or an
unknown transport break the owner is terminated and, if needed, killed and
reaped. Queue and operation ownership are held until cleanup ends; unknown
input is never repeated automatically. Late replies, mismatched ids,
incompatible version/build and invalid bodies create no authority for the next
request. A request waiting before a disconnect cannot start the owner after it.
Closing the owner and deleting the token complete before a replacement owner
starts. A `Closed` signal from an old session cannot disconnect its
replacement.

Microphone shutdown in standby does not close the input session. If stopping
the speech app cancels a running input operation, session closure is the
conservative result of that cancellation. A real exit disconnects the session;
closing the window with X only minimizes in current behavior and is not an
exit. Restarting the app restores the stored session under the conditions
above. The "Disconnect live input session" button closes the connection;
revoking the capability and saving also deletes KYRIN's recovery token.

A successful scroll is `dispatched_unverified` at the input boundary; it makes
no claim of verified visual movement. Telegram and interface-control paths with
real postconditions keep their existing result checks.

## Version contract and tests

Private protocol version 1, build `desktop-input-owner-2026-10-25-l03`; the
final reply carries `shared-input-session-v1`. Packaged helpers of the same
install are imported into the owner; a probe and helper process per action are no
longer created. A standalone `--capabilities` probe remains for version
detection. GNOME is still checked with GetCapabilities before an action. No new
extension is needed for L03.

Unit, headless Qt, fake-portal-on-private-D-Bus and real GNOME tests must be
reported separately. Ten operations over two fake identities with one Start do
not prove real input into two applications.

### Guard tests (preserve when changing startup/exit, owner, settings, token or packaging)

- `tests/actions/test_input_session.py`: one setup and two restores with fresh
  services, with global trust and with independent scroll/click permission;
  token replacement, use of one session, rejection of an unpermitted capability.
- `tests/app/test_qt_window.py`: startup restore without a click, token kept at
  exit with a queued setup result, deletion of a revoked token, restore on
  enabling command execution; a missing token or rejected restore must not
  create duplicate requests via unrelated saves.
- `tests/app/test_qt_input_access.py`, `tests/app/test_permission_token.py` and
  `tests/actions/test_input_session_bus.py`: non-blocking worker, cancellation,
  private file, consume/replace, and session ownership on a private D-Bus.

Run the full check from the repository root:

```bash
.venv/bin/python scripts/development/check.py
```

The checker builds a temporary home and XDG paths and removes the personal
desktop-session connection; tests need no clicks or scrolls in personal
applications, but the environment must allow local sockets and a private D-Bus.

### Troubleshooting order

1. The executed build must include startup restore; compare the launcher path
   and the imported package location with the checkout (a source edit does not
   update an already-running process).
2. Command execution and the capability permission must be stored. The old
   scroll- or click-specific token file is not enough; current restore uses the
   shared `desktop-input.token` under `kyrin/permissions` in the XDG data path.
   It must be readable and private; check only existence, size and mode, and put
   the token content in no report, UI or Git.
3. After successful setup, check "access stored". A temporary state means the
   current session is ready but no recoverable token was issued or stored. File
   existence alone does not prove OS acceptance.
4. Exit with the real exit action, relaunch and wait for connection before
   pressing Setup; repeat twice and after a reboot. Scroll and click must work
   without setup. X only minimizes. The Start count restarts per owner process.
5. If the state stays needs-interaction, disconnected or temporary, check the
   rejection/absence of the token, folder write access, data path and portal
   identity. After fixing, set up manually once and re-check two fresh runs. Do
   not restore a consumed token from backup. Revocation plus save must still
   prevent restore on the next run.

Automated tests do not replace live acceptance of portal consent after a
restart or reboot.

Official sources:
[RemoteDesktop](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html),
[Session lifetime](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Session.html),
[Registry](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.host.portal.Registry.html).
Initial consent and mandatory OS confirmation are not bypassed; the absence of a
dialog on every backend, or acceptance of the token after any restart, is not
guaranteed.
