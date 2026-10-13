"""Measure one live command with saved local models and an inert executor.

Say "Open Telegram" after LISTENING_READY. No application is opened and no
audio or transcript is written. The saved settings file is only read.
"""

import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from unittest.mock import patch

from kyrin.actions.models import ActionOutcome, ActionRequest, ActionResult
from kyrin.app.platforms.ubuntu import UbuntuSessionFactory, standard_stt_openers
from kyrin.app.qt.main import _whisper_server_path
from kyrin.app.settings_store import JsonSettingsStore, linux_settings_path
from kyrin.audio.activity.speech_activity_monitor import SpeechActivityFrame
from kyrin.runtime.latency import SpeechActionLatency
from kyrin.runtime.speech_sessions import SpeechSessionEnded
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


class InertExecutor:
    def execute(self, request: ActionRequest) -> ActionResult:
        return ActionResult(
            request.key, ActionOutcome.UNKNOWN, error_code="safe_measurement_only"
        )


def main() -> int:
    saved = JsonSettingsStore(linux_settings_path()).load()
    if saved.stt is None:
        raise RuntimeError("Select a speech model in KYRIN before measuring")
    telegram = tuple(app for app in saved.allowed_apps if app.app_id == "telegram")
    if not telegram:
        raise RuntimeError("Telegram must be allowed in Desktop Actions")
    settings = replace(
        saved,
        listening_enabled=True,
        action_execution_enabled=True,
        system_power_enabled=False,
        allowed_apps=telegram,
        allowed_chat_apps=(),
        allowed_window_apps=(),
        allowed_close_apps=(),
    )
    completed = Event()
    latency = SpeechActionLatency()
    result: dict[str, object] = {}
    activity_events = 0
    session_ends = 0

    def on_event(event: object) -> None:
        nonlocal activity_events, session_ends
        if isinstance(event, SpeechActivityFrame):
            activity_events += 1
        elif isinstance(event, SpeechSessionEnded):
            session_ends += 1
        sample = latency.observe(event)
        if (
            isinstance(event, TranscriptUpdate)
            and event.status is TranscriptStatus.FINAL
        ):
            print("FINAL_TRANSCRIPT_RECEIVED", flush=True)
        if sample is not None:
            result.update(
                {
                    "speech_to_final_ms": sample.speech_to_final_ms,
                    "final_to_result_ms": sample.final_to_result_ms,
                    "speech_to_result_ms": sample.speech_to_result_ms,
                    "executor": "inert; no application opened",
                }
            )
            completed.set()

    factory = UbuntuSessionFactory(
        stt_openers=standard_stt_openers(
            whisper_server_path=_whisper_server_path(
                "KYRIN_WHISPER_SERVER", "whisper-server"
            ),
            whisper_gpu_server_path=_whisper_server_path(
                "KYRIN_WHISPER_GPU_SERVER", "whisper-server-gpu"
            ),
        ),
        on_event=on_event,
        executor_factory=lambda _apps: InertExecutor(),
    )
    data_root = Path(__file__).resolve().parents[2] / "local-data"
    with TemporaryDirectory(prefix="latency-", dir=data_root) as directory:
        temporary_history = Path(directory) / "conversation.sqlite3"
        with patch(
            "kyrin.app.platforms.ubuntu.default_history_path",
            return_value=temporary_history,
        ):
            with factory(settings) as runtime:
                def stop_after_one_command() -> None:
                    completed.wait(90)
                    runtime.stop()

                Thread(target=stop_after_one_command, daemon=True).start()
                print("LISTENING_READY: Say Open Telegram once.", flush=True)
                runtime.run()
    result["activity_transitions"] = activity_events
    result["session_ends"] = session_ends
    if not completed.is_set():
        result["error"] = "no action result"
    print(json.dumps(result))
    return 0 if completed.is_set() else 1


if __name__ == "__main__":
    raise SystemExit(main())
