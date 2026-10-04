# KYRIN — Project Context

> Engineering handoff for the current repository state.
> Updated: 2026-10-05.
>
> This document records confirmed implementation state, engineering decisions,
> current direction, experiments, and open questions. The repository remains
> the source of truth when this document and the code disagree.

## Status Vocabulary

- **CONFIRMED** — implemented, tested, directly observed, or explicitly decided.
- **CURRENT DIRECTION** — the next agreed engineering direction; implementation
  may not have started yet.
- **TEMPORARY / EXPERIMENTAL** — local hardware or development observations that
  must not be treated as portable product behavior.
- **PROPOSAL / IDEA** — discussed but not committed.
- **OPEN** — unresolved and requiring a future engineering decision.

---

## 1. Project Overview

- **Name:** KYRIN.
- **Package name:** `kyrin`.
- **Project version:** `0.1.0`.
- **Product status:** early development.
- **Current major engineering area:** V1 voice/audio pipeline.
- **Current completed foundation:** audio capture, core PCM data model,
  streaming mono INT16 sample-rate conversion, configurable audio framing,
  an offline VAD adapter, continuous speech-activity monitoring, replaceable
  STT contracts, and a bounded live VAD/STT pipeline.
- **Current next direction:** validate the GNOME active-app prototype with real
  windows and design localized response presentation before
  connecting live voice commands to the action executor. A GNOME 50 prototype
  now exists but needs validation with real foreground windows. Windows, macOS,
  and Android adapters remain future work.
  Device-specific stop behavior and multilingual STT quality still require
  separate evaluation.

KYRIN is an open-source modular AI Desktop Agent. The high-level product vision
is to understand voice, vision, and text and interact naturally with the
operating system.

---

## 2. Current Audio Architecture

The implemented components can be composed as follows:

```text
Microphone
    ↓
MicrophoneInput
    ↓
AudioCaptureQueue (dedicated capture thread, bounded queue)
    ↓
AudioData
    ↓
SampleRateConverter (mono INT16 sample-rate conversion)
    ↓
AudioFramer (configurable processing windows)
    ↓
VoiceActivityDetector / SileroVad (offline, 16 kHz mono INT16)
    ↓
SpeechActivityMonitor (continuous audio and stable activity transitions)
```

`ContinuousAudioPipeline` composes the components above for one stream.

The implemented live STT composition is:

```text
Microphone
    ↓
MicrophoneInput
    ↓
AudioCaptureQueue
    ├──→ AudioBacklog → STT worker → SpeechToTextSession
    └──→ SampleRateConverter → AudioFramer → VoiceActivityDetector
                                           ↓
                                  SpeechActivityMonitor

Both branches → live events → command decision layer (implemented, dry-run)
```

`SampleRateConverter` and `AudioFramer` are separate downstream components.
The capture-to-activity pipeline, replaceable STT contract, optional Vosk
adapter, and backend-independent live VAD/STT composition exist. The desktop
application has not yet been wired to run them. A separate command coordinator
now accepts transcript updates. A separate Linux app launcher exists, but is
not yet wired to the live microphone diagnostic or application runtime.
A downstream engine that accepts variable-size chunks may bypass `AudioFramer`.

### Architectural boundary

`MicrophoneInput` is only responsible for audio acquisition.

It must not contain:

- STT logic
- VAD logic
- intent understanding
- agent decision-making
- desktop automation
- unrelated application logic

Downstream audio processing must remain separate from microphone acquisition.

---

## 3. Implemented Core Components

### `AudioSampleFormat`

Location:

```text
src/kyrin/audio/audio_format.py
```

Implemented values:

```text
INT16
FLOAT32
```

Current byte sizes:

```text
INT16   -> 2 bytes per sample
FLOAT32 -> 4 bytes per sample
```

`AudioSampleFormat` is implemented as a `StrEnum`.

**Status:** CONFIRMED.

---

### `AudioFormat`

Location:

```text
src/kyrin/audio/audio_format.py
```

Current shape:

```python
@dataclass(frozen=True)
class AudioFormat:
    sample_rate: int
    channels: int
    sample_format: AudioSampleFormat
```

Responsibilities:

- describe how PCM bytes must be interpreted
- store sample rate
- store channel count
- store sample representation
- calculate `bytes_per_frame`
- reject invalid non-positive sample rates
- reject invalid non-positive channel counts

`AudioFormat` is immutable.

`frames_per_chunk` does not belong to `AudioFormat`; it is streaming
configuration rather than an intrinsic property of the audio representation.

**Status:** CONFIRMED.

---

## 4. PCM Terminology

### Sample

A sample is one numeric audio measurement for one channel.

### Sample rate

The number of PCM sample frames per second.

Example:

```text
16000 Hz
```

means:

```text
16000 sample frames per second
```

### PCM sample frame

A PCM sample frame contains one sample for every channel at one instant.

Examples:

```text
mono   -> 1 sample per PCM frame
stereo -> 2 samples per PCM frame
```

### Bytes per PCM frame

The current formula is:

```text
bytes_per_frame =
    channels × bytes_per_sample
```

Example:

```text
stereo INT16

2 channels × 2 bytes
= 4 bytes per PCM frame
```

### Chunk

A chunk is a group of PCM sample frames read or processed together.

A microphone chunk size is not automatically the same as a VAD or
processing window size.

### Processing window

A framing/VAD window can be a time-based block such as:

```text
10 ms
20 ms
30 ms
```

A processing window contains many PCM sample frames.

The term "frame" can be ambiguous in audio systems, so this project should
distinguish:

```text
PCM sample frame
processing/VAD window
```

