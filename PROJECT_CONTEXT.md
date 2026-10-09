# KYRIN — Project Context

> Engineering handoff for the current repository state.
> Updated: 2026-10-09.
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
- **Current major engineering area:** GNOME screen-access boundary for V1
  desktop vision, alongside the existing voice/audio pipeline.
- **Current completed foundation:** audio capture, core PCM data model,
  streaming mono INT16 sample-rate conversion, configurable audio framing,
  an offline VAD adapter, continuous speech-activity monitoring, replaceable
  STT contracts, and a bounded live VAD/STT pipeline.
- **Current next direction:** measure and improve the speech-to-command path
  before more chat automation. The owner reported that non-English speech,
  varying spellings of KYRIN, and `Open chat Save Message` were not reliably
  understood. The application now displays an in-memory decision trace,
  accepts configurable wake-name spellings, and supports `auto` language
  detection with the installed multilingual Whisper adapter. These are
  diagnostics and bounded improvements, not general multilingual command
  understanding or an installed translation engine. The permission-gated
  `Saved Messages` action still needs a live product-path test. Runtime
  packaging and broader model management remain future work.
  Settings, lifecycle control, Ubuntu session composition, a Qt control
  window, a single-instance guard, and user-scoped XDG registration exist.
  English development uses the locally
  installed Whisper `small` CPU/GPU adapter while Vosk remains replaceable; this
  is not a packaged default or a general accuracy claim. The terminal
  diagnostic stays dry-run by default. Explicitly allowlisted app launch and
  registered app-name matching have passed focused tests, and the owner
  validated a real microphone-to-Telegram launch. Model packaging,
  multilingual setup, a complete product UI, broader stability validation, and
  Windows/macOS/mobile adapters remain future work.
- **Current speech and window-focus correction (2026-10-09):** The owner supplied
  diagnostic traces showing standalone wake-name spellings `Kairin`, `Kyreen`,
  `Kyrie`, and `Kairi`. The standalone name is now acknowledged with text-only
  readiness and cannot create an action; the observed variants are exact wake
  aliases. An unsupported phrase after the name still asks for repetition.
  The owner also requested that `Open Telegram` raise its existing window.
  The Ubuntu composition now optionally uses a GNOME Shell adapter to request
  activation of an existing registered app window, confirms foreground focus
  with a fresh observation, and launches only when the extension explicitly
  reports no window. Uncertain activation never triggers a second launch.
  Focused Python and GJS tests cover these paths. The updated extension file
  is installed for the current user, but the running GNOME session still
  exposes the old D-Bus methods after a disable/enable cycle; a fresh GNOME
  session and live user validation remain required.
  After that restart, the owner reported repeated `Open Telegram` finals with
  `activation_unverified` while the Telegram window was minimized; GNOME showed
  "Telegram is ready" instead of focusing it. One attempt did confirm. The
  interpreter and allowlist were working; the focus request was intermittent.
  GNOME's `Shell.App.activate_window` compares the passed timestamp with the
  last user interaction and may request attention instead of activating an
  existing window. The extension now uses the same `Main.activateWindow` path
  used by Ubuntu Dock, with a fresh display timestamp, for this allowlisted
  voice action. Deterministic extension and Python tests pass; the revised
  installed extension still needs a fresh GNOME session and live verification.
- **Application foundation:** immutable, versioned settings, an injectable
  JSON store, and a UI-independent lifecycle controller now exist under
  `src/kyrin/app/`. Ubuntu composition and an optional Qt control UI connect
  them to the live runtime. User-scoped login startup registration exists. A missing settings
  file yields no selected STT model and no action permission. See
  `docs/app/UBUNTU_APPLICATION_LIFECYCLE_DESIGN.md`.
- **Visual feedback in progress:** a backend-independent status controller and
  optional GNOME Shell 50 character adapter now exist in the repository. The
  character distinguishes processing, clarification, actual action execution,
  confirmed completion, accepted-but-unverified launch, and failure. Focused
  Python tests and extension packaging passed. After correcting a GNOME 50
  drag API incompatibility, the owner observed a visible, draggable character
  and GNOME reported the extension as `ACTIVE`. Dragging felt laggy, so the
  extension now coalesces pointer motion and updates position once before each
  redraw. A separate fresh GNOME Shell 50.1 session verified status delivery
  and newest-position application. The owner reported that this was much
  better but still lagged. A visual-translation experiment passed a separate
  coordinate check but felt much worse on the user's actual desktop, so it was
  rolled back to frame-coalesced position updates. The remaining live delay
  needs measurement before another change. The owner rejected the dark static
  preview and authorized a smaller electric blue/violet animated mascot with
  contextual captions and a hide control. The optional GNOME
  adapter now uses a compact vector character and short state-driven motion;
  the UI has a × button and a top-bar restore control. The owner confirmed
  dragging, × hide, and restore after restarting the desktop session. The visual
  caption contract is independent of STT and TTS adapters. Headless GNOME
  tests verified movement, captions, hide/reopen, and queued position changes.
  The owner reported that real dragging failed; GNOME logs identified a null
  pointer-event source passed to `Clutter.Actor.contains()`. The owner later
  confirmed dragging after a session restart, but × did not hide the mascot.
  Drag starts on the image-and-caption content now, leaving × as a separate
  click target. A follow-up made × always clickable, handled primary press
  directly, and added a hover hint; the owner validated hide/restore after
  restarting the session. The owner approved more distinct state reactions.
  The mascot now uses head, eye, body, arm, and leg SVG layers, with
  compositor-only poses for ready, listening, processing, clarification,
  actual execution, confirmed/unverified results, and failure. The revised
  package is installed for the current user. A separate headless GNOME Shell
  50.1 session loaded all eight states without an extension error. After a
  restart, the owner observed distinct listening, processing, and execution
  motion; correct symbols and captions; smooth movement; and working ×
  hide/restore in a no-action display run. The user-session log showed no
  extension error. A later local `Open Telegram` microphone run produced a
  confirmed Telegram foreground action; the owner independently saw Telegram
  activate and observed the character change states during the real command.
  A later non-command transcript was the owner's spoken reaction and caused no
  action. Broader timing and other desktop environments remain unverified.
  This is not packaged product UI.

The 2026-10-07 repository audit read the project files by component and found
two small gaps in the current vertical slice. A final non-command could leave
the mascot showing Processing; a worker failure could go without immediate
user feedback. The status controller now returns to Ready on a final
non-command, with a later clarification event taking precedence. Executor
exceptions are represented as UNKNOWN because an action might have occurred
before the exception. A fatal worker processing error also emits immediate
UNKNOWN feedback before the worker stops. Deterministic tests cover these
paths. The full static type check now passes after synchronizing test doubles
with the current contracts. No new live microphone/GNOME validation has been
run for these corrections.

KYRIN is an open-source modular AI Desktop Agent. The high-level product vision
is to understand voice, vision, and text and interact naturally with the
operating system.

