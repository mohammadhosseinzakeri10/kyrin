"""Resource release for KYRIN's private command-model server."""

import json
from pathlib import Path
from urllib.request import Request

import pytest

from kyrin.commands import ollama_server


def test_closing_private_server_unloads_model_before_termination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    request_data: list[Request] = []

    class FakeProcess:
        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            events.append("terminate")

        def wait(self, *, timeout: float) -> None:
            events.append("wait")

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def read(self) -> bytes:
            return b"{}"

        def __exit__(self, *_exc: object) -> None:
            return None

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        request_data.append(request)
        events.append("unload")
        return FakeResponse()

    monkeypatch.setattr(ollama_server, "urlopen", fake_urlopen)
    server = ollama_server.LocalOllamaServer(tmp_path, "command-model")
    server._process = FakeProcess()  # type: ignore[assignment]
    server.base_url = "http://127.0.0.1:12345"

    server.__exit__(None, None, None)

    assert events == ["unload", "terminate", "wait"]
    assert request_data[0].full_url == "http://127.0.0.1:12345/api/generate"
    assert request_data[0].get_method() == "POST"
    data = request_data[0].data
    assert isinstance(data, bytes)
    assert json.loads(data) == {
        "model": "command-model",
        "prompt": "",
        "keep_alive": 0,
        "stream": False,
    }
