"""Command placement evidence is independent of a requested device."""

import select
import socket
from collections.abc import Callable
from time import monotonic

import pytest

from kyrin.commands import ollama_device
from kyrin.commands.models import CommandContext
from kyrin.commands.ollama_device import (
    CleanupState,
    CommandDeviceReport,
    DeviceObservation,
    InferenceState,
    ModelPlacement,
    ModelPresence,
    parse_running_device,
)
from kyrin.commands.ollama_engine import CommandModelError, OllamaCommandEngine
from kyrin.commands.understanding import UnderstandingInput
from kyrin.model_resources import MemorySnapshot, ModelResources
from kyrin.operations import Operation, OperationStopped, activate
from kyrin.stt.device import DevicePreference

MODEL = "test:latest"
URL = "http://127.0.0.1:12345"


def row(vram: object = 5, total: object = 10, **fields: object) -> dict[str, object]:
    return {"name": MODEL, "model": MODEL, "size_vram": vram, "size": total, **fields}


def observation(vram: object = 5, total: object = 10) -> DeviceObservation:
    return parse_running_device({"models": [row(vram, total)]}, MODEL)


class Harness:
    def __init__(self) -> None:
        self.order: list[str] = []
        self.reports: list[CommandDeviceReport] = []
        self.seen_timeouts: list[float] = []
        self.evidence = observation()
        self.result: object = {
            "model": MODEL,
            "done": True,
            "prompt_eval_count": 10,
            "message": {"content": '{"route":"no_action","steps":[]}'},
        }
        self.probe_error: Exception | None = None
        self.inference_error: Exception | None = None
        self.cleanup_error = False
        self.cleanup_transport_error: Exception | None = None
        self.unload_result: object = {
            "model": MODEL,
            "done": True,
            "done_reason": "unload",
        }
        self.after_inference: Callable[[], None] = lambda: None

    def transport(self, url: str, payload: dict[str, object], timeout: float) -> object:
        assert url.startswith(URL)
        if payload.get("keep_alive") == 0:
            self.order.append("unload")
            if self.cleanup_transport_error is not None:
                raise self.cleanup_transport_error
            if self.cleanup_error:
                raise OSError("private content must not enter diagnostics")
            return self.unload_result
        self.order.append("infer")
        assert payload["keep_alive"] == "30s"
        if self.inference_error is not None:
            raise self.inference_error
        self.after_inference()
        return self.result

    def probe(self, url: str, model: str, timeout: float) -> DeviceObservation:
        assert (url, model) == (URL, MODEL)
        self.order.append("probe")
        self.seen_timeouts.append(timeout)
        if self.probe_error is not None:
            raise self.probe_error
        return self.evidence

    def engine(
        self, device: DevicePreference = DevicePreference.AUTO
    ) -> OllamaCommandEngine:
        return OllamaCommandEngine(
            URL,
            MODEL,
            device,
            transport=self.transport,
            device_probe=self.probe,
            on_device_report=self.reports.append,
            token_counter=lambda _: 10,
            resources=ModelResources(memory=lambda: MemorySnapshot()),
        )

    def run(self, device: DevicePreference = DevicePreference.AUTO) -> None:
        self.engine(device).understand(
            UnderstandingInput("hello", "en"), context=CommandContext()
        )


def test_auto_observes_after_inference_before_unload() -> None:
    h = Harness()
    h.run()
    assert h.order == ["infer", "probe", "unload"]
    assert [r.state for r in h.reports] == [
        InferenceState.RUNNING,
        InferenceState.COMPLETED,
    ]
    assert h.reports[-1].residency is ModelPresence.UNKNOWN
    assert h.reports[-1].observation.placement is ModelPlacement.MIXED


@pytest.mark.parametrize("value", [None, True, False, -1, "2", 1.5, [], {}])
def test_invalid_vram_is_not_device_evidence(value: object) -> None:
    assert observation(value).placement is ModelPlacement.UNKNOWN


@pytest.mark.parametrize("total", [None, True, False, -1, 0, "10", 1.5])
def test_invalid_total_is_not_device_evidence(total: object) -> None:
    assert observation(5, total).placement is ModelPlacement.UNKNOWN


