"""Scroll and More stay bound to the window observed for the spoken request."""

from collections.abc import Iterator

import pytest

from kyrin.commands import coordinator
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import (
    CommandIntent,
    CommandKind,
    CommandResolution,
    ResponseKind,
    ResponseRequest,
)
from kyrin.desktop.window_observation import WindowObservation
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate

APP = "org.example.Viewer.desktop"


def _window(token: str, generation: str, *, pid: int = 42) -> WindowObservation:
    return WindowObservation(APP, pid, token, generation, 100, 110)


def _final(segment_id: int, text: str) -> TranscriptUpdate:
    return TranscriptUpdate(segment_id, text, TranscriptStatus.FINAL, "en")


def _intent(events: object) -> CommandIntent | None:
    assert isinstance(events, tuple)
    return next(
        event for event in events if isinstance(event, CommandResolution)
    ).intent


def _coordinator(windows: Iterator[WindowObservation | None]) -> CommandCoordinator:
    return CommandCoordinator(
        DemoCommandInterpreter(scroll_any_focused_app=True),
        window_observer=lambda: next(windows),
    )


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(coordinator, "monotonic", lambda: 101)


def test_scroll_carries_initial_window_generation_and_deadline() -> None:
    evidence = _window("window-1", "initial")
    commands = _coordinator(iter((evidence,)))
    intent = _intent(
        commands.observe(_final(0, "Scroll down less"), observed_scroll_app=APP)
    )
    assert intent == CommandIntent(
        CommandKind.SCROLL_DOWN, APP, scroll_steps=2, scroll_observation=evidence
    )
    assert intent is not None and intent.scroll_observation is evidence


@pytest.mark.parametrize(
    "evidence",
    [
        None,
        WindowObservation(APP, 42, "window-1", "expired", 90, 100),
        WindowObservation("other.desktop", 42, "window-1", "other", 100, 110),
    ],
)
def test_missing_expired_or_other_app_evidence_produces_no_scroll(
    evidence: WindowObservation | None,
) -> None:
    commands = _coordinator(iter((evidence,)))
    events = commands.observe(_final(0, "Scroll down"), observed_scroll_app=APP)
    assert _intent(events) is None
    assert any(
        isinstance(event, ResponseRequest) and event.kind is ResponseKind.REPEAT_COMMAND
        for event in events
    )


def test_more_repeats_only_in_the_same_window_with_its_new_evidence() -> None:
    first = _window("window-1", "first")
    again = _window("window-1", "again")
    commands = _coordinator(iter((first, again)))
    assert _intent(
        commands.observe(_final(0, "Scroll up less"), observed_scroll_app=APP)
    ) == CommandIntent(
        CommandKind.SCROLL_UP, APP, scroll_steps=2, scroll_observation=first
    )
    intent = _intent(commands.observe(_final(1, "More"), observed_scroll_app=APP))
    assert intent == CommandIntent(
        CommandKind.SCROLL_UP, APP, scroll_steps=2, scroll_observation=again
    )
    assert intent is not None and intent.scroll_observation is again


@pytest.mark.parametrize(
    "replacement",
    [
        # Another window of the same application and process.
        _window("window-2", "replacement"),
        # The same token reported for a different process is not the same window.
        _window("window-1", "replacement", pid=43),
    ],
)
def test_more_cannot_inherit_another_windows_scroll_history(
    replacement: WindowObservation,
) -> None:
    commands = _coordinator(iter((_window("window-1", "first"), replacement)))
    assert _intent(
        commands.observe(_final(0, "Scroll down"), observed_scroll_app=APP)
    ) is not None
    assert _intent(commands.observe(_final(1, "More"), observed_scroll_app=APP)) is None


def test_more_after_unbound_scroll_is_not_offered() -> None:
    commands = _coordinator(iter((None, _window("window-1", "again"))))
    assert _intent(
        commands.observe(_final(0, "Scroll down"), observed_scroll_app=APP)
    ) is None
    assert _intent(commands.observe(_final(1, "More"), observed_scroll_app=APP)) is None


def test_partial_scroll_does_not_read_window_evidence() -> None:
    commands = CommandCoordinator(
        DemoCommandInterpreter(scroll_any_focused_app=True),
        window_observer=lambda: pytest.fail("partial must not read window evidence"),
    )
    commands.observe(
        TranscriptUpdate(0, "Scroll down", TranscriptStatus.PARTIAL, "en"),
        observed_scroll_app=APP,
    )
