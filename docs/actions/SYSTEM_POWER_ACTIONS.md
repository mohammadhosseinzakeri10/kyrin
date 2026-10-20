# System power actions on Ubuntu GNOME

System power requests are independent of application-window commands. Existing
settings migrate to schema 5 with `system_power_enabled = false`. The global
action switch and the separate system-power permission must both be enabled.
No model, microphone, or desktop application allowlist is needed to use the
four on-screen request buttons. Spoken requests require an active STT session.
The initial spoken restart request now needs an explicit computer target,
such as `Restart this computer` or `این رایانه را دوباره راه‌اندازی کن`.
Bare `Restart` is ambiguous and does not begin a system-power flow; `Restart
Telegram` also cannot be treated as a computer restart. The reviewed phrase
recognizer is separate from any future language-model proposal. A new language
needs its own verified recognition path before voice power control is enabled.

`SystemPowerFlow` owns one pending request with a 45-second deadline. Only a
final transcript can start or advance it. A pending request consumes unrelated
speech instead of passing it to ordinary command interpretation. The first
answer is `Yes` or `Continue` by voice or the Continue button. The second is a short,
action-specific phrase shown in the UI or its matching button: `Power off`,
`Restart computer`, `Log out`, or `Suspend computer`. `Okay` and a second `Yes`
cannot confirm the final step. Unclear speech keeps the same request and
deadline and asks for repetition. It cannot switch to another power action.
Either voice or click may be used at either stage. Cancel, timeout,
microphone-session shutdown, and permission revocation clear the pending
request. Stale button events use the request ID and cannot confirm a newer
request. During a listening session with PipeWire echo cancellation, spoken
confirmation can be accepted while KYRIN's response speaker is active.
Without echo cancellation, `PlaybackGuardInput` and the voice-ready check
suppress KYRIN's own playback. Unclear replies update the dialog in text only,
avoiding a voice feedback loop.

The Qt application shows a separate, non-modal confirmation window over the
desktop. It labels the initial check as "no confirmation yet" and then labels
the two confirmation stages as 1 of 2 and 2 of 2. The main settings window is
not brought forward. Closing the confirmation window cancels the request.
Power prompts are shown and spoken through the shared speech synthesizer.
With PipeWire echo cancellation, users can answer while the prompt is playing;
the two required stages remain. The final spoken prompt states the phrase,
button option, and cancel option. If the user advances before a local TTS model
finishes generating a stage prompt, that now-obsolete audio is discarded before
playback rather than speaking over the next screen.

Before the first answer, the GNOME adapter queries `IsInhibited(1)` for logout,
shutdown, and reboot, or `IsInhibited(4)` for suspend. A reported inhibitor is
shown as a warning. An unavailable or unparseable reply is reported as unknown.
The absence of a registered inhibitor **does not prove all files are saved**:
applications such as editors may retain unsaved state without exposing it to
KYRIN. The prompt always asks the user to save work before continuing.

After both confirmations, the adapter calls GNOME's normal session methods:
`Shutdown`, `Reboot`, `Logout(0)`, or `Suspend`. It never calls forced logout or
suppresses native dialogs. A successful D-Bus call means the request was sent,
not that the machine shut down or a blocker was cleared. A GNOME dialog or an
application warning may still require the user to act. The control center
continues running while the session exists. Execution is on a background thread, and
unit tests replace the adapter so no test changes machine power state.

The owner confirmed a safe live preview on GNOME/Wayland: the top-level
window appeared over the current application, and text and audio worked at
both confirmation stages. The preview used a fake backend and could not send
any system-power request. Audio was initially inaudible because the system's
default output was a digital sink; selecting the TSCO Bluetooth headset made
Speech Dispatcher audible. Product playback follows the operating system's
selected output. A supervised end-to-end check inside the installed KYRIN
application, including spoken input, was subsequently completed with the
inert safe-preview backend described below. This does not validate a real
operating-system power request. Automated tests cover policy, timeout,
mixed voice/click confirmation, rejected ambiguous replies, stale IDs,
echo guard, the separate
Qt window without a microphone session, and the exact non-forced GNOME calls.
Spoken **input** remains
available whenever the microphone/STT session is running; click confirmation
also works when listening is off.

# Safe live preview, 2026-10-13

The owner completed a live microphone preview with the actual confirmation
dialog and spoken prompts. The observed sequence was `Power off` → `Yes` →
`Power off`; both dialog stages appeared and both spoken prompts were audible.
The preview used an inert backend whose `request()` only recorded
`SAFE_BACKEND_ONLY: power_off`. It did not call GNOME, logind, or any operating
system power API. A focused Qt integration test also exercises the same
spoken-stage sequence with a fake backend. This validates the interaction
path, not an actual shutdown or unsaved-work detection by every application.

The installed control center now has **Desktop Actions → Test power
confirmation safely (no shutdown)…**. It starts the same two-stage flow with
an inert backend. The dialogue is marked `SAFE PREVIEW`, and its final status
explicitly says no operating-system request was sent. A running listening
session can answer both stages by voice; clicking remains available. The
normal power buttons continue to use the GNOME backend and their separate
permission. The built-in preview is covered by automated backend-routing
tests. On 2026-10-14, the owner restarted the installed control center and
confirmed the `SAFE PREVIEW` window, both spoken stages, and the final
`No operating-system request was sent` message while responding by voice.

On 2026-10-20 the owner additionally reported that the real spoken Power Off
and Restart flows completed successfully on their machine. Diagnostic logs
for these runs were not provided. This live report covers those two actions;
it does not establish live results for Logout or Suspend.
