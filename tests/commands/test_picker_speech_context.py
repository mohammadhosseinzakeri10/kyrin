"""Keep a non-executable picker question across agreeing audio hypotheses."""

from collections.abc import Callable
from dataclasses import replace
from unittest.mock import Mock

import pytest

from kyrin.actions.models import ActionKey
from kyrin.app.permissions import PermissionPolicy
from kyrin.app.settings import AllowedApp, AppSettings
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.diagnostics import trace
from kyrin.commands.model_interpreter import ModelAssistedInterpreter
from kyrin.commands.models import (
    CommandIntent,
    CommandKind,
    CommandResolution,
    PendingNumberedCloseConfirmation,
    PendingWindowSelection,
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
from kyrin.timing import TimingEvent, TimingScope, timing_scope
from scripts.commands.evaluate_l04_baseline import fixture


def coordinator(
    *, action_authorizer: Callable[[CommandIntent], bool] | None = None,
    window_count: int = 2,
) -> tuple[CommandCoordinator, Mock]:
    names, rules = fixture(window_count)
    model = Mock()
    model.understand.side_effect = AssertionError("picker needs no model inference")
    recovery = SpeechCommandRecovery(
        PhoneticCandidateGenerator(
            names, allowed_apps=frozenset({"browser", "telegram", "school"}),
            chat_apps=frozenset(),
        ),
        rules,
    )
    base = ModelAssistedInterpreter(
        rules, model, names,
        allowed_apps=frozenset({"browser", "telegram", "school"}),
        supported_chat_apps=frozenset(),
        action_review=rules.review_model_action,
        recovery_review=recovery.review,
    )
    return CommandCoordinator(
        SpeechRecoveryInterpreter(base, recovery), action_authorizer=action_authorizer,
    ), model


def final(index: int, text: str) -> TranscriptUpdate:
    return TranscriptUpdate(index, text, TranscriptStatus.FINAL, "en")


def intent(events: object) -> CommandIntent | None:
    assert isinstance(events, tuple)
    result = events[0]
    assert isinstance(result, CommandResolution)
    return result.intent


@pytest.mark.parametrize("phrase", ["Close Number 1.", "Close First."])
@pytest.mark.parametrize("all_apps", [False, True])
@pytest.mark.parametrize("grant", ["none", "granular", "trust"])
def test_agreeing_audio_close_preserves_number_and_saved_authorization(
    phrase: str, all_apps: bool, grant: str,
) -> None:
    policy = PermissionPolicy(AppSettings(
        action_execution_enabled=grant != "none",
        trust_all_capabilities=grant == "trust",
        allowed_apps=(AllowedApp("browser", "browser.desktop"),)
        if grant == "granular" else (),
        allowed_window_apps=("browser",) if grant == "granular" else (),
        allowed_close_apps=("browser",) if grant == "granular" else (),
    ))
    owner, model = coordinator(action_authorizer=policy.allows_intent)
    owner.observe(final(
        0, "Show all open windows" if all_apps else "Show Browser windows",
    ))
    audio = RetainedAudio(
        b"\x01\x00" * 8,
        lambda pcm: SpeechHypothesis(
            "close number one", "test", "same_audio_reprocess",
        ),
        AudioRecoveryPolicy(),
    )
    events = owner.observe(replace(final(1, phrase), retained_audio=audio))
    if grant == "none":
        assert intent(events) is None
        assert isinstance(events[1], ResponseRequest)
        assert events[1].kind is ResponseKind.CONFIRM_NUMBERED_CLOSE
        assert isinstance(owner.pending_clarification, PendingNumberedCloseConfirmation)
        assert owner.pending_clarification.window_index == 1
        assert intent(owner.observe(final(2, "No"))) is None
        assert isinstance(owner.pending_clarification, PendingWindowSelection)
    else:
        assert intent(events) == CommandIntent(
            CommandKind.CLOSE_SHOWN_WINDOW, "desktop", window_index=1,
        )
        assert owner.pending_clarification is None
    assert audio.retained_bytes == 0
    model.understand.assert_not_called()


@pytest.mark.parametrize("alternative", [
    "Close number two", "Number one", "Cancel", "Do not close number one",
    "Close number 100", "unrecognized words",
])
def test_contrary_close_audio_cannot_use_saved_consent(alternative: str) -> None:
    policy = PermissionPolicy(AppSettings(
        action_execution_enabled=True, trust_all_capabilities=True,
    ))
    owner, model = coordinator(action_authorizer=policy.allows_intent)
    owner.observe(final(0, "Show Browser windows"))
    update = replace(final(1, "Close Number 1"), evidence=SpeechEvidence(
        "test", (SpeechHypothesis(alternative, "test"),),
    ))
    assert intent(owner.observe(update)) is None
    model.understand.assert_not_called()


@pytest.mark.parametrize("case", ["allowed", "denied", "conflict", "expired"])
def test_one_window_close_reports_rejection_boundary_without_changing_decision(
    case: str,
) -> None:
    policy = PermissionPolicy(AppSettings(
        action_execution_enabled=case != "denied", trust_all_capabilities=True,
    ))
    owner, model = coordinator(
        action_authorizer=policy.allows_intent, window_count=1,
    )
    for i, phrase in enumerate((
        "Show Browser windows", "Do not close number one", "Show Browser windows",
    )):
        owner.observe(final(i, phrase))
    update = final(3, "Close Number 1.")
    if case == "conflict":
        update = replace(update, evidence=SpeechEvidence(
            "test", (SpeechHypothesis("Cancel", "test"),),
        ))
    elif case == "expired":
        update = replace(update, emitted_ns=1)
    events: list[TimingEvent] = []
    with timing_scope(TimingScope("inert", ActionKey(0, 3), events.append)):
        result = owner.observe(update)
        trace("guard", "private transcript must not enter diagnostics")
    stages = {event.stage for event in events}
    assert "command_diagnostic_build_numbered_close_trace_v1" in stages
    assert "command_diagnostic_pending_PendingWindowSelection" in stages
    assert not any("private transcript" in stage for stage in stages)
    if case == "allowed":
        assert intent(result) == CommandIntent(
            CommandKind.CLOSE_SHOWN_WINDOW, "desktop", window_index=1,
        )
        assert "command_diagnostic_authorization_allowed" in stages
    else:
        assert intent(result) is None
        expected = {
            "denied": "command_diagnostic_authorization_denied",
            "conflict": "command_diagnostic_guard_hypothesis_conflict",
            "expired": "command_diagnostic_guard_operation_stopped",
        }[case]
        assert expected in stages
    model.understand.assert_not_called()


@pytest.mark.parametrize("app", ["Browser", "Telegram", "School"])
@pytest.mark.parametrize(
    ("reply", "number"),
    [("One.", 1), ("First.", 1), ("Number One.", 1), ("Number 1", 1),
     ("Two.", 2), ("Second.", 2), ("Number 2", 2), ("Cancel.", None)],
)
def test_filtered_picker_survives_agreeing_non_action_audio_reply(
    app: str, reply: str, number: int | None,
) -> None:
    owner, model = coordinator()
    owner.observe(final(0, "Show all open windows"))
    assert intent(owner.observe(final(1, app))) == CommandIntent(
        CommandKind.SHOW_APP_WINDOWS, app.casefold()
    )
    pending = owner.pending_clarification
    # Different punctuation/casing can result from actual same-audio reprocessing.
    # The hypothesis is designed here; it is not claimed as a captured owner WAV.
    audio = RetainedAudio(
        b"\x01\x00" * 8,
        lambda pcm: SpeechHypothesis(app.casefold(), "test", "same_audio_reprocess"),
        AudioRecoveryPolicy(),
    )
    repeated = owner.observe(replace(final(2, app + "."), retained_audio=audio))
    assert intent(repeated) is None
    assert owner.pending_clarification == pending
    assert isinstance(owner.pending_clarification, PendingWindowSelection)
    assert audio.retained_bytes == 0
    expected = CommandIntent(
        CommandKind.HIDE_APP_WINDOWS
        if number is None else CommandKind.SELECT_APP_WINDOW,
        "desktop", window_index=number,
    )
    assert intent(owner.observe(final(3, reply))) == expected
    assert owner.pending_clarification is None
    model.understand.assert_not_called()


@pytest.mark.parametrize("alternative", ["Two", "Cancel"])
def test_conflicting_audio_still_cannot_choose_a_number(alternative: str) -> None:
    owner, model = coordinator()
    owner.observe(final(0, "Show Browser windows"))
    update = replace(
        final(1, "One"),
        evidence=SpeechEvidence("test", (SpeechHypothesis(alternative, "test"),)),
    )
    assert intent(owner.observe(update)) is None
    model.understand.assert_not_called()


def test_agreeing_non_action_cannot_mask_another_executable_hypothesis() -> None:
    owner, model = coordinator()
    owner.observe(final(0, "Show Browser windows"))
    update = replace(
        final(1, "Browser."),
        evidence=SpeechEvidence("test", (
            SpeechHypothesis("browser", "test"),
            SpeechHypothesis("Number one", "test"),
        )),
    )
    assert intent(owner.observe(update)) is None
    assert owner.pending_clarification is None
    model.understand.assert_not_called()


def test_matching_number_hypotheses_still_select_the_shown_number() -> None:
    owner, model = coordinator()
    owner.observe(final(0, "Show Browser windows"))
    update = replace(
        final(1, "Number 2"),
        evidence=SpeechEvidence("test", (SpeechHypothesis("Second", "test"),)),
    )
    assert intent(owner.observe(update)) == CommandIntent(
        CommandKind.SELECT_APP_WINDOW, "desktop", window_index=2
    )
    model.understand.assert_not_called()


def test_partial_repeated_app_does_not_reprocess_or_advance_picker() -> None:
    owner, model = coordinator()
    owner.observe(final(0, "Show Browser windows"))
    pending = owner.pending_clarification
    reprocess = Mock(side_effect=AssertionError("partial cannot reprocess"))
    audio = RetainedAudio(b"\x01\x00" * 8, reprocess, AudioRecoveryPolicy())
    events = owner.observe(TranscriptUpdate(
        1, "Browser", TranscriptStatus.PARTIAL, "en", retained_audio=audio
    ))
    assert not any(isinstance(event, CommandResolution) for event in events)
    assert owner.pending_clarification == pending
    reprocess.assert_not_called()
    model.understand.assert_not_called()


def test_standby_drops_picker_question_before_later_number() -> None:
    owner, _ = coordinator()
    owner.observe(final(0, "Show Browser windows"))
    owner.cancel_dialogue()
    assert owner.pending_clarification is None
    # Use the rules to inspect no-context behavior without asking a mock model.
    _, rules = fixture(2)
    owner.interpreter = rules
    assert intent(owner.observe(final(1, "One"))) is None
