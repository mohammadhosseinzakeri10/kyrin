# Live speech pipeline

English reference. The Persian original,
LIVE_SPEECH_PIPELINE_FA.md (source repository only), is preserved unchanged
and also holds dated local observations (device-specific, not general).

- **Status:** current structure; defaults checked in
  `src/kyrin/audio/audio_backlog.py` and
  `src/kyrin/audio/live_speech_pipeline.py`. Latency, long-session stability and
  recognition quality with a real microphone and model are not established here.

## Purpose and data flow

Audio is taken from the source once and fed to two consumers: voice-activity
detection (VAD), to know whether the user is speaking or paused, and
speech-to-text (STT), for interim and final text. A pause does not end the
speech session; a separate command-understanding layer makes bounded decisions
(see [Command understanding](../commands/COMMAND_UNDERSTANDING.md)).

```text
AudioInput -> AudioCaptureQueue -> VAD worker -> SampleRateConverter -> AudioFramer -> SpeechActivityMonitor
                                      |
                                      +-> AudioBacklog -> STT worker -> SpeechToTextSession

                    activity transitions / transcript updates / backlog notices
```

A worker is a separate thread. The STT worker is separate because recognition may
take a while and must not stop microphone capture. VAD and STT each receive the
sample rate they need; STT need not consume the fixed VAD windows.

## Backlog control

`AudioBacklog` counts audio waiting for STT plus the audio being processed.
Current defaults (`warning_ms`, `recovery_ms`, `maximum_ms`; the constructor
requires `0 <= recovery < warning < maximum`):

| Threshold | Value | Behavior |
| --- | ---: | --- |
| Warning | 1000 ms | one `WAIT` event so the UI can ask the user to wait |
| Recovery | 250 ms | one `READY` event announcing speech may continue |
| Maximum | 5000 ms | explicit `AudioQueueOverflowError` |

The gap between warning and recovery prevents repeated messages. Reaching the
warning drops no audio. Past the maximum the stream stops with an error so a
command is never dropped silently. The values are initial settings to be
measured on real devices. The initial capture queue also has a separate chunk
limit (`max_capture_chunks`); abnormal VAD slowness or unconsumed events can
fill it. A caller of `LiveSpeechPipeline.open()` must read events continuously
and define user-visible behavior for audio-input and overflow errors.

## Contracts and change points

- The audio source implements `AudioInput`; a file source could take the same
  place later.
- The STT engine implements `SpeechToTextEngine`; swapping Vosk for another
  engine needs no change to the microphone path or VAD.
- `BacklogNotice` only reports state; `ResponsePresenter` builds the wait
  message (text and voice channel) and the text-only recovery message.
- `SpeechActivityFrame` is emitted only on a confirmed speech-state change;
  every window is evaluated, but not every window is sent to the UI.
- `session.finish()` is called only when the source ends naturally, never on a
  user pause; closing the path early releases the session.

To debug, first decide whether the fault came from the capture queue, the STT
buffer, rate conversion, VAD or the STT engine. `tests/audio/test_live_speech_pipeline.py`
shows small examples of each behavior.

## Diagnostic microphone tool

`scripts/audio/check_live_speech.py` defaults to a timed run of at most 120
seconds (`--seconds`, validated in the script). `--mode commands --until-stopped`
listens until `Ctrl+C`; the two duration forms are mutually exclusive. Silence
between commands does not clear the conversation session. The tool stores no
audio and, without `--execute-actions` and an explicit application mapping,
executes nothing. The device id and input rate are explicit; no device id is
hard-coded.

```bash
.venv/bin/python scripts/audio/check_live_speech.py --mode vad --device DEVICE_ID --seconds 10
```

The live path to STT needs the optional `stt-vosk` extra and a local Vosk model;
the tool downloads nothing:

```bash
.venv/bin/python scripts/audio/check_live_speech.py --mode stt --device DEVICE_ID --model-path /path/to/local/model --language fa --seconds 15
```

