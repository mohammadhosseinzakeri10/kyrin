# Changelog

Changes to the published source snapshot are recorded here. Versions identify
source milestones, not portable binary distributions.

## [0.1.0] - 2026-10-26

Initial public portfolio release (alpha).

### Added

- Continuous local audio acquisition, framing, resampling and bundled Silero
  VAD, with separate recognition contracts and local-file replay tools.
- Vosk, whisper.cpp and isolated Omnilingual STT adapters; optional CPU/GPU
  selection with explicit readiness and failure reporting.
- Bounded command interpretation, optional local Ollama proposals, speech
  recovery candidates and clarification flows.
- Permission-gated Ubuntu/GNOME app, window, scrolling, Telegram and named
  visible-control actions, with fresh observations and outcome checks.
- Shared desktop input sessions, saved-grant startup restoration and
  revocation; distinct microphone, command and desktop-input lifecycles.
- PySide6 control center, English/Persian UI, local model library, optional
  TTS, bounded transcript history and GNOME status integrations.
- Deterministic tests, pinned check dependencies, strict typing, headless CI
  and source/wheel build verification.
- Installation and architecture guides, contribution and security policies,
  issue templates and explicit public-release scope.

### Known limitations

- Source installation and separately obtained model/runtime packages are
  required. Desktop integration targets Ubuntu/GNOME; the bundled extensions
  declare GNOME Shell 50.
- Live checks cover selected owner scenarios; the wider L04 acceptance matrix,
  arbitrary phrasing, all application layouts and cross-platform support are
  not complete.
- Some actions report dispatch without a verified visible effect. No claim
  of production readiness or comprehensive security auditing is made.

[0.1.0]: https://github.com/mohammadhosseinzakeri10/kyrin/releases/tag/v0.1.0
