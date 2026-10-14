# Ubuntu application lifecycle and settings design

Status: settings, lifecycle controller, Ubuntu session factory, optional Qt
control window, single-instance activation, user-scoped XDG launcher, login
startup registration, and local TTS selection are implemented. Portable
packaging remains planned. The historical milestones below may describe earlier
TTS limitations; current behavior is in
[TTS_MODEL_MANAGEMENT.md](../responses/TTS_MODEL_MANAGEMENT.md).

## Goal and current boundary

KYRIN should start in the user's graphical session after login, listen without a
microphone-button press when listening is enabled, and remain controllable from
an ordinary application window. It must work offline once its selected models
are installed. The window, the optional GNOME character, and the live command
runtime have different responsibilities.

Today `LiveCommandRuntime` already routes speech, command decisions, and bounded
actions. `scripts/audio/check_live_speech.py` still chooses the concrete audio
device, STT backend, responses, and desktop adapters from terminal arguments.
There is now a product settings data model, file store, lifecycle controller,
Ubuntu session factory, and a multi-page control window. The Preferences page
can register login startup for the current user. The factory chooses a
microphone, STT engine, response presenter, and bounded desktop action adapters
from explicit settings. The STT contract accepts AUTO/CPU/GPU requests. Vosk
advertises CPU only; Whisper can use a separate CUDA-enabled runtime when one
is installed. Voice Output now selects supported local TTS models, language
routes, speakers, speed where the engine supports it, and AUTO/CPU/GPU
preference. The selected adapter and runtime validate actual compatibility;
see [TTS model management](../responses/TTS_MODEL_MANAGEMENT.md).

## User-visible controls

Three controls must remain distinct:

| Control | Immediate effect | After the next login |
| --- | --- | --- |
| Listening on/off | Start or stop microphone capture and the live runtime; keep the control application available. | Persist the chosen listening state. If off, the app starts without opening the microphone. |
| Start at login on/off | Change the user's login startup registration; do not interrupt the current session. | Start KYRIN only when this setting is on. |
| Quit | Stop the runtime, release the microphone, STT engine, speaker, and action worker, then exit the process. | Does not change either saved setting. |

Hiding the character or closing the settings window must not change listening.
Opening KYRIN from the desktop launcher while an instance is running should
show the existing control window instead of starting another microphone
session. A shutdown or process exit clears in-memory conversation context;
silence and system sleep do not deliberately erase it.

Login startup belongs to the signed-in user's graphical session, not a root
system service before login. Microphone, sound output, desktop actions, and the
GNOME status adapter are session resources. The login startup option should be
enabled by default when a completed application installation registers it,
while the user can disable it from settings.

## Settings and startup sequence

The application core should receive validated settings as typed values rather
than read a machine-specific file itself. A Linux settings adapter can store a
versioned, human-readable file in the user's configuration directory. Paths
and device identities must not be embedded in the repository or assumed to be
the same on another computer. A save should replace the file atomically; an
invalid or unreadable file must be reported and preserved for repair rather
than overwritten with defaults.

For the first implementation slice, propose JSON with `schema_version: 1` at
`$XDG_CONFIG_HOME/kyrin/settings.json` (or `~/.config/kyrin/settings.json`
when that variable is absent). The settings store must also accept an injected
path so tests never use a real home directory. JSON uses the Python standard
library and does not add a dependency. The typed settings model remains
platform-neutral; only the Linux path resolver knows the XDG location. An
unknown schema version is an explicit setup error, not an invitation to guess
or overwrite. Future migrations require their own reviewed change.

Initial settings need to describe:

- Whether listening and login startup are enabled.
- Selected microphone, including a system-default choice. Device index alone
  is not a durable identity across reboots; selection needs a resolution step
  against currently available devices.
- STT backend, installed model, language, and AUTO/CPU/GPU preference.
- Selected TTS backend, local model, voice, language route, and separate
  AUTO/CPU/GPU preference. The adapter validates a requested device before
  applying it; unavailable GPU support produces an error and preserves the
  previous valid setting. Speed is available only where the selected engine
  and installed processing tools support it.
- Explicitly allowed desktop applications and whether action execution is
  enabled. No application receives permission merely because it is installed.
- Optional visual feedback and response-language preferences.

The startup sequence is:

1. Load and validate settings; obtain a single application instance.
2. Check the selected model, backend, requested device, microphone, and desktop
   permissions. The selected STT engine must load before microphone capture.
3. If listening is off or setup is incomplete, keep the control app available
   and show a clear status without opening the microphone.
4. Otherwise construct concrete adapters around the existing
   `LiveCommandRuntime` and begin continuous listening.
