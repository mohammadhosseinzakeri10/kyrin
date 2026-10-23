# Semantic command-understanding boundary

## Purpose and current state

`CommandInterpreter` and `CommandCoordinator` remain the live product path.
`DemoCommandInterpreter` handles fast reviewed phrases; when a local Ollama
model is selected, `ModelAssistedInterpreter` handles unresolved speech.
`src/kyrin/commands/understanding.py` is its **proposal-only** contract.
`target_resolution.py` resolves proposed names without execution. The live
adapter still requires source evidence, a permitted target, and the normal
action gate. Named controls and focused scrolling have their own fresh-window
checks; system-power proposals from the model cannot start a power action.

The reference cases in `datasets/commands/semantic_cases.jsonl` define desired
behavior, not a measured accuracy result. They distinguish owner-verified,
owner-reported, and designed examples. No audio is bundled.

## Boundary

```text
Original text + attributed language + optional ASR alternatives
                  + fresh/remembered context
                           ↓
              CommandUnderstandingEngine
                           ↓
  UnderstandingResult (proposed meaning, status, uncertainty)
                           ↓
    Source-operation verifier + target resolver
             + source-target grounding
                 + dialogue clarification + planner
                           ↓
  Existing CommandIntent / CommandPlan / system-power request
                           ↓
          ActionGate + confirmation + executor
```

`UnderstandingInput` retains the original words. A translation-backed engine
may translate internally, but must not overwrite the source text or assume
that translated app/contact names are canonical. `language` is attributed by
the source; it is not automatically verified language identification. Optional
`alternatives` are present only when an STT engine supplies them. Text input
or a future audio-file source can use the same contract. Empty/blank final
transcripts are valid input and should produce a non-command result.

`MeaningStep` contains a requested operation and the user's target phrase.
It does **not** contain an installed-app ID, a window handle, a shell command,
or permission. The catalog and fresh desktop observation resolve targets later.
System operations have no app target. A chat may have an explicit app phrase;
otherwise context resolution can ask the user. `ProposedMeaning` supports
ordered steps without promising every step is executable. The current action
planner still enforces its own two-to-three-step limit.

`UnderstandingResult` distinguishes ready, negated, ambiguous, incomplete,
non-command, and unsupported text. A ready result requires exactly one
meaning, no recorded uncertainty, and affirmative polarity for every step.
A clear negation receives its own non-executable status. Uncertain polarity
cannot be ready or negated. The result is never itself an
authorization: a later adapter must recheck resolved target, permissions,
fresh context, action support, and any confirmation requirement.

The independent `SourceOperationVerifier` compares the proposed **ordered
operations** with explicit action evidence in the original transcript. Its
first replaceable rule profile covers a conservative subset of English and
Persian; an uncovered language or uncertain wording requires clarification.
It also checks supplied alternative transcripts, rejects a changed operation
or negation, and keeps all system-power requests in their separate flow. It
does not infer intent from the model's own explanation. A matched operation
alone does not prove the app or chat target was actually spoken. Conservative
rules can clarify a mixed negative/positive instruction; this is a known
coverage limit, not evidence that the utterance had no action.

The new `SemanticTargetResolver` is a pure, proposal-only stage after this
contract and operation check. It accepts only one `READY` meaning with at most
three steps. An
application phrase resolves only when it matches one installed, explicitly
allowed catalog application exactly. Approximate matches and multiple matches
return a clarification with candidates; unknown names also clarify. A chat
without an application uses a fresh, unconflicted foreground observation, or
a preceding resolved `open_app`/`restore_app` step in the same proposed plan.
That planned dependency must still be verified after execution. It retains the
spoken chat name unchanged and does not establish that the chat exists.
Negated and non-command input produces no action; ambiguous input clarifies.
Every proposed system-power step is rejected from this stage because the
separate source-text recognizer and two-confirmation flow own those actions.
The result is **not** a `CommandIntent`. The live model adapter may convert a
verified proposal to one only after its source, target, context, and permission
checks. Resolving a target alone does not validate the model's operation or
grant any permission.

`SourceTargetGrounder` then independently extracts the app and chat names from
each source-language clause and compares them with the resolved proposal. It
uses the same catalog alias mapping to establish app identity, but requires an
exact, unique source match; a fuzzy catalog suggestion only clarifies. Chat
names currently require a lexical match after basic Unicode normalization;
the code does not claim that a contact exists or silently equate "Save
Message" with "Saved Messages". An app explicitly named for a chat must match
the resolved app. If the source omits an app, the model cannot supply one in
its proposal; fresh context or an earlier resolved step may still determine
the app. Supplied alternative transcripts must agree. This narrow EN/FA check
does not repair STT errors or cover every way to phrase a command.

`understanding_json.py` now checks structured model responses before they can
become `UnderstandingResult`: unknown fields, contradictory route/step pairs,
negated action proposals, app/system target confusion, and plans longer than
three steps fail closed. A redundant app field identical to an app operation's
target is discarded; a different app is rejected. This checks internal shape,
not whether the proposed operation matches the user's original words.
`scripts/commands/replay_decisions.py` applies this decoder, the independent
source-operation verifier, target resolver, and source-target grounder to saved
benchmark outputs with a fixed test catalog. It reports unsafe resolved
*proposals*, never executed actions. Its independent
source-text power check reports only eligibility for the existing confirmation
flow and never starts that flow.

Uncertainty is categorical (`speech`, `language`, `operation`, `target`,
`negation`, `context`). We deliberately do not expose one universal numeric
"confidence": STT, translation, and NLU scores have different meanings and
are not comparable without calibration. An implementation may retain its
native scores for diagnostics, but must validate its decisions against the
reference corpus and real audio before using any threshold.

## Integration rules for the next implementation

1. Only final STT text can authorize a downstream action. Partial text may
   update the visual candidate and must remain retractable.
2. Preserve the original transcript and source language through the decision
   trace. Keep a translated rendering separately if translation is used.
3. Resolve proposed app names against explicitly registered/allowed apps.
   Similarity may suggest a candidate; it does not silently grant a match.
4. A proposed system action is not enough to start a power request. The
   original final transcript must independently match
   `recognized_power_request`, with explicit computer scope for restart.
   Only then may the request enter the existing two-confirmation
   `SystemPowerFlow`; it must never bypass that flow or its opt-in permission.
   Languages without a reviewed power-request recognizer must clarify or
   report unavailable rather than accepting a model-only system proposal.
5. Reject or clarify ambiguity in operation, target, negation, or app/system
   scope before action. A missing negation in STT cannot be repaired reliably
   by a language model alone.
6. Run supported plan steps in order. Verify a dependent target using fresh
   observation, and report an unsupported later step after an allowed earlier
   step when the complete utterance has been understood.
7. Keep the understanding engine replaceable. A direct multilingual engine
   and a local translation-backed engine should consume the same input and
   produce the same proposal type. The winner must be selected by end-to-end
   command accuracy, false actions, latency, and RAM/VRAM on target hardware.

## Evaluation before model selection

First score text-only understanding against the reference cases. Then use
consented recordings with exact spoken references to measure STT separately
and the full speech-to-action path together. Track at least: correct action,
false action, missed action, missed negation, unnecessary clarification,
language and accent, end-of-speech-to-decision latency (median and tail), and
peak CPU/RAM/VRAM. A text-only corpus cannot establish microphone or model
quality. The first corpus is small and must grow before broad multilingual
claims. English, Persian, and German examples are present; other languages
need native-speaker or otherwise reliable references before being scored.

No additional runtime dependency is introduced by this contract.
