# Historical architecture and reliability audit (2026-10-23)

> **Status: historical record, not a current defect list.** This file is a concise
> English index of an audit performed on **2026-10-23** against commit `63df339`
> (the working tree was clean when the audit began). The full original report was
> written in Persian and is no longer shipped here. Findings below describe what the
> auditor observed **at that time**. A finding marked `CONFIRMED` in the original was
> confirmed against that commit only; it is **not** automatically confirmed, fixed or
> still open in the current working tree. Nothing here is a current acceptance status.

## Scope and evidence limits (as of the audit)

- **Scope:** about 459 versioned files were listed and statically reviewed: Python
  source, tests, scripts, Markdown documents and a few JavaScript files. Python files
  were parsed with the AST; entry points, dependency composition, audio, command
  understanding, policy, click execution, Telegram, output and memory were read in
  depth. Not every line of every test or document was read manually. Model weights,
  third-party library code and personal data were out of scope.
- **Checks run by the auditor:** syntax parsing of all Python files (no errors);
  `ruff check` (clean); `ruff format --check` (77 files needed formatting, none were
  changed); 71 selected tests passed (2 deselected); several defects were reproduced
  in memory with mocks (identical-pixel PNGs with different metadata, label policy,
  reversed scroll direction, model inference on partial text, plan continuation after
  queue cancellation, Persian phrase assembly).
- **Not run:** the full test suite, `mypy`, live microphone/click/portal checks,
  access to page content, real model runs and an end-to-end benchmark.
- **Evidence tags in the original:** `CONFIRMED` (seen in code or reproduced with mock
  dependencies; not a successful desktop run), `LIKELY` (strong inference), and
  `SPECULATION` (hypothesis needing an experiment). Severities were engineering
  priorities for this product, not formal security scores. The primary observation of
  every finding below was tagged `CONFIRMED`; many impact statements were `LIKELY`, and
  F13 contained a `SPECULATION`.
- **Environment seen by the auditor:** Ubuntu 26.04, GNOME Shell 50, Wayland. GPU, VRAM,
  monitor layout, selected model and the loaded extension version were not verified.
  Historical latency figures cited in project notes were not re-measured.
- **Main conclusion (original):** the project already had separated contracts,
  dependency injection, a bounded action queue, permissions, GNOME observation and
  several audio/STT backends; a rewrite was not justified. The central problem was an
  inconsistent request/result contract and unclear lifecycle ownership at component
  boundaries. Swapping the OCR model alone was not expected to fix unreliable clicks.
  No arbitrary-shell path, proven permission bypass or leaked secret was found, so no
  finding was rated Critical.

## Findings index (F01-F22, historical)

Severity is the original one. "Meaning" is a short paraphrase, not a re-verification.

### High

| ID | Meaning (as observed at the audited commit) |
| --- | --- |
| F01 | Target freshness was checked by comparing the bytes of two PNG captures. GNOME writes a creation-time field into the PNG, so identical pixels could compare as different and a static window could be rejected as "moved". Recommended comparing decoded pixels or a target region instead. |
| F02 | A new risk policy rejected most click requests and all on/off toggles before OCR ran (only a few generic labels passed), a safe but coverage-reducing regression that looked like an OCR miss. Recommended action- and consequence-based policy with a bounded confirmation flow. |
| F03 | A dispatched click was not proof that the action happened: no post-click verification, toggles did not re-read state, and a plan could continue after `LAUNCH_ACCEPTED`. Recommended semantic postconditions and a separate unverified-dispatch state. |
| F04 | AT-SPI existed but depended on OCR readiness and was mostly reduced to coordinates; window ancestry, visibility/defunct state and the action interface were not fully used. Recommended an independent semantic AT-SPI locator and actuator. |
| F05 | Stopping or cancelling the queue did not stop an already started plan or an active helper process (reproduced with a mock executor). Recommended shared cancellation/deadline and a permission check just before input. |
| F06 | No single owner for all desktop input: Telegram selection/paging used its own threads next to the action queue. Recommended one input broker serializing keyboard/pointer and portal use. |
| F07 | The local model could be called on partial transcripts, and the synchronous call could block stop/final handling (timeouts of 60 s, 120 s on CPU). Recommended no model inference on partials and cancellable final-only workers. |
| F08 | A caller-side timeout did not stop the real OCR work or give an overall deadline; fallbacks could start after the caller had given up. Recommended an absolute deadline and cancellable workers. |
| F09 | The scroll-intent check did not compare direction with the model's proposal; a reversed model suggestion could become an executable command (reproduced with a mock model). Recommended independent parameter extraction and comparison. |
| F10 | Telegram flows still depended on fixed layout crops and fixed points, and typing a chat name did not re-check focus between characters. Recommended live locators, field identity and focus checks during typing. |
| F11 | Confirmation before closing windows with possibly unsaved work was not uniform across applications. Recommended consequence-aware confirmation with window identity and expiry. |

