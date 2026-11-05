# Offline spoken responses in the live command diagnostic

## Behavior

The command coordinator asks for a repetition only after a **final** transcript
looks like an incomplete, unrecognized, or explicitly addressed command.
Ordinary conversation, silence, and partial transcripts do not trigger a
repetition. An STT result such as `to open telegram` (a previously observed
dropped negation prefix) is treated as unclear: it cannot authorize an action
and asks the speaker to repeat. The exact negative command
`do not open telegram` remains a no-op.
This small demo interpreter cannot detect every unclear utterance or infer the
speaker's intent from arbitrary STT errors.

`ResponsePresenter` converts the response request into localized text and a
requested channel. Persian and English messages currently exist. The live
`commands` diagnostic always prints that text. Unclear-command repetition and
approximate app-name clarification use `TEXT_ONLY`, so the user can immediately
repeat or answer without waiting for a spoken prompt. For `TEXT_AND_VOICE`,
`ResponseSpeaker` also queues it for `SpeechDispatcherSynthesizer`. The backend
uses a dedicated local Unix SSIP connection to Speech Dispatcher with the
`espeak-ng` output module and response language. BEGIN/END/CANCEL notifications
track actual playback; cancellation uses `CANCEL SELF`, never a global stop.
`spd-say --list-output-modules` is used only to autospawn the existing service
when its local socket is absent. No Python dependency or remote service is added. The speech contract is separate from STT and can be
implemented by another offline backend later. `TEXT_ONLY` responses are never
sent to speech output.

If speech output is missing, fails, or its bounded queue is full, the text is
still shown and a diagnostic warning is printed. Completion notifications
report the local service's lifecycle; audible output still requires a human
listening check. If a submitted message loses its cancellation acknowledgement,
playback remains uncertain and the half-duplex microphone guard remains active.
Restore the local speech service and restart KYRIN before relying on capture;
service disconnection is not treated as proof that playback stopped.
At diagnostic shutdown, queued voice gets a bounded chance to finish; if it
does not, the text remains visible and a warning reports the incomplete voice.

## Preventing self-hearing

The playback guard follows `is_playing` plus a 350 ms echo tail. Queueing
or generating speech alone leaves the microphone active. Backends without
playback state use the conservative guard. Muting replaces frames with
silence downstream of `MicrophoneInput`, retaining frame format and timing.

The optional PipeWire echo-cancellation path binds a uniquely resolved
microphone and checks its reference-speaker links. Ambiguous aliases leave the
half-duplex route active. The path does not change global audio defaults.
Confirmed speech activity can interrupt the response from the VAD worker
before final recognition. The speech pipeline keeps ordered frames and
preserves the initial buffer for turn-based recognition. Authorization still
uses final text and the action policy.

Without echo cancellation, the UI reports half-duplex mode. **Stop spoken
response** cancels playback and queued audio independently of microphone and
action state. It discards late synthesis output. The CLI uses the
half-duplex guard. Synthetic tests exercise these paths, while native
echo cancellation and speech interruption require device acceptance.

On desktop exit, the synthesizer interrupts playback and stops an active
isolated model worker. If in-process CPU generation still holds the model lock,
shutdown waits at most two seconds for that lock. It does not close a model
while generation is using it. The response speaker then gets a one-second
join deadline and the exiting process reclaims its remaining CPU memory.
Normal model switches still retire cached models once generation finishes.
This exceptional path has a deterministic blocked-generation test; an actual
stalled hardware runtime has not been induced on the owner's machine.

For system-power confirmation, a live safe-preview test initially appeared to
advance without user speech. The follow-up diagnostic showed `[BLANK_AUDIO]`,
and the new button still said `Continue`: this was the initial checking screen
changing to the first confirmation stage, not an accepted voice reply. The
dialogue now labels these stages explicitly. The owner also heard repeated
speech in the first run; unclear power replies now display a text-only reminder
instead of creating another spoken prompt. PipeWire barge-in remains enabled.

The desktop Voice Output page now has a saved **Play spoken responses** switch.
It defaults to on for existing settings. Turning it off and applying settings
interrupts the current announcement and suppresses subsequent voice, while
visual responses and microphone command processing continue. Turning it back
on restores voice using the selected engine and language routes. The switch is
enforced by the shared `ResponseSpeaker`, including system-power prompts.
Power-stage announcements replace the previous announcement in the queue and
interrupt active local-model playback, so the next stage does not wait for the
previous stage's audio to finish. A physical listening retest is still needed.

## Running

The existing `scripts/audio/check_live_speech.py --mode commands` invocation
speaks response requests by default when `spd-say` is installed. Its speech
backend requires the local Speech Dispatcher `espeak-ng` module. Use
`--no-voice-responses` when silent diagnostics are needed. STT/VAD-only modes
remain silent. The diagnostic is a desktop-action dry run by default; explicit
`--execute-actions` and `--launch-app` bindings enable limited app launch.
It never saves microphone audio. A later application UI can consume the same `PresentedResponse` and
`SpeechSynthesizer` contracts without reusing this diagnostic script.

Only Persian and English response catalogs are present. The installed
`espeak-ng` module exposes both on the development machine, but voice quality
and device output depend on local configuration. Windows, macOS, and mobile
speech adapters remain future platform work. This is an offline voice
prototype, not a packaged cross-platform TTS installation.

The local speech lifecycle follows the upstream
[SSIP protocol](https://github.com/brailcom/speechd/blob/master/doc/ssip.texi).
AEC configuration follows the official [Echo Cancel module](https://docs.pipewire.org/page_module_echo_cancel.html),
[stream target properties](https://docs.pipewire.org/page_man_pipewire-props_7.html)
and [ALSA identity keys](https://docs.pipewire.org/group__spa__keys.html).

Model admission and residency follow the [shared resource policy](../app/MODEL_RESOURCE_POLICY.md).
The application keeps device selection and capability checks separate. Native
latency and memory behavior still require measurement.
