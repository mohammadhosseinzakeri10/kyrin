"""The Telegram shortcut stays behind permission, focus, and OCR checks."""

import subprocess
from itertools import cycle
from pathlib import Path
from threading import Event

import pytest

from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.platforms import telegram
from kyrin.actions.telegram_selection import TelegramChatSelection
from kyrin.actions.telegram_verification import ChatSearchChoices, ChatSearchMatch
from kyrin.actions.visible_control import VisibleControlTarget, VisibleTextOption
from kyrin.commands.models import CommandIntent, CommandKind, ResponseRequest

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
        choices: ChatSearchChoices | None = None,
        settings_header: str | None = None,
    ) -> None:
        self.available = ready
        self.verified = verified
        self.match = match
        self.choices = choices
        self.settings_header = settings_header if settings_header is not None else (
            "settings" if verified else None
        )
        self.calls: list[tuple[str, int, str]] = []

    def ready(self) -> bool:
        return self.available

    def list_visible_text(self, app_id: str, pid: int) -> tuple[VisibleTextOption, ...]:
        raise AssertionError("chat navigation should not inventory generic controls")

    def find_visible_control(
        self, app_id: str, pid: int, label: str
    ) -> VisibleControlTarget | None:
        raise AssertionError("chat navigation should not locate generic controls")

    def verify(self, app_id: str, pid: int, target: str = "Saved Messages") -> bool:
        self.calls.append((app_id, pid, target))
        return self.verified

    def find_search_result(
        self, app_id: str, pid: int, target: str
    ) -> ChatSearchMatch | None:
        return self.match

    def find_search_choices(
        self, app_id: str, pid: int, target: str
    ) -> ChatSearchChoices | None:
        return self.choices

    def find_visible_chat_choices(
        self, app_id: str, pid: int, target: str
    ) -> ChatSearchChoices | None:
        return self.choices

    def choice_status(self) -> str:
        return "classified" if self.choices is not None else "unclassified"

    def find_left_label(
        self, app_id: str, pid: int, label: str, *, menu: bool = False
    ) -> ChatSearchMatch | None:
        self.calls.append((app_id, pid, label))
        return self.match

    def find_settings_item(
        self, app_id: str, pid: int, label: str
    ) -> ChatSearchMatch | None:
        self.calls.append((app_id, pid, label))
        return self.match

    def has_view_title(self, app_id: str, pid: int, title: str) -> bool:
        return self.verified

    def settings_page_header(self, app_id: str, pid: int) -> str | None:
        return self.settings_header

    def has_search_query(self, app_id: str, pid: int, query: str) -> bool:
        self.calls.append((app_id, pid, query))
        return self.verified


