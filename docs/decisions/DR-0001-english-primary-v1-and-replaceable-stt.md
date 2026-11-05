# DR-0001: English-primary V1 and replaceable speech-to-text engines

- **Status:** Accepted for development; live acceptance is open (UNVERIFIED on other hardware and speakers).
- **Area:** speech recognition, language scope.

## Problem

Early evaluation covered Persian and English speech and no engine was
chosen. Small local comparisons showed that engine quality, latency,
language coverage and runtime requirements differ widely, that no engine
dominated on every axis, and that evidence came from a few single-speaker
recordings. The project needed a language scope and an engine strategy that
would not lock the pipeline to one model.

## Decision

1. **English is the primary V1 command and acceptance language.** Persian
   speech commands remain limited, experimental compatibility; the Persian
   interface stays selectable. Literal targets keep their original script.
   See the language policy (`docs/LANGUAGE_POLICY.md`).
2. **Engines are replaceable behind one contract.** Engines implement the
   speech-to-text contract in [`contracts.py`](../../src/kyrin/stt/contracts.py);
   Vosk, Whisper and Omnilingual adapters live in
   [`backends/`](../../src/kyrin/stt/backends/) and are optional.
3. **Development default.** A Vosk English model was first chosen as a default
   candidate; local Whisper `small` replaced it for current development
   because correct command text was prioritised over the fastest provisional
   response. Neither choice is a packaged default.
4. **Engine-specific turn handling.** Turn-aware engines receive VAD-confirmed
   start/pause markers; streaming engines keep their own conversion path.
   Only a full-turn result after a confirmed pause is final for such engines.
   The Omnilingual selection uses a longer pause threshold (800 ms) than other
   engines (384 ms) in [`ubuntu.py`](../../src/kyrin/app/platforms/ubuntu.py),
   because a shorter threshold split one utterance in a replay.
5. **Python-version isolation.** Omnilingual runs in a separate worker because
   its upstream requires an older Python than the main application.

## Alternatives considered

- *Persian-first evaluation:* rejected as the primary scope; it remains
  compatibility work.
- *One hard-wired engine:* rejected to keep selection a user choice and to
  allow later engines.
- *Longer global pause threshold:* rejected because it delays finalization
  for every engine; applied only where evidence required it.

## Consequences and limits

- Engine choice and thresholds are configuration, not architecture.
- Evidence was small, single-speaker and CPU-heavy; it supports no accuracy,
  accent or latency claim. Thresholds for acceptable accuracy are not defined.
- A longer pause delays finalization and can merge close utterances.

## References

Language policy (`docs/LANGUAGE_POLICY.md`) ·
[Whisper adapter](../stt/WHISPER_LIVE_ADAPTER.md) ·
[Omnilingual setup](../stt/OMNILINGUAL_ASR.md) ·
[Model library](../app/MODEL_LIBRARY.md)
