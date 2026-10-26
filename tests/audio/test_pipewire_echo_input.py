"""Echo-cancelled capture has the same stop and PCM contract as microphone input."""

from collections.abc import Generator
from io import BytesIO

import pytest

from kyrin.audio.pipewire_echo_input import PipeWireEchoInput


class RecordProcess:
    def __init__(self) -> None:
        self.stdout = BytesIO(b"\x01\x02" * 320)
        self.terminated = False

    def poll(self) -> int | None:
        return 0 if self.terminated else None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: int) -> int:
        return 0


def test_echo_capture_yields_pcm_and_stops_record_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = RecordProcess()
    import subprocess

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    source = PipeWireEchoInput("kyrin-test-source", "pw-record")
    chunks = source.capture()
    chunk = next(chunks)
    assert chunk.audio_format.sample_rate == 16000
    assert chunk.data == b"\x01\x02" * 320
    source.stop_capture()
    assert isinstance(chunks, Generator)
    chunks.close()
    assert process.terminated
