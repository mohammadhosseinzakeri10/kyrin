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
    PendingCommandClarification,
    ResponseChannel,
    ResponseKind,
    ResponseRequest,
)
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


def update(segment_id: int, text: str, status: TranscriptStatus) -> TranscriptUpdate:
    return TranscriptUpdate(segment_id, text, status)


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


def test_custom_wake_spelling_changes_only_prefix_recognition() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter(wake_aliases=("Kayrin",)))
    assert coordinator.observe(
        update(0, "Kayrin open Telegram", TranscriptStatus.FINAL)
    ) == (CommandResolution(0, CommandIntent(CommandKind.OPEN_APP, "telegram")),)
    assert coordinator.observe(update(1, "Kayrin", TranscriptStatus.FINAL)) == (
        CommandResolution(1, None),
        ResponseRequest(1, ResponseKind.READY_FOR_COMMAND, ResponseChannel.TEXT_ONLY),
    )


@pytest.mark.parametrize(
    "name",
    (
        "Kyreen",
        "Kyrie",
        "Kairi",
        "Kairin!",
        "Kyren",
        "Kyrene",
        "Kirin",
        "Kairina",
        "Kiring",
        "Curring",
    ),
)
def test_observed_wake_spellings_alone_acknowledge_without_an_action(
    name: str,
) -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(update(0, name, TranscriptStatus.FINAL)) == (
        CommandResolution(0, None),
        ResponseRequest(0, ResponseKind.READY_FOR_COMMAND, ResponseChannel.TEXT_ONLY),
    )
    assert coordinator.observe(
        update(1, f"{name} open Telegram", TranscriptStatus.FINAL)
    ) == (CommandResolution(1, CommandIntent(CommandKind.OPEN_APP, "telegram")),)


def test_unrelated_creator_word_is_not_a_wake_name() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(update(0, "Creator", TranscriptStatus.FINAL)) == (
        CommandResolution(0, None),
    )


def test_observed_unsupported_door_phrase_does_not_become_an_action() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(
        update(0, "Kairin please open door", TranscriptStatus.FINAL)
    ) == (
        CommandResolution(0, None),
        ResponseRequest(0, ResponseKind.REPEAT_COMMAND, ResponseChannel.TEXT_ONLY),
    )


@pytest.mark.parametrize(
    "phrase",
    ("Kairin Open Telegram", "تلیگرام را باز کن"),
)
def test_observed_stt_spellings_resolve_to_telegram(phrase: str) -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(update(0, phrase, TranscriptStatus.FINAL)) == (
        CommandResolution(0, CommandIntent(CommandKind.OPEN_APP, "telegram")),
    )


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


@pytest.mark.parametrize(
    ("phrase", "kind"),
    (
        ("Restore Telegram", CommandKind.RESTORE_APP),
        ("Show Telegram", CommandKind.RESTORE_APP),
        ("Minimize Telegram", CommandKind.MINIMIZE_APP),
        ("Close Telegram", CommandKind.CLOSE_APP_WINDOW),
        ("Exit Telegram", CommandKind.CLOSE_APP_WINDOW),
        ("Quit Telegram", CommandKind.CLOSE_APP_WINDOW),
        ("Please hide Telegram", CommandKind.MINIMIZE_APP),
        ("Bring Telegram to front", CommandKind.RESTORE_APP),
        ("تلگرام را پنهان کن", CommandKind.MINIMIZE_APP),
        ("تلگرام رو نشان بده", CommandKind.RESTORE_APP),
        ("تلگرام را دوباره نشان بده", CommandKind.RESTORE_APP),
        ("تلگرام را کوچک کن", CommandKind.MINIMIZE_APP),
        ("تلگرام را ببند", CommandKind.CLOSE_APP_WINDOW),
        ("Maximize Telegram", CommandKind.MAXIMIZE_APP),
        ("Unmaximize Telegram", CommandKind.UNMAXIMIZE_APP),
        ("Make Telegram fullscreen", CommandKind.FULLSCREEN_APP),
        ("Exit fullscreen on Telegram", CommandKind.UNFULLSCREEN_APP),
        ("تلگرام را بزرگ کن", CommandKind.MAXIMIZE_APP),
        ("تلگرام را به اندازه عادی برگردان", CommandKind.UNMAXIMIZE_APP),
        ("تلگرام را تمام صفحه کن", CommandKind.FULLSCREEN_APP),
        ("تلگرام را از تمام صفحه خارج کن", CommandKind.UNFULLSCREEN_APP),
    ),
)
def test_window_command_requires_exact_app_name(phrase: str, kind: CommandKind) -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(update(0, phrase, TranscriptStatus.FINAL)) == (
        CommandResolution(0, CommandIntent(kind, "telegram")),
    )


