"""Shared bounded recovery before model meaning and the existing execution gate."""

from dataclasses import replace
from time import monotonic, perf_counter_ns

from kyrin.commands.app_names import SpokenAppCandidate
from kyrin.commands.interpreter import (
    CommandInterpreter,
    Interpretation,
    NeedsClarification,
    NotACommand,
    ReadyCommand,
    ReadyPlan,
    UnrecognizedCommand,
)
from kyrin.commands.models import (
    CommandContext,
    CommandIntent,
    CommandKind,
    CommandPlan,
    PendingAppClarification,
    PendingCommandClarification,
    PendingOperationClarification,
    RecoveryTrace,
)
from kyrin.commands.recovery_candidates import (
    PhoneticCandidateGenerator,
    explicit_non_action_role,
)
from kyrin.commands.understanding import (
    ProposedMeaning,
    UnderstandingInput,
    UnderstandingResult,
    UnderstandingStatus,
)
from kyrin.operations import OperationStopped, budget, check_operation
from kyrin.stt.audio_recovery import AudioRecoveryPolicy
from kyrin.stt.errors import SpeechToTextError
from kyrin.stt.evidence import SpeechEvidence


def _intents(result: Interpretation) -> tuple[CommandIntent, ...]:
    if isinstance(result, ReadyCommand):
        return (result.intent,)
    return result.plan.steps if isinstance(result, ReadyPlan) else ()


class SpeechCommandRecovery:
    """Generate evidence independently; a semantic proposal cannot self-verify."""

    def __init__(
        self, generator: PhoneticCandidateGenerator, rules: CommandInterpreter
    ) -> None:
        self.generator = generator
        self.rules = rules

    def clarify(self, intents: tuple[CommandIntent, ...]) -> Interpretation:
        if not intents:
            return UnrecognizedCommand()
        options = {
            item.app_id: item.display_name
            for item in self.generator.names.model_options()
        }
        if (
            len({intent.kind for intent in intents}) == 1
            and len({intent.target for intent in intents}) > 1
        ):
            if all(intent.target in options for intent in intents):
                return NeedsClarification(
                    PendingAppClarification(
                        tuple(
                            SpokenAppCandidate(key, options[key])
                            for key in dict.fromkeys(i.target for i in intents)
                        ),
                        confirmation=False,
                        operation=intents[0].kind,
                    )
                )
        if (
            len({intent.target for intent in intents}) == 1
            and len({intent.kind for intent in intents}) > 1
        ):
            target = intents[0].target
            return NeedsClarification(
                PendingOperationClarification(
                    SpokenAppCandidate(target, options.get(target, target)),
                    tuple(dict.fromkeys(intent.kind for intent in intents)),
                )
            )
        return UnrecognizedCommand()

    def review(
        self,
        source: UnderstandingInput,
        proposal: UnderstandingResult,
        context: CommandContext,
    ) -> Interpretation | None:
        if proposal.status is not UnderstandingStatus.READY:
            return None
        candidates = context.recovery_candidates or self.generator.generate(
            source.text,
            source.language,
            context,
        )
        if not candidates:
            return None
        top = candidates[0]
        if (
            len(candidates) > 1
            and top.similarity - candidates[1].similarity
            < self.generator.policy.minimum_margin
        ):
            if top.following:
                return UnrecognizedCommand()
            competing = tuple(
                candidate.intent
                for candidate in candidates
                if top.similarity - candidate.similarity
                < self.generator.policy.minimum_margin
            )
            return self.clarify(competing)

        steps = proposal.candidates[0].steps
        if len(steps) != len(top.steps):
            return UnrecognizedCommand()
        if top.following:
            verified: list[CommandIntent] = []
            for intent, step in zip(top.steps, steps, strict=True):
                single = replace(top, intent=intent, following=())
                result = self.review(
                    source,
                    UnderstandingResult(
                        UnderstandingStatus.READY, (ProposedMeaning((step,)),)
                    ),
                    replace(context, recovery_candidates=(single,)),
                )
                if not isinstance(result, ReadyCommand):
                    return UnrecognizedCommand()
                verified.append(result.intent)
            return ReadyPlan(CommandPlan(tuple(verified)))

        step = proposal.candidates[0].steps[0]
        if step.operation.value != top.intent.kind.value:
            return UnrecognizedCommand()
        if top.intent.kind not in {
            CommandKind.SCROLL_UP,
            CommandKind.SCROLL_DOWN,
            CommandKind.SHOW_ALL_WINDOWS,
        }:
            target = step.target_phrase
            if target is None:
                return UnrecognizedCommand()
            if top.intent.kind in {
                CommandKind.OPEN_CHAT,
                CommandKind.TELEGRAM_SEARCH,
                CommandKind.TELEGRAM_VIEW,
                CommandKind.TELEGRAM_SETTINGS,
                CommandKind.TELEGRAM_SEARCH_FOCUS,
                CommandKind.VISIBLE_CONTROL,
            }:
                if target.casefold() != top.intent.target.casefold():
                    return UnrecognizedCommand()
                if top.intent.kind is CommandKind.OPEN_CHAT:
                    if step.app_phrase is None:
                        return UnrecognizedCommand()
                    app = self.generator.names.resolve(step.app_phrase)
                    if (
                        not app.exact
                        or len(app.candidates) != 1
                        or app.candidates[0].app_id != top.intent.app
                    ):
                        return UnrecognizedCommand()
                if top.intent.kind is CommandKind.VISIBLE_CONTROL and (
                    step.control_state != top.intent.control_state
                    or top.intent.control_observation is None
                    or not top.intent.control_observation.observed_at
                    <= monotonic()
                    < top.intent.control_observation.deadline
                ):
                    return UnrecognizedCommand()
                if (
                    top.intent.kind is CommandKind.VISIBLE_CONTROL
                    and step.target_id is not None
                ):
                    if not any(
                        option.option_id == step.target_id
                        and option.label == top.intent.target
                        and option.observation == top.intent.control_observation
                        and option.anchor == top.intent.control_anchor
                        for option in context.visible_options
                    ):
                        return UnrecognizedCommand()
            elif top.intent.window_index is not None:
                if target != str(top.intent.window_index):
                    return UnrecognizedCommand()
            else:
                resolved = self.generator.names.resolve(target)
                if (
                    not resolved.exact
                    or len(resolved.candidates) != 1
                    or resolved.candidates[0].app_id != top.intent.target
                ):
                    return UnrecognizedCommand()
        if top.target_requires_clarification:
            option = next(
                (
                    item
                    for item in self.generator.names.model_options()
                    if item.app_id == top.intent.target
                ),
                None,
            )
            if option is None:
                return UnrecognizedCommand()
            return NeedsClarification(
                PendingAppClarification(
                    (SpokenAppCandidate(option.app_id, option.display_name),),
                    confirmation=True,
                    operation=top.intent.kind,
                )
            )
        # Never pass a model-rewritten sentence to the legacy source verifier.
        trace = RecoveryTrace(
            source.text,
            top.control_span,
            top.canonical_control,
            top.source,
            "semantic_and_independent_role_evidence",
            top.similarity,
        )
        return ReadyCommand(replace(top.intent, recovery=trace))


