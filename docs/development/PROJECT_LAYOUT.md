# KYRIN project layout

This map describes the current source tree and its local setup. Keep separately
acquired models, optional runtimes, recordings and settings outside Git.
The bundled Silero VAD model has its own [notice](../../THIRD_PARTY_NOTICES.md).

## Top level

| Path | Purpose | Git |
| --- | --- | --- |
| `src/kyrin/` | Product Python package, divided by responsibility | Tracked |
| `tests/` | Deterministic tests, grouped like the package | Tracked |
| `scripts/` | Development diagnostics and benchmark tools | Tracked |
| `integrations/gnome-shell/` | Optional GNOME Shell extensions | Tracked |
| `docs/` | Design, operation, and validation notes by subject | Tracked |
| `datasets/` | Evaluation manifests; local recordings and results are ignored | Mixed |
| `src/kyrin/app/qt/assets/` | Visual assets used by the Qt application | Tracked |
| `models/` | Model documentation and ignored development model packages | Mixed |
| `local-data/` | Checkout-local downloads, caches and development outputs | Ignored |
| `downloads/`, `build/`, `.venv/` | Temporary downloads, build products, and development environment | Ignored |

## Product source and matching tests

| Package | Responsibility | Tests |
| --- | --- | --- |
| `audio/` | Audio acquisition, framing, conversion, VAD, and microphone adapter | `tests/audio/` |
| `stt/` | Speech-to-text contracts, backends, and device selection | `tests/stt/` |
| `tts/` | Speech-output selection types, model families, adapters, and isolated worker | `tests/tts/` |
| `commands/` | Command understanding, entity resolution, and local command-model adapters | `tests/commands/` |
| `actions/` | Permission-gated action execution and platform actions | `tests/actions/` |
| `desktop/` | Installed-app catalog, window identity, observation, and desktop adapters | `tests/desktop/` |
| `vision/` | Screen capture and OCR boundaries | `tests/vision/` |
| `responses/` | Text, speech, and visual feedback | `tests/responses/` |
| `memory/` | Local, text-only conversation history | `tests/memory/` |
| `system_power/` | Separately permitted power operations and the safe confirmation preview | `tests/system_power/` |
| `runtime/` | Listening-session and command orchestration | `tests/runtime/` |
| `app/` | Settings, model import, Ubuntu composition, and `qt/` user interface | `tests/app/` |

Interfaces stay with the component they describe. Ubuntu and GNOME adapters
live in `platforms/` inside the relevant package; other operating systems can
add adapters without moving the contracts. Development scripts do not belong
in the product package.

## Desktop UI code map

The Qt entry point is `app/qt/main.py`. `app/qt/window.py` owns navigation,
settings submission, and runtime event handling. Each page owns its widgets:

| File | Visible area |
| --- | --- |
| `dashboard_page.py` and `dashboard.py` | Welcome copy and cosmic artwork |
| `audio_page.py` | Microphone selection |
| `recognition_page.py` | STT engine, model, device, and diagnostics |
| `model_library_page.py` | Locally installed speech models |
| `command_model_page.py` | Command-understanding models |
| `tts_page.py` | Speech output models and voices |
| `actions_page.py` | App permissions and power actions |
| `screen_access_page.py` | Screen permission and OCR controls |
| `preferences_page.py` | Interface language and login startup |

`page_layout.py` holds the small shared settings-page layout; `theme.py`
holds the control-window stylesheet. Page widgets remain connected to their
settings and runtime events by `ControlWindow`. A page file is a useful
boundary here because it represents a distinct area that users navigate to,
not merely because the old file was long.

## Structure review

The source, tests, scripts, GNOME integration, and documentation have been
inventoried by responsibility. Two larger files remain intentionally intact:
`app/platforms/ubuntu.py` assembles the Ubuntu runtime, while
`commands/demo_interpreter.py` contains the bounded command interpretation
flow. Splitting either by line count alone would obscure the execution path.

The TTS adapters and selection types now live in `tts/`. `app/settings.py`
re-exports the selection types for existing settings consumers. The old
`app/tts_worker.py` module remains a small entry-point wrapper so already
installed optional runtimes can still start the worker by its existing module
path. New engine behavior belongs in `tts/`, not in that wrapper.

`audio/live_speech_pipeline.py` composes audio and STT, so it is broader than
raw acquisition. Its callers span the app, runtime, evaluation, and tests.
A future boundary change should move that orchestration and update those
callers together; the current file name and imports are stable.

## Model and runtime locations

Development model packages live under `models/local/by-model/`. App imports
use the XDG application data directory. Imported STT entries have stable
internal IDs and `model.json` metadata. See [local storage](../app/LOCAL_DATA_STORAGE.md)
for settings, history and caches, and [model notes](../../models/README.md)
for engine-specific catalog examples.

The Qt entry point discovers the development catalog only when its module
is physically inside a source checkout with the expected `src/kyrin/app/qt/`
layout and `pyproject.toml`. A wheel installation uses the application model
library instead of inferring a checkout from its parent directories. Model
acquisition, optional runtime setup and GNOME integration are separate from
installing the wheel.

## Where to add future work

- Add a new engine implementation beside existing backends in the responsible
  package and test it in the corresponding `tests/` directory.
- Put a development model in a named folder under `models/local/by-model/`.
  Import STT models through the application; select TTS packages directly from
  their family/model folder on this source checkout.
- Put one-off evaluation output under the ignored results directory for its
  dataset. Keep reference manifests and expected decisions reviewable in Git.
- Add operating-system integration under the responsible `platforms/`
  package or `integrations/`, leaving portable contracts in place.

Move a source module when its responsibility changes, and update imports,
tests, and docs in the same change.