On 2026-10-09 a separate, read-only visual text foundation was added under
`kyrin.vision`: a permission-aware one-shot Ubuntu ScreenCast window capture,
a backend-independent OCR contract, a Tesseract CPU adapter, and a composition
that never executes desktop actions. The owner authorized and selected a window
in a live portal test; one 1920×1080 PNG was returned in memory. A local
Tesseract 5.5 runtime and English data were then extracted under the ignored
`models/local/ocr/tesseract/` directory without a system install. A synthetic
`Open Telegram` image returned both words and their boxes; live screenshot OCR
then found both expected words in a portal capture of a temporary test window
that the owner confirmed selecting. OCR processing after capture took 0.146 s
in that one run; broader live accuracy and latency remain unverified.
The selected portal window is not yet bound to active-app identity. This work
does not provide verified browser/chat navigation or a model-management UI.
An optional GNOME 50 active-window capture prototype was added as a separate
extension. Its first version asked for user consent for every image. It
returned focused-window identity and image in one request and rejected a focus
change. The subsequent live validation is described below. See
`docs/vision/GNOME_ACTIVE_WINDOW_CAPTURE_PROTOTYPE.md`.
After the owner restarted, GNOME Shell 50.1 listed the extension as ACTIVE.
In an explicitly approved live one-shot test, the owner accepted the GNOME
prompt; the temporary `KYRIN OCR Test` window was captured in memory and OCR
found `Open` and `Telegram`. GNOME reported `window:8`, which is a temporary
window-backed ID rather than an installed-app ID. The extension and adapter
were then tightened to reject those IDs. A second, user-approved live test of
a window bearing KYRIN's registered desktop ID returned
`local.kyrin.KYRIN.desktop`, its test process ID, and OCR words including
`Open` and `Telegram`. This confirms the read-only capture+identity+OCR path
for that one registered window. It does not authenticate the D-Bus requester,
generalize to other apps, or authorize actions. The prototype extension was
disabled after the tests and GNOME reports it INACTIVE.
The owner then approved a session-scoped access design. The Qt app now claims
`org.kyrin.Desktop` and provides a `Screen Access` page with a non-persistent
on/off control. The revised GNOME extension checks the D-Bus sender against
the current owner of that name, prompts once per app session, and revokes on
explicit request, owner loss, or extension disable. The old separate-process
image helper and terminal diagnostic were removed because their D-Bus sender
cannot be the Qt app's connection. Python and GJS tests cover grant, foreign
sender denial, revocation, owner loss, and a late owner response after revoke.
The corrected extension was installed and enabled. An unauthorized direct
D-Bus capture request returned no image. The first live Qt grant request was
denied before the GNOME prompt appeared. D-Bus monitoring confirmed that the
request sender and `org.kyrin.Desktop` owner matched. A real GJS check found
that `GLib.Variant.unpack()` returned a wrapped child variant rather than the
owner string. The extension now uses `deepUnpack()` for the owner check and
the name-owner-change signal; the GJS harness models this distinction.
Focused tests passed, but an immediate retry in the same GNOME session still
returned the old denial. After the owner restarted the desktop session, the
corrected Qt request displayed the GNOME dialog and received a grant. A
separate approved live test captured one 20,072-byte PNG in memory from a
registered KYRIN test window, with `local.kyrin.KYRIN.desktop` and its PID.
After explicit revoke, a further capture request returned no image. This
validates the Qt/GNOME one-image path and revocation on this desktop; it is
not connected to OCR-triggered actions. A session-bus name is not strong
authentication of a binary against a malicious process running as the same
user; GNOME consent remains required.

The owner approved a staged connection from screen observation toward command
understanding. The first slice is read-only: `ScreenTextReader` receives an
on-demand image from the Qt-owned `ScreenAccess`, runs the replaceable `OcrEngine`
on a worker thread, and discards the result if the active desktop ID/PID has
changed or access was revoked. The `Screen Access` page displays bounded plain
text and clears it on revoke. The Ubuntu Qt composition discovers an optional
English Tesseract runtime from the user's XDG data directory. The previously
downloaded local runtime was copied there on this development machine without
installing system packages. Focused automated tests pass. In a live Qt run
on 2026-10-09, session access was granted and the combined reader returned
`local.kyrin.KYRIN.desktop`, the test process PID, and OCR words including
`Open` and `Telegram` from the registered test window. Access was revoked on
exit. A portal app-ID registration warning appeared but did not prevent this
test. This validates one local read-only path, not recognition quality across
apps or permission behavior on other desktops. OCR text is still not fed to
the command interpreter and cannot authorize an action.
Two further read-only Qt tests captured the owner's real Telegram Desktop
window with a stable desktop ID and PID; the GNOME session grant was revoked
after each run. The first mixed Persian/English view yielded 162 OCR words but
none of the small English label set checked by the probe. The owner clarified
that this view contained both languages, while the installed Tesseract data is
English only. A controlled Telegram Settings view yielded 394 OCR words,
including `Settings`, `Notifications`, `Privacy`, `Security`, `Language`,
`Folders`, and `Advanced`; 102 of 394 spans had confidence at least 0.8.
The probe printed counts and fixed generic labels, not chat names or images.
This establishes that English UI labels can be read in this window; it does
not establish reliable contact matching, Persian OCR, or click coordinates.
A third read-only Telegram run used the owner's chat list with the public
`Saved Messages` title visible. OCR found the exact adjacent English words;
252 spans were returned, 56 at confidence 0.8 or higher. The probe reported
only whether that title was present, not other chat names. This is one
controlled title match, not evidence of reliable arbitrary contact matching.
An exact, same-line OCR phrase matcher with duplicate preservation was added
as read-only groundwork and passes focused tests. A proposed first input
action is documented in `docs/actions/TELEGRAM_CHAT_NAVIGATION_DESIGN.md`.
The local Wayland session exposes RemoteDesktop Portal v2, but its keyboard
permission is desktop-wide rather than Telegram-window-scoped. The owner
approved a one-shot, keyboard-only diagnostic. The installed Telegram shortcut
file maps `self_chat` to `Ctrl+0` with no custom override. A system-Python
portal helper requested a non-persistent keyboard session, rechecked the
Telegram desktop ID and PID, sent only that fixed shortcut, and closed its
session. The subsequent read-only Qt OCR run found one `Saved Messages` phrase
in the same Telegram window; the owner independently confirmed that this chat
opened. A subsequent owner-approved read-only test located a single exact
`Saved Messages` phrase in the upper chat pane of a 1853×1048 Telegram image
at x=679, y=45 with confidence above 0.87. The Ubuntu application now has a
separate saved Telegram chat permission (settings schema 2, with schema 1
migrating to permission off), and the action gate enables `OPEN_CHAT` only
when this permission and the required observer, window-identity reader, and
Qt screen verifier are present. Its one implemented target is `Saved Messages`.
The portal helper rechecks focus before the keyboard shortcut and the Qt-owned
OCR reader checks a fresh matching window and upper-pane title afterward.
Focused automated tests pass. The full product microphone-to-chat path has
not yet been live tested, and arbitrary contact navigation remains open.

The owner then prioritized speech understanding before further chat actions.
The Speech Recognition page now keeps a bounded, session-only trace of final
STT text, command decisions, clarification or block reasons, and action
results. Current settings schema 3 adds optional user-editable wake-name
spellings, with schema 1/2 migration to no custom spellings. The Whisper
adapter can use `language=auto` with a multilingual model and forward the
detected language code from local verbose JSON; Vosk rejects `auto`. On this
development machine, the installed Whisper `small` model returned `en` and
`fa` for one previously recorded clip in each language. This confirms the
adapter path for those two clips, not accuracy or broad language coverage.
The demo command interpreter still recognizes a limited English/Persian
grammar. See `docs/stt/MULTILINGUAL_COMMAND_INPUT.md`.

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
adapter, and backend-independent live VAD/STT composition exist. A reusable
`LiveCommandRuntime` connects transcript decisions to the bounded action
worker. The Linux launcher is available only with explicit execution and app
bindings in the terminal diagnostic; a packaged application entry point does
not yet exist.
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

This section preserves an earlier milestone snapshot. Later sections 43–57
record decisions and implementation that supersede its old next-step and test
counts; use the overview above and the repository for current status.

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

Broaden the English command corpus and validate the owner-selected Vosk
`lgraph` default candidate on ordinary CPU hardware before bundling it. The
current replay includes errors in confirmed command names. Then design a
user-facing model manager and optional language installation. Keep live voice
action execution disabled until app state and feedback are handled honestly.

