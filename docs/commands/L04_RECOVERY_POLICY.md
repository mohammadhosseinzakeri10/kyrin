# L04 admission and recovery budget policy

English reference. The Persian original,
L04_RECOVERY_POLICY_FA.md (source repository only), is preserved unchanged.
Related: [DR-0002](../decisions/DR-0002-model-proposals-need-independent-verification.md),
[DR-0009](../decisions/DR-0009-evaluation-integrity-and-data-handling.md).

- **Status:** experimental operating policy. The numbers are **not** validated
  thresholds for accents; the designed public set and eight earlier recordings
  are insufficient to calibrate intent probability. Defaults checked in
  `src/kyrin/stt/audio_recovery.py` (`AudioRecoveryPolicy`) and
  `src/kyrin/commands/recovery_candidates.py` (`PhoneticPolicy`).

## Admission rules

Admission on the fast path still depends on the rules and the operation
contract. For recovery, operation, target, direction, negation and free content
must be kept separate. A phonetic candidate alone never permits execution: the
semantic model must independently agree with the same candidate, and operation
review and the existing gate still apply. A real disagreement about operation,
target, direction or negation blocks admission; missing evidence leads to
non-execution or disambiguation.

The original text is never replaced by a model rewrite. An application target
must bind to an allowed name and real identity. Chat/search content is kept
verbatim; a phonetic target name cannot run without independent identity
resolution. Listening and power controls are outside general recovery. A new
operation needs a registered role contract and its own test.

## Default budget (configurable)

- **Audio per utterance:** at most 8 s and 256,000 bytes of 16 kHz 16-bit mono
  PCM (`max_pcm_bytes`). The measured rate of the existing format is 32,000
  bytes/s; the cap is an engineering choice for short commands. Longer audio is
  truncated and not used as complete audio.
- **Reprocessing:** at most one (`max_reprocess`), and only with a really
  compatible adapter. It is not re-execution of the operation.
- **Audio ownership lifetime:** at most 15 s from finalization
  (`retention_seconds`); a late result is not accepted. This is experimental:
  earlier Qwen times were about 42 to 48 s, so reprocessing must happen before the
  semantic call; audio is not held while waiting for the model.
- **Total deadline:** 120 s (`total_seconds`) from publication of the final STT
  text; waiting in the command-understanding queue is deducted. Capture and
  initial speech conversion are outside it. For replays without production time
  the budget starts at entry to the interpreter. A child deadline never extends
  the parent. The number is not a UI responsiveness guarantee or product latency
  target.
- **Audio owners:** at most five per session (`max_pending`), matching four queue
  requests plus one active; the retained PCM ceiling is 1.28 MB. Model memory,
  HTTP and the initial STT buffer are separate.
- **Closing an owner:** cancellation, exit, generation/session change, queue
  rejection, end of processing and expiry. Generation cancel also reaches a
  running understanding operation. Resources of the current request may stay in a
  library stack until a non-interruptible call returns; its result after
  cancellation or expiry is discarded.

The Vosk score, Whisper mean log-probability and phonetic string similarity are
none of them "intent confidence"; only a score with a name and origin is kept.
The absence of real data for a general threshold is explicit; similarity values
must be reported with an experimental label and separate development and review
results.

## Experimental selection and support limits

`PhoneticPolicy`: minimum similarity 0.80 and margin 0.08 between first and
second candidates. Weighted edit distance over IPA units: a vowel difference or
the s/z pair costs 0.35, adding/removing English r costs 0.5, other differences
cost 1. These are linguistic assumptions of recovery, not learned from user
audio and not intent confidence.

In the sensitivity analysis of the first turn of the development part,
thresholds 0.75 and 0.80 both produced 32 first candidates matching the action
reference; 0.85 gave 25 and 0.90 gave 23. "32" must not be read as 32 accepted
executions: model and independent review remain mandatory. The public review part
is reported separately and is not a blind test. The 0.08 margin and the edit
costs have no statistical calibration.

The eight existing recordings last 1.77 to 2.7 s; the 8 s cap is an engineering
margin for short commands, not an optimum derived from the samples. Five owners
match the current queue capacity. The 1.28 MB ceiling covers PCM in owners only;
it does not bound total model memory, and the shared model-resource policy still
applies ([Model resource policy](../app/MODEL_RESOURCE_POLICY.md)).

- **Whisper** re-checks the same full PCM once without the initial vocabulary
  hint, only when that hint was non-empty and the adapter can; reprocessing with
  unchanged settings is not done for every request.
- **Vosk** passes real decoder alternatives but this implementation has no audio
  owner for Vosk reprocessing.
- **Omnilingual** receives no fabricated alternatives or scores; reprocessing is
  not enabled.
- All 25 command kinds have registered contracts; registration is not coverage of
  every phrase or error of each kind. Scroll direction is now compared
  independently of the verb and both roles need the minimum similarity; an
  opposite, ambiguous or absent explicit direction is not accepted. For
  visible-control state, an exact label, a current observation and a readable
  state are required and the model must propose that same state; an expired
  observation is not accepted.
- **Multi-step recovery** is limited to two or three application operations with
  an explicit target in each step and an explicit separator; order and all model
  steps are matched. Context from executing the first step is not guessed to fill
  the next step's target. Chat/search content is not split at "and/then". A plan
  needing a question or confirmation does not become multi-step execution.
  Multi-step recovery of visual control, selector and free typed text is
  unsupported. A phonetic application name only creates an identity question.

The numbers are configurable through `AudioRecoveryPolicy`, `PhoneticPolicy` and
session-construction options; no new graphical settings UI was built. Enabling
the combined path in the Ubuntu composition depends on an already-selected
command model; this change selects no new model.
