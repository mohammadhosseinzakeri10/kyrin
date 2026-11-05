Saved permission or configured trust grants authority for supported actions.
Command and target evidence, clarification, and rejection of invalid model
proposals remain separate checks. See [persistent permissions](../actions/PERSISTENT_PERMISSIONS.md)
for current behavior where older confirmation examples differ.

# Local command models in the Ubuntu application

For generic interface control and Telegram, a dispatch without a verified
effect is `DISPATCHED_UNVERIFIED`. Dependent steps do not proceed from that
outcome. The [postcondition contract](../actions/ACTION_POSTCONDITIONS.md)
describes the limited verification paths.

The **Command Understanding** page can select an installed model from a local
Ollama model store or a directory of separate stores. The initial selection is
**Fast rules only**, preserving the existing behavior until the owner chooses
a model. Four development tags are currently present in separate Git-ignored
folders under `models/local/by-model/command-understanding/ollama/`; model
weights are never copied into application settings or Git.

## Use

1. Open KYRIN and go to **Command Understanding**.
2. Select **Ollama**, confirm the local model-store directory, and click
   **Refresh installed models**.
3. Choose a model and **Auto**, **CPU**, or **GPU**. CPU and GPU use the same
   model files; the Ollama runner chooses where to compute. An explicit GPU
   request requires observed GPU participation (full or mixed placement); pure CPU
   and unknown placement fail. Explicit CPU requires observed CPU placement.
   Auto lets Ollama decide and reports the observed result, including unknown.
   The page separately shows the requested device and the last inference's memory
   placement, inference status, and unload-request acknowledgement. Current memory
   residency after that acknowledgement remains unknown; Ollama expires runners
   asynchronously. Completed audio-file snapshots explicitly name their ended file
   session and cannot replace a newer microphone observation. This is memory
   placement, not processor-utilization telemetry. See the
   [device reporting contract](COMMAND_MODEL_DEVICE_REPORTING.md).
4. Click **Save**. KYRIN stops and restarts the listening session with the new
   selection. Use **Speech Recognition → Diagnostics** to inspect recognized
   speech and interpreted commands. Desktop actions still need the separate
   permissions in **Actions**.

KYRIN starts a private loopback Ollama server with the selected model's store for the
listening session. It does not alter the user's default Ollama daemon, download
models, or use a cloud service. The server stops with that session. Missing or
incomplete models cause a visible start error rather than a silent switch.

## Decision boundary

`LiveCommandRuntime` owns one understanding thread with four waiting updates
plus one in flight. Accepted finals remain FIFO; a final discards waiting
previews to free capacity. A full live queue uses the existing repeat-command
response without inventing an action intent. Exact listening controls stay on
the speech consumer. Stop, standby, or an STT stream change invalidates queued
work and late results, including speculative dialogue state and action tickets.
Understanding, focus reads, and inference run outside that consumer. Dialogue
flows retain their order on the understanding worker. Finite file input waits
for capacity and drains at normal EOF. On stop, understanding has a one-second
join budget; a timeout reports an error and suppresses late delivery. This does
not kill a Python thread or prove the model computation has stopped. No live
microphone/model latency measurement has been made for this change.

Existing fast rules decide simple commands immediately. Partial transcripts
return only the fast-rule result for replaceable previews; they never call
model understanding, model confirmation classification, the model app catalog,
or visible-control inventory/OCR. Only unresolved final speech is sent to the
model. Common polite English app-opening requests also use the
fast rules, avoiding both model inference and screen reading. A brief direct
greeting or question can now produce a
conversational response in the user's language, with no command intent. The
response is shown as text with a brief mascot gesture. Product speech output
is deferred. Reviewed spellings of KYRIN from the owner's speech diagnostics are
recognized as wake names; `Creator` is excluded because it can be ordinary
speech. `Hello Kyren` and `Hello Kyrene` were checked with the selected local
model and produced a greeting without an action. An exact German `Ja` or
`Nein` can answer a pending application-name
confirmation, but a standalone word with no pending question cannot launch an
application. These words do not replace the separate power-action confirmation.

