"""Local Ollama adapter that proposes command meaning, never an action."""

import json
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from kyrin.commands.models import CommandContext
from kyrin.commands.understanding import UnderstandingInput, UnderstandingResult
from kyrin.commands.understanding_json import decode_model_response
from kyrin.stt.device import DevicePreference


class CommandModelError(RuntimeError):
    """The local model is unavailable or returned an invalid proposal."""


_OPERATIONS = [
    "open_app",
    "open_chat",
    "restore_app",
    "minimize_app",
    "close_app_window",
    "maximize_app",
    "unmaximize_app",
    "fullscreen_app",
    "unfullscreen_app",
    "power_off_system",
    "restart_system",
    "log_out_system",
    "suspend_system",
]
_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "route": {
            "type": "string",
            "enum": ["execute", "clarify", "confirm", "no_action", "unsupported"],
        },
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": _OPERATIONS},
                    "target": {"type": "string"},
                    "app": {"type": "string"},
                    "polarity": {"type": "string", "enum": ["affirmative", "negated"]},
                },
                "required": ["operation"],
                "additionalProperties": False,
            },
        },
        "uncertainty": {"type": "string"},
    },
    "required": ["route", "steps"],
    "additionalProperties": False,
}
_SYSTEM = (
    "Interpret the user's command as JSON only. Do not execute actions. "
    "Allowed routes: execute, clarify, confirm, no_action, unsupported. "
    "Preserve negation. If the operation or target is uncertain, choose clarify. "
    "Never turn an application request into a computer power request. "
    "Only explicit requests about the computer may propose power operations. "
    "Unknown applications and chats require clarification. "
    "open_app means opening an application such as Telegram. "
    "open_chat is only for an explicit chat or conversation inside an app; "
    "never use open_chat for a request to open the app itself. "
    "Use the original spoken target, not an invented replacement. "
    "For app operations put the app in target; for open_chat put the chat in "
    "target and, when explicit, its application in app. "
    "For ordinary speech return no_action with empty steps. "
    "Return at most three ordered steps. The required keys are route and steps. "
    "The permitted step keys are operation, target, app, and polarity."
)


def _post_json(url: str, payload: dict[str, object], timeout: float) -> object:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _running_vram(url: str, model: str) -> int | None:
    with urlopen(f"{url}/api/ps", timeout=3) as response:
        document = json.load(response)
    for item in document.get("models", []):
        if isinstance(item, dict) and item.get("name") == model:
            size = item.get("size_vram")
            return size if isinstance(size, int) else None
    return None


class OllamaCommandEngine:
    """Use an owned loopback server and a selected installed model tag."""

    def __init__(
        self,
        base_url: str,
        model: str,
        device: DevicePreference,
        *,
        transport: Callable[[str, dict[str, object], float], object] = _post_json,
        device_probe: Callable[[str, str], int | None] = _running_vram,
    ) -> None:
        if not base_url.startswith("http://127.0.0.1:"):
            raise ValueError("command inference must use a loopback Ollama server")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._device = device
        self._transport = transport
        self._device_probe = device_probe

    def understand(
        self, utterance: UnderstandingInput, *, context: CommandContext
    ) -> UnderstandingResult:
        options: dict[str, object] = {
            "temperature": 0,
            "num_ctx": 4096,
            "num_predict": 768,
        }
        if self._device is DevicePreference.CPU:
            options["num_gpu"] = 0
        elif self._device is DevicePreference.GPU:
            options["num_gpu"] = 999
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "text": utterance.text,
                            "language_hint": utterance.language,
                            "context": {
                                "observed_active_app": context.observed_active_app
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "format": _SCHEMA,
            "stream": False,
            "think": False,
            "options": options,
            "keep_alive": "5m",
        }
        timeout = 120.0 if self._device is DevicePreference.CPU else 60.0
        try:
            result = self._transport(f"{self._base_url}/api/chat", payload, timeout)
            if self._device is not DevicePreference.AUTO:
                vram = self._device_probe(self._base_url, self._model)
                if vram is None or (self._device is DevicePreference.GPU) != (vram > 0):
                    raise CommandModelError(
                        "selected command compute device was not used"
                    )
            if not isinstance(result, dict):
                raise ValueError("model reply is not an object")
            message = result.get("message")
            if not isinstance(message, dict) or not isinstance(
                content := message.get("content"), str
            ):
                raise ValueError("model reply has no text")
            decoded: Any = json.loads(content)
            return decode_model_response(decoded)
        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            ValueError,
            TypeError,
        ) as exc:
            raise CommandModelError(
                "local command model failed or returned invalid JSON"
            ) from exc
