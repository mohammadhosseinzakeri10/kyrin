# App-scoped normal close of all windows

Owner-requested addition on 2026-10-29. This does not start roadmap stages 13+.

`Close all Calculator` and `Close all windows of Calculator` admit a
`close_all_app_windows` request only for an exact registered app with the existing
app-scoped `close_window` grant. This is an exact rules path, not model inference
or phonetic recovery. Bare/unknown targets, negation, reported content and partial
transcripts cannot authorize it. An ambiguous literal app named `All X` does not
silently become bulk close of `X`; use the explicit `windows of` form for bulk.
The existing single-window command remains distinct.

The optional platform group controller prepares a complete immutable set of
one to 32 windows with app ID, PID, stable window IDs, generation and the original
ten-second deadline. Larger/empty/unclosable sets are rejected without closing a
subset. By default the Shell modal displays the app/count and requires one-time
approval. The owner-requested `close_all_without_confirmation` option now uses the
existing Desktop actions registry and saved `capability_grants`; existing global
future-capability trust also covers it. It removes only this per-request modal.
App-scoped `close_window` permission and enabled actions remain required. The new
option is absent from granular defaults and is never enabled by the assistant.
The settings schema and desktop input setup/consent are unchanged.

The Shell rechecks full membership, object/ID/PID identity, focus, generation,
deadline and either native approval or client-authorized saved consent before
issuing normal close in the same event-loop turn. Changed sets require a new
request and matching consent. Each commit attempt burns
the binding. Cancellation/timeout of the confirmation caller dismisses its dialog;
the action checks its generation/cancellation budget before commit. Already issued
normal close requests cannot be undone. New windows and native Save dialogs are
not followed. There is no force quit, process termination, automatic save/discard
answer or close retry. The adapter verifies every original stable ID is absent
before reporting confirmed; partial/uncertain results remain unknown. An app may
retain a background/tray process according to its own normal close behavior.

The additive protocol requires `PrepareAppWindowsClose`, `ConfirmAppWindowsClose`
and `CloseConfirmedAppWindows`, plus existing `GetAppWindowState`. An old loaded
extension fails closed with missing capabilities; there is no legacy close loop.
Direct saved-consent commit additionally requires `CloseAuthorizedAppWindows` and
build `active-app@kyrin.local-2026-10-29-app-window-group-consent`. It uses the same
atomic commit routine with approval supplied by the existing permission policy.
Old backends reject direct mode without opening an unexpected fallback dialog or
closing one window instead. The earlier three-method build still supports manual
confirmation mode.

Update the GNOME extension from the same source checkout and verify the
loaded capabilities before trying the command with disposable windows.
An extension update does not require repeating input setup.

The development checks used inert GJS window and modal objects and preserved
the existing rules replay. A bounded native manual-confirmation close was
observed during development. Native acceptance of saved direct mode remains
open. See [validation](../VALIDATION.md) for the scope of current checks.