class SpeechRecoveryInterpreter:
    """Keep final original text intact; release PCM before semantic inference."""

    def __init__(
        self,
        base: CommandInterpreter,
        recovery: SpeechCommandRecovery,
        *,
        policy: AudioRecoveryPolicy | None = None,
    ) -> None:
        self.base = base
        self.recovery = recovery
        self.policy = policy or AudioRecoveryPolicy()

    def interpret(
        self,
        text: str,
        *,
        language: str | None,
        context: CommandContext,
        pending: PendingCommandClarification | None,
    ) -> Interpretation:
        if not context.is_final_transcript:
            return self.base.interpret(
                text, language=language, context=context, pending=pending
            )
        audio = context.retained_audio
        try:
            elapsed = (
                max(
                    0.0,
                    (perf_counter_ns() - context.transcript_emitted_ns) / 1_000_000_000,
                )
                if context.transcript_emitted_ns is not None
                else 0.0
            )
            with budget(self.policy.total_seconds - elapsed):
                direct = self.recovery.rules.interpret(
                    text, language=language, context=context, pending=pending
                )
                if (
                    pending is None
                    and isinstance(direct, NotACommand)
                    and explicit_non_action_role(text, language)
                ):
                    return direct
                candidates = self.recovery.generator.generate(
                    text, language, context, pending
                )
                evidence = context.speech_evidence
                if (
                    audio is not None
                    and not _intents(direct)
                    and not (evidence and evidence.alternatives)
                ):
                    try:
                        hypothesis = audio.reprocess()
                    except SpeechToTextError, OSError, ValueError:
                        hypothesis = None
                    if (
                        hypothesis is not None
                        and hypothesis.text.strip() != text.strip()
                    ):
                        evidence = SpeechEvidence(
                            evidence.engine if evidence else hypothesis.engine,
                            (hypothesis,),
                            evidence.scores if evidence else (),
                        )
                if audio is not None:
                    audio.close()
                check_operation()
                # A contrary or uninterpretable real hypothesis cannot be
                # outvoted. Unknown scores never become intent confidence.
                for hypothesis in evidence.alternatives if evidence else ():
                    other = self.recovery.rules.interpret(
                        hypothesis.text,
                        language=language,
                        context=context,
                        pending=pending,
                    )
                    expected = _intents(direct) or (
                        candidates[0].steps if candidates else ()
                    )
                    if not expected or _intents(other) != expected:
                        alternative_candidates = self.recovery.generator.generate(
                            hypothesis.text, language, context, pending
                        )
                        if (
                            not expected
                            or not alternative_candidates
                            or alternative_candidates[0].steps != expected
                        ):
                            return self.recovery.clarify(expected + _intents(other))
                context = replace(
                    context,
                    speech_evidence=evidence,
                    retained_audio=None,
                    recovery_candidates=candidates,
                )
                result = self.base.interpret(
                    text, language=language, context=context, pending=pending
                )
                check_operation()
                return result
        except OperationStopped:
            return UnrecognizedCommand()
        finally:
            if audio is not None:
                audio.close()
