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

## Roadmap

- Voice Interaction
- Vision Understanding
- Desktop Automation
- Cross-Platform Support

## Package version

0.1.0 (early development)

## License

MIT License
