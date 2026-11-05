# KYRIN command guide

English is the primary command language for V1. These are supported request
forms, not guarantees that every recognizer or application will handle them.
An action also requires the relevant saved capability, an available adapter
and a sufficiently identified target. Start with desktop actions disabled
while checking what the recognizer actually heard.

This guide describes the current source as reviewed on 2026-10-28. The
Persian guide (`USER_COMMAND_GUIDE_FA.md`, source repository only) is retained as a learning and
historical reference; some of its earlier power and control descriptions
predate the current permission policy. The
[language policy](../LANGUAGE_POLICY.md) distinguishes interface language,
speech language, responses and target text. See
[validation](../VALIDATION.md) for the limits of automated and owner evidence.

## Listening controls

| Say | Effect |
| --- | --- |
| `Start listening` | Leave standby and accept commands after capture is ready. |
| `Stop listening` | Enter standby; capture/recognition may continue to hear the start phrase. |
| `Turn off microphone completely` | Stop capture. Use the application controls to start it again. |

These controls require complete final phrases. A partial transcript or a
phrase quoted as ordinary speech must not change microphone mode. Saying
the start phrase cannot reactivate hardware after capture is fully off.

## Applications and windows

Replace the example app with an installed app whose action is permitted.
An ambiguous app name may produce a numbered question. Opening an app may
activate its existing window rather than create another one.

| Say | Request |
| --- | --- |
| `Open Calculator` | Open or activate the application. |
| `Restore Calculator` | Bring its window forward. |
| `Minimize Calculator` | Minimize its window. |
| `Close Calculator` | Request normal window close; this has a separate permission. |
| `Close all Calculator` / `Close all windows of Calculator` | Normal close of the exact app's complete window set; uses the native app/count dialog unless saved direct-close consent is enabled. Requires the updated extension. |
| `Maximize Calculator` | Maximize the window. |
| `Unmaximize Calculator` / `Un-maximize Calculator` / `Un maximize Calculator` | Restore normal size while keeping the window visible. |
| `Fullscreen Calculator` / `Full screen Calculator` / `Full-screen Calculator` | Enter full screen. |
| `Exit fullscreen Calculator` / `Exit fullscreen on Calculator` | Leave full screen; `full screen` and `full-screen` spellings also work. |
| `Show all open windows` | Show numbered window previews. |
| `Show Calculator windows` / `Show Calculator's windows` | Show only this exact permitted application's open windows. |

Say the complete app-preview phrase in one utterance. `Show Calculator` alone
means restore; a separate later `Windows` does not change that earlier request
into an app-preview command. A multiple-window restore must not guess a window.

Bulk close is an exact-source command. In Desktop actions, enable and save
`Close all windows without asking each time (permitted apps only)` to use remembered
direct consent; existing global trust also covers this capability. App-specific
close permission remains required. Without that saved grant, the native app/count
dialog remains. A changed window set rejects either commit path. Groups over 32
windows are refused as a whole. Application Save
dialogs remain for you to answer; partial/uncertain closes are not success and are
not retried. Background/tray behavior remains the application's normal behavior.
See the [group close contract](../actions/APP_WINDOW_GROUP_CLOSE.md).

In Terminal's pending operation menu, `Preference` and `Preferences` both select
the offered preferences action. With desktop control enabled, exact `New tab`,
`Create new tab` and `Create a new tab` also work directly: fresh focused Terminal
evidence selects that window; otherwise KYRIN shows Terminal windows and asks for
a number. The number continues the original tab request. Say `Cancel` to abandon
it. This needs the updated tab-picker extension and existing app/window/control
grants. Clicking a preview only focuses it; a fresh tab request can then target
that window. No MRU or guessed destination is used. Without targeted desktop
control, the older menu/CLI tab path still requires exactly one Terminal window.
See the [Terminal tab targeting contract](../actions/TERMINAL_TAB_TARGETING.md).

Minimize removes the window from view; unmaximize restores its normal visible
size. Restore brings a minimized window back. These are distinct operations.
Explicit size-operation spellings also accept a comma before the exact app name,
as in `Full screen, Calculator`. Only the operation span is canonicalized; app
names and free search/chat text retain their existing handling. A bare `Exit`
does not name an application and must not infer one from foreground focus.

While a window question is pending, use `Number two` to select a preview.
In the all-app picker, naming an app with several windows opens a fresh picker
filtered to that app; choose a displayed number afterward. A sole shown window
can retain the existing exact app activation path. Missing or unknown windows
must not be replaced by a guessed window. Only registered apps with saved window
permission enter this picker. The existing Shell snapshot rechecks numbered
selection; `Cancel` closes the picker without closing the application windows.
`One`, `First`, `Number one`, `Two` and `Second` are exact numbered replies while
that question is pending. Repeating the app name does not select a window; agreeing
audio hypotheses preserve the same numbered question. After a successful choice,
show a fresh picker before choosing another number. This behavior uses registered,
permitted applications rather than a special browser name; actual compatibility
still depends on the desktop exposing the application's windows.
`Close window two` enters the existing close-confirmation path. The number
only applies to the current observed list, not a remembered position.
Normal close does not answer an application's save dialog or force-kill it.
Saved close/window permission can authorize an explicit numbered close directly;
an extra spoken Yes is then unnecessary. Without saved authorization the existing
confirmation question remains. Agreeing audio hypotheses may advance the same
picker to the same numbered-close question; conflicting numbers or operations
must still reject. The executor revalidates the actual permitted window.

