"""Power requests stay inert until two independent, current confirmations."""

from threading import Event
from time import monotonic, sleep

from kyrin.system_power.flow import (
    PowerAction,
    PowerPrompt,
    PowerStage,
    SystemPowerFlow,
    recognized_power_request,
)


class FakeBackend:
    def __init__(self) -> None:
        self.actions: list[PowerAction] = []
        self.done = Event()

    def work_warning(self, action: PowerAction) -> str:
        return "GNOME reports one session blocker."

    def request(self, action: PowerAction) -> None:
        self.actions.append(action)
        self.done.set()


def _wait_for(events: list[PowerPrompt], stage: PowerStage) -> PowerPrompt:
    deadline = monotonic() + 2
    while monotonic() < deadline:
        matching = [event for event in events if event.stage is stage]
        if matching:
            return matching[-1]
        sleep(0.01)
    raise AssertionError(f"missing {stage} prompt")


def test_restart_requires_explicit_computer_scope() -> None:
    events: list[PowerPrompt] = []
    flow = SystemPowerFlow(FakeBackend(), events.append, enabled=False)

    for phrase in (
        "Restart",
        "KYRIN, please restart",
        "Restart Telegram",
        "Restart the browser",
        "تلگرام را دوباره راه‌اندازی کن",
        "ریستارت کن",
    ):
        assert not flow.on_final_speech(phrase)
    assert events == []

    for phrase in (
        "Restart this computer",
        "Reboot this machine",
        "این رایانه را دوباره راه‌اندازی کن",
    ):
        assert flow.on_final_speech(phrase)
        assert events[-1].action is PowerAction.RESTART
        assert events[-1].stage is PowerStage.FAILED
    assert recognized_power_request("Restart Telegram") is None


def test_voice_and_click_share_two_step_flow() -> None:
    backend = FakeBackend()
    events: list[PowerPrompt] = []
    flow = SystemPowerFlow(backend, events.append, enabled=True)
    assert flow.on_final_speech("KYRIN, power off")
    first = _wait_for(events, PowerStage.FIRST)
    assert flow.is_current_prompt(first)
    assert "cannot verify unsaved" in first.text
    assert backend.actions == []
    assert flow.on_final_speech("Yes")
    second = _wait_for(events, PowerStage.SECOND)
    assert not flow.is_current_prompt(first)
    assert flow.is_current_prompt(second)
    assert second.phrase == "Power off"
    assert second.speech_text == (
        "Final confirmation. Say exactly Power off, or click the matching "
        "button. You can still cancel."
    )
    assert not flow.respond(first.request_id + 1, second.phrase)
    assert flow.on_final_speech("Restart this computer")
    assert backend.actions == []
    assert flow.respond(second.request_id, second.phrase)
    assert backend.done.wait(2)
    assert not flow.is_current_prompt(second)
    assert backend.actions == [PowerAction.POWER_OFF]


def test_spoken_continue_advances_only_first_power_stage() -> None:
    backend = FakeBackend()
    events: list[PowerPrompt] = []
    flow = SystemPowerFlow(backend, events.append, enabled=True)
    assert flow.on_final_speech("Restart this computer")
    first = _wait_for(events, PowerStage.FIRST)
    assert "Say Yes or Continue" in first.text
    assert flow.on_final_speech("Continue")
    second = _wait_for(events, PowerStage.SECOND)
    assert second.phrase == "Restart computer"
    assert backend.actions == []
    assert flow.on_final_speech("Restart computer")
    assert backend.done.wait(2)
    assert backend.actions == [PowerAction.RESTART]


def test_safe_preview_uses_only_inert_backend_even_when_real_actions_disabled() -> None:
    real_backend = FakeBackend()
    preview_backend = FakeBackend()
    events: list[PowerPrompt] = []
    flow = SystemPowerFlow(
        real_backend,
        events.append,
        enabled=False,
        preview_backend=preview_backend,
    )
    assert flow.start_preview(PowerAction.POWER_OFF)
    first = _wait_for(events, PowerStage.FIRST)
    assert first.preview
    assert flow.on_final_speech("Yes")
    second = _wait_for(events, PowerStage.SECOND)
    assert second.preview
    assert flow.on_final_speech("Power off")
    assert preview_backend.done.wait(2)
    assert real_backend.actions == []
    assert preview_backend.actions == [PowerAction.POWER_OFF]
    finished = _wait_for(events, PowerStage.FINISHED)
    assert "No operating-system request" in finished.text


