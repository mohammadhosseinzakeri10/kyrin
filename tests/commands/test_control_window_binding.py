"""A new command is required when initial window evidence is insufficient."""

import pytest

from kyrin.commands import coordinator
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import CommandResolution, ResponseKind, ResponseRequest
from kyrin.desktop.window_observation import WindowObservation
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


@pytest.mark.parametrize(
    "evidence",
    [
        None,
        WindowObservation("example.desktop", 42, "window-7", "initial", 100, 110),
    ],
)
def test_missing_or_expired_initial_evidence_requests_review(
    evidence: WindowObservation | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(coordinator, "monotonic", lambda: 110)
    commands = CommandCoordinator(
        DemoCommandInterpreter(control_any_focused_app=True),
        window_observer=lambda: evidence,
    )
    events = commands.observe(
        TranscriptUpdate(0, "Click Settings", TranscriptStatus.FINAL, "en"),
        observed_scroll_app="example.desktop",
    )
    assert (
        next(event for event in events if isinstance(event, CommandResolution)).intent
        is None
    )
    assert any(
        isinstance(event, ResponseRequest) and event.kind is ResponseKind.REPEAT_COMMAND
        for event in events
    )


def test_rules_preserve_initial_generation_and_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(coordinator, "monotonic", lambda: 101)
    evidence = WindowObservation("example.desktop", 42, "window-7", "initial", 100, 110)
    commands = CommandCoordinator(
        DemoCommandInterpreter(control_any_focused_app=True),
        window_observer=lambda: evidence,
    )
    events = commands.observe(
        TranscriptUpdate(0, "Click Settings", TranscriptStatus.FINAL, "en"),
        observed_scroll_app="example.desktop",
    )
    intent = next(
        event for event in events if isinstance(event, CommandResolution)
    ).intent
    assert intent is not None and intent.control_observation is evidence


def test_partial_does_not_read_window_evidence() -> None:
    commands = CommandCoordinator(
        DemoCommandInterpreter(control_any_focused_app=True),
        window_observer=lambda: pytest.fail("partial must not read window evidence"),
    )
    commands.observe(
        TranscriptUpdate(0, "Click Settings", TranscriptStatus.PARTIAL, "en"),
        observed_scroll_app="example.desktop",
    )