when the distinction matters.

---

## 5. `AudioData`

Location:

```text
src/kyrin/audio/audio_data.py
```

Current shape:

```python
@dataclass(frozen=True)
class AudioData:
    data: bytes
    audio_format: AudioFormat
```

`AudioData` uses composition:

```text
AudioData has an AudioFormat
```

Responsibilities:

- carry immutable raw PCM bytes
- carry the exact format needed to interpret those bytes
- reject byte sequences that do not contain complete PCM sample frames

Current alignment invariant:

```text
len(data) % audio_format.bytes_per_frame == 0
```

This guarantees that an `AudioData` instance cannot end in the middle of a PCM
sample frame.

`AudioData` is source-independent. It is not tied specifically to microphone
capture.

**Status:** CONFIRMED.

---

## 6. `AudioInput`

Location:

```text
src/kyrin/audio/audio_input.py
```

Current contract:

```python
class AudioInput(Protocol):
    def capture(self) -> Iterator[AudioData]: ...
```

The protocol defines the behavior of an audio source without requiring callers
to depend on a concrete hardware implementation.

This supports structural typing and loose coupling between audio consumers and
audio sources.

**Status:** CONFIRMED.

---

## 7. `MicrophoneInput`

Location:

```text
src/kyrin/audio/microphone/input.py
```

Constructor configuration:

```text
device
audio_format
frames_per_chunk
```

Responsibilities:

- retain microphone configuration
- validate `frames_per_chunk`
- open `sounddevice.RawInputStream` inside `capture()`
- read microphone chunks
- convert the library-provided buffer to independent `bytes`
- construct `AudioData`
- yield `AudioData` continuously
- detect microphone overflow
- translate `sounddevice.PortAudioError` into project-level errors
- release the stream through context-manager semantics

Current invariant:

```text
frames_per_chunk > 0
```

Hardware is intentionally not acquired inside `__init__`.

The current flow inside `capture()` is conceptually:

```text
open RawInputStream
    ↓
read frames
    ↓
check overflow
    ↓
convert buffer to bytes
    ↓
construct AudioData
    ↓
yield
    ↓
repeat
```

**Status:** CONFIRMED.

---

## 8. Audio Error Hierarchy

Location:

```text
src/kyrin/audio/audio_errors.py
src/kyrin/audio/microphone/errors.py
```

Current hierarchy:

```text
AudioError
    ↓
MicrophoneError
    ↓
MicrophoneOverflowError
```

`AudioError` and capture-queue errors live in the shared audio package.
`MicrophoneError` and `MicrophoneOverflowError` live with the microphone source.
`MicrophoneError` acts as the project-level boundary for microphone-related
failures.

PortAudio-specific failures are translated rather than leaked directly as the
main application-facing exception type.

Exception chaining is preserved for translated `PortAudioError` failures.

**Status:** CONFIRMED.

---

## 9. Testing State

Current automated test areas include:

- package import
- `AudioFormat`
- `AudioSampleFormat`
- `AudioData`
- audio error hierarchy
- `MicrophoneInput`
- `SampleRateConverter`
- `AudioFramer`
- `AudioCaptureQueue`
- `ContinuousAudioPipeline`
- `SileroVad`
- `SpeechActivityMonitor`
- replaceable STT contract and transcript/device value types
- optional Vosk adapter behavior and lifecycle

Current behaviors covered include:

- `AudioFormat` value storage
- `AudioFormat` immutability
- value-based equality
- zero sample-rate rejection
- negative sample-rate rejection
- zero-channel rejection
- negative-channel rejection
- sample-format string values
- bytes-per-sample calculation
- bytes-per-frame calculation
- `AudioData` value storage
- `AudioData` immutability
- misaligned PCM data rejection
- microphone `AudioData` production
- microphone stream configuration
- overflow handling
- multiple chunk production
- PortAudio stream-open error translation
- PortAudio read error translation
- zero `frames_per_chunk` rejection
- negative `frames_per_chunk` rejection
- package import
- streaming resampling duration across input rates and chunk boundaries
- removal of frequencies above the output Nyquist limit
- output before the input stream ends
- identity conversion, empty input, and unsupported-format errors
- audio framing across arbitrary chunk boundaries without losing PCM data
- full windows during streaming and an unpadded remainder at natural end
- independent framing calls, format checking, and converter/framer composition
- bounded capture, source-failure propagation, and stop behavior
- continuous capture-to-activity composition
- offline Silero VAD inference and speech-activity transitions

Latest observed full quality gate:

```text
ruff check src tests scripts
→ All checks passed!

mypy src tests
→ Success: no issues found in 36 source files

pytest -q
→ 90 passed (full suite requires access to the system audio service)
```

**Status:** CONFIRMED.

---

## 10. Test Doubles

`tests/audio/microphone/test_input.py` uses fake `RawInputStream` implementations to
test microphone behavior without requiring real hardware.

Current fake behaviors cover:

- normal capture
- overflow
- multiple chunks
- stream-open failure
- read failure

Some fake state is currently stored using class variables.

This is accepted for the current test suite but may be refactored later for
stronger test isolation.

**Status:** known non-blocking technical debt.

---

## 11. Hardware Validation Scripts

Hardware-dependent checks are intentionally separated from deterministic unit
tests.

Current scripts:

```text
scripts/audio/microphone/check_audio_rates.py
scripts/audio/microphone/check_microphone_stream.py
scripts/audio/check_live_speech.py
```

### `check_audio_rates.py`

Used to manually test selected device/sample-rate combinations using
`sounddevice.check_input_settings()`.

