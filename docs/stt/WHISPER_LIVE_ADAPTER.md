# Local Whisper live adapter

## Decision and scope

The owner chose the existing multilingual Whisper `small` weights for the next
English STT development step. On five local English clips this candidate
recognized command words better than the installed Vosk English candidate,
but those clips are from one speaker. Vosk remains available. This change does
not add an automatic product default, installer, GPU backend, or downloader.

## Data flow

For a turn-aware backend, `LiveSpeechPipeline` converts captured audio to the
VAD's 16 kHz PCM format, classifies each frame, and queues the **same** frames
for STT. Confirmed `STARTED` and `PAUSED` markers follow their corresponding
frames in that queue. A pause seals one transcript segment, not the listening
session or conversation. Existing streaming engines such as Vosk retain their
independent source-to-STT conversion path.

`WhisperSession` retains 0.5 seconds before speech starts. During a turn, it
requests a preview after 1.5 seconds of confirmed speech (excluding the
pre-roll) and then no more frequently than every
2.5 seconds. Previews use at most the last 8 seconds and have `PARTIAL` status.
After a confirmed pause, the complete bounded turn is transcribed as `FINAL`.
Final text can correct a preview; only final text may reach the action gate.
A turn longer than 30 seconds ends with empty final text, retracting any
preview instead of executing a truncated command. These timings are settings,
not measured latency guarantees.

`WhisperCppServer` starts one local `whisper-server` process, preloads the
configured model, binds only to `127.0.0.1`, and sends WAV windows over
loopback HTTP with proxy routing disabled. It times out requests, closes with
the engine, and writes no transcript or audio to disk. Its process output is
discarded to avoid an ever-growing log. Paths and CPU thread count are
explicit; nothing is downloaded.

## Local construction

```python
from kyrin.stt.backends.whisper import WhisperEngine

engine = WhisperEngine(
    "build/tools/whisper.cpp-v1.9.4/build-cpu/bin/whisper-server",
    "models/local/whisper.cpp/ggml-small.bin",
    language="en",
    threads=4,
)
try:
    # Supply engine to the existing LiveSpeechPipeline.
    ...
finally:
    engine.close()
```

These paths are Git-ignored development assets. A packaged app will need
deployment configuration for both. The adapter currently supports CPU only;
an explicit GPU request fails. Its language tag is configured English, not
automatic language detection.

The existing microphone diagnostic can select this backend explicitly. It
prints transcripts and dry-run decisions, never executes a desktop command:

```bash
PYTHONPATH=src .venv/bin/python scripts/audio/check_live_speech.py \
  --mode commands --stt-backend whisper --language en \
  --model-path models/local/whisper.cpp/ggml-small.bin \
  --whisper-server build/tools/whisper.cpp-v1.9.4/build-cpu/bin/whisper-server \
  --seconds 20
```

The diagnostic keeps its previous Vosk default for existing invocations;
this flag does not select a packaged application default.

## Validation and limits

Focused deterministic tests cover boundary order, repeated turns, partial
replacement, overlong-turn retraction, device requests, and cleanup. On the
existing `en-02.wav`, the real local server returned an incorrect preview
(`Open Telephone.`) and a correct final transcript (`Open Telegram.`). A
recorded-speed run through actual Silero VAD and `LiveSpeechPipeline` emitted
`PARTIAL Open Telegram` and `FINAL Open Telegram`. These runs used a file
source, not a microphone, and executed no desktop action. The first run took
about 3.9 seconds of processing after model startup. Responsiveness on other
hardware remains unknown. The bounded backlog still reports wait or fails
visibly if CPU inference cannot keep up; it does not silently discard audio.

## First real microphone dry run

On 2026-10-05 the owner read `Open Telegram.` and, after a pause,
`Do not open Telegram.` to the USB microphone (48 kHz source). The diagnostic
saved no audio and executed no desktop action. The first utterance produced
`FINAL Open Telegram.` about 3.5 seconds after the VAD pause and an authorized
**dry-run** request. The second produced `FINAL to open telegram.` about 3.5
seconds after its pause. The owner confirmed that they spoke the negative
sentence exactly. The interpreter did not authorize the second utterance, so
the missing `not` did not cause an action. Both turns raised a backlog wait
notice near 1024 ms and later recovered without overflow.

For isolation, the existing confirmed `en-03.wav` negative sentence was also
replayed at recorded speed through the same VAD, live pipeline, and local
Whisper server. It produced `PARTIAL Do not open.` and
`FINAL Do not open telegram.` This shows the pipeline can preserve negation in
one recorded example. The cause of the live microphone error is unresolved:
the dry run deliberately did not save the microphone waveform, so its onset,
level, and pronunciation cannot be inspected afterward.

The owner then explicitly consented to one 15-second local WAV containing only
the negative sentence. It is saved at the ignored path
`datasets/stt/recordings/raw/live-negation-2026-10-05.wav`. Silero detected
one speech interval, about 8.29–10.37 seconds from file start. Recorded-speed
replay of this file through the full live path produced
`FINAL Do not open telegram.` The earlier microphone failure therefore did not
reproduce on the newly captured utterance; its exact cause remains unknown.

Review of the scheduler found that pre-roll audio had counted toward the
first-preview threshold. It now counts 1.5 seconds **after** confirmed speech
start, so a short command is less likely to start a redundant preview just
before its final transcription. Deterministic tests cover this rule. In one
recorded-speed replay of `en-02.wav` after the change, VAD paused at 2.41 s
and the correct final text arrived at 4.33 s, about 1.92 s later. This is a
single local file run, not a microphone latency guarantee. Product use must
retain final-only action gating and visible recovery/clarification.