5. On stop or quit, request runtime stop and release owned resources in order.
   A failed stop must be visible rather than reported as success.

A bad model, missing microphone, or unavailable requested GPU must leave the
application controllable. The app must not silently switch an explicit GPU
request to CPU. AUTO may select CPU when that is the only supported and usable
choice; the UI should show the device actually selected. AUTO is not a promise
of globally optimal speed. Hardware support, model/backend capability, memory,
and measured performance must be considered before claiming a faster option.
The CPU, GPU, and AUTO choices remain visible for both STT and TTS. If a user
selects GPU but it cannot be used, do not apply the change; explain the actual
reason, such as no compatible GPU, no GPU-capable backend for the selected
model, or missing GPU runtime support. Do not assume that every model needs a
separate GPU weight file: the backend determines whether the selected model can
run on a device. Keep the last valid setting active until a compatible choice
is installed or selected.

## Component responsibilities

```text
Settings window / desktop launcher / user-session login startup
                  ↓
Application controller (one instance, start/stop, visible errors)
                  ↓
Validated settings + backend and platform adapter selection
                  ↓
SpeechSessionController → LiveCommandRuntime → action policy/worker
                  ↓
Text/voice/optional GNOME visual presentation
```

The application controller owns lifecycle and resources. It does not parse
speech or implement actions. The existing runtime remains independent of the
UI toolkit, STT/TTS provider, and operating-system login mechanism. Linux
login startup, microphone enumeration, and desktop launch remain adapters so
future Windows, macOS, and mobile work does not require rewriting the core.
The terminal diagnostic remains available for focused debugging.

## Ordered implementation slices

1. Define typed, versioned settings and the JSON store with an injected path.
   The first slice covers startup/listening preferences, a default-microphone
   selector, explicit STT model/backend/language/device preference, and an
   empty-by-default action allowlist. TTS GPU cannot become an active setting
   until its contract and backend support can validate it; the later UI must
   still offer the option and explain why it is unavailable. Test load/save,
   atomic replacement, unsupported schema, malformed settings, and safe defaults
   without touching real user settings.
2. Create a reusable application composition/lifecycle layer around the
   existing runtime. Test start, stop, restart, missing model/microphone, and
   orderly cleanup with fake adapters.
3. Choose and validate an Ubuntu UI toolkit and packaging path against the
   project's Python version, accessibility/RTL requirements, and installation
   method before adding a dependency. Build the small control/settings window.
4. Add a desktop launcher and user-session login startup with a single-instance
   behavior. Validate start, stop, reboot/login, and disabled listening on the
   owner's Ubuntu desktop.
5. In the subsequent model-management stage, add installed-model discovery,
   import/download, compatibility checks, and user selection without code
   edits. Extend TTS contracts and UI capability reporting before applying
   model, speed, or GPU settings that current backends cannot honor. Keep those
   choices visible with a reason when unavailable.

## Decisions and checks still required

- Confirm the UI toolkit and distribution/install mechanism. A development
  virtual environment path is not a portable desktop launcher.
- Define a durable microphone selector and behavior when that device is gone.
- Decide the exact safe migration and recovery behavior for future settings
  schema versions.
- Extend GPU validation beyond the current local NVIDIA Whisper test to
  release targets. Vosk remains CPU-only; current TTS has no device or speed
  contract.
- Decide how the control window is reopened when the optional GNOME character
  is hidden, while guaranteeing only one live microphone session.

## First slice implemented

The numbered slice descriptions below record the implementation at that
point in time; later sections describe subsequent changes.

`src/kyrin/app/settings.py` defines immutable preferences. The default has
login startup and listening requested but no STT model selected and no desktop
action permission; the later application must therefore show setup without
opening the microphone. An STT GPU preference may be saved, but storage does
not claim that the chosen backend or current hardware supports it. That check
belongs to application startup and the selected engine.

`src/kyrin/app/settings_store.py` reads and atomically replaces a version-1
JSON file. Its caller supplies an absolute path, and a Linux helper computes
the proposed XDG location without creating it. Missing files return safe
defaults. Malformed, duplicated, unknown-version, or otherwise invalid data
raises `SettingsError` without overwriting the source. The first slice is not
connected to the terminal diagnostic or a new application process. No real
user settings, system startup entry, model download, or new dependency was
changed by this implementation.

## Second slice implemented

