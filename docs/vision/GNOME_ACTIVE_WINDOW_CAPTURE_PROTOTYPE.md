# GNOME active-window capture: session-access prototype

## Why this exists

The ScreenCast Portal safely lets a user choose a window, but its stream ID
does not identify the installed application. GNOME's focused-window API can
return the image and application ID from the same window object. This is an
optional Ubuntu/GNOME adapter; core OCR and vision contracts do not depend on
GNOME or Qt.

## Confirmed read-only foundation

On 2026-10-09, the owner approved two live, in-memory captures. The first test
window yielded `window:8`, a temporary ID for an unregistered window. The
extension now rejects window-backed IDs. The second test window used KYRIN's
registered desktop identity and returned `local.kyrin.KYRIN.desktop`, its
process ID, and OCR words including `Open` and `Telegram`. These two results
verify the earlier one-image prototype on this GNOME 50.1 desktop. They do not
verify other apps, persistent access, or any action based on OCR text.

## Current session-access design

The Qt control application owns `org.kyrin.Desktop` on the user's session
D-Bus. `ScreenAccess` sends all image and permission requests on that same
connection. The GNOME extension checks that a `RequestSession` sender is the
current unique owner of the name and asks the user once in a GNOME Shell
dialog. A second owner check follows the decision. A successful grant is bound
to that unique connection name in memory. Another process cannot use the
grant by sending its own request. The `Screen Access` page turns the grant on
or off; it is off at each application start and is never stored in settings.

The extension revokes its grant when the app's bus name changes owner, on an
explicit `RevokeSession`, or when the extension is disabled. Capture requests
still reject an unregistered active window, missing PID, focus change during
capture, failed screenshot, image over 16 MiB, concurrent capture, and the
eight-second capture timeout. Image bytes remain in memory. No capture runs
periodically. The Qt adapter is asynchronous so it does not block the UI.

The old separate-process helper and its terminal diagnostic were removed:
their D-Bus sender could never match the control app's unique connection.
`ActiveWindowTextReader` remains a platform-neutral composition for future
adapters. The session adapter is not connected to OCR-triggered actions.

## Trust and current limits

Owning a well-known D-Bus name proves which **connection** sent a request; it
does not prove that the process is a trustworthy KYRIN binary. Another process
in the same user session could claim the name before KYRIN starts and ask the
user to approve its prompt. The Qt app refuses screen access if the name is
already owned; the Shell dialog is the user's explicit gate. This prototype
is not a security boundary against a malicious process running as the same
user, which could also alter user-installed extension files. A stronger
isolation requirement would need a sandbox and a trusted portal design.

The session path has passed focused Python tests and a GJS permission harness,
including foreign-caller denial, revocation, lost bus ownership, and a late
reply after revocation. A live Qt request initially returned `false` before any GNOME
prompt appeared. D-Bus monitoring showed that the request sender matched the
owner of `org.kyrin.Desktop`. A focused GJS check then showed that
`GLib.Variant.unpack()` left the owner's string wrapped in a child variant;
the extension now uses `deepUnpack()` for owner replies and owner-change
signals. An unauthorized direct D-Bus capture request returned no image.
After the owner restarted the desktop session, the corrected extension
accepted the Qt app's request and displayed the GNOME session-consent dialog.
In a separate approved one-image test, `ScreenAccess` received a 20,072-byte
PNG in memory with the registered ID `local.kyrin.KYRIN.desktop` and the test
window's PID. After `RevokeSession`, another capture request returned no image.
The Qt adapter, live GNOME grant, one-image path, and explicit revocation are
therefore validated on this desktop. Later read-only Qt OCR runs captured the
actual Telegram Desktop window; its Settings view yielded several expected
English labels. This does not validate contact matching, OCR-based decisions,
other applications, or stronger protection against a malicious process in the
same user account.
No image should be used to authorize a click or keystroke until the active
target is checked again at action time.
