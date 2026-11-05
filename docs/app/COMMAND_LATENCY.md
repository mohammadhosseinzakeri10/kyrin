# Command latency measurement

(English migration of a previously Persian-only note; the original is
preserved in the private migration pre-images and in Git history.)

Times are recorded at the producer with an injected monotonic clock; the time
received by the Qt interface is not the measurement basis. A sample's identity
is a unique session id together with `stream_id` and `segment_id`; each step has
its own `step_index`. A late result from an earlier session or stream does not
consume a new segment with the same number.

## Recorded boundaries

- **Audio acquisition** before the capture queue. The first-sample time is
  estimated from packet arrival time and audio length; it is not hardware ADC
  time. It passes through rate conversion and framing. Speech start is the first
  speech frame of the VAD confirmation window; speech end is the end of the last
  speech frame, not the time silence was confirmed.
- **Speech-to-text.** Text finalization at the return of the STT call, the wait
  for the end-of-speech marker in the STT queue, and the duration of that final
  STT call. This duration includes adapter processing and is not pure GPU model
  time; preview inferences are excluded.
- **Command understanding.** Queue entry and start/end of understanding; real
  command-model calls are recorded separately. Durations of repeated model calls
  are summed and the gaps between them are dropped.
- **Action.** Action-queue entry, processing start, executor entry and exit for
  each step, and feedback production. In this contract, dispatch time is the
  whole executor call, including input acceptance and internal checks; it is not
  the pure time of sending input to the OS.
- **Postcondition.** Waiting at the existing application-observation and
  Telegram re-read boundaries, and the time the confirmed result was observed.
  A check inside an independent helper is visible only at the helper's reply
  boundary. Postcondition time may be a subset of dispatch time; do not add the
  two.
- **Completion.** Exit of processing for the whole command or plan, even after
  a step fails or stops. First feedback is only the time of the first step
  result and does not replace the end of the plan. End of processing alone is
  not a claim that the action succeeded or that a later interactive choice
  finished.

For a streaming backend with no definite attribution of an audio turn to a text
segment, audio start/end stays unknown; it is not guessed from the latest VAD
event. File input has no live capture time. Time of the first TTS sound is not
recorded by this measure.

## Reporting

Reports are grouped by live/file source, command or plan type, rule/model path
and test conditions. The cold/warm (`cold`/`warm`) model state must be set by the
tester or caller; the default is `unknown`, and the first command is not
necessarily cold. Use a fresh collector when the model, device or test
conditions change.

Each group and metric has its own valid sample count. Below 20 samples no
percentile is reported. The 50th and 95th percentiles use nearest rank; a more
stable estimate needs more samples. Retention is limited to 16 open commands,
256 times per command and 512 complete samples; an incomplete or overflowed
sample produces no full statistic.

The existing tool below uses an inert executor and produces JSON without speech
text, audio, images or target names. Speak each repeat after the previous
result. The test-conditions option is only a label for controlled conditions;
it does not warm or unload a model. For a cold test, cold models must be
established and verified independently before each sample; twenty consecutive
repeats must not be called "cold" merely because of this option.

```bash
.venv/bin/python scripts/commands/measure_safe_live_latency.py --samples 20 --temperature unknown
```

## Evidence limits

The deterministic tests use fake time and a fake executor and are not a device
benchmark. In the F18 correction the microphone, a live model, GNOME and real
cold/warm latency distributions were not tested.
