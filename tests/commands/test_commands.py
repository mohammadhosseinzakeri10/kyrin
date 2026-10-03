"""Command decisions are deterministic without a microphone or OS actions."""

import pytest

from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.interpreter import Interpretation, ReadyCommand
from kyrin.commands.models import (
    CommandCandidateUpdate,
    CommandContext,
    CommandIntent,
    CommandKind,
    CommandResolution,
    PendingClarification,
    ResponseChannel,
    ResponseRequest,
)
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


def update(segment_id: int, text: str, status: TranscriptStatus) -> TranscriptUpdate:
    return TranscriptUpdate(segment_id, text, status, language="fa")


def test_first_ready_partial_is_candidate_and_final_resolves_same_segment() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    intent = CommandIntent(CommandKind.OPEN_APP, "telegram")
    partial = update(0, "کایری تلگرام را باز کن", TranscriptStatus.PARTIAL)

    assert coordinator.observe(partial) == (CommandCandidateUpdate(0, intent),)
    assert coordinator.observe(partial) == ()
    assert coordinator.observe(update(0, partial.text, TranscriptStatus.FINAL)) == (
        CommandResolution(0, intent),
    )
    assert coordinator.observe(update(0, partial.text, TranscriptStatus.FINAL)) == ()


def test_revised_partial_retracts_candidate_and_final_can_disagree() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    first = update(0, "تلگرام را باز کن", TranscriptStatus.PARTIAL)
    assert coordinator.observe(first) == (
        CommandCandidateUpdate(0, CommandIntent(CommandKind.OPEN_APP, "telegram")),
    )
    assert coordinator.observe(
        update(0, "تلگرام را باز نکن", TranscriptStatus.PARTIAL)
    ) == (CommandCandidateUpdate(0, None),)
    assert coordinator.observe(
        update(0, "تلگرام را باز نکن", TranscriptStatus.FINAL)
    ) == (CommandResolution(0, None),)


def test_later_ready_partial_replaces_candidate_under_same_id() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(
        update(0, "تلگرام را باز کن", TranscriptStatus.PARTIAL)
    ) == (CommandCandidateUpdate(0, CommandIntent(CommandKind.OPEN_APP, "telegram")),)
    assert coordinator.observe(
        update(0, "مرورگر را باز کن", TranscriptStatus.PARTIAL)
    ) == (CommandCandidateUpdate(0, CommandIntent(CommandKind.OPEN_APP, "browser")),)
    assert coordinator.observe(
        update(0, "مرورگر را باز کن", TranscriptStatus.FINAL)
    ) == (CommandResolution(0, CommandIntent(CommandKind.OPEN_APP, "browser")),)


def test_final_only_backend_can_produce_command_without_partials() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(
        update(0, "open the Telegram", TranscriptStatus.FINAL)
    ) == (CommandResolution(0, CommandIntent(CommandKind.OPEN_APP, "telegram")),)


def test_chat_requires_fresh_active_app_or_asks_for_app() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(
        update(0, "به گفتگوی علی برو", TranscriptStatus.FINAL)
    ) == (
        CommandResolution(0, None),
        ResponseRequest(
            0, "چت را در کدام برنامه باز کنم؟", ResponseChannel.TEXT_AND_VOICE
        ),
    )
    assert coordinator.pending_clarification is not None
    assert coordinator.observe(update(1, "تلگرام", TranscriptStatus.FINAL)) == (
        CommandResolution(1, CommandIntent(CommandKind.OPEN_CHAT, "علی", "telegram")),
    )
    assert coordinator.pending_clarification is None

    observed = CommandCoordinator(DemoCommandInterpreter())
    assert observed.observe(
        update(0, "چت علی را باز کن", TranscriptStatus.FINAL),
        observed_active_app="telegram",
    ) == (
        CommandResolution(0, CommandIntent(CommandKind.OPEN_CHAT, "علی", "telegram")),
    )


