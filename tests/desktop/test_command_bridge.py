"""Foreground context is fresh at final decisions and absent when unavailable."""

from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import (
    CommandIntent,
    CommandKind,
    CommandResolution,
    ResponseChannel,
    ResponseKind,
    ResponseRequest,
)
from kyrin.desktop.command_bridge import observe_command_update
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


class Observer:
    def __init__(self, results: list[str | None]) -> None:
        self.results = iter(results)
        self.calls = 0

    def observe_active_app(self) -> str | None:
        self.calls += 1
        return next(self.results)


def test_final_only_observation_does_not_reuse_earlier_focus() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    observer = Observer(["telegram", None])

    active, events = observe_command_update(
        coordinator,
        TranscriptUpdate(0, "چت علی را باز کن", TranscriptStatus.PARTIAL, "fa"),
        observer,
    )
    assert active is None
    assert events == ()
    assert observer.calls == 0

    active, events = observe_command_update(
        coordinator,
        TranscriptUpdate(0, "چت علی را باز کن", TranscriptStatus.FINAL, "fa"),
        observer,
    )
    assert active == "telegram"
    assert events == (
        CommandResolution(
            0, CommandIntent(CommandKind.OPEN_CHAT, "علی", "telegram"), language="fa"
        ),
    )
    assert observer.calls == 1

    active, events = observe_command_update(
        coordinator,
        TranscriptUpdate(1, "چت مریم را باز کن", TranscriptStatus.FINAL, "fa"),
        observer,
    )
    assert active is None
    assert events == (
        CommandResolution(1, None, language="fa"),
        ResponseRequest(
            1,
            ResponseKind.CHOOSE_CHAT_APP,
            ResponseChannel.TEXT_AND_VOICE,
            target="مریم",
            language="fa",
        ),
    )
    assert observer.calls == 2


def test_scroll_focus_is_read_only_for_final_speech() -> None:
    coordinator = CommandCoordinator(
        DemoCommandInterpreter(scroll_any_focused_app=True)
    )
    focus = [("unselected.desktop", 42)]
    calls = 0

    def read_focus() -> tuple[str, int] | None:
        nonlocal calls
        calls += 1
        return focus.pop(0)

    _, partial = observe_command_update(
        coordinator,
        TranscriptUpdate(0, "Scroll down", TranscriptStatus.PARTIAL, "en"),
        None,
        read_focus,
    )
    assert partial == ()
    assert calls == 0
    _, final = observe_command_update(
        coordinator,
        TranscriptUpdate(0, "Scroll down", TranscriptStatus.FINAL, "en"),
        None,
        read_focus,
    )
    assert final == (
        CommandResolution(
            0, CommandIntent(CommandKind.SCROLL_DOWN, "unselected.desktop"),
            language="en",
        ),
    )
    assert calls == 1
