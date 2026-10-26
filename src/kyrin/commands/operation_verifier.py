"""Check proposed operations against independent evidence in original text.

This is a conservative, proposal-only boundary. A positive result says only
that the operation words agree; target identity, permission, and execution
remain separate checks.
"""

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from kyrin.commands.understanding import (
    RequestedOperation,
    UnderstandingInput,
    UnderstandingResult,
    UnderstandingStatus,
)
from kyrin.commands.wake_names import DEFAULT_WAKE_NAMES


class OperationVerificationStatus(StrEnum):
    MATCHED = "matched"
    CLARIFY = "clarify"
    NO_ACTION = "no_action"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class OperationVerification:
    status: OperationVerificationStatus
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class OperationEvidence:
    operations: tuple[RequestedOperation, ...] = ()
    clauses: tuple[str, ...] = ()
    reason: str | None = None


class OperationEvidenceExtractor(Protocol):
    """A replaceable source-language rule pack; never the proposal model."""

    def extract(self, text: str, *, language: str | None) -> OperationEvidence: ...


_EN_ACTION = re.compile(
    r"^(?:exit fullscreen|leave fullscreen|unfullscreen|unmaximize|"
    r"maximize|minimize|hide|fullscreen|restore|bring back|show|"
    r"close|exit|quit|open|go to|launch|start|switch to)\b"
)
_EN_FORBIDDEN = re.compile(
    r"\b(?:restart|reboot|shut down|shutdown|power off|log out|logout|"
    r"suspend|sleep|search|click|send|delete|type)\b"
)
_EN_NEGATION = re.compile(r"\b(?:not|never|no|don't|dont|cannot|can't)\b")
_EN_SPLIT = re.compile(r"\s*(?:[;,]|\b(?:and|then)\b)\s*")
_EN_WAKE = re.compile(
    r"^(?:" + "|".join(re.escape(name) for name in DEFAULT_WAKE_NAMES) + r")\b\s*,?\s*"
)
_EN_OPERATION = {
    "exit fullscreen": RequestedOperation.UNFULLSCREEN_APP,
    "leave fullscreen": RequestedOperation.UNFULLSCREEN_APP,
    "unfullscreen": RequestedOperation.UNFULLSCREEN_APP,
    "unmaximize": RequestedOperation.UNMAXIMIZE_APP,
    "maximize": RequestedOperation.MAXIMIZE_APP,
    "minimize": RequestedOperation.MINIMIZE_APP,
    "hide": RequestedOperation.MINIMIZE_APP,
    "fullscreen": RequestedOperation.FULLSCREEN_APP,
    "restore": RequestedOperation.RESTORE_APP,
    "bring back": RequestedOperation.RESTORE_APP,
    "show": RequestedOperation.RESTORE_APP,
    "close": RequestedOperation.CLOSE_APP_WINDOW,
    "exit": RequestedOperation.CLOSE_APP_WINDOW,
    "quit": RequestedOperation.CLOSE_APP_WINDOW,
    "open": RequestedOperation.OPEN_APP,
    "go to": RequestedOperation.OPEN_APP,
    "launch": RequestedOperation.OPEN_APP,
    "start": RequestedOperation.OPEN_APP,
    "switch to": RequestedOperation.OPEN_APP,
}

_FA_FORBIDDEN = re.compile(
    r"ریستارت|دوباره\s+راه\s*اندازی|راه\s*اندازی\s+مجدد|خاموش|"
    r"خروج\s+از\s+حساب|تعلیق|جستجو|سرچ|کلیک|ارسال|حذف"
)
_FA_NEGATION = re.compile(r"(?:\bنکن\w*|\bنبند\w*|\bنمی\w*|\bهرگز\b|\bنه\b)")
_FA_SPLIT = re.compile(r"\s*(?:[؛;]|\b(?:و|بعد|سپس)\b)\s*")
_FA_ACTIONS = (
    (
        re.compile(r"از\s+تمام\s+صفحه\s+خارج\s+کن(?:ید)?$"),
        RequestedOperation.UNFULLSCREEN_APP,
    ),
    (
        re.compile(r"به\s+اندازه\s+عادی\s+برگردان(?:ید)?$"),
        RequestedOperation.UNMAXIMIZE_APP,
    ),
    (re.compile(r"تمام\s+صفحه\s+کن(?:ید)?$"), RequestedOperation.FULLSCREEN_APP),
    (re.compile(r"بزرگ\s+کن(?:ید)?$"), RequestedOperation.MAXIMIZE_APP),
    (re.compile(r"کوچک\s+کن(?:ید)?$"), RequestedOperation.MINIMIZE_APP),
    (re.compile(r"دوباره\s+نشان\s+بده(?:ید)?$"), RequestedOperation.RESTORE_APP),
    (re.compile(r"نشان\s+بده(?:ید)?$"), RequestedOperation.RESTORE_APP),
    (re.compile(r"برگردان(?:ید)?$"), RequestedOperation.RESTORE_APP),
    (re.compile(r"پنهان\s+کن(?:ید)?$"), RequestedOperation.MINIMIZE_APP),
    (re.compile(r"ببند(?:ید)?$"), RequestedOperation.CLOSE_APP_WINDOW),
    (re.compile(r"باز\s+کن(?:ید)?$"), RequestedOperation.OPEN_APP),
    (re.compile(r"اجرا\s+کن(?:ید)?$"), RequestedOperation.OPEN_APP),
)
_EN_CHAT = re.compile(r"\b(?:chat|conversation)\b")
_FA_CHAT = re.compile(r"(?:چت|گفتگو|گفت\s*و\s*گو)")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    text = text.replace("’", "'")
    return " ".join(text.split())


