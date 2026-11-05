# DR-0007: TTS adapter boundary and isolated optional runtimes

- **Status:** Accepted and implemented; packaging of optional runtimes is OPEN.
- **Area:** voice output.

## Problem

Voice packages are data in many incompatible families. Some need runtimes that
pin conflicting library versions; unknown weights cannot safely be executed.

## Decision

1. **Typed adapter contract** for inspecting, validating, selecting a device,
   loading and synthesising ([`families.py`](../../src/kyrin/tts/families.py),
   [`runtime.py`](../../src/kyrin/tts/runtime.py)). Unsupported packages are
   rejected, not executed. A saved adapter identifier survives a temporarily
   missing adapter and validation reports it.
2. **Model folders are data, never plugins.** Only built-in adapters are loaded.
3. **Isolated workers** for incompatible optional runtimes, with a bounded
   line protocol that returns audio ([`isolation.py`](../../src/kyrin/tts/isolation.py),
   [`worker.py`](../../src/kyrin/tts/worker.py)); the UI does not install them.
4. **Selection without code edits:** the control center detects a supported
   package and exposes its engine and built-in voices.
5. **GPU is explicit:** requesting a GPU that is not available is an error with
   a specific reason, not a silent CPU fallback.

## Alternatives considered

- *One shared Python environment:* rejected because upstream pins conflict.
- *Executable plugins from model folders:* rejected on safety grounds.

## Consequences and limits

- Audible quality and fresh-installation provisioning are not established for
  every family. Peak memory of some CPU runs is unmeasured.

## References

[TTS model management](../responses/TTS_MODEL_MANAGEMENT.md) ·
Offline speech output (`OFFLINE_SPEECH_OUTPUT.md`, source repository only)
