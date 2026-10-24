"""Measure repeated live commands with saved models and an inert executor.

Say "Open Telegram" after LISTENING_READY. No application is opened and no
audio or transcript is written. The saved settings file is only read.
"""

import argparse
import json
from dataclasses import asdict, replace
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
from kyrin.timing import TimingEvent


class InertExecutor:
    def execute(self, request: ActionRequest) -> ActionResult:
        return ActionResult(
            request.key, ActionOutcome.UNKNOWN, error_code="safe_measurement_only"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument(
        "--temperature",
        choices=("cold", "warm", "unknown"),
        default="unknown",
        help="Operator-controlled experiment condition; never inferred from run order",
    )
    args = parser.parse_args()
    if not 20 <= args.samples <= 512:
        parser.error("--samples must be between 20 and 512")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
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
        allow_desktop_scroll=False,
        allow_desktop_control=False,
        allowed_apps=telegram,
        allowed_chat_apps=(),
        allowed_window_apps=(),
        allowed_close_apps=(),
    )
    completed = Event()
    latency = SpeechActionLatency()
    sample_count = 0
    result: dict[str, object] = {"executor": "inert; no application opened"}
    activity_events = 0
    session_ends = 0

    def on_event(event: object) -> None:
        nonlocal activity_events, session_ends, sample_count
        if isinstance(event, SpeechActivityFrame):
            activity_events += 1
        elif isinstance(event, SpeechSessionEnded):
            session_ends += 1
        if isinstance(event, TimingEvent):
            event = replace(event, temperature=args.temperature)
        sample = latency.observe(event)
        if (
            isinstance(event, TranscriptUpdate)
            and event.status is TranscriptStatus.FINAL
        ):
            print("FINAL_TRANSCRIPT_RECEIVED", flush=True)
        if sample is not None:
            sample_count += 1
            print(json.dumps({"sample": asdict(sample)}), flush=True)
            if sample_count >= args.samples:
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

                def stop_after_samples() -> None:
                    completed.wait(args.timeout_seconds)
                    runtime.stop()

                Thread(target=stop_after_samples, daemon=True).start()
                print(
                    f"LISTENING_READY: Say Open Telegram {args.samples} times, "
                    "waiting for each result.",
                    flush=True,
                )
                runtime.run()
    result["samples"] = sample_count
    result["summaries"] = [asdict(summary) for summary in latency.summaries()]
    result["activity_transitions"] = activity_events
    result["session_ends"] = session_ends
    if not completed.is_set():
        result["error"] = "requested sample count not reached"
    print(json.dumps(result))
    return 0 if completed.is_set() else 1


if __name__ == "__main__":
    raise SystemExit(main())