class RuleBasedOperationEvidence:
    """Small EN/FA source-text profiles; other languages fail closed."""

    def extract(self, text: str, *, language: str | None) -> OperationEvidence:
        code = language.strip().lower().split("-", 1)[0] if language else None
        if code not in {"en", "fa"}:
            return OperationEvidence(reason="unsupported_language")
        normalized = _normalize(text)
        if not normalized:
            return OperationEvidence(reason="empty_text")
        if code == "en":
            return self._english(normalized)
        return self._persian(normalized)

    def _english(self, text: str) -> OperationEvidence:
        text = _EN_WAKE.sub("", text)
        if _EN_NEGATION.search(text):
            return OperationEvidence(reason="negated_or_uncertain_source")
        if _EN_FORBIDDEN.search(text) or re.search(r"\bor\b", text):
            return OperationEvidence(reason="unsupported_or_alternative_operation")
        operations: list[RequestedOperation] = []
        clauses: list[str] = []
        for clause in _EN_SPLIT.split(text):
            clause = clause.strip(" .!?\t")
            clause = re.sub(r"^(?:please|kindly|gently)\s+", "", clause)
            if not clause:
                return OperationEvidence(reason="incomplete_clause")
            match = _EN_ACTION.match(clause)
            if match is None:
                return OperationEvidence(reason="operation_not_explicit")
            operation = _EN_OPERATION[match.group()]
            if _EN_CHAT.search(clause):
                if operation is not RequestedOperation.OPEN_APP:
                    return OperationEvidence(reason="chat_operation_unsupported")
                operation = RequestedOperation.OPEN_CHAT
            operations.append(operation)
            clauses.append(clause)
        return OperationEvidence(tuple(operations), tuple(clauses))

    def _persian(self, text: str) -> OperationEvidence:
        if _FA_NEGATION.search(text):
            return OperationEvidence(reason="negated_or_uncertain_source")
        if _FA_FORBIDDEN.search(text) or re.search(r"\bیا\b", text):
            return OperationEvidence(reason="unsupported_or_alternative_operation")
        operations: list[RequestedOperation] = []
        clauses: list[str] = []
        for clause in _FA_SPLIT.split(text):
            clause = clause.strip(" .!؟?،\t")
            if not clause:
                return OperationEvidence(reason="incomplete_clause")
            operation = next(
                (item for pattern, item in _FA_ACTIONS if pattern.search(clause)),
                None,
            )
            if operation is None:
                return OperationEvidence(reason="operation_not_explicit")
            if _FA_CHAT.search(clause):
                if operation is not RequestedOperation.OPEN_APP:
                    return OperationEvidence(reason="chat_operation_unsupported")
                operation = RequestedOperation.OPEN_CHAT
            operations.append(operation)
            clauses.append(clause)
        return OperationEvidence(tuple(operations), tuple(clauses))


class SourceOperationVerifier:
    """Require every affirmative proposed operation to agree with source text."""

    def __init__(self, extractor: OperationEvidenceExtractor | None = None) -> None:
        self._extractor = extractor or RuleBasedOperationEvidence()

    def verify(
        self, source: UnderstandingInput, proposal: UnderstandingResult
    ) -> OperationVerification:
        if proposal.status in {
            UnderstandingStatus.NOT_COMMAND,
            UnderstandingStatus.NEGATED,
        }:
            return OperationVerification(OperationVerificationStatus.NO_ACTION)
        if proposal.status is UnderstandingStatus.UNSUPPORTED:
            return OperationVerification(OperationVerificationStatus.UNSUPPORTED)
        if proposal.status is not UnderstandingStatus.READY:
            return OperationVerification(
                OperationVerificationStatus.CLARIFY, "model_uncertainty"
            )
        proposed = tuple(step.operation for step in proposal.candidates[0].steps)
        if any(operation.value.endswith("_system") for operation in proposed):
            return OperationVerification(
                OperationVerificationStatus.UNSUPPORTED, "separate_power_flow"
            )
        evidence = self._extractor.extract(source.text, language=source.language)
        if evidence.reason is not None:
            return OperationVerification(
                OperationVerificationStatus.CLARIFY, evidence.reason
            )
        if evidence.operations != proposed:
            return OperationVerification(
                OperationVerificationStatus.CLARIFY, "operation_mismatch"
            )
        for alternative in source.alternatives:
            other = self._extractor.extract(alternative, language=source.language)
            if other.reason is not None or other.operations != proposed:
                return OperationVerification(
                    OperationVerificationStatus.CLARIFY,
                    "alternative_transcript_conflict",
                )
        return OperationVerification(OperationVerificationStatus.MATCHED)
