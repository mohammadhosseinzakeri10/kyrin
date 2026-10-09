"""Bounded Telegram Saved Messages action over a permission-aware keyboard helper."""

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from kyrin.actions.executor import ActionExecutor
from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.commands.models import CommandKind

_HELPER = Path(__file__).with_name("telegram_portal_helper.py")
WindowIdentityReader = Callable[[], tuple[str, int] | None]


class ChatVerifier(Protocol):
    def ready(self) -> bool: ...

    def verify(self, app_id: str, pid: int) -> bool: ...


class TelegramSavedMessagesExecutor:
    """Handle one chat target; leave ordinary app launches to the delegate."""

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
        if (
            intent.app != "telegram"
            or " ".join(intent.target.casefold().split()) != "saved messages"
        ):
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
        try:
            completed = subprocess.run(
                [
                    self._system_python,
                    str(self._helper_path),
                    identity[0],
                    str(identity[1]),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=65,
            )
        except OSError, subprocess.TimeoutExpired:
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
        if not self._verifier.verify(*identity):
            return ActionResult(
                request.key, ActionOutcome.UNKNOWN, error_code="chat_unverified"
            )
        return ActionResult(
            request.key,
            ActionOutcome.CONFIRMED,
            observed_active_app="telegram",
        )
