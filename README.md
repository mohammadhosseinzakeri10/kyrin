# KYRIN

An open-source, modular AI desktop agent under active development.

For a map of the source, tests, models, and installed local data, see
[project layout](docs/development/PROJECT_LAYOUT.md).

## Vision

KYRIN is an intelligent AI agent designed to understand voice, vision, and text, and interact with the operating system naturally like a human.

## Current status

KYRIN runs as a local Ubuntu/GNOME desktop application with continuous
microphone listening, a PySide6 control center, and an optional movable GNOME
status character. Its components separate audio acquisition, replaceable STT,
bounded command understanding, permission-gated actions, optional screen/OCR
observation, TTS, and responses. The current user's session can start KYRIN at
login; the control center can pause listening or quit. Opening the launcher
again activates the existing window. This development installation is not yet
a portable, self-contained release.

The control center has separate pages for audio input, speech recognition,
local speech models, command understanding, voice output, desktop actions,
screen access, and preferences. English and Persian interface text are built
in; other interface languages can be imported from local JSON packs. The
selected black-hole K logo appears in the window and Ubuntu launcher. Models
are selected from local files; KYRIN does not download model weights in the
application. The **Model Library** shows installed STT models in All, CPU,
and GPU views and stores compatible Whisper weights only once. See
[model library](docs/app/MODEL_LIBRARY.md),
[interface language packs](docs/app/UI_LANGUAGE_PACKS.md), and
[voice management](docs/responses/TTS_MODEL_MANAGEMENT.md).

The current Ubuntu action path can open or activate explicitly allowed apps,
control supported windows, and show a numbered open-window overview. Telegram
Saved Messages and named-chat selection have passed live speech-to-action
checks, including the owner's choice of a second visible same-name chat.
Other layouts and Persian titles still need live validation. Screen and
keyboard permissions can be remembered and
revoked in the app. System power actions require separate permission and two
confirmations; the owner has also reported successful real Power Off and
Restart voice flows, while Logout and Suspend remain unverified live.
Finalized speech text can be retained in a bounded local conversation history;
audio is not stored by that feature.

For spoken command examples and their meanings, see the [Persian command guide](docs/commands/USER_COMMAND_GUIDE_FA.md).

Vosk currently runs on CPU. Whisper can use CPU or a separately installed
CUDA runtime on supported NVIDIA hardware; the same weights serve both. A
local Omnilingual ASR runtime can use one of six separately stored v2
checkpoints through an isolated Python worker. Its model comparison and
current hardware limits are documented in
[local speech model comparison](docs/stt/LOCAL_MODEL_COMPARISON_FA.md). A
local Ollama command model can assist the live interpreter behind independent
source-text and action-permission checks. The interpreter is still bounded:
automatic language detection, arbitrary phrasing, and general multilingual
desktop control are not guaranteed. STT, TTS, and command-model weights are
not bundled by default.
See [Whisper GPU execution](docs/stt/WHISPER_GPU_EXECUTION.md),
[command-model integration](docs/app/COMMAND_MODEL_LIVE_INTEGRATION.md), and
[OCR architecture](docs/vision/OCR_ARCHITECTURE.md).

## Development entry point

For pinned check-environment dependencies and the shared local/CI quality gate,
see [quality checks](docs/development/QUALITY_CHECKS.md). These checks need no
external model weights or personal data; existing type-check failures remain
visible and fail the gate.

Python 3.14 or newer is required by the current package. From a configured
development environment, inspect the microphone diagnostic options with:

```bash
.venv/bin/python scripts/audio/check_live_speech.py --help
```

The diagnostic needs an explicit local STT model and language for speech or
command modes. Whisper runs on CPU by default in this diagnostic; pass
`--compute-device gpu` with a working GPU-enabled `--whisper-server` to test
the GPU path. Application execution additionally requires `--execute-actions`
and an explicit `--launch-app` binding. See
[live application launch](docs/actions/LIVE_OPEN_APP_INTEGRATION.md) and
[local models](models/README.md). No microphone audio is saved by the
diagnostic. See [project context](PROJECT_CONTEXT.md) for confirmed state,
experiments, and remaining limitations.

For the development control window, install the optional desktop dependency
in a connected development environment, then run:

```bash
.venv/bin/python -m pip install -e '.[desktop]'
.venv/bin/python -m kyrin.app.qt.main
```

The window uses `$XDG_CONFIG_HOME/kyrin/settings.json`, or
`~/.config/kyrin/settings.json` when the XDG variable is unset. It does not
create this file until settings are saved. A Whisper model also needs a local
`whisper-server` executable beside the installed `kyrin-desktop` script or on
`PATH`, or an absolute executable path in `KYRIN_WHISPER_SERVER`. For Whisper
GPU, provide a CUDA-enabled `whisper-server-gpu` in either executable location
or set `KYRIN_WHISPER_GPU_SERVER` to its absolute path. The app shows the
device actually opened by STT. Explicit GPU selection
reports an error if the GPU runtime cannot start, while AUTO can use the CPU
runtime if GPU startup fails. Vosk still runs on CPU. The close
button minimizes the window while listening continues; use **Quit KYRIN** to
stop and exit. The **Voice Output** page selects local voices by language,
including Persian Piper/VITS packages and supported Kokoro packages, along with speaking speed and
compute preference. It can play a short sample. See
[voice model management](docs/responses/TTS_MODEL_MANAGEMENT.md).

In **Preferences**, **Start KYRIN when I sign in** registers a per-user XDG
autostart entry and desktop-menu launcher. Turning it off removes only the
KYRIN autostart entry; the menu launcher remains. The entry points to the
current `kyrin-desktop` installation. If this development environment moves
or is removed, install KYRIN at its new location and reapply the setting.
The saved `start_at_login` flag alone does not install an entry; use the
Preferences control. With no STT model selected, startup opens the control
window in setup mode without opening the microphone.

## Roadmap

- Voice Interaction
- Vision Understanding
- Desktop Automation
- Cross-Platform Support

## Package version

0.1.0 (early development)

## License

MIT License