For action proposals, the model proposes command meaning only. The STT
language label is advisory: a spoken English verb may arrive in Persian,
Arabic, or Urdu script. Reviewed spellings of `open` from the owner's
diagnostic trace use the fast path when the spoken app name exactly matches a
registered, permitted app. The uncertain `Opend` spelling asks for
confirmation. Other transcripts still go to the selected local model, which
returns canonical operation identifiers while retaining the target as written
in the original transcript.

For a language without an independently reviewed operation grammar, or speech
mislabelled as English/Persian whose operation is not recognized, a single-app
proposal can only create a pending confirmation when the model's target occurs
literally in the transcript and resolves exactly to one permitted installed
app. Opening and supported app-window actions name the proposed action in the
question; the user must explicitly confirm it, and the normal action gate
checks its permission afterward. A short reply in another language can be
classified by the local model as yes, no, or unclear; an unclear, incomplete,
negative, or unavailable classification does not run the action. Chat opening
and system power do not use this fallback. A focused scroll or named
visible-control request may use the model when the related Desktop Actions
permission is enabled. The focused window is observed again before input.
Model-proposed scrolling additionally requires a complete bounded English or
Persian request whose independently extracted direction matches the proposal.
Opposite, ambiguous, negated, quoted, and conditional requests are rejected;
languages without an independent direction grammar do not authorize scrolling.

