"""Permission-aware Telegram chat navigation with fresh visual verification."""

import subprocess
from collections.abc import Callable
from pathlib import Path
from time import monotonic, sleep
from typing import Protocol

from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.telegram_verification import ChatSearchMatch
from kyrin.commands.models import CommandKind

_HELPER = Path(__file__).with_name("telegram_portal_helper.py")
_SAVED_MESSAGES_TARGETS = frozenset({"saved messages", "saved massages"})
_SEARCH_SETTLE_SECONDS = 3.0
_SEARCH_POLL_SECONDS = 0.2
WindowIdentityReader = Callable[[], tuple[str, int] | None]


def _same_search_box(first: ChatSearchMatch, second: ChatSearchMatch) -> bool:
    """Allow minor OCR box jitter while keeping one result and image size fixed."""
    return (
        (first.image_width, first.image_height)
        == (second.image_width, second.image_height)
        and all(
            abs(left - right) <= 5
            for left, right in zip(
                (first.left, first.top, first.width, first.height),
                (second.left, second.top, second.width, second.height),
                strict=True,
            )
        )
    )


class ChatVerifier(Protocol):
    def ready(self) -> bool: ...

    def find_search_result(
        self, app_id: str, pid: int, target: str
    ) -> ChatSearchMatch | None: ...

    def verify(self, app_id: str, pid: int, target: str = "Saved Messages") -> bool: ...


class TelegramSavedMessagesExecutor:
    """Keep Saved Messages fast; search other chats only with bounded input."""

    def __init__(
        self,
        delegate: ActionExecutor,
        *,
        telegram_desktop_id: str,
        identity_reader: WindowIdentityReader,
        verifier: ChatVerifier,
        system_python: str = "/usr/bin/python3",
        helper_path: Path = _HELPER,
    ) -> None:
        self._delegate = delegate
        self._telegram_desktop_id = telegram_desktop_id
        self._identity_reader = identity_reader
        self._verifier = verifier
        self._system_python = system_python
        self._helper_path = helper_path

    def execute(self, request: ActionRequest) -> ActionResult:
        intent = request.intent
        if intent.kind is not CommandKind.OPEN_CHAT:
            return self._delegate.execute(request)
        if intent.app != "telegram":
            return ActionResult(
                request.key, ActionOutcome.FAILED, error_code="unsupported_chat"
            )
        if not self._verifier.ready():
            return ActionResult(
                request.key, ActionOutcome.FAILED, error_code="screen_access_required"
            )
        identity = self._identity_reader()
        if identity is None or identity[0] != self._telegram_desktop_id:
            return ActionResult(
                request.key, ActionOutcome.FAILED, error_code="telegram_not_active"
            )
        target = " ".join(intent.target.split())
        if target.casefold() in _SAVED_MESSAGES_TARGETS:
            return self._open_saved_messages(request, identity)
        if not 1 <= len(target) <= 64 or any(
            not (char.isalnum() or char in " -_.'@") for char in target
        ):
            return ActionResult(
                request.key, ActionOutcome.FAILED, error_code="unsupported_chat"
            )
        return self._open_searched_chat(request, identity, target)

    def _run_helper(
        self, identity: tuple[str, int], *args: str
    ) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                [
                    self._system_python,
                    str(self._helper_path),
                    identity[0],
                    str(identity[1]),
                    *args,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=65,
            )
        except OSError, subprocess.TimeoutExpired:
            return None

    def _open_saved_messages(
        self, request: ActionRequest, identity: tuple[str, int]
    ) -> ActionResult:
        completed = self._run_helper(identity)
        if completed is None:
            return ActionResult(
                request.key, ActionOutcome.UNKNOWN, error_code="chat_input_unknown"
            )
        if completed.returncode == 2:
            return ActionResult(
                request.key, ActionOutcome.FAILED, error_code="telegram_focus_changed"
            )
        if completed.returncode != 0 or "SHORTCUT_DISPATCHED" not in completed.stdout:
            return ActionResult(
                request.key, ActionOutcome.UNKNOWN, error_code="chat_input_unknown"
            )
        if not self._verifier.verify(*identity, "Saved Messages"):
            return ActionResult(
                request.key, ActionOutcome.UNKNOWN, error_code="chat_unverified"
            )
        return ActionResult(
            request.key,
            ActionOutcome.CONFIRMED,
            observed_active_app="telegram",
        )

    def _open_searched_chat(
        self, request: ActionRequest, identity: tuple[str, int], target: str
    ) -> ActionResult:
        searched = self._run_helper(identity, "search", target)
        if (
            searched is None
            or searched.returncode != 0
            or "SEARCH_TYPED" not in searched.stdout
        ):
            return ActionResult(
                request.key, ActionOutcome.UNKNOWN, error_code="chat_input_unknown"
            )
        match = self._settled_search_result(identity, target)
        if match is None:
            return ActionResult(
                request.key, ActionOutcome.FAILED, error_code="chat_search_uncertain"
            )
        clicked = self._run_helper(
            identity,
            "click",
            *(
                str(value)
                for value in (
                    match.left,
                    match.top,
                    match.width,
                    match.height,
                    match.image_width,
                    match.image_height,
                )
            ),
        )
        if (
            clicked is None
            or clicked.returncode != 0
            or "CHAT_RESULT_CLICKED" not in clicked.stdout
        ):
            return ActionResult(
                request.key, ActionOutcome.UNKNOWN, error_code="chat_input_unknown"
            )
        if not self._verifier.verify(*identity, target):
            return ActionResult(
                request.key, ActionOutcome.UNKNOWN, error_code="chat_unverified"
            )
        return ActionResult(
            request.key, ActionOutcome.CONFIRMED, observed_active_app="telegram"
        )

    def _settled_search_result(
        self, identity: tuple[str, int], target: str
    ) -> ChatSearchMatch | None:
        """Wait briefly for Telegram's results; click only after two matching reads."""
        deadline = monotonic() + _SEARCH_SETTLE_SECONDS
        previous: ChatSearchMatch | None = None
        while monotonic() < deadline:
            current = self._verifier.find_search_result(*identity, target)
            if current is not None and previous is not None:
                if _same_search_box(previous, current):
                    return current
            previous = current
            remaining = deadline - monotonic()
            if remaining > 0:
                sleep(min(_SEARCH_POLL_SECONDS, remaining))
        return None