@pytest.mark.parametrize(
    ("document", "presence"),
    [
        (None, ModelPresence.UNKNOWN),
        ([], ModelPresence.UNKNOWN),
        ({}, ModelPresence.UNKNOWN),
        ({"models": None}, ModelPresence.UNKNOWN),
        ({"models": [None]}, ModelPresence.UNKNOWN),
        ({"models": []}, ModelPresence.NOT_LOADED),
        ({"models": [row(name="other:latest")]}, ModelPresence.NOT_LOADED),
        ({"models": [row(name="test:latest-extra")]}, ModelPresence.NOT_LOADED),
        ({"models": [row(), row()]}, ModelPresence.UNKNOWN),
        ({"models": [row(model="other:latest")]}, ModelPresence.UNKNOWN),
    ],
)
def test_missing_invalid_or_ambiguous_identity(
    document: object, presence: ModelPresence
) -> None:
    result = parse_running_device(document, MODEL)
    assert result.placement is ModelPlacement.UNKNOWN
    assert result.presence is presence


def test_multiple_models_use_only_exact_selected_tag() -> None:
    result = parse_running_device(
        {"models": [row(10, name="other:latest"), row(0)]}, MODEL
    )
    assert result.placement is ModelPlacement.CPU


@pytest.mark.parametrize(
    ("vram", "expected"),
    [
        (0, ModelPlacement.UNKNOWN),
        (5, ModelPlacement.GPU_PARTICIPATION),
    ],
)
def test_missing_total_keeps_only_partial_evidence(
    vram: int, expected: ModelPlacement
) -> None:
    item = row(vram)
    del item["size"]
    assert parse_running_device({"models": [item]}, MODEL).placement is expected


def test_missing_vram_and_excess_vram_are_unknown() -> None:
    item = row()
    del item["size_vram"]
    assert (
        parse_running_device({"models": [item]}, MODEL).placement
        is ModelPlacement.UNKNOWN
    )
    assert observation(11).placement is ModelPlacement.UNKNOWN


@pytest.mark.parametrize("device", list(DevicePreference))
@pytest.mark.parametrize("placement", list(ModelPlacement))
def test_requested_device_policy(
    device: DevicePreference, placement: ModelPlacement
) -> None:
    h = Harness()
    h.evidence = DeviceObservation(placement, ModelPresence.LOADED)
    accepted = (
        device is DevicePreference.AUTO
        or device is DevicePreference.CPU
        and placement is ModelPlacement.CPU
        or device is DevicePreference.GPU
        and placement
        in {
            ModelPlacement.GPU,
            ModelPlacement.MIXED,
            ModelPlacement.GPU_PARTICIPATION,
        }
    )
    if accepted:
        h.run(device)
    else:
        with pytest.raises(CommandModelError, match="device"):
            h.run(device)
    report = h.reports[-1]
    assert report.requested is device
    assert report.observation is h.evidence
    assert report.state is (
        InferenceState.COMPLETED if accepted else InferenceState.FAILED
    )
    assert report.residency is ModelPresence.UNKNOWN


@pytest.mark.parametrize("error", [TimeoutError(), OSError(), ValueError()])
@pytest.mark.parametrize("device", list(DevicePreference))
def test_probe_failure_unknown_and_explicit_selection_fails(
    error: Exception, device: DevicePreference
) -> None:
    h = Harness()
    h.probe_error = error
    if device is DevicePreference.AUTO:
        h.run(device)
    else:
        with pytest.raises(CommandModelError, match="device"):
            h.run(device)
    assert h.reports[-1].observation.placement is ModelPlacement.UNKNOWN
    assert h.order[-1] == "unload"


def test_probe_uses_remaining_shared_deadline() -> None:
    h = Harness()
    with activate(Operation(monotonic() + 0.5)):
        h.run()
    assert 0 < h.seen_timeouts[0] <= 0.5


@pytest.mark.parametrize("stop_at", ["before_probe", "during_probe"])
def test_cancelled_observation_is_not_success_and_still_unloads(stop_at: str) -> None:
    h = Harness()
    operation = Operation(monotonic() + 5)
    if stop_at == "before_probe":
        h.after_inference = operation.cancel
    else:
        h.probe_error = OperationStopped("cancelled")
    with activate(operation), pytest.raises(OperationStopped):
        h.run()
    assert h.order[-1] == "unload"
    assert h.reports[-1].state is InferenceState.FAILED
    assert h.reports[-1].reason == "operation_stopped"


