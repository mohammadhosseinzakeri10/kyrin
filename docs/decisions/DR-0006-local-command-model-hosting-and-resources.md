# DR-0006: Local command-model hosting, device reporting and limited latency work

- **Status:** Accepted and implemented; resource and latency questions OPEN.
- **Area:** command understanding, resources.

## Problem

The optional command model must stay local, support GPU and CPU machines, and
share memory with speech recognition and voice output. Reported device choice
and actual placement differ, and measured latency needs care.

## Decision

1. **Loopback only.** Command inference accepts a server only on a `127.0.0.1`
   endpoint ([`ollama_engine.py`](../../src/kyrin/commands/ollama_engine.py)).
2. **GPU and CPU both supported.** Device preference supports CPU, GPU and Auto (shared
   `DevicePreference`); the accepted correctness and permission criteria are the same for both, while
   latency targets may differ.
3. **Report the device honestly.** A device request is reported separately from
   where the runtime actually loaded the model, classified from runtime memory
   data as CPU, GPU, mixed, GPU participation or unknown
   (`src/kyrin/commands/ollama_device.py`). Partial
   evidence, such as positive VRAM without a total size, proves GPU
   participation only, never pure CPU or GPU placement.
4. **One small latency fix only.** Reuse the real token count for an identical
   fully rendered prompt, keyed on file identity metadata; model responses are
   never cached and rendering/inference stay fresh
   ([`token_budget.py`](../../src/kyrin/commands/token_budget.py)).
5. **Deliberately unchanged:** keep-alive, per-request unload, queue and
   `ResourceLimits`. Changing residency affects ownership and memory shared
   with speech and voice output and needs its own design.

## Alternatives considered

- *Response caching:* not allowed; it would hide real inference.
- *Longer keep-alive:* promising but not justified by the available evidence.

## Open

Warm-state residency, model-load time inside rendering, peak memory, live
speech with a real queue, and the cause of an observed CPU server disconnect
are unresolved. Measurements used synthetic text and are not product latency.

## References

[Model resource policy](../app/MODEL_RESOURCE_POLICY.md) ·
Command model integration (`COMMAND_MODEL_LIVE_INTEGRATION.md`, source repository only) ·
Local model comparison (`LOCAL_MODEL_COMPARISON.md`, source repository only)
