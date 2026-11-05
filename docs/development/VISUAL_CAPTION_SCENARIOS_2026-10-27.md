# Visual caption scenario review — 2026-10-27

The [follow-up completeness review](VISUAL_CAPTION_COMPLETENESS_REVIEW_2026-10-27.md)
adds later fixes and verification. The original counts/evidence below describe
this delivery snapshot and are retained as history.

The owner requested scenario-specific messages beneath the existing character
across the supported application flows, rather than a special case for Start
listening. English is the primary caption language. The existing movement remains
selected; this task changes Python presentation and event wiring only.

## Actual lifecycle and language contract

Desktop captions use the explicit visual language (English by default), separately
from STT and UI preferences. Persian remains an explicit composition option.
Literal targets and the model's original conversational reply retain their text.
A Persian transcript cannot silently switch English status/clarification text.
The optional `scripts/audio/check_live_speech.py --visual-feedback` path follows
the same English preference, capture-ready/startup/shutdown reporting, voice-mode
observation, stream attribution and classified error contract. Its ordinary text
and voice response language keeps its existing configuration.

| Lifecycle trigger | Current English caption |
| --- | --- |
| Opening capture; readiness not yet confirmed | Starting microphone… |
| Capture ready, ordinary request routing disabled | Standby. Say Start listening to speak. |
| Capture closed; GUI activation required | Microphone off. Press Start listening to turn it on. |
| Shutdown requested; cleanup underway | Stopping microphone… |
| Recoverable audio/STT interruption | Speech recognition interrupted; reconnecting… |
| Fatal listening/startup failure | Listening unavailable. Check the microphone and speech model. |
| Speech paused; partial transcription pending | Transcribing speech… |
| A file session is processing input | Processing audio file… |
| File session finished; meaningful result is retained | Audio file processing finished. |
| File session cancelled | Audio file processing stopped. |
| No speech model selected | Choose a speech model to enable listening. |
| Understanding queue accepted the final transcript | Request queued for understanding… |
| Request-model resource admission waiting | Waiting for the request model… |
| Request-model inference started | The model is processing your request… |
| Speech synthesis/playback failed; text still available | Voice output failed; the text response is still available. |
| File validation/processing failed | Audio file processing failed. Check the file and speech model. |
| File importer unavailable | Audio-file input is unavailable. Check the speech settings. |
| Request model raised a classified failure | The request model failed. No action was executed; check the model settings. |
| Import blocked by unsaved settings | Save current settings before importing audio. |

Capture-ready active mode says `Ready to listen…`; speaking says `Listening…`;
final transcript interpretation says `Understanding request…`. Consumed exact
Start/Stop listening controls restore the authorized runtime mode. Repeated Start
listening is an acknowledgement, not an understanding request. Standby remains
distinct from physically closed capture. Silent frames do not erase results.
Audio failures also retain the existing classified microphone/STT/device/queue
notice; raw backend exception messages are not copied into the bar.

## Every supported operation

The executor-start callback, rather than model proposals or queue admission,
selects these progress messages. The example target below is the inert test
fixture; no listed operation was executed on the owner's desktop.

| Command kind | Current English progress example |
| --- | --- |
| `open_app` | Opening or bringing telegram forward… |
| `open_chat` | Opening chat Ada… |
| `telegram_view` | Opening Telegram archive… |
| `telegram_settings` | Opening Telegram setting Privacy and Security… |
| `telegram_search_focus` | Focusing Telegram search… |
| `telegram_search` | Searching Telegram for telegram… |
| `scroll_up` | Scrolling up… |
| `scroll_down` | Scrolling down… |
| `visible_control` | Activating control telegram… |
| `restore_app` | Bringing telegram forward… |
| `minimize_app` | Minimizing telegram… |
| `close_app_window` | Closing a window of telegram… |
| `maximize_app` | Maximizing telegram… |
| `unmaximize_app` | Restoring normal size of telegram… |
| `fullscreen_app` | Making telegram full screen… |
| `unfullscreen_app` | Leaving full screen in telegram… |
| `new_app_window` | Opening a new window of telegram… |
| `new_app_tab` | Opening a new tab in telegram… |
| `app_preferences` | Opening preferences for telegram… |
| `show_all_windows` | Showing open application windows… |
| `show_app_windows` | Showing windows of telegram… |
| `select_app_window` | Selecting window 2 of terminal… |
| `close_shown_window` | Closing window 2 of terminal… |
| `hide_app_windows` | Hiding window previews… |
| `select_open_app_window` | Selecting an open window of telegram… |

