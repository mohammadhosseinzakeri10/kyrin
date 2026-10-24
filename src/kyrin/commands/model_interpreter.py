"""Use a selected model only when bounded rules cannot decide a command."""

import re
from collections.abc import Callable
from dataclasses import replace
from typing import Protocol

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
from kyrin.commands.visible_options import VisibleOption
from kyrin.text_normalization import fold_case, source_spelling
from kyrin.timing import timed_stage


def _words(value: str) -> tuple[str, ...]:
    normalized = fold_case(value)
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
_VISIBLE_ACTION_EN = re.compile(
    r"\b(?:click|tap|press|select|choose|open|opened|show|go to|navigate to|"
    r"turn on|turn off|switch on|switch off|enable|disable|check|uncheck)\b"
)
_VISIBLE_ACTION_FA = re.compile(
    r"(?:کلیک|بزن|انتخاب|باز\s+کن|نشان\s+بده|برو|روشن\s+کن|"
    r"خاموش\s+کن|فعال\s+کن|غیرفعال\s+کن|تیک\s+بزن|تیک\s+بردار)"
)
_VISIBLE_ON = re.compile(
    r"\b(?:turn on|switch on|enable|check)\b|"
    r"\b(?:want|make|set|turn|switch)\b[^.!?]{0,60}\bon\b|"
    r"(?:روشن|(?<!غیر)فعال|تیک\s+بزن)"
)
_VISIBLE_OFF = re.compile(
    r"\b(?:turn off|switch off|disable|uncheck)\b|"
    r"\b(?:want|make|set|turn|switch)\b[^.!?]{0,60}\boff\b|"
    r"(?:خاموش|غیرفعال|تیک\s+بردار)"
)
_VISIBLE_EXCLUDED = re.compile(
    r"\b(?:if|when|maybe|perhaps|should i|how (?:do|can) i|"
    r"don't|dont|not|never|without|instead of)\b|"
    r"(?:اگر|شاید|چطور|چگونه|آیا|نباید|نکن|نمی\s*خواهم|به\s*جای)"
)
_SOURCE_NOT_INSTRUCTION = re.compile(
    r"^(?:what|why|how|who|where|when|the words|it says|this says)\b"
)
_SOURCE_QUOTES = re.compile(r'["“”«»]')
_SOURCE_NEGATION = re.compile(
    r"\b(?:no|not|never|don't|dont|without)\b|"
    r"(?:نکن|نمی\s*خواهم|نباید|هرگز)"
)
_EN_REQUEST_PREFIX = r"(?:please\s+|could you\s+|can you\s+|would you\s+)*"
_EN_VISIBLE_REQUEST = re.compile(
    r"^"
    + _EN_REQUEST_PREFIX
    + r"(?:click|tap|press|select|choose|open|show|go to|navigate to|"
    r"turn on|turn off|switch on|switch off|enable|disable|check|uncheck)\b"
    r"|^i (?:want|would like)\b.+\b(?:opened|on|off)\b"
)
_EN_SCROLL_REQUEST = re.compile(
    r"^" + _EN_REQUEST_PREFIX + r"scroll\s+(up|down)"
    r"(?:\s+(?:on|in)\s+(?:this|the|the current|the active)\s+(?:page|window))?"
    r"(?:\s+please)?[.!?]?"
)
_FA_SCROLL_REQUEST = re.compile(
    r"(?:لطفا\s+)?(?:این\s+صفحه\s+را\s+)?(?:به\s+)?"
    r"(?:(بالا|پایین)\s+(?:برو|(?:اسکرول|پیمایش)(?:\s+کن)?)|"
    r"(?:اسکرول|پیمایش)\s+(بالا|پایین)(?:\s+کن)?)[.!؟]?"
)


def _source_is_instruction(text: str, language: str | None, *, scroll: bool) -> bool:
    normalized = fold_case(text).strip()
    code = language.strip().lower().split("-", 1)[0] if language else None
    if (
        code not in {"en", "fa"}
        or _SOURCE_NEGATION.search(normalized)
        or _SOURCE_QUOTES.search(text)
        or _SOURCE_NOT_INSTRUCTION.search(normalized)
    ):
        return False
    if code == "en":
        return bool(
            (_EN_SCROLL_REQUEST if scroll else _EN_VISIBLE_REQUEST).search(normalized)
        )
    return bool(
        _FA_SCROLL_REQUEST.search(normalized)
        if scroll
        else _VISIBLE_ACTION_FA.search(normalized)
    )


