"""Producer timing is attributed by session, stream, segment and step."""

from collections.abc import Generator
from dataclasses import asdict, replace

import pytest

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import ActionKey, ActionOutcome, ActionRequest, ActionResult
from kyrin.audio.live_speech_pipeline import LiveSpeechEvent
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import CommandKind
from kyrin.runtime.command_runtime import LiveCommandRuntime
from kyrin.runtime.latency import ActionLatency, SpeechActionLatency
from kyrin.runtime.speech_sessions import SpeechSessionEnded
from kyrin.stt.transcript import TranscriptStatus, TranscriptTiming, TranscriptUpdate
from kyrin.timing import TimingEvent, TimingScope, timed_stage, timing_scope


def stamp(
    stage: str,
    ms: int,
    *,
    session: str = "a",
    stream: int = 0,
    segment: int = 4,
    step: int = 0,
) -> TimingEvent:
    return TimingEvent(session, ActionKey(stream, segment, step), stage, ms * 1_000_000)


def test_speech_action_latency_uses_producer_times_without_speech_content() -> None:
    tracker = SpeechActionLatency()
    tracker.observe(stamp("capture", 1000))
    tracker.observe(stamp("speech_end", 1700))
    tracker.observe(stamp("final", 2000))
    tracker.observe(stamp("feedback", 2200))
    sample = tracker.observe(stamp("command_completed", 2250))
    assert sample is not None
    assert sample.speech_to_final_ms == 1000
    assert sample.speech_end_to_final_ms == 300
    assert sample.final_to_first_feedback_ms == 200
    assert sample.final_to_result_ms == 250
    assert sample.speech_to_result_ms == 1250
    assert tracker.observe(stamp("command_completed", 2400)) is None
    assert "text" not in repr(asdict(sample))


def test_late_previous_stream_cannot_consume_new_segment() -> None:
    tracker = SpeechActionLatency()
    tracker.observe(stamp("final", 100))
    tracker.observe(stamp("final", 500, stream=1))
    old = tracker.observe(stamp("command_completed", 600))
    current = tracker.observe(stamp("command_completed", 900, stream=1))
    assert old is not None and old.final_to_result_ms == 500
    assert current is not None and current.final_to_result_ms == 400
    assert old.key != current.key


def test_runtime_sessions_with_identical_action_keys_are_independent() -> None:
    tracker = SpeechActionLatency()
    tracker.observe(stamp("final", 100, session="old"))
    tracker.observe(stamp("final", 200, session="new"))
    old = tracker.observe(stamp("command_completed", 600, session="old"))
    new = tracker.observe(stamp("command_completed", 900, session="new"))
    assert old is not None and old.final_to_result_ms == 500
    assert new is not None and new.final_to_result_ms == 700
    assert old.session_id != new.session_id


def test_first_step_feedback_is_not_plan_completion() -> None:
    tracker = SpeechActionLatency()
    tracker.observe(stamp("final", 100))
    tracker.observe(stamp("dispatch_started", 200))
    tracker.observe(stamp("dispatch_finished", 300))
    assert tracker.observe(stamp("feedback", 300)) is None
    tracker.observe(stamp("dispatch_started", 400, step=1))
    tracker.observe(stamp("dispatch_finished", 800, step=1))
    assert tracker.observe(stamp("feedback", 800, step=1)) is None
    sample = tracker.observe(stamp("command_completed", 900))
    assert sample is not None
    assert sample.final_to_first_feedback_ms == 200
    assert sample.final_to_result_ms == 800
    assert [step.duration_ms("dispatch") for step in sample.steps] == [100, 400]


def test_repeated_inference_and_postcondition_have_separate_durations() -> None:
    tracker = SpeechActionLatency()
    for stage, ms in (
        ("final", 0),
        ("understanding_queued", 10),
        ("understanding_started", 30),
        ("inference_started", 40),
        ("inference_finished", 50),
        ("inference_started", 80),
        ("inference_finished", 100),
        ("action_queued", 120),
        ("action_started", 150),
        ("dispatch_started", 150),
        ("postcondition_started", 170),
        ("postcondition_finished", 210),
        ("dispatch_finished", 220),
    ):
        tracker.observe(stamp(stage, ms))
    sample = tracker.observe(stamp("command_completed", 230))
    assert sample is not None
    assert sample.understanding_queue_ms == 20
    assert sample.action_queue_ms == 30
    assert sample.steps[0].duration_ms("inference") == 30
    assert sample.steps[0].duration_ms("postcondition") == 40
    assert sample.steps[0].duration_ms("dispatch") == 70


