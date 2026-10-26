# Validation and known limits

This page separates reproducible repository checks from live owner evidence.
A passing test suite does not establish reliable behavior on every microphone,
model, GPU, compositor or application.

## Publication checks — 2026-10-26

The publication review uses CPython 3.14.4 and the existing pinned check
environment on Ubuntu 26.04. The shared gate checks all source, scripts and
tests with no scope reduction. The full local gate passed on the publication branch.

| Check | Publication result |
| --- | --- |
| Pinned environment `pip check` | Passed |
| Syntax, Ruff and strict mypy | Passed; strict mypy checked 429 files |
| Deterministic pytest suite | 2,576 passed in 150.76 seconds; no failures or skips |
| Source and wheel build | Passed with the pinned setuptools/wheel environment |
| Wheel installation without dependencies | Passed in a separate environment; imports, version and bundled resources checked |
| Source contents | Model weights, recordings and local settings excluded; bundled Silero VAD retained; only template STT CSV manifests included |
| Relative links and UI image | Public entry-guide links checked; actual Qt window rendered with isolated synthetic preview dependencies |
| GitHub Actions | [Live workflow status and logs](https://github.com/mohammadhosseinzakeri10/kyrin/actions/workflows/quality.yml); assess the exact published commit separately from the local result |

Checks write ignored local logs under `local-data/publication-review/`.
The headless gate creates temporary user/XDG directories, removes live desktop
connection variables and disables Hugging Face model downloads. It uses
synthetic fixtures and private test buses. This environment isolation is not a
host-wide network/security sandbox.

A pattern-based review covered 1,703 unique file blobs reachable from the
publication branch before the publication-documentation commit. It found no
matches for the reviewed private-key, GitHub, Hugging Face, AWS access-key or
OpenAI key patterns, no potential local audio/database/settings paths, and no
blob larger than 10 MB. It is a limited publication check, not an independent
security audit or proof that no secret or vulnerability exists.

The source manifest explicitly excludes local STT manifests before including
versioned templates; this also prevents cached packaging file lists from
reintroducing those local manifests. Source contents are inspected locally
before release assets are uploaded.

## First remote run and environment correction

The first GitHub Actions run on Ubuntu 24.04 passed syntax, Ruff and strict
mypy, then reported 28 failed and 2,548 passing tests. The private Gio portal
fixture used `/usr/bin/python3`, whose older grammar rejected Python 3.14
exception syntax. Other failures came from missing `spd-say` and `bwrap`: those
executables are checked while validating voice settings and protected OCR
commands, including tests using inert workers.

CI now targets Ubuntu 26.04, aligned with the supported system-Python/GI
environment, and explicitly installs/checks those tools and GI bindings.
`setup-python` uses the available Python 3.14 patch for this runner: its catalog
does not provide the older exact 3.14.4 build for Ubuntu 26.04. Python dependency
pins are unchanged; both application and system interpreter versions are
retained in the run artifacts. No
test was removed or skipped and no authorization/sandbox boundary was relaxed.
The available runner label was verified against the official
[runner image catalog](https://github.com/actions/runner-images#available-images).
The live workflow link above identifies subsequent results. CI also streams
verbose pytest logs and requests a thread dump when an individual test takes
more than 60 seconds; this is diagnostic output, not a relaxed timeout or a
passing exception. Branch pushes use PR validation; pushes to main validate
the published merge.

## Live evidence inherited from development

- The owner reported successful selected app-opening, Telegram Saved Messages
  and named-chat navigation flows. Matching all layouts, scripts and names is
  not established.
- L03 shared-input-session owner checks were accepted for the recorded local
  scenario. See the [L03 report](development/L03_SHARED_INPUT_SESSION_2026-10-25_FA.md).
- On 2026-10-26 the owner confirmed the local Chrome fixture's button click
  and repeated enable/disable sequence (`on, on, off, off`) after directional
  action selection fixes. See the [visible-control report](development/L04_VISIBLE_CONTROL_2026-10-26_FA.md).
- The broader L04 speech-understanding/desktop acceptance matrix remains open.
  The latest fixture confirmation is an owner report; it does not include new
  machine-readable per-turn postconditions or cover other applications.

No new live microphone recording, desktop operation, power operation or model
inference is performed as part of publication preparation. The screenshot in
the README is an isolated rendering of the real control window, not evidence
of a successful voice-command session.

## Known release limits

- The release is source-first. Runtime acquisition, model licensing, drivers
  and per-machine desktop integration remain separate setup work.
- The application requires Python 3.14+. Optional workers may use different
  isolated Python versions. The GNOME extensions declare Shell 50; support on
  other versions and platforms is not implied by headless CI.
- Recognition and local models can produce wrong words or meaning. Bounded
  checks and clarification reduce risk but do not guarantee semantic accuracy.
- Accessibility exports, OCR and live window identity can be missing or
  ambiguous. Unsupported/stale targets are allowed to fail rather than force
  an action. Not every dispatch has an observable postcondition.
- There is no portable installer, complete hardware matrix, independently
  audited security guarantee or long-term maintenance commitment.

Historical reports in [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md) and
`docs/development/` retain earlier failures and intermediate experiments.
Read their dates and superseding entries before treating them as current.
