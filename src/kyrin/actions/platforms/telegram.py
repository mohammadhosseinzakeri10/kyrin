"""Permission-aware Telegram chat navigation with fresh visual verification."""

import subprocess
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from threading import Event, Lock
from time import monotonic, sleep
from typing import Protocol

from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.platforms.desktop_scroll import SCROLL_HELPER
from kyrin.actions.telegram_selection import TelegramChatSelection
from kyrin.actions.telegram_verification import ChatSearchChoices, ChatSearchMatch
from kyrin.commands.models import CommandIntent, CommandKind
from kyrin.commands.telegram_settings import SETTING_SECTIONS
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
        for left, right in zip(first.global_results, second.global_results, strict=True)
    )


def _keep_global_scope(
    shown: ChatSearchChoices, fresh: ChatSearchChoices
) -> ChatSearchChoices:
    """Rows below a previously verified global heading stay global."""
    if (
        not shown.local_results
        and shown.global_section_verified
        and fresh.local_results
        and not fresh.global_section_verified
    ):
        return replace(
            fresh,
            own_chat=None,
            other_local_results=(),
            global_results=(*fresh.local_results, *fresh.global_results),
            global_section_verified=True,
        )
    return fresh


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

    def find_left_label(
        self, app_id: str, pid: int, label: str, *, menu: bool = False
    ) -> ChatSearchMatch | None: ...

    def find_settings_item(
        self, app_id: str, pid: int, label: str
    ) -> ChatSearchMatch | None: ...

    def settings_page_header(self, app_id: str, pid: int) -> str | None: ...

    def has_view_title(self, app_id: str, pid: int, title: str) -> bool: ...

    def has_search_query(self, app_id: str, pid: int, query: str) -> bool: ...


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
        if intent.kind not in {
            CommandKind.OPEN_CHAT,
            CommandKind.TELEGRAM_VIEW,
            CommandKind.TELEGRAM_SETTINGS,
            CommandKind.TELEGRAM_SEARCH_FOCUS,
            CommandKind.TELEGRAM_SEARCH,
        }:
            return self._delegate.execute(request)
        if intent.kind is CommandKind.OPEN_CHAT and intent.app != "telegram":
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
        if intent.kind is CommandKind.TELEGRAM_VIEW:
            return self._open_telegram_view(request, identity)
        if intent.kind is CommandKind.TELEGRAM_SETTINGS:
            return self._open_telegram_setting(request, identity)
        if intent.kind in {
            CommandKind.TELEGRAM_SEARCH_FOCUS,
            CommandKind.TELEGRAM_SEARCH,
        }:
            return self._telegram_search(request, identity)
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

    def _telegram_search(
        self, request: ActionRequest, identity: tuple[str, int]
    ) -> ActionResult:
        if request.intent.kind is CommandKind.TELEGRAM_SEARCH_FOCUS:
            completed = self._run_helper(identity, "focus-search")
            marker = "SEARCH_FOCUSED"
        else:
            completed = self._run_helper(identity, "search", request.intent.target)
            marker = "SEARCH_TYPED"
        if (
            completed is None
            or completed.returncode != 0
            or marker not in completed.stdout
        ):
            return self._telegram_input_result(request, completed)
        if request.intent.kind is CommandKind.TELEGRAM_SEARCH and (
            self._verifier.has_search_query(*identity, request.intent.target)
        ):
            return ActionResult(
                request.key, ActionOutcome.CONFIRMED, observed_active_app="telegram"
            )
        return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

    def _open_telegram_setting(
        self, request: ActionRequest, identity: tuple[str, int]
    ) -> ActionResult:
        destination = request.intent.target
        if destination in {"back", "cancel"}:
            completed = self._run_helper(identity, "escape")
            if (
                completed is None
                or completed.returncode != 0
                or "ESCAPE_DISPATCHED" not in completed.stdout
            ):
                return self._telegram_input_result(request, completed)
            return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

        contextual = destination.startswith("visible:")
        label = (
            destination.split(":", 1)[1]
            if destination.startswith(("label:", "visible:"))
            else SETTING_SECTIONS[destination]
        )
        if label.casefold() == "default interface scale":
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="telegram_setting_requires_value",
            )
        if contextual and not self._verifier.has_view_title(*identity, "Settings"):
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="telegram_settings_not_open",
            )
        match = self._stable_settings_item(identity, label)
        if match is None and not contextual:
            header = self._verifier.settings_page_header(*identity)
            for _ in range(3):
                if header is None or header == "settings":
                    break
                returned = self._run_helper(identity, "escape")
                if (
                    returned is None
                    or returned.returncode != 0
                    or "ESCAPE_DISPATCHED" not in returned.stdout
                ):
                    return self._telegram_input_result(request, returned)
                header = self._verifier.settings_page_header(*identity)
                if header is None:
                    return ActionResult(
                        request.key,
                        ActionOutcome.FAILED,
                        error_code="telegram_settings_navigation_uncertain",
                    )
            if header is not None and header != "settings":
                return ActionResult(
                    request.key,
                    ActionOutcome.FAILED,
                    error_code="telegram_settings_navigation_uncertain",
                )
            if header == "settings":
                match = self._stable_settings_item(identity, label)
        if (
            match is None
            and not contextual
            and not self._verifier.has_view_title(*identity, "Settings")
        ):
            settings_request = replace(
                request,
                intent=CommandIntent(CommandKind.TELEGRAM_VIEW, "settings"),
            )
            opened = self._open_telegram_view(settings_request, identity)
            if opened.outcome not in {
                ActionOutcome.CONFIRMED,
                ActionOutcome.LAUNCH_ACCEPTED,
            }:
                return opened
            match = self._stable_settings_item(identity, label)
        # My Account is the first fixed row. Scrolling cannot reveal it when
        # OCR misses the already visible row, and would only add delay.
        scroll_attempts = 0 if label.casefold() == "my account" else 3
        for _ in range(scroll_attempts):
            if match is not None:
                break
            if not self._scroll_settings(identity):
                break
            match = self._stable_settings_item(identity, label)
        if match is None:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="telegram_setting_not_found",
            )
        clicked = self._run_helper(
            identity,
            "settings-click",
            *(str(value) for value in (
                match.left,
                match.top,
                match.width,
                match.height,
                match.image_width,
                match.image_height,
            )),
        )
        if (
            clicked is None
            or clicked.returncode != 0
            or "SETTING_CLICKED" not in clicked.stdout
        ):
            return self._telegram_input_result(request, clicked)
        if self._verifier.has_view_title(*identity, label):
            return ActionResult(
                request.key, ActionOutcome.CONFIRMED, observed_active_app="telegram"
            )
        return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)

    def _stable_settings_item(
        self, identity: tuple[str, int], label: str
    ) -> ChatSearchMatch | None:
        previous: ChatSearchMatch | None = None
        for _ in range(3):
            current = self._verifier.find_settings_item(*identity, label)
            if current is not None and previous is not None:
                if _same_search_box(previous, current):
                    return current
            previous = current
            sleep(0.15)
        return None

    def _scroll_settings(self, identity: tuple[str, int]) -> bool:
        try:
            result = subprocess.run(
                [
                    self._system_python,
                    str(SCROLL_HELPER),
                    identity[0],
                    str(identity[1]),
                    "down",
                    "2",
                    "right",
                    "telegram-control",
                ],
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
        except OSError, subprocess.TimeoutExpired:
            return False
        dispatched = result.returncode == 0 and "SCROLL_DISPATCHED" in result.stdout
        if dispatched:
            sleep(0.25)
        return dispatched

    def _open_telegram_view(
        self, request: ActionRequest, identity: tuple[str, int]
    ) -> ActionResult:
        destination = request.intent.target
        headings = {
            "archive": "Archived Chats",
            "contacts": "Contacts",
            "settings": "Settings",
            "profile": "My Profile",
            "calls": "Calls",
            "new_group": "New Group",
            "new_channel": "New Channel",
        }
        if destination in {"archive", "contacts"}:
            completed = self._run_helper(identity, "view", destination)
            marker = "VIEW_SHORTCUT_DISPATCHED"
        else:
            menu_label = headings[destination]
            match = self._stable_menu_item(identity, menu_label, fast_missing=True)
            # In Archive the same top-left button first returns to All Chats.
            # At most two clicks can reach the main menu from there.
            for _ in range(2):
                if match is not None:
                    break
                opened = self._run_helper(identity, "menu")
                if (
                    opened is None
                    or opened.returncode != 0
                    or "MENU_CLICKED" not in opened.stdout
                ):
                    return self._telegram_input_result(request, opened)
                match = self._stable_menu_item(identity, menu_label)
            if match is None:
                return ActionResult(
                    request.key,
                    ActionOutcome.FAILED,
                    error_code="telegram_menu_uncertain",
                )
            completed = self._run_helper(
                identity,
                "menu-click",
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
            marker = "CHAT_RESULT_CLICKED"
        if (
            completed is None
            or completed.returncode != 0
            or marker not in completed.stdout
        ):
            return self._telegram_input_result(request, completed)
        destination_visible = (
            self._verifier.has_view_title(*identity, "Settings")
            if destination == "settings"
            else self._verifier.find_left_label(*identity, headings[destination])
            is not None
        )
        if not destination_visible:
            return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)
        return ActionResult(
            request.key,
            ActionOutcome.CONFIRMED,
            observed_active_app="telegram",
        )

    def _stable_menu_item(
        self,
        identity: tuple[str, int],
        label: str,
        *,
        fast_missing: bool = False,
    ) -> ChatSearchMatch | None:
        previous: ChatSearchMatch | None = None
        for _ in range(3):
            current = self._verifier.find_left_label(*identity, label, menu=True)
            if current is None and fast_missing:
                return None
            if current is not None and previous is not None:
                if _same_search_box(previous, current):
                    return current
            previous = current
            sleep(0.1)
        return None

    @staticmethod
    def _telegram_input_result(
        request: ActionRequest, completed: subprocess.CompletedProcess[str] | None
    ) -> ActionResult:
        if completed is not None and "CONTROL_SETUP_REQUIRED" in completed.stdout:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="telegram_control_setup_required",
            )
        if completed is not None and completed.returncode == 2:
            return ActionResult(
                request.key,
                ActionOutcome.FAILED,
                error_code="telegram_focus_changed",
            )
        return ActionResult(
            request.key,
            ActionOutcome.UNKNOWN,
            error_code="telegram_input_unknown",
        )

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
                request.key,
                ActionOutcome.FAILED,
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
                request.key,
                ActionOutcome.FAILED,
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
            if choices is not None:
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
                if self._selection is not None
                else "chat_search_uncertain",
            )
        return self._click_result(request, identity, target, match)

    def next_search_page(
        self,
        identity: tuple[str, int],
        target: str,
        shown: ChatSearchChoices,
        cancellation: Event,
    ) -> ChatSearchChoices | None:
        """Advance the visible result list only while the same search is active."""
        with self._lock:
            if cancellation.is_set() or self._identity_reader() != identity:
                return None
            fresh = self._settled_search_choices(identity, target)
            if fresh is not None:
                fresh = _keep_global_scope(shown, fresh)
            if fresh is None or not _same_selectable_choices(shown, fresh):
                return None
            if not self._scroll_search_results(identity):
                return None
            next_choices = self._settled_search_choices(identity, target)
            if next_choices is not None:
                next_choices = _keep_global_scope(shown, next_choices)
            if (
                next_choices is None
                or not next_choices.selectable_results
                or next_choices.view_signature == fresh.view_signature
            ):
                return None
            if shown.local_results:
                # On a later page, the OCR top-row fallback can mistake a
                # global row for a personal chat. Require the boundary in
                # this frame before offering any personal row for selection.
                if (
                    not next_choices.local_results
                    or not next_choices.global_section_verified
                ):
                    return None
            else:
                # Once the verified global heading has been passed, every
                # lower row remains global even when the heading scrolls away.
                if next_choices.local_results or not next_choices.global_results:
                    return None
            return next_choices

    def _scroll_search_results(self, identity: tuple[str, int]) -> bool:
        try:
            result = subprocess.run(
                [
                    self._system_python,
                    str(SCROLL_HELPER),
                    identity[0],
                    str(identity[1]),
                    "down",
                    "3",
                    "left",
                    "telegram-control",
                ],
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
        except OSError, subprocess.TimeoutExpired:
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
        *,
        unique_identity: bool = True,
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
        if not unique_identity:
            # A matching header cannot distinguish same-title chats. The
            # selected row was clicked, but its identity is not proven.
            return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)
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
                    request.key,
                    ActionOutcome.FAILED,
                    error_code="chat_selection_cancelled",
                )
            if self._identity_reader() != identity:
                return ActionResult(
                    request.key,
                    ActionOutcome.FAILED,
                    error_code="telegram_focus_changed",
                )
            fresh = self._settled_search_choices(identity, target)
            if fresh is not None:
                fresh = _keep_global_scope(shown, fresh)
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
                    request.key,
                    ActionOutcome.FAILED,
                    error_code="chat_selection_cancelled",
                )
            return self._click_result(
                request, identity, target, match, unique_identity=False
            )

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
