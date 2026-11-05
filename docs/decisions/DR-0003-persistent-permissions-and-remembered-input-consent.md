# DR-0003: Persistent permissions and remembered desktop-input consent

- **Status:** Accepted. Supersedes earlier per-action confirmation and per-run setup.
- **Area:** permissions, desktop input.

## Problem

Saving an action permission did not remove repeated confirmations: individual
executors still asked their own confirmation. Desktop input through the
RemoteDesktop portal needed an explicit setup on every run, and a late setup
result could be treated like a revocation and delete the saved consent.

## Decision

1. **`PermissionPolicy` is the shared authority** for capabilities
   ([`permissions.py`](../../src/kyrin/app/permissions.py)). A saved partial
   permission (or the global trust setting, which does not replace the
   action-execution switch) is honoured by executors; they do not add a second
   confirmation for an already-permitted capability. Send, delete and payment
   remain separate, dedicated operations.
2. **Four distinct states:** saved KYRIN permission, operating-system consent,
   the restore token, and the live input session. None substitutes for another.
3. **Remembered input:** after successful setup and durable portal consent,
   selected and enabled capabilities are restored asynchronously at startup.
   Enabling action execution later in the same run also attempts one restore.
4. **Exit is not revocation.** Normal exit and microphone shutdown close the
   live session and keep consent; only explicit revocation closes input and
   removes the token (`disconnect(forget=...)` in
   [`input_session.py`](../../src/kyrin/actions/platforms/input_session.py)).
5. **Tokens are single-use and rotated.** Commands and status polling never
   start or retry setup; a rejected restore does not loop; missing OS
   persistence stays visible and recoverable.

## Superseded approaches

- Per-action Approve button or spoken confirmation for already-permitted actions.
- Mandatory setup on every run.

## Alternatives considered

- *Keep per-run setup:* not adopted; the accepted requirement is one-time
  preparation that is remembered.
- *Treat exit as revocation:* rejected after a reproduced defect deleted tokens
  when a queued result arrived during exit.

## Consequences and limits

- The maintained behavior contract is documented with regression checks in the
  shared input session reference. Automatic tests expose known failures; they do
  not prove that every portal backend accepts persisted tokens.
- Saved grants are not a boundary against a malicious process of the same user.

## References

[Shared input session](../actions/SHARED_INPUT_SESSION.md) ·
[Persistent permissions](../actions/PERSISTENT_PERMISSIONS.md) ·
[Control policy](../actions/CONTROL_POLICY.md)