Visible-control Boolean state additionally selects `Enabling control ...` or
`Disabling control ...`. Telegram settings back/cancel and canonical destination
names receive their own readable captions. Numbered windows retain the actual
number. Plans show the step count during permission/queue processing, then show
the real operation when each step starts; a delayed first-step result cannot
replace a later step's result.

## Decisions and results

All five executor outcomes are covered for every operation (125 combinations).
Only `CONFIRMED` gives the confirmed reaction. `LAUNCH_ACCEPTED`,
`DISPATCHED_UNVERIFIED` and `UNKNOWN` retain an unverified result. `FAILED` reports
failure. Window-picker launch acceptance instead asks for the window number.
Every final action message retains its operation label. Dry run explicitly says
`Preview only: ...; no action was executed.` An executor exception reports an
unverified result because an input may already have been sent.

| Policy result | Status | Current English example |
| --- | --- | --- |
| `not_allowed` | `failed` | Minimize telegram — I can't perform that action. |
| `confirmation_required` | `question` | Minimize telegram — Please confirm before I do that. |
| `busy` | `ready` | Minimize telegram — I'm still processing. Please wait and try again. |
| `cancelled` | `ready` | Minimize telegram — That action was cancelled. |
| `unsupported` | `failed` | Minimize telegram — I can't perform this step yet. |
| `dependency_unverified` | `unverified` | Minimize telegram — A prerequisite was not verified, so I skipped the dependent step. |

Existing dialog approval is observed, not granted by the caption controller.
While waiting it says `Confirm in the dialog: ...`; only the existing confirmer's
true return resumes the execution message. Declining confirmation/cancelling
selection is distinct from execution failure; expired selection asks for a new
choice. Chat and window selection retain their existing permission/evidence
checks.

| Response kind | Status | Current example |
| --- | --- | --- |
| `ready_for_command` | `ready` | I'm listening. Tell me what to do. |
| `choose_chat_app` | `question` | Which app should I open the chat in? |
| `choose_app` | `question` | Which app do you mean? 1. Telegram; 2. Terminal. Say its number or name. |
| `confirm_app` | `question` | Did you mean the Ada app? |
| `choose_app_or_chat` | `question` | Do you mean the Ada app or a chat? 1. App. 2. Chat. Say app, chat, or the option number. |
| `choose_operation` | `question` | What should I do with terminal? 1. Open or bring forward; 2. Minimize Say yes to open or bring it forward, no to cancel, or choose an option number. |
| `choose_window` | `question` | Only terminal windows are shown. Say a window number or click its preview. |
| `confirm_action` | `question` | Do you really want me to close terminal? Yes or no? |
| `confirm_numbered_close` | `question` | Close window number 2? Yes or no? |
| `repeat_command` | `question` | I didn't understand. Please repeat the command. |
| `conversation` | `conversation` | Original model reply, unchanged |

## Power actions and ordering

All four power actions (power-off, restart, logout, suspend), eight stages and
both real/preview modes have status assertions (64 combinations). Checking is
processing; the first/second consent stages are questions; real submission is
executing. Accepted submission is unverified, never proof of completed shutdown.
Cancelled/expired prompts return to ready; failed submission reports failure.
Safe-preview submission/completion never claims real execution or confirmation.
The original English power-flow prompt supplies the operation-specific detail.