The standalone Vosk adapter works with a locally supplied model. The live
pipeline accepts any engine implementing the STT contract, including Vosk;
the owner's product direction chooses Vosk for English V1, but no runtime
default is wired yet. Acceptance still requires measured command accuracy,
partial-result latency, resource use, and offline packaging. The first semantic
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
thread. `MicrophoneInput.stop_capture()` sets a stop signal, briefly allows the
current read to finish, and aborts the active stream only if capture does not
end promptly. A stopped `MicrophoneInput` is one-use; create
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
success/failure and the requested text/voice channel for the localized
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
The dry-run microphone tool can now supply foreground observations on final
transcripts when explicitly configured with exact GNOME desktop-ID bindings.
The GNOME observer was validated with live focus switching; the combined
microphone-to-context path still needs a coordinated live test. Other platforms
need their own adapters where possible. Otherwise the safe path is a
clarification question. No `OPEN_CHAT` desktop
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
GNOME Shell 50 session loaded the extension and returned an empty app ID when
no window was focused; the diagnostic displayed `unknown`. An attempt to focus
Calculator in that headless session also displayed `unknown`, so that run did
not validate nonempty app-ID reporting.
The first live Wayland session did not recognize the newly installed extension.
After the user restarted the system, GNOME Shell 50.1 recognized and enabled
it. In a 20-second test, the observed IDs alternated between Chrome and
Telegram as the user confirmed switching between those windows. The extension
is enabled in that user session. No command was executed. See
`docs/desktop/ACTIVE_APP_OBSERVATION.md`.

---

## 35. XDG Installed-App Catalog

`kyrin.desktop.app_catalog.AppCatalog` is a small platform-independent
discovery contract. `XdgDesktopAppCatalog` reads XDG `.desktop` entries with
the standard library, including the user's data directory before system data
directories. It derives exact desktop IDs, honors `Hidden=true`, and returns
base display names. The active-app diagnostic can now show a registered name
beside a freshly observed ID. On this device it found the local Telegram ID
and two Chrome IDs with the same display name. Display names are therefore
not trusted to infer a KYRIN command target. `AppIdentityResolver` applies
explicit exact-ID bindings, with an optional catalog-presence check; the GNOME
observer delegates to it without breaking its existing constructor. A
read-only live probe mapped the freshly observed `chatgpt.desktop` to `codex`
with a test binding and catalog validation. At that stage, no live command
integration or desktop action was added. No new runtime dependency was added.

---

## 36. Optional Active-App Context in Live Command Dry Run

`src/kyrin/desktop/command_bridge.py` supplies a fresh active-app observation
to `CommandCoordinator` only for final transcript updates. Partial updates
remain advisory and do not wait for the desktop. The microphone diagnostic's
`commands` mode accepts repeated, explicit `--active-app-binding`
`DESKTOP_ID=KYRIN_APP_ID` values and composes the GNOME observer with the XDG
catalog. Without bindings it preserves the old behavior. Missing focus,
unrecognized IDs, or an unavailable extension give `None`, so ambiguous chat
commands still ask for clarification. The action gate remains a dry run and
no executor is connected.

Deterministic bridge tests cover final-only observation and an unknown
observation after a previously known app. The CLI option was parsed in the
user session without opening the microphone. A read-only probe combined the
real GNOME observer with a synthetic final Persian chat transcript while
Codex was focused. It returned `None` for the Telegram binding and asked
which app to use; no action was executed. A coordinated real microphone test
is still pending because the local Persian Vosk model directory was not found
after the restart. This change does not establish STT accuracy or actual
desktop-action behavior.

---

## 37. Localized Response Text

`ResponseRequest` now carries a `ResponseKind` and structured chat details,
not a prewritten Persian sentence. `PendingClarification` retains the chat
target and candidate app IDs, so the demo interpreter and coordinator no
longer choose output wording. `ResponsePresenter` turns a command response,
`ActionNotice`, or `ActionFeedback` into `PresentedResponse` with text, channel,
locale, and stream/segment identity. The component has no microphone, OS,
UI, or TTS access and adds no dependency. The live-command diagnostic prints
the localized response text and still executes no actions or voice output.

Persian and English text are currently available; unsupported locales fall
back to the supported session preference, or English. This is presentation
coverage, not multilingual STT or command-understanding coverage.
`LAUNCH_ACCEPTED` text explicitly says that
completion is unconfirmed. `error_code` stays internal and is never copied
to user-facing text. Focused command/action/desktop-bridge/presenter tests
pass. A real active-app microphone test remains pending because the local
Persian Vosk model used earlier under `/tmp` was not found after restart.

---

## 38. Per-Command Response Language and Process Notices

Final transcript language now travels with `CommandResolution` and
`ResponseRequest`. `ActionGate` retains it in requests, notices, pending
confirmations, and eventual feedback, so late results do not adopt the
language of a later command. The presenter uses a supported event language,
then the session preference, then English. The actual output language remains
visible in `PresentedResponse.language`. Vosk's language tag is the configured
model language, not evidence of automatic language detection.

`SystemNotice` and focused adapters classify backlog wait/ready states and
known audio/STT failures without displaying raw exception text. The backlog
warning requests a pause with text and voice; recovery is text-only. A queue
overflow says that speech may have been lost. The live diagnostic prints
localized text, accepts an independent `--response-language`, and still does
not synthesize audio, show a product UI, or execute recognized commands.
It now loads the audio runtime after parsing CLI arguments, so a startup
failure can be reported as a localized microphone error.
Only Persian and English catalogs exist. Additional language catalogs and
offline TTS voices remain future work; no new dependency was added. See
`docs/responses/RESPONSE_LANGUAGE.md`.

---

## 39. Bounded Recovery of Live Speech Sessions

`SpeechSessionController` now supervises one bounded listening run. It uses a
factory to construct a fresh `LiveSpeechPipeline` and microphone source after
recoverable capture, queue-overflow, or STT failures. The shared STT engine
opens a fresh session for each attempt; Silero VAD is reset by the monitor at
each new stream. Default recovery is two retries with a one-second delay, and
the live diagnostic exposes both values as CLI options. The diagnostic's
duration applies to the full supervised run. The VAD-only diagnostic is not
under this controller.

A `SpeechSessionEnded` boundary tells the command consumer to retract partial
candidates and increment its stream ID while retaining dialogue reference
and pending clarification. A failed capture stop, failed STT-session close,
worker shutdown failure, or unavailable compute device is terminal; the
controller does not risk reusing an uncertain native resource. System notices
give localized text for recoverable errors and an impending retry. No real
command is executed or voice output produced.

Focused deterministic tests cover fresh attempts, retry limits, interruption
of backoff, active stop, and unsafe-close classification. A real microphone
recovery run is still pending: the temporary Persian Vosk model used in
earlier sessions is no longer present after restart, and the sandbox does not
expose the desktop audio server. No new dependency was added. See
`docs/audio/LIVE_SPEECH_PIPELINE_FA.md`.

---

## 40. Reproducible Offline STT Evaluation Tool

`kyrin.stt.evaluation` reads a labeled CSV manifest and local mono 16-bit PCM
WAV files, feeds audio through the existing sample-rate converter and any
`SpeechToTextEngine`, and computes normalized character error from final
transcripts. The default paced run reports first partial/final event times
relative to file replay; unpaced mode measures processing without simulated
capture timing. The Vosk CLI in `scripts/stt/evaluate_offline_stt.py` adds no
dependency and never downloads a model or audio. Focused tests use a fake
engine and generated PCM files; they do not establish recognition quality.

The temporary `/tmp/kyrin-stt-eval-20261003` corpus/model directory is absent
in the current environment. No STT model weights are tracked in Git. An
official `vosk-model-small-fa-0.42` ZIP was downloaded and kept in the ignored
local `models/archive/` directory. Its extracted files live in `models/local/`;
ZIP CRC passed and the bundled WAV/reference
were processed with paced 20 ms chunks. Vosk loaded and produced “من عرضه این
کار رو ندارم” against “من عرضه اين کارو ندارم”; the defined character metric
counted 2 edits in 22 normalized characters. The one-file result shows that
this local model runs, not that it is suitable for KYRIN commands or other
languages. A small six-command Persian corpus was then recorded with explicit
consent using one USB microphone and kept under Git-ignored
`datasets/stt/recordings/`. The speaker confirmed the `fa-05` reference. On
these six clips, Vosk exactly matched four; aggregate normalized CER was
12/133 (9.0%). It misheard “کایرین” as “طاهری” and the `fa-05` phrase
“چت علی را در واتساپ” as “ساعت علی را در صبح”. This is a local baseline, not a
representative quality claim. A first cross-engine file comparison has now
been run, but representative multilingual samples and live comparison remain
open. See `docs/stt/STT_EVALUATION_FA.md`.

