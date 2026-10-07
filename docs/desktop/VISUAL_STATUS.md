# Visual command status on GNOME

KYRIN can optionally show a small movable character near the top of a GNOME
desktop. It reports **the state of the command**, while the existing text and
voice responses carry the details. The character does not read the screen,
inspect windows, or execute actions.

## Meaning of each state

The short caption beneath the animated character describes the current event.
The controller localizes it before sending it to the GNOME adapter when a
supported language is selected.

| State | Example caption | Meaning |
| --- | --- | --- |
| Ready | Ready to listen… | Continuous microphone session is waiting for speech. |
| Listening | Listening… | The user has started speaking. |
| Processing | Understanding speech… | Speech is being transcribed or interpreted. |
| Question | Please clarify… | KYRIN needs the user to repeat or clarify a command. |
| Executing | Opening telegram… | An approved desktop action has actually started. |
| Confirmed | Done. | The action executor confirmed the result. |
| Unverified | Request sent; checking… | A launch was accepted or its result is unknown. |
| Failed | Could not complete that. | The action failed or was blocked. |

An STT partial result or an action merely waiting in the queue never means an
action is running. `LAUNCH_ACCEPTED` never produces a confirmed caption. The running
animation ends when the executor returns. After a result, the character retains
that state until the next speech or command event; silence does not erase the
conversation.
When a final transcript is not a command (including a negated command), the
character returns from processing to Ready. If that final also needs a repeat
or clarification, the following response event changes it to Question. Neither
transition interrupts an action that is already executing.
An authorized request in dry-run mode returns to listening; it does not display
an action result because no desktop action happened.

## Components

`VisualStatusController` maps structured speech, clarification, and action
events to these states. It does not depend on Whisper, Vosk, a voice model, or
GNOME. The optional `GnomeVisualStatusSink` sends a status and short caption over the
user session D-Bus. It uses a small worker so desktop IPC never blocks the
audio consumer. The extension displays the status in GNOME Shell and lets the
user drag it; it does not modify application windows. This first adapter
targets GNOME Shell 50 on Ubuntu. Other desktops can add sinks for the same
status contract later.

The current mascot is an experimental electric blue and violet vector design
drawn for small desktop sizes. It is assembled from transparent SVG layers for
the head, eyes, body, arms, and legs. `MascotAnimator` moves these layers with
compositor transforms; it does not generate frames at runtime. Ready uses a
subtle breathing motion; listening tilts the head and blinks; processing has a
thinking pose; execution alternates arms and legs in place. Question, unknown
result, confirmed result, and failure have distinct poses and symbols. A
confirmed check mark appears only after a confirmed action result. The GNOME
reduced-motion setting leaves it still. A small × button hides the
character; a temporary KYRIN top-bar control shows it again. Hiding lasts for
the current session and does not stop KYRIN or uninstall the extension. The
existing frame-coalesced drag implementation is unchanged.

## Manual setup and validation

The repository contains the extension source; it is not installed by running
tests or by the microphone diagnostic. To use it on GNOME Shell 50, package,
install, and enable it for the current user:

```bash
gnome-extensions pack --out-dir /tmp --extra-source=mascot.svg --extra-source=mascotAnimation.js --extra-source=mascotLeftLeg.svg --extra-source=mascotRightLeg.svg --extra-source=mascotLeftArm.svg --extra-source=mascotRightArm.svg --extra-source=mascotBody.svg --extra-source=mascotHead.svg --extra-source=mascotEyes.svg integrations/gnome-shell/visual-status@kyrin.local
gnome-extensions install /tmp/visual-status@kyrin.local.shell-extension.zip
gnome-extensions enable visual-status@kyrin.local
```

Depending on the Shell session, a manual logout/login may be needed before a
new extension becomes available. Start the existing microphone diagnostic in
commands mode with its usual explicit STT model and app bindings, adding
`--visual-feedback`. Real actions still require `--execute-actions` and
`--launch-app`; visual feedback does not grant permission to launch anything.
Without the extension, the diagnostic states that visual feedback is
unavailable and continues with text.

Verify listening, a clarification question, an actual action start, an
accepted but unverified launch, and a confirmed foreground app separately.
Drag the character and verify that it remains within the primary monitor. A
successful package build and Python tests do not establish that the character
rendered or moved correctly in the user's live GNOME session.

