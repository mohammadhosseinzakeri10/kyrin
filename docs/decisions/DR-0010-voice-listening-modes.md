# DR-0010: Voice listening modes reuse the selected speech engine

- **Status:** Accepted for the implemented control phrases; first-wake reliability is UNVERIFIED.
- **Area:** runtime, listening control.

## Problem

Users need hands-free start, a standby state and a full microphone shutoff,
without a second always-on model.

## Decision

1. **Standby reuses the selected speech engine** and filters its output; there is
   no separate low-power keyword spotter. Ordinary transcripts in standby are
   not sent to command interpretation.
2. **Exact bounded control phrases:** start listening, stop listening (back to
   standby, audio session stays open), and complete microphone shutoff, which
   also persists `listening_enabled=false` ([`voice_control.py`](../../src/kyrin/runtime/voice_control.py)).
   The shutoff phrase is a control phrase, not an authentication secret.
3. **Truthful readiness:** `AudioCaptureReady`
   ([`events.py`](../../src/kyrin/app/events.py)) is emitted after the first
   captured chunk; the interface shows a microphone-starting state until then and
   ignores readiness notices from older sessions or generations.
4. An explicitly saved off setting stays off at the next startup.

## Alternatives considered

- *Dedicated low-power keyword spotter:* not part of this first version.
- *Mark running before capture opens:* rejected after the interface showed
  standby before audio was available.

## Limits

Reliability of the very first spoken wake after startup was not established in a
live check; later controls were. Standby still runs the full engine.

## References

[Architecture overview](../architecture/OVERVIEW.md)