The currently encoded device IDs are local development values and must not be
treated as portable application defaults.

### `check_microphone_stream.py`

Used for a minimal real `RawInputStream` capture experiment.

Current example configuration is local development configuration and is not a
portable product default.

**Status:** CONFIRMED development utilities.

---

## 12. Observed Hardware Environment

Local hardware experiments established that audio-device support depends on the
full combination of:

```text
device
sample rate
channels
sample format
```

A reported default sample rate must not be treated as proof that every complete
configuration is supported.

Observed development findings include:

- device 4 rejected one tested 32 kHz configuration
- device 4 successfully captured at 48 kHz, mono, INT16
- device 5 accepted selected 44.1 kHz and 48 kHz configurations

These findings are machine-specific.

**Status:** TEMPORARY / EXPERIMENTAL.

---

## 13. Package and Tooling

Project configuration is stored in:

```text
pyproject.toml
```

Current baseline:

```text
Python >= 3.14
setuptools src layout
```

Runtime dependencies:

```text
numpy >= 2.0
onnxruntime >= 1.30, < 2
soxr >= 1.1.0
sounddevice >= 0.5.6
```

Development tools:

```text
coverage >= 7.0
mypy >= 2.0
pytest >= 9.0
ruff >= 0.16
```

Ruff target:

```text
py314
```

Mypy configuration:

```text
python_version = 3.14
strict = true
```

Pytest test root:

```text
tests
```

Coverage source:

```text
kyrin
```

**Status:** CONFIRMED.

---

## 14. Current Repository Structure

Relevant current files:

```text
KYRIN/
├── README.md
├── LICENSE
├── pyproject.toml
├── AGENTS.md
├── PROJECT_CONTEXT.md
├── scripts/
│   └── audio/
│       └── microphone/
│           ├── check_audio_rates.py
│           └── check_microphone_stream.py
├── src/
│   └── kyrin/
│       ├── __init__.py
│       ├── audio/
│       │   ├── audio_data.py
│       │   ├── audio_errors.py
│       │   ├── audio_framer.py
│       │   ├── audio_format.py
│       │   ├── audio_input.py
│       │   ├── audio_capture_queue.py
│       │   ├── continuous_audio_pipeline.py
│       │   ├── sample_rate_converter.py
│       │   ├── activity/
│       │   │   ├── voice_activity_detector.py
│       │   │   ├── silero_vad.py
│       │   │   ├── speech_activity_monitor.py
│       │   │   └── models/
│       │   │       └── silero_vad.onnx
│       │   └── microphone/
│       │       ├── input.py
│       │       └── errors.py
│       └── stt/
│           ├── capabilities.py
│           ├── contracts.py
│           ├── device.py
│           ├── errors.py
│           └── transcript.py
└── tests/
    ├── test_package.py
    ├── audio/
    │   ├── test_audio_data.py
    │   ├── test_audio_framer.py
    │   ├── test_audio_format.py
    │   ├── test_sample_rate_converter.py
    │   ├── activity/
    │   │   ├── test_silero_vad.py
    │   │   └── test_speech_activity_monitor.py
    │   └── microphone/
    │       ├── test_input.py
    │       └── test_errors.py
    └── stt/
        └── test_contracts.py
```

The tree lists representative files. Shared audio contracts and processing
remain in `kyrin.audio`. Microphone-specific acquisition and errors live in
`kyrin.audio.microphone`; VAD, speech-activity monitoring, and the bundled
Silero model live in `kyrin.audio.activity`. This leaves room for a future
file-based source without tying processing to the microphone. STT contracts
are isolated in `kyrin.stt`; no backend library is imported there.

---

## 15. Major Confirmed Design Decisions

### Separate contract from implementation

```text
AudioInput
```

is the abstraction.

```text
MicrophoneInput
```

is the concrete microphone implementation.

**Reason:** loose coupling and testability.

---

### Acquire hardware during capture

`MicrophoneInput.__init__` stores configuration only.

The audio device is acquired inside:

```text
capture()
```

**Reason:** cleaner resource lifetime and easier testing.

---

### Use streaming generators

`capture()` returns:

```text
Iterator[AudioData]
```

and uses `yield`.

**Reason:** audio must be processed incrementally rather than accumulated in
memory.

---

### Convert external buffers to `bytes`

The temporary buffer received from `sounddevice` is converted to independent:

```text
bytes
```

before entering the project data model.

**Reason:** avoid coupling domain objects to temporary external-library memory.

---

### Represent audio format explicitly

Sample rate, channel count, and sample representation are grouped into:

```text
AudioFormat
```

instead of being scattered independently.

**Reason:** they form one logical description of PCM interpretation.

---

### Keep streaming configuration separate from audio format

```text
frames_per_chunk
```

remains outside `AudioFormat`.

**Reason:** chunk size controls streaming behavior, not how individual PCM bytes
are interpreted.

---

### Require complete PCM sample frames

`AudioData` rejects byte lengths that are not divisible by:

```text
audio_format.bytes_per_frame
```

**Reason:** downstream processing can rely on structurally valid PCM input.

---

### Keep hardware configuration portable

Machine-specific device IDs must not become hard-coded application defaults.

**Reason:** device numbering and capabilities differ between machines and
operating systems.

---

## 16. Implemented Sample-Rate Conversion

`SampleRateConverter` is located in `src/kyrin/audio/sample_rate_converter.py`.
It accepts an explicit `AudioFormat` and target sample rate, then converts an
iterable of `AudioData` chunks. Each `convert()` call has independent streaming
state. The converter yields nonempty output as it becomes available and flushes
the filter when the iterable ends. Output chunk sizes can differ from input
chunk sizes. No fixed target rate is built into the component.

