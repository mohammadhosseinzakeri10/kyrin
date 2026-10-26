"""Resource admission uses fake models/memory, never hardware or weights."""

from threading import Event, Thread

import pytest

from kyrin.model_resources import (
    MemorySnapshot,
    ModelResources,
    PeakMemory,
    ResourceLimits,
    ResourceUnavailable,
    Workload,
)


def test_priority_bounded_backpressure_and_nonpreemptive_owner() -> None:
    resources = ModelResources(
        ResourceLimits(max_waiters=2), memory=lambda: MemorySnapshot()
    )
    order: list[Workload] = []
    threads: list[Thread] = []

    def run(workload: Workload) -> None:
        with resources.use(workload):
            order.append(workload)

    with resources.use(Workload.OCR):
        for workload in (Workload.TTS, Workload.COMMAND):
            thread = Thread(target=run, args=(workload,))
            thread.start()
            threads.append(thread)
            assert resources.wait_for_waiters(len(threads), timeout=1)
        with pytest.raises(ResourceUnavailable, match="full"):
            with resources.use(Workload.OCR):
                pytest.fail("overload must not run a model")
        # A reserved admission slot keeps STT independent of a full background queue.
        thread = Thread(target=run, args=(Workload.STT,))
        thread.start()
        threads.append(thread)
        assert resources.wait_for_waiters(3, timeout=1)
        assert order == []
    for thread in threads:
        thread.join(2)
        assert not thread.is_alive()
    assert order == [Workload.STT, Workload.COMMAND, Workload.TTS]


def test_measured_peak_includes_resident_stt_and_fails_before_load() -> None:
    resources = ModelResources(
        ResourceLimits(ram_bytes=100, vram_bytes=80, ram_headroom_bytes=0),
        peaks={"stt": PeakMemory(30, 40, 20, 30), "tts": PeakMemory(80, 60)},
        memory=lambda: MemorySnapshot(100, 80),
    )
    with resources.use(Workload.STT, "stt", keep_resident=True):
        pass
    with pytest.raises(ResourceUnavailable, match="budget"):
        with resources.use(Workload.TTS, "tts"):
            pytest.fail("measured peak plus resident model exceeds budget")
    resources.forget("stt")
    with resources.use(Workload.TTS, "tts"):
        pass


def test_unknown_peak_is_not_weight_size_and_explicit_cap_fails_closed() -> None:
    resources = ModelResources(
        ResourceLimits(vram_bytes=100), memory=lambda: MemorySnapshot()
    )
    with pytest.raises(ResourceUnavailable, match="unknown"):
        with resources.use(Workload.COMMAND, "unknown-model"):
            pytest.fail("unknown peak must not be treated as zero")


def test_free_memory_rechecked_after_wait_and_failure_releases_owner() -> None:
    free = [100]
    resources = ModelResources(
        ResourceLimits(ram_headroom_bytes=10),
        peaks={"ocr": PeakMemory(70, 0)},
        memory=lambda: MemorySnapshot(free[0], None),
    )
    with resources.use(Workload.STT):
        free[0] = 50
    with pytest.raises(ResourceUnavailable, match="memory"):
        with resources.use(Workload.OCR, "ocr"):
            pytest.fail("no model load on insufficient free RAM")
    free[0] = 100
    with pytest.raises(MemoryError):
        with resources.use(Workload.OCR, "ocr"):
            raise MemoryError("fake OOM")
    with resources.use(Workload.STT):
        pass


def test_cancelled_waiter_never_loads_and_does_not_leak_capacity() -> None:
    resources = ModelResources(memory=lambda: MemorySnapshot())
    cancelled, finished = Event(), Event()
    calls: list[str] = []

    def wait() -> None:
        try:
            with resources.use(Workload.OCR, cancelled=cancelled.is_set):
                calls.append("loaded")
        except ResourceUnavailable:
            finished.set()

    with resources.use(Workload.STT):
        thread = Thread(target=wait)
        thread.start()
        assert resources.wait_for_waiters(1, timeout=1)
        cancelled.set()
        assert finished.wait(1)
    thread.join(1)
    assert calls == []
    with resources.use(Workload.OCR):
        pass


def test_wait_deadline_and_operation_cancellation_preserve_capacity() -> None:
    from kyrin.operations import Operation, OperationStopped, activate

    now = [0.0]
    resources = ModelResources(memory=lambda: MemorySnapshot(), clock=lambda: now[0])
    done = Event()
    errors: list[Exception] = []

    def wait() -> None:
        try:
            with resources.use(Workload.TTS):
                pytest.fail("expired waiter loaded")
        except ResourceUnavailable as exc:
            errors.append(exc)
        finally:
            done.set()

    with resources.use(Workload.STT):
        thread = Thread(target=wait)
        thread.start()
        assert resources.wait_for_waiters(1, timeout=1)
        now[0] = 6.0
        assert done.wait(1)
    thread.join(1)
    assert len(errors) == 1
    operation = Operation(100, clock=lambda: now[0])
    operation.cancel()
    with activate(operation), pytest.raises(OperationStopped):
        with resources.use(Workload.OCR):
            pytest.fail("cancelled operation loaded")
    with resources.use(Workload.OCR):
        pass


def test_resource_wait_and_run_reuse_content_free_timing_scope() -> None:
    from kyrin.actions.models import ActionKey
    from kyrin.timing import TimingEvent, TimingScope, timing_scope

    events: list[TimingEvent] = []
    resources = ModelResources(memory=lambda: MemorySnapshot())
    with timing_scope(TimingScope("session", ActionKey(1, 2), events.append)):
        with resources.use(Workload.COMMAND):
            pass
    assert [event.stage for event in events] == [
        "model_resource_wait_started",
        "model_resource_wait_finished",
        "model_resource_run_started",
        "model_resource_run_finished",
    ]
    assert all(event.session_id == "session" for event in events)
