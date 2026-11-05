# Extension and helper protocol

(English migration of a previously Persian-only note; the original is preserved
in the private migration pre-images and in Git history. Identifiers checked in
`src/kyrin/backend_protocol.py` and `src/kyrin/app/qt/screen_access.py`.)

## Handshake contract (F20)

All three GNOME extensions expose the read-only method `GetCapabilities`. The
reply is a JSON string with `protocol_version` equal to 1 (`PROTOCOL_VERSION`),
a fixed `build_id` of the loaded code, and a `capabilities` list. The version
installed on disk, an install success message and introspection do not prove the
loaded version. The build id identifies a contract release and is not a file
hash; an incompatible contract change must increase the version. An older
extension without the handshake is rejected.

The consumer checks the version and required capability before calling. Window
control also requires the postcondition-reading capability before changing
anything; close preparation additionally requires the verified-close capability.
Screen permission, screen capture and region validation are separate
capabilities. A screen probe takes no permission and produces no screenshot. This
contract does not replace user permission, window identity, observation freshness
or checks before input.

In a GNOME session adapters are not dropped because a service is temporarily
absent. Each probe makes at most three attempts with a 500 ms timeout and 50 ms
delay; only an absent or late service is retried. A version mismatch, invalid
reply, missing handshake, access denial or incomplete capability set is not
retried. The next request probes anew; a successful result is not cached forever.
The act of activating, closing, clicking or typing is never repeated by this
mechanism. Shared operation deadline and cancellation still govern budgeted
paths.

`BackendStatus` holds the reason, version, build id and capabilities of the
responder. Reasons include `protocol_mismatch`, `handshake_missing`,
`malformed_handshake`, `missing_capabilities:...`, `service_unavailable`,
`service_timeout` and specific transport or access errors. A helper execution
error at the action boundary is kept as `backend:...`. The screen UI also shows
the probe reason. In `ScreenAccess`, `transport_available` only means local
connection ownership while `available` requires a compatible reply; a stored
token does not prove the extension is ready.

Three-member or eleven-member legacy screen replies are rejected by default.
Only constructing `ScreenAccess(allow_legacy_capture=True)` enables the
compatibility path, which covers only a missing handshake and the legacy formats;
it does not allow a declared version mismatch or invalid twelve-member metadata.
The normal application composition does not enable it. The compatibility path
keeps the earlier geometry and permission limits and claims no current-protocol
readiness.

## Shared input owner (L03)

Normal input uses the packaged helpers of the same install inside one shared
owner process; a separate probe and input process per action are not created.
Private messages carry version 1, build `desktop-input-owner-2026-10-25-l03`, a
request id and a deadline. The final reply must carry the
`shared-input-session-v1` capability and a valid body; an incompatible or late
reply disconnects the owner and the action is not resent. Helpers still check the
really loaded extension before acting.

The standalone `--capabilities` probe exits before importing GI and changes
neither portal nor token. The contracts `desktop_control-v1`,
`desktop_scroll-v1` and `telegram_portal-v1` are kept; input probes carry the
build suffix `2026-10-25-l03` and the shared capability. Owner status includes
the D-Bus sender, process id, Start count, portal version and the registered
app_id or null; none of this is permission. Full session contract:
[Shared input session](../actions/SHARED_INPUT_SESSION.md).

## Tests

Deterministic tests cover an old backend, an incomplete capability set, late
loading, recovery, a legacy reply, real GJS methods without `enable`, and running
the real helper probe. Live GNOME is not needed. Existing screen tests use the PNG
processor and a separate temporary D-Bus and may be limited in a restricted
sandbox. Installation/loading of the extension in the owner's session and a live
test were not done in this card.

Transport references: the official
[D-Bus guide for GJS](https://gjs.guide/guides/gio/dbus.html) and the official
[Qt timer documentation](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QTimer.html);
the schema and version above are KYRIN's internal contract.

## Persistent close permission (2026-10-25)

The earlier consent contract was replaced by the user's stored selection in
`PermissionPolicy`. Before `PrepareWindowClose`, the capabilities
`CloseAuthorizedWindow` and `GetAppWindowState` are required. The new method
takes a generation string, consumes the prepared connection once and returns
`requested` only after rechecking the deadline, focus, snapshot,
application/PID/token and close capability. It shows no dialog; consent is
applied in KYRIN. Older confirmation methods remain for compatibility and are
not used in the main path.

The current build is `active-app@kyrin.local-2026-10-25-persistent-permissions`
with protocol version 1. The previous extension stops with
`missing_capabilities:CloseAuthorizedWindow`. Installing the package does not
prove the code is loaded; a `GetCapabilities` check is required. A real separate
GNOME/Wayland session with Python/busctl and a fake window confirmed dialog-free
closing; the owner's session was not replaced. See the
[persistent permissions contract](../actions/PERSISTENT_PERMISSIONS.md) and the
installation and test report (`PERSISTENT_PERMISSIONS_2026-10-25_FA.md`, source repository only).
