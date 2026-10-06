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
`commands` diagnostic always prints that text. For `TEXT_AND_VOICE`,
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
Speech from the user during KYRIN's spoken reply is also suppressed; this
diagnostic does not support interrupting its own voice (barge-in). The guard
does not provide acoustic echo cancellation for every speaker/microphone setup.

## Running

The existing `scripts/audio/check_live_speech.py --mode commands` invocation
speaks response requests by default when `spd-say` is installed. Its speech
backend requires the local Speech Dispatcher `espeak-ng` module. Use
`--no-voice-responses` when silent diagnostics are needed. STT/VAD-only modes
remain silent, and the tool never executes desktop actions or saves microphone
audio. A later application UI can consume the same `PresentedResponse` and
`SpeechSynthesizer` contracts without reusing this diagnostic script.

Only Persian and English response catalogs are present. The installed
`espeak-ng` module exposes both on the development machine, but voice quality
and device output depend on local configuration. Windows, macOS, and mobile
speech adapters remain future platform work. This is an offline voice
prototype, not a packaged cross-platform TTS installation.

The use of `--language`, `--output-module`, and `--wait` follows the upstream
[Speech Dispatcher `spd-say` manual](https://github.com/brailcom/speechd/blob/master/doc/spd-say.texi).
