"""The local whisper.cpp launcher must not silently claim GPU execution."""

import subprocess
from pathlib import Path

import pytest

from kyrin.stt.backends import whisper_server
from kyrin.stt.device import ComputeDevice
from kyrin.stt.errors import DeviceUnavailableError


class ExitedProcess:
    def poll(self) -> int:
        return 0


def test_server_flags_and_cuda_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "whisper-server"
    executable.write_bytes(b"binary")
    executable.chmod(0o700)
    model = tmp_path / "model.bin"
    model.write_bytes(b"model")
    launches: list[list[str]] = []
    startup_log = b"whisper_backend_init_gpu: using CUDA0 backend\n"

    def launch(arguments: list[str], **kwargs: object) -> ExitedProcess:
        nonlocal startup_log
        launches.append(arguments)
        stderr = kwargs["stderr"]
        if hasattr(stderr, "write"):
            stderr.write(startup_log)
        return ExitedProcess()

    monkeypatch.setattr(subprocess, "Popen", launch)
    monkeypatch.setattr(whisper_server, "_free_loopback_port", lambda: 12345)
    monkeypatch.setattr(
        whisper_server.WhisperCppServer, "_wait_ready", lambda self: None
    )

    cpu = whisper_server.WhisperCppServer(executable, model)
    cpu.close()
    assert "--no-gpu" in launches[0]

    gpu = whisper_server.WhisperCppServer(
        executable, model, compute_device=ComputeDevice.GPU
    )
    gpu.close()
    assert "--no-gpu" not in launches[1]

    startup_log = b"whisper_init_with_params_no_state: use gpu = 1\n"
    with pytest.raises(DeviceUnavailableError, match="CUDA backend"):
        whisper_server.WhisperCppServer(
            executable, model, compute_device=ComputeDevice.GPU
        )


def test_auto_response_keeps_original_text_and_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[tuple[str, str]] = []

    def infer(
        self: whisper_server.WhisperCppServer,
        pcm: bytes,
        language: str,
        response_format: str,
    ) -> dict[str, object]:
        requested.append((language, response_format))
        return {"text": " تلگرام را باز کن ", "language": "persian"}

    monkeypatch.setattr(whisper_server.WhisperCppServer, "_request_inference", infer)
    server = object.__new__(whisper_server.WhisperCppServer)
    assert server.transcribe_auto(b"pcm") == whisper_server.WhisperResult(
        "تلگرام را باز کن", "fa"
    )
    assert requested == [("auto", "verbose_json")]


def test_auto_response_uses_language_code_for_unlisted_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        whisper_server.WhisperCppServer,
        "_request_inference",
        lambda self, pcm, language, response_format: {
            "text": "bonjour",
            "language": "unknown-language-name",
            "language_probabilities": {"fr": 0.94, "en": 0.06},
        },
    )
    server = object.__new__(whisper_server.WhisperCppServer)
    assert server.transcribe_auto(b"pcm").language == "fr"


def test_whisper_request_includes_hints_only_when_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[bytes] = []

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def read(self) -> bytes:
            return b'{"text":"ok"}'

    class Client:
        def open(self, request: object, timeout: int) -> Response:
            assert timeout == 8
            requests.append(request.data)  # type: ignore[attr-defined]
            return Response()

    class Process:
        def poll(self) -> None:
            return None

    monkeypatch.setattr(whisper_server, "_HTTP", Client())
    server = object.__new__(whisper_server.WhisperCppServer)
    server._process = Process()  # type: ignore[assignment]
    server._port = 12345
    server.transcribe(bytes(320), "fa")
    server.transcribe(bytes(320), "fa", hints=("مرورگر", "تلگرام"))
    assert b'name="prompt"' not in requests[0]
    assert "مرورگر، تلگرام.".encode() in requests[1]