def test_unknown_window_target_never_becomes_action() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(update(0, "Close Telegrum", TranscriptStatus.FINAL))[
        0
    ] == (CommandResolution(0, None))


@pytest.mark.parametrize("phrase", (
    "Launch Telegram", "Please start Telegram", "Switch to Telegram",
))
def test_clear_open_synonyms_use_registered_open_action(phrase: str) -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(update(0, phrase, TranscriptStatus.FINAL)) == (
        CommandResolution(0, CommandIntent(CommandKind.OPEN_APP, "telegram")),
    )


def test_chat_requires_fresh_active_app_or_asks_for_app() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(
        update(0, "به گفتگوی علی برو", TranscriptStatus.FINAL)
    ) == (
        CommandResolution(0, None),
        ResponseRequest(
            0,
            ResponseKind.CHOOSE_CHAT_APP,
            ResponseChannel.TEXT_AND_VOICE,
            target="علی",
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
        1, ResponseKind.CHOOSE_CHAT_APP, ResponseChannel.TEXT_AND_VOICE, target="علی"
    )


def test_unrelated_active_app_does_not_fill_chat_app() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    decisions = coordinator.observe(
        update(0, "چت علی را باز کن", TranscriptStatus.FINAL),
        observed_active_app="browser",
    )
    assert decisions[-1] == ResponseRequest(
        0, ResponseKind.CHOOSE_CHAT_APP, ResponseChannel.TEXT_AND_VOICE, target="علی"
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
            ResponseKind.CHOOSE_CHAT_APP,
            ResponseChannel.TEXT_AND_VOICE,
            target="علی",
            app_candidates=("telegram", "whatsapp"),
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
            0,
            ResponseKind.CHOOSE_CHAT_APP,
            ResponseChannel.TEXT_AND_VOICE,
            1,
            target="علی",
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
            ResponseKind.REPEAT_COMMAND,
            ResponseChannel.TEXT_ONLY,
        ),
    )


def test_ambient_speech_does_not_trigger_prompt() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(
        update(0, "امروز هوا خوب است", TranscriptStatus.FINAL)
    ) == (CommandResolution(0, None),)


def test_dropped_negation_prefix_requests_repetition_without_authorizing() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(
        update(0, "to open telegram", TranscriptStatus.FINAL)
    ) == (
        CommandResolution(0, None),
        ResponseRequest(0, ResponseKind.REPEAT_COMMAND, ResponseChannel.TEXT_ONLY),
    )
    assert coordinator.observe(
        update(1, "do not open telegram", TranscriptStatus.FINAL)
    ) == (CommandResolution(1, None),)


@pytest.mark.parametrize("phrase", ["Kyrin, please help"])
def test_short_or_addressed_unclear_final_requests_repetition(phrase: str) -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(update(0, phrase, TranscriptStatus.FINAL)) == (
        CommandResolution(0, None),
        ResponseRequest(0, ResponseKind.REPEAT_COMMAND, ResponseChannel.TEXT_ONLY),
    )


