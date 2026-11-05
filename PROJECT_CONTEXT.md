# KYRIN — Project Context

Concise engineering reference for the current state of KYRIN. Read it before
making architectural or implementation decisions, then inspect the code. It
summarizes and links; it does not repeat the detailed references.

- **The repository wins.** If this file and the code disagree, inspect the
  code and investigate the discrepancy instead of silently choosing one.
- **Authoritative detail** lives in the linked `docs/` references and in the
  source modules named below.
- Dated notes in the [documentation index](docs/README.md) give historical context.

## Status vocabulary

- **CONFIRMED** — implemented, tested, directly observed, or explicitly decided.
- **CURRENT DIRECTION** — the next agreed engineering direction; implementation
  may not have started yet.
- **TEMPORARY / EXPERIMENTAL** — local hardware or development observations that
  must not be treated as portable product behavior.
- **PROPOSAL / IDEA** — discussed but not committed.
- **OPEN** — unresolved and requiring a future engineering decision.

In this file, **UNVERIFIED** marks a claim whose live or cross-environment
behavior has not been established.

## Project snapshot

| Item | State |
| --- | --- |
| Package | `kyrin`, version `0.1.0` (`pyproject.toml`); Python `>=3.14` |
| Release | v0.1.0 is the public alpha source snapshot; later development is planned to be private ([release policy](docs/RELEASE_POLICY.md)) |
| Platform | Ubuntu with GNOME Shell 50 (extensions declare `shell-version` 50). Windows, macOS and mobile adapters are not implemented |
| Processing | Local: speech recognition, command models and TTS run on the user's machine. Model files are user-supplied data, not source |
| Language scope | English is the primary V1 command and acceptance language; Persian speech commands are limited, experimental compatibility ([language policy](docs/LANGUAGE_POLICY.md)) |
| Product status | Early development / experimental. No portable installer, no complete hardware matrix ([validation](docs/VALIDATION.md)) |

The end-to-end data flow and package responsibilities are described in
[Current architecture](docs/architecture/OVERVIEW.md). Directory layout:
[Project layout](docs/development/PROJECT_LAYOUT.md).

## Current state by subsystem

Statuses describe repository behavior with deterministic tests unless noted.
Live behavior on other hardware, models and desktops is UNVERIFIED.

