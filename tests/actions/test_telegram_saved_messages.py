"""The Telegram shortcut stays behind permission, focus, and OCR checks."""

import subprocess
from itertools import cycle
from pathlib import Path

import pytest

from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.platforms import telegram
from kyrin.actions.telegram_verification import ChatSearchMatch
from kyrin.commands.models import CommandIntent, CommandKind

KEY = ActionKey(0, 1, 0)
DESKTOP_ID = "org.telegram.desktop.desktop"


class Delegate:
    def __init__(self) -> None:
        self.calls: list[ActionRequest] = []

    def execute(self, request: ActionRequest) -> ActionResult:
        self.calls.append(request)
        return ActionResult(request.key, ActionOutcome.LAUNCH_ACCEPTED)


class Verifier:
    def __init__(
        self,
        *,
        ready: bool = True,
        verified: bool = True,
        match: ChatSearchMatch | None = None,
    ) -> None:
        self.available = ready
        self.verified = verified
        self.match = match
        self.calls: list[tuple[str, int, str]] = []

    def ready(self) -> bool:
        return self.available

    def verify(self, app_id: str, pid: int, target: str = "Saved Messages") -> bool:
        self.calls.append((app_id, pid, target))
        return self.verified

    def find_search_result(
        self, app_id: str, pid: int, target: str
    ) -> ChatSearchMatch | None:
        return self.match


def _request(kind: CommandKind, target: str, app: str | None = None) -> ActionRequest:
    return ActionRequest(KEY, CommandIntent(kind, target, app), "en")


def _executor(
    delegate: Delegate, verifier: Verifier, identity: tuple[str, int] | None
) -> telegram.TelegramSavedMessagesExecutor:
    return telegram.TelegramSavedMessagesExecutor(
        delegate,
        telegram_desktop_id=DESKTOP_ID,
        identity_reader=lambda: identity,
        verifier=verifier,
        helper_path=Path("/tmp/telegram-helper.py"),
    )


def test_other_actions_delegate_without_keyboard_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "kyrin.actions.platforms.telegram.subprocess.run",
        lambda *args, **kwargs: pytest.fail(),
    )
    delegate = Delegate()
    request = _request(CommandKind.OPEN_APP, "telegram")
    result = _executor(delegate, Verifier(), None).execute(request)
    assert result.outcome is ActionOutcome.LAUNCH_ACCEPTED
    assert delegate.calls == [request]


@pytest.mark.parametrize(
    ("target", "identity", "ready", "error"),
    [
        ("Ali", (DESKTOP_ID, 12), False, "screen_access_required"),
        ("Ali;evil", (DESKTOP_ID, 12), True, "unsupported_chat"),
        ("Saved Messages", (DESKTOP_ID, 12), False, "screen_access_required"),
        ("Saved Messages", None, True, "telegram_not_active"),
        ("Saved Messages", ("browser.desktop", 12), True, "telegram_not_active"),
    ],
)
def test_preconditions_block_keyboard_input(
    target: str,
    identity: tuple[str, int] | None,
    ready: bool,
    error: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "kyrin.actions.platforms.telegram.subprocess.run",
        lambda *args, **kwargs: pytest.fail(),
    )
    delegate = Delegate()
    result = _executor(delegate, Verifier(ready=ready), identity).execute(
        _request(CommandKind.OPEN_CHAT, target, "telegram")
    )
    assert result.outcome is ActionOutcome.FAILED
    assert result.error_code == error
    assert delegate.calls == []


@pytest.mark.parametrize(
    ("returncode", "stdout", "verified", "outcome", "error"),
    [
        (2, "FOCUS_CHANGED", True, ActionOutcome.FAILED, "telegram_focus_changed"),
        (1, "", True, ActionOutcome.UNKNOWN, "chat_input_unknown"),
        (0, "", True, ActionOutcome.UNKNOWN, "chat_input_unknown"),
        (0, "SHORTCUT_DISPATCHED", False, ActionOutcome.UNKNOWN, "chat_unverified"),
        (0, "SHORTCUT_DISPATCHED", True, ActionOutcome.CONFIRMED, None),
    ],
)
def test_shortcut_outcome_requires_fresh_verified_chat_header(
    returncode: int,
    stdout: str,
    verified: bool,
    outcome: ActionOutcome,
    error: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, returncode, stdout, "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.subprocess.run", run)
    verifier = Verifier(verified=verified)
    result = _executor(Delegate(), verifier, (DESKTOP_ID, 12)).execute(
        _request(CommandKind.OPEN_CHAT, "Saved Messages", "telegram")
    )
    assert calls == [["/usr/bin/python3", "/tmp/telegram-helper.py", DESKTOP_ID, "12"]]
    assert result.outcome is outcome
    assert result.error_code == error
    assert verifier.calls == (
        [(DESKTOP_ID, 12, "Saved Messages")] if returncode == 0 and stdout else []
    )


@pytest.mark.parametrize(
    ("verified", "outcome", "error"),
    [
        (False, ActionOutcome.UNKNOWN, "chat_unverified"),
        (True, ActionOutcome.CONFIRMED, None),
    ],
)
def test_observed_stt_spelling_still_requires_verified_saved_messages_header(
    verified: bool,
    outcome: ActionOutcome,
    error: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, "SHORTCUT_DISPATCHED", "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.subprocess.run", run)
    verifier = Verifier(verified=verified)
    result = _executor(Delegate(), verifier, (DESKTOP_ID, 12)).execute(
        _request(CommandKind.OPEN_CHAT, "Saved Massages", "telegram")
    )

    assert result.outcome is outcome
    assert result.error_code == error
    assert verifier.calls == [(DESKTOP_ID, 12, "Saved Messages")]