@pytest.mark.parametrize(
    "reply",
    [
        {"model": "other:latest", "done": True},
        {"model": MODEL, "done": False},
        {},
        None,
    ],
)
def test_unconfirmed_response_never_probes_old_resident_data(reply: object) -> None:
    h = Harness()
    h.result = reply
    with pytest.raises(CommandModelError):
        h.run(DevicePreference.GPU)
    assert "probe" not in h.order
    assert h.reports[-1].observation.placement is ModelPlacement.UNKNOWN


def test_new_attempt_does_not_reuse_previous_evidence() -> None:
    h = Harness()
    engine = h.engine()
    engine.understand(UnderstandingInput("hello", "en"), context=CommandContext())
    h.inference_error = TimeoutError("private message")
    with pytest.raises(CommandModelError):
        engine.understand(UnderstandingInput("hello", "en"), context=CommandContext())
    assert h.reports[-1].observation.placement is ModelPlacement.UNKNOWN
    assert "private" not in repr(h.reports)


def test_cleanup_failure_reports_unknown_residency_and_blocks_resources() -> None:
    h = Harness()
    h.cleanup_error = True
    engine = h.engine()
    with pytest.raises(CommandModelError, match="cleanup"):
        engine.understand(UnderstandingInput("hello", "en"), context=CommandContext())
    assert h.reports[-1].state is InferenceState.FAILED
    assert h.reports[-1].residency is ModelPresence.UNKNOWN
    assert h.reports[-1].reason == "cleanup_failed"
    h.order.clear()
    with pytest.raises(CommandModelError, match="resource"):
        engine.understand(UnderstandingInput("hello", "en"), context=CommandContext())
    assert not h.order


def test_packing_failure_does_not_report_a_fresh_inference() -> None:
    h = Harness()
    engine = OllamaCommandEngine(
        URL,
        MODEL,
        DevicePreference.AUTO,
        transport=h.transport,
        on_device_report=h.reports.append,
        token_counter=lambda _: 999999,
        resources=ModelResources(memory=lambda: MemorySnapshot()),
    )
    with pytest.raises(CommandModelError, match="budget"):
        engine.understand(UnderstandingInput("hello", "en"), context=CommandContext())
    assert not h.reports
    assert h.order == ["unload"]


def test_confirmation_and_conversational_reply_report_the_same_evidence() -> None:
    h = Harness()
    engine = h.engine()
    h.result = {
        "model": MODEL,
        "done": True,
        "prompt_eval_count": 10,
        "message": {"content": '{"decision":"yes","evidence":"oui"}'},
    }
    engine.classify_confirmation(UnderstandingInput("oui", "fr"), question="Open?")
    h.result = {
        "model": MODEL,
        "done": True,
        "prompt_eval_count": 10,
        "message": {"content": '{"route":"respond","steps":[],"reply":"Hello"}'},
    }
    engine.understand(UnderstandingInput("hello", "en"), context=CommandContext())
    assert h.order == ["infer", "probe", "unload"] * 2
    assert len(h.reports) == 4


def test_real_probe_is_bound_to_the_given_endpoint_and_does_not_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, float]] = []

    def get(url: str, timeout: float) -> object:
        calls.append((url, timeout))
        return {"models": [row(10)]}

    monkeypatch.setattr(ollama_device, "_get_running_models", get)
    assert ollama_device.running_device(URL, MODEL, 0.2).placement is ModelPlacement.GPU
    assert calls == [(URL, 0.2)]


class ProbeSocket:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.sent = b""
        self.closed = False
        self.connected: tuple[str, int] | None = None

    def __enter__(self) -> ProbeSocket:
        return self

    def __exit__(self, *args: object) -> None:
        self.closed = True

    def setblocking(self, value: bool) -> None:
        assert value is False

    def connect_ex(self, endpoint: tuple[str, int]) -> int:
        self.connected = endpoint
        return 0

    def getsockopt(self, *args: object) -> int:
        return 0

    def send(self, data: memoryview) -> int:
        self.sent += bytes(data)
        return len(data)

    def recv(self, size: int) -> bytes:
        result, self.response = self.response[:size], self.response[size:]
        return result


def install_socket(monkeypatch: pytest.MonkeyPatch, response: bytes) -> ProbeSocket:
    sock = ProbeSocket(response)
    monkeypatch.setattr(socket, "socket", lambda *args: sock)
    monkeypatch.setattr(
        select,
        "select",
        lambda reads, writes, errors, timeout: (reads, writes, []),
    )
    return sock


