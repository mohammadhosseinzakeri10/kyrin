# Documentation

Start with [Getting started](GETTING_STARTED.md), then use the
[English command guide](commands/USER_COMMAND_GUIDE.md). The current source
targets Ubuntu/GNOME. Configure local speech models and desktop permissions
separately.

| Topic | References |
| --- | --- |
| Project and milestones | [Roadmap](ROADMAP.md), [current context](../PROJECT_CONTEXT.md), [release policy](RELEASE_POLICY.md), [changelog](../CHANGELOG.md) |
| Architecture | [Overview](architecture/OVERVIEW.md), [source layout](development/PROJECT_LAYOUT.md), [decision records](decisions/README.md) |
| Recognition | [Live pipeline](audio/LIVE_SPEECH_PIPELINE.md), [Vosk](stt/VOSK_ADAPTER.md), [whisper.cpp](stt/WHISPER_LIVE_ADAPTER.md), [Omnilingual](stt/OMNILINGUAL_ASR.md), [model setup](../models/README.md) |
| Commands | [Understanding](commands/COMMAND_UNDERSTANDING.md), [semantic contract](commands/SEMANTIC_UNDERSTANDING_CONTRACT.md), [recovery](commands/L04_RECOVERY_POLICY.md), [conversation memory](commands/CONVERSATION_MEMORY.md) |
| Desktop authority | [Action gate](actions/ACTION_GATE.md), [permissions](actions/PERSISTENT_PERMISSIONS.md), [control policy](actions/CONTROL_POLICY.md), [shared input](actions/SHARED_INPUT_SESSION.md), [outcomes](actions/ACTION_POSTCONDITIONS.md) |
| GNOME and applications | [Backend protocol](desktop/BACKEND_PROTOCOL.md), [window and app observation](desktop/ACTIVE_APP_OBSERVATION.md), [window group close](actions/APP_WINDOW_GROUP_CLOSE.md), [Ptyxis tabs](actions/TERMINAL_TAB_TARGETING.md), [Telegram](actions/TELEGRAM_CHAT_NAVIGATION_DESIGN.md) |
| Screen observation | [Screen observation](desktop/SCREEN_OBSERVATION.md), [OCR architecture](vision/OCR_ARCHITECTURE.md), [document-model isolation](vision/DOCUMENT_MODEL_PROTECTION.md) |
| Settings and feedback | [Local data](app/LOCAL_DATA_STORAGE.md), [model library](app/MODEL_LIBRARY.md), [model resources](app/MODEL_RESOURCE_POLICY.md), [language policy](LANGUAGE_POLICY.md), [speech output](responses/TTS_MODEL_MANAGEMENT.md), [visual status](desktop/VISUAL_STATUS.md) |
| Development and safety | [Contributing](../CONTRIBUTING.md), [quality gate](development/QUALITY_GATE.md), [validation and limits](VALIDATION.md), [security reporting](../SECURITY.md), [third-party notices](../THIRD_PARTY_NOTICES.md) |
| Evaluation | [Command cases](../datasets/commands/README.md), [STT evaluation](stt/STT_EVALUATION.md), [STT manifest templates](../datasets/stt/README.md) |

Dated engineering notes document specific earlier changes and experiments.
Use the current guides for setup and consult the [validation guide](VALIDATION.md)
for the distinction between deterministic checks and live observations.