The current supported input and output representation is mono INT16 PCM.
Changing the sample rate is implemented; changing channel count or sample
representation is not. Unsupported formats and midstream format changes raise
`ValueError`. Equal rates pass through without resampling. Empty input yields
no output.

NumPy interprets the PCM bytes as numeric samples; `soxr.ResampleStream` does
the stateful conversion with MQ quality and anti-alias filtering. A local trial
with `samplerate` lost output frames when the same one-second signal was fed in
small chunks; this was the reason to choose `soxr` for this implementation.
The installed `soxr` package declares LGPL-2.1-or-later licensing. Distribution
packaging and license obligations still need review before a release. This
environment verified Linux only; Windows and macOS packaging remain untested.

`MicrophoneInput` has not been modified or wired to the converter yet.
Downstream framing can consume the converter's `AudioData` iterator.

**Status:** CONFIRMED for the implemented mono INT16 path. Other conversion
dimensions remain OPEN until a consumer requires them.

---

## 17. Implemented Audio Framing

`AudioFramer` is located in `src/kyrin/audio/audio_framer.py`. It accepts an explicit
`AudioFormat` and a positive `frames_per_window` count. The caller chooses this
count to match a downstream engine; no duration or VAD-specific setting is
hard-coded. It works with any currently represented PCM channel count and
sample format because it only groups bytes along PCM frame boundaries.

`frame()` accepts an iterable of `AudioData` chunks and creates independent
buffer state for each call. It yields complete windows as soon as enough audio
arrives, even if the source continues indefinitely. At natural stream end, it
yields any remaining PCM data as a single shorter, unpadded `AudioData` item.
Consumers can identify that final item by its length and decide how to handle
it. The framer never invents silence or discards input data. Empty chunks are
ignored; midstream format changes raise `ValueError`.

The buffer holds at most one incomplete window between input chunks. Larger
incoming chunks are sliced directly into windows rather than first being copied
into the buffer. No new runtime dependency was needed. Framing is optional for
consumers that can use variable-size audio chunks.

**Status:** CONFIRMED for the implemented behavior. Required window sizes for
specific downstream engines remain OPEN.

---

## 18. VAD and Turn Detection

`VoiceActivityDetector` is a small streaming contract: required `input_format`,
`frames_per_window`, `detect(window) -> bool`, and `reset()`. Consumers can use
another engine without importing Silero. A detector instance belongs to one
audio stream. `reset()` clears engine state when a genuinely new stream starts;
pauses in a continuing conversation do not reset it.

`SileroVad` implements that contract with a bundled Silero VAD 6.2.3 ONNX
model. ONNX Runtime performs local CPU inference. No Torch installation or
runtime model download is needed. Input must be complete 512-sample windows
of mono 16 kHz INT16 PCM; the adapter normalizes samples to float32 and keeps
the model's recurrent state and 64-sample context between windows. Threshold
defaults to 0.5 and is configurable. The model and upstream MIT license are
packaged under `src/kyrin/audio/activity/models/`.

KYRIN sets `ORT_DISABLE_TELEMETRY=1` before importing ONNX Runtime through
this adapter. The official ONNX Runtime package may initialize telemetry at
import time, so calling its disable API only after import is insufficient for
the project's offline requirement. This setting affects the process; other
code must not import ONNX Runtime earlier if this guarantee is required.

`SpeechActivityMonitor` composes any `VoiceActivityDetector` and returns one
`SpeechActivityFrame` per input window, without reading ahead or withholding
audio. Each result contains the original audio, raw VAD decision, stable
`LISTENING`/`SPEAKING` state, and an optional `STARTED`/`PAUSED` transition.
The default confirmation intervals are 64 ms of speech and 384 ms of silence;
they are configurable in milliseconds and are provisional until validated on
real speech. The monitor never treats a pause as the end of the conversation.
Its `reset()` starts a new audio stream and resets detector state, not
conversation memory.

The final partial window emitted by `AudioFramer` is forwarded with an unknown
speech decision. It is not passed to a VAD that requires complete windows and
does not count as silence. Another window after that partial requires an
explicit stream reset. The monitor does not transcribe audio, decide whether
a command is complete, or execute actions.

The new command coordinator interprets streaming transcript updates and emits
replaceable candidates plus final resolutions. It does not execute actions.
A pause is an activity signal, not a mandatory command boundary.

The current high-level composition is:

```text
Audio capture ──→ VAD / SpeechActivityMonitor ──→ activity events
       └───────→ streaming STT ────────────────→ TranscriptUpdate
                                                   ↓
                                          CommandCoordinator
                                                   ↓
                                   candidate / resolution / response request
```

Silence or absence of speech must eventually be treated as a normal listening
state rather than as an exceptional failure.

STT selection and desktop application integration remain open.

---

## 19. Open Questions

The following engineering decisions are still open:

- What exact normalized audio format should downstream V1 processing use?
- Will downstream consumers require sample representation or channel conversion?
- What distribution steps will be required for the `soxr` license?
- What exact framing-window durations will downstream consumers require?
- Which reversible commands, if any, may execute from a provisional partial
  candidate, and how should a later correction be reconciled?
- Which STT engine will be used?
- What retry/recovery behavior should occur after microphone device failure?
- How will default microphone selection work across operating systems?

These questions must not be silently decided without investigation or an
explicit project decision.

---

## 20. Known Risks and Constraints

- Audio device IDs are machine-specific.
- Supported audio configurations vary by hardware and OS.
- Streaming chunk boundaries are not semantic speech boundaries.
- Streaming chunk boundaries are not necessarily future processing-window
  boundaries.
