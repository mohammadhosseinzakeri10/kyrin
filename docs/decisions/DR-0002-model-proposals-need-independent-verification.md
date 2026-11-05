# DR-0002: Model and recovery proposals need independent verification

- **Status:** Accepted and implemented; breadth of language and accent coverage is OPEN.
- **Area:** command understanding, safety.

## Problem

Speech recognition errors and local language-model output can both produce a
plausible but wrong command. Comparing four local models on small designed
corpora showed unsafe proposals, for example reading a request about one
application as a request about the whole computer. More prompting did not
remove that class of error.

## Decision

A model, a phonetic candidate or a recovery step may only **propose**. Before
anything is resolved or executed, independent checks run on the **original
text**:

1. **Operation check:** the proposed operation and its order must be supported
   by wording in the source text. Negation, unsupported actions, uncertain
   alternatives and uncovered languages ask for clarification
   ([`operation_verifier.py`](../../src/kyrin/commands/operation_verifier.py)).
2. **Target grounding:** each application or chat target must be grounded in
   the source words and, for applications, match the registered catalog
   uniquely ([`target_grounding.py`](../../src/kyrin/commands/target_grounding.py)).
3. **Power scope:** system power requests use their own source-text recognizer
   and two-step confirmation ([`flow.py`](../../src/kyrin/system_power/flow.py)).
4. **Permission and gate:** existing permission and action-gate checks remain
   in force.
5. **Recovery is candidate-only:** looser name matching may return candidates
   and ask a question; it never marks a candidate exact. A phonetic candidate
   alone never authorises execution, and the semantic model must agree with the
   independently derived candidate. Original text is never replaced by a model
   rewrite; chat and search content is preserved verbatim.

## Alternatives considered

- *Stronger prompts:* tried; did not remove unsafe proposals.
- *Rely on a larger model:* not adopted; the larger models in the comparison
  still produced unsafe proposals.
- *Operation check alone:* rejected after a test showed a wrong but allow-listed
  target could still resolve, which led to target grounding.

## Consequences and limits

- Safe abstention is preferred over a guess; some correct requests ask a
  question instead of acting.
- Rule coverage is a conservative English/Persian subset. Evidence came from
  small, partly designed corpora and is not an accuracy or false-action rate.
- Scores from engines or string similarity are not intent confidence.

## References

[Semantic contract](../commands/SEMANTIC_UNDERSTANDING_CONTRACT.md) ·
[Recovery policy](../commands/L04_RECOVERY_POLICY.md) ·
Local model comparison (`LOCAL_MODEL_COMPARISON.md`, source repository only) ·
[Control policy](../actions/CONTROL_POLICY.md)
