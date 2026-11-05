# Tool result and postcondition contract (F03)

This note replaces the historical "click accepted" description in the generic
control and Telegram paths. (English migration of a previously Persian-only
note; the original is preserved in the private migration pre-images and in Git
history.)

- `CONFIRMED`: the requested state was confirmed by observation. It may already
  have held, so no input may have been needed.
- `LAUNCH_ACCEPTED`: the application launch request was accepted but the result
  has not been observed. Earlier uses by tools outside this card are kept.
- `DISPATCHED_UNVERIFIED`: input dispatch was reported but the postcondition was
  not verified. This is not success and produces no verified active app.
- `UNKNOWN`: the transport or execution answer is unknown; even input dispatch
  may be unknown. A user message must not claim definite failure or success.
- `FAILED`: the tool reported a specific error. It is not permission for
  automatic retry.

## Required evidence

For generic navigation, only a fresh, active dialog of the same application and
a process with the exact option title counts as evidence. The token must change
relative to the initial window and stay stable when read. Application identity
is rechecked. An image change, an arbitrary node appearing, an already-open
dialog or the existence of a button name is not enough. Internal pages or dialogs
with a different title stay unverified.

For a toggle, the boolean state of the same node and structure in the same
window is re-read after input. Both the semantic and the coordinate paths do
this check. An already-desired state is confirmed without input. An uncertain
Action response is first checked by reading state and never triggers a fallback
click. Permission for generic toggles follows
[the F02 capability and bounded-approval policy](CONTROL_POLICY.md); approval of
an action does not replace postcondition observation.

For Telegram, the navigation target title, search phrase or chat header is read.
A chat title alone does not prove the exact contact: paths through visible rows
and duplicate titles stay unverified even with a matching header. A search path
with a unique identity still needs a matching header. For Escape and search
focus there is no sufficient generic postcondition, so only input dispatch is
reported.

Each Telegram operation is bound to the GNOME window token focused when it
starts; a pending chat selection or result page keeps the token of the window
whose capture showed its rows. Every helper call, scroll, OCR read and
postcondition requires that token, not only the application ID and process ID.
A same-process replacement window therefore receives no further input, and its
text is treated as absent evidence: the step fails before input or stays
`dispatched_unverified`, never `confirmed`. A capture without a window token
cannot be bound and is rejected. No transition to another window is accepted as
a legitimate destination, and no input is retried after a replacement.

The generic postcondition acceptance window is 300 ms. Telegram verification
reads at most three times, 100 ms apart. The operation ceiling, cancellation and
initial observation deadline still apply. These intervals do not guarantee the
duration of accessibility or OCR calls. A result later than the budget is not
assumed successful.

## Dependencies and recovery

Dependent steps run only with a confirmed prerequisite. Opening a different
named application is independent and may continue. Repeating the same
unverified launch is not independent. For opening a chat, a fresh observation
of the active application may confirm the launch prerequisite; it does not
replace the evidence of a navigation or toggle. Without finer dependency
metadata, other steps conservatively depend on earlier ones.

Tools only read while checking a postcondition and never resend input. A missing
Telegram menu option or the disappearance of an Archive title is not positive
evidence of the correct transition, so the automatic second click was removed.
If the first click on Archive returns but no menu is observed, the result stays
unverified. A fresh request first re-reads menu state. After the budget ends, the
dependent step does not run, with a specific message; there is no late automatic
continuation or rollback.

The meaning of invoking an Action and of clearing the cache was checked against
the official documentation:
[Action invocation](https://docs.gtk.org/atspi2/method.Action.do_action.html)
and [refreshing accessibility information](https://docs.gtk.org/atspi2/method.Accessible.clear_cache.html).

Tests are deterministic and cover an ineffective click, a slow target, an
already-desired state, an unknown answer, node or focus replacement and
continuation of independent actions. Live GNOME, AT-SPI and Telegram tests were
not performed.
