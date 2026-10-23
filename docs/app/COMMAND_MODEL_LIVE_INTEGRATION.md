# Local command models in the Ubuntu application

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
   request fails if inference did not use GPU memory. Auto lets Ollama decide.
4. Click **Save**. KYRIN stops and restarts the listening session with the new
   selection. Use **Speech Recognition → Diagnostics** to inspect recognized
   speech and interpreted commands. Desktop actions still need the separate
   permissions in **Actions**.

KYRIN starts a private loopback Ollama server with the selected model's store for the
listening session. It does not alter the user's default Ollama daemon, download
models, or use a cloud service. The server stops with that session. Missing or
incomplete models cause a visible start error rather than a silent switch.

## Decision boundary

Existing fast rules decide simple commands immediately. Unresolved speech is
sent to the model. Common polite English app-opening requests also use the
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

The model receives the original STT text, its advisory language hint, a
periodically refreshed catalog of installed permitted applications with
localized and owner aliases, and the operations enabled in the session. Screen
requests use fresh accessibility controls first and OCR when needed. A unique
exact visible name uses one model inference; an inexact name needs a second
inference against current option IDs. The selected control retains the focused
app ID; the executor rechecks that app, focus, and target before input.
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
