# Action gate

English reference for the command-execution gate. The Persian original,
ACTION_GATE_FA.md (source repository only), is kept unchanged as historical
context. The current execution contract is
[Persistent permissions](PERSISTENT_PERMISSIONS.md).

- **Status:** current direction; behavior below was checked against
  `src/kyrin/actions/gate.py`, not live-tested.

## Role

The command-understanding layer turns interim text into
`CommandCandidateUpdate` and final text into `CommandResolution`. `ActionGate`
sits between those decisions and an executor:

```text
TranscriptUpdate -> CommandCoordinator -> CommandCandidateUpdate / CommandResolution
                                                    |
                                                ActionGate
                                                    |
                                      ActionRequest or ActionNotice
                                                    |
                                          bounded platform executor
                                                    |
                          ActionResult -> ActionFeedback / VerifiedContext
```

`ActionGate` opens no application and depends on no operating system, STT
engine or microphone. An `ActionRequest` is structured data only; it contains
no terminal or shell string.

## Rules

1. **Interim candidates are display-only.** `CommandCandidateUpdate` never
   creates an `ActionRequest`; interim text may still be corrected or negated.
2. **Only final results are evaluated, once.** The pair
   `(stream_id, segment_id)` identifies a decision for the life of one gate. A
   repeated or stale event does not create a second request. Each live
   `CommandCoordinator` needs its own `ActionGate`.
3. **Deny by default.** `ActionPolicy` accepts only explicitly allowed
   application ids for `OPEN_APP` and `OPEN_CHAT`. An application name is an
   internal id mapped by the executor; speech text never becomes an OS command.
4. **Confirmation-required work does not run automatically.** The gate first
   emits `ActionNotice(CONFIRMATION_REQUIRED)`; only `confirm()` from a
   trustworthy confirmation flow can approve it. Under the persistent-permission
   contract this path is no longer required for already-permitted actions.
5. **Open requests are capped.** `max_pending` defaults to 32 and bounds
   requests awaiting a result or confirmation. A full gate returns
   `ActionNotice(BUSY)`; work is not queued without bound or retried silently.

## Results and conversation context

Issuing a request does not mean the action happened. The executor must return
an `ActionResult`; the gate accepts a result only for a request it issued, and
rejects unknown or duplicate results.

`ActionResult.outcome` distinguishes `CONFIRMED`, `LAUNCH_ACCEPTED`,
`DISPATCHED_UNVERIFIED`, `UNKNOWN` and `FAILED`. `VerifiedContext.active_app`
changes to an application name only for `CONFIRMED` with an explicitly
reported observed active application. An accepted or unknown launch clears the
active-app context (the previous app is no longer certain); a definite failure
keeps the earlier context.

`ActionFeedback` carries the precise state to the response layer. Text is built
by `ResponsePresenter`; `error_code` is diagnostic data and is not shown raw.
The final command's language travels with the request, notice, pending
confirmation and feedback, so a late result keeps its own command language
(see [Response language](../responses/RESPONSE_LANGUAGE.md)).

## Example and limit

If STT first hears an interim "open Telegram", only a suggestion appears. The
final result of the same command creates an `ActionRequest` when `telegram` is
allowed. Only `CONFIRMED` with an observed active app updates
`VerifiedContext`. A following "open Ali's chat" needs a fresh observation of
the active app; a stored earlier result is not sufficient. A final "do not
open" creates no request.

## Multi-step commands

For each step of a `CommandPlanResolution`, `ActionKey` has its own
`step_index` in addition to stream and segment ids. `ActionPlanRunner` feeds
steps to the gate and executor in order and stops after a rejection or
failure; earlier steps are not rolled back. A chat step additionally requires a
fresh observation that the same application is active. See
[Multi-step commands](../commands/MULTI_STEP_COMMANDS.md).

## Live speech wiring

The `commands` mode of `scripts/audio/check_live_speech.py` forwards
`CommandCoordinator` events to the gate. By default it only prints the
permitted request or rejection reason. Real execution needs
`--execute-actions` and an explicit `--launch-app` mapping. No synthetic
`ActionResult` is recorded in the diagnostic mode, so `VerifiedContext` stays
empty. See [Live open-app integration](LIVE_OPEN_APP_INTEGRATION.md).

## Tests

`tests/actions/test_gate.py` covers the flow, repeat control, interim
correction, the allow list, the confirmation path, capacity and result types
without hardware. `tests/responses/test_presenter.py` covers presentation and
hidden internal error codes. Live desktop behavior is not covered here.