@pytest.mark.parametrize(
    ("destination", "mode"),
    [
        ("archive", "view"),
        ("contacts", "view"),
        ("settings", "menu"),
        ("new_group", "menu"),
        ("new_channel", "menu"),
    ],
)
def test_telegram_view_dispatch_and_verification(
    destination: str, mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    match = ChatSearchMatch(80, 100, 70, 20, 1000, 800)
    menu_visible = False

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal menu_visible
        calls.append(args)
        if args[4] == "menu":
            menu_visible = True
        elif args[4] == "menu-click":
            menu_visible = False
        marker = {
            "view": "VIEW_SHORTCUT_DISPATCHED",
            "menu": "MENU_CLICKED",
            "menu-click": "CHAT_RESULT_CLICKED",
        }[args[4]]
        return subprocess.CompletedProcess(args, 0, marker, "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    verifier = Verifier(match=match)
    verifier.find_left_label = (  # type: ignore[method-assign]
        lambda app_id, pid, label, *, menu=False: (
            match if not menu or menu_visible else None
        )
    )
    result = _executor(Delegate(), verifier, (DESKTOP_ID, 12)).execute(
        _request(CommandKind.TELEGRAM_VIEW, destination)
    )
    assert result.outcome is ActionOutcome.CONFIRMED
    assert calls[0][4] == mode
    assert len(calls) == (1 if mode == "view" else 2)


def test_telegram_menu_item_must_be_stable_before_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "MENU_CLICKED", "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    result = _executor(Delegate(), Verifier(), (DESKTOP_ID, 12)).execute(
        _request(CommandKind.TELEGRAM_VIEW, "settings")
    )
    assert result.outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert result.error_code is None
    assert len(calls) == 1  # A missing menu is not permission to click again.


def test_closed_menu_precheck_does_not_repeat_expensive_ocr() -> None:
    verifier = Verifier()
    executor = _executor(Delegate(), verifier, (DESKTOP_ID, 12))
    assert executor._stable_menu_item(  # noqa: SLF001
        (DESKTOP_ID, 12), "Settings", fast_missing=True
    ) is None
    assert verifier.calls == [(DESKTOP_ID, 12, "Settings")]


def test_telegram_setting_clicks_only_stable_ocr_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modes: list[str] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        modes.append(args[4])
        return subprocess.CompletedProcess(args, 0, "SETTING_CLICKED", "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    verifier = Verifier(match=ChatSearchMatch(540, 205, 205, 24, 1600, 900))
    result = _executor(Delegate(), verifier, (DESKTOP_ID, 12)).execute(
        _request(CommandKind.TELEGRAM_SETTINGS, "privacy")
    )
    assert result.outcome is ActionOutcome.CONFIRMED
    assert modes == ["settings-click"]


def test_named_visible_settings_row_uses_same_verified_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modes: list[str] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        modes.append(args[4])
        return subprocess.CompletedProcess(args, 0, "SETTING_CLICKED", "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    verifier = Verifier(match=ChatSearchMatch(790, 244, 76, 14, 1853, 1048))
    result = _executor(Delegate(), verifier, (DESKTOP_ID, 12)).execute(
        _request(CommandKind.TELEGRAM_SETTINGS, "label:my account")
    )
    assert result.outcome is ActionOutcome.CONFIRMED
    assert modes == ["settings-click"]


def test_known_settings_section_returns_from_advanced_before_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modes: list[str] = []
    match = ChatSearchMatch(790, 363, 95, 14, 1853, 1048)

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        mode = args[4]
        modes.append(mode)
        marker = "ESCAPE_DISPATCHED" if mode == "escape" else "SETTING_CLICKED"
        return subprocess.CompletedProcess(args, 0, marker, "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    verifier = Verifier(settings_header="advanced")
    verifier.settings_page_header = (  # type: ignore[method-assign]
        lambda app_id, pid: "settings" if "escape" in modes else "advanced"
    )
    verifier.find_settings_item = (  # type: ignore[method-assign]
        lambda app_id, pid, label: match if "escape" in modes else None
    )
    result = _executor(Delegate(), verifier, (DESKTOP_ID, 12)).execute(
        _request(CommandKind.TELEGRAM_SETTINGS, "chat_settings")
    )
    assert result.outcome is ActionOutcome.CONFIRMED
    assert modes == ["escape", "settings-click"]


def test_nested_settings_navigation_stops_if_back_is_not_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modes: list[str] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        modes.append(args[4])
        return subprocess.CompletedProcess(args, 0, "ESCAPE_DISPATCHED", "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    verifier = Verifier(settings_header="advanced")
    verifier.settings_page_header = (  # type: ignore[method-assign]
        lambda app_id, pid: None if modes else "advanced"
    )
    result = _executor(Delegate(), verifier, (DESKTOP_ID, 12)).execute(
        _request(CommandKind.TELEGRAM_SETTINGS, "chat_settings")
    )
    assert result.outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert result.error_code is None
    assert modes == ["escape"]


def test_short_settings_label_never_reopens_a_closed_settings_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modes: list[str] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        modes.append(args[4])
        return subprocess.CompletedProcess(args, 0, "MENU_CLICKED", "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    result = _executor(
        Delegate(), Verifier(verified=False), (DESKTOP_ID, 12)
    ).execute(_request(CommandKind.TELEGRAM_SETTINGS, "visible:display name"))
    assert result.error_code == "telegram_settings_not_open"
    assert modes == []


def test_missing_my_account_keeps_open_settings_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modes: list[str] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        modes.append(args[4])
        return subprocess.CompletedProcess(args, 0, "MENU_CLICKED", "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    result = _executor(Delegate(), Verifier(), (DESKTOP_ID, 12)).execute(
        _request(CommandKind.TELEGRAM_SETTINGS, "my_account")
    )
    assert result.error_code == "telegram_setting_not_found"
    assert modes == []


def test_settings_control_is_not_clicked_as_navigation() -> None:
    result = _executor(Delegate(), Verifier(), (DESKTOP_ID, 12)).execute(
        _request(CommandKind.TELEGRAM_SETTINGS, "default_scale")
    )
    assert result.error_code == "telegram_setting_requires_value"


def test_telegram_back_sends_only_escape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modes: list[str] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        modes.append(args[4])
        return subprocess.CompletedProcess(args, 0, "ESCAPE_DISPATCHED", "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    result = _executor(Delegate(), Verifier(), (DESKTOP_ID, 12)).execute(
        _request(CommandKind.TELEGRAM_SETTINGS, "back")
    )
    assert result.outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert modes == ["escape"]


@pytest.mark.parametrize(
    ("kind", "target", "marker", "outcome"),
    [
        (
            CommandKind.TELEGRAM_SEARCH_FOCUS,
            "telegram",
            "SEARCH_FOCUSED",
            ActionOutcome.DISPATCHED_UNVERIFIED,
        ),
        (
            CommandKind.TELEGRAM_SEARCH,
            "My Mother",
            "SEARCH_TYPED",
            ActionOutcome.CONFIRMED,
        ),
    ],
)
def test_telegram_search_never_clicks_a_result(
    kind: CommandKind,
    target: str,
    marker: str,
    outcome: ActionOutcome,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, marker, "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    result = _executor(Delegate(), Verifier(), (DESKTOP_ID, 12)).execute(
        _request(kind, target)
    )
    assert result.outcome is outcome
    assert len(calls) == 1
    assert calls[0][4] == (
        "focus-search" if kind is CommandKind.TELEGRAM_SEARCH_FOCUS else "search"
    )


def test_missing_setting_never_dispatches_a_setting_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modes: list[str] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        modes.append(args[4])
        return subprocess.CompletedProcess(args, 0, "MENU_CLICKED", "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    result = _executor(Delegate(), Verifier(verified=False), (DESKTOP_ID, 12)).execute(
        _request(CommandKind.TELEGRAM_SETTINGS, "label:unlisted section")
    )
    assert result.outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert result.error_code is None
    assert "settings-click" not in modes


def test_archive_navigation_reads_state_before_an_explicit_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    match = ChatSearchMatch(80, 100, 70, 20, 1000, 800)

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        mode = args[4]
        calls.append(mode)
        marker = {
            "menu": "MENU_CLICKED",
            "menu-click": "CHAT_RESULT_CLICKED",
        }[mode]
        return subprocess.CompletedProcess(args, 0, marker, "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    verifier = Verifier(match=match)
    verifier.find_left_label = (  # type: ignore[method-assign]
        lambda app_id, pid, label, *, menu=False: (
            (match if not calls else None)
            if label == "Archived Chats"
            else match
            if not menu or calls.count("menu") >= 2
            else None
        )
    )
    executor = _executor(Delegate(), verifier, (DESKTOP_ID, 12))
    result = executor.execute(_request(CommandKind.TELEGRAM_VIEW, "profile"))
    assert result.outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert calls == ["menu"]
    # The explicit next command must read menu state again before any input.
    reads: list[int] = []
    original = verifier.find_left_label

    def read(
        app_id: str, pid: int, label: str, *, menu: bool = False
    ) -> ChatSearchMatch | None:
        reads.append(len(calls))
        return original(app_id, pid, label, menu=menu)

    monkeypatch.setattr(verifier, "find_left_label", read)
    result = executor.execute(_request(CommandKind.TELEGRAM_VIEW, "profile"))
    assert result.outcome is ActionOutcome.CONFIRMED
    assert calls == ["menu", "menu", "menu-click"]
    assert reads[0] == 1


def test_telegram_shortcut_with_unverified_heading_is_accepted_not_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "kyrin.actions.platforms.telegram.run_process",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args, 0, "VIEW_SHORTCUT_DISPATCHED", ""
        ),
    )
    result = _executor(Delegate(), Verifier(), (DESKTOP_ID, 12)).execute(
        _request(CommandKind.TELEGRAM_VIEW, "archive")
    )
    assert result.outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert result.error_code is None


def test_navigation_polls_slow_heading_without_repeating_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modes: list[str] = []
    reads: list[bool] = []
    verifier = Verifier()

    def title(*_args: object, **_kwargs: object) -> ChatSearchMatch | None:
        reads.append(True)
        return ChatSearchMatch(80, 80, 100, 20, 1000, 800) if len(reads) >= 3 else None

    def run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        modes.append(args[4])
        return subprocess.CompletedProcess(args, 0, "VIEW_SHORTCUT_DISPATCHED", "")

    monkeypatch.setattr(verifier, "find_left_label", title)
    monkeypatch.setattr(telegram, "run_process", run)
    monkeypatch.setattr(telegram, "sleep", lambda _seconds: None)
    result = _executor(Delegate(), verifier, (DESKTOP_ID, 12)).execute(
        _request(CommandKind.TELEGRAM_VIEW, "archive")
    )
    assert result.outcome is ActionOutcome.CONFIRMED
    assert modes == ["view"]
    assert len(reads) == 3


def _request(kind: CommandKind, target: str, app: str | None = None) -> ActionRequest:
    return ActionRequest(KEY, CommandIntent(kind, target, app), "en")


def _visible_request(target: str = "My Mother") -> ActionRequest:
    return ActionRequest(
        KEY,
        CommandIntent(CommandKind.OPEN_CHAT, target, "telegram", chat_scope="visible"),
        "en",
    )


def test_visible_chat_clicks_one_stable_row_without_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    choices = ChatSearchChoices(
        ChatSearchMatch(70, 220, 90, 18, 1600, 900),
        (),
        global_section_verified=True,
        source="visible",
    )

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "CHAT_RESULT_CLICKED", "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    result = _executor(
        Delegate(), Verifier(choices=choices), (DESKTOP_ID, 12)
    ).execute(_visible_request())
    assert result.outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert [args[4] for args in calls] == ["visible-click"]
    assert calls[0][5:7] == ["70", "220"]


def test_visible_chat_reports_changed_target_instead_of_unknown_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    choices = ChatSearchChoices(
        ChatSearchMatch(70, 780, 90, 18, 1600, 900),
        (), global_section_verified=True, source="visible",
    )
    monkeypatch.setattr(
        "kyrin.actions.platforms.telegram.run_process",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args, 2, "TARGET_CHANGED", ""
        ),
    )
    result = _executor(
        Delegate(), Verifier(choices=choices), (DESKTOP_ID, 12)
    ).execute(_visible_request())
    assert result.outcome is ActionOutcome.FAILED
    assert result.error_code == "chat_target_changed"


def test_visible_chat_reports_control_session_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    choices = ChatSearchChoices(
        ChatSearchMatch(70, 220, 90, 18, 1600, 900),
        (), global_section_verified=True, source="visible",
    )
    monkeypatch.setattr(
        "kyrin.actions.platforms.telegram.run_process",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args, 1, "CONTROL_SESSION_UNAVAILABLE:start", ""
        ),
    )
    result = _executor(
        Delegate(), Verifier(choices=choices), (DESKTOP_ID, 12)
    ).execute(_visible_request())
    assert result.outcome is ActionOutcome.FAILED
    assert result.error_code == "telegram_control_unavailable"


def test_visible_chat_never_falls_back_to_search_on_uncertain_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "kyrin.actions.platforms.telegram.run_process",
        lambda *args, **kwargs: pytest.fail("no input should be sent"),
    )
    result = _executor(Delegate(), Verifier(), (DESKTOP_ID, 12)).execute(
        _visible_request()
    )
    assert result.error_code == "visible_chat_uncertain:unclassified"