The repository now tracks `models/README.md` and `models/.gitignore` so the
development model location and recorded ZIP checksum are discoverable while
the large weights remain outside Git. This is a development storage
convention, not a product default model or installed-app storage decision.

---

## 41. Experimental Whisper CPU Comparison

The user requested a Whisper comparison and emphasized that the eventual
product should also work on ordinary machines without a 16 GB GPU. No existing
Whisper weight file was found in the project or common local model caches.
`whisper.cpp` tag `v1.9.4` was built for CPU under ignored `build/tools/`;
CMake was installed only in the ignored project virtual environment. No
production dependency, STT contract or live pipeline was changed. Two
multilingual weights are retained under ignored `models/local/whisper.cpp/`:
full-precision `ggml-small.bin` (487,601,967 bytes) and quantized
`ggml-large-v3-turbo-q5_0.bin` (574,041,195 bytes). Paths and hashes are in
`models/README.md`. An aborted large-turbo download was removed.

On the same six consented recordings converted to common 16 kHz mono PCM,
normalized CER was 8/133 (6.0%) for Vosk, 18/133 (13.5%) for Whisper small,
and 25/133 (18.8%) for quantized Whisper turbo. The earlier Vosk test using
KYRIN's own resampler gave 12/133 (9.0%), reproduced twice; the resampler
path affected the `fa-05` transcript. Whisper CLI processed complete files
on CPU with four threads: about 2.4–2.6 seconds per clip for small, and
8.6–8.9 seconds for turbo-q5. These are local file-process measurements,
not live partial-text latency. Peak measured RSS for one clip was about
750 MiB and 793 MiB, respectively. Vosk's unpaced common-input processing
took about 0.13–0.23 seconds per clip with its model already loaded, but this
timing is not directly comparable with a separate Whisper process per clip.

The six-file, one-speaker experiment does not justify selecting or rejecting
Whisper as the product engine. `whisper.cpp` CLI was kept outside the streaming
`SpeechToTextEngine` contract because a whole-file transcription test cannot
demonstrate partial updates. GPU execution, broader language data, and live
command latency remain open. Full conditions and caveats are in
`docs/stt/WHISPER_CPP_COMPARISON_FA.md`.

## 42. Initial Whisper Rolling-Window CPU Replay

The user approved a multilingual corpus and a separate live-CPU diagnostic.
English command prompts and one optional exploratory German prompt were added
as separate templates; at that point, no new microphone recording had
occurred. The speaker
is fluent in Persian and English and has some German, so German speech from
this speaker cannot serve as a definitive quality result. Public multilingual
audio with references remains to be selected and recorded by source/license.

An isolated `scripts/stt/benchmark_whisper_replay.py` now replays an existing
consented WAV at recorded speed to a temporary loopback-only `whisper-server`
with one preloaded CPU model. It logs each overlapping window's transcript,
request time and lateness. No production dependency, STT contract, live
pipeline or command execution path changed. On `ggml-small.bin`, four threads,
the `fa-03` negative command (3.6 s) took 9.33 s overall at a 1 s window step
and 6.26 s at a 2 s step; first nonempty text arrived at 3.05 s and 4.24 s,
respectively, from file start. The `fa-02` positive command (2.5 s) took
6.07 s at a 2 s step, with first text at 4.04 s. At the 1 s step, processing
accumulated 3.70 s of dispatch lag. These are single-run, rolling-window
diagnostics, not actual microphone or native streaming STT measurements and
not grounds to select a product default. See
`docs/stt/WHISPER_LIVE_REPLAY_FA.md` and local ignored JSON results.

The user then explicitly authorized the first English recording, “Open
Telegram.” A short, near-silent attempt was rejected by the recorder. A
second 20 s capture yielded a 2.5 s crop (`en-02`, from 16.7–19.2 s); the
original capture was retained under ignored `datasets/stt/recordings/raw/`.
Whisper small returned the exact English reference on that crop. With a 2 s
rolling-window step and explicit `en`, first text arrived at 3.94 s and total
replay/processing took 5.89 s. With automatic language detection, first text
arrived at 5.79 s and total took 9.59 s. These are individual runs on one
English clip and cannot establish multilingual quality or a universal cost
for automatic language detection. No other new voice or public audio was
recorded/downloaded at that point. The English local manifest initially listed
only `en-02`.

The user also authorized recording the negative English command `en-03`.
A 2.7 s crop (22.2–24.9 s of the 30 s capture) was retained for scoring and
the original was preserved in the ignored recordings/raw directory. Whisper
small transcribed the whole crop exactly. With 1 s rolling windows, explicit
English yielded first nonempty text at 2.93 s and full reference at 4.89 s;
auto language yielded 4.79 s and 8.61 s, respectively. Both first nonempty
texts contained “Do not” in this one clip, but the worker accumulated 2.19 s
and 5.91 s maximum dispatch lag, respectively. The local English manifest now
lists `en-02` and `en-03`. No command was executed.

## 43. English Vosk Desktop Default Candidate

The owner selected English as the only initially installed language for V1
desktop and chose `vosk-model-en-us-0.22-lgraph` as the intended default.
Users should be able to add other compatible languages later; the model manager
and application settings do not exist yet. This is a product-direction decision,
not evidence that the model is accurate enough for KYRIN commands on ordinary
machines. The replaceable STT contract remains unchanged.

The official 130,557,655-byte ZIP was downloaded to ignored `models/archive/`,
checked by ZIP CRC and safe-path inspection, then extracted to ignored
`models/local/`. Its local SHA-256 and exact paths are recorded in
`models/README.md`. No product dependency or runtime default was added.

Two previously consented English commands were replayed through the existing
Vosk evaluator on CPU, both with KYRIN's 48-to-16 kHz conversion and with
previously prepared 16 kHz WAVs. `en-02`, “Open Telegram,” became “open filler
drop” in both paths; `en-03`, “Do not open Telegram,” became “do not open
telegram.” The two-file normalized CER was 8/33 (24.2%), which is not a
representative quality estimate. The paced run loaded the model in about
0.49 s and reached about 470 MiB peak RSS for the whole process. Detailed
outputs and timing are in ignored `datasets/stt/results/`, summarized in
`docs/stt/STT_EVALUATION_FA.md`. Further commands and speakers, target-machine
memory/latency checks, and actual microphone validation are required before
shipping this choice. No desktop command was executed in this evaluation.

The speaker then consented to three more English prompts. One near-silent
`en-01` attempt was rejected; the USB microphone input level was adjusted from
14% to 60% and the three prompts were recorded successfully. First-utterance
crops of `en-01`, `en-04`, and `en-05` and their original raw recordings remain
under ignored `datasets/stt/`. Vosk transcribed `en-01` as “corinne opened the
door,” `en-02` as “open filler drum,” `en-03` correctly, and `en-05` correctly.
The first `en-04` crop was transcribed “open alleys charge in telegram.” The
speaker then clarified that they actually said Telegram, not the template's
WhatsApp. The initial five-file scoring report was therefore invalidated and
marked `UNVERIFIED-REFERENCE`; it must not be cited as a model-error result.
Four clips with usable references were replayed and yielded CER 20/80 (25.0%),
still far too small and single-speaker to generalize. A later `en-04` crop
yielded “open alleys chart in what's up,” but its exact spoken reference is
unconfirmed and it is not scored. The model loaded in about 0.46 s and the
whole evaluation process peaked at about 491 MiB RSS on this machine. See
`docs/stt/STT_EVALUATION_FA.md` for the full results and limits.

A new `en-06` recording then explicitly captured “Open Ali's chat in
WhatsApp,” and the speaker confirmed the word WhatsApp. Vosk returned “open
alleys child in what's up”: the app name was rendered as ordinary words, but
the contact/chat phrase was wrong. A five-file replay using only confirmed
references (`en-01`, `en-02`, `en-03`, `en-05`, `en-06`) yielded normalized CER
29/107 (27.1%) on this one speaker. The model loaded in about 0.47 s and the
whole process peaked at about 493 MiB RSS on this machine. This is a small
diagnostic, not a production accuracy guarantee. No action was executed.

