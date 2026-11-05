# Validation and known limits

This page separates reproducible repository checks from live owner evidence.
A passing test suite does not establish reliable behavior on every microphone,
model, GPU, compositor or application.

## Current public development source

Run the [quality gate](development/QUALITY_GATE.md) from the checkout you want
to verify. Use the [Python quality workflow](https://github.com/mohammadhosseinzakeri10/kyrin/actions/workflows/quality.yml)
to find the run for an exact commit. CI checks syntax, Ruff, strict mypy, the
deterministic suite, and distribution builds. Tests use headless Qt, temporary
XDG paths and fake services. They exercise permission, target, lifecycle and
package contracts with synthetic evidence.

## Historical v0.1.0 checks

The original public alpha had separate source, wheel and deterministic checks.
See the [tagged validation record](https://github.com/mohammadhosseinzakeri10/kyrin/blob/v0.1.0/docs/VALIDATION.md)
for its results and environment corrections. Those results apply to the
original release and its check environment.

## Live evidence inherited from development

- The owner reported successful selected app-opening, Telegram Saved Messages
  and named-chat navigation flows. Matching all layouts, scripts and names is
  not established.
- L03 shared-input-session owner checks were accepted for the recorded local
  scenario.
- On 2026-10-26 the owner confirmed the local Chrome fixture's button click
  and repeated enable/disable sequence (`on, on, off, off`) after directional
  action selection fixes.
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