def test_click_first_and_spoken_second_with_voice_guard() -> None:
    backend = FakeBackend()
    events: list[PowerPrompt] = []
    voice_ready = False
    flow = SystemPowerFlow(
        backend, events.append, enabled=True, voice_ready=lambda: voice_ready
    )
    assert flow.start(PowerAction.RESTART)
    first = _wait_for(events, PowerStage.FIRST)
    assert flow.respond(first.request_id, "continue")
    second = _wait_for(events, PowerStage.SECOND)
    assert second.phrase is not None
    assert flow.on_final_speech(second.phrase)
    assert not backend.done.is_set()
    voice_ready = True
    assert flow.on_final_speech(second.phrase)
    assert backend.done.wait(2)
    assert backend.actions == [PowerAction.RESTART]


def test_unclear_final_voice_never_confirms_or_changes_the_action() -> None:
    backend = FakeBackend()
    events: list[PowerPrompt] = []
    flow = SystemPowerFlow(backend, events.append, enabled=True)
    announcements: list[PowerPrompt] = []
    flow.set_announcement(announcements.append)
    assert flow.on_final_speech("Power off")
    first = _wait_for(events, PowerStage.FIRST)
    assert first.spoken and "Power off" in first.speech_text
    assert flow.on_final_speech("Yes")
    second = _wait_for(events, PowerStage.SECOND)
    assert second.phrase == "Power off"
    announcement_count = len(announcements)

    for unclear in ("Okay", "Restart computer", "Yes", "Power"):
        assert flow.on_final_speech(unclear)
        assert events[-1].stage is PowerStage.SECOND
        assert events[-1].request_id == second.request_id
        assert not events[-1].spoken
        assert len(announcements) == announcement_count
        assert backend.actions == []
    assert flow.on_final_speech("Power off")
    assert backend.done.wait(2)
    assert backend.actions == [PowerAction.POWER_OFF]


def test_each_short_challenge_only_confirms_its_own_action() -> None:
    phrases = {
        PowerAction.POWER_OFF: "Power off",
        PowerAction.RESTART: "Restart computer",
        PowerAction.LOG_OUT: "Log out",
        PowerAction.SUSPEND: "Suspend computer",
    }
    for action, phrase in phrases.items():
        backend = FakeBackend()
        events: list[PowerPrompt] = []
        flow = SystemPowerFlow(backend, events.append, enabled=True)
        assert flow.start(action)
        first = _wait_for(events, PowerStage.FIRST)
        assert flow.respond(first.request_id, "continue")
        second = _wait_for(events, PowerStage.SECOND)
        assert second.phrase == phrase
        assert flow.on_final_speech("Okay")
        assert backend.actions == []
        assert flow.on_final_speech(phrase)
        assert backend.done.wait(2)
        assert backend.actions == [action]


def test_permission_cancel_and_expiry_never_execute() -> None:
    backend = FakeBackend()
    events: list[PowerPrompt] = []
    now = 10.0
    flow = SystemPowerFlow(
        backend, events.append, enabled=False, clock=lambda: now, timeout_s=5
    )
    assert flow.on_final_speech("suspend")
    assert events[-1].stage is PowerStage.FAILED
    flow.configure(enabled=True)
    assert flow.start(PowerAction.SUSPEND)
    first = _wait_for(events, PowerStage.FIRST)
    assert flow.respond(first.request_id, "cancel")
    assert any(event.stage is PowerStage.CANCELLED for event in events)
    assert flow.start(PowerAction.LOG_OUT)
    deadline = monotonic() + 2
    while monotonic() < deadline and not any(
        event.stage is PowerStage.FIRST and event.action is PowerAction.LOG_OUT
        for event in events
    ):
        sleep(0.01)
    second_request = next(
        event
        for event in events
        if event.stage is PowerStage.FIRST and event.action is PowerAction.LOG_OUT
    )
    now = 16.0
    flow.expire()
    assert events[-1].stage is PowerStage.EXPIRED
    assert not flow.respond(second_request.request_id, "continue")
    assert backend.actions == []


def test_fresh_request_waits_for_running_backend() -> None:
    class SlowBackend(FakeBackend):
        def __init__(self) -> None:
            super().__init__()
            self.release = Event()

        def request(self, action: PowerAction) -> None:
            assert self.release.wait(2)
            super().request(action)

    backend = SlowBackend()
    events: list[PowerPrompt] = []
    flow = SystemPowerFlow(backend, events.append, enabled=True)
    assert flow.start(PowerAction.SUSPEND)
    first = _wait_for(events, PowerStage.FIRST)
    assert flow.respond(first.request_id, "continue")
    second = _wait_for(events, PowerStage.SECOND)
    assert flow.respond(second.request_id, second.phrase or "")
    assert not flow.start(PowerAction.POWER_OFF)
    backend.release.set()
    assert backend.done.wait(2)
