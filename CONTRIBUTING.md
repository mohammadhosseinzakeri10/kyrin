# Contributing to KYRIN

KYRIN v0.1.0 is a public portfolio snapshot. Focused fixes, reproducible bug
reports and architectural feedback about this release are welcome. Later
versions are planned to be private; see the [release policy](docs/RELEASE_POLICY.md).
There is no guaranteed review or maintenance schedule.

## Before changing code

1. Read the [architecture](docs/architecture/OVERVIEW.md) and
   [source map](docs/development/PROJECT_LAYOUT.md).
2. Check existing issues and open a proposal before a substantial feature,
   new runtime dependency or architectural change.
3. Inspect the actual interfaces, callers and tests. Historical notes can
   describe experiments that have since been superseded.

Use English for new public issues and pull requests where practical.
Existing Persian engineering notes do not need wholesale translation.

## Development setup

Follow [getting started](docs/GETTING_STARTED.md), then install the pinned
`requirements/dev.txt` and system test tools. Run from the repository root:

```bash
export PIP_CACHE_DIR="$PWD/local-data/pip-cache"
.venv/bin/python -m pip install -r requirements/dev.txt
.venv/bin/python -m pip check
.venv/bin/python scripts/development/check.py
```

The gate checks all `src`, `tests` and `scripts` with syntax validation, Ruff,
strict mypy and pytest. Qt runs headlessly. Tests must not use personal
settings, microphone hardware, model downloads or the owner's desktop.
Use synthetic fixtures and a private test bus where needed. Live microphone,
GPU and GNOME checks must be labeled separately.

## Keep changes reviewable

- Keep audio acquisition, STT, understanding, authorization and execution
  separate. A model proposal does not grant execution authority.
- Use explicit configuration and Python types. Preserve cancellation,
  time limits, ambiguity handling and fresh target checks.
- Add focused regression tests for changed behavior, including rejection and
  failure cases. Do not relax checks or hide failures to obtain a passing CI.
- Keep each pull request focused. Explain the problem, resulting behavior,
  validation and any limits; update affected documentation.
- Do not commit recordings, screenshots of private desktops, model weights,
  settings, permission tokens, caches or generated local evaluation output.
  Keep local assets under ignored `models/local/` and `local-data/`.
- Disclose material AI assistance and verify generated changes. Do not claim
  checks or live validation you did not perform.

## License and conduct

By submitting a contribution, you agree to license it under this repository's
MIT license and confirm that you have the right to submit it. You retain your
copyright. No copyright assignment or promise to open-source future versions
is implied. Preserve third-party licenses and attribution.

Follow the [community conduct policy](CODE_OF_CONDUCT.md). The maintainer may
remove abusive content or close work outside the published scope.

For vulnerabilities, follow [SECURITY.md](SECURITY.md) instead of opening a
public issue containing exploit details or personal data.