def test_visible_chat_scrolls_once_only_for_recognized_clipped_bottom_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    choices = ChatSearchChoices(
        ChatSearchMatch(69, 900, 8, 9, 1853, 1048),
        (),
        global_section_verified=True,
        source="visible",
    )
    executor = _executor(Delegate(), Verifier(choices=choices), (DESKTOP_ID, 12))
    reads = iter((None, choices))
    scrolls: list[tuple[str, int]] = []

    def read(*_args: object) -> ChatSearchChoices | None:
        executor._choice_status = "partial_bottom_row_matches_1"  # noqa: SLF001
        return next(reads)

    monkeypatch.setattr(executor, "_settled_visible_choices", read)
    def scroll(identity: tuple[str, int]) -> bool:
        scrolls.append(identity)
        return True

    monkeypatch.setattr(executor, "_scroll_visible_list", scroll)
    monkeypatch.setattr(
        "kyrin.actions.platforms.telegram.run_process",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args, 0, "CHAT_RESULT_CLICKED", ""
        ),
    )
    result = executor.execute(_visible_request("H"))
    assert result.outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert scrolls == [(DESKTOP_ID, 12)]


def test_two_visible_chats_wait_for_number_and_recheck_chosen_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    prompts: list[ResponseRequest] = []
    feedback = []
    done = Event()
    choices = ChatSearchChoices(
        ChatSearchMatch(70, 220, 90, 18, 1600, 900),
        (),
        (ChatSearchMatch(70, 280, 90, 18, 1600, 900),),
        global_section_verified=True,
        source="visible",
    )

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "CHAT_RESULT_CLICKED", "")

    def on_feedback(item: object) -> None:
        feedback.append(item)
        done.set()

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    selection = TelegramChatSelection(prompts.append, on_feedback)
    verifier = Verifier(choices=choices)
    verifier.find_search_choices = (  # type: ignore[method-assign]
        lambda *_: pytest.fail("visible selection must not read search results")
    )
    executor = telegram.TelegramSavedMessagesExecutor(
        Delegate(),
        telegram_desktop_id=DESKTOP_ID,
        identity_reader=lambda: (DESKTOP_ID, 12),
        verifier=verifier,
        selection=selection,
        remember_pointer=True,
    )
    selection.set_completion(executor.complete_selection)
    result = executor.execute(_visible_request())
    try:
        assert result.error_code == "chat_selection_pending"
        assert "2 visible chats" in prompts[0].message
        assert "next" not in prompts[0].message.casefold()
        assert calls == []
        assert selection.on_final_speech("number two")
        assert done.wait(2)
        assert [args[4] for args in calls] == ["visible-click"]
        assert calls[0][6] == "280"
    finally:
        selection.cancel()


