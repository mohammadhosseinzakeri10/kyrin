# Visual status on GNOME

KYRIN can optionally show a small movable character near the top of a GNOME
desktop. It reports **the current speech, conversation or action state**, while text and
voice responses carry the details. The character does not read the screen,
inspect windows, or execute actions.

## Meaning of each state

The short caption beneath the animated character describes the current event.
The desktop composition defaults to English, independently of the interface
and STT languages. An explicit `visual_language="fa"` composition still supports
Persian captions. Transcript language never changes this preference. Application
names, observed titles and the model's original conversation reply remain verbatim.
Built-in chat-selection questions supply reviewed English/Persian alternatives,
so they follow the visual language while text/voice keep their own presentation
language. This local catalog does not automatically translate model replies.
The caption grows for longer messages, wraps at a screen-bounded width, and
shrinks again for short states. The extension keeps the resulting character
inside the primary monitor instead of replacing the end of a message with an
ellipsis. The mascot sits in a row that tracks the caption width; its
horizontal position is recalculated whenever the caption grows or shrinks.
This keeps it centered over the status bar. The visual transport sends the
full caption.

| State | Example caption | Meaning |
| --- | --- | --- |
| Ready | Ready to listen… | Capture is ready and command listening is active. |
| Ready | Standby. Say Start listening to speak. | Capture is open for exact voice controls; ordinary speech is not routed as a request. |
| Ready | Microphone off. Press Start listening to turn it on. | Capture is closed; use the GUI to reopen it. |
| Ready | Starting microphone… | The microphone session is opening; capture readiness is not yet confirmed. |
| Conversation | The model's original reply | A conversation response, retaining its original text/language. |
| Listening | Listening… | The user has started speaking. |
| Processing | Transcribing speech… | Speech paused and transcription is pending. |
| Processing | Understanding request… | Final speech is being interpreted. |
| Processing | Waiting for the request model… | Resource admission is waiting; inference has not started. |
| Processing | Queued for execution: Minimize telegram… | Authorization/queue progress; the executor has not started. |
| Question | Please clarify… | KYRIN needs the user to repeat or clarify a command. |
| Question | Confirm in the dialog: Activate control Mode | An existing control-confirmation dialog needs a response. |
| Executing | Minimizing telegram… | An approved desktop action has actually started. |
| Confirmed | Minimize telegram — Done. | The action executor confirmed this result. |
| Unverified | Result not confirmed. | Input was sent, a launch was accepted, or the result is unknown. |
| Failed | Could not complete that. | The action failed or was blocked. |

An STT partial result or an action merely waiting in the queue never means an
action is running. `LAUNCH_ACCEPTED` never produces a confirmed caption. The running
animation ends when the executor returns. After a result, the character retains
that state until the next speech or command event; silence does not erase the
conversation.
When a final transcript is not a command (including a negated command), the
character returns to the current idle state (file processing for file input).
If that final also needs a repeat
or clarification, the following response event changes it to Question. Neither
transition interrupts an action that is already executing.
An authorized request in dry-run mode explicitly says `Preview only: ...; no
action was executed.` It never displays a successful desktop-action result.

Exact `Start listening` / `Stop listening` controls render the runtime's actual
mode, including a repeated control; their final transcript cannot leave an
`Understanding` caption behind. `Stop listening` means standby, while microphone
off is a separate state. Queued replies from an older utterance and backwards
voice revisions cannot overwrite the current request. Capture callbacks from an
earlier speech generation cannot mark a replacement stream ready.
Final transcripts seal their segment. Duplicate/late partials and a delayed VAD
pause cannot reopen transcription after the response is ready. A streaming final
can start the model-progress caption before VAD has announced its pause.

All 25 command kinds have explicit operation captions, including window sizes,
window/tab creation, numbered selection, scrolling, Telegram destinations/search/
settings, and enabling/disabling visible controls. Every result keeps the
operation label. Policy confirmation, busy/cancelled work and unverified
dependencies have distinct meanings; they are not all rendered as failures.
The asynchronous chat-selection and result-paging workers report their actual
start, then return to a question when another choice is required. Paging says
`Loading more chat choices for ...` rather than claiming the target chat opened.

Audio retry, fatal capture/STT errors, request-model failure, TTS failure, setup,
file validation, file completion/cancellation and shutdown use separate captions.
Raw backend errors are not copied into the mascot bar. Completed file processing
preserves its last meaningful action/reply result; finishing a file is not proof
that its requested action succeeded. Periodic Qt refreshes cannot erase these
results.
Voice/file-import warnings retain the primary activity or result and append the
warning; a voice failure cannot falsely turn a successful action into failure.
Action outcomes retain concurrent standby/recovery guidance. Finishing a closed
file session cannot invite speech into capture that has already ended.

Power-off, restart, logout and suspend use their existing explicit confirmation
flow. Its prompt takes priority over ordinary captions until cancellation,
expiry or completion. The display router rejects older requests/backward phases;
it never grants consent. An accepted OS request is **unverified**, not confirmed
system completion; safe preview never displays real execution or success.

See the complete scenario matrix and verification record (`VISUAL_CAPTION_SCENARIOS_2026-10-27.md`, source repository only)
for current examples and test coverage.
The follow-up completeness review (`VISUAL_CAPTION_COMPLETENESS_REVIEW_2026-10-27.md`, source repository only)
records additional ordering, delivery and localized-chat fixes after that delivery.

## Components

`VisualStatusController` maps structured runtime lifecycle, speech, clarification, and action
events to these states. It does not depend on Whisper, Vosk, a voice model, or
GNOME. The optional `GnomeVisualStatusSink` sends a status and short caption over the
user session D-Bus. It uses a small worker so desktop IPC never blocks the
audio consumer. The extension displays the status in GNOME Shell and lets the
user drag it; it does not modify application windows. This first adapter
targets GNOME Shell 50 on Ubuntu. Other desktops can add sinks for the same
status contract later. `VisualPresentationRouter` serializes desktop publishing
and protects pending power prompts. Qt reports lifecycle transitions outside a
running runtime, without resetting captions on each timer tick. These components
only observe events; they do not approve actions or start input setup.
The sink keeps one latest pending presentation and refreshes it after capability
probing, avoiding a backlog of obsolete captions. One display call already in
flight cannot be recalled; native delivery latency/order still needs live checks.

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

The owner chose to retain the existing movement on 2026-10-27. The caption
changes reuse all nine existing animation IDs and do not replace SVG layers,
animation JavaScript, styling or installed GNOME extension files. Reloading the
Python application is sufficient for these caption changes when the current
extension is already installed; a Shell restart is not required for this task.

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
