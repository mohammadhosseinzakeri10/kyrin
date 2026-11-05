"""Menu replies retain context without authorizing a tab in an unknown window."""

from dataclasses import replace
from unittest.mock import Mock

import pytest

from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.interpreter import ReadyCommand
from kyrin.commands.model_interpreter import ModelAssistedInterpreter
from kyrin.commands.models import (
    CommandContext,
    CommandIntent,
    CommandKind,
    CommandResolution,
    PendingOperationClarification,
    ResponseKind,
    ResponseRequest,
)
from kyrin.commands.recovery_candidates import PhoneticCandidateGenerator
from kyrin.commands.speech_recovery import (
    SpeechCommandRecovery,
    SpeechRecoveryInterpreter,
)
from kyrin.stt.audio_recovery import AudioRecoveryPolicy, RetainedAudio
from kyrin.stt.evidence import SpeechEvidence, SpeechHypothesis
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from scripts.commands.evaluate_l04_baseline import fixture


def final(index: int, text: str) -> TranscriptUpdate:
    return TranscriptUpdate(index, text, TranscriptStatus.FINAL, "en")


def menu(count: int) -> tuple[CommandCoordinator, Mock]:
    names, rules = fixture(count)
    model = Mock()
    model.understand.side_effect = AssertionError("explicit menu reply needs no model")
    recovery = SpeechCommandRecovery(
        PhoneticCandidateGenerator(
            names,
            allowed_apps=frozenset({"terminal"}),
            chat_apps=frozenset(),
            phonemize=lambda value: value,
        ),
        rules,
    )
    base = ModelAssistedInterpreter(
        rules,
        model,
        names,
        allowed_apps=frozenset({"terminal"}),
        supported_chat_apps=frozenset(),
        action_review=rules.review_model_action,
        recovery_review=recovery.review,
    )
    return CommandCoordinator(SpeechRecoveryInterpreter(base, recovery)), model


def selected(events: object) -> CommandIntent | None:
    assert isinstance(events, tuple) and isinstance(events[0], CommandResolution)
    return events[0].intent


@pytest.mark.parametrize("count", [1, 2])
@pytest.mark.parametrize("reply", ["Preference.", "Preferences."])
def test_preferences_singular_and_plural_are_exact_scoped_menu_replies(
    count: int,
    reply: str,
) -> None:
    owner, model = menu(count)
    owner.observe(final(0, "Open Terminal"))
    assert selected(owner.observe(final(1, reply))) == CommandIntent(
        CommandKind.APP_PREFERENCES, "terminal"
    )
    model.understand.assert_not_called()


@pytest.mark.parametrize("next_reply", ["New window", "Preferences"])
def test_multiwindow_tab_is_not_guessed_and_agreeing_audio_keeps_menu(
    next_reply: str,
) -> None:
    owner, model = menu(2)
    owner.observe(final(0, "Open Terminal"))
    pending = owner.pending_clarification
    assert isinstance(pending, PendingOperationClarification)
    assert CommandKind.NEW_APP_TAB not in pending.options
    audio = RetainedAudio(
        b"\x01\x00" * 8,
        lambda pcm: SpeechHypothesis("new tab", "test", "same_audio_reprocess"),
        AudioRecoveryPolicy(),
    )
    result = owner.observe(replace(final(1, "New tab."), retained_audio=audio))
    assert selected(result) is None
    assert owner.pending_clarification == pending
    assert any(
        isinstance(e, ResponseRequest) and e.kind is ResponseKind.CHOOSE_OPERATION
        for e in result
    )
    assert audio.retained_bytes == 0
    assert selected(owner.observe(final(2, next_reply))) == CommandIntent(
        CommandKind.NEW_APP_WINDOW
        if next_reply == "New window"
        else CommandKind.APP_PREFERENCES,
        "terminal",
    )
    model.understand.assert_not_called()


def test_one_window_tab_is_still_explicit_and_executable() -> None:
    owner, model = menu(1)
    owner.observe(final(0, "Open Terminal"))
    assert selected(owner.observe(final(1, "New tab"))) == CommandIntent(
        CommandKind.NEW_APP_TAB, "terminal"
    )
    model.understand.assert_not_called()


def test_real_action_conflict_is_not_treated_as_menu_agreement() -> None:
    owner, model = menu(2)
    owner.observe(final(0, "Open Terminal"))
    update = replace(
        final(1, "New tab"),
        evidence=SpeechEvidence("test", (SpeechHypothesis("New window", "test"),)),
    )
    assert selected(owner.observe(update)) is None
    assert owner.pending_clarification is None
    model.understand.assert_not_called()


@pytest.mark.parametrize("text", ["Preference", "Preferences"])
def test_preference_without_menu_cannot_use_stale_app_context(text: str) -> None:
    _, rules = fixture(1)
    assert not isinstance(
        rules.interpret(
            text,
            language="en",
            context=CommandContext(last_referenced_app="terminal"),
            pending=None,
        ),
        ReadyCommand,
    )


@pytest.mark.parametrize("reply", ["Do not open preferences", "Cancel"])
def test_negative_menu_reply_has_no_action_or_retained_question(reply: str) -> None:
    owner, model = menu(1)
    owner.observe(final(0, "Open Terminal"))
    assert selected(owner.observe(final(1, reply))) is None
    assert owner.pending_clarification is None
    model.understand.assert_not_called()


def test_cancelled_menu_does_not_survive_as_a_partial_preview() -> None:
    owner, _ = menu(1)
    owner.observe(final(0, "Open Terminal"))
    partial = owner.observe(
        TranscriptUpdate(1, "Preference", TranscriptStatus.PARTIAL, "en")
    )
    assert not any(isinstance(e, CommandResolution) for e in partial)
    owner.cancel_dialogue()
    assert owner.pending_clarification is None
