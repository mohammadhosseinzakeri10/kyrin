# System power actions on Ubuntu GNOME

System power requests are independent of application-window commands. Existing
settings migrate to schema 5 with `system_power_enabled = false`. The global
action switch and the separate system-power permission must both be enabled.
No model, microphone, or desktop application allowlist is needed to use the
four on-screen request buttons. Spoken requests require an active STT session.

`SystemPowerFlow` owns one pending request with a 45-second deadline. Only a
final transcript can start or advance it. A pending request consumes unrelated
speech instead of passing it to ordinary command interpretation. The first
answer is an exact `Yes` or the Continue button. The second is the exact,
action-specific phrase shown in the UI or its matching button. Either method
may be used at either stage. Cancel, timeout, microphone-session shutdown, and
permission revocation clear the pending request. Stale button events use the
request ID and cannot confirm a newer request. KYRIN's own speech playback is
excluded from microphone input by `PlaybackGuardInput`; the flow also rejects
spoken confirmation while the configured response speaker is active.

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
stays open while the session exists. Execution is on a background thread, and
unit tests replace the adapter so no test changes machine power state.

Product validation still needs a deliberate, supervised live check on the
owner's desktop. Automated tests cover policy, timeout, mixed voice/click
confirmation, stale IDs, echo guard, UI buttons without a microphone session,
and the exact non-forced GNOME calls. The current desktop composition has no
configured TTS synthesizer; prompts are visible as text, and spoken prompt
playback is available only when a synthesizer is injected. Spoken **input**
remains available whenever the microphone/STT session is running.