- Resampling cannot safely be implemented as naive sample deletion without
  considering aliasing.
- Real-time processing may require state to persist across chunks.
- Queues can introduce latency and backpressure problems if introduced without
  a clear ownership model.
- External audio-processing dependencies should not be added without first
  evaluating why they are required.

---

## 21. Development Workflow

The user is learning while building KYRIN.

Preferred workflow:

1. Explain the new concept from first principles.
2. Use a small example outside KYRIN when useful.
3. Give a small exercise when a concept is new.
4. Review the answer.
5. Connect the concept to KYRIN.
6. Design the component boundary.
7. Use TDD for behavioral changes.
8. Run focused tests.
9. Run the full quality gate.

When a complete file replacement is requested, provide the entire final file
rather than partial fragments.

---

## 22. Current Project State

### Completed

```text
AudioSampleFormat
AudioFormat
AudioData
AudioInput
MicrophoneInput
SampleRateConverter (mono INT16 sample-rate conversion)
AudioFramer (configurable audio framing)
VoiceActivityDetector (replaceable VAD contract)
SileroVad (bundled offline ONNX model)
SpeechActivityMonitor (continuous, smoothed VAD observations)
AudioCaptureQueue (bounded capture worker and explicit overflow error)
ContinuousAudioPipeline (capture-to-activity composition)
SpeechToTextEngine / SpeechToTextSession (replaceable STT contracts)
TranscriptUpdate and CPU/GPU device preferences
VoskEngine / VoskSession (optional CPU-only experimental STT adapter)
AudioBacklog (duration-bounded pending STT audio and wait/ready notices)
LiveSpeechPipeline (one capture, independent VAD/STT workers)
CommandInterpreter / CommandCoordinator (dry-run command decisions)
DemoCommandInterpreter (limited example phrases, not a product NLP engine)
ActionPolicy / ActionGate (final-only, allowlisted requests and result tracking)
ActionExecutor / LinuxDesktopEntryExecutor (separate, limited OPEN_APP launcher)
ContextResolver / CommandContext (dialogue history versus fresh active-app state)
Audio error hierarchy
hardware diagnostic scripts
unit-test foundation
```

Latest focused quality checks for the command and action-gate changes:

```text
Ruff   -> passing
Mypy   -> passing
Pytest -> 61 focused action/command/STT/live-pipeline tests passing
```

The earlier full-suite result was 90 passing tests. A new full-suite attempt
in the current isolated environment did not complete collection because
PortAudio could not connect to PulseAudio. This does not validate or invalidate
the hardware-dependent tests; they need a normal audio environment.

### Current next step

Evaluate before wiring the OS executor into the live application:

```text
Validate the GNOME active-app prototype with real foreground windows and
design a localized response presenter; keep live voice action execution
disabled until the app state and feedback can be handled honestly
```

The standalone Vosk adapter works with a locally supplied model. The live
pipeline accepts any engine implementing the STT contract, including Vosk;
it is not yet selected as the production default.
Selection still requires measured multilingual accuracy, command-relevant
partial-result latency, CPU/GPU use, and offline packaging. The first semantic
command layer exists as a dry-run contract and coordinator; its demo interpreter
recognizes only a few example phrases and is not a production language engine.
Additional audio-format conversions should be implemented only when a
downstream requirement is known.

### Current blocker

No known blocker prevents evaluating offline STT engines. Short real
microphone runs produced partial and final transcripts through the live
pipeline; a repeated short Persian sentence matched the user's reference
closely, but this is not a representative accuracy benchmark. A direct ALSA
input device failed to stop cleanly; the corresponding PulseAudio source
stopped successfully. Long-running stability, precise end-to-end latency,
recovery after device failure, and packaging on other operating systems
remain to be validated.

---

## 23. Handoff Instructions for Future AI Assistants

1. Inspect the actual repository before making architectural claims.
2. Read this document before planning major project changes.
3. Treat repository code and observed test output as stronger evidence than
   stale documentation.
4. Preserve the `AudioInput` / `MicrophoneInput` separation.
5. Keep microphone acquisition separate from downstream processing.
6. Preserve `AudioFormat` as the PCM format value object unless a documented
   requirement justifies changing it.
7. Preserve `AudioData` frame-alignment guarantees.
8. Do not assume microphone chunk boundaries equal downstream processing
   windows.
9. Do not jump directly from microphone capture to STT without reconsidering
   format conversion, framing, VAD, and turn detection.
10. Do not add a new audio-processing dependency without explaining and
    evaluating it first.
11. Treat local hardware IDs and sample-rate observations as experimental, not
    portable defaults.
12. Update this document whenever a significant architectural or behavioral
    milestone makes it inaccurate.

---

## 24. Source and Confidence Notes

This document combines:

- the current verified repository state
- observed local test output from the current development session
- confirmed engineering decisions from the KYRIN development conversation
- explicitly stated current architectural direction

It intentionally distinguishes implemented behavior from future design.

When this document becomes inconsistent with the repository:

```text
inspect repository
    ↓
identify newer evidence
    ↓
verify with tests where possible
    ↓
update PROJECT_CONTEXT.md
```

Do not preserve stale documentation merely for historical consistency.

---

## 25. Continuous Capture and Processing Pipeline

`AudioInput` now includes `stop_capture()`, which may be called from another
thread. `MicrophoneInput.stop_capture()` sets a stop signal and aborts an active
blocking `RawInputStream.read()`. A stopped `MicrophoneInput` is one-use; create
a new instance for a restarted capture session. Its hardware stream remains
owned by the capture thread and is never opened in `__init__`.