def test_probe_http_get_and_memory_response(monkeypatch: pytest.MonkeyPatch) -> None:
    body = b'{"models":[{"name":"test:latest","size":10,"size_vram":5}]}'
    sock = install_socket(
        monkeypatch,
        b"HTTP/1.1 200 OK\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\n\r\n"
        + body,
    )
    result = ollama_device.running_device(URL, MODEL, 1)
    assert result.placement is ModelPlacement.MIXED
    assert sock.connected == ("127.0.0.1", 12345)
    assert (
        sock.sent
        == b"GET /api/ps HTTP/1.1\r\nHost: 127.0.0.1:12345\r\nConnection: close\r\n\r\n"
    )
    assert sock.closed


def test_silent_probe_checks_cancel_and_closes_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sock = install_socket(monkeypatch, b"")
    operation = Operation(monotonic() + 10)

    def silent(
        reads: list[object], writes: list[object], errors: list[object], timeout: float
    ) -> tuple[list[object], list[object], list[object]]:
        assert timeout <= 0.05
        operation.cancel()
        return [], [], []

    monkeypatch.setattr(select, "select", silent)
    with activate(operation), pytest.raises(OperationStopped):
        ollama_device.running_device(URL, MODEL, 3)
    assert sock.closed
    assert sock.sent == b""


def test_trickling_probe_cannot_renew_absolute_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sock = install_socket(monkeypatch, b"HTTP/1.1 200 OK\r\n\r\n" + b" " * 100)
    now = [0.0]
    monkeypatch.setattr(ollama_device, "monotonic", lambda: now[0])

    def trickle(
        reads: list[object], writes: list[object], errors: list[object], timeout: float
    ) -> tuple[list[object], list[object], list[object]]:
        now[0] += 0.04
        return reads, writes, []

    monkeypatch.setattr(select, "select", trickle)
    with pytest.raises(TimeoutError):
        ollama_device.running_device(URL, MODEL, 0.1)
    assert sock.closed
    assert now[0] <= 0.15


@pytest.mark.parametrize(
    "response",
    [
        b"HTTP/1.1 500 Error\r\n\r\n{}",
        b"HTTP/1.1 200 OK\r\n\r\nnot-json",
        b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n{}",
    ],
)
def test_bad_http_does_not_become_cpu_evidence(
    monkeypatch: pytest.MonkeyPatch, response: bytes
) -> None:
    from http.client import HTTPException

    sock = install_socket(monkeypatch, response)
    with pytest.raises((ValueError, HTTPException)):
        ollama_device.running_device(URL, MODEL, 1)
    assert sock.closed


def test_raw_generation_observes_before_unload_without_second_inference() -> None:
    from kyrin.commands.token_budget import OllamaTokenCounter

    class RenderedCounter(OllamaTokenCounter):
        def __call__(self, payload: dict[str, object]) -> int:
            self.rendered_prompt = "already rendered"
            return 10

    order: list[str] = []
    reports: list[CommandDeviceReport] = []
    model = "qwen3.5:4b"

    def transport(url: str, payload: dict[str, object], timeout: float) -> object:
        assert url == URL + "/api/generate"
        if payload.get("keep_alive") == 0:
            order.append("unload")
            return {"model": payload["model"], "done": True, "done_reason": "unload"}
        order.append("generate")
        assert payload["raw"] is True and payload["prompt"] == "already rendered"
        return {
            "model": model,
            "done": True,
            "prompt_eval_count": 10,
            "response": '{"route":"no_action","steps":[]}',
        }

    def probe(url: str, selected: str, timeout: float) -> DeviceObservation:
        assert (url, selected) == (URL, model)
        order.append("probe")
        return observation(10)

    engine = OllamaCommandEngine(
        URL,
        model,
        DevicePreference.GPU,
        transport=transport,
        token_counter=RenderedCounter(URL, model, None, transport),
        device_probe=probe,
        on_device_report=reports.append,
        resources=ModelResources(memory=lambda: MemorySnapshot()),
    )
    engine.understand(UnderstandingInput("hello", "en"), context=CommandContext())
    assert order == ["generate", "probe", "unload"]
    assert reports[-1].observation.placement is ModelPlacement.GPU