The model receives the original STT text, its advisory language hint, a
periodically refreshed catalog of installed permitted applications with
localized and owner aliases, and the operations enabled in the session. Screen
requests use fresh accessibility controls first and OCR when needed. A unique
exact visible name uses one model inference; an inexact name needs a second
inference against current option IDs. Before interpretation (including the
first inference when controls are discovered later), the coordinator records
the existing GNOME `GetActiveWindowToken` plus app/PID, an observation generation,
monotonic time and the existing ten-second absolute deadline. Options carry
their observation too; OCR uses its capture ID as the observation generation.
`CommandIntent.control_observation`, retained inside `ActionRequest`, carries the
original request evidence to both OCR and accessibility helpers. Fresh target
reads never renew that deadline or authorize a replacement window of the same
app/PID, even with identical labels, anchors and frames. Helpers recheck the
token/age after portal consent, after accessibility lookup and before pressing;
the input budget also includes the original deadline. Missing/expired evidence
requests a new command, and a changed window stops the old request.
AT-SPI traversal uses only one active top-level window of the process; absent or
ambiguous window evidence supplies no accessible target. `ACTIVE` follows the
[official AT-SPI state contract](https://docs.gtk.org/atspi2/enum.StateType.html).
Semantic AT-SPI actions can run with OCR off. The helper re-resolves the
control and ancestry in the unique active window bound to the original token.
It requires visible, showing, enabled and sensitive controls and rejects stale,
ambiguous, or changed structures. Actions are selected by the interface's
advertised names. Desktop-control permission and the shared input ownership
checks still apply.

A successful `do_action` is an accepted call. Boolean state requires a fresh
read. The coordinate fallback is limited to missing exported semantic actions
or controls and retains the ownership and pre-press checks. Transport errors
and invalid or unknown actions fail closed. See the
[control policy](../actions/CONTROL_POLICY.md) and
[AT-SPI Action interface](https://docs.gtk.org/atspi2/iface.Action.html).
Deterministic tests exercise this route. Native coverage with OCR disabled
remains open.

These controls do not claim atomicity with focus changes after the final check.
These paths have deterministic tests but still need a live test with the
selected STT, command model, and OCR engine.
Slow model inference (at least two seconds), accessibility scans, and OCR reads
(at least one second) emit duration-only warnings. They do not log the spoken
text or visible labels, and allow a live latency report to identify the slow
stage.

Registered application names with three or more words also receive derived
short forms. For example, a registered `Visual Studio Code` entry accepts
`VS Code` and `VSCode`; duplicate short forms remain ambiguous and require a
choice. When the selected STT backend advertises vocabulary-hint support,
KYRIN passes at most 16 short names and registered multiword display names to
that backend. The current Whisper adapter passes them to its local inference
prompt. This may help transcription of unusual application names but does not
repair audio that contains no recognizable command or target. It never adds an
application to the action allowlist or changes STT language selection.

Model output cannot directly execute anything. The original transcript must
independently support the proposed operation and target, the target must resolve
to exactly one installed and permitted application, and the normal action gate
must approve it. Negation, uncertainty, unsupported operations, model errors,
and unverified targets never turn into an action. Existing two-step power
confirmation remains separate. The independent recognizer now accepts the
owner's colloquial `سیستمم رو خاموش کن`; a model-only power proposal cannot
start the power dialogue.

This is a usable local integration, not a claim of universal language support.
Direct app-operation source checks currently cover English and Persian; other
languages may require explicit operation confirmation. The question still
uses the available interface language. CPU inference may pause command
handling while the model runs; follow-up responsiveness and real microphone
behavior require owner validation. Model quality, false actions and
false-rejection rates must be measured with verified spoken references before
choosing a default model.

## Spoken application choices and window presence

When speech identifies an allowed installed app but not a clear operation,
KYRIN asks what to do. The menu is numbered and accepts exact replies such as
`one`, `number one`, `1`, `یک`, and `شماره یک`. An approximate app name is only a
suggestion: the user first confirms the app, then chooses an operation. A
Latin sound key helps suggest names such as `VTorain` for a registered
`V2RayN`, but it cannot directly authorize an action. Candidates come from
the installed, permitted app catalog rather than a fixed machine-specific
list. Closing from this menu requires a separate yes/no confirmation.

The platform-neutral window-presence contract has an optional GNOME adapter.
It reads only a mapped app's window existence through the active-app extension;
an unknown or unavailable reply offers only opening/bringing forward. If an
open window is observed and the related permission exists, minimizing and
closing also appear. The probe runs only on a final transcript. Windows and
macOS can supply their own adapters later without changing this dialogue.

In a live Terminal check, `gio launch` and GNOME activation accepted the
request, while `GetActiveApp` still reported ChatGPT. The owner later clarified
that the window seen was their pre-existing ChatGPT-related terminal. Therefore
the requested Ptyxis activation has not yet been visually verified. The new
presence method needs a fresh GNOME session before a live end-to-end check;
it does not by itself prove which window is in front. Terminal-specific
choices are now limited to a binding for the installed GNOME Ptyxis entry.
On `Open Terminal`, zero observed windows leads to a normal launch; one
window asks whether to bring it forward, open a new window or tab, or open
Preferences. With several Ptyxis windows, KYRIN can show a numbered picker
containing only windows belonging to the bound `org.gnome.Ptyxis.desktop`
application, open a new window, or open Preferences. The picker displays
equal-sized live previews. The owner can click a preview or say its number
(for example, `number two` or `شماره دو`). The extension records stable window
tokens when the picker appears and rechecks the token and app ID before
activation. A disappeared window is not replaced by another window. `Cancel`
or Escape closes the picker. The GNOME-wide overview is no longer offered by
the Terminal menu. This GNOME 50 UI still needs a live desktop check after
the extension is reloaded.
It does not guess which existing window should receive a new tab. When window
count is unavailable, only open/bring forward is offered. The fixed Ptyxis
arguments come from its installed desktop entry and cannot contain transcript
text. A `Close Terminal` request now requires a separate confirmation. A
bulk Quit and dock Unpin are not offered: Quit could terminate a running
shell task, while Unpin belongs to the desktop dock rather than Ptyxis.
These new behaviors need a fresh GNOME session and live owner validation.
The GNOME window adapter remains attached during login even if the Shell
extension loads a little later; unavailable reads return unknown rather than
locking the feature off until the app is restarted. A new-tab request checks
again immediately before execution that exactly one Ptyxis window remains.

Model admission and residency follow the [shared resource policy](../app/MODEL_RESOURCE_POLICY.md).
The application keeps device selection and capability checks separate. Native
latency and memory behavior still require measurement.