`AudioCaptureQueue` runs `capture()` on a dedicated worker thread and transfers
chunks to one consumer through a bounded standard-library queue. Its default
capacity is eight source chunks, not eight VAD windows; the actual buffered
duration depends on the source's chunk size. When the queue fills, the worker
records `AudioQueueOverflowError` and the consumer receives that failure.
Capture or source errors also propagate to the consumer. The class is used as
a context manager: leaving it requests source stop and joins the worker. A
worker that cannot stop within the configured timeout produces
`AudioCaptureStopError`; this condition requires application-level handling.

`ContinuousAudioPipeline` composes capture queue, `SampleRateConverter`,
`AudioFramer`, and `SpeechActivityMonitor` for one active stream. The caller
must consume its `open()` iterator inside the context manager; exiting that
context stops capture even if the consumer exits early. The current conversion
path requires mono INT16 input and a mono INT16 detector format. Unsupported
formats fail explicitly. The pipeline does not transcribe speech, run actions,
or clear conversation memory. No new runtime dependency was introduced.

The application is not yet wired to instantiate this pipeline or supervise
restarts. Tests use deterministic fake audio sources and a mocked microphone
stream. Queue capacity, real microphone latency, and recovery behavior still
need validation on target systems. A bounded queue protects short processing
bursts but cannot fix sustained processing slower than audio arrival.

---

## 26. Replaceable Speech-to-Text Contract

The core `kyrin.stt` modules contain backend-independent contracts and value
types. An optional concrete adapter lives under `kyrin.stt.backends`. No model
weights, runtime download, or microphone logic have been added to STT.

`SpeechToTextEngine.capabilities` reports the configured model's supported
devices, known languages (if enumerable), partial-update support, and
automatic language-detection support. Declared GPU support does not guarantee
that a usable GPU exists on the current machine. Language coverage does not
guarantee accuracy, and an unknown language list never means all languages.

`SpeechToTextEngine.open_session(options)` creates one
`SpeechToTextSession` for one ordered audio stream. The session declares its
required `AudioFormat`, its actual CPU or GPU device, and whether it can emit
partial updates. It accepts `AudioData` chunks, returns newly available
`TranscriptUpdate` values, flushes pending results through `finish()` when the
stream truly ends, and releases session resources through `close()`. The engine
also has `close()` for its loaded model. Pauses within a continuing stream do
not call `finish()` and do not clear conversation memory.

Each transcript update carries a segment ID, text, `PARTIAL` or `FINAL`
status, and an optional language. A later update for the same segment may
replace partial text. `FINAL` seals that text segment, not the conversation.
No confidence score or timing field is required because candidate engines
have not yet been validated to provide those values consistently.

`SpeechToTextOptions` requests `AUTO`, `CPU`, or `GPU` and may include a language
hint. An adapter must honor an explicit device choice or raise
`DeviceUnavailableError`; the actual choice made for `AUTO` is reported by the
session. The contract does not prescribe a particular GPU API, model path, or
sample rate. Tests use fake partial/GPU and final-only/CPU engines to verify
that one consumer can use both through the same contract.

`ContinuousAudioPipeline` remains an activity-only API. `LiveSpeechPipeline`
adds a separate STT path, so engines receive their own requested sample rate
without being forced through Silero's fixed windows. STT inference runs on its
own worker. Engine selection, multilingual quality, latency, device
availability, offline model packaging, and integration with file input remain
OPEN.

---

## 27. Offline STT Evaluation Preparation

`docs/stt/STT_EVALUATION_FA.md` records the candidate shortlist, comparable
measurements, and observed limitations of the current development machine.
This is an evaluation plan, not an engine-selection decision or a claim of
measured recognition quality. The repository contains no STT model or labeled
speech benchmark yet. The local NVIDIA GPU is visible via PCI, but
`nvidia-smi` cannot communicate with its driver; GPU STT results cannot be
reported from this environment until that is resolved. No runtime dependency
or application behavior changed during this preparation.

The subsequent CPU-only smoke test is documented in
`docs/stt/STT_CPU_SMOKE_2026-10-03_FA.md`. It used 12 public Persian read-speech
clips and disposable models/dependencies under `/tmp`, without changing
KYRIN's runtime dependencies or code. Vosk small-fa-0.42 produced streaming
partials and a 3.0% corpus CER on that small subset; faster-whisper multilingual
base/int8 produced 32.5%; small/int8 produced a provisional 17.0%, pending
verification of its tokenizer after a network TLS error. These numbers cannot
establish multilingual or conversational suitability. The optional Vosk
adapter can now be used through `LiveSpeechPipeline`, but it is not the
production default or wired into a desktop application. A labeled multilingual
command corpus and meaningful live-command latency measurement remain
necessary before selection.

---

## 28. Experimental Vosk Adapter

`src/kyrin/stt/backends/vosk.py` implements the portable STT engine/session
contracts for a locally provided Vosk model. `pyproject.toml` exposes Vosk as
the optional `stt-vosk` dependency; the default project install is unchanged.
The adapter accepts mono INT16 PCM at the configured model sample rate, emits
revisable partial updates and final segment updates, and never ends a session
merely because speech pauses. It supports CPU only and one configured language
per model instance. A GPU request or a mismatched language hint fails
explicitly. It does not download a model or access microphone hardware.

The adapter's design and use are documented in `docs/stt/VOSK_ADAPTER_FA.md`.
Its deterministic tests use a fake Vosk API. A separate run with the actual
Persian model and a public WAV produced partials and a correct final transcript
while network connection attempts were blocked. Live microphone throughput,
multilingual switching, and production model selection remain unvalidated.