def test_previous_app_alone_does_not_resolve_chat_target() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(
        update(0, "تلگرام را باز کن", TranscriptStatus.FINAL)
    ) == (CommandResolution(0, CommandIntent(CommandKind.OPEN_APP, "telegram")),)
    assert coordinator.last_referenced_app == "telegram"
    assert coordinator.observe(update(1, "چت علی را باز کن", TranscriptStatus.FINAL))[
        -1
    ] == ResponseRequest(
        1, "چت را در کدام برنامه باز کنم؟", ResponseChannel.TEXT_AND_VOICE
    )


def test_unrelated_active_app_does_not_fill_chat_app() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    decisions = coordinator.observe(
        update(0, "چت علی را باز کن", TranscriptStatus.FINAL),
        observed_active_app="browser",
    )
    assert decisions[-1] == ResponseRequest(
        0, "چت را در کدام برنامه باز کنم؟", ResponseChannel.TEXT_AND_VOICE
    )


def test_explicit_chat_app_needs_no_context() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(
        update(0, "چت علی را در تلگرام باز کن", TranscriptStatus.FINAL)
    ) == (
        CommandResolution(0, CommandIntent(CommandKind.OPEN_CHAT, "علی", "telegram")),
    )


def test_conflicting_current_and_previous_app_requires_choice() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    coordinator.observe(update(0, "تلگرام را باز کن", TranscriptStatus.FINAL))
    assert coordinator.observe(
        update(1, "چت علی را باز کن", TranscriptStatus.FINAL),
        observed_active_app="whatsapp",
    ) == (
        CommandResolution(1, None),
        ResponseRequest(
            1,
            "چت علی را در تلگرام باز کنم یا واتساپ؟",
            ResponseChannel.TEXT_AND_VOICE,
        ),
    )
    assert coordinator.last_referenced_app == "telegram"
    assert coordinator.observe(update(2, "واتساپ", TranscriptStatus.FINAL)) == (
        CommandResolution(2, CommandIntent(CommandKind.OPEN_CHAT, "علی", "whatsapp")),
    )
    assert coordinator.last_referenced_app == "whatsapp"


def test_matching_fresh_active_app_resolves_after_earlier_app_command() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    coordinator.observe(update(0, "تلگرام را باز کن", TranscriptStatus.FINAL))
    assert coordinator.observe(
        update(1, "چت علی را باز کن", TranscriptStatus.FINAL),
        observed_active_app="telegram",
    ) == (
        CommandResolution(1, CommandIntent(CommandKind.OPEN_CHAT, "علی", "telegram")),
    )


def test_current_chat_app_is_used_when_history_does_not_conflict() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(
        update(0, "چت علی را باز کن", TranscriptStatus.FINAL),
        observed_active_app="whatsapp",
    ) == (
        CommandResolution(0, CommandIntent(CommandKind.OPEN_CHAT, "علی", "whatsapp")),
    )


def test_explicit_app_overrides_conflicting_foreground_and_history() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    coordinator.observe(update(0, "تلگرام را باز کن", TranscriptStatus.FINAL))
    assert coordinator.observe(
        update(1, "چت علی را در واتساپ باز کن", TranscriptStatus.FINAL),
        observed_active_app="telegram",
    ) == (
        CommandResolution(1, CommandIntent(CommandKind.OPEN_CHAT, "علی", "whatsapp")),
    )


def test_partial_app_change_does_not_replace_dialogue_reference() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    coordinator.observe(update(0, "تلگرام را باز کن", TranscriptStatus.FINAL))
    coordinator.observe(update(1, "مرورگر را باز کن", TranscriptStatus.PARTIAL))
    assert coordinator.last_referenced_app == "telegram"
    coordinator.observe(update(1, "مرورگر را باز نکن", TranscriptStatus.FINAL))
    assert coordinator.last_referenced_app == "telegram"


def test_referenced_app_survives_new_stt_stream_without_active_app_assumption() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    coordinator.observe(update(0, "تلگرام را باز کن", TranscriptStatus.FINAL))
    coordinator.start_new_stream()
    assert coordinator.last_referenced_app == "telegram"
    assert coordinator.observe(update(0, "چت علی را باز کن", TranscriptStatus.FINAL))[
        -1
    ] == (
        ResponseRequest(
            0, "چت را در کدام برنامه باز کنم؟", ResponseChannel.TEXT_AND_VOICE, 1
        )
    )