### Current validation, 2026-10-07

The Python status tests, type checks, lint checks, and extension package build
passed. The first live enable exposed a GNOME 50 error because
`Clutter.DragAction` was unavailable. Pointer-event dragging replaced it. In
a later user session, GNOME reported the extension as `ACTIVE`, its D-Bus
method was available, and the owner confirmed that the character was visible
and draggable. The owner noticed lag while dragging.

Previously every pointer motion called `set_position`, requesting repeated
layout and redraw work. The extension now keeps the newest coordinates and
updates position once before the next redraw, then flushes the last position
on release. A separate GNOME Shell 50.1 session loaded this version, accepted
a D-Bus status call, and verified that successive queued positions ended at
the newest coordinates. The updated package replaced the user's installed
copy. The current Shell may still run the previous JavaScript until a session
restart; improved smoothness on the real desktop awaits the owner's check.

### Remaining drag delay, 2026-10-07

The owner reported that frame-coalesced dragging was much better but still
trailed the pointer. A subsequent visual-translation experiment passed a
separate GNOME Shell 50.1 coordinate check, but the owner found that its live
dragging lag was substantially worse. That experiment was rolled back to the
frame-coalesced position update. The cause of the remaining live delay has not
yet been measured.

### Animated mascot preview, 2026-10-07

The earlier dark static concept was replaced with a compact original SVG mascot.
Focused Python tests verify localized status captions and action-target text.
A separate GNOME Shell 50.1 session loaded the vector asset and verified caption
updates, actual execution motion, × hide, top-bar reopen, and the existing
frame-coalesced drag behavior. Appearance and responsiveness in the user's live
desktop still need owner validation after the updated extension is loaded.

The owner then found that the new mascot could not be dragged. The live GNOME
log showed a click handler exception: `event.get_source()` can be null, so
passing it to `Clutter.Actor.contains()` aborted the drag before it began. The
handler was first changed to accept a null source. A focused headless test
verified that dragging could start again. After restarting the session, the
owner confirmed dragging but found that × did not hide the character.

### Close control correction, 2026-10-07

The drag press handler was attached to the whole character container, which
could consume a press intended for ×. Dragging now starts only on the
image-and-caption content; × is a separate click target. The owner confirmed
that dragging still works, but × still did not hide the character in that
session. The close button is now always clickable, hides on primary-button
press, and shows a short "Hide KYRIN" hint on hover. Its existing `clicked`
handler remains for keyboard activation. The revised package needs fresh Shell
code to load before live hide/reopen behavior can be confirmed.

The owner restarted the desktop session and confirmed that dragging, × hide,
and top-bar restore work. The new layered state reactions were packaged and
installed for the current user. A separate headless GNOME Shell 50.1 session
loaded all eight states, including repeated execution motion, without an
extension error. After restarting the desktop session, the owner checked a
no-microphone, no-action display run of all eight states. Listening, processing,
and execution motion were distinct; question, confirmed, unverified, and
failure symbols were visible; captions were readable; movement was smooth;
and × hide/top-bar restore still worked. The GNOME user-session log showed no
extension error during this run. This validates the presentation on the
owner's current GNOME desktop, not the timing of every state in a live
microphone-to-action run or other desktop environments.

In a subsequent 40-second live command diagnostic with local Whisper small,
explicit Telegram-only launch permission, foreground confirmation, and visual
feedback, the final transcript was `Open Telegram.` The action was reported
confirmed after Telegram became the observed foreground app. The owner also
confirmed that Telegram activated and that the character's state changes were
visible during this real command. A later non-command transcript reflected the
owner's spoken reaction after success; it caused no action. The diagnostic
exited normally and saved no microphone audio. This validates one local
microphone-to-action path, not all command timings or platforms.

### Final non-command correction, 2026-10-07

A focused audit found that an ordinary spoken reaction could leave the character
showing "Understanding speech…" after the final non-command decision. The
status controller now returns to Ready for that decision, while a following
clarification request still shows Question. Focused tests also verify that this
does not overwrite an action still running. The Python behavior is verified;
the revised presentation has not been checked in a new live GNOME run.