---

## 29. Live VAD/STT Composition and Backpressure

`LiveSpeechPipeline` opens one `AudioInput` source through `AudioCaptureQueue`.
A VAD worker sends each source chunk to `AudioBacklog` before independently
resampling and framing it for the existing `SpeechActivityMonitor`. An STT
worker consumes the same ordered source chunks from the backlog and resamples
them to the session's declared input format. Only confirmed activity
transitions are emitted to the caller; every VAD window is still examined.
Partial and final transcript updates are also emitted. A speech pause never
calls `session.finish()`; only natural source completion does. Exiting the
context early stops the source and closes the session.

The STT backlog includes audio currently under inference. Its default warning,
recovery, and hard limits are 1000, 250, and 5000 ms of source PCM. It emits
`BacklogNotice(WAIT)` once when the warning threshold is crossed and
`BacklogNotice(READY)` once after processing catches up. The UI must decide
how to display those notices; no UI is wired yet. A hard limit raises
`AudioQueueOverflowError` rather than silently dropping speech. Capture
itself retains its separate chunk-count limit, so unusually slow VAD or an
unresponsive event consumer may still trigger a capture overflow. These
thresholds are provisional and must be measured on real devices.

Deterministic tests cover one capture and ordered delivery to both branches,
independent sample rates, warning/recovery, explicit sustained-overflow
failure, early stop, and continued STT session across a speech pause. The
bounded diagnostic `scripts/audio/check_live_speech.py` was then run on a real
microphone. One 20-second PulseAudio run with a locally supplied Persian Vosk
model emitted streaming partials and three final segments while continuing
across pauses, without backlog or stop errors. A separate direct ALSA input
run received audio but failed to stop within the current timeout. The model's
own WAV test file produced partial and final text through the same pipeline.
Device IDs, model files under `/tmp`, and these observations are local and
temporary. No raw microphone recording or private transcript was committed.
One additional 35-second run of a short, repeated Persian sentence produced
two matching final texts close to the user's reference without backlog or
stop errors. General command accuracy, exact audio-to-text latency,
multilingual quality, and long-duration behavior remain unvalidated. See
`docs/audio/LIVE_SPEECH_PIPELINE_FA.md` for the commands and observations.

A controlled live test with three Persian desktop commands produced three
final transcripts without backlog or stop errors. Two matched their references
apart from punctuation/spacing. The first transcribed the spoken wake name
imperfectly, and a partial transcript briefly contained incorrect words before
correcting itself. This supports cautious partial-command handling and wake
name evaluation, not a production STT selection. Reference phrases and
results are in `docs/stt/STT_LIVE_COMMAND_SMOKE_2026-10-03_FA.md`.

---

## 30. Model-Independent Command Decisions

`src/kyrin/commands/` now contains a replaceable `CommandInterpreter`
contract, a `CommandCoordinator` for one ordered STT stream at a time, and a
limited offline `DemoCommandInterpreter`. The contract receives text, optional
language, dialogue context plus any fresh active-app observation, and an
outstanding clarification.
It returns a ready command, a question, an incomplete/unclear command, or
ordinary speech. It does not import Vosk or operate the desktop.

The first ready partial interpretation produces a replaceable
`CommandCandidateUpdate`; repeated identical partials produce no duplicate.
Later partials may replace or retract it. A final
transcript produces `CommandResolution` for the same `(stream_id, segment_id)`.
Candidates are advisory and never authorize execution by themselves. Later
partial changes can retract a candidate; final resolution supersedes it.
Repeated final updates for the same segment are ignored. VAD pauses do not
clear dialogue state. `start_new_stream()` increments the stream ID and resets
segment IDs after an STT restart while keeping an outstanding clarification.
The coordinator keeps the last app referenced in a final command separately
from an active-app observation. A previous action result or spoken proposal is
not a fresh foreground observation for a later command.

The limited demo recognizes only a few Persian and English app/chat phrases,
with or without a wake name. It is not the multilingual production engine.
Ambiguous chat commands ask which app; incomplete or unclear final text asks
for repetition; ordinary speech remains silent. Response events specify
text-only or text-and-voice delivery, but UI and TTS are not implemented.
The Linux app executor exists separately; no live desktop integration exists.
See
`docs/commands/COMMAND_UNDERSTANDING_FA.md` for behavior and limitations.
Focused command, STT, and live-pipeline tests passed (35 tests); Ruff and Mypy
passed. Full-suite collection was blocked by unavailable PulseAudio in the
isolated execution environment.

The bounded diagnostic `scripts/audio/check_live_speech.py` now has a
`commands` mode. It feeds live `TranscriptUpdate` events into the coordinator
and prints command candidates, final resolutions, and response requests. It
uses the limited demo interpreter and does not infer verified application
state or execute any action. A hardware-free integration test replays a
partial command that later becomes negated through `LiveSpeechPipeline` and
checks candidate retraction. A user-coordinated, 35-second microphone run
then confirmed four final decisions: a separately transcribed wake word did
not trigger an action; open Telegram was proposed; opening Ali's chat asked
which app and accepted "Telegram" as the answer; a negated open command did
not become an action. Under the rule used at that time, there were no
provisional candidates because each complete ready partial appeared only once
before its final update. The rule was subsequently changed to emit the first
ready partial as a retractable candidate. A second 25-second user-coordinated
microphone run produced a candidate for "open Telegram" about 0.72 seconds
before the final decision and no open candidate for "do not open Telegram".
The run did not observe a live candidate retraction; that behavior remains
covered by deterministic tests. These are local event timestamps, not exact
audio-to-action latency measurements. No action or voice response was executed.
See `docs/commands/COMMAND_LIVE_SMOKE_2026-10-03_FA.md` for exact test text,
observations, and limits. No action or voice response was executed.