### Medium

| ID | Meaning |
| --- | --- |
| F12 | OCR phrase grouping and target locating did not behave the same for Persian/RTL multi-span labels, mixed languages and a single confidence threshold. Recommended a shared phrase assembler and calibrated thresholds. |
| F13 | The capture-geometry converter was improved, but the producer's metadata (scale, padding, mixed-DPI, shadows) still needed proof, and a legacy path remained. Recommended producer-to-actuator tests. |
| F14 | The new window token covered only part of the path from command understanding to execution; a window switch between detection and action could redirect a click. Recommended carrying token, generation and deadline in the initial evidence. |
| F15 | Helper error causes (content, window token, stale capture) were collapsed to "unknown" at the helper boundary. Recommended a versioned structured error response. |
| F16 | Listening during TTS was not true barge-in: without echo cancellation the microphone was muted while speaking, and echo cancellation applied only to the default device. Recommended AEC for the selected device and immediate playback interrupt, or an explicit half-duplex mode. |
| F17 | Text history was on by default with no setting to turn it off, and the archive had no retention cap of its own. Recommended persistence control, retention and clear semantics. |
| F18 | Latency metrics were keyed only by segment id, did not cover plans or streams fully, and used event-receipt time. Recommended a full action identity and stage timings. |
| F19 | No shared GPU/RAM/token budget across the command model, TTS and STT. Recommended a lightweight central residency and memory policy and token-budgeted prompts. |
| F20 | Backend capability and version discovery did not equal a successful install (late or stale extension, no reproducible install record or CI at that time). Recommended capability/version handshake, probes and reproducible install. |
| F21 | "Offline" document-model workers were not a security sandbox (local checkpoint code was trusted). No malicious model was found. Recommended artifact hashes/provenance and restricted worker privileges. |

### Low

| ID | Meaning |
| --- | --- |
| F22 | Very large functions and half-finished contracts (for example an observation reader that did not fill all geometry fields) made maintenance harder. Recommended extracting shared validators and lifecycle code after behavior is fixed, without a broad refactor. |

## Historical recommendations and unresolved concerns

These were proposals in the original, not implemented in the audit and not confirmed as
done or abandoned here:

1. **Action contract:** observe, validate, execute once, then verify a semantic
   postcondition; distinguish confirmed, dispatched-but-unverified, failed and
   cancelled outcomes; never blindly repeat toggle, send, delete or buy.
2. **Lifecycle:** one desktop input owner, shared cancellation, deadlines and
   permission epochs carried into helpers, and no model inference for partial text.
3. **Locating targets:** prefer an application API or shortcut for known operations,
   then AT-SPI semantic actions, then targeted OCR, then icon matching, with a GUI
   vision model only as a last, independently verified fallback. Keep Wayland support;
   X11 tools were not a general answer.
4. **Resources and audio:** measure latency per stage (historical figures were not a
   baseline), keep capture/VAD on CPU, avoid running every model on every request,
   and treat echo cancellation and barge-in as separate lifecycles.
5. **Architecture:** evolve toward an event-driven coordinator with a dialogue state
   machine and a single input broker (option A), optionally followed by a limited
   tool-registry planner (option C). A full async rewrite (option B) was judged lower
   value. Local-only processing was the default assumption.
6. **Proposed order (original):** structured errors and timings first; then fix PNG
   freshness and click-policy coverage; then the input broker and cancellation; then an
   AT-SPI-first path; then locator/geometry unification; postconditions; independent
   command understanding; audio/residency tuning; and finally memory and tools.
7. **Major open concerns at the time:** real-desktop acceptance of every backend,
   mixed-DPI and multi-monitor geometry, calibrated OCR confidence, and measured
   latency on the target hardware.

## Where to look for current information

These documents describe present behavior or recorded decisions. They are **not** a
finding-by-finding re-verification of this audit.

- [Decision records](docs/decisions/README.md), notably
  [late and stale result guards](docs/decisions/DR-0004-guards-against-late-and-stale-results.md),
  [semantic-first control targeting](docs/decisions/DR-0005-semantic-first-control-targeting.md) and
  [persistent permissions](docs/decisions/DR-0003-persistent-permissions-and-remembered-input-consent.md).
- [Action gate](docs/actions/ACTION_GATE.md) and
  [control policy](docs/actions/CONTROL_POLICY.md) for outcomes and permission rules.
- [Quality gate](docs/development/QUALITY_GATE.md) and [validation](docs/VALIDATION.md)
  for what is checked and the limits of that evidence.

To establish whether any finding applies today, inspect the current code and run the
relevant checks; do not rely on the historical `CONFIRMED` tags above.
