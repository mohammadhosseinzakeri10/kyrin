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
runs Ubuntu's local `spd-say` with the `espeak-ng` output module, the response
language, and `--wait` so playback completion is observable. It uses no network
or new Python package. The speech contract is separate from STT and can be
implemented by another offline backend later. `TEXT_ONLY` responses are never
sent to speech output.

If speech output is missing, fails, or its bounded queue is full, the text is
still shown and a diagnostic warning is printed. A successful `spd-say` exit
means the local service accepted/completed the request; whether the speaker
actually heard it requires a human listening check.
At diagnostic shutdown, queued voice gets a bounded chance to finish; if it
does not, the text remains visible and a warning reports the incomplete voice.

## Preventing self-hearing

`ResponseSpeaker` marks playback active as soon as a voice response is queued.
`PlaybackGuardInput` replaces microphone chunks captured during playback and
for a short trailing interval with silence of the same format and length.
Microphone acquisition stays open. The guard sits outside `MicrophoneInput`,
so capture, VAD, STT, command interpretation, and TTS remain separate.
Speech from the user during KYRIN's other spoken replies is also suppressed;
this diagnostic does not support interrupting its own voice (barge-in). The guard
does not provide acoustic echo cancellation for every speaker/microphone setup.

The Ubuntu desktop application now tries a temporary PipeWire WebRTC
echo-cancellation source when the default microphone is selected. PipeWire
removes output from the default speaker monitor before the audio reaches VAD
and STT. While that source is available, KYRIN keeps capturing user speech
through its own voice playback. The source exists only for the listening
session and is removed on shutdown. If PipeWire tools or the source are
unavailable, or an explicit microphone is selected, the existing playback
guard stays active. This path does not change the desktop's default devices.
Its real acoustic performance depends on the selected microphone, speaker,
room, and PipeWire routing and needs an owner speech-over-playback test.

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

The use of `--language`, `--output-module`, and `--wait` follows the upstream
[Speech Dispatcher `spd-say` manual](https://github.com/brailcom/speechd/blob/master/doc/spd-say.texi).
