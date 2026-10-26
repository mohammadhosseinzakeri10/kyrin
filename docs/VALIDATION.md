# Validation and known limits

This page separates reproducible repository checks from live owner evidence.
A passing test suite does not establish reliable behavior on every microphone,
model, GPU, compositor or application.

## Publication checks — 2026-10-26

The publication review uses CPython 3.14.4 and the existing pinned check
environment on Ubuntu 26.04. The shared gate checks all source, scripts and
tests with no scope reduction. The full local gate passed again after the
test-session lifetime, asynchronous signal synchronization and Qt cleanup
corrections.

| Check | Publication result |
| --- | --- |
| Pinned environment `pip check` | Passed |
| Syntax, Ruff and strict mypy | Passed; strict mypy checked 429 files |
| Deterministic pytest suite | 2,576 passed in 77.64 seconds; no failures or skips |
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

A later diagnostic run exposed a test-only lifetime bug: the fake live session
expired after two seconds, so a slow CI event loop could reach an unmocked
history-confirmation dialog and wait indefinitely. The fake now stays alive
until explicit controller stop, as the scenario requires; the test fails
immediately if a live producer opens the confirmation dialog. This changes
no production timeout or permission check. GJS image tests also explicitly
require the GdkPixbuf GI typelib, now installed and checked during CI setup.

The subsequent complete CI run passed 2,575 tests and exposed one remaining
test-only scheduling assumption: a synthetic executor stopped waiting after
three seconds while the UI was still applying permission revocation. The
fixture now holds that in-flight action until the test explicitly releases it,
with unconditional cleanup. The assertion still verifies that the first action
finishes and the next step is cancelled. A local private-bus run also exposed
an asynchronous `Closed` signal arriving after the method reply; that fixture
now waits up to two seconds for the disconnected state and still fails if it
is not observed. Neither correction changes production timeouts or permissions.

The following remote run passed those scenarios but exceeded the Qt test
helper's two-second readiness budget in five model-import/session-restart
checks. The shared test helper now allows ten seconds for asynchronous UI
readiness on a hosted runner. It still checks the same exact predicates and
fails at the deadline; this is not an application latency benchmark. Production
timeouts, assertions and the full suite remain unchanged.
The Qt fixture also explicitly destroys each test's new top-level widgets and
drains deferred deletion; normal window close minimizes KYRIN and otherwise
leaves child timers alive across test cases.

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