def test_single_grounded_visible_title_opens_without_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    choices = ChatSearchChoices(
        ChatSearchMatch(70, 220, 90, 18, 1600, 900),
        (),
        global_section_verified=True,
        source="visible",
        grounded_titles=("matin",),
    )

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "CHAT_RESULT_CLICKED", "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    verifier = Verifier(choices=choices)
    result = _executor(Delegate(), verifier, (DESKTOP_ID, 12)).execute(
        _visible_request("martin")
    )
    assert result.outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert [args[4] for args in calls] == ["visible-click"]
    assert verifier.calls == [(DESKTOP_ID, 12, "matin")]


def test_single_grounded_visible_title_does_not_need_selection_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "kyrin.actions.platforms.telegram.run_process",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args, 0, "CHAT_RESULT_CLICKED", ""
        ),
    )
    choices = ChatSearchChoices(
        ChatSearchMatch(70, 220, 90, 18, 1600, 900),
        (),
        global_section_verified=True,
        source="visible",
        grounded_titles=("matin",),
    )
    result = _executor(Delegate(), Verifier(choices=choices), (DESKTOP_ID, 12)).execute(
        _visible_request("martin")
    )
    assert result.outcome is ActionOutcome.DISPATCHED_UNVERIFIED


def _executor(
    delegate: Delegate,
    verifier: Verifier,
    identity: tuple[str, int] | None,
    *,
    remember_pointer: bool = True,
) -> telegram.TelegramSavedMessagesExecutor:
    return telegram.TelegramSavedMessagesExecutor(
        delegate,
        telegram_desktop_id=DESKTOP_ID,
        identity_reader=lambda: identity,
        verifier=verifier,
        remember_pointer=remember_pointer,
        helper_path=Path("/tmp/telegram-helper.py"),
    )


def test_other_actions_delegate_without_keyboard_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "kyrin.actions.platforms.telegram.run_process",
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
        "kyrin.actions.platforms.telegram.run_process",
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
        (0, "SHORTCUT_DISPATCHED", False, ActionOutcome.DISPATCHED_UNVERIFIED, None),
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

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    verifier = Verifier(verified=verified)
    result = _executor(Delegate(), verifier, (DESKTOP_ID, 12)).execute(
        _request(CommandKind.OPEN_CHAT, "Saved Messages", "telegram")
    )
    assert calls == [["/usr/bin/python3", "/tmp/telegram-helper.py", DESKTOP_ID, "12"]]
    assert result.outcome is outcome
    assert result.error_code == error
    assert verifier.calls == (
        [(DESKTOP_ID, 12, "Saved Messages")] * (1 if verified else 3)
        if returncode == 0 and stdout else []
    )


