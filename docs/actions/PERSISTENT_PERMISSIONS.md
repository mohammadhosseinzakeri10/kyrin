# Persistent command-execution permissions

English reference. The Persian original,
PERSISTENT_PERMISSIONS_FA.md (source repository only), is preserved
unchanged. See also [DR-0003](../decisions/DR-0003-persistent-permissions-and-remembered-input-consent.md).

- **Status:** current contract, effective 2026-10-25 by explicit owner
  decision. Identifiers were checked in `src/kyrin/app/permissions.py`,
  `src/kyrin/app/settings_store.py` (`SCHEMA_VERSION = 17`),
  `src/kyrin/actions/authorized.py` and
  `src/kyrin/desktop/platforms/gnome_window_control.py`. Live GNOME behavior
  across all applications is not claimed.

## Decision

This contract replaces the earlier requirement of a separate confirmation for
every operation (F02/F11) and the real two-step power flow. Confirming a name
recognition or choosing a target remains disambiguation; trusting a capability
never produces target evidence.

In the "Desktop operations" settings the user enables command execution and
chooses individual permissions or "trust all current and future supported
KYRIN capabilities". Choices are stored in settings schema 17.

- Global trust is off by default. Schema versions 1-16 keep their individual
  permissions and do not gain global trust. Existing permissions are now
  persistent consent; no re-grant is needed. Corrupt settings grant nothing and
  the file is not rewritten.
- Global trust covers all supported command-execution capabilities, desktop
  discoverable applications and capabilities introduced later; it does not
  guarantee a tool, model, unique target or OS permission. Individual grants
  are kept and apply again when global trust is turned off.
- "Revoke all permissions" clears the selections; "Save" applies it. Turning
  off command execution stops all commands but keeps the individual choices.
  History, model, screen-access and explicit listening settings are not changed
  automatically.

## Enforcement

`PermissionPolicy` (`src/kyrin/app/permissions.py`) is the shared decision
point. `ActionGate` checks it before issuing a request and `PermissionExecutor`
checks it again after taking the input turn. Numbered window close needs the
control permission and the close permission for the same resolved application;
the close executor also matches the real target id against permission and
command. A disabled master switch or missing permission never executes. The
diagnostic no-execute mode may still display a hypothetical request with the old
policy; no executor is attached and it is not consent.

Saving settings while running passes through the earlier stop-and-wait path.
Request-generation cancellation, operation budget and input ownership are kept;
then a new session with a fresh permission snapshot is built. Queued requests
and helpers cannot continue with the old snapshot. Recovery tokens of a revoked
input permission are deleted; this does not revoke access other applications
may hold in OS settings. An action sent before the cancellation boundary cannot
be undone.

## Consent and request validity

In the main path, window close and control no longer call `ControlConfirmer`.
Observation, re-resolution of the target and the single-use `ControlApproval`
remain; that binding is now the validity of the *same request*, with consent
coming from settings. The original ten-second budget is not extended. Role,
structure and accessibility state, image geometry, window id, PID, generation,
focus, selection snapshot and cancellation are still checked. Send, delete and
payment through generic clicks have no implemented capability; global trust
creates no missing tool or outcome contract. No generic standalone typing was
added; existing typing inside Telegram navigation follows the same permission,
identity and helper checks.

For GNOME, `PrepareWindowClose` observes, and `CloseAuthorizedWindow` consumes
the generation once and, in the same Shell loop turn, rechecks the target and
sends an ordinary close. The extension build required is
`active-app@kyrin.local-2026-10-25-persistent-permissions`. Protocol version 1
is kept and the new capability is negotiated explicitly; an older backend is
rejected with no dialog fallback. Older Qt/native confirmation paths remain
only for compatibility and isolated tests. The extension endpoint stores no
KYRIN permissions; consent lives in the application and atomic target
validation in the Shell. Same-user D-Bus is not a security boundary against a
malicious process of the same account.

A specific system-power command, once permitted, sends the ordinary GNOME
request directly. Independent initial command detection, id, deadline,
cancellation and the permission check before sending remain; a late button or
speech answer cannot run another request. The earlier harmless preview still
exercises the two-step display against a neutral backend and cannot execute.

## Adding a future capability

1. Add a `Capability` with a stable id, Persian/English labels and command
   kinds to `CAPABILITIES`. Every current `CommandKind` must map to a
   capability (the registry test covers this).
2. It appears in settings automatically and is stored in `capability_grants`.
   Do not add the new id to `LEGACY_CAPABILITIES` (only for existing partial
   editors). A future general permission in partial mode covers all valid
   targets of that capability; a capability with a special scope defines it in
   this policy, not in a separate dialog.
3. Wire the really-ready capability into `supported_kinds` and the executor
   chain under `PermissionExecutor`. Global trust covers it without changing the
   previous setting; in partial mode the new permission defaults to off. A
   missing tool or identity contract is not compensated by global trust.
4. The executor must check target evidence, validity, cancellation and the real
   result. If a permission is needed outside the gate, use the same policy
   instance and `allows()`. Models, control names, speech text and OCR cannot
   grant permission.

## Limits of external confirmations

Stored KYRIN permissions only remove KYRIN's own repeated confirmation.
RemoteDesktop/ScreenCast may still require OS consent; the input-setup buttons
in settings remain for that step before commands. The OS may reject or revoke a
recovery token and KYRIN does not bypass that. Save-file prompts, target
application warnings, inhibitors and native power confirmations get no
automatic reply. Only ordinary close and ordinary power requests are sent: no
kill, force or automatic answer to save/discard.

For the live shared input session, see
[Shared input session](SHARED_INPUT_SESSION.md). Install and test results are in
the implementation report (`PERSISTENT_PERMISSIONS_2026-10-25_FA.md`, source repository only),
which separates unit, headless Qt and real-session tests from owner tests.
