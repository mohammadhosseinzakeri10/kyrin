# Documentation

Start with the public guides below. KYRIN v0.1.0 is an experimental source
release for Ubuntu/GNOME, with local models configured separately.

| Guide | Purpose |
| --- | --- |
| [Getting started](GETTING_STARTED.md) | Install, configure a first speech session, and add desktop integration |
| [Architecture](architecture/OVERVIEW.md) | Current components, contracts and data flow |
| [Validation](VALIDATION.md) | Deterministic checks, live evidence and known limits |
| [Release policy](RELEASE_POLICY.md) | Scope of the public snapshot and future private development |
| [Project layout](development/PROJECT_LAYOUT.md) | Source, tests, scripts, models and local data |
| [Contributing](../CONTRIBUTING.md) | Development and review expectations |
| [Security](../SECURITY.md) | Trust boundaries and private vulnerability reporting |
| [Changelog](../CHANGELOG.md) | Published version history |

## Feature references

| Topic | Documents |
| --- | --- |
| Commands | [User command guide (Persian)](commands/USER_COMMAND_GUIDE_FA.md), [semantic contract](commands/SEMANTIC_UNDERSTANDING_CONTRACT.md), [local command models](app/COMMAND_MODEL_LIVE_INTEGRATION.md) |
| Speech input | [Live pipeline (Persian)](audio/LIVE_SPEECH_PIPELINE_FA.md), [Whisper adapter](stt/WHISPER_LIVE_ADAPTER.md), [GPU execution](stt/WHISPER_GPU_EXECUTION.md), [local models](../models/README.md) |
| Desktop actions | [Control policy](actions/CONTROL_POLICY.md), [postconditions](actions/ACTION_POSTCONDITIONS.md), [shared input session (Persian)](actions/SHARED_INPUT_SESSION_FA.md) |
| Observation | [Active app](desktop/ACTIVE_APP_OBSERVATION.md), [OCR architecture](vision/OCR_ARCHITECTURE.md), [document model protection](vision/DOCUMENT_MODEL_PROTECTION.md) |
| Application | [Model library](app/MODEL_LIBRARY.md), [UI languages](app/UI_LANGUAGE_PACKS.md), [TTS models](responses/TTS_MODEL_MANAGEMENT.md), [conversation memory](commands/CONVERSATION_MEMORY.md) |
| Quality | [Pinned environment and gate (Persian)](development/QUALITY_CHECKS.md), [command evaluation](../datasets/commands/README.md), [STT evaluation](../datasets/stt/README.md) |

## Reading the engineering history

[PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md), `docs/development/` reports and
[REVIEW.md](../REVIEW.md) preserve development stages, experiments, owner
reports and open questions. Newer entries may supersede earlier ones. They
include workstation-specific examples and references to ignored local logs;
those paths are not files shipped in a fresh clone. An owner report is not
an automated acceptance result.

The [original Voice Core requirements](architecture/v1-voice-core-analysis.md)
remain useful historical context; the current architecture is broader.
Documentation ending in `_FA.md` is generally Persian. Public entry guides
are English so reviewers can navigate the implementation without reading the
entire development history.
