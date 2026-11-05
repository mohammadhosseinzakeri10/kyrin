# L04: speech-error-tolerant command understanding contract

English reference. The Persian original,
L04_SPEECH_UNDERSTANDING_CONTRACT_FA.md (source repository only),
is preserved unchanged and contains the dated status notes. See also
[DR-0002](../decisions/DR-0002-model-proposals-need-independent-verification.md),
the [admission and recovery budget](L04_RECOVERY_POLICY.md) and the current
[semantic understanding contract](SEMANTIC_UNDERSTANDING_CONTRACT.md).

- **Status (as of the 2026-10-26 notes):** an experimental shared path is
  implemented. Final L04 acceptance and calibration on real speech are **not**
  done; live acceptance is performed by the owner with the
  L04 live acceptance guide (`L04_LIVE_ACCEPTANCE_FA.md`, source repository only). Details
  and limits: implementation report (`L04_IMPLEMENTATION_2026-10-26_FA.md`, source repository only),
  follow-up report (`L04_FOLLOWUP_2026-10-26_FA.md`, source repository only),
  prerequisites baseline (`L04_PREREQUISITES_2026-10-26_FA.md`, source repository only).
  Experimental numbers and results on designed data are not proof of accent
  support or product acceptance.

This contract records the owner's decision for a combined method: semantic
understanding, phonetic matching and valid context. Using real alternative
hypotheses and bounded reprocessing of the same audio is part of the intended
path, subject to feasibility. It replaces the earlier L04 restriction to the
scroll family; other operation contracts, persistent permission, target
identity, cancellation and the explicit listening controls remain valid.

## 1. Problem and intended result

A speech-recognition error may change the verb, the target name or parts of the
sentence, even yielding an unfamiliar word. The goal is to extract the command's
meaning and needed information despite such errors: a correctly spelled verb must
not be the only way to be accepted, and the user should not have to repeat until
the system's expected spelling appears. Scope is every registered, supported
KYRIN operation; the shared mechanism must accommodate future operations, each
still needing its own definition, evidence, admission policy and evaluation.
This document creates no new operation and promises no coverage of all errors,
languages or accents.

**Language priority (owner):** model evaluation and selection currently focus on
English, including accented speech; Persian is not a model-selection condition.
Keep the structure language-dependent so other languages can be added with
separate data. Current Persian or mixed-language coverage must not be inferred,
and each language and speaker group is measured separately.

## 2. Accepted decisions and open work

- **Accepted:** combine sentence meaning, language-dependent phonetic proximity
  and valid context; use several real hypotheses when the engine provides them;
  re-examine the same audio in hard cases; targeted disambiguation after bounded
  system checks.
- **Accepted:** shared infrastructure for all supported operations; the design and
  completion criterion are not limited to a few scroll spellings. Evidence
  requirements may differ per operation but must be explicit and testable.
- **Experimental implementation:** English phonetic representation with the
  existing eSpeak library, carrying Vosk hypotheses and named Whisper scores,
  and bounded Whisper reprocessing without the vocabulary hint. Not generalized
  to all engines.
- **Experimental, unverified for accents:** resource limits and recovery
  thresholds are in the separate policy. Persian tooling and calibration with
  real data remain open.
- **Possible later stage:** specialized training with real errors and optional
  personalization, only after a gap in the initial path is shown. No training,
  download or model swap is done or required here.

## 3. Role recognition within the sentence

Operation verb, target, direction, negation and user content are interpreted
separately. In a synthetic example "type school down", the phrase after a typing
request is content and must not become a scroll operation. The same holds for a
search phrase, application name, chat name and quoted text; support for typing or
search itself must be confirmed separately in code. The absence of "type" or
"search" does not prove the rest is a command, and a direction word alone does
not fix the operation type. Candidates must fit the whole phrase, roles and valid
context. Typed or searched content is protected from command-word correction;
for a target name a phonetic suggestion is allowed but its binding to a real
identity is checked independently; global name substitution is not allowed.

## 4. Intended processing path

1. Keep the original final text, attributed language and request origin. A clear
   command may pass the existing fast path; interim text only displays
   retractable suggestions.
2. For unresolved input, generate and compare meaning candidates using the
   original text, phonetic and semantic similarity, existing operations and fresh
   context. Output is operation plus needed data; rebuilding a perfect sentence is
   not required.
3. Use real engine alternatives with their origin when available. Textual
   difference is not necessarily difference in meaning; differences in verb,
   target, negation or direction are checked separately. Majority vote is not
   sufficient.
4. When ambiguity affects the decision, consider bounded reprocessing of the same
   audio segment (never re-executing the operation). Start from existing models; a
   second engine or different setting only after support and cost are examined;
   not every request needs multiple passes.
5. Check the proposed meaning against input evidence and the operation's
   requirements; then target-identity resolution, planning and the existing
   execution gate. Residual ambiguity gets a question about only the unknown part;
   asking to repeat the entire sentence is last. With insufficient evidence and a
   possible disambiguation, not executing is a valid outcome.

## 5. Model role and independent verification