When `Open Terminal` produces a question, choices can include `New window`,
`New tab`, `Preferences` and `Terminal windows`. Availability depends on
the application's desktop entry and observed windows; these are contextual
answers; direct tab requests are the scoped Terminal exception described above.

Bounded plans such as `Open Telegram and open Calculator` are supported.
They are not arbitrary automation programs. A later rejected step does not
undo an earlier completed step.

## Scrolling and visible controls

Use `Scroll down`, `Scroll up`, `Scroll down more` or `Scroll up less` in
the active observable window. `More` or `Again` can repeat a recent scroll
only within the existing time and foreground-context limits. Scroll input
requires its own capability and prepared desktop input access.

Named-control examples include:

```text
Click Advanced
Go to Settings
Select Language
Click Search icon
Turn on Desktop notifications
Uncheck Show tray icon
```

These are requests to inspect a control, not permission to click arbitrary
coordinates. Execution depends on capability classification, fresh
accessibility/OCR evidence and, where required, explicit confirmation.
Unavailable, ambiguous, moved or unsupported controls are rejected.
An optional command model may propose a meaning or a currently observed
option; it cannot override these checks. See the
[control policy](../actions/CONTROL_POLICY.md).

## Telegram Desktop

Telegram navigation requires its own capability and a verified active Telegram
window. Some paths additionally require screen access, a usable OCR engine
and prepared input access. These commands operate on the local application;
they are not messages to a Telegram bot.

| Say | Request |
| --- | --- |
| `Open chat Saved Messages` | Find and open the named chat through the supported search path. |
| `Open visible chat My Mother` | Inspect the visible chat list without typing into search. |
| `Go to search` | Focus Telegram's search box. |
| `Search Telegram for My Mother` | Enter a search; do not select a result or send a message. |
| `Go to archive` | Navigate to archived chats. |
| `Go to contacts` | Navigate to contacts. |
| `Go to settings` | Navigate to settings. |
| `Go to my profile` | Navigate to the profile. |
| `Go to my calls` | Navigate to calls. |
| `New group` / `New channel` | Open the creation entry screen; do not complete creation. |
| `Scroll chat down` | Scroll the conversation area. |
| `Scroll chat list down` | Scroll the chat-list area. |

Chat titles retain their original script. A misheard title is not permission
to choose a similar person. Observed alternatives may require a numbered
selection and a fresh header check. In a pending results question, `Number
two`, `Next`, `More results` or `Cancel` apply only to that dialogue.

Settings requests include `Go to Notifications and Sounds`, `Go to Privacy
and Security`, `Go to Chat Settings`, `Go to Folders`, `Go to Advanced`,
`Go to Speakers and Camera`, `Go to Battery and Animations` and `Go to
Language`. After settings is verified open, an observed navigable row may
also be requested with `Go to Display Name`. Reading or opening a settings
section does not authorize changing its values. `Go to Back` requests the
existing back/Escape path; it does not prove which screen will appear.

## System power

Explicit requests include `Power off this computer`, `Restart this computer`,
`Log out` and `Suspend`. A bare `Restart` is not an explicit request to reboot
the computer.

The current desktop application uses persisted action permission: execution
and the system-power capability (or global trust) must be enabled. An
authorized explicit request can proceed without the old per-command two-stage
dialogue. Native operating-system/application warnings may still appear;
KYRIN does not force shutdown or dismiss save warnings. A successful request
submission does not prove that shutdown, restart or logout completed.

**Test power confirmation safely (no shutdown)…** is a separate inert preview.
Its two-stage dialogue does not submit a real power action and is not the
authorization contract for normal desktop requests. See the current-policy
section of [system power actions](../actions/SYSTEM_POWER_ACTIONS.md).

## Replies, uncertainty and limits

- `Yes`, `No`, numbered choices and `Cancel` only resolve an applicable
  pending question. They are not fresh authorization for an unrelated action.
- A correct transcript can still produce an unsupported or ambiguous command.
  An accepted command can still be rejected by permissions or observation.
- An input-dispatched or request-accepted result is distinct from verified
  completion. Do not infer success from an animation or automatically repeat
  an uncertain action.
- Optional local conversation replies do not grant actions. No universal
  multilingual recognition, arbitrary shell execution or unrestricted
  desktop control is promised.
- Sending, editing, deleting or forwarding Telegram messages, completing
  group/channel creation and placing calls are not provided by these examples.

For setup use [Getting started](../GETTING_STARTED.md). For deterministic
checks and the separate live acceptance boundary use the
[quality gate](../development/QUALITY_GATE.md).