def test_pause_between_commands_does_not_reset_context_or_pending_question() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    coordinator.observe(update(0, "چت علی را باز کن", TranscriptStatus.FINAL))
    # A VAD pause is not forwarded to the command coordinator.
    assert coordinator.pending_clarification is not None
    assert coordinator.observe(update(1, "تلگرام", TranscriptStatus.FINAL)) == (
        CommandResolution(1, CommandIntent(CommandKind.OPEN_CHAT, "علی", "telegram")),
    )


def test_unfinished_or_unknown_command_requests_repetition_only_on_final() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert (
        coordinator.observe(update(0, "تلگرام را باز", TranscriptStatus.PARTIAL)) == ()
    )
    assert coordinator.observe(update(0, "تلگرام را باز", TranscriptStatus.FINAL)) == (
        CommandResolution(0, None),
        ResponseRequest(
            0,
            "متوجه نشدم. لطفاً فرمان را دوباره بگویید.",
            ResponseChannel.TEXT_AND_VOICE,
        ),
    )


def test_ambient_speech_does_not_trigger_prompt() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(
        update(0, "امروز هوا خوب است", TranscriptStatus.FINAL)
    ) == (CommandResolution(0, None),)


def test_new_segment_retracts_unfinished_previous_candidate() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    partial = update(0, "تلگرام را باز کن", TranscriptStatus.PARTIAL)
    coordinator.observe(partial)
    assert coordinator.observe(update(1, "سلام", TranscriptStatus.FINAL)) == (
        CommandCandidateUpdate(0, None),
        CommandResolution(1, None),
    )


def test_new_stt_stream_reuses_segment_ids_without_forgetting_question() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    coordinator.observe(update(0, "چت علی را باز کن", TranscriptStatus.FINAL))
    assert coordinator.start_new_stream() == ()
    assert coordinator.pending_clarification is not None
    assert coordinator.observe(update(0, "تلگرام", TranscriptStatus.FINAL)) == (
        CommandResolution(
            0, CommandIntent(CommandKind.OPEN_CHAT, "علی", "telegram"), stream_id=1
        ),
    )


def test_optional_wake_and_direct_command_have_same_meaning() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(
        update(0, "کایرین، تلگرام را باز کن", TranscriptStatus.FINAL)
    ) == (CommandResolution(0, CommandIntent(CommandKind.OPEN_APP, "telegram")),)
    assert coordinator.observe(update(1, "go to Telegram", TranscriptStatus.FINAL)) == (
        CommandResolution(1, CommandIntent(CommandKind.OPEN_APP, "telegram")),
    )


def test_invalid_intent_is_rejected() -> None:
    with pytest.raises(ValueError, match="target"):
        CommandIntent(CommandKind.OPEN_APP, " ")
    with pytest.raises(ValueError, match="requires"):
        CommandIntent(CommandKind.OPEN_CHAT, "Ali")


def test_interpreter_is_replaceable_and_receives_language_and_context() -> None:
    class AlternateInterpreter:
        def __init__(self) -> None:
            self.seen: tuple[str, str | None, CommandContext] | None = None

        def interpret(
            self,
            text: str,
            *,
            language: str | None,
            context: CommandContext,
            pending: PendingClarification | None,
        ) -> Interpretation:
            self.seen = (text, language, context)
            return ReadyCommand(CommandIntent(CommandKind.OPEN_APP, "calculator"))

    interpreter = AlternateInterpreter()
    coordinator = CommandCoordinator(interpreter)
    assert coordinator.observe(
        TranscriptUpdate(0, "calculadora", TranscriptStatus.FINAL, language="es"),
        observed_active_app="telegram",
    ) == (CommandResolution(0, CommandIntent(CommandKind.OPEN_APP, "calculator")),)
    assert interpreter.seen == (
        "calculadora",
        "es",
        CommandContext(observed_active_app="telegram"),
    )