A serialized presentation router protects a pending power prompt from ordinary
speech, playback-error and polling captions. Older request IDs and backwards
stages cannot reopen an obsolete dialog. Terminal stages release the priority.
No caption callback approves a request, submits OS power input, starts portal
setup, changes a saved permission or rotates a token.

Other ordering contracts:

- Runtime mode revisions, speech-stream generations and utterance IDs prevent
  stale capture readiness, transcripts and replies from restoring an older state.
- New speech protects its caption even before its first transcript arrives.
- An actually running action retains priority over concurrent speech and busy
  notices. Feedback for a different/older action cannot end its running state.
- Backlog recovery restores an earlier caption only if its backlog notice is
  still current; it cannot erase a new reply or question.
- Timing finish events never overwrite conversation replies or action results.
- Repeating an explicit voice control reasserts its actual mode after an
  independent power/app caption; internal duplicate suppression cannot leave
  a cancelled power message in place of the requested listening acknowledgement.
- Qt reports nonrunning lifecycle transitions once; polling does not continually
  reset captions. A queued file completion is protected until GUI delivery.
- File completion retains a meaningful action/reply outcome and appends completion
  information; file completion never upgrades an unverified action to success.
- Closed sessions ignore subsequent callbacks. Control prompts cannot replace
  standby/stopping captions with an impossible invitation to answer.

## Verification record

The caption layer reacts to existing events and timing boundaries. It adds no
per-frame renderer, model inference, external service or dependency. It reuses the
existing asynchronous GNOME sink; native latency/resource use was not benchmarked.

The final full checker completed successfully:

| Check | Result |
| --- | --- |
| Syntax | Passed |
| Global Ruff | Passed |
| Strict mypy | Passed on 454 files |
| Full pytest | 3285 passed in 86.35 seconds |
| Source provenance | This checkout's `src/kyrin` |
| Source/test/configuration drift during the final check | None across 455 files |
| Original animation preservation | All 11 source, Git HEAD and installed hashes matched |
| Local links in the three updated reference/index documents | Resolved |

These global counts include other existing repository work. Raw final evidence is
under `local-data/visual-caption-fix/verified-check/`, with before/after hashes and
`verified-drift.json` beside it. Earlier raw runs are retained separately; one
intermediate run caught unrelated formatting edits in progress. The final run
passed all four gates without source changes during execution.

The initial two regressions were reproduced before correction; their output is
in `local-data/visual-caption-fix/before.txt`. A further regression reproduced a
repeated Start listening acknowledgement remaining on a cancelled power caption;
it now has a passing guard. Focused caption/composition/UI/runtime tests also
passed after that correction (564 cases).

Focused tests use fake audio, models and executors; Qt runs offscreen. The full checker isolates
HOME/XDG and removes the personal session's display/D-Bus environment. Input-session
regressions use private fake services. These tests do not establish live STT,
voice quality, GNOME rendering latency or native resource usage.

The full suite includes the maintained input-session regression checks in
`tests/actions/test_input_session.py`, `tests/actions/test_input_session_bus.py`,
`tests/app/test_qt_window.py`, `tests/app/test_qt_input_access.py` and
`tests/app/test_permission_token.py`. Deterministic tests retain their distinction
from owner validation of remembered OS consent after a restart.

The machine-readable examples are in
`local-data/visual-caption-fix/caption-matrix.json`. Animation preservation is
recorded in `local-data/visual-caption-fix/animation-preservation.json`: all eleven
source and installed animation/SVG/style files match both the original baseline
and Git HEAD. No installed extension file or personal setting was changed.

To validate the delivered Python changes on the desktop, restart KYRIN normally
and check standby → Start listening → ready → speech → transcription → model
response, a clarification, an approved action and its observed outcome, then
Stop listening and microphone off separately. Check failed/cancelled file import
and a safe power preview separately. Retain the existing grants and use ordinary
configured controls. Live owner acceptance remains pending.
