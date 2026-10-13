"""Own an isolated, offline Ollama process for one KYRIN listening session."""

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from kyrin.commands.ollama_engine import CommandModelError
from kyrin.commands.ollama_models import ollama_model_stores


def _unused_loopback_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class LocalOllamaServer:
    """A private model store and loopback endpoint; no shared daemon changes."""

    def __init__(self, store: Path, model: str) -> None:
        self._store = store
        self._model = model
        self._process: subprocess.Popen[bytes] | None = None
        self.base_url: str | None = None

    def __enter__(self) -> str:
        binary = shutil.which("ollama")
        if binary is None:
            raise CommandModelError("Ollama is not installed")
        selected_store = ollama_model_stores(self._store).get(self._model)
        if selected_store is None:
            raise CommandModelError("selected command model is not in the local store")
        port = _unused_loopback_port()
        url = f"http://127.0.0.1:{port}"
        environment = os.environ.copy()
        environment.update(
            {
                "OLLAMA_MODELS": str(selected_store),
                "OLLAMA_HOST": f"127.0.0.1:{port}",
                "OLLAMA_NO_CLOUD": "1",
            }
        )
        try:
            self._process = subprocess.Popen(
                [binary, "serve"],
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if self._process.poll() is not None:
                    raise CommandModelError("local Ollama server exited during startup")
                try:
                    with urlopen(f"{url}/api/tags", timeout=0.5) as response:
                        document = json.load(response)
                except URLError, TimeoutError, OSError, ValueError:
                    time.sleep(0.1)
                    continue
                names = {
                    item.get("name")
                    for item in document.get("models", [])
                    if isinstance(item, dict)
                }
                if self._model not in names:
                    raise CommandModelError(
                        "selected command model is not in the local store"
                    )
                self.base_url = url
                return url
            raise CommandModelError("local Ollama server did not become ready")
        except (OSError, ValueError) as exc:
            self.__exit__(None, None, None)
            raise CommandModelError("local Ollama server could not start") from exc
        except CommandModelError:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_exc: object) -> None:
        process = self._process
        self._process = None
        self.base_url = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