`src/kyrin/app/controller.py` supervises one injected runtime session from a
worker thread. With listening turned off, it reports Paused without creating
the session; with no selected STT model, it reports Setup Required. Otherwise
it reports Starting, then Running, and supports a nonblocking stop request.
Running means the session's `run()` method has begun; it does not assert that
microphone capture has already produced audio. The future UI can use live audio
events for a precise listening indicator. The controller refuses a second
active session, retains startup/runtime/cleanup failures for the UI, and waits
for both run and stop work during shutdown. Its injected context manager owns
release of the STT model, microphone, speaker, and action worker. Focused tests
use fake resources and one real `LiveCommandRuntime` instance with a fake audio
event source; they never access microphone hardware or user login settings.

## Third slice implemented

`src/kyrin/app/platforms/ubuntu.py` builds a managed `LiveCommandRuntime`
session from validated settings. It resolves a saved microphone by host API
and device name at startup and again for each retry, since PortAudio indices
can change. An absent or ambiguous device stops setup with a visible error;
there is no silent switch to another microphone. The default microphone is
resolved through the current PortAudio default. The factory opens an installed
STT backend and passes the language and AUTO/CPU/GPU request through the
existing engine-independent contract. A requested GPU that the chosen adapter
cannot support raises `DeviceUnavailableError`; it never silently uses CPU.
The current built-in Vosk and Whisper adapters remain CPU-only, and Whisper
still needs an explicit local `whisper-server` path.

Only registered desktop entries that also have an explicit allowed-app binding
are given launch paths and spoken installed names. Action execution still
defaults to off; no program is launched by constructing the factory. Optional
visual and voice adapters remain injected. Text responses and structured
events are always emitted; no TTS model or voice is selected by current
settings. The application UI must marshal callback events from audio/action
threads to its own UI thread.

Focused tests use fake microphones, engines, event sources, and executors to
cover dry run, exact app allowlisting, disabled action execution, unavailable
microphone, explicit unsupported GPU, and unknown STT backend. These tests do
not prove behavior with a physical microphone, desktop action, real settings
file, or login startup. The terminal diagnostic remains independent.

## Fourth slice implemented

The owner chose PySide6 for the desktop control surface. Only the Qt Widgets
capable `PySide6_Essentials` distribution is in the optional `desktop` extra.
The core application and audio
runtime do not import Qt. `kyrin.app.qt.window.ControlWindow` shows lifecycle
status and recent text responses, lists microphone inputs, accepts an installed
Vosk or Whisper model path and language, and exposes AUTO/CPU/GPU for STT.
Current CPU-only adapters reject GPU with a visible message and do not replace
the previous saved settings. A missing microphone, model path, or Whisper
server is also reported before new settings are saved. The user can start or
stop listening; a model change stops the old session before saving and starting
the new one. The UI event bridge delivers worker-thread events through a Qt
signal on the GUI thread; its event type is defined outside the Ubuntu adapter.
Closing the window minimizes it without stopping
listening; the explicit Quit button requests cleanup and exits afterward.

The entry point is `python -m kyrin.app.qt.main` (or `kyrin-desktop` after
installation). It reads the existing XDG settings location but does not create
it until the user saves. A malformed settings file is shown as an error and
cannot be overwritten from the window. The Whisper server must be installed
on `PATH` or supplied as an absolute executable in `KYRIN_WHISPER_SERVER`.
At this fourth slice, action permissions already in settings remained unchanged
and were not yet editable in the window. Later sections describe their editor,
login startup, and the single-instance launcher. TTS selection, voice speed
and device controls, model import/download, and a portable installed-app
package remain later work. Qt tests use offscreen
rendering and fake sessions; they do not turn on the owner's microphone or
alter the owner's settings file. On this host, `PySide6_Essentials` was installed
in the development virtual environment and Qt tests passed there. The initial
sandboxed package install was blocked by network policy; the approved
environment install succeeded.

## Current control-center presentation

The control window now has separate Dashboard, Audio Input, Speech Recognition,
Desktop Actions, and Preferences pages. The owner selected the fifth dark cosmic concept as the
Dashboard artwork. After a real-time 3D prototype was reviewed, the owner
chose a static dashboard to avoid its graphics and package cost. The selected
PNG is included in the Python package; it is aspect-filled without stretching
and is not continuously rendered. `PySide6_Addons` and the experimental QML
scene are not required. Audio and command execution still use the same
independent controller and worker-thread event bridge.
The owner later asked for the welcome copy to sit on the image rather than in
a separate side panel. The artwork now fills the dashboard content area, with
the title and supporting lines over its darker right side. A subtle gradient
and text shadow maintain contrast at the normal and minimum window sizes.