---

## 31. Dry-Run Action Gate

`src/kyrin/actions/` now contains `ActionPolicy`, `ActionGate`, and structured
request/notice/result/feedback types. The gate consumes command events but
only a final `CommandResolution` may produce an `ActionRequest`. Partial
candidates and command response requests cannot authorize work. The policy
defaults to denying everything and has explicit allowed app identifiers for
`OPEN_APP` and `OPEN_CHAT`. An optional per-command-kind confirmation rule
returns a notice until an explicit trusted confirmation decision arrives.

The gate deduplicates resolutions by `(stream_id, segment_id)` within one
coordinator/gate lifetime. Pending confirmations and issued requests are
bounded by `max_pending`; reaching the limit returns a visible busy notice.
No shell command or OS call is derived from recognized speech here.

`ActionResult` must match an outstanding request. Only a successful result
that explicitly reports the observed active app updates `VerifiedContext`;
failure leaves prior context intact. `ActionFeedback` carries structured
success/failure and the requested text/voice channel for a later localized
presenter. Unit tests use synthetic results, not actual desktop actions.
No executor is connected to the live voice diagnostic. No confirmation
interface, UI, or TTS is connected. See
`docs/actions/ACTION_GATE_FA.md` for the rules and limitations.

The microphone diagnostic's `commands` mode now feeds live command events to
the gate and prints allowed or blocked dry-run decisions. Its small diagnostic
allowlist covers `telegram` and `browser` for app opening and `telegram` for
chat opening. It records no synthetic success, so it does not invent verified
application context. A real three-phrase microphone run observed an authorized
dry-run request for "open Telegram", no action for "do not open Telegram",
and a clarification request for "open Ali's chat". No app launched in that run.

---

## 32. Limited Linux App Executor

`ActionExecutor` is a platform-neutral request/result protocol. Its first
implementation, `LinuxDesktopEntryExecutor`, handles only `OPEN_APP` on Linux.
Trusted configuration maps internal app IDs to absolute `.desktop` file paths;
the executor invokes `gio launch` with separate arguments and no shell. Other
commands or unconfigured apps return controlled errors. Windows, macOS, and
Android will need separate adapters behind the same contract.

`ActionOutcome` distinguishes `CONFIRMED`, `LAUNCH_ACCEPTED`, `UNKNOWN`, and
`FAILED`. A zero exit status from the Linux launcher means only
`LAUNCH_ACCEPTED`, not that a window opened or became active. The executor
never fabricates `observed_active_app`; the gate updates verified context only
from an independently confirmed active app. A new app launch that is accepted
or uncertain invalidates the previously verified active app. See
`docs/actions/OS_EXECUTOR_FA.md` for behavior and limitations.

Focused deterministic tests and static checks pass. A manual launch request
for the installed Telegram desktop entry returned `LAUNCH_ACCEPTED` twice;
the first visual check was inconclusive because Telegram was already open.
After closing Telegram, the user confirmed it opened again on the second
request. This is a human observation on one Linux desktop, not an automatic
foreground-app verification mechanism. No live voice command is yet connected
to this executor.

---

## 33. Chat-App Context Resolution

`CommandContext` separates the last app mentioned in final dialogue from a
fresh, optional `observed_active_app` supplied for the current transcript
update. `CommandCoordinator` retains the dialogue reference across silence
and STT stream restarts; partial text never changes it. The interpreter uses
an explicitly named app first. For an omitted chat app, `ContextResolver`
uses a supported fresh foreground observation if dialogue history does not
conflict. If the last referenced app is Telegram but the newly observed app
is WhatsApp, the demo interpreter asks which one the user means. With no
fresh observation, dialogue history alone cannot authorize an implicit app.

This is a language-neutral resolution boundary with limited Persian demo
phrases; it does not read the actual foreground app or search contacts.
The dry-run microphone tool supplies no foreground observation. A GNOME
prototype now exists but needs live focus validation; other supported
platforms need their own adapters where possible. Otherwise the safe path is
a clarification question. No `OPEN_CHAT` desktop
executor exists yet. Focused tests cover conflict, explicit choice, missing
observation, partial correction, and context surviving an STT restart.

---

## 34. GNOME Active-App Observation Prototype

`kyrin.desktop.active_app.ActiveAppObserver` is a minimal cross-platform contract for a
fresh active-app observation. `GnomeShellActiveAppObserver` queries a tiny GNOME
Shell extension over the existing `org.gnome.Shell` session D-Bus connection.
The extension returns only the focused app's desktop ID, never window titles or
screen content. The Python adapter maps only configured external IDs to KYRIN
app IDs; an absent extension, missing focus, unknown app, malformed response,
or timeout returns `None`. It does not cache observations or execute actions.
No new Python dependency was added. The diagnostic under `scripts/desktop/`
prints raw desktop IDs as focus changes.

Seven focused deterministic tests, Ruff, and Mypy passed. A separate headless
GNOME Shell 50 session loaded the extension and returned `unknown` when no
window was focused. An attempt to focus Calculator in that headless session
also returned `unknown`, so nonempty app-ID reporting has not been validated.
The current live Wayland session did not recognize the
newly installed extension without a new login, so an in-session Telegram/Chrome
focus-switch test has **not** passed. The temporary user installation was
removed after this attempt. See `docs/desktop/ACTIVE_APP_OBSERVATION.md`.