def test_short_operation_joins_only_nearby_final_target() -> None:
    from kyrin.commands.fragments import CommandFragmentBuffer

    now = [0.0]
    coordinator = CommandCoordinator(
        DemoCommandInterpreter(),
        fragment_buffer=CommandFragmentBuffer(clock=lambda: now[0]),
    )
    assert coordinator.observe(update(0, "Open", TranscriptStatus.FINAL)) == (
        CommandResolution(0, None),
    )
    now[0] = 1.0
    assert coordinator.observe(update(1, "Telegram", TranscriptStatus.FINAL)) == (
        CommandResolution(1, CommandIntent(CommandKind.OPEN_APP, "telegram")),
    )


def test_split_open_chat_joins_nearby_name_with_active_telegram() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(update(0, "Open chat.", TranscriptStatus.FINAL)) == (
        CommandResolution(0, None),
    )
    assert coordinator.observe(
        update(1, "Hunter VPN", TranscriptStatus.FINAL),
        observed_active_app="telegram",
    ) == (
        CommandResolution(
            1, CommandIntent(CommandKind.OPEN_CHAT, "hunter vpn", "telegram")
        ),
    )


def test_split_open_chat_cannot_join_late_or_negated_name() -> None:
    from kyrin.commands.fragments import CommandFragmentBuffer

    now = [0.0]
    coordinator = CommandCoordinator(
        DemoCommandInterpreter(),
        fragment_buffer=CommandFragmentBuffer(clock=lambda: now[0]),
    )
    coordinator.observe(update(0, "Open chat", TranscriptStatus.FINAL))
    now[0] = 5.0
    assert coordinator.observe(
        update(1, "Hunter VPN", TranscriptStatus.FINAL),
        observed_active_app="telegram",
    )[0].intent is None
    coordinator.observe(update(2, "Open chat", TranscriptStatus.FINAL))
    assert coordinator.observe(
        update(3, "Do not open chat Hunter VPN", TranscriptStatus.FINAL),
        observed_active_app="telegram",
    )[0].intent is None


@pytest.mark.parametrize(
    ("operation", "target", "kind"),
    [
        ("Minimize", "Telegram", CommandKind.MINIMIZE_APP),
        ("Restore", "Telegram", CommandKind.RESTORE_APP),
        ("Maximize", "Telegram", CommandKind.MAXIMIZE_APP),
        ("Fullscreen", "Telegram", CommandKind.FULLSCREEN_APP),
        ("باز کن", "تلگرام", CommandKind.OPEN_APP),
        ("کوچک کن", "تلگرام", CommandKind.MINIMIZE_APP),
        ("بزرگ کن", "تلگرام", CommandKind.MAXIMIZE_APP),
    ],
)
def test_window_operation_joins_nearby_target(
    operation: str, target: str, kind: CommandKind
) -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    assert coordinator.observe(update(0, operation, TranscriptStatus.FINAL)) == (
        CommandResolution(0, None),
    )
    assert coordinator.observe(update(1, target, TranscriptStatus.FINAL)) == (
        CommandResolution(1, CommandIntent(kind, "telegram")),
    )


def test_old_fragment_cannot_authorize_a_later_target() -> None:
    from kyrin.commands.fragments import CommandFragmentBuffer

    now = [0.0]
    coordinator = CommandCoordinator(
        DemoCommandInterpreter(),
        fragment_buffer=CommandFragmentBuffer(clock=lambda: now[0]),
    )
    coordinator.observe(update(0, "Open", TranscriptStatus.FINAL))
    now[0] = 5.0
    decisions = coordinator.observe(update(1, "Telegram", TranscriptStatus.FINAL))
    assert all(
        not isinstance(event, CommandResolution) or event.intent is None
        for event in decisions
    )


