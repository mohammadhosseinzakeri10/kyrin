# DR-0009: Evaluation integrity and data handling

- **Status:** Accepted practice.
- **Area:** quality, evaluation.

## Problem

Small corpora and repeated tuning can make results look better than they are.
Recordings are personal data and must not leak through test artifacts.

## Decision

1. **Freeze references** before measurement and keep before/after runs paired on
   the same reference. Do not tune vocabulary, thresholds or transcripts to a
   specific evaluation case, and do not rewrite a reference to hide a miss.
2. **Separate evidence classes:** synthetic text, consented single-speaker
   recordings and live desktop observations are never merged or presented as
   one accuracy number. Misses are reported as misses, not as safe abstentions.
3. **Say what is not measured:** rule-only timings are not model speed; a
   sample from one run is not a distribution; a subset result is not
   generalised.
4. **Keep raw evidence private.** Recordings, transcripts and per-run logs are
   kept in ignored local directories, not tracked; public summaries carry
   aggregate counts and source binding only.
5. **Quality gate** (syntax, Ruff, strict mypy, full tests) runs in an isolated
   temporary profile with the desktop session address removed so tests cannot
   touch personal settings.

## Consequences and limits

- No accuracy thresholds are defined; claims stay qualitative until more varied
  data exists.
- Hardware validation and owner live checks are distinct from deterministic tests.

## References

[Validation](../VALIDATION.md) ·
Quality gate (`docs/development/QUALITY_GATE.md`)
