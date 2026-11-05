# Development quality gate

Run checks from the repository root using the project's installed Python
3.14+ development environment. The pinned reference profile uses Python
3.14.4; dependencies are under `requirements/`. See
[Getting started](../GETTING_STARTED.md) and
[Contributing](../../CONTRIBUTING.md) for the required tools and environment.

```bash
.venv/bin/python scripts/development/check.py
```

The checker runs syntax compilation, Ruff, strict mypy and the complete pytest
suite. Each stage writes a log and retains its exit code in `summary.json`;
a nonzero stage makes the overall command fail. `--output-dir` can select a
separate project-local evidence directory so an earlier result is preserved.

## Source and environment isolation

The checker explicitly selects this checkout's `src/` instead of trusting an
editable installation that might still point at an old checkout. Before
pytest, a child process records and validates interpreter, package origin
and package search paths in `source-provenance.json` and its log. A source
mismatch blocks pytest rather than testing a different copy of KYRIN.

The child checks use temporary home/XDG directories, headless Qt, offline
model settings and a separate bytecode cache under the output directory.
The personal desktop bus/display variables are removed. This does not
install a model, start a microphone or grant desktop permissions.

Some tests start private D-Bus services, subprocesses and local sockets.
The execution environment must allow these operations. A failure caused by
restricted execution is still a failed run; retain the evidence and identify
the restriction. Do not remove tests or weaken guards to report a pass.

## Focused language regression

These checks need the already installed Qt test dependencies but no model,
speaker device or personal desktop session:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH="$PWD/src" \
  .venv/bin/python -m pytest -q \
  tests/app/test_ui_language_contract.py \
  tests/app/test_ui_translations.py \
  tests/responses/test_language_contract.py \
  tests/responses/test_presenter.py \
  tests/responses/test_speech.py \
  tests/responses/test_visual_status.py \
  tests/app/test_qt_control_confirmation.py \
  tests/desktop/test_gnome_close_confirmation.py \
  tests/tts/test_tts_page.py \
  tests/stt/test_evaluation_languages.py
```

The language tests distinguish English defaults, saved Persian/system
preferences, event-language responses, fixed-language status captions and
literal target preservation. Voice tests use inert implementations. They
do not establish recognition accuracy or the pronunciation of mixed-script
names by an installed voice. See the [V1 language policy](../LANGUAGE_POLICY.md).

The native-confirmation tests use an isolated GJS harness rather than the live
GNOME session; they require the installed `gjs` test dependency. Regional locale
and voice-preview cases keep UI, request and voice languages independent.
STT-summary tests verify separate weighted metrics per source language without
altering the original aggregate metrics or references.

## Desktop input regressions

Changes to startup/shutdown, input ownership, settings, token storage or
packaging must preserve remembered input access. The maintained contract and
live restart/reboot checks are in
[shared input session](../actions/SHARED_INPUT_SESSION.md). Required
automated coverage includes:

- `tests/actions/test_input_session.py`
- `tests/actions/test_input_session_bus.py`
- `tests/app/test_qt_window.py`
- `tests/app/test_qt_input_access.py`
- `tests/app/test_permission_token.py`

The full gate includes these checks. Deterministic test success does not
establish that a particular OS accepts a token after a real reboot.

## Evidence limits

Report exact checks run and their results; keep pre-existing or concurrent
failures visible. Scope claims to the checked source and environment.
Unit/integration tests are distinct from model benchmarks, real microphone
sessions, actual voice playback and native GNOME rendering. Model evaluation
must report languages separately and retain the original corpus/references.
Use [validation notes](../VALIDATION.md) for the broader acceptance status.
