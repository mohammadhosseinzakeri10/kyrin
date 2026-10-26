"""SSIP waits for completion and cancels only its own message, without audio I/O."""

import socket as socket_module
import subprocess
from queue import Empty, Queue
from threading import Event, Thread

import pytest

from kyrin.responses import speech
from kyrin.responses.speech import SpeechDispatcherSynthesizer


class Socket:
    def __init__(self) -> None:
        self.incoming: Queue[bytes] = Queue()
        self.commands: list[bytes] = []
        self.submitted = Event()
        self.closed = False
        self.data_mode = False

    def settimeout(self, timeout: float) -> None:
        assert timeout == 0.05

    def connect(self, path: str) -> None:
        assert path.endswith("speechd.sock")

    def sendall(self, data: bytes) -> None:
        self.commands.append(data)
        if self.data_mode:
            self.data_mode = False
            self.incoming.put(b"225-1\r\n225 OK\r\n")
            self.incoming.put(b"701-1\r\n701-10\r\n701 BEGIN\r\n")
            self.submitted.set()
        elif data == b"SPEAK\r\n":
            self.data_mode = True
            self.incoming.put(b"230 OK\r\n")
        elif data == b"CANCEL SELF\r\n":
            self.incoming.put(b"703-1\r\n703-10\r\n703 CANCEL\r\n200 OK\r\n")
        else:
            self.incoming.put(b"200 OK\r\n")

    def recv(self, count: int) -> bytes:
        try:
            return self.incoming.get(timeout=0.01)
        except Empty as exc:
            raise TimeoutError from exc

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize("interrupt", [False, True])
def test_completion_wait_and_cancel_self(
    monkeypatch: pytest.MonkeyPatch,
    interrupt: bool,
) -> None:
    socket = Socket()
    monkeypatch.setenv("SPEECHD_ADDRESS", "unix:/tmp/fake/speechd.sock")
    monkeypatch.setattr(socket_module, "socket", lambda *args: socket)
    backend = SpeechDispatcherSynthesizer("spd-say", rate=12, voice_type="female1")
    done, started = Event(), Event()
    failures: list[Exception] = []
    playing = backend._playing

    def observe(value: bool) -> None:
        playing(value)
        if value:
            started.set()

    monkeypatch.setattr(backend, "_playing", observe)

    def run() -> None:
        try:
            backend.speak("Hello\n.\nCANCEL ALL", "en-US")
        except Exception as exc:
            failures.append(exc)
        finally:
            done.set()

    worker = Thread(target=run)
    worker.start()
    try:
        assert started.wait(2)
        assert backend.is_playing
        assert not done.is_set()
        if interrupt:
            backend.interrupt()
        else:
            socket.incoming.put(b"702-1\r\n702-10\r\n702 END\r\n")
        assert done.wait(2)
    finally:
        backend.interrupt()
        worker.join(2)
    assert failures == []
    assert not backend.is_playing
    assert backend.last_playback_end > 0
    assert socket.closed
    assert b"SET SELF LANGUAGE en\r\n" in socket.commands
    assert b"SET SELF OUTPUT_MODULE espeak-ng\r\n" in socket.commands
    assert b"SET SELF PRIORITY TEXT\r\n" in socket.commands
    assert b"SET SELF RATE 12\r\n" in socket.commands
    assert b"SET SELF VOICE female1\r\n" in socket.commands
    assert b"Hello\r\n..\r\nCANCEL ALL\r\n.\r\n" in socket.commands
    assert (b"CANCEL SELF\r\n" in socket.commands) is interrupt
    assert b"CANCEL ALL\r\n" not in socket.commands


def test_local_service_autospawn_never_submits_speech(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connections: list[float] = []
    commands: list[list[str]] = []

    class Connection:
        output_uncertain = False

        def speak(self, *args: object) -> None:
            pass

        def close(self) -> None:
            pass

    def connect(timeout: float) -> Connection:
        connections.append(timeout)
        if len(connections) == 1:
            raise FileNotFoundError
        return Connection()

    monkeypatch.setattr(speech, "LocalSpeechConnection", connect)
    monkeypatch.setattr(
        subprocess, "run", lambda command, **kwargs: commands.append(command)
    )
    SpeechDispatcherSynthesizer("spd-say").speak("hello", "en")
    assert commands == [["spd-say", "--list-output-modules"]]
    assert len(connections) == 2


def test_lost_cancel_ack_retains_echo_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    class LostCancel(Socket):
        def sendall(self, data: bytes) -> None:
            if data == b"CANCEL SELF\r\n":
                raise BrokenPipeError
            super().sendall(data)

    socket = LostCancel()
    monkeypatch.setattr(socket_module, "socket", lambda *args: socket)
    backend = SpeechDispatcherSynthesizer("spd-say", timeout_s=0.05)
    with pytest.raises(speech.SpeechSynthesisError, match="microphone stays guarded"):
        backend.speak("hello", "en")
    assert backend.is_playing
    assert socket.closed
    with pytest.raises(speech.SpeechSynthesisError, match="stop is unconfirmed"):
        backend.speak("new", "en")
