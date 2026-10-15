"""Use a selected model only when bounded rules cannot decide a command."""

import re
import unicodedata
from collections.abc import Callable

from kyrin.commands.app_names import AppNameResolver
from kyrin.commands.interpreter import (
    CommandInterpreter,
    ConversationalReply,
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
    PendingAppClarification,
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
    ConfirmationDecision,
    RequestedOperation,
    UnderstandingInput,
    UnderstandingResult,
    UnderstandingStatus,
)


def _words(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("ي", "ی").replace("ك", "ک")
    return tuple(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))


def _spoken_target_occurs(text: str, target: str) -> bool:
    source, name = _words(text), _words(target)
    return bool(name) and any(
        source[index : index + len(name)] == name
        for index in range(len(source) - len(name) + 1)
    )


_NEGATIVE_REPLY = re.compile(
    r"\b(?:no|not|never|don't|dont|nein|nicht|non|pas|нет|نہیں|نه|خیر)\b"
    r"|不要|别|不|لا"
)
_OTHER_WINDOW_COLLECTION = re.compile(
    r"\b(?:installed|downloaded)\s+apps?\b|"
    r"\b(?:browser\s+)?tabs?\b|\bfiles?\b|"
    r"برنامه\s+های\s+(?:نصب\s+شده|دانلود\s+شده)|"
    r"تب\s+های\s+مرورگر|فایل\s+ها"
)
_OVERVIEW_NEGATION = re.compile(r"نشان\s+نده|نمایش\s+نده|نمی\s*خواهم")
_OVERVIEW_EXTRA_ACTION = re.compile(
    r"\b(?:and|then)\b.{0,60}\b(?:open|close|minimize|restart|delete|send)\b|"
    r"(?:و|بعد|سپس).{0,60}(?:باز|ببند|خاموش|حذف|ارسال)\s+کن"
)
_AMBIGUOUS_PAGES = re.compile(r"\bpages?\b|صفحه|صفحات")
_DESKTOP_QUALIFIER = re.compile(
    r"\b(?:window|windows|app|apps|application|applications|desktop)\b|"
    r"پنجره|برنامه"
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
        action_review: Callable[[CommandIntent, CommandContext], Interpretation]
        | None = None,
    ) -> None:
        self._rules = rules
        self._model = model
        self._app_names = app_names
        self._operations = SourceOperationVerifier()
        self._source_operations = RuleBasedOperationEvidence()
        self._targets = SemanticTargetResolver(
            app_names,
            allowed_apps=allowed_apps,
            supported_chat_apps=supported_chat_apps,
        )
        self._grounder = SourceTargetGrounder(app_names)
        self._action_review = action_review

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
        if pending is not None:
            if _words(text) == ("یا",):
                return NeedsClarification(pending)
            if isinstance(direct, (ReadyCommand, ReadyPlan, DeclinedClarification)):
                return direct
            if isinstance(direct, NeedsClarification) and direct.pending != pending:
                # The rules advanced to a new question (for example, from
                # app identity to close confirmation). Never restore the old
                # question because a model reply is slow or unavailable.
                return direct
            if isinstance(pending, PendingAppClarification) and (
                self._source_operations.extract(text, language=language).operations
            ):
                # A new explicit command replaces an older app-name question.
                # It still passes through normal model, source, and target checks.
                return self.interpret(
                    text, language=language, context=context, pending=None
                )
            if (
                isinstance(pending, PendingAppClarification)
                and pending.confirmation
                and len(_words(text)) <= 5
            ):
                if self._source_operations.extract(
                    text, language=language
                ).operations:
                    return direct
                try:
                    decision = self._model.classify_confirmation(
                        UnderstandingInput(text, language),
                        question=(
                            f"Close {pending.candidates[0].display_name}?"
                            if pending.operation is CommandKind.CLOSE_APP_WINDOW
                            else (
                                "Is this the "
                                f"{pending.candidates[0].display_name} app?"
                            )
                        ),
                    )
                except CommandModelError, ValueError:
                    return NeedsClarification(pending)
                if decision is ConfirmationDecision.YES and not _NEGATIVE_REPLY.search(
                    text.casefold()
                ):
                    return self._rules.interpret(
                        "yes", language="en", context=context, pending=pending
                    )
                if decision is ConfirmationDecision.NO:
                    return DeclinedClarification()
                return NeedsClarification(pending)
            return direct
        if isinstance(
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
        if proposal.status is UnderstandingStatus.RESPOND:
            evidence = self._source_operations.extract(text, language=language)
            if evidence.operations or evidence.reason != "operation_not_explicit":
                return UnrecognizedCommand()
            assert proposal.reply is not None
            return ConversationalReply(proposal.reply)
        if proposal.status is not UnderstandingStatus.READY:
            return UnrecognizedCommand()
        steps = proposal.candidates[0].steps
        if (
            len(steps) == 1
            and steps[0].operation is RequestedOperation.SHOW_ALL_WINDOWS
        ):
            if (
                _NEGATIVE_REPLY.search(text.casefold())
                or _OVERVIEW_NEGATION.search(text)
                or _OTHER_WINDOW_COLLECTION.search(text.casefold())
                or _OVERVIEW_EXTRA_ACTION.search(text.casefold())
                or (
                    _AMBIGUOUS_PAGES.search(text.casefold())
                    and not _DESKTOP_QUALIFIER.search(text.casefold())
                )
            ):
                return UnrecognizedCommand()
            intent = CommandIntent(CommandKind.SHOW_ALL_WINDOWS, "desktop")
            return (
                self._action_review(intent, context)
                if self._action_review is not None
                else ReadyCommand(intent)
            )
        evidence = self._source_operations.extract(text, language=language)
        if evidence.reason in {"unsupported_language", "operation_not_explicit"}:
            if _NEGATIVE_REPLY.search(text.casefold()):
                return UnrecognizedCommand()
            pending_app = self._uncovered_open_app(source, proposal, context)
            return (
                NeedsClarification(pending_app)
                if pending_app
                else UnrecognizedCommand()
            )
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
            if self._action_review is not None:
                return self._action_review(intents[0], context)
            return ReadyCommand(intents[0])
        if self._action_review is not None:
            for intent in intents:
                if not isinstance(self._action_review(intent, context), ReadyCommand):
                    return UnrecognizedCommand()
        return ReadyPlan(CommandPlan(tuple(intents)))

    def _uncovered_open_app(
        self,
        source: UnderstandingInput,
        proposal: UnderstandingResult,
        context: CommandContext,
    ) -> PendingAppClarification | None:
        """For an unreviewed language, request consent instead of execution."""
        steps = proposal.candidates[0].steps
        if len(steps) != 1 or steps[0].operation is not RequestedOperation.OPEN_APP:
            return None
        target = steps[0].target_phrase
        if target is None or not _spoken_target_occurs(source.text, target):
            return None
        resolution = self._targets.resolve(proposal, context=context)
        if resolution.status is not TargetResolutionStatus.RESOLVED:
            return None
        match = self._app_names.resolve(target)
        if not match.exact or len(match.candidates) != 1:
            return None
        return PendingAppClarification(match.candidates, confirmation=True)

    def _unusable_model_result(
        self, direct: Interpretation, source: UnderstandingInput
    ) -> Interpretation:
        evidence = self._source_operations.extract(
            source.text, language=source.language
        )
        if evidence.reason is None and evidence.operations:
            return UnrecognizedCommand()
        return direct