## 44. Spoken Application Name Matching Prototype

An optional `CatalogSpokenAppResolver` now reads a cached snapshot of
registered application labels and configured spoken aliases. Only explicit
platform-ID-to-KYRIN-ID bindings are eligible. The command interpreter can use
it for simple English/Persian open-app phrases. Exact matches can form a final
command; approximate matches require confirmation and ambiguous labels require
a choice. The existing final-only `ActionGate` and explicit executor mapping
remain separate. The microphone diagnostic exposes opt-in bindings/aliases and
still executes no desktop actions. The similarity parameters are provisional,
and no product settings UI or cross-platform catalog exists yet. See
`docs/desktop/SPOKEN_APP_MATCHING.md`.

## 45. Verified English Command Decision Replay

On 2026-10-05 the five user-confirmed English command WAVs were replayed
through the selected local Vosk candidate, then both the confirmed references
and resulting transcripts were separately passed through the demo interpreter,
catalog-assisted app-name resolver, and final-only ActionGate. STT output was
identical to the prior five-file run (CER 29/107). No wrong action was
authorized. Two basic Telegram requests failed because STT misheard their
targets; two other commands failed even with perfect reference text because
the demo parser does not cover compound navigation or that English chat form.
No OS executor or microphone was used. The reusable decision replay tool and
full limits are in `docs/commands/VERIFIED_ENGLISH_COMMAND_REPLAY_2026-10-05.md`.

## 46. Pending English Reference Recheck and Shared-Audio STT Comparison

The owner later questioned whether every word in the English WAVs matches the
previously accepted reference text. The five clips were checked for audio
format and signal, then converted to a shared 16 kHz PCM set. On those same
files, local Vosk, `whisper.cpp` small, and quantized large-v3-turbo were
compared without network or desktop actions. Both Whisper variants recognized
the short `Open Telegram` clip where Vosk did not; small was faster than turbo
in this file-based CPU setup. The old-reference error rates are provisional,
and neither Whisper candidate has a production streaming adapter. The speaker
has been asked to listen to `en-01`, `en-02`, and `en-06`; any uncertain words
must be corrected or rerecorded before scoring. Details and limits are in
`docs/stt/ENGLISH_AUDIO_REFERENCE_AUDIT_2026-10-05.md`.

## 47. English Whisper Small Live Adapter

The speaker re-listened to `en-01`, `en-02`, and `en-06` and confirmed their
displayed reference wording. The owner chose to stop expanding the comparative
corpus for now and proceed with the locally installed Whisper `small` weights
for English STT development, prioritizing correct command text over the fastest
provisional response. This supersedes the earlier English Vosk default direction
for current development; it does not remove Vosk or choose a packaged default.

`src/kyrin/stt/backends/whisper.py` now implements the existing STT engine and
session contracts with optional turn hints. `whisper_server.py` owns a preloaded
local, CPU-only `whisper.cpp` server bound to loopback, with no model download or
new Python dependency. The live pipeline passes VAD-confirmed start/pause
markers in audio order only to turn-aware sessions. Streaming sessions such as
Vosk retain their independent source-to-STT conversion path. Whisper previews
are partial; only a full-turn re-transcription after a confirmed pause is final.
Turns over 30 seconds retract previews with empty final text. Listening remains
continuous across pauses.

Focused STT/pipeline tests passed. A local `en-02.wav` run produced provisional
`Open Telephone.` and final `Open Telegram.` with the real server; a paced file
run through Silero VAD and `LiveSpeechPipeline` produced partial and final
`Open Telegram`. No microphone or desktop command was used in these validations.
Measured live microphone latency, performance on other hardware, GPU support,
multi-language switching, and packaging remain open. See
`docs/stt/WHISPER_LIVE_ADAPTER.md`.

## 48. First Whisper Microphone Dry Run

The owner read `Open Telegram.` and `Do not open Telegram.` into the selected
USB microphone during a 25-second local, no-save, no-action diagnostic. The
first turn finalized as `Open Telegram.` and was authorized only as a dry-run
request. The negative turn finalized as `to open telegram.` despite the owner
confirming they spoke `Do not open Telegram.` exactly. The interpreter produced
no command for that text, so no action was authorized. Each final arrived
about 3.5 seconds after its VAD pause; backlog wait appeared near 1024 ms and
then recovered. A separate recorded-speed replay of the previously confirmed
`en-03.wav` through the same new pipeline preserved `Do not open telegram.`.
The live failure remains unexplained because the microphone audio was not
saved. The owner then consented to one 15-second local, Git-ignored WAV of the
same negative sentence at `datasets/stt/recordings/raw/live-negation-2026-10-05.wav`.
VAD found one speech interval; recorded-speed replay through the full new
pipeline finalized correctly as `Do not open telegram.` The original failure
did not reproduce and its exact cause remains unknown. A focused scheduler
fix now excludes pre-roll from the first-preview timer. On one subsequent
recorded-speed `en-02.wav` run, the correct final arrived about 1.92 seconds
after VAD pause. This is not a live microphone latency guarantee. See the
live-adapter document for conditions and limits.

## 49. Offline Spoken Repeat Prompt and Playback Guard

The owner approved text and offline voice feedback for unclear commands.
`CommandCoordinator` already emitted a `REPEAT_COMMAND` request with
`TEXT_AND_VOICE` only after an incomplete or unrecognized **final** command
transcript; partial text and ordinary speech stay silent. The demo interpreter
now also classifies the observed `to open telegram` STT result as unclear,
without authorizing an open action. A clear `do not open telegram` still
authorizes nothing.

`ResponseSpeaker` is a separate, replaceable speech-output contract with a
bounded background queue. The Ubuntu adapter uses local Speech Dispatcher and
its `espeak-ng` module. The `commands` microphone diagnostic prints the
localized text and speaks responses requested as `TEXT_AND_VOICE`, unless
`--no-voice-responses` is supplied. It still never executes desktop actions.
`PlaybackGuardInput` preserves continuous microphone capture but substitutes
silence while a response is queued/playing and for a short tail, preventing
the diagnostic from feeding its own voice back to VAD/STT in that interval.
The guard also suppresses user speech during playback; barge-in is not yet
supported. Text remains available on speech failures. No network or new
Python dependency was introduced.

Focused unit tests cover final-only repetition, the dropped-negation result,
asynchronous speech dispatch, backend command construction, and audio guarding.
A local `spd-say` playback command returned successfully on the development
machine. Audible output and real microphone echo behavior still need owner
listening validation. See `docs/responses/OFFLINE_SPEECH_OUTPUT.md`.

## 50. Owner-selected TTS Trial and Ordered English Commands

In a local, Git-ignored listening trial, the owner preferred the English
Kitten v0.2 sample over Piper after adjusting their speaking rates. This is a
**temporary voice preference**, not a product dependency, packaged voice, or
new default. The owner deferred TTS integration and wants to revisit voice
quality later. Trial files are under `downloads/tts-trials/`; product code was
not changed for this comparison.

The owner approved ordered commands and explicitly chose partial completion:
when a later step is unsupported, perform an earlier supported step and tell
the user what remains undone. `CommandPlan` and `CommandPlanResolution` now
represent two or three ordered intents from one final utterance. The current
demo parser recognizes exact two-step English forms such as `Open Telegram and
open Alice chat`; it does not claim general compound-language understanding.
`ActionPlanRunner` applies `ActionGate` and an injected executor one step at a
time, with a distinct action key per step. It stops on a block, failure,
unknown result, or pending confirmation. Before a supported chat step it
requires a fresh foreground-app observation; `LAUNCH_ACCEPTED` or old context
cannot stand in for that observation. An
unsupported chat step gives a specific localized notice after an earlier app
step. The microphone diagnostic prints this plan and per-step dry-run gate
decisions, but still executes no desktop actions. Focused tests use a fake
executor. See `docs/commands/MULTI_STEP_COMMANDS.md`.

