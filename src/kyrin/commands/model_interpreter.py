"""Use a selected model only when bounded rules cannot decide a command."""

from kyrin.commands.app_names import AppNameResolver
from kyrin.commands.interpreter import (
    CommandInterpreter,
    DeclinedClarification,
    Interpretation,
    NeedsClarification,
    ReadyCommand,
    ReadyPlan,
    UnrecognizedCommand,
    WakeOnly,
)
from kyrin.commands.models import (
    CommandContext,
    CommandIntent,
    CommandKind,
    CommandPlan,
    PendingCommandClarification,
)
from kyrin.commands.ollama_engine import CommandModelError
from kyrin.commands.operation_verifier import (
    OperationVerificationStatus,
    RuleBasedOperationEvidence,
    SourceOperationVerifier,
)
from kyrin.commands.target_grounding import SourceTargetGrounder, TargetGroundingStatus
from kyrin.commands.target_resolution import (
    SemanticTargetResolver,
    TargetResolutionStatus,
)
from kyrin.commands.understanding import (
    CommandUnderstandingEngine,
    UnderstandingInput,
    UnderstandingStatus,
)


class ModelAssistedInterpreter:
    """Convert independently verified proposals to the existing command domain."""

    def __init__(
        self,
        rules: CommandInterpreter,
        model: CommandUnderstandingEngine,
        app_names: AppNameResolver,
        *,
        allowed_apps: frozenset[str],
        supported_chat_apps: frozenset[str],
    ) -> None:
        self._rules = rules
        self._model = model
        self._operations = SourceOperationVerifier()
        self._source_operations = RuleBasedOperationEvidence()
        self._targets = SemanticTargetResolver(
            app_names,
            allowed_apps=allowed_apps,
            supported_chat_apps=supported_chat_apps,
        )
        self._grounder = SourceTargetGrounder(app_names)

    def interpret(
        self,
        text: str,
        *,
        language: str | None,
        context: CommandContext,
        pending: PendingCommandClarification | None,
    ) -> Interpretation:
        direct = self._rules.interpret(
            text, language=language, context=context, pending=pending
        )
        if pending is not None or isinstance(
            direct,
            (
                ReadyCommand,
                ReadyPlan,
                NeedsClarification,
                DeclinedClarification,
                WakeOnly,
            ),
        ):
            return direct
        if not text.strip():
            return direct
        source = UnderstandingInput(text, language)
        try:
            proposal = self._model.understand(source, context=context)
        except CommandModelError, ValueError:
            return self._unusable_model_result(direct, source)
        if proposal.status in {
            UnderstandingStatus.NOT_COMMAND,
            UnderstandingStatus.NEGATED,
        }:
            return self._unusable_model_result(direct, source)
        if proposal.status is not UnderstandingStatus.READY:
            return UnrecognizedCommand()
        if (
            self._operations.verify(source, proposal).status
            is not OperationVerificationStatus.MATCHED
        ):
            return UnrecognizedCommand()
        resolution = self._targets.resolve(proposal, context=context)
        if resolution.status is not TargetResolutionStatus.RESOLVED:
            return UnrecognizedCommand()
        if (
            self._grounder.verify(source, proposal, resolution).status
            is not TargetGroundingStatus.MATCHED
        ):
            return UnrecognizedCommand()
        intents: list[CommandIntent] = []
        for step in resolution.steps:
            try:
                kind = CommandKind(step.operation.value)
            except ValueError:
                return UnrecognizedCommand()
            if kind is CommandKind.OPEN_CHAT:
                assert step.target_phrase is not None
                intents.append(CommandIntent(kind, step.target_phrase, step.app_id))
            else:
                intents.append(CommandIntent(kind, step.app_id))
        if len(intents) == 1:
            return ReadyCommand(intents[0])
        return ReadyPlan(CommandPlan(tuple(intents)))

    def _unusable_model_result(
        self, direct: Interpretation, source: UnderstandingInput
    ) -> Interpretation:
        evidence = self._source_operations.extract(
            source.text, language=source.language
        )
        if evidence.reason is None and evidence.operations:
            return UnrecognizedCommand()
        return direct
