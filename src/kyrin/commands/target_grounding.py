"""Check resolved targets against words in the original utterance.

This proposal-only check uses narrow English/Persian source grammars. Unknown
wording clarifies rather than trusting a model-supplied app or chat name.
"""

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from kyrin.commands.app_names import AppNameResolver
from kyrin.commands.operation_verifier import (
    OperationEvidenceExtractor,
    RuleBasedOperationEvidence,
)
from kyrin.commands.target_resolution import TargetResolution, TargetResolutionStatus
from kyrin.commands.understanding import (
    RequestedOperation,
    UnderstandingInput,
    UnderstandingResult,
    UnderstandingStatus,
)


class TargetGroundingStatus(StrEnum):
    MATCHED = "matched"
    CLARIFY = "clarify"


@dataclass(frozen=True, slots=True)
class TargetGrounding:
    status: TargetGroundingStatus
    reason: str | None = None


_EN_ACTION = re.compile(
    r"^(?:exit fullscreen|leave fullscreen|unfullscreen|unmaximize|"
    r"maximize|minimize|fullscreen|restore|bring back|show|"
    r"close|exit|quit|open|go to)\s+"
)
_EN_CHAT_POSSESSIVE = re.compile(
    r"^(?P<name>.+?)'s (?:chat|conversation)(?: in (?P<app>.+))?$"
)
_EN_CHAT_PREFIX = re.compile(
    r"^(?:the )?(?:chat|conversation)(?: with)? (?P<name>.+?)"
    r"(?: in (?P<app>.+))?$"
)
_FA_ENDING = re.compile(
    r"(?:از\s+تمام\s+صفحه\s+خارج\s+کن(?:ید)?|"
    r"به\s+اندازه\s+عادی\s+برگردان(?:ید)?|"
    r"تمام\s+صفحه\s+کن(?:ید)?|بزرگ\s+کن(?:ید)?|"
    r"کوچک\s+کن(?:ید)?|دوباره\s+نشان\s+بده(?:ید)?|"
    r"برگردان(?:ید)?|ببند(?:ید)?|باز\s+کن(?:ید)?)$"
)
_FA_CHAT = re.compile(r"^(?:چت|گفتگو|گفت\s+و\s+گو)\s+(?P<name>.+)$")


def _words(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.replace("ي", "ی").replace("ك", "ک")
    return " ".join(re.findall(r"[^\W_]+", value, flags=re.UNICODE))


def _strip_case_marker(value: str) -> str:
    return re.sub(r"\s+(?:را|رو)$", "", value).strip()


def _source_names(
    clause: str, operation: RequestedOperation, language: str
) -> tuple[str, str | None] | None:
    """Return (app or chat name, explicit chat app) only for reviewed syntax."""

    if language == "en":
        body = _EN_ACTION.sub("", clause, count=1)
        if body == clause:
            return None
        body = re.sub(r"^(?:the|a)\s+", "", body)
        if operation is RequestedOperation.OPEN_CHAT:
            match = _EN_CHAT_POSSESSIVE.fullmatch(body) or _EN_CHAT_PREFIX.fullmatch(
                body
            )
            if match is None:
                return None
            return match.group("name").strip(), match.group("app")
        body = re.sub(r"\s+(?:window|app|application)$", "", body)
        return body.strip(), None

    if language == "fa":
        body = _FA_ENDING.sub("", clause, count=1).strip()
        if body == clause:
            return None
        body = _strip_case_marker(body)
        if operation is RequestedOperation.OPEN_CHAT:
            match = _FA_CHAT.fullmatch(body)
            if match is None:
                return None
            name = match.group("name")
            parts = re.split(r"\s+(?:در|داخل)\s+", name, maxsplit=1)
            if len(parts) == 2:
                return _strip_case_marker(parts[0]), _strip_case_marker(parts[1])
            return _strip_case_marker(name), None
        return body, None
    return None


class SourceTargetGrounder:
    """Require the resolved app and chat name to be supported by source text."""

    def __init__(
        self,
        app_names: AppNameResolver,
        extractor: OperationEvidenceExtractor | None = None,
    ) -> None:
        self._app_names = app_names
        self._extractor = extractor or RuleBasedOperationEvidence()

    def verify(
        self,
        source: UnderstandingInput,
        proposal: UnderstandingResult,
        resolution: TargetResolution,
    ) -> TargetGrounding:
        if (
            proposal.status is not UnderstandingStatus.READY
            or resolution.status is not TargetResolutionStatus.RESOLVED
            or len(proposal.candidates[0].steps) != len(resolution.steps)
        ):
            return TargetGrounding(TargetGroundingStatus.CLARIFY, "unresolved_proposal")
        primary = self._verify_text(source.text, source.language, proposal, resolution)
        if primary.reason is not None:
            return primary
        for alternative in source.alternatives:
            other = self._verify_text(
                alternative, source.language, proposal, resolution
            )
            if other.reason is not None:
                return TargetGrounding(
                    TargetGroundingStatus.CLARIFY, "alternative_target_conflict"
                )
        return TargetGrounding(TargetGroundingStatus.MATCHED)

    def _verify_text(
        self,
        text: str,
        language: str | None,
        proposal: UnderstandingResult,
        resolution: TargetResolution,
    ) -> TargetGrounding:
        evidence = self._extractor.extract(text, language=language)
        steps = proposal.candidates[0].steps
        if evidence.reason is not None or len(evidence.clauses) != len(steps):
            return TargetGrounding(TargetGroundingStatus.CLARIFY, "source_uncovered")
        code = language.strip().lower().split("-", 1)[0] if language else ""
        for clause, operation, proposed, resolved in zip(
            evidence.clauses, evidence.operations, steps, resolution.steps, strict=True
        ):
            if (
                operation is not proposed.operation
                or operation is not resolved.operation
            ):
                return TargetGrounding(
                    TargetGroundingStatus.CLARIFY, "operation_mismatch"
                )
            names = _source_names(clause, operation, code)
            if names is None or not _words(names[0]):
                return TargetGrounding(
                    TargetGroundingStatus.CLARIFY, "target_uncovered"
                )
            source_name, source_app = names
            if operation is RequestedOperation.OPEN_CHAT:
                if _words(source_name) != _words(proposed.target_phrase or ""):
                    return TargetGrounding(
                        TargetGroundingStatus.CLARIFY, "chat_name_mismatch"
                    )
                if source_app is None:
                    if proposed.app_phrase is not None:
                        return TargetGrounding(
                            TargetGroundingStatus.CLARIFY, "unspoken_chat_app"
                        )
                elif not self._matches_app(source_app, resolved.app_id):
                    return TargetGrounding(
                        TargetGroundingStatus.CLARIFY, "chat_app_mismatch"
                    )
            elif not self._matches_app(source_name, resolved.app_id):
                return TargetGrounding(TargetGroundingStatus.CLARIFY, "app_mismatch")
        return TargetGrounding(TargetGroundingStatus.MATCHED)

    def _matches_app(self, source_name: str, app_id: str) -> bool:
        match = self._app_names.resolve(source_name)
        return (
            match.exact
            and len(match.candidates) == 1
            and match.candidates[0].app_id == app_id
        )