All built-in control-window labels are English. The interface locale is
independent of the selected STT language. Preferences can import a complete
JSON UI language pack and select it without changing application code. A pack
has `locale`, `name`, and `strings` fields; `strings` must include every key in
`kyrin.app.qt.translations.ENGLISH`. Installed packs and the selected locale
live under the user's KYRIN XDG config directory. No additional language pack
is bundled yet. Response text and transcripts are user content and may remain
in the spoken language.

Invalid UI-language preferences or a missing selected pack do not block
startup. The app opens with English controls, reports the issue, and preserves
the affected file until the user explicitly saves a new language choice.
Details for pack authors and users are in `docs/app/UI_LANGUAGE_PACKS.md`.

## Single-instance control process

The Qt entry point now holds a `QLockFile` for the process lifetime and listens
on a local socket in the user-session runtime directory. A second invocation
activates the existing control window and exits before creating audio adapters.
The lock owner can clear a socket left by a crash. If the existing window
cannot be contacted, startup reports an error instead of risking a second
microphone session. This behavior is covered with local-socket tests.

## Per-user desktop and login registration

`XdgDesktopRegistration` writes one managed desktop entry under
`$XDG_DATA_HOME/applications` and a matching entry under
`$XDG_CONFIG_HOME/autostart` when the user enables **Start KYRIN when I sign
in**. The Preferences control is explicit: the saved `start_at_login` value
alone never writes an operating-system entry. Disabling the option removes only
the managed autostart entry, leaving the menu launcher. A same-named entry
without KYRIN's ownership marker is preserved and reported as an error.
Writes use a temporary file followed by atomic replacement. If saving the
application preference fails, the previous autostart registration is restored.
The generated entries passed `desktop-file-validate` on Ubuntu. The current
development installation points to its `.venv/bin/kyrin-desktop`; a portable
installer must provide a durable executable path and re-register the entry.
The owner's actual login/reboot behavior remains to be validated after the
next login.
The owner selected the original second black-hole K concept as the application
logo. Its transparent PNG is packaged with the Qt assets, shown in the control
window, and referenced by the managed menu and autostart desktop entries.
The logo was later rerendered with more realistic lighting while retaining its
K silhouette and black-hole center. The earlier PNG remains beside it as
`kyrin-logo-original.png`; `kyrin-logo.png` is the active asset at the same
path used by existing desktop entries.
The Qt process also declares the same desktop-file ID as the menu entry and
sets the display name to `KYRIN`, so the desktop can associate its live window
with that launcher instead of showing the Python runtime as the application.
The owner restarted the application and confirmed that the menu/dock identity
and icon appear correctly.

## Desktop action permissions and GNOME integration

The Desktop Actions page lists launchable, visible applications from the XDG
desktop catalog. Search matches the displayed app name and desktop-entry ID.
The user can save an explicit allowlist and enable action execution only when
at least one app is selected. Hidden or removed entries in existing settings
remain visible in the picker so they can be reviewed or removed. Saving stops
the current listening session before applying settings; a restarted session
uses the new allowlist. The command gate still checks the saved permission
before launching an app.

The picker also toggles an app when the rest of its row is clicked; clicking
the checkbox itself still toggles only once. **Select all shown** and **Clear
shown** act on entries visible under the current search filter. With no
search, Select all shown selects all listed installed apps. A selected-count
label makes the scope visible. Bulk selection does not enable action execution;
the separate permission checkbox and Save changes remain required.

When the optional GNOME Shell extension endpoint is available, the Qt entry
point also connects the existing active-app observer and visual-status sink to
the live session. Missing GNOME integration leaves the control window usable;
it does not loosen action permissions. Neither adapter is a requirement for
other desktop environments or future operating-system implementations.

## Whisper CPU and GPU runtime selection

The STT device setting now selects a concrete Whisper runtime before its model
process starts. CPU passes `--no-gpu`; GPU requires a separately installed
CUDA-enabled executable and a positive CUDA-backend startup confirmation.
AUTO tries that GPU runtime when configured and falls back to the CPU runtime
if GPU startup fails. An explicit GPU request fails visibly instead of silently
using CPU. The opened STT session reports its actual compute device to the
control window. Vosk remains CPU-only and its GPU choice stays visible with an
unavailable message. This does not change the TTS compute-device design.

Development runtime paths can be supplied through `KYRIN_WHISPER_SERVER` and
`KYRIN_WHISPER_GPU_SERVER`; installed commands named `whisper-server` and
`whisper-server-gpu` are also discovered beside the `kyrin-desktop` script or
on `PATH`. The local CUDA build is an
ignored development artifact rather than a portable application package.
See `docs/stt/WHISPER_GPU_EXECUTION.md` for the hardware result and test scope.