def _source_scroll_operation(
    text: str, language: str | None
) -> RequestedOperation | None:
    """Extract one direction from a bounded request, independently of the model."""
    if not _source_is_instruction(text, language, scroll=True):
        return None
    assert language is not None
    code = language.strip().lower().split("-", 1)[0]
    pattern = _EN_SCROLL_REQUEST if code == "en" else _FA_SCROLL_REQUEST
    # Match the entire request: a direction in a quote, condition, second
    # instruction, or ambiguous suffix cannot authorize the proposed input.
    match = pattern.fullmatch(fold_case(text).strip())
    if match is None:
        return None
    direction = next(value for value in match.groups() if value is not None)
    return (
        RequestedOperation.SCROLL_UP
        if direction in {"up", "بالا"}
        else RequestedOperation.SCROLL_DOWN
    )


_CONFIRMABLE_APP_OPERATIONS = frozenset(
    {
        RequestedOperation.OPEN_APP,
        RequestedOperation.RESTORE_APP,
        RequestedOperation.MINIMIZE_APP,
        RequestedOperation.CLOSE_APP_WINDOW,
        RequestedOperation.MAXIMIZE_APP,
        RequestedOperation.UNMAXIMIZE_APP,
        RequestedOperation.FULLSCREEN_APP,
        RequestedOperation.UNFULLSCREEN_APP,
    }
)


class VisibleOptionsReader(Protocol):
    def read_options(
        self, expected_app: str, utterance: str
    ) -> tuple[VisibleOption, ...]: ...