The command model may flag a probable error, propose a meaning candidate or
correction and extract sentence information, limited to supported operations and
contracts. The model's explanation of its own reading is not independent
evidence. Independent verification is not limited to the exact spelling of a few
verbs: per operation it must state which part of the original text, real
hypothesis, phonetic proximity, context or audio evidence supports the proposal;
negation, scope and contradictory information are also checked. Handing the
model's rewritten text to an old verifier does not create independence, and
execution based only on the model's guess or explanation is not accepted.
Original text, speech candidates, model-built candidates, accepted meaning and the
reason for acceptance or rejection must stay distinguishable (this traceability
does not require permanent storage of private content).

Textual similarity, phonetic proximity derived from text, engine score and
semantic-model uncertainty are different concepts. Converting text to phonetics
is not hearing the original audio. None may be called "intent confidence" without
calibration. The absence of a score or real alternative is stated explicitly; an
empty field or a model-built candidate must not be presented as speech-engine
support.

## 6. Vocabulary hints and operation boundaries

Use the existing `vocabulary_hints` mechanism; hints must be compatible with the
engine, language and context and evaluated, and a fixed public default list is
not the solution. A decoder hint only helps text generation and is not
independent evidence of intent or permission; no closed grammar is imposed on the
whole conversation. Error-understanding infrastructure may serve sensitive
supported operations, but their dedicated paths, scope and evidence requirements
are kept and evaluated separately. Understanding or correcting a sentence grants
no permission to close, send, delete or power off and does not enable an absent
capability; persistent permission applies as in the current contract, and
disambiguating meaning or target must not bring back repeated confirmation of the
internal permission.

Start/Stop/Off belong to the independent explicit listening path; correction or
meaning suggestions must not enter those controls. "More" is interpreted only
with fresh context relating to the same request and application. Speech language,
interface language and the language-independent operation id stay separate. The
initiating window's identity, the deadline and the request generation are kept to
the execution boundary; disambiguation UI must not replace the target with the
KYRIN window. Fresh focus/identity checks, cancellation, the current permission
policy and the shared L03 input session remain valid, and a late correction or
reprocessing of a cancelled, expired or earlier-session request must not run.

## 7. Audio, time and privacy

Audio ownership is temporary, in memory and limited to the request (limits in the
[policy](L04_RECOVERY_POLICY.md)): by default at most 8 s of audio, a 15 s
lifetime and one reprocess; PCM is released before semantic-model inference, and
reprocessing passes shared STT admission
([Model resource policy](../app/MODEL_RESOURCE_POLICY.md)). Exit, cancellation,
expiry and session replacement invalidate a late result and release resources;
reprocessing must not cause unbounded waiting, repeated execution or closing the
microphone. Use synthetic data and already-authorized audio. This contract does
not permit new recording, reading private files, downloading models, sending
audio to an external service, permanent audio/text storage or telemetry.
Synthetic samples are not recorded as real speech or accent evidence.

## 8. Remaining prerequisites and order (status per the original)

1. **Done:** contract and card revised per the owner decision (documentation only).
2. **Done in initial scope:** 158 English text scenarios, metadata of eight
   authorized recordings by two speakers and a rule/audio baseline; 16 scenarios
   were checked with the existing Qwen model. The lack of audio diversity and the
   public nature of the review part are explicit; this data is neither a blind
   test nor proof of quality for all accents.
3. **Done at feasibility level:** three adapters examined; real Vosk hypotheses,
   detailed Whisper metadata and re-requesting the same PCM were tried; text to
   phonetics with the existing eSpeak worked for English and two Persian samples;
   no new package was installed. Transfer of these data and request-scoped audio
   retention were not implemented at the prerequisite stage; the current wiring is
   in the implementation report.
4. **Experimental policy implemented:** reference and per-turn logging, a separate
   historical index, recovery sensitivity analysis and resource budget exist.
   Confirming thresholds with diverse real audio and measuring live latency stays
   open.

Evaluation should cover at least first-try correctness of operation, target and
command data, false acceptance of ordinary conversation, missed negation,
unnecessary questions, need to repeat, and latency; the gain from reprocessing and
its cost are reported separately, and results are split by operation, language and
speaker with tuning data separate from final evaluation data. Samples must include
several existing operation families, verb and target errors, ordinary sentences,
typed/search content as a boundary example, negation, quotation, missing or
contradictory information, noise, silence, stale context, cancellation, focus
change, interim text and late results. Synthetic-text results are not equal to
audio evaluation or live microphone testing.

## 9. Historical observations (before the code change)

At that time `TranscriptUpdate` carried no alternative hypotheses or confidence;
`UnderstandingInput` had an optional `alternatives` field that the then-current
`OllamaCommandEngine` request did not send; Whisper passed the vocabulary hint
and the Ubuntu composition built hints from relevant application names, while the
Vosk adapter rejected a non-empty hint; independent verification of operations and
scrolling was still based on limited patterns. These are code observations, not
model results. Reference code: `src/kyrin/stt/transcript.py`,
`src/kyrin/commands/{understanding,ollama_engine,operation_verifier,model_interpreter}.py`,
`src/kyrin/stt/backends/`, `src/kyrin/app/platforms/ubuntu.py`. The current state
is in the implementation report; completing prerequisites does not close L04, and
a full project check remains required at the end of L04 implementation.