## 51. Controlled Ubuntu Live Open-App Dispatch

The owner approved a bounded microphone-to-application integration after
reviewing the existing dry-run command and action layers. The live diagnostic
still defaults to dry-run. With `--mode commands`, `--execute-actions`, and
explicit `--launch-app KYRIN_APP_ID=/absolute/path.desktop` bindings, a final
command decision may launch only a bound app through the existing
`LinuxDesktopEntryExecutor`. The action policy uses those same app IDs as its
allowlist. No dependency or core action contract changed.

Single-step finals pass through `ActionGate`, `ActionExecutor`, and
`record_result`; ordered plans pass through `ActionPlanRunner`. Partial
transcripts never reach execution. The diagnostic prints localized action
feedback, preserving the distinction between `LAUNCH_ACCEPTED` and confirmed
completion. Chat and all other desktop actions remain unsupported. Focused
tests cover final-only execution, correction from a partial open command to a
negated final, unknown text, allowlist denial, duplicate suppression, and
ordered-plan stopping behavior without touching desktop hardware. In an owner
validated microphone smoke test, Whisper finalized `Open Telegram.` and the
launcher returned `LAUNCH_ACCEPTED`; the owner confirmed the Telegram window
opened. This is a single local observation, not a general STT accuracy claim.
The initial 45-second run then failed while stopping microphone capture. A
short graceful-read wait with abort fallback was added; a later five-second VAD
run and eight-second Whisper run both ended normally with exit code zero. The
full voice-to-action run was repeated during the queued-dispatch work below. See
`docs/actions/LIVE_OPEN_APP_INTEGRATION.md`.

## 52. Bounded Ordered Action Worker

The owner approved moving live OS actions off the microphone event consumer
before making KYRIN a persistent listener. In explicit execution mode, final
single-step decisions and ordered plans enter a small bounded FIFO. One
`QueuedActionDispatcher` worker owns the existing `ActionGate` and Linux
executor, preserving their order and avoiding shared mutable policy state.
Partial transcripts and no-command finals are not enqueued. A full queue
returns a localized `BUSY` notice; on shutdown, commands that have not started
receive `CANCELLED` notices, and an active action gets bounded completion time.
Dry-run mode remains synchronous and never invokes an executor. No new
dependency or platform action was added. Focused tests cover blocking executor
behavior, order, capacity, cancellation, and an ordered plan. A 25-second live
Whisper-to-queued-action run finalized `Open Telegram.`, produced
`LAUNCH_ACCEPTED`, and exited with code zero. The owner confirmed Telegram
opened or became active. Automated window verification and broader latency
measurements remain open. See `docs/actions/LIVE_OPEN_APP_INTEGRATION.md`.

## 53. Fresh Foreground Confirmation After App Launch

An optional `ObservedAppExecutor` wraps the platform launcher only when an
exact GNOME active-app binding is configured. After a `LAUNCH_ACCEPTED` result,
it makes a small bounded set of fresh foreground observations. A match with
the requested internal app ID produces `CONFIRMED` and carries
`observed_active_app` through `ActionGate` into user feedback; otherwise the
accepted result is unchanged. Only feedback with a matching observed app says
the requested app is now active. This confirms foreground state at observation
time, not whether the launcher created a new window or caused focus to change.
No new dependency was added. Unit tests cover matching, delayed, missing, and
mismatched focus. A 30-second live Whisper command finalized `Open telegram.`,
reported `CONFIRMED`, and exited cleanly. The owner confirmed Telegram became
active. See `docs/actions/LIVE_OPEN_APP_INTEGRATION.md`.

## 54. Consecutive Live Commands and App Process Lifetime

A 45-second live microphone test recognized and dispatched four separate final
commands in one listening session: Telegram, browser, Telegram, browser. The
owner confirmed the same foreground sequence. The first two launches returned
`LAUNCH_ACCEPTED`; fresh observations confirmed the later two. Listening did
not stop after the first action. The owner also noticed Chrome closing at the
end of the diagnostic. A local reproduction showed Chrome running in the
diagnostic's process session and exiting when that session ended. Starting
`gio launch` in a separate process session kept Chrome open after the launching
command exited. The Linux executor now requests a new session for the launcher;
focused automated tests assert that invocation. This does not change action
result semantics or claim portability beyond the observed Ubuntu/GNOME setup.

## 55. Opt-In Continuous Listening Trial

The owner approved a controlled longer listening trial before a packaged
always-on application. The command microphone diagnostic now accepts
`--until-stopped`, mutually exclusive with the existing `--seconds` option.
Its default remains a 10-second dry run, and bounded runs still cap at 120
seconds. The opt-in mode keeps the same `SpeechSessionController`, command
coordinator, action queue, and engine alive until Ctrl+C or a terminal error.
Silence does not reset command context. Manual interruption requests controller
stop before the existing cleanup closes the action worker, optional speaker,
and STT engine. The mode does not save audio or enable actions on its own.
Focused tests cover argument boundaries and resource cleanup without opening a
microphone. A roughly three-minute dry-run microphone trial on this Ubuntu
machine kept listening across about 90 seconds of silence and later recognized
`Open browser.`; earlier it misheard `Open Boser.` and issued no action. The
owner thinks they repeated the final browser phrase, so the two final browser
segments are not evidence of an unintended duplicate. Several Telegram finals
were also produced. Backlog wait/ready notices occurred, but no overflow or
recovery failure was observed. Manual Ctrl+C exited with code zero, and both
the diagnostic Python process and the local Whisper server were gone afterward.
Two process snapshots showed roughly 94 MiB RSS for the diagnostic and
637–641 MiB RSS for the Whisper server; this short run cannot establish
long-term memory stability. No desktop action or audio recording occurred.
See `docs/actions/LIVE_OPEN_APP_INTEGRATION.md`.

## 56. Reusable Live Command Runtime

The owner approved moving continuous command orchestration out of the terminal
diagnostic. `LiveCommandRuntime` in `src/kyrin/runtime/command_runtime.py` now
consumes `SpeechSessionController` events, asks `CommandCoordinator` for
decisions, reads fresh app focus only for final transcripts, and routes final
commands through the existing bounded action worker. In dry-run mode it uses
the same action policy without launching applications. Session boundaries
invalidate provisional speech segments but do not clear dialogue context;
silence alone has no reset behavior. The runtime exposes `run()` and `stop()`
and sends events to injected presentation callbacks. The terminal diagnostic
still selects microphone, VAD/STT adapters, Linux bindings, response output,
and optional timer, and owns the STT engine and speaker cleanup. No new
dependency, default action permission, platform integration, or model choice
was introduced. Deterministic tests cover multiple finals across a stream
boundary, partial-positive/final-negated speech, worker execution, and the
existing manual stop path. A packaged background app and longer stability
validation remain future work.

## 57. Registered App Names from Explicit Launch Bindings

The owner prioritized correct execution and asked KYRIN to use system app
names and desktop context without slowing the live audio path. The Ubuntu
command diagnostic now identifies an exact `--launch-app` desktop-entry path
in the XDG registered-app catalog at startup. For such entries it automatically
binds the installed display name and the configured internal app ID to the
existing `CatalogSpokenAppResolver`. The interpreter can recognize that name
without a duplicate `--spoken-app-binding`; near matches still require user
confirmation and `ActionGate` still restricts actual execution to explicitly
allowed apps. Unregistered paths gain no inferred name, and conflicting
explicit bindings fail at startup. The resolver uses a startup snapshot, so
no catalog scan is added to each partial transcript. Fresh foreground state
continues to be read only for final transcripts when explicitly configured.
Deterministic tests use temporary desktop entries and a fake executor. Names
that overlap command syntax, such as a name beginning with "Chat", remain an
open interpreter ambiguity. No system settings are changed or UI internals
inspected by this step.

## 58. Exact App-Name Versus Chat-Command Ambiguity