def test_percentiles_require_twenty_samples_in_each_condition() -> None:
    tracker = SpeechActionLatency()
    for temperature, count in (("cold", 19), ("warm", 20), ("unknown", 1)):
        for index in range(count):
            for stage, ms in (("final", 0), ("command_completed", index + 1)):
                tracker.observe(
                    replace(
                        stamp(stage, ms, session=temperature, segment=index),
                        temperature=temperature,
                    )
                )
    summaries = {item.temperature: item for item in tracker.summaries()}
    assert summaries["cold"].count == 19
    assert summaries["cold"].p95_ms is None
    assert summaries["unknown"].p50_ms is None
    assert summaries["warm"].p50_ms == 10
    assert summaries["warm"].p95_ms == 19


def test_eviction_or_missing_final_never_produces_partial_metrics() -> None:
    tracker = SpeechActionLatency()
    tracker.observe(stamp("final", 0, segment=0))
    for segment in range(1, 17):
        tracker.observe(stamp("final", segment, segment=segment))
    assert tracker.observe(stamp("command_completed", 20, segment=0)) is None
    assert tracker.observe(stamp("command_completed", 20, session="missing")) is None
    tracker.observe(stamp("final", 0, session="overflow"))
    for _ in range(256):
        tracker.observe(stamp("inference_started", 1, session="overflow"))
    assert tracker.observe(stamp("command_completed", 20, session="overflow")) is None


def test_timing_scope_carries_injected_clock_and_restores_context() -> None:
    events: list[TimingEvent] = []
    clock = iter((100, 200))
    with timing_scope(
        TimingScope("session", ActionKey(1, 2), events.append, lambda: next(clock))
    ):
        with timed_stage("postcondition", key=ActionKey(1, 2, 3)):
            pass
    with timed_stage("dispatch"):
        pass
    assert [event.at_ns for event in events] == [100, 200]
    assert [event.key.step_index for event in events] == [3, 3]


@pytest.mark.parametrize(
    "second_outcome", [ActionOutcome.CONFIRMED, ActionOutcome.FAILED]
)
@pytest.mark.parametrize("ui_delay_ms", [0, 500])
def test_runtime_reports_actual_plan_end_after_both_step_boundaries(
    second_outcome: ActionOutcome,
    ui_delay_ms: int,
) -> None:
    class Clock:
        now = 2_000_000_000

        def __call__(self) -> int:
            return self.now

    clock = Clock()

    class Controller:
        def events(self) -> Generator[LiveSpeechEvent | SpeechSessionEnded]:
            yield TranscriptUpdate(
                4,
                "Open Telegram and open browser",
                TranscriptStatus.FINAL,
                "en",
                emitted_ns=2_000_000_000,
                timing=TranscriptTiming((("capture", 1_000_000_000),)),
            )

        def stop(self) -> None:
            pass

    class Executor:
        def execute(self, request: ActionRequest) -> ActionResult:
            clock.now += 250_000_000 if request.key.step_index == 0 else 750_000_000
            outcome = (
                ActionOutcome.CONFIRMED
                if request.key.step_index == 0
                else second_outcome
            )
            return ActionResult(
                request.key,
                outcome,
                error_code="test_failure" if outcome is ActionOutcome.FAILED else None,
            )

    tracker = SpeechActionLatency()
    samples: list[ActionLatency] = []
    events: list[TimingEvent] = []

    def observe(event: TimingEvent) -> None:
        events.append(event)
        sample = tracker.observe(event)
        if sample is not None:
            samples.append(sample)

    def show_live(event: LiveSpeechEvent) -> None:
        clock.now += ui_delay_ms * 1_000_000

    runtime = LiveCommandRuntime(
        Controller(),
        coordinator=CommandCoordinator(DemoCommandInterpreter()),
        gate=ActionGate(
            ActionPolicy(
                allowed_apps=frozenset({"telegram", "browser"}),
                supported_kinds=frozenset({CommandKind.OPEN_APP}),
            )
        ),
        observer=None,
        executor=Executor(),
        finite_source=True,
        on_live_event=show_live,
        on_command_event=lambda event: None,
        on_action_output=lambda event: None,
        on_session_end=lambda event: None,
        on_timing=observe,
        clock_ns=clock,
    )
    runtime.run()
    assert len(samples) == 1
    sample = samples[0]
    assert sample.route == "file/plan/rules"
    assert sample.final_to_first_feedback_ms == 250 + ui_delay_ms
    assert sample.final_to_result_ms == 1000 + ui_delay_ms
    assert sample.speech_to_result_ms == 2000 + ui_delay_ms
    assert [step.duration_ms("dispatch") for step in sample.steps] == [250, 750]
    assert {event.session_id for event in events} == {sample.session_id}
    assert "Open Telegram" not in repr(events)
