"""Permission-aware Telegram chat navigation with fresh visual verification."""

import subprocess
from collections.abc import Callable
from pathlib import Path
from threading import Event, Lock
from time import monotonic, sleep
from typing import Protocol

from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.platforms.desktop_scroll import SCROLL_HELPER
from kyrin.actions.telegram_selection import TelegramChatSelection
from kyrin.actions.telegram_verification import ChatSearchChoices, ChatSearchMatch
from kyrin.commands.models import CommandKind
from kyrin.text_normalization import fold_case

TELEGRAM_PORTAL_HELPER = Path(__file__).with_name("telegram_portal_helper.py")
_SAVED_MESSAGES_TARGETS = frozenset(
    {"saved messages", "saved massages", "save the messages"}
)
_SEARCH_SETTLE_SECONDS = 3.0
_SEARCH_POLL_SECONDS = 0.2
_MAX_SEARCH_SCROLLS = 4
_MAX_SEARCH_SCAN_SECONDS = 18.0
WindowIdentityReader = Callable[[], tuple[str, int] | None]


def _same_search_box(first: ChatSearchMatch, second: ChatSearchMatch) -> bool:
    """Allow minor OCR box jitter while keeping one result and image size fixed."""
    return (first.image_width, first.image_height) == (
        second.image_width,
        second.image_height,
    ) and all(
        abs(left - right) <= 5
        for left, right in zip(
            (first.left, first.top, first.width, first.height),
            (second.left, second.top, second.width, second.height),
            strict=True,
        )
    )


def _same_local_choices(first: ChatSearchChoices, second: ChatSearchChoices) -> bool:
    """Only local rows can be selected; global results may refresh independently."""
    if len(first.local_results) != len(second.local_results):
        return False
    return not any(
        not _same_search_box(left, right)
        for left, right in zip(first.local_results, second.local_results, strict=True)
    )


def _same_selectable_choices(
    first: ChatSearchChoices, second: ChatSearchChoices
) -> bool:
    """Compare only the rows that the pending question can select."""
    if first.local_results:
        return _same_local_choices(first, second)
    if (
        second.local_results
        or not first.global_section_verified
        or not second.global_section_verified
        or len(first.global_results) != len(second.global_results)
    ):
        return False
    return all(
        _same_search_box(left, right)
        for left, right in zip(
            first.global_results, second.global_results, strict=True
        )
    )