The owner prioritized command correctness before other incomplete work. A
registered app such as "Chat One" previously matched the chat-command grammar
before the spoken app name was considered. The demo interpreter now detects a
unique plausible registered app name that also matches a chat form and emits an
app-or-chat clarification on a final transcript. The app opens only after an
explicit "app" reply; "chat" follows the existing fresh-context rules. A
generic "yes" repeats the question, while a negated final never acts. Such an
ambiguity inside a compound command rejects the whole plan to avoid executing
an uncertain fragment. This is a safety rule for the limited demo interpreter,
not general natural-language disambiguation. Focused tests use a fake catalog
and do not launch desktop apps. No STT/TTS backend or new dependency changed.

## 59. First Ubuntu Application Settings Slice

The owner approved building the Ubuntu application in ordered slices and
specified automatic start after user login, an in-app listening switch, and
visible CPU/GPU/AUTO choices for both STT and TTS. An unavailable GPU choice
must explain the reason and keep the last valid active setting rather than
disappearing or silently falling back. The current Vosk/Whisper adapters still
support CPU only, and TTS has no compute-device or speed contract yet.

`AppSettings`, `SttSelection`, and `AllowedApp` now describe immutable saved
preferences. The default requests login start and listening, but selects no
STT model, enables no desktop action, and grants no app binding. The future
application must enter setup without microphone capture in that state.
`JsonSettingsStore` uses an injected absolute path and version-1 JSON; the
Linux path helper points to the user's XDG config location. Missing files
return defaults. Invalid, duplicate-key, or unknown-version files raise a
settings error and are not overwritten. Saving writes a private temporary
file in the same directory and atomically replaces the old file. Tests use
temporary directories and cover round trips, preservation on bad input or a
failed replacement, permission defaults, and path selection. This slice does
not create real user settings, autostart entries, a running application, or a
model manager. No dependency was added.

## 60. UI-Independent Application Lifecycle

The next approved slice added `ApplicationController` in
`src/kyrin/app/controller.py`. It receives saved settings and a factory for a
managed runtime session, rather than choosing STT, microphone, desktop, or UI
implementations itself. Listening disabled yields PAUSED; a missing STT model
yields SETUP_REQUIRED without constructing audio. A configured session runs on
one worker thread. Stop requests do not wait on microphone shutdown in the
calling thread, and a second live session is rejected. Factory, runtime, and
cleanup errors remain visible through a status snapshot. RUNNING means the
runtime has begun, not that microphone capture has already been observed.
The factory's context manager remains responsible for closing the model,
speaker, and action resources. Tests cover pause/setup, stop during startup,
restart, duplicate prevention, slow stop, errors, and a real
`LiveCommandRuntime` with a fake event source. This slice changes neither the
terminal diagnostic nor the user's audio devices, settings, startup entries,
or model files. A concrete factory and product UI remain future work.

## 61. Ubuntu Live Session Composition

The owner approved the next implementation slice. `UbuntuSessionFactory` in
`src/kyrin/app/platforms/ubuntu.py` now connects saved app settings to the
existing live runtime. A microphone resolver records a stable host-API/name
selection and resolves the current PortAudio index before startup and on each
retry. Missing or ambiguous selections fail visibly. Vosk and Whisper remain
replaceable through injected STT openers; their standard adapters are CPU-only
and reject explicit GPU rather than falling back silently. The factory
preserves the existing VAD, speech-session recovery, command coordinator,
action gate, optional desktop observer, response presenter, optional visual
adapter, and optional injected speech synthesizer. Installed app names and
launch paths are limited to explicit allowed-app desktop-entry bindings;
actual action execution remains disabled by default. Focused fake-adapter
tests cover dry run, allowlisting, setup failures, and resource cleanup. No
physical microphone, real desktop launch, user settings file, login startup,
new dependency, or model download was used in this slice. The Ubuntu control
window and model/TTS settings remain future work.

## 62. First Qt Control Window

The owner explicitly selected PySide6. The project now offers its smaller
`PySide6_Essentials` distribution as an optional `desktop` extra and a
`kyrin-desktop` entry point. A small
right-to-left Qt window controls the existing `ApplicationController` and
persists microphone/STT choices through `JsonSettingsStore`; it does not move
audio work onto the GUI thread. Final transcript and presented response
events cross a Qt signal to the UI; their shared event type is independent of
Ubuntu and Qt. Explicit GPU remains visible and fails
without changing the last saved choice because the current STT adapters are
CPU-only. Applying a model change requests the old session to stop before
restarting. The window minimizes on close and has an explicit Quit control.
Offscreen tests with fake sessions cover GPU rejection, listening persistence,
stop-before-restart, and malformed settings preservation. `PySide6_Essentials`
6.11.2 was installed into `.venv` after the sandboxed download failed, and the
tests were rerun there. No live
microphone, real user settings file, login startup, or desktop launcher was
changed. Model management, TTS controls, packaging and single-instance login
startup remain open work.

## 63. English control center and static cosmic dashboard

The owner selected the dark fifth cosmic concept for the application and
requested English control text plus a path for adding UI languages later. A
multi-page Qt Widgets control center now separates Dashboard, Audio Input,
Speech Recognition, and Preferences. The built-in UI strings are English;
interface locale selection and complete JSON language-pack import are separate
from the STT language. The selected concept art is packaged as a static,
aspect-preserved dashboard image. The owner explicitly dropped real-time 3D
after reviewing its graphics and installation costs. The temporary Qt Quick 3D
scene and `PySide6_Addons` dependency were removed. The microphone/STT/runtime
controller interfaces were not changed. The app still lacks a portable
installer, TTS configuration, login startup, and a single-instance launcher.

The control-center follow-up made UI language loading recoverable: invalid
preferences or a missing selected pack now open English, show an error, and
leave the original file untouched. Catalog strings are cached rather than read
on every status update. Runtime language changes refresh the action status and
microphone label, while unsaved speech settings remain in the form. UI content
uses plain-text labels so transcripts and imported strings are not treated as
rich text. Qt tests inject a temporary UI config directory. A full test run
passed with 308 tests, and an isolated offscreen startup reached the event loop.
No physical desktop presentation or microphone validation was performed in
this follow-up.

## 64. One Qt control instance per user session

The next desktop-lifecycle slice adds a `QLockFile` held for the control
process lifetime and a local Qt socket in the user-session runtime directory.
Opening `kyrin-desktop` again sends an activation request to the existing
window, instead of constructing a second microphone runtime. A lock owner may
remove a socket abandoned by a crashed process; a second process may not take
over a live socket. The activation raises a minimized window. Tests cover
second-instance activation and abandoned-socket recovery without audio.
This slice does not install a desktop menu entry or register login startup;
the saved `start_at_login` preference still has no operating-system effect.

## 65. User-scoped Ubuntu launcher and login startup

The owner approved the next lifecycle step. `XdgDesktopRegistration` now
generates managed XDG desktop entries for the application menu and per-user
autostart directory. The Qt Preferences page exposes an explicit login-startup
control. Disabling it removes only KYRIN's autostart file. Unknown same-named
files are not overwritten, and a failed settings save attempts to restore the
previous registration. Unit tests use temporary XDG directories; both desktop
entries pass Ubuntu's `desktop-file-validate`. On this host, the owner-approved
registration was installed for the current user and points to
`/mnt/ai_projects/KYRIN/.venv/bin/kyrin-desktop`. The current settings have no
selected STT model, so a future login opens setup without microphone capture.
Real next-login behavior is not yet observed; the development-environment
launcher is not portable if the project directory moves. A stable packaged
installation and model-management UI remain future work.

## 66. Dashboard copy over the cosmic artwork

The owner clarified that the first dashboard should use the selected cosmic
image across the entire content panel, with the welcome title and two supporting
lines placed on the image. The previous separate right-hand copy panel was
removed. The black hole remains visible on the left; a translucent right-side
shade and a title shadow keep text readable. The existing UI language keys
still supply the text. The dashboard is a static image and does not add a
continuous rendering loop. Offscreen previews were inspected at the normal
window size and the current minimum size; live display feedback remains with
the owner.

## 67. Owner-selected original black-hole K logo

