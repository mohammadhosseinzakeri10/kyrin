"""A compound utterance resolves as one final, ordered command plan."""

import pytest

from kyrin.commands.app_names import ModelAppOption, SpokenAppCandidate, SpokenAppMatch
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import (
    CommandCandidateUpdate,
    CommandIntent,
    CommandKind,
    CommandPlan,
    CommandPlanResolution,
    CommandResolution,
    ResponseKind,
    ResponseRequest,
)
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


@pytest.mark.parametrize(
    "phrase",
    (
        "Open Telegram and open Alice chat.",
        "Open Telegram and open Alice's chat.",
        "Open Telegram and open Alice’s chat.",
        "KYRIN, open Telegram and open chat Alice.",
    ),
)
def test_final_compound_command_keeps_both_steps_and_chat_app(phrase: str) -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    expected = CommandPlan(
        (
            CommandIntent(CommandKind.OPEN_APP, "telegram"),
            CommandIntent(CommandKind.OPEN_CHAT, "Alice", "telegram"),
        )
    )

    assert (
        coordinator.observe(TranscriptUpdate(4, phrase, TranscriptStatus.PARTIAL, "en"))
        == ()
    )
    assert coordinator.observe(
        TranscriptUpdate(4, phrase, TranscriptStatus.FINAL, "en")
    ) == (CommandPlanResolution(4, expected, language="en"),)
    assert coordinator.last_referenced_app == "telegram"
    assert (
        coordinator.observe(TranscriptUpdate(4, phrase, TranscriptStatus.FINAL, "en"))
        == ()
    )


def test_two_open_app_steps_keep_order() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(
        TranscriptUpdate(
            0, "Open Telegram and open WhatsApp", TranscriptStatus.FINAL, "en"
        )
    ) == (
        CommandPlanResolution(
            0,
            CommandPlan(
                (
                    CommandIntent(CommandKind.OPEN_APP, "telegram"),
                    CommandIntent(CommandKind.OPEN_APP, "whatsapp"),
                )
            ),
            language="en",
        ),
    )


def test_final_plan_retracts_an_earlier_single_step_preview() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(
        TranscriptUpdate(0, "Open Telegram", TranscriptStatus.PARTIAL, "en")
    ) == (CommandCandidateUpdate(0, CommandIntent(CommandKind.OPEN_APP, "telegram")),)
    final = coordinator.observe(
        TranscriptUpdate(
            0, "Open Telegram and open Alice chat", TranscriptStatus.FINAL, "en"
        )
    )
    assert final[0] == CommandCandidateUpdate(0, None)
    assert isinstance(final[1], CommandPlanResolution)


def test_unclear_second_clause_never_authorizes_first_fragment() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    events = coordinator.observe(
        TranscriptUpdate(
            0, "Open Telegram and go to Google", TranscriptStatus.FINAL, "en"
        )
    )
    assert events[0] == CommandResolution(0, None, language="en")
    assert isinstance(events[1], ResponseRequest)
    assert events[1].kind is ResponseKind.REPEAT_COMMAND


def test_negation_in_second_clause_never_makes_a_plan() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    events = coordinator.observe(
        TranscriptUpdate(
            0, "Open Telegram and do not open Alice chat", TranscriptStatus.FINAL
        )
    )
    assert all(not isinstance(event, CommandPlanResolution) for event in events)
    assert events[0] == CommandResolution(0, None)


def test_approximate_app_name_in_plan_never_executes_a_fragment() -> None:
    class NearMatchResolver:
        def model_options(self) -> tuple[ModelAppOption, ...]:
            return ()

        def suggest(self, spoken_name: str) -> SpokenAppMatch:
            return self.resolve(spoken_name)

        def resolve(self, _spoken_name: str) -> SpokenAppMatch:
            return SpokenAppMatch((SpokenAppCandidate("telegram", "Telegram"),))

    coordinator = CommandCoordinator(DemoCommandInterpreter(NearMatchResolver()))
    events = coordinator.observe(
        TranscriptUpdate(
            0, "Open Telegram and open Alice chat", TranscriptStatus.FINAL, "en"
        )
    )
    assert events[0] == CommandResolution(0, None, language="en")
    assert all(not isinstance(event, CommandPlanResolution) for event in events)


def test_plan_rejects_zero_or_unbounded_steps() -> None:
    step = CommandIntent(CommandKind.OPEN_APP, "telegram")
    with pytest.raises(ValueError, match="two or three"):
        CommandPlan((step,))
    with pytest.raises(ValueError, match="two or three"):
        CommandPlan((step, step, step, step))