def test_fragment_does_not_join_negation_or_new_command() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    coordinator.observe(update(0, "Open", TranscriptStatus.FINAL))
    assert coordinator.observe(
        update(1, "Do not open Telegram", TranscriptStatus.FINAL)
    ) == (CommandResolution(1, None),)
    coordinator.observe(update(2, "Open", TranscriptStatus.FINAL))
    assert coordinator.observe(update(3, "Close Telegram", TranscriptStatus.FINAL)) == (
        CommandResolution(
            3, CommandIntent(CommandKind.CLOSE_APP_WINDOW, "telegram")
        ),
    )


def test_window_fragment_discards_negated_or_confirming_continuation() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    coordinator.observe(update(0, "Minimize", TranscriptStatus.FINAL))
    decisions = coordinator.observe(
        update(1, "Do not minimize Telegram", TranscriptStatus.FINAL)
    )
    assert all(
        not isinstance(event, CommandResolution) or event.intent is None
        for event in decisions
    )
    coordinator.observe(update(2, "Minimize", TranscriptStatus.FINAL))
    decisions = coordinator.observe(update(3, "Yes", TranscriptStatus.FINAL))
    assert all(
        not isinstance(event, CommandResolution) or event.intent is None
        for event in decisions
    )


def test_a_complete_persian_window_command_supersedes_an_old_fragment() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    coordinator.observe(update(0, "Minimize", TranscriptStatus.FINAL))
    assert coordinator.observe(
        update(1, "تلگرام را از تمام صفحه خارج کن", TranscriptStatus.FINAL)
    ) == (
        CommandResolution(
            1, CommandIntent(CommandKind.UNFULLSCREEN_APP, "telegram")
        ),
    )


def test_fragment_allows_unreliable_language_labels_but_not_stream_restart() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    coordinator.observe(TranscriptUpdate(0, "Open", TranscriptStatus.FINAL, "ar"))
    assert coordinator.observe(
        TranscriptUpdate(1, "Telegram", TranscriptStatus.FINAL, "en")
    ) == (
        CommandResolution(
            1, CommandIntent(CommandKind.OPEN_APP, "telegram"), language="en"
        ),
    )
    coordinator.observe(TranscriptUpdate(2, "Open", TranscriptStatus.FINAL, "en"))
    coordinator.start_new_stream()
    decisions = coordinator.observe(
        TranscriptUpdate(0, "Telegram", TranscriptStatus.FINAL, "en")
    )
    assert all(
        not isinstance(event, CommandResolution) or event.intent is None
        for event in decisions
    )


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
            pending: PendingCommandClarification | None,
        ) -> Interpretation:
            self.seen = (text, language, context)
            return ReadyCommand(CommandIntent(CommandKind.OPEN_APP, "calculator"))

    interpreter = AlternateInterpreter()
    coordinator = CommandCoordinator(interpreter)
    assert coordinator.observe(
        TranscriptUpdate(0, "calculadora", TranscriptStatus.FINAL, language="es"),
        observed_active_app="telegram",
    ) == (
        CommandResolution(
            0, CommandIntent(CommandKind.OPEN_APP, "calculator"), language="es"
        ),
    )
    assert interpreter.seen == (
        "calculadora",
        "es",
        CommandContext(observed_active_app="telegram"),
    )


def test_each_final_event_keeps_its_own_transcript_language() -> None:
    coordinator = CommandCoordinator(DemoCommandInterpreter())
    english_events = coordinator.observe(
        TranscriptUpdate(0, "open chat Ali", TranscriptStatus.FINAL, "en")
    )
    assert english_events == (
        CommandResolution(0, None, language="en"),
        ResponseRequest(
            0,
            ResponseKind.CHOOSE_CHAT_APP,
            ResponseChannel.TEXT_AND_VOICE,
            target="ali",
            language="en",
        ),
    )
    persian_events = coordinator.observe(
        TranscriptUpdate(1, "تلگرام", TranscriptStatus.FINAL, "fa")
    )
    assert persian_events == (
        CommandResolution(
            1, CommandIntent(CommandKind.OPEN_CHAT, "ali", "telegram"), language="fa"
        ),
    )
