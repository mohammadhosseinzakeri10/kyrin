# DR-0004: Generation, sequence and deadline guards against late results

- **Status:** Accepted; deterministic tests cover points 1, 2, 3 and 5 in part (see
  *Test evidence*); point 4 is UNVERIFIED by a named test; live acceptance remains OPEN.
- **Area:** runtime, concurrency.

## Problem

Speech, model inference, resource waits and desktop actions finish at different
times. Reproduced defects included: a replayed or older final control reverting
a newer state; a slow speech result reverting a fresh GUI start; a cancelled
speech request that kept waiting for a native resource; and a late
capture-ready notice from an older session marking recovery as ready.

## Decision

1. **Tag and compare.** Events that can arrive late carry a generation or
   stream sequence ([`events.py`](../../src/kyrin/app/events.py),
   [`command_runtime.py`](../../src/kyrin/runtime/command_runtime.py)); a
   consumer accepts only the newest value for its stream, once.
2. **Cancellation reaches waiting work.** A cancel signal is passed to resource
   admission so waiting stops, but a native call that already owns the resource
   is not pre-empted.
3. **Absolute deadlines are inherited** by nested work, including time spent
   waiting for resources ([`operations.py`](../../src/kyrin/operations.py)).
4. **Cleanup is not quiescence.** End of a worker thread is reported separately
   from resource ownership being idle; an unreadable child process state is not
   treated as exit.
5. **Stale-result discard.** Late results after stop, standby, session change or
   expiry are dropped rather than applied.

## Alternatives considered

- *Rely on timeouts alone:* insufficient, because a timeout is not completion
  of the underlying work.
- *Pre-empt native calls on cancel:* not done; the late result is discarded
  instead.

## Test evidence

- Stale stream and queued finals discarded after invalidation; cancellation of
  an active operation does not poison the next one:
  [`test_command_worker.py`](../../tests/runtime/test_command_worker.py).
- Cancelled or expired owner does not dispatch input or spawn a process;
  deadline and epoch are checked immediately before dispatch:
  [`test_operations.py`](../../tests/test_operations.py).
- UNVERIFIED by a named test: point 4 (worker end versus resource idleness,
  unreadable child state) and the reported late capture-ready defect.
  The listed defects come from historical reports that were only partly
  reviewed; they are not reproduced here.

## Consequences and limits

- A guard without a named test above remains UNVERIFIED.
- A fix is not proof that the original historical stop event had this cause;
  that root cause was never established.

## References

[Operation lifecycle](../actions/DESKTOP_OPERATION_LIFECYCLE.md) ·
[Postconditions](../actions/ACTION_POSTCONDITIONS.md) ·
[Architecture overview](../architecture/OVERVIEW.md)