| Subsystem | Status | Code | Reference |
| --- | --- | --- | --- |
| Audio acquisition, PCM model, framing, conversion, VAD | CONFIRMED | `src/kyrin/audio/` (`AudioInput`, `MicrophoneInput`, `SileroVad`, `AudioBacklog`, `LiveSpeechPipeline`) | [Live speech pipeline (Persian)](docs/audio/LIVE_SPEECH_PIPELINE.md) |
| Speech-to-text contracts and adapters | CONFIRMED contracts; Whisper, Vosk and Omnilingual adapters are optional and replaceable | `src/kyrin/stt/contracts.py`, `src/kyrin/stt/backends/` | [Whisper adapter](docs/stt/WHISPER_LIVE_ADAPTER.md), [models](models/README.md) |
| Listening modes (standby, start/stop listening, full microphone shutoff) | CONFIRMED in tests; bounded exact control phrases. Standby reuses the selected STT engine (no separate keyword spotter) | `src/kyrin/runtime/`, `listening_enabled` in `src/kyrin/app/settings.py`, `AudioCaptureReady` in `src/kyrin/app/events.py` | [Validation](docs/VALIDATION.md) |
| Command understanding | CONFIRMED: deterministic rules plus an optional local Ollama model that only proposes structured meaning; bounded recovery and clarification | `src/kyrin/commands/` (`CommandCoordinator`, `ContextResolver`) | [Semantic contract](docs/commands/SEMANTIC_UNDERSTANDING_CONTRACT.md), [L04 contract](docs/commands/L04_SPEECH_UNDERSTANDING_CONTRACT.md), [user guide](docs/commands/USER_COMMAND_GUIDE.md) |
| Authorization and action gate | CONFIRMED | `src/kyrin/actions/gate.py`, `src/kyrin/actions/control_policy.py`, `src/kyrin/app/permissions.py` | [Action gate](docs/actions/ACTION_GATE.md), [control policy](docs/actions/CONTROL_POLICY.md), [persistent permissions](docs/actions/PERSISTENT_PERMISSIONS.md) |
| Desktop observation (apps, windows, accessibility, OCR) | CONFIRMED contracts; coverage depends on each application's accessibility export and OCR quality | `src/kyrin/desktop/`, `src/kyrin/vision/`, `integrations/gnome-shell/` | [Active app](docs/desktop/ACTIVE_APP_OBSERVATION.md), [screen observation](docs/desktop/SCREEN_OBSERVATION.md), [OCR architecture](docs/vision/OCR_ARCHITECTURE.md) |
| Desktop input (pointer/keyboard through the RemoteDesktop portal) | CONFIRMED in tests and in a recorded owner scenario; other systems UNVERIFIED | `src/kyrin/actions/platforms/input_session.py`, `input_session_owner.py`, `src/kyrin/actions/desktop_input.py` | [Shared input session](docs/actions/SHARED_INPUT_SESSION.md) |
| App and window operations (open, focus, close, pickers, Terminal tabs, Telegram navigation) | CONFIRMED for implemented operations; native behavior varies per application and is partly OPEN (see below) | `src/kyrin/actions/`, `src/kyrin/actions/platforms/` | [Live open-app integration](docs/actions/LIVE_OPEN_APP_INTEGRATION.md), [window group close](docs/actions/APP_WINDOW_GROUP_CLOSE.md), [Telegram navigation design](docs/actions/TELEGRAM_CHAT_NAVIGATION_DESIGN.md) |
| System power actions | CONFIRMED as a separate capability with saved permission checks; the two-step flow is retained for safe preview | `src/kyrin/system_power/` | [System power actions](docs/actions/SYSTEM_POWER_ACTIONS.md) |
| Responses, TTS and status character | CONFIRMED presenter and replaceable local TTS; voice availability depends on installed models | `src/kyrin/responses/`, `src/kyrin/tts/`, `integrations/gnome-shell/visual-status@kyrin.local/` | [Response language](docs/responses/RESPONSE_LANGUAGE.md), [TTS models](docs/responses/TTS_MODEL_MANAGEMENT.md), [visual status](docs/desktop/VISUAL_STATUS.md) |
| Qt application, settings and lifecycle | CONFIRMED: immutable versioned settings, UI-independent controller, Ubuntu composition, single-instance guard, user-scoped launcher | `src/kyrin/app/` | [Application lifecycle design](docs/app/UBUNTU_APPLICATION_LIFECYCLE_DESIGN.md), [model library](docs/app/MODEL_LIBRARY.md), [model resource policy](docs/app/MODEL_RESOURCE_POLICY.md) |
| Conversation memory | CONFIRMED: bounded local text-only history | `src/kyrin/memory/history.py` | [Conversation memory](docs/commands/CONVERSATION_MEMORY.md) |
| Dashboard animation | CONFIRMED: 2D particle scene with CPU and GPU renderers; the 3D option was evaluated and removed | `src/kyrin/app/qt/` | — |

## Architectural invariants

These rules define the boundaries. Change one only with an explicit,
documented decision. Each links to its authoritative reference.

1. **Acquisition is separate from processing.** `AudioInput` is the capture
   contract; `MicrophoneInput` only acquires raw audio and opens the device
   inside `capture()`, never in `__init__`. STT, intent understanding and
   desktop actions stay downstream. Audio configuration stays explicit and
   portable; no machine-specific device identifiers.
   ([Architecture](docs/architecture/OVERVIEW.md); `src/kyrin/audio/microphone/input.py`)
2. **Replaceable recognition.** Engines implement `SpeechToTextEngine` /
   `SpeechToTextSession`; no engine is hard-wired into the pipeline.
   (`src/kyrin/stt/contracts.py`)
3. **Partial and final speech have different authority.** Only final
   transcripts enter command processing; previews never cause repeated
   actions. Stop, standby or session changes invalidate pending work and late
   results. ([Architecture](docs/architecture/OVERVIEW.md); `src/kyrin/actions/gate.py`)
4. **Understanding proposes; execution authorizes.** Rules, recovery,
   recognition alternatives and model output can propose or ask for
   clarification but never grant permission. A model response to recognizable
   command text is not executed as conversation; model proposals require
   independent source-text, target and permission checks.
   ([Semantic contract](docs/commands/SEMANTIC_UNDERSTANDING_CONTRACT.md))
5. **Permissions are explicit and persistent.** `PermissionPolicy` is the
   authority for capabilities. A missing settings file yields no selected STT
   model and no action permission. Saved KYRIN permission, operating-system
   consent, the restore token and the live input session are four distinct
   things; OS pointer/keyboard access never substitutes for a KYRIN
   capability. Send, delete and payment operations require dedicated tools
   with their own postcondition contract and permission.
   ([Control policy](docs/actions/CONTROL_POLICY.md); `src/kyrin/app/permissions.py`)