@pytest.mark.parametrize(
    ("verified", "outcome", "error"),
    [
        (False, ActionOutcome.DISPATCHED_UNVERIFIED, None),
        (True, ActionOutcome.CONFIRMED, None),
    ],
)
@pytest.mark.parametrize("target", ["Saved Massages", "Save the messages"])
def test_observed_stt_spelling_still_requires_verified_saved_messages_header(
    target: str,
    verified: bool,
    outcome: ActionOutcome,
    error: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, "SHORTCUT_DISPATCHED", "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    verifier = Verifier(verified=verified)
    result = _executor(Delegate(), verifier, (DESKTOP_ID, 12)).execute(
        _request(CommandKind.OPEN_CHAT, target, "telegram")
    )

    assert result.outcome is outcome
    assert result.error_code == error
    assert verifier.calls == (
        [(DESKTOP_ID, 12, "Saved Messages")] * (1 if verified else 3)
    )


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

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
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
    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    verifier = DelayedVerifier()
    result = _executor(
        Delegate(), verifier, (DESKTOP_ID, 12), remember_pointer=True
    ).execute(_request(CommandKind.OPEN_CHAT, "Alice", "telegram"))
    assert result.outcome is ActionOutcome.CONFIRMED
    assert len(calls) == 2
    assert calls[1][4:11] == ["click", "72", "219", "91", "24", "1600", "900"]
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
    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
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

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    verifier = Verifier(match=ChatSearchMatch(70, 220, 90, 24, 1600, 900))
    result = _executor(
        Delegate(), verifier, (DESKTOP_ID, 12), remember_pointer=True
    ).execute(_request(CommandKind.OPEN_CHAT, "Alice", "telegram"))
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


def test_chat_click_requires_advance_pointer_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "SEARCH_TYPED", "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    verifier = Verifier(match=ChatSearchMatch(70, 92, 90, 13, 1600, 900))
    result = _executor(
        Delegate(), verifier, (DESKTOP_ID, 12), remember_pointer=False
    ).execute(_request(CommandKind.OPEN_CHAT, "Alice", "telegram"))
    assert result.error_code == "telegram_control_setup_required"
    assert calls == []  # Setup is required before any action-time portal request.


def test_one_local_chat_opens_without_prompt_despite_global_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    prompts: list[ResponseRequest] = []
    own = ChatSearchMatch(70, 92, 90, 13, 1600, 900)
    verifier = Verifier(
        match=own,
        choices=ChatSearchChoices(
            own,
            (ChatSearchMatch(70, 182, 90, 13, 1600, 900),),
            global_section_verified=True,
        ),
    )
    selection = TelegramChatSelection(prompts.append, lambda _: None)
    executor = telegram.TelegramSavedMessagesExecutor(
        Delegate(),
        telegram_desktop_id=DESKTOP_ID,
        identity_reader=lambda: (DESKTOP_ID, 12),
        verifier=verifier,
        selection=selection,
        remember_pointer=True,
        helper_path=Path("/tmp/telegram-helper.py"),
    )
    selection.set_completion(executor.complete_selection)

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        marker = "SEARCH_TYPED" if args[4] == "search" else "CHAT_RESULT_CLICKED"
        return subprocess.CompletedProcess(args, 0, marker, "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    result = executor.execute(_request(CommandKind.OPEN_CHAT, "Alice", "telegram"))
    assert result.outcome is ActionOutcome.CONFIRMED
    assert prompts == []
    assert len(calls) == 2
    assert calls[1][6] == "92"
    assert calls[1][-1] == "900"


def test_one_visible_local_without_section_boundary_waits_for_user_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    prompts: list[ResponseRequest] = []
    own = ChatSearchMatch(70, 92, 90, 13, 1600, 900)
    verifier = Verifier(match=own, choices=ChatSearchChoices(own, ()))
    selection = TelegramChatSelection(prompts.append, lambda _: None)
    executor = telegram.TelegramSavedMessagesExecutor(
        Delegate(),
        telegram_desktop_id=DESKTOP_ID,
        identity_reader=lambda: (DESKTOP_ID, 12),
        verifier=verifier,
        selection=selection,
        remember_pointer=True,
        helper_path=Path("/tmp/telegram-helper.py"),
    )
    selection.set_completion(executor.complete_selection)

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "SEARCH_TYPED", "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    result = executor.execute(_request(CommandKind.OPEN_CHAT, "Alice", "telegram"))
    assert result.error_code == "chat_selection_pending"
    assert len(calls) == 1
    assert "personal chats" in prompts[0].message
    selection.cancel()


def test_global_paging_keeps_scope_after_heading_scrolls_away(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = ChatSearchChoices(
        None,
        (ChatSearchMatch(70, 244, 90, 13, 1600, 900),),
        global_section_verified=True,
        view_signature="first",
    )
    # Without the heading, the OCR fallback calls this top row local.
    later = ChatSearchChoices(
        ChatSearchMatch(70, 92, 90, 13, 1600, 900),
        (),
        view_signature="later",
    )
    verifier = Verifier(choices=later)
    executor = _executor(Delegate(), verifier, (DESKTOP_ID, 12))
    readings = iter((first, later, later))
    monkeypatch.setattr(executor, "_settled_search_choices", lambda *_: next(readings))
    monkeypatch.setattr(executor, "_scroll_search_results", lambda *_: True)
    monkeypatch.setattr(
        executor,
        "_run_helper",
        lambda *_: subprocess.CompletedProcess([], 0, "CHAT_RESULT_CLICKED", ""),
    )
    identity = (DESKTOP_ID, 12)
    next_page = executor.next_search_page(identity, "Alice", first, Event())
    assert next_page is not None
    assert not next_page.local_results
    assert len(next_page.global_results) == 1
    result = executor.complete_selection(
        _request(CommandKind.OPEN_CHAT, "Alice", "telegram"),
        identity,
        "Alice",
        next_page,
        1,
        Event(),
    )
    assert result.outcome is ActionOutcome.DISPATCHED_UNVERIFIED


def test_personal_paging_never_switches_to_global_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = ChatSearchChoices(
        ChatSearchMatch(70, 92, 90, 13, 1600, 900),
        (),
        view_signature="first",
    )
    later = ChatSearchChoices(
        None,
        (ChatSearchMatch(70, 244, 90, 13, 1600, 900),),
        global_section_verified=True,
        view_signature="later",
    )
    executor = _executor(Delegate(), Verifier(), (DESKTOP_ID, 12))
    readings = iter((first, later))
    monkeypatch.setattr(executor, "_settled_search_choices", lambda *_: next(readings))
    monkeypatch.setattr(executor, "_scroll_search_results", lambda *_: True)
    assert executor.next_search_page((DESKTOP_ID, 12), "Alice", first, Event()) is None


def test_personal_paging_rejects_unverified_section_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = ChatSearchChoices(
        ChatSearchMatch(70, 92, 90, 13, 1600, 900),
        (),
        view_signature="first",
    )
    # This might be another personal row or a global row after its heading
    # scrolled out of view; neither is safe to label personal.
    ambiguous = ChatSearchChoices(
        ChatSearchMatch(70, 92, 90, 13, 1600, 900),
        (),
        view_signature="later",
    )
    executor = _executor(Delegate(), Verifier(), (DESKTOP_ID, 12))
    readings = iter((first, ambiguous))
    monkeypatch.setattr(executor, "_settled_search_choices", lambda *_: next(readings))
    monkeypatch.setattr(executor, "_scroll_search_results", lambda *_: True)
    assert executor.next_search_page((DESKTOP_ID, 12), "Alice", first, Event()) is None


def test_personal_paging_accepts_local_row_above_verified_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = ChatSearchChoices(
        ChatSearchMatch(70, 92, 90, 13, 1600, 900),
        (),
        view_signature="first",
    )
    later = ChatSearchChoices(
        ChatSearchMatch(70, 92, 90, 13, 1600, 900),
        (),
        global_section_verified=True,
        view_signature="later",
    )
    executor = _executor(Delegate(), Verifier(), (DESKTOP_ID, 12))
    readings = iter((first, later))
    monkeypatch.setattr(executor, "_settled_search_choices", lambda *_: next(readings))
    monkeypatch.setattr(executor, "_scroll_search_results", lambda *_: True)
    assert executor.next_search_page((DESKTOP_ID, 12), "Alice", first, Event()) == later


@pytest.mark.parametrize(
    ("answer", "expected_top"),
    [("number one", 92), ("number two", 154), ("two", 154), ("the second one", 154)],
)
def test_named_chat_asks_then_rechecks_selected_row(
    answer: str, expected_top: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    prompts: list[ResponseRequest] = []
    feedback = []
    done = Event()
    choices = ChatSearchChoices(
        ChatSearchMatch(70, 92, 90, 13, 1600, 900),
        (ChatSearchMatch(70, 244, 90, 13, 1600, 900),),
        (ChatSearchMatch(70, 154, 90, 13, 1600, 900),),
    )
    verifier = Verifier(choices=choices)

    def on_feedback(item: object) -> None:
        feedback.append(item)
        done.set()

    selection = TelegramChatSelection(prompts.append, on_feedback)
    executor = telegram.TelegramSavedMessagesExecutor(
        Delegate(),
        telegram_desktop_id=DESKTOP_ID,
        identity_reader=lambda: (DESKTOP_ID, 12),
        verifier=verifier,
        selection=selection,
        remember_pointer=True,
        helper_path=Path("/tmp/telegram-helper.py"),
    )
    selection.set_completion(executor.complete_selection)

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        marker = "SEARCH_TYPED" if args[4] == "search" else "CHAT_RESULT_CLICKED"
        return subprocess.CompletedProcess(args, 0, marker, "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    result = executor.execute(_request(CommandKind.OPEN_CHAT, "Alice", "telegram"))
    assert result.error_code == "chat_selection_pending"
    assert len(prompts) == 1
    assert len(calls) == 1
    verifier.choices = ChatSearchChoices(
        choices.own_chat,
        (ChatSearchMatch(70, 310, 90, 13, 1600, 900),),
        choices.other_local_results,
    )
    assert selection.on_final_speech(answer)
    assert done.wait(4)
    assert feedback[0].outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert calls[1][6] == str(expected_top)


def test_global_only_chat_asks_and_rechecks_selected_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    prompts: list[ResponseRequest] = []
    feedback = []
    done = Event()
    choices = ChatSearchChoices(
        None,
        (
            ChatSearchMatch(70, 244, 90, 13, 1600, 900),
            ChatSearchMatch(70, 306, 90, 13, 1600, 900),
        ),
        global_section_verified=True,
    )
    verifier = Verifier(choices=choices)
    selection = TelegramChatSelection(
        prompts.append, lambda item: (feedback.append(item), done.set())
    )
    executor = telegram.TelegramSavedMessagesExecutor(
        Delegate(),
        telegram_desktop_id=DESKTOP_ID,
        identity_reader=lambda: (DESKTOP_ID, 12),
        verifier=verifier,
        selection=selection,
        remember_pointer=True,
        helper_path=Path("/tmp/telegram-helper.py"),
    )
    selection.set_completion(executor.complete_selection)

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        marker = "SEARCH_TYPED" if args[4] == "search" else "CHAT_RESULT_CLICKED"
        return subprocess.CompletedProcess(args, 0, marker, "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    result = executor.execute(_request(CommandKind.OPEN_CHAT, "Alice", "telegram"))
    assert result.error_code == "chat_selection_pending"
    assert "global search results" in prompts[0].message
    assert len(calls) == 1
    assert selection.on_final_speech("number two")
    assert done.wait(4)
    assert feedback[0].outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert calls[1][6] == "306"


def test_global_only_chat_rejects_moved_row_before_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    feedback = []
    done = Event()
    shown = ChatSearchChoices(
        None,
        (ChatSearchMatch(70, 244, 90, 13, 1600, 900),),
        global_section_verified=True,
    )
    verifier = Verifier(choices=shown)
    selection = TelegramChatSelection(
        lambda _: None, lambda item: (feedback.append(item), done.set())
    )
    executor = telegram.TelegramSavedMessagesExecutor(
        Delegate(),
        telegram_desktop_id=DESKTOP_ID,
        identity_reader=lambda: (DESKTOP_ID, 12),
        verifier=verifier,
        selection=selection,
        remember_pointer=True,
        helper_path=Path("/tmp/telegram-helper.py"),
    )
    selection.set_completion(executor.complete_selection)

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "SEARCH_TYPED", "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    result = executor.execute(_request(CommandKind.OPEN_CHAT, "Alice", "telegram"))
    assert result.error_code == "chat_selection_pending"
    verifier.choices = ChatSearchChoices(
        None,
        (ChatSearchMatch(70, 306, 90, 13, 1600, 900),),
        global_section_verified=True,
    )
    assert selection.on_final_speech("one")
    assert done.wait(4)
    assert feedback[0].error_code == (
        "chat_search_uncertain:selection_global_rows_changed_1_to_1"
    )
    assert len(calls) == 1


def test_named_chat_rejects_moved_result_after_spoken_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    feedback = []
    done = Event()
    shown = ChatSearchChoices(
        ChatSearchMatch(70, 92, 90, 13, 1600, 900),
        (ChatSearchMatch(70, 182, 90, 13, 1600, 900),),
        (ChatSearchMatch(70, 154, 90, 13, 1600, 900),),
    )
    verifier = Verifier(choices=shown)

    def on_feedback(item: object) -> None:
        feedback.append(item)
        done.set()

    selection = TelegramChatSelection(lambda _: None, on_feedback)
    executor = telegram.TelegramSavedMessagesExecutor(
        Delegate(),
        telegram_desktop_id=DESKTOP_ID,
        identity_reader=lambda: (DESKTOP_ID, 12),
        verifier=verifier,
        selection=selection,
        remember_pointer=True,
        helper_path=Path("/tmp/telegram-helper.py"),
    )
    selection.set_completion(executor.complete_selection)

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "SEARCH_TYPED", "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    result = executor.execute(_request(CommandKind.OPEN_CHAT, "Alice", "telegram"))
    assert result.error_code == "chat_selection_pending"
    verifier.choices = ChatSearchChoices(
        shown.own_chat,
        shown.global_results,
        (ChatSearchMatch(70, 160, 90, 13, 1600, 900),),
    )
    assert selection.on_final_speech("number one")
    assert done.wait(4)
    assert feedback[0].error_code == (
        "chat_search_uncertain:selection_local_rows_changed_2_to_2"
    )
    assert len(calls) == 1


def test_stopping_selection_during_fresh_read_prevents_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    reading = Event()
    resume = Event()
    finished = Event()
    shown = ChatSearchChoices(
        ChatSearchMatch(70, 92, 90, 13, 1600, 900),
        (ChatSearchMatch(70, 182, 90, 13, 1600, 900),),
        (ChatSearchMatch(70, 154, 90, 13, 1600, 900),),
    )

    class PausingVerifier(Verifier):
        def __init__(self) -> None:
            super().__init__(choices=shown)
            self.reads = 0

        def find_search_choices(self, app_id, pid, target):
            self.reads += 1
            if self.reads == 3:
                reading.set()
                assert resume.wait(3)
            return self.choices

    verifier = PausingVerifier()
    selection = TelegramChatSelection(lambda _: None, lambda _: None)
    executor = telegram.TelegramSavedMessagesExecutor(
        Delegate(),
        telegram_desktop_id=DESKTOP_ID,
        identity_reader=lambda: (DESKTOP_ID, 12),
        verifier=verifier,
        selection=selection,
        remember_pointer=True,
        helper_path=Path("/tmp/telegram-helper.py"),
    )

    def complete(*args):
        try:
            return executor.complete_selection(*args)
        finally:
            finished.set()

    selection.set_completion(complete)

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "SEARCH_TYPED", "")

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", run)
    result = executor.execute(_request(CommandKind.OPEN_CHAT, "Alice", "telegram"))
    assert result.error_code == "chat_selection_pending"
    assert selection.on_final_speech("number one")
    assert reading.wait(3)
    selection.cancel()
    resume.set()
    assert finished.wait(3)
    assert len(calls) == 1


def test_refreshing_global_results_do_not_block_local_choice_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    own = ChatSearchMatch(70, 92, 90, 13, 1600, 900)
    second_local = ChatSearchMatch(70, 154, 90, 13, 1600, 900)
    choices = cycle(
        (
            ChatSearchChoices(
                own,
                (ChatSearchMatch(70, 244, 90, 13, 1600, 900),),
                (second_local,),
            ),
            ChatSearchChoices(
                own,
                (ChatSearchMatch(70, 310, 90, 13, 1600, 900),),
                (second_local,),
            ),
        )
    )

    class UnstableVerifier(Verifier):
        def find_search_choices(self, app_id, pid, target):
            return next(choices)

        def choice_status(self) -> str:
            return "classified_own_1_global_1"

    monkeypatch.setattr(
        "kyrin.actions.platforms.telegram.run_process",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 0, "SEARCH_TYPED", ""),
    )
    prompts: list[ResponseRequest] = []
    flow = TelegramChatSelection(prompts.append, lambda _: None)
    executor = telegram.TelegramSavedMessagesExecutor(
        Delegate(),
        telegram_desktop_id=DESKTOP_ID,
        identity_reader=lambda: (DESKTOP_ID, 12),
        verifier=UnstableVerifier(),
        selection=flow,
        remember_pointer=True,
        helper_path=Path("/tmp/telegram-helper.py"),
    )
    flow.set_completion(executor.complete_selection)
    result = executor.execute(_request(CommandKind.OPEN_CHAT, "Alice", "telegram"))
    assert result.error_code == "chat_selection_pending"
    assert len(prompts) == 1
    flow.cancel()


def test_empty_search_view_waits_for_result_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elapsed = [0.0]
    own = ChatSearchMatch(70, 92, 90, 13, 1600, 900)
    global_row = ChatSearchMatch(70, 182, 90, 13, 1600, 900)
    populated = ChatSearchChoices(own, (global_row,))
    readings = iter(
        (ChatSearchChoices(None, ()), ChatSearchChoices(None, ()), populated, populated)
    )

    class DelayedVerifier(Verifier):
        def find_search_choices(self, app_id, pid, target):
            return next(readings)

    monkeypatch.setattr(
        "kyrin.actions.platforms.telegram.monotonic", lambda: elapsed[0]
    )
    monkeypatch.setattr(
        "kyrin.actions.platforms.telegram.sleep",
        lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
    )
    executor = _executor(Delegate(), DelayedVerifier(), (DESKTOP_ID, 12))

    assert executor._settled_search_choices((DESKTOP_ID, 12), "Alice") == populated


def test_keyboard_timeout_never_claims_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired("helper", 65)

    monkeypatch.setattr("kyrin.actions.platforms.telegram.run_process", timeout)
    result = _executor(Delegate(), Verifier(), (DESKTOP_ID, 12)).execute(
        _request(CommandKind.OPEN_CHAT, "Saved Messages", "telegram")
    )
    assert result.outcome is ActionOutcome.UNKNOWN


def test_slow_first_visible_read_does_not_get_extra_confirmation_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elapsed = [0.0]
    calls = []
    choices = ChatSearchChoices(ChatSearchMatch(70, 92, 90, 13, 1600, 900), ())

    class SlowVerifier(Verifier):
        def find_visible_chat_choices(self, app_id, pid, target):
            calls.append(target)
            elapsed[0] += 11
            return choices

    monkeypatch.setattr(telegram, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(telegram, "sleep", lambda delay: None)
    executor = _executor(Delegate(), SlowVerifier(), (DESKTOP_ID, 12))
    assert executor._settled_visible_choices((DESKTOP_ID, 12), "Alice") is None
    assert calls == ["Alice"]


@pytest.mark.parametrize("reply_known", [True, False])
def test_slow_chat_header_is_observed_without_resending_click(
    monkeypatch: pytest.MonkeyPatch, reply_known: bool,
) -> None:
    verifier = Verifier()
    executor = _executor(Delegate(), verifier, (DESKTOP_ID, 12))
    events: list[str] = []

    def verify(*_args: object) -> bool:
        events.append("read")
        return events.count("read") >= 3

    def run(*_args: object) -> subprocess.CompletedProcess[str] | None:
        events.append("dispatch")
        return (
            subprocess.CompletedProcess([], 0, "CHAT_RESULT_CLICKED", "")
            if reply_known else None
        )

    monkeypatch.setattr(verifier, "verify", verify)
    monkeypatch.setattr(executor, "_run_helper", run)
    monkeypatch.setattr(telegram, "sleep", lambda _seconds: None)
    result = executor._click_result(
        _request(CommandKind.OPEN_CHAT, "Alice", "telegram"),
        (DESKTOP_ID, 12), "Alice", ChatSearchMatch(80, 200, 90, 20, 1000, 800),
    )
    assert result.outcome is ActionOutcome.CONFIRMED
    assert events == ["dispatch", "read", "read", "read"]


def test_no_effect_chat_click_stays_dispatched_and_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = Verifier(verified=False)
    executor = _executor(Delegate(), verifier, (DESKTOP_ID, 12))
    calls: list[bool] = []

    def run(*_args: object) -> subprocess.CompletedProcess[str]:
        calls.append(True)
        return subprocess.CompletedProcess([], 0, "CHAT_RESULT_CLICKED", "")

    monkeypatch.setattr(executor, "_run_helper", run)
    monkeypatch.setattr(telegram, "sleep", lambda _seconds: None)
    result = executor._click_result(
        _request(CommandKind.OPEN_CHAT, "Alice", "telegram"),
        (DESKTOP_ID, 12), "Alice", ChatSearchMatch(80, 200, 90, 20, 1000, 800),
    )
    assert result.outcome is ActionOutcome.DISPATCHED_UNVERIFIED
    assert len(calls) == 1 and len(verifier.calls) == 3


def test_focus_change_during_postcondition_read_cannot_confirm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = [(DESKTOP_ID, 12)]
    verifier = Verifier()
    executor = telegram.TelegramSavedMessagesExecutor(
        Delegate(), telegram_desktop_id=DESKTOP_ID,
        identity_reader=lambda: identity[0], verifier=verifier,
    )

    def read() -> bool:
        identity[0] = ("other.desktop", 14)
        return True

    assert not executor._wait_postcondition((DESKTOP_ID, 12), read)
