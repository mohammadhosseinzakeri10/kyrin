"""App focus can confirm an accepted launch without inventing completion."""

from collections.abc import Iterator

import pytest

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest, ActionResult
from kyrin.actions.observed_executor import ObservedAppExecutor
from kyrin.commands.models import CommandIntent, CommandKind, CommandResolution

REQUEST = ActionRequest(
    ActionKey(0, 0), CommandIntent(CommandKind.OPEN_APP, "telegram"), "en"
)
ACCEPTED = ActionResult(REQUEST.key, ActionOutcome.LAUNCH_ACCEPTED)


class FakeExecutor:
    def __init__(self, result: ActionResult) -> None:
        self.result = result
        self.calls: list[ActionRequest] = []

    def execute(self, request: ActionRequest) -> ActionResult:
        self.calls.append(request)
        return self.result


class FakeObserver:
    def __init__(self, observations: tuple[str | None, ...]) -> None:
        self._observations: Iterator[str | None] = iter(observations)
        self.calls = 0

    def observe_active_app(self) -> str | None:
        self.calls += 1
        return next(self._observations)


def test_matching_fresh_focus_confirms_active_app() -> None:
    launcher = FakeExecutor(ACCEPTED)
    observer = FakeObserver(("telegram",))

    result = ObservedAppExecutor(launcher, observer).execute(REQUEST)

    assert result == ActionResult(
        REQUEST.key, ActionOutcome.CONFIRMED, observed_active_app="telegram"
    )
    assert launcher.calls == [REQUEST]
    assert observer.calls == 1


def test_delayed_focus_can_confirm_without_blocking_indefinitely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits: list[float] = []
    monkeypatch.setattr("kyrin.actions.observed_executor.sleep", waits.append)
    observer = FakeObserver((None, "browser", "telegram"))

    result = ObservedAppExecutor(
        FakeExecutor(ACCEPTED), observer, attempts=3, retry_delay_s=0.1
    ).execute(REQUEST)

    assert result.outcome is ActionOutcome.CONFIRMED
    assert observer.calls == 3
    assert waits == [0.1, 0.1]


def test_missing_or_other_focus_keeps_launch_unverified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("kyrin.actions.observed_executor.sleep", lambda _: None)
    observer = FakeObserver(("browser", None, "browser"))

    result = ObservedAppExecutor(FakeExecutor(ACCEPTED), observer, attempts=3).execute(
        REQUEST
    )

    assert result is ACCEPTED
    assert observer.calls == 3


@pytest.mark.parametrize(
    "result",
    [
        ActionResult(REQUEST.key, ActionOutcome.FAILED, error_code="failed"),
        ActionResult(REQUEST.key, ActionOutcome.UNKNOWN, error_code="timeout"),
        ActionResult(REQUEST.key, ActionOutcome.CONFIRMED, "telegram"),
    ],
)
def test_other_outcomes_are_not_observed_or_changed(result: ActionResult) -> None:
    observer = FakeObserver(())
    assert (
        ObservedAppExecutor(FakeExecutor(result), observer).execute(REQUEST) is result
    )
    assert observer.calls == 0


def test_non_app_action_is_not_promoted() -> None:
    chat = ActionRequest(
        ActionKey(0, 1), CommandIntent(CommandKind.OPEN_CHAT, "Ali", "telegram")
    )
    accepted = ActionResult(chat.key, ActionOutcome.LAUNCH_ACCEPTED)
    observer = FakeObserver(())
    assert (
        ObservedAppExecutor(FakeExecutor(accepted), observer).execute(chat) is accepted
    )
    assert observer.calls == 0


def test_confirmed_focus_updates_gate_context() -> None:
    gate = ActionGate(ActionPolicy(allowed_apps=frozenset({"telegram"})))
    decision = gate.observe(CommandResolution(0, REQUEST.intent, language="en"))
    assert isinstance(decision, ActionRequest)
    result = ObservedAppExecutor(
        FakeExecutor(ACCEPTED), FakeObserver(("telegram",))
    ).execute(decision)

    feedback = gate.record_result(result)

    assert feedback.outcome is ActionOutcome.CONFIRMED
    assert feedback.observed_active_app == "telegram"
    assert gate.verified_context.active_app == "telegram"


def test_observation_limits_are_validated() -> None:
    observer = FakeObserver(())
    with pytest.raises(ValueError, match="attempts"):
        ObservedAppExecutor(FakeExecutor(ACCEPTED), observer, attempts=0)
    with pytest.raises(ValueError, match="retry_delay_s"):
        ObservedAppExecutor(FakeExecutor(ACCEPTED), observer, retry_delay_s=-1)