class ChatVerifier(Protocol):
    def ready(self) -> bool: ...

    def find_search_result(
        self, app_id: str, pid: int, target: str
    ) -> ChatSearchMatch | None: ...

    def find_search_choices(
        self, app_id: str, pid: int, target: str
    ) -> ChatSearchChoices | None: ...

    def choice_status(self) -> str: ...

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
        selection: TelegramChatSelection | None = None,
        remember_pointer: bool = False,
        system_python: str = "/usr/bin/python3",
        helper_path: Path = TELEGRAM_PORTAL_HELPER,
    ) -> None:
        self._delegate = delegate
        self._telegram_desktop_id = telegram_desktop_id
        self._identity_reader = identity_reader
        self._verifier = verifier
        self._selection = selection
        self._remember_pointer = remember_pointer
        self._lock = Lock()
        self._choice_status = "not_requested"
        self._system_python = system_python
        self._helper_path = helper_path

    def execute(self, request: ActionRequest) -> ActionResult:
        with self._lock:
            return self._execute(request)

    def _execute(self, request: ActionRequest) -> ActionResult:
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
        if not self._remember_pointer:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="telegram_control_setup_required",
            )
        target = " ".join(intent.target.split())
        if fold_case(target) in _SAVED_MESSAGES_TARGETS:
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
        if "CONTROL_SETUP_REQUIRED" in completed.stdout:
            return ActionResult(
                request.key, ActionOutcome.FAILED,
                error_code="telegram_control_setup_required",
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
        if searched is not None and "CONTROL_SETUP_REQUIRED" in searched.stdout:
            return ActionResult(
                request.key, ActionOutcome.FAILED,
                error_code="telegram_control_setup_required",
            )
        if (
            searched is None
            or searched.returncode != 0
            or "SEARCH_TYPED" not in searched.stdout
        ):
            return ActionResult(
                request.key, ActionOutcome.UNKNOWN, error_code="chat_input_unknown"
            )
        if self._selection is not None:
            choices = self._settled_search_choices(identity, target)
            scan_deadline = monotonic() + _MAX_SEARCH_SCAN_SECONDS
            for _ in range(_MAX_SEARCH_SCROLLS):
                if choices is not None and choices.selectable_results:
                    break
                if monotonic() >= scan_deadline:
                    break
                if not self._scroll_search_results(identity):
                    break
                choices = self._settled_search_choices(identity, target)
            if choices is not None and (
                len(choices.local_results) > 1
                or (
                    not choices.local_results
                    and choices.global_section_verified
                    and choices.global_results
                )
            ):
                if self._selection.begin(request, identity, target, choices):
                    return ActionResult(
                        request.key,
                        ActionOutcome.UNKNOWN,
                        error_code="chat_selection_pending",
                    )
        match = self._settled_search_result(identity, target)
        if match is None:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code=f"chat_search_uncertain:{self._choice_status}"
                if self._selection is not None else "chat_search_uncertain",
            )
        return self._click_result(request, identity, target, match)

    def next_search_page(
        self, identity: tuple[str, int], target: str,
        shown: ChatSearchChoices, cancellation: Event,
    ) -> ChatSearchChoices | None:
        """Advance the visible result list only while the same search is active."""
        with self._lock:
            if cancellation.is_set() or self._identity_reader() != identity:
                return None
            fresh = self._settled_search_choices(identity, target)
            if fresh is None or not _same_selectable_choices(shown, fresh):
                return None
            if not self._scroll_search_results(identity):
                return None
            next_choices = self._settled_search_choices(identity, target)
            if (
                next_choices is None
                or not next_choices.selectable_results
                or next_choices.view_signature == fresh.view_signature
            ):
                return None
            return next_choices

    def _scroll_search_results(self, identity: tuple[str, int]) -> bool:
        try:
            result = subprocess.run(
                [
                    self._system_python, str(SCROLL_HELPER),
                    identity[0], str(identity[1]), "down", "3", "left",
                    "telegram-control",
                ],
                capture_output=True, text=True, timeout=45, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        dispatched = result.returncode == 0 and "SCROLL_DISPATCHED" in result.stdout
        if dispatched:
            sleep(0.25)
        return dispatched

    def _click_result(
        self,
        request: ActionRequest,
        identity: tuple[str, int],
        target: str,
        match: ChatSearchMatch,
    ) -> ActionResult:
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
        if clicked is not None and "CONTROL_SETUP_REQUIRED" in clicked.stdout:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="telegram_control_setup_required",
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

    def complete_selection(
        self,
        request: ActionRequest,
        identity: tuple[str, int],
        target: str,
        shown: ChatSearchChoices,
        number: int | None,
        cancellation: Event,
    ) -> ActionResult:
        """Re-read the same rows and focused window before a chosen click."""
        with self._lock:
            if cancellation.is_set():
                return ActionResult(
                    request.key, ActionOutcome.FAILED,
                    error_code="chat_selection_cancelled",
                )
            if self._identity_reader() != identity:
                return ActionResult(
                    request.key,
                    ActionOutcome.FAILED,
                    error_code="telegram_focus_changed",
                )
            fresh = self._settled_search_choices(identity, target)
            if fresh is None:
                return ActionResult(
                    request.key,
                    ActionOutcome.FAILED,
                    error_code=f"chat_search_uncertain:selection_read_{self._choice_status}",
                )
            if not _same_selectable_choices(shown, fresh):
                section = "local" if shown.local_results else "global"
                return ActionResult(
                    request.key,
                    ActionOutcome.FAILED,
                    error_code=(
                        f"chat_search_uncertain:selection_{section}_rows_changed_"
                        f"{len(shown.selectable_results)}_to_"
                        f"{len(fresh.selectable_results)}"
                    ),
                )
            results = fresh.selectable_results
            match = (
                results[number - 1]
                if number is not None and 1 <= number <= len(results)
                else None
            )
            if match is None:
                return ActionResult(
                    request.key,
                    ActionOutcome.FAILED,
                    error_code="chat_search_uncertain",
                )
            if cancellation.is_set():
                return ActionResult(
                    request.key, ActionOutcome.FAILED,
                    error_code="chat_selection_cancelled",
                )
            return self._click_result(request, identity, target, match)

    def _settled_search_choices(
        self, identity: tuple[str, int], target: str
    ) -> ChatSearchChoices | None:
        deadline = monotonic() + _SEARCH_SETTLE_SECONDS
        previous: ChatSearchChoices | None = None
        saw_choices = False
        while monotonic() < deadline:
            current = self._verifier.find_search_choices(*identity, target)
            self._choice_status = self._verifier.choice_status()
            has_rows = current is not None and (
                current.own_chat is not None or bool(current.global_results)
            )
            saw_choices = saw_choices or has_rows
            if current is not None and has_rows and previous is not None:
                if _same_selectable_choices(previous, current):
                    return current
            previous = current if has_rows else None
            remaining = deadline - monotonic()
            if remaining > 0:
                sleep(min(_SEARCH_POLL_SECONDS, remaining))
        if saw_choices:
            self._choice_status = f"unstable_{self._choice_status}"
        return None

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
