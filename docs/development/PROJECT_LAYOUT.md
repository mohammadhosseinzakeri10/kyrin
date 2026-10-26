# KYRIN project layout

This map separates product source, tests, documentation, development models,
and installed application data. It describes the current repository, not a
future package format. Model weights, runtimes, recordings, and settings are
local machine data and are not committed to Git.

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
| `local-data/` | Installed STT/OCR models, optional runtimes, caches, and app settings on this workstation | Ignored |
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
| `system_power/` | Separately confirmed power operations | `tests/system_power/` |
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

## Model and runtime locations on this Ubuntu workstation

```text
models/
  README.md
  archive/                         downloaded source archives
  local/
    by-model/                       named development packages
      command-understanding/ollama/ one complete store per model
      stt/vosk/                     one extracted folder per Vosk model
      stt/whisper.cpp/              one folder per Whisper model
      stt/omnilingual-asr/           six local v2 model folders
      tts/<family>/<model>/         selected TTS packages, one per model
      ocr/tesseract/                OCR language data only
    ocr/tesseract/                   experimental OCR executable and libraries

local-data/
  kyrin/
    models/stt/                     models imported through the application
    models/ocr/                     installed OCR runtime and language data
    runtimes/                       optional engine environments
    tools/                          download/setup tools
    cache/                          project-specific caches, when used
  diagnostics/                      retained local artifacts of uncertain origin
  config/kyrin/                     application settings
```

The named `by-model/` directory is the canonical **development catalog** and,
for TTS in this source checkout, the application's model library.
Every Ollama model has its own `blobs/` and `manifests/`; a file needed by two
models was copied into both stores. The Command Understanding page lists the
four stores together and starts only the selected store. The old combined
Ollama store and duplicate development STT folders were removed after path,
content, and startup checks.

`local-data/kyrin/models/` is the **installed application library**. Its STT
entries have readable names plus unique internal IDs and `model.json` metadata,
so the application can manage imports without depending on folder spelling.
The UI displays model names from that metadata. Keeping an installed copy
separate from a development model allows either one to change without silently changing the
other. TTS packages are organized by family and model under
`models/local/by-model/tts/` and are selected by path without an installed
duplicate. A packaged app without this checkout uses its platform application
data directory as a fallback. The OCR runtime is separate from its trained
language data.

The desktop entry point accepts a development model catalog only when its
module is physically inside the expected `src/kyrin/app/qt/` source layout
and that checkout has `pyproject.toml`. An installed wheel therefore uses the
application model library for TTS and installed STT entries; it does not infer
a model catalog from unrelated parent directories. This guards path discovery
but does not yet constitute a portable release: optional speech runtimes,
model acquisition, and desktop integration still need packaging and an
installed-environment acceptance test.

On this machine, the standard XDG application paths point to `local-data/`
through symlinks. See [local storage](../app/LOCAL_DATA_STORAGE.md). Portable
product code derives platform paths; it must not hard-code this mount path.

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
