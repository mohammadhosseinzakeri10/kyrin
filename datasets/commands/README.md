# KYRIN command-understanding reference cases

English is the primary V1 command/acceptance language. Retain the existing
multilingual reference cases and report language-specific results separately;
do not translate a fixture and reuse its identity as new evidence. The L04
corpus and its evaluation contract remain separate from these historical
semantic cases. See the [language policy](../../docs/LANGUAGE_POLICY.md) and
[English command guide](../../docs/commands/USER_COMMAND_GUIDE.md).

`semantic_cases.jsonl` defines intended behavior independently of the current
demo interpreter and any future STT, translator, or understanding model. Each
line is one JSON object with:

- `id`: stable case identifier.
- `origin`: `owner_verified` for wording confirmed by the owner in a prior
  live test, `owner_reported` for wording recalled or proposed by the owner,
  or `designed` for a new specification example. None of these labels claims
  that an audio recording exists.
- `input_text`: reference words, a reported phrase, or an observed STT
  spelling, as described by `input_kind`. `language` identifies the source
  language when known.
- `context`: optional known foreground and dialogue facts. Missing context is
  intentionally unknown, not a guess about the user's desktop.
- `expected.route`: `execute`, `clarify`, `confirm`, `no_action`, or
  `unsupported`. `steps` describes the intended structured meaning, including
  polarity; it does **not** grant permission or claim that an executor exists.

Cases marked `designed` are specifications for later validation, **not**
measured model successes. The corpus includes user-observed examples but does
not include voice recordings. A future audio evaluation must reference a
consented recording, its exact spoken words, speaker/language, and the STT
output separately. Do not score an STT error against an uncertain reference.

The corpus deliberately includes negation, unrecognized speech, uncertain app
names, system power, and dependent steps. A safe implementation must never
turn `clarify`, `no_action`, or `unsupported` into an executable action merely
because an STT or language model produced a plausible command.

## Designed L04 replay

`l04_cases.jsonl`, `l04_followup_cases.jsonl` and
`l04_turn_references.jsonl` supply the designed text corpus and its per-turn
references. `l04_baseline_summary.json` stores the frozen rules-only summary
used by the deterministic regression. The generic evaluation plan is in
`evaluation/plan.v1.json`.

Offline audio and spoken-reference audit tools require separately prepared,
consented inputs. The linked recordings, recording manifests, and machine
results stay private. See the [STT templates](../stt/README.md) and
[data-handling decision](../../docs/decisions/DR-0009-evaluation-integrity-and-data-handling.md).
