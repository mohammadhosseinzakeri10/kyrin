---
name: kyrin-evaluation-integrity
description: Plans, runs or reviews KYRIN offline measurements of speech recognition, command understanding, model latency and resource use (evaluators, replays and benchmarks under scripts/stt/ and scripts/commands/), and interprets their reports under DR-0009 evaluation integrity. Use when asked to measure, compare, benchmark or score models or corpora, or to judge an evaluation result. Not for fixing a failing test or defect (kyrin-engineering-workflow) or for owner-run live desktop checks (kyrin-live-acceptance).
---

# KYRIN evaluation integrity

`AGENTS.md` is the policy; DR-0009
(`docs/decisions/DR-0009-evaluation-integrity-and-data-handling.md`) is the
decision this procedure applies. A code change found during evaluation goes
through `kyrin-engineering-workflow`.

## 1. Name the question and the evidence class

- State what is measured (recognition errors, command route and target,
  latency boundary, device placement, memory) and for which model, device,
  language and corpus.
- Evidence classes are never merged into one number: synthetic or public
  text cases, consented local recordings, and owner live observations.
- Languages are reported separately (`docs/LANGUAGE_POLICY.md`). English is the
  V1 acceptance language; a mixed `auto` total is not an English result.

## 2. Choose the existing tool and reference

| Question | Start with | Reference |
| --- | --- | --- |
| STT error rates on labeled WAVs | `scripts/stt/evaluate_offline_stt.py`, `compare_local_models.py` | `docs/stt/STT_EVALUATION.md`, `datasets/stt/README.md` |
| STT output to command decisions | `scripts/stt/score_local_model_commands.py`, `scripts/commands/replay_stt_decisions.py`, `audit_speech_replay.py` | `datasets/commands/README.md` |
| L04 command understanding | `scripts/commands/evaluate_l04_baseline.py`, `evaluate_l04_audio.py`, `evaluation_contract.py` | `docs/commands/L04_SPEECH_UNDERSTANDING_CONTRACT.md`, `datasets/commands/L04_EVALUATION_FA.md` |
| Command-model speed, device, resources | `scripts/commands/measure_command_models.py`, `measure_model_composition.py`, `benchmark_understanding.py` | `docs/app/COMMAND_LATENCY.md`, `docs/app/COMMAND_MODEL_DEVICE_REPORTING.md`, `docs/app/MODEL_RESOURCE_POLICY.md`, DR-0006 |

Extend an existing evaluator rather than writing a parallel one. Read
`--help` and the script's code before running it.

## 3. Run safely

- Actions stay inert: never pass `--execute-actions` or bind a real
  executor, and do not change saved settings, permissions, history or the
  input session.
- Owner-run only (prepare the command, do not start it): microphone or
  recording tools such as `scripts/stt/record_command_corpus.py`,
  `scripts/audio/check_live_speech.py`, `scripts/audio/accept_l01.py` and
  `scripts/commands/measure_safe_live_latency.py`. Use `kyrin-live-acceptance`
  for that handoff.
- Model inference only when the owner's request is a measurement. Several
  evaluators start a local Ollama server (`LocalOllamaServer`); check this
  first, keep runs bounded, and run long ones in the background. Use only
  installed models and runtimes; no downloads, installs or driver changes.
- Write each report to a new path in an ignored location
  (`datasets/stt/results/`, `datasets/commands/evaluation/`, `local-data/`).
  Do not overwrite or rewrite an earlier report.

## 4. Keep the measurement honest

- Freeze references and record the source state (HEAD plus working-tree
  hashes of the code under test) and the model and profile identity before
  measuring. Compare before and after only on the same cases and references.
- Never tune vocabulary, rules, thresholds or prompts to a specific
  evaluation case, and never edit a reference to remove a miss. Fixes need a
  separate regression test and a fresh, paired run.
- Report misses as misses; an absent action is not accuracy. A wrong valid
  target counts as a failure even when the words look close.
- Keep timing boundaries distinct: model load, first partial, final
  transcript, command result and audio onset. `--unpaced` replay is not live
  latency. Requested device is not observed device; sampled peak memory is not
  a guarantee.
- No accuracy or latency thresholds are defined. Do not invent one; report
  numbers with sample size, speakers and limits.

## 5. Report

Report to the owner in Persian with English identifiers: question, tool and
exact command, source and model identity, corpus or manifest and case count,
per-language results, the failed cases, what was not measured, and the status
of each claim (CONFIRMED for the measured scope, UNVERIFIED beyond it). Raw
transcripts, per-item logs and recordings stay in Git-ignored locations;
tracked documents carry aggregate counts and source binding only. Use
`kyrin-technical-writing` when a result is written into a tracked document.