def test_other_chat_requires_unique_result_before_pointer_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    elapsed = [0.0]

    monkeypatch.setattr(
        "kyrin.actions.platforms.telegram.monotonic", lambda: elapsed[0]
    )
    monkeypatch.setattr(
        "kyrin.actions.platforms.telegram.sleep",
        lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
    )

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "SEARCH_TYPED", "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.subprocess.run", run)
    result = _executor(Delegate(), Verifier(), (DESKTOP_ID, 12)).execute(
        _request(CommandKind.OPEN_CHAT, "Alice", "telegram")
    )
    assert result.outcome is ActionOutcome.FAILED
    assert result.error_code == "chat_search_uncertain"
    assert calls == [
        [
            "/usr/bin/python3",
            "/tmp/telegram-helper.py",
            DESKTOP_ID,
            "12",
            "search",
            "Alice",
        ]
    ]
    assert elapsed[0] == pytest.approx(telegram._SEARCH_SETTLE_SECONDS)


def test_other_chat_waits_for_two_stable_search_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    elapsed = [0.0]
    matches = iter(
        [
            None,
            ChatSearchMatch(70, 220, 90, 24, 1600, 900),
            ChatSearchMatch(72, 219, 91, 24, 1600, 900),
        ]
    )

    class DelayedVerifier(Verifier):
        def find_search_result(
            self, app_id: str, pid: int, target: str
        ) -> ChatSearchMatch | None:
            self.calls.append((app_id, pid, target))
            return next(matches)

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(
            args, 0, "SEARCH_TYPED" if len(calls) == 1 else "CHAT_RESULT_CLICKED", ""
        )

    monkeypatch.setattr(
        "kyrin.actions.platforms.telegram.monotonic", lambda: elapsed[0]
    )
    monkeypatch.setattr(
        "kyrin.actions.platforms.telegram.sleep",
        lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
    )
    monkeypatch.setattr("kyrin.actions.platforms.telegram.subprocess.run", run)
    verifier = DelayedVerifier()
    result = _executor(Delegate(), verifier, (DESKTOP_ID, 12)).execute(
        _request(CommandKind.OPEN_CHAT, "Alice", "telegram")
    )
    assert result.outcome is ActionOutcome.CONFIRMED
    assert len(calls) == 2
    assert calls[1][-7:] == ["click", "72", "219", "91", "24", "1600", "900"]
    assert verifier.calls == [(DESKTOP_ID, 12, "Alice")] * 4


def test_other_chat_never_clicks_when_search_result_moves_between_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elapsed = [0.0]
    results = cycle(
        (
            ChatSearchMatch(70, 220, 90, 24, 1600, 900),
            ChatSearchMatch(70, 280, 90, 24, 1600, 900),
        )
    )
    calls: list[list[str]] = []

    class MovingVerifier(Verifier):
        def find_search_result(
            self, app_id: str, pid: int, target: str
        ) -> ChatSearchMatch | None:
            return next(results)

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "SEARCH_TYPED", "")

    monkeypatch.setattr(
        "kyrin.actions.platforms.telegram.monotonic", lambda: elapsed[0]
    )
    monkeypatch.setattr(
        "kyrin.actions.platforms.telegram.sleep",
        lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
    )
    monkeypatch.setattr("kyrin.actions.platforms.telegram.subprocess.run", run)
    result = _executor(Delegate(), MovingVerifier(), (DESKTOP_ID, 12)).execute(
        _request(CommandKind.OPEN_CHAT, "Alice", "telegram")
    )
    assert result.outcome is ActionOutcome.FAILED
    assert result.error_code == "chat_search_uncertain"
    assert len(calls) == 1


def test_other_chat_clicks_only_the_verified_box_and_checks_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    outputs = iter(["SEARCH_TYPED", "CHAT_RESULT_CLICKED"])

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, next(outputs), "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.subprocess.run", run)
    verifier = Verifier(match=ChatSearchMatch(70, 220, 90, 24, 1600, 900))
    result = _executor(Delegate(), verifier, (DESKTOP_ID, 12)).execute(
        _request(CommandKind.OPEN_CHAT, "Alice", "telegram")
    )
    assert result.outcome is ActionOutcome.CONFIRMED
    assert calls[1] == [
        "/usr/bin/python3",
        "/tmp/telegram-helper.py",
        DESKTOP_ID,
        "12",
        "click",
        "70",
        "220",
        "90",
        "24",
        "1600",
        "900",
    ]
    assert verifier.calls == [(DESKTOP_ID, 12, "Alice")]


def test_keyboard_timeout_never_claims_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired("helper", 65)

    monkeypatch.setattr("kyrin.actions.platforms.telegram.subprocess.run", timeout)
    result = _executor(Delegate(), Verifier(), (DESKTOP_ID, 12)).execute(
        _request(CommandKind.OPEN_CHAT, "Saved Messages", "telegram")
    )
    assert result.outcome is ActionOutcome.UNKNOWN
