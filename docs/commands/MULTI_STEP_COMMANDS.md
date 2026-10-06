# Ordered commands in the English V1 diagnostic

## Scope

An English final transcript can describe two explicit steps, such as
`Open Telegram and open Alice chat` or `Open Telegram and open WhatsApp`.
`DemoCommandInterpreter` resolves exact app names to stable internal app IDs
and returns one `CommandPlanResolution` with ordered `CommandIntent` steps.
`Alice` is a spoken chat target, not a verified contact. The plan data model is
bounded to two or three steps; the current parser recognizes only two-step
English forms. No new language model or dependency was added.

The first clause must name an application. The second clause may open another
application or request a chat in the first application. An optional `KYRIN`
prefix is accepted. Approximate or ambiguous app names are **not** accepted
inside a plan yet, because the current clarification state cannot retain the
remaining steps. Unknown, incomplete, negated, or otherwise unsupported
compound forms do not authorize any fragment of the utterance.

## Execution boundary

The data flow is:

```text
final transcript -> CommandPlanResolution -> ActionPlanRunner
                 -> ActionGate -> ActionExecutor -> ActionFeedback / ActionNotice
```

Partial transcripts may display a replaceable single-step candidate, but
never authorize an action. If the final text becomes a plan, the old candidate
is retracted. Each final plan step has a distinct `(stream_id, segment_id,
step_index)` action key. The gate checks policy separately for each step and
rejects a duplicate plan. The runner executes one step at a time and stops
after a denied, unsupported, failed, unknown, or confirmation-required step.
Earlier completed steps are not rolled back.

For the current Linux launcher, only `OPEN_APP` is supported. With a policy
that advertises that capability, `Open Telegram and open Alice chat` submits
the Telegram launch first; the second step returns an explicit unsupported-chat
notice. A successful `gio launch` reports `LAUNCH_ACCEPTED`, not proof that a
window opened. If a future executor supports chat navigation, the runner will
require a fresh foreground-app observation immediately before a supported
`OPEN_CHAT` step. Without an observer, or if focus differs, it stops. This
avoids navigating the wrong application even if an earlier launch succeeded.

The live microphone diagnostic remains a **dry run by default**. An explicit
`--execute-actions` flag plus `--launch-app` bindings now connect final plan
steps to the Ubuntu launcher. Only bound `OPEN_APP` steps can execute; chat
steps still return an unsupported notice. `ActionPlanRunner` is tested using a
fake executor, and the diagnostic's action dispatch is tested without hardware.
See `docs/actions/LIVE_OPEN_APP_INTEGRATION.md`. The selected experimental
Kitten voice is not wired into the product.

## Deliberate limits

- Site navigation such as `Open Chrome and go to Google` has no action kind or
  executor yet. The entire utterance asks for repetition; Chrome is not opened
  as a fragment of an unrecognized command.
- Chat discovery and navigation are not implemented. The spoken contact name
  must not be treated as a verified match.
- A launch request may be accepted before the app is visibly open. Dependent
  chat navigation waits for a fresh foreground observation when supported.
- The parser supports a small set of exact English forms. Multilingual plans,
  natural-language planning, more steps, and clarification within a plan are
  separate work.

Focused tests: `tests/commands/test_multi_step_commands.py` and
`tests/actions/test_plan_runner.py`.
