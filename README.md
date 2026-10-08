# KYRIN

An open-source, modular AI desktop agent under active development.

## Vision

KYRIN is an intelligent AI agent designed to understand voice, vision, and text, and interact with the operating system naturally like a human.

## Current status

KYRIN has an offline, continuously listening voice prototype for Ubuntu. It
separates microphone capture, audio processing, replaceable speech recognition,
command interpretation, desktop actions, and responses. A terminal diagnostic
can launch explicitly allowed applications after a final command; it is a dry
run by default. An optional GNOME Shell extension shows a movable animated
status character. This is not yet a packaged, always-on application.
An optional Qt control window can edit the first set of local microphone and
STT settings, show status, and start or stop listening. Opening it again in the
same user session activates the existing window. On Ubuntu, Preferences can
install a per-user desktop launcher and enable or disable login startup.
The Desktop Actions page can select installed applications for an explicit
allowlist and enable execution. TTS and model management are not yet available
in that window.
The selected black-hole K logo appears in the window and Ubuntu launcher.

The current interpreter recognizes a small set of English and Persian example
commands. It does not provide general multilingual understanding or desktop
automation. Local Vosk and Whisper models are development assets, not bundled
defaults. The current adapters use CPU; the STT contract allows future device
selection without changing the audio pipeline.

## Development entry point

Python 3.14 or newer is required by the current package. From a configured
development environment, inspect the microphone diagnostic options with:

```bash
.venv/bin/python scripts/audio/check_live_speech.py --help
```

The diagnostic needs an explicit local STT model and language for speech or
command modes. Application execution additionally requires `--execute-actions`
and an explicit `--launch-app` binding. See
[live application launch](docs/actions/LIVE_OPEN_APP_INTEGRATION.md) and
[local models](models/README.md). No microphone audio is saved by the
diagnostic. See [project context](PROJECT_CONTEXT.md) for confirmed state,
experiments, and remaining limitations. The two V1 Word guides in `docs/`
teach the early microphone foundation; some example file paths reflect that
historical stage rather than the current package layout.

For the experimental control window, install the optional desktop dependency
in a connected development environment, then run:

```bash
.venv/bin/python -m pip install -e '.[desktop]'
.venv/bin/python -m kyrin.app.qt.main
```

The window uses `$XDG_CONFIG_HOME/kyrin/settings.json`, or
`~/.config/kyrin/settings.json` when the XDG variable is unset. It does not
create this file until settings are saved. A Whisper model also needs a local
`whisper-server` executable on `PATH`, or an absolute executable path in
`KYRIN_WHISPER_SERVER`. Current Vosk and Whisper adapters run on CPU; choosing
GPU reports unavailable without replacing a valid saved choice. The close
button minimizes the window while listening continues; use **Quit KYRIN** to
stop and exit. The window currently shows text responses and does not select
or play a TTS voice.

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