The owner chose the second of four black-hole logo concepts and explicitly
preferred its original generated image over a later simplified revision. The
original transparent PNG is copied unchanged into the Qt assets as
`kyrin-logo.png`. The control window displays it beside the KYRIN name; the Qt
application uses it as its window icon, and managed XDG desktop entries include
its packaged absolute path. The user's existing menu and autostart entries
were refreshed without changing their enabled state. A built wheel contains
the PNG and the desktop entries passed `desktop-file-validate`. An offscreen
window preview was inspected. A future packaged release may need
multi-resolution icon files.

The owner then reported that the applications menu showed a generic gear and
the running application's tooltip said `Python 3`. Inspection found that the
desktop entry already resolves to the selected PNG, but the Qt process did not
declare its matching desktop-file ID. Qt now sets that ID and its display name
to `KYRIN` before creating the window. The owner restarted the application and
confirmed that its menu/dock identity and icon now appear correctly.

## 68. Desktop action permissions in the Qt control center

The owner authorized completing five follow-up steps after a repository audit.
The existing Ubuntu control-center work was saved in local Git commit `6eb64f1`
without pushing to GitHub. The Qt window now has a Desktop Actions page with
searchable visible XDG launchers. The user can select explicit app bindings and
enable action execution; a session is stopped before changed settings are saved
and restarted. Saved hidden or removed entries stay visible for review.
Permission checks remain in the existing action gate, not in the page.

The Qt entry point now reuses the XDG catalog for both the picker and runtime.
It connects the existing GNOME active-app observer and visual-status sink only
when their optional Shell endpoints are available. The owner has previously
verified the character and a Telegram launch separately. The new end-to-end
control-center path has passed automated tests; its live voice test remains to
be confirmed. UI language packs imported before these new labels remain usable
with English fallbacks for the added strings; new imports require all labels.

## 69. Local Whisper GPU execution and actual-device reporting

The owner prioritized completing GPU STT on capable hardware while preserving
CPU and AUTO choices. The current `whisper.cpp` adapter can now start separate
CPU and CUDA-enabled server executables for the same model weights. CPU starts
with `--no-gpu`. Explicit GPU fails if the CUDA runtime is missing or does not
confirm a CUDA backend; it cannot silently fall back to CPU. AUTO first tries a
configured GPU runtime and falls back to CPU if GPU startup fails. Vosk remains
CPU-only. The session's actual compute device is emitted to the Qt control
center, separately from its selected preference. Paths are configured through
`KYRIN_WHISPER_SERVER` and `KYRIN_WHISPER_GPU_SERVER` or executable names on
`PATH`.

On this Ubuntu development machine, an isolated CUDA 13.1 toolkit and pinned
`whisper.cpp` v1.9.4 GPU build were placed under Git-ignored `build/tools/`.
The toolkit was not installed into the operating system. The existing
multilingual Whisper `small` weights worked on the local RTX 5060 Ti. Three
short recorded English clips had a warm mean request time of about 1.95 s on
CPU and 0.032 s on GPU; this small sample is not a general performance or
quality promise. A real GPU engine session returned the expected text and a
CPU-only binary placed in the GPU slot was rejected. A live microphone dry run
reported an actual GPU session and recognized `Open Telegram` without storing
audio or executing a desktop action. The two final segments matched the owner's
later clarification that they said the sentence twice. The desktop entry point
now discovers CPU and GPU server executables beside its installed script as
well as from explicit environment variables or `PATH`. Git-ignored links in
the local `.venv/bin/` point to the two builds; the app's discovery path opened
the GPU engine with the existing model successfully. This is local development
setup, not a portable runtime package. The detailed scope and remaining
release work are in `docs/stt/WHISPER_GPU_EXECUTION.md`.

## 70. Engine-aware speech model library in the control center

The owner requested separate CPU and GPU model views and import controls,
alongside a default view of all models. They clarified that a model usable on
both devices should be stored once and listed in both views. The control center
now includes those three views. It imports local Vosk directories and
`whisper.cpp` GGML files into a per-user XDG data library in a background
thread, using a private staging directory before publishing the model. The
library derives device compatibility from the backend: Vosk is CPU-only and
Whisper supports CPU or GPU with the appropriate runtime. Import location does
not itself assert compatibility. Reimporting identical content and language
uses the existing stored copy. The current external model path remains visible
and usable. Selecting from All requests AUTO; selecting from a device-specific
view requests that device and fills the existing Speech Recognition form for
explicit saving. The library does not download models or install GPU software.
Format checks are intentionally lightweight; actual model loading and hardware
availability are verified when the selected runtime starts. See
`docs/app/MODEL_LIBRARY.md`.

The owner found that both existing Whisper files were rejected by the new
importer. Investigation reproduced the problem: the on-disk GGML magic is a
little-endian integer, while the first implementation compared its bytes to
the display-order text `ggml`. The importer now reads the numeric magic in
little-endian order. Both local Whisper files passed validation and a full
temporary import, appearing in both CPU and GPU views. No user model files or
settings were moved during this diagnosis.

## 71. Desktop Actions picker usability

The owner reported that clicking an app row did not toggle its checkbox and
that selecting many apps required individual clicks. The Qt picker now treats
row clicks and checkbox clicks as one toggle each. It adds Select all shown and
Clear shown controls scoped to the current search results, plus a selected
count. With no search filter, Select all shown selects all listed installed
apps. Bulk selection never turns on action execution; the separate permission
checkbox and Save changes remain required. Qt mouse-click tests cover both
click targets and filtered bulk selection without modifying real user
permissions.

## 72. Read-only active-window observation foundation

The owner approved the first step toward desktop-aware browser and chat work:
an on-demand observation of the focused window before adding new actions.
`ScreenObserver` is a platform-neutral, read-only contract. An Ubuntu adapter
uses the existing GNOME extension's new desktop-ID/PID method and an isolated
AT-SPI helper to return bounded visible labels. It never clicks or runs a
command. A failed or ambiguous identity match returns unknown. The extension
update is installed for the current user but may require the next desktop
login/restart to expose its new method. Focused tests pass; product integration
and live end-to-end validation remain open. AT-SPI coverage varies by app;
Chrome did not expose a top-level window in the current diagnostic. See
`docs/desktop/SCREEN_OBSERVATION.md`. Telegram also exposed no top-level
AT-SPI window in this session. The screenshot portal is version 2 and local
Tesseract is absent, so OCR fallback is not yet implemented.

## 73. Explicit existing-window controls

After a restart, the owner confirmed that `Open Telegram` now brings an
already-running, minimized Telegram window forward. They approved separate
commands to restore, minimize, and close an existing application window.
`CLOSE_APP_WINDOW` means a normal window close request, not process termination;
full application quit remains a distinct future behavior. Maximize, return to
normal size, fullscreen, and exit fullscreen were added before a planned GNOME
session restart, using the same window-control permission. The interpreter,
action gate, persisted settings, control-center permissions, platform-neutral
controller, and GNOME adapter now support these window commands. New window
permissions default to off for existing settings. When an app has multiple
windows, GNOME selects the focused window only if it belongs to that app;
otherwise KYRIN asks the user to focus the desired one. Verification uses an
opaque stable window token so a focus change cannot accidentally verify a
different window. The updated extension source still needs to be installed
for the user before the next GNOME login. The prior version remains loaded in
the current session, and real desktop behavior is not yet validated. See
`docs/desktop/ACTIVE_APP_OBSERVATION.md`.

## 74. Two-step system power requests

The owner approved shutdown, reboot, logout, and suspend requests with a
warning about possible unsaved work and two confirmations. Either confirmation
may be spoken or clicked. A separate opt-in setting defaults off. The power
flow is independent of microphone session lifetime so the on-screen buttons
work when listening is unavailable. Spoken input is accepted from final STT
transcripts only. A bounded GNOME session-inhibitor query informs the warning,
but cannot establish that every editor buffer is saved. The adapter uses
GNOME's normal session methods and does not bypass native prompts or blockers.
Focused deterministic tests pass; no live system-power action has been run.
See `docs/actions/SYSTEM_POWER_ACTIONS.md`.
