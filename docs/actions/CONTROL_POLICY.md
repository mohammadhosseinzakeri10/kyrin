# General control policy and persistent consent

(English migration of a previously Persian-only note; the original is preserved
in the private migration pre-images and in Git history.)

Since 2026-10-25, by explicit owner decision, the stored desktop-control
permission is consent for the operations it covers. The earlier F02/F11
contract, which required a separate button per operation, was replaced by the
[shared permission contract](PERSISTENT_PERMISSIONS.md).

## Enforcement

`PermissionPolicy` is applied in the gate and again after the input turn is
acquired. In the main path a control with an unknown outcome still requires an
independent, unique observation of the target but does not call
`ControlConfirmer` again. Permission, the OS input token and the tool capability
are all required. A model and a control label never grant permission. Send,
delete and payment still require a tool with its own outcome and permission
contract; a general tool trust implements none of them.

An observation is bound to the request, capability, name and target evidence,
application/PID/token/generation and desired state. The single-use
`ControlApproval` and its original ten-second budget are kept.

## Observation rules

- Before scrolling, if the standard window-properties API is available it is
  read so a provider with on-demand export has time to prepare. Property values
  are not retained or passed to a model.
- For the first absent child, at most three readiness reads and two 50 ms pauses
  are made; then the active window is selected again and the full tree is
  validated with every constraint. A readiness result alone is not evidence of a
  control; a still-absent child or an unreadable count does not permit
  execution.
- Trailing role words such as *button* and *option* remain part of the full
  name; a different shorter name is not selected in place of the spoken one.
  Name, role, state and structural path are separate fields.
- A control with AT-SPI structural identity may run through its own Action
  without coordinates. This exception does not permit guessed coordinates.
- If the source application's SCREEN extents are zero-origin and do not fit the
  GNOME frame, the semantic path is accepted only with a unique active window of
  the same PID, an exact positive frame-size match and explicit zero-origin
  WINDOW extents. Every control's WINDOW extents must be positive and entirely
  inside that window. No global coordinates are produced in this case and this
  evidence does not authorize a coordinate click. A size mismatch or invalid
  relative extents is still rejected. The rule does not depend on an application
  name.
- The target is resolved again and compared with earlier evidence: AT-SPI
  structure, role, position and state, or OCR box and geometry. Just before the
  change the helper rechecks identity, focus, position, state, permission
  generation and cancellation. OCR does not guess boolean state.

## Directed check / uncheck

`check` and `uncheck` are accepted only with a readable boolean state:
`check` turns an off control on and `uncheck` turns an on control off. For an
explicit click on such an option, the direction is derived from the inverse of
the observed state. The action name is read from the non-localized API; index
zero is not assumed and more than one compatible action is still ambiguous.
An already-satisfied state is confirmed without action. After the action, a
change is confirmed only by re-reading the same control; a successful API reply
alone is insufficient.

## Shared control list

The shared list is a versioned result with traversal state, valid controls and
rejected names. A read error, incomplete tree or malformed helper reply is not
equivalent to a "successful, empty list" and does not fall through to OCR. A
duplicate or invalid name is not made valid again via OCR. An explicit absence of
the application in AT-SPI is distinguished from a traversal failure; the
existing visual path is usable only with valid evidence and its earlier
constraints. A stable execution-failure cause is converted to a Persian or
English message from `visible_control_observation:<reason>`; window text and raw
errors are not published. This contract is shared by all applications; it does
not follow that every application has the control capability.

## Focused scroll and More

A final scroll request carries the `WindowObservation` (application, PID,
window token, generation and deadline) read before interpretation, in
`CommandIntent.scroll_observation`. The coordinator rejects the request when
that evidence is missing, expired or belongs to another application. The
evidence is never refreshed: it travels unchanged through the action queue and
input admission, and its deadline bounds the whole operation.
`DesktopScrollExecutor` rechecks identity and the original token before
admission, and `desktop_scroll_helper.py` rechecks them after acquiring the
input session and before every input event. A replacement window of the same
application or process, a changed PID or an expired deadline sends no scroll
and yields `failed` / `scroll_focus_changed`; a stop after the first event stays
`unknown`. A scroll step inside a multi-step plan has no such evidence and is
rejected.

`More` / `Again` reuses the recent direction, amount and area only within 30
seconds and only when the newly observed window has the same identity and token
as the scroll it repeats; the repeated request carries its own new evidence.
Telegram's internal list scrolls are unchanged by this rule; their window
binding across helper calls is tracked separately.

## Close

Window close uses the dedicated tool and `CloseAuthorizedWindow`; a generic
click on Close is unsupported with this permission. Older Qt/native confirmation
methods remain for compatibility and isolated tests; the main composition
injects the persistent policy. Consent comes from settings and the one-use
binding keeps the validity of that request.

Input dispatch is not necessarily success; the
[postcondition contract](ACTION_POSTCONDITIONS.md) is kept. Tests for changed
target, cancellation, expiry and absent dialog are in the
implementation report (`PERSISTENT_PERMISSIONS_2026-10-25_FA.md`, source repository only).
Live click testing in all applications and OCR/AT-SPI paths is not claimed. The
optional read-only tool and the shared blocker state of application control are
in the L04 report (`L04_VISIBLE_CONTROL_2026-10-26_FA.md`, source repository only).
