# Getting started

KYRIN v0.1.0 is an alpha source release. The first goal is to open the control
center; recognition, voice output and desktop actions are configured separately.
There is no single download containing every model and runtime.

## 1. Install the development application

Use Python 3.14 or newer. The reproducible check profile is CPython 3.14.4 on
Linux x86_64. Desktop adapters target Ubuntu/GNOME; owner live validation was
on Ubuntu 26.04 / GNOME Shell 50. Headless CI on Ubuntu 24.04 does not establish
live integration support for its desktop version.

On Ubuntu, install missing system libraries:

```bash
sudo apt-get update
sudo apt-get install -y libportaudio2 libegl1 libopengl0 ffmpeg
```

From a clone of this repository:

```bash
git checkout v0.1.0
export PIP_CACHE_DIR="$PWD/local-data/pip-cache"
export HF_HOME="$PWD/local-data/cache/huggingface"
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements/bootstrap.txt
.venv/bin/python -m pip install -r requirements/core.txt -r requirements/test-ui.txt
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
.venv/bin/python -m pip check
.venv/bin/kyrin-desktop
```

`requirements/test-ui.txt` pins the Qt packages used for the control center
and headless tests. It does not install a speech-output engine. Alternatively,
install the `desktop` extra for Qt plus Sherpa local TTS support:

```bash
.venv/bin/python -m pip install -e '.[desktop]'
```

The optional-extra command resolves compatible versions from `pyproject.toml`;
it is not the pinned check-environment installation. Other optional runtimes
may require their own Python environments and compatible hardware.

A missing STT selection opens setup without microphone capture. No speech
weights are downloaded by launching the application. Run from a normal user
session; do not run the desktop application as root.

## 2. Configure speech input

Choose one supported backend rather than installing every engine.

| Backend | Additional setup | Reference |
| --- | --- | --- |
| Whisper | A local compatible whisper.cpp `whisper-server` executable and a GGML model; CPU is the simplest starting point | [Whisper adapter](stt/WHISPER_LIVE_ADAPTER.md) |
| Vosk | Install the `stt-vosk` extra and provide a Vosk model directory for the selected language | [Vosk adapter (Persian)](stt/VOSK_ADAPTER_FA.md) |
| Omnilingual | Compatible isolated Python worker/runtime, checkpoint and tokenizer | [Integration (Persian)](stt/OMNILINGUAL_ASR_FA.md) |

Store downloaded models in ignored `models/local/` and runtimes/caches under
`local-data/`. [Model notes](../models/README.md) describe the owner's catalog
and upstream references; those installed folders are not present in a clone.
Check each model's license before downloading or redistributing it. Download
and runtime build procedures depend on the chosen engine and are not automated
by this release.

For Vosk, the runtime extra can be installed with:

```bash
.venv/bin/python -m pip install -e '.[stt-vosk]'
```

For Whisper, place `whisper-server` beside `.venv/bin/kyrin-desktop`, expose it
on `PATH`, or set `KYRIN_WHISPER_SERVER` to its absolute executable path.
An explicit variable must reference an executable file. GPU uses a separately
built CUDA server named `whisper-server-gpu` or the absolute path in
`KYRIN_WHISPER_GPU_SERVER`; the model file is shared. Do not assume that a CPU
server provides CUDA inference. See [GPU execution](stt/WHISPER_GPU_EXECUTION.md).

In the application:

1. In **Model Library**, import a supported local model. Whisper imports a
   model file; Vosk imports its model directory.
2. In **Speech Recognition**, select the backend, model and language (`en`
   is a practical first command-language check). Start with **CPU**.
3. In **Audio Input**, choose the microphone. Save the configuration.
4. Wait for capture and recognition readiness, then use **Start listening**
   to enable command handling. Leave action execution disabled for the first
   transcription check.

A model/language mismatch or an unavailable runtime is a setup error, not a
reason to grant additional desktop permissions. The diagnostic area reports
recognized speech and command interpretation separately.

## 3. Add optional command and voice models

The default bounded interpreter does not require Ollama. Optional local
command understanding uses a separate loopback Ollama process and an existing
local model store. It proposes intent; it does not bypass action permission or
fresh-target checks. See [command-model integration](app/COMMAND_MODEL_LIVE_INTEGRATION.md).

Local voice output requires a compatible TTS model and the corresponding
runtime. It can be disabled while verifying recognition. See
[TTS model management](responses/TTS_MODEL_MANAGEMENT.md).

## Desktop integration

App launching uses installed desktop entries. Window identity/control and
several observation paths additionally use the bundled **KYRIN Active App**
GNOME Shell extension. Input and screen operations need the corresponding
system portal and user consent. Accessibility uses system Python with GI and
AT-SPI; these are separate from the Python 3.14 application environment.

On Ubuntu, check or install the optional integration tools:

```bash
sudo apt-get install -y python3-gi gir1.2-atspi-2.0 gjs \
  libglib2.0-bin systemd xdg-desktop-portal xdg-desktop-portal-gnome
```

The bundled extensions declare **GNOME Shell 50**. Check your shell version
before installation; do not disable version validation to force compatibility:

```bash
gnome-shell --version
```

To install the active-window extension for the current user, run from the
repository root on the compatible shell:

```bash
mkdir -p "${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions"
cp -R integrations/gnome-shell/active-app@kyrin.local \
  "${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/"
```

If this is its first installation, sign out and back in so GNOME discovers it,
then enable it:

```bash
gnome-extensions enable active-app@kyrin.local
```

The optional `visual-status@kyrin.local` extension can be installed the same
way for the movable status character. The `window-capture-prototype@kyrin.local`
extension is experimental; it is not part of the minimal first-speech setup.
Read the [active-app contract](desktop/ACTIVE_APP_OBSERVATION.md),
[screen capture notes](desktop/SCREEN_OBSERVATION.md) and
[OCR architecture](vision/OCR_ARCHITECTURE.md) before adding observation paths.

In **Desktop Actions**, enable execution and select only the apps/capabilities
needed for a synthetic test. Use the settings controls to prepare portal input
access. A remembered token can support a startup restoration attempt; it does
not guarantee that the OS will skip consent. Revocation and session disconnect
remain available. System power has its own capability and should be left off
for initial tests.

## Settings, shutdown and troubleshooting

- Settings normally use `$XDG_CONFIG_HOME/kyrin/settings.json`, falling back
  to `~/.config/kyrin/settings.json`. Paths follow XDG; the owner's drive/symlink
  layout in engineering notes is not required on another computer.
- Closing the window minimizes it. **Quit KYRIN** stops the application.
- Standby stops commands while capture may continue. **Turn off microphone
  completely** stops capture.
- An unsupported or unprepared desktop action should be investigated through
  its capability/readiness error. Do not respond by enabling every permission.
- Missing Qt platform libraries, an absent PortAudio library and an absent
  speech runtime are different setup failures. Include the exact error in a
  bug report after removing private paths/content.

For the developer gate, install `gjs`, `dbus-daemon`, `systemd` and the pinned
`requirements/dev.txt`, then run `scripts/development/check.py`. See
[validation](VALIDATION.md) and [quality setup](development/QUALITY_CHECKS.md).