@pytest.mark.parametrize(
    "document",
    [
        {"models": [{}]},
        {"models": [{"name": None}]},
        {"models": [{"name": True}]},
        {"models": [{"name": ""}]},
    ],
)
def test_invalid_names_do_not_prove_absence(document: object) -> None:
    assert parse_running_device(document, MODEL).presence is ModelPresence.UNKNOWN


def test_unload_acknowledgement_does_not_prove_memory_was_released() -> None:
    h = Harness()
    h.run()
    assert h.reports[-1].residency is ModelPresence.UNKNOWN
    assert h.reports[-1].cleanup is CleanupState.ACKNOWLEDGED


@pytest.mark.parametrize("identity", [None, "other:latest", True])
def test_unload_reply_must_identify_the_same_model(identity: object) -> None:
    h = Harness()
    h.unload_result = {"model": identity, "done": True, "done_reason": "unload"}
    with pytest.raises(CommandModelError, match="cleanup"):
        h.run()
    assert h.reports[-1].state is InferenceState.FAILED


@pytest.mark.parametrize(
    "fields",
    [
        {"model": "other:latest"},
        {"model": None},
        {"model": True},
        {"done": None},
        {"done": 0},
        {"done": 1},
        {"done": "true"},
    ],
)
def test_auto_rejects_invalid_completion_envelope(fields: dict[str, object]) -> None:
    h = Harness()
    assert isinstance(h.result, dict)
    h.result.update(fields)
    with pytest.raises(CommandModelError):
        h.run()
    assert "probe" not in h.order
    assert h.reports[-1].state is InferenceState.FAILED


def test_probe_rechecks_local_deadline_when_eof_becomes_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b'{"models":[]}'
    install_socket(monkeypatch, b"HTTP/1.1 200 OK\r\n\r\n" + body)
    now = [0.0]
    calls = [0]
    monkeypatch.setattr(ollama_device, "monotonic", lambda: now[0])

    def ready_after_deadline(
        reads: list[object], writes: list[object], errors: list[object], timeout: float
    ) -> tuple[list[object], list[object], list[object]]:
        calls[0] += 1
        if calls[0] == 4:
            now[0] = 2.0
        return reads, writes, []

    monkeypatch.setattr(select, "select", ready_after_deadline)
    with pytest.raises(TimeoutError):
        ollama_device.running_device(URL, MODEL, 1.0)


@pytest.mark.parametrize("field", ["model", "done"])
def test_missing_completion_identity_or_done_is_rejected(field: str) -> None:
    h = Harness()
    assert isinstance(h.result, dict)
    del h.result[field]
    with pytest.raises(CommandModelError):
        h.run()
    assert h.order == ["infer", "unload"]


def test_missing_unload_identity_is_not_acknowledged() -> None:
    h = Harness()
    h.unload_result = {"done": True, "done_reason": "unload"}
    with pytest.raises(CommandModelError, match="cleanup"):
        h.run()
    assert h.reports[-1].cleanup is CleanupState.UNCONFIRMED


def test_incomplete_http_cleanup_is_failed_and_blocks_further_admission() -> None:
    from http.client import IncompleteRead

    h = Harness()
    h.cleanup_transport_error = IncompleteRead(b"private response fragment", 10)
    engine = h.engine()
    with pytest.raises(CommandModelError, match="cleanup"):
        engine.understand(UnderstandingInput("hello", "en"), context=CommandContext())
    report = h.reports[-1]
    assert report.state is InferenceState.FAILED
    assert report.cleanup is CleanupState.UNCONFIRMED
    assert report.reason == "cleanup_failed"
    assert "private" not in repr(h.reports)
    h.order.clear()
    with pytest.raises(CommandModelError, match="resource"):
        engine.understand(UnderstandingInput("hello", "en"), context=CommandContext())
    assert not h.order


def test_incomplete_http_inference_is_a_controlled_failure_and_still_cleans_up() -> (
    None
):
    from http.client import IncompleteRead

    h = Harness()
    h.inference_error = IncompleteRead(b"private response fragment", 10)
    with pytest.raises(CommandModelError):
        h.run()
    assert h.order == ["infer", "unload"]
    assert h.reports[-1].state is InferenceState.FAILED
    assert h.reports[-1].cleanup is CleanupState.ACKNOWLEDGED
    assert "private" not in repr(h.reports)