6. **Remembered desktop-input consent is a maintained contract.** After
   successful setup and durable portal consent, selected and enabled input
   capabilities are restored asynchronously at startup without another setup
   click. Normal exit and microphone shutdown close the live session but keep
   saved consent; explicit revocation closes input and removes the token.
   Tokens are single-use and rotated. Commands and status polling never start
   or retry setup. Missing or rejected OS persistence stays visible and
   recoverable. ([Shared input session](docs/actions/SHARED_INPUT_SESSION.md);
   `InputSessionService.disconnect(forget=...)`, `prepare(..., restore=...)`)
7. **Observations expire; targets keep their identity.** Window tokens,
   process/app identity, observation provenance and deadlines travel with the
   action evidence. A fresh read does not make an old request valid for a
   replacement window. Targets are re-resolved and compared with earlier
   evidence immediately before input; ambiguity, incomplete reads or stale
   identity reject the request. OCR does not infer boolean control state.
   ([Control policy](docs/actions/CONTROL_POLICY.md); `ControlEvidence`,
   `WindowObservation`)
8. **Every operation has a bounded lifetime.** An absolute operation deadline
   and cancellation generation are inherited by nested work, including time
   spent waiting for input ownership. Cancellation and expiry stop owned
   subprocesses; late callbacks cannot authorize input. Cooperative
   cancellation does not imply that a running dispatch can be recalled.
   ([Operation lifetime](docs/actions/DESKTOP_OPERATION_LIFECYCLE.md);
   `src/kyrin/operations.py`, `src/kyrin/actions/cancellation.py`)
9. **Outcomes state their certainty.** `ActionOutcome` distinguishes
   `confirmed`, `launch_accepted`, `dispatched_unverified`, `unknown` and
   `failed`. Dispatch is not a verified effect, and an unknown result never
   justifies automatic repetition.
   ([Postconditions](docs/actions/ACTION_POSTCONDITIONS.md); `src/kyrin/actions/models.py`)
10. **Language surfaces are independent.** Interface, STT, command-response,
    status-caption and voice languages are configured separately; a delayed
    result keeps its own command language. Literal targets (app names, chat
    titles, labels, OCR text) keep their original script and are never
    silently translated or transliterated into a different target.
    ([Language policy](docs/LANGUAGE_POLICY.md), [response language](docs/responses/RESPONSE_LANGUAGE.md))
11. **Local first.** Speech, command and voice models run locally from
    user-installed model files; the optional command-model server is
    accepted only on a `127.0.0.1` endpoint (`src/kyrin/commands/ollama_engine.py`).
    No cloud service or external model provider is part of the design.
12. **The UI composes; it does not decide.** Qt pages edit settings; the
    Ubuntu factory assembles adapters and engines. Optional workers isolate
    incompatible runtimes and are not a security sandbox.
    ([Architecture](docs/architecture/OVERVIEW.md); `src/kyrin/app/platforms/ubuntu.py`)

## Open work and current direction

- **OPEN — broader L04 acceptance.** The speech-understanding and desktop
  acceptance matrix is not closed. Individual owner checks are reports, not
  automated acceptance, and do not cover other applications.
  ([Validation](docs/VALIDATION.md))
- **OPEN — application-specific native behavior.** Some Telegram menu routes
  and other native control paths remain unaccepted or only
  `dispatched_unverified`; root causes are not fully established. Do not add
  guessed coordinates or installed-application patches.
  ([Telegram navigation design](docs/actions/TELEGRAM_CHAT_NAVIGATION_DESIGN.md))
- **UNVERIFIED — live acceptance of recent deterministic changes**, including
  status-caption completeness and some listening-control phrase variants.
- **OPEN — recognition quality.** English acoustic/model accuracy, latency
  and cross-device resource use require measured acceptance per model,
  device and corpus; no thresholds are defined yet.
- **CURRENT DIRECTION** — English-primary V1 completion with Persian retained
  as limited compatibility; runtime packaging, broader model management and
  non-GNOME adapters remain future work.

## Known risks and constraints

See [Known release limits](docs/VALIDATION.md#known-release-limits). In short:
recognition and local models can be wrong; accessibility exports, OCR and
window identity can be missing or ambiguous; not every dispatch has an
observable postcondition; GNOME Shell 50 is the only declared Shell version;
headless CI does not establish live desktop behavior.

## Development workflow

- Quality gate: `scripts/development/check.py` (syntax, Ruff, strict mypy,
  full pytest) — see [quality gate](docs/development/QUALITY_GATE.md).
- Distinguish deterministic tests from hardware validation and owner live
  checks; do not claim a test that was not run.
- Desktop-input changes must run the regression checks listed in the
  [shared input session contract](docs/actions/SHARED_INPUT_SESSION.md).
- Documentation language follows the [language policy](docs/LANGUAGE_POLICY.md).