`--mode commands` shows the experimental command decisions. By default it only
prints; execution needs the explicit options in
[Live open-app integration](../actions/LIVE_OPEN_APP_INTEGRATION.md). For long
listening add the same model and language options with `--until-stopped`. After
`Ctrl+C` the tool closes the microphone controller, command queue, optional
voice reply and STT engine. It is not a persistent service or an installable app.

### Listening-session recovery

In `stt` and `commands` modes, `SpeechSessionController`
(`src/kyrin/runtime/speech_sessions.py`) retries recoverable audio-input,
queue-overflow and STT errors by building a fresh path: a new `MicrophoneInput`
and STT session each time; a stopped microphone instance is never reused.
Defaults are at most two retries one second apart (`--retries`,
`--retry-delay`); `--seconds` covers the whole run including retries.

The `SpeechSessionEnded` boundary reaches the consumer before the next attempt.
In `commands` mode the interim command candidate is discarded and the stream id
changes, while conversation context and a pending disambiguation question remain.
No command is executed from interim text. A capture-stop error, an STT session
that fails to close and an unavailable processing device do not trigger an
automatic retry, because resource health or the ability to run the model is
unconfirmed. Error and retry messages come from the response layer in the
current preferred language (Persian and English only); recovery was tested
without hardware.

Events print with terminal receive time. This is not a precise speech-to-text
latency measure because `AudioData` does not yet carry per-chunk capture time.

## Silence accumulation while a model is busy (L01)

In the Ubuntu composition, the chunked Whisper and Omnilingual engines run with
the explicit `idle_preroll_ms=500` option. All audio still reaches VAD; silence
between chunks is held only in a short pre-speech buffer. On a confirmed start
the buffer and the start-of-speech audio reach STT before the start marker, then
the chunk's audio follows in order until the confirmed pause. The buffer size is
rounded up to a whole VAD window, must cover start-confirmation latency
(`idle_preroll_ms` must be at least `start_confirm_ms`, default 64) and must fit
inside the STT backlog cap (checked in the constructor). After a chunk ends, long
silence does not enter the inference queue. This is neither standby nor
microphone shutdown, and creates no new audio file.

The option is off by default and should be enabled only for a chunked engine
compatible with gaps between chunks; a streaming engine still receives all audio.
The file path and model admission policy are unchanged
([Model resource policy](../app/MODEL_RESOURCE_POLICY.md)). In the managed path,
a command model may hold the STT turn until its native call ends; speech-free
silence alone should no longer fill the queue cap while waiting. This is not a
speed guarantee for continuous speech beyond processing capacity: the
five-second cap and the explicit overflow error for real backlog are kept.

An overflow error now carries the location (`capture_queue` or `stt_backlog`),
capacity, the size of the overflowing request and the unit; the L01-v2 report
copies these numbers without speech content or full error text.

## Progress tracking and generation control (L01-v3)

In addition to queue error reports, counts of capture generation, VAD window
processing and actual STT call returns are recorded. Busy-state age, ownership
and shared-resource waiting, and bounded-queue pressure are kept separate. A
steady count or UI heartbeat does not prove line health; absence of text in
silence is not an error in itself. This recording is optional, in memory only
and retains no private audio or text.

Cancelling a managed engine also cancels its wait for admission; ownership of a
running native call is kept until it really returns. The capture-ready notice and
end-of-stream carry the generation of their attempt, so a late event cannot
change the readiness of a newer generation. The runtime accepts the final segment
number once per stream, including explicit controls consumed before command
understanding. A stream boundary resets the numbers; a retry does not change the
permitted command state. Queue caps, retry budget, timeouts and silence
pre-roll are unchanged. Fake tools and tests are not a substitute for real
acceptance.

**Late explicit control.** For an explicit control, text-generation time alone is
not evidence: if a valid end-of-speech time or the start of the same STT call is
earlier than a fresh GUI request, a late output does not revert the newer state.
A valid control after the GUI still works. Before the first control request there
is no artificial time cutoff. If the producer supplies no valid time, the guard
can only consume the publication time; the age of audio inside a streaming
backend's internal buffer is not guessed. (This relates to [DR-0004](../decisions/DR-0004-guards-against-late-and-stale-results.md);
the review notes are private L01 development reports.)