def _visible_request_supported(
    text: str,
    target: str,
    state: bool | None,
    language: str | None,
    *,
    require_action_cue: bool = True,
) -> bool:
    """Check the proposal against the current utterance before UI grounding."""
    normalized = fold_case(text)
    if (
        not _source_is_instruction(text, language, scroll=False)
        or not _spoken_target_occurs(text, target)
        or _VISIBLE_EXCLUDED.search(normalized)
        or (
            require_action_cue
            and not (
                _VISIBLE_ACTION_EN.search(normalized)
                or _VISIBLE_ACTION_FA.search(normalized)
                or _VISIBLE_ON.search(normalized)
                or _VISIBLE_OFF.search(normalized)
            )
        )
    ):
        return False
    on = bool(_VISIBLE_ON.search(normalized))
    off = bool(_VISIBLE_OFF.search(normalized))
    if on and off:
        return False
    if not require_action_cue and not (on or off):
        return True
    return (
        (state is None and not (on or off))
        or (state is True and on)
        or (state is False and off)
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
        allow_visible_control: bool = False,
        visible_options_reader: VisibleOptionsReader | None = None,
        action_review: Callable[[CommandIntent, CommandContext], Interpretation]
        | None = None,
        available_operations: tuple[str, ...] | None = None,
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
        self._allow_visible_control = (
            allow_visible_control and visible_options_reader is not None
        )
        self._visible_options_reader = visible_options_reader
        self._available_operations = available_operations

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
        if not context.is_final_transcript:
            # Keep provisional previews on rules only, before confirmation
            # inference, catalog refresh, or visible-control inventory/OCR.
            return direct
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
                if self._source_operations.extract(text, language=language).operations:
                    return direct
                try:
                    with timed_stage("inference"):
                        decision = self._model.classify_confirmation(
                            UnderstandingInput(text, language),
                            question=(
                                f"Confirm {pending.operation.value} for "
                                f"{pending.candidates[0].display_name}?"
                                if pending.operation is not None
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
        context = replace(
            context,
            available_apps=self._app_names.model_options(),
            available_operations=self._available_operations,
            visible_control_enabled=self._allow_visible_control,
        )
        visible_cue = bool(
            _VISIBLE_ACTION_EN.search(fold_case(text))
            or _VISIBLE_ACTION_FA.search(fold_case(text))
            or _VISIBLE_ON.search(fold_case(text))
            or _VISIBLE_OFF.search(fold_case(text))
        )
        if (
            self._allow_visible_control
            and self._visible_options_reader is not None
            and context.observed_scroll_app
            and visible_cue
        ):
            context = replace(
                context,
                visible_options=self._visible_options_reader.read_options(
                    context.observed_scroll_app, text
                ),
            )
        try:
            with timed_stage("inference"):
                proposal = self._model.understand(source, context=context)
        except CommandModelError, ValueError:
            return self._unusable_model_result(direct, source)
        discovered_visible = False
        exact_visible_option: VisibleOption | None = None
        if (
            not visible_cue
            and self._allow_visible_control
            and self._visible_options_reader is not None
            and context.observed_scroll_app
            and proposal.status is UnderstandingStatus.READY
            and len(proposal.candidates[0].steps) == 1
            and proposal.candidates[0].steps[0].operation
            is RequestedOperation.VISIBLE_CONTROL
        ):
            initial_step = proposal.candidates[0].steps[0]
            if initial_step.target_phrase is None or not _spoken_target_occurs(
                text, initial_step.target_phrase
            ):
                return UnrecognizedCommand()
            if initial_step.target_id is not None:
                return UnrecognizedCommand()
            context = replace(
                context,
                visible_options=self._visible_options_reader.read_options(
                    context.observed_scroll_app, text
                ),
            )
            exact_matches = tuple(
                item
                for item in context.visible_options
                if _words(item.label) == _words(initial_step.target_phrase)
            )
            if len(exact_matches) == 1:
                exact_visible_option = exact_matches[0]
            else:
                try:
                    with timed_stage("inference"):
                        proposal = self._model.understand(source, context=context)
                except CommandModelError, ValueError:
                    return UnrecognizedCommand()
                if (
                    proposal.status is not UnderstandingStatus.READY
                    or len(proposal.candidates[0].steps) != 1
                    or proposal.candidates[0].steps[0].operation
                    is not RequestedOperation.VISIBLE_CONTROL
                    or _words(proposal.candidates[0].steps[0].target_phrase or "")
                    != _words(initial_step.target_phrase)
                    or proposal.candidates[0].steps[0].control_state
                    is not initial_step.control_state
                ):
                    return UnrecognizedCommand()
            discovered_visible = True
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
        if self._available_operations is not None and any(
            step.operation.value not in self._available_operations for step in steps
        ):
            return UnrecognizedCommand()
        if len(steps) == 1 and steps[0].operation in {
            RequestedOperation.SCROLL_UP,
            RequestedOperation.SCROLL_DOWN,
        }:
            if (
                context.observed_scroll_app is None
                or _source_scroll_operation(text, language) is not steps[0].operation
            ):
                return UnrecognizedCommand()
            intent = CommandIntent(
                CommandKind(steps[0].operation.value), context.observed_scroll_app
            )
            return (
                self._action_review(intent, context)
                if self._action_review is not None
                else ReadyCommand(intent)
            )
        if any(step.operation is RequestedOperation.VISIBLE_CONTROL for step in steps):
            if (
                not self._allow_visible_control
                or not context.observed_scroll_app
                or len(steps) != 1
            ):
                return UnrecognizedCommand()
            visible_step = steps[0]
            target = visible_step.target_phrase
            option = exact_visible_option or next(
                (
                    item
                    for item in context.visible_options
                    if item.option_id == visible_step.target_id
                ),
                None,
            )
            if (
                target is None
                or option is None
                or _words(option.label) != _words(target)
                or (visible_step.control_state is not None and option.checked is None)
                or not _visible_request_supported(
                    text,
                    target,
                    visible_step.control_state,
                    language,
                    require_action_cue=not discovered_visible,
                )
            ):
                return UnrecognizedCommand()
            try:
                intent = CommandIntent(
                    CommandKind.VISIBLE_CONTROL,
                    option.label,
                    control_state=visible_step.control_state,
                    control_source=option.source,
                    control_accessibility=option.accessibility,
                    control_anchor=option.anchor,
                    control_window_app=context.observed_scroll_app,
                    control_observation=option.observation,
                )
            except ValueError:
                return UnrecognizedCommand()
            return (
                self._action_review(intent, context)
                if self._action_review is not None
                else ReadyCommand(intent)
            )
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
            pending_app = self._uncovered_app_action(source, proposal, context)
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
                intents.append(
                    CommandIntent(
                        kind, source_spelling(text, step.target_phrase), step.app_id
                    )
                )
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

    def _uncovered_app_action(
        self,
        source: UnderstandingInput,
        proposal: UnderstandingResult,
        context: CommandContext,
    ) -> PendingAppClarification | None:
        """For an unreviewed language, confirm an exact app action explicitly."""
        steps = proposal.candidates[0].steps
        if len(steps) != 1 or steps[0].operation not in _CONFIRMABLE_APP_OPERATIONS:
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
        return PendingAppClarification(
            match.candidates,
            confirmation=True,
            operation=CommandKind(steps[0].operation.value),
        )

    def _unusable_model_result(
        self, direct: Interpretation, source: UnderstandingInput
    ) -> Interpretation:
        evidence = self._source_operations.extract(
            source.text, language=source.language
        )
        if evidence.reason is None and evidence.operations:
            return UnrecognizedCommand()
        return direct
