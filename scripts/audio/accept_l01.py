"""Owner-run bounded microphone acceptance; dry-run actions, no content recording.

Console: start, standby, off, tts, snapshot, quit; pass/ fail/ skip SCENARIO.
Do not tee terminal output: the JSON report is the content-free evidence.
"""

import argparse
import json
import logging
import os
import select
import subprocess
import sys
from collections import Counter, deque
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from time import monotonic
from uuid import uuid4

import kyrin
from kyrin.actions.models import ActionRequest
from kyrin.app.controller import ApplicationController, ApplicationState
from kyrin.app.events import (
    AudioCaptureReady,
    AudioDuplexChanged,
    CommandDeviceReported,
    SttDeviceReady,
)
from kyrin.app.model_library import linux_model_library_path
from kyrin.app.platforms.pipewire_aec import PipeWireEchoCancellation
from kyrin.app.platforms.ubuntu import UbuntuSessionFactory, standard_stt_openers
from kyrin.app.qt.main import _whisper_server_path
from kyrin.app.settings import AppSettings
from kyrin.app.settings_store import JsonSettingsStore, linux_settings_path
from kyrin.commands.models import ResponseChannel
from kyrin.model_resources import ModelResources
from kyrin.responses.presenter import PresentedResponse
from kyrin.responses.speech import ResponseSpeaker, SpeechSynthesisError
from kyrin.runtime.speech_sessions import SpeechSessionEnded
from kyrin.runtime.voice_control import VoiceMode, VoiceModeChanged
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate
from kyrin.system_power.flow import InertPowerBackend
from kyrin.timing import TimingEvent
from kyrin.tts.runtime import ConfiguredSpeechSynthesizer
from scripts.commands.evaluation_contract import fingerprint, source_snapshot

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = (
    "natural",
    "silence",
    "model_wait",
    "consecutive",
    "tts",
    "controls",
    "next_session",
    "disconnect",
)
CUES = (
    "start: say Start listening; ordinary conversation",
    "silence: pause, then speak immediately",
    "model_wait: request a short explanation; pause while waiting",
    "consecutive: two short requests, wait for each completion",
    "tts: type tts; try speech during playback; note AEC vs half duplex",
    "controls: say Stop listening, Start listening, Turn microphone off; type start",
)


def safe_settings(saved: AppSettings) -> AppSettings:
    """Ephemeral diagnostic settings: no permission setup or desktop executor."""
    return replace(
        saved,
        listening_enabled=True,
        history_enabled=False,
        action_execution_enabled=False,
        system_power_enabled=False,
        allow_desktop_scroll=False,
        allow_desktop_control=False,
        allowed_chat_apps=(),
        allowed_window_apps=(),
        allowed_close_apps=(),
    )


def memory_sample() -> dict[str, int]:
    """Own process only; native child/model occupancy is separately reported."""
    result = {}
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith(("VmRSS:", "VmHWM:", "Threads:")):
                key, value, *_ = line.split()
                result[key.rstrip(":")] = int(value)
    except OSError, ValueError:
        return {"unavailable": 1}
    return result


class ChildAudit:
    """Sample only descendants of this tool, without reading command lines."""

    def __init__(self) -> None:
        self.observed: dict[int, str] = {}
        self.truncated = False
        self.errors: Counter[str] = Counter()
        self.unverified: set[int] = set()

    @staticmethod
    def identity(pid: int) -> tuple[str, int, str] | None:
        try:
            fields = (
                (Path("/proc") / str(pid) / "stat")
                .read_text()
                .rpartition(")")[2]
                .split()
            )
            return fields[19], int(fields[21]) * os.sysconf("SC_PAGE_SIZE"), fields[0]
        except FileNotFoundError, ProcessLookupError:
            return None

    def sample(self) -> dict[str, object]:
        pending = [os.getpid()]
        seen: set[int] = set()
        rss = 0
        while pending:
            pid = pending.pop()
            try:
                tasks = list((Path("/proc") / str(pid) / "task").iterdir())
            except FileNotFoundError, ProcessLookupError:
                if pid == os.getpid():
                    self.errors["children_unavailable"] += 1
                continue
            except OSError:
                self.errors["children_unavailable"] += 1
                continue
            children: set[int] = set()
            for task in tasks:
                try:
                    children.update(
                        int(item) for item in (task / "children").read_text().split()
                    )
                except FileNotFoundError, ProcessLookupError:
                    continue  # An exited thread is an ordinary /proc race.
                except OSError, ValueError:
                    self.errors["children_unavailable"] += 1
            for child in children - seen:
                if (
                    len(self.observed) + len(self.unverified) >= 256
                    and child not in self.observed
                    and child not in self.unverified
                ):
                    self.truncated = True
                    continue
                seen.add(child)
                try:
                    observed = self.identity(child)
                except OSError, ValueError, IndexError:
                    self.errors["identity_unavailable"] += 1
                    self.unverified.add(child)
                    continue
                self.unverified.discard(child)
                if observed is not None:
                    self.observed[child] = observed[0]
                    rss += observed[1]
                    pending.append(child)
        return {
            "sampled_descendants": len(seen),
            "rss_bytes": rss,
            "audit_truncated": self.truncated,
            "errors": dict(self.errors),
            "unverified": len(self.unverified),
        }

    def remaining(self) -> list[int]:
        remaining = []
        for pid, start in self.observed.items():
            try:
                identity = self.identity(pid)
            except OSError, ValueError, IndexError:
                self.errors["identity_unavailable"] += 1
                self.unverified.add(pid)
                continue
            self.unverified.discard(pid)
            if identity is not None and identity[0] == start and identity[2] != "Z":
                remaining.append(pid)
        return remaining


class Evidence:
    def __init__(self) -> None:
        self.lock = Lock()
        self.counts: Counter[str] = Counter()
        self.records: deque[dict[str, object]] = deque(maxlen=256)
        self.transitions: deque[dict[str, object]] = deque(maxlen=1024)
        self.transition_count = 0
        self.started = monotonic()

    def record(self, kind: str, **values: object) -> None:
        with self.lock:
            self.counts[kind] += 1
            record = {"t_s": monotonic() - self.started, "kind": kind, **values}
            self.records.append(record)
            if kind in {
                "voice_mode",
                "speech_end",
                "explicit_control",
                "application_error",
                "tts_error",
                "duplex",
                "stt_device",
                "command_device",
                "capture_ready",
                "owner_scenario",
            }:
                self.transitions.append(record)
                self.transition_count += 1

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            return {
                "counts": dict(self.counts),
                "recent": list(self.records),
                "transitions": list(self.transitions),
                "transitions_dropped": self.transition_count - len(self.transitions),
            }

    def observe(self, event: object) -> None:
        if isinstance(event, AudioCaptureReady):
            self.record(
                "capture_ready", session=event.session_id, generation=event.generation
            )
        elif isinstance(event, TranscriptUpdate):
            if event.status is TranscriptStatus.FINAL:
                self.record("final", segment=event.segment_id)
        elif isinstance(event, TimingEvent):
            if event.stage in {
                "understanding_started",
                "understanding_finished",
                "model_resource_wait_started",
                "model_resource_wait_finished",
                "model_resource_run_started",
                "model_resource_run_finished",
            }:
                self.record(
                    event.stage,
                    session=event.session_id,
                    stream=event.key.stream_id,
                    segment=event.key.segment_id,
                )
        elif isinstance(event, SpeechSessionEnded):
            self.record(
                "speech_end",
                session=event.session_id,
                generation=event.generation,
                attempt=event.attempt,
                retry_delay_s=event.retry_delay_s,
                error=type(event.error).__name__ if event.error else None,
            )
        elif isinstance(event, SttDeviceReady):
            self.record("stt_device", device=event.device.value)
        elif isinstance(event, CommandDeviceReported):
            report = event.report
            self.record(
                "command_device",
                requested=report.requested.value,
                state=report.state.value,
                placement=report.observation.placement.value,
                cleanup=report.cleanup.value,
            )
        elif isinstance(event, AudioDuplexChanged):
            self.record("duplex", aec=event.echo_cancelled)
        elif isinstance(event, VoiceModeChanged):
            self.record(
                "voice_mode",
                mode=event.mode.value,
                previous=event.previous,
                source=event.source,
                reason=event.reason,
                session=event.session_id,
                generation=event.generation,
                revision=event.revision,
            )
        elif isinstance(event, SpeechSynthesisError):
            self.record("tts_error", error=type(event).__name__)
        elif isinstance(event, ActionRequest):
            self.record("dry_run_action")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--cycle-seconds", type=int, default=180)
    parser.add_argument("--duplex", choices=("auto", "guard"), default="auto")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 60 <= args.seconds <= 7200 or not 60 <= args.cycle_seconds <= 1800:
        parser.error("seconds: 60..7200; cycle-seconds: 60..1800")
    if not args.output.resolve().is_relative_to(ROOT / "local-data"):
        parser.error("output must be under local-data")
    if Path(kyrin.__file__).resolve() != ROOT / "src/kyrin/__init__.py":
        parser.error(
            "source provenance mismatch; set PYTHONPATH to this checkout's src and root"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Refuse overwrite before opening any microphone or speaker.
    with args.output.open("x") as output:
        output.write('{"status": "initializing"}\n')
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        return run(args)
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
        KeyboardInterrupt,
    ) as exc:
        args.output.write_text(
            json.dumps(
                {
                    "schema": "L01-live-v1",
                    "run_id": uuid4().hex,
                    "status": "tool_failed",
                    "error": type(exc).__name__,
                    "source_unchanged": False,
                    "cleanup_confirmed": False,
                    "scenarios": dict.fromkeys(SCENARIOS, "not_run"),
                }
            )
            + "\n"
        )
        return 1
    finally:
        logging.disable(previous_logging)


def run(args: argparse.Namespace) -> int:
    evidence = Evidence()
    initial = source_snapshot()
    saved = JsonSettingsStore(linux_settings_path()).load()
    settings = safe_settings(saved)
    resources = ModelResources()
    synthesizer = ConfiguredSpeechSynthesizer(
        saved.tts, saved.tts_languages, resources=resources
    )
    speaker = ResponseSpeaker(synthesizer, on_error=evidence.observe)
    speaker.set_enabled(saved.tts_enabled)
    controller: ApplicationController

    def event_sink(event: object) -> None:
        evidence.observe(event)
        if isinstance(event, AudioCaptureReady):
            print(f"CAPTURE_READY generation={event.generation}", flush=True)
        if isinstance(event, VoiceModeChanged) and event.mode is VoiceMode.OFF:
            controller.request_stop(source="voice", reason="explicit_microphone_off")

    try:
        factory = UbuntuSessionFactory(
            stt_openers=standard_stt_openers(
                whisper_server_path=_whisper_server_path(
                    "KYRIN_WHISPER_SERVER", "whisper-server"
                ),
                whisper_gpu_server_path=_whisper_server_path(
                    "KYRIN_WHISPER_GPU_SERVER", "whisper-server-gpu"
                ),
                omnilingual_python=linux_model_library_path().parents[1]
                / "runtimes/stt/omnilingual-asr/bin/python",
            ),
            on_event=event_sink,
            response_speaker=speaker,
            model_resources=resources,
            power_backend_factory=InertPowerBackend,
            echo_cancellation_factory=PipeWireEchoCancellation
            if args.duplex == "auto"
            else None,
            voice_standby=True,
        )
        controller = ApplicationController(factory, start_in_standby=True)
    except OSError, RuntimeError, ValueError, KeyboardInterrupt:
        try:
            speaker.interrupt()
            synthesizer.close()
        finally:
            speaker.close(timeout_s=5)
        raise
    samples: deque[dict[str, object]] = deque(maxlen=256)
    children = ChildAudit()
    outcomes = dict.fromkeys(SCENARIOS, "not_run")
    scenario_counts = {
        name: dict.fromkeys(("pass", "fail", "skip"), 0) for name in SCENARIOS
    }
    failure: str | None = None
    cleanup = False
    started = monotonic()
    last_sample = last_cue = -1
    last_error: Exception | None = None

    def observe_status() -> None:
        nonlocal last_error, failure
        error = controller.status().error
        if error is not None and error is not last_error:
            last_error = error
            failure = failure or type(error).__name__
            evidence.record("application_error", error=type(error).__name__)

    print(
        "L01-v3 owner test; dry-run desktop; no audio/text history. "
        "Commands: start standby off tts snapshot quit; pass/fail/skip SCENARIO.",
        flush=True,
    )
    try:
        controller.start(settings)
        while monotonic() - started < args.seconds:
            elapsed = monotonic() - started
            cue = int(elapsed / (args.cycle_seconds / len(CUES)))
            if cue != last_cue:
                last_cue = cue
                print(
                    f"CYCLE {int(elapsed // args.cycle_seconds) + 1}: "
                    f"{CUES[cue % len(CUES)]}",
                    flush=True,
                )
            if int(elapsed // 5) != last_sample:
                last_sample = int(elapsed // 5)
                observe_status()
                status = controller.status()
                print(
                    f"STATE {status.state.value} "
                    f"commands_active={controller.commands_active()}",
                    flush=True,
                )
                samples.append(
                    {
                        "t_s": elapsed,
                        "application_state": status.state.value,
                        "memory_kib_threads": memory_sample(),
                        "child_memory": children.sample(),
                        "diagnostics": controller.listening_diagnostics(),
                    }
                )
            readable, _, _ = select.select([sys.stdin], [], [], 0.25)
            if not readable:
                continue
            command = sys.stdin.readline()
            if not command:  # EOF is an explicit end, not a successful acceptance.
                break
            observe_status()  # Preserve an error before Start replaces the session.
            command = command.strip()
            if command in {"start", "standby", "off", "tts", "quit"}:
                evidence.record("explicit_control", control=command)
            if command == "quit":
                break
            if command == "start":
                if controller.status().state in {
                    ApplicationState.RUNNING,
                    ApplicationState.STARTING,
                }:
                    controller.set_commands_active(
                        True, source="gui", reason="explicit_control"
                    )
                elif controller.wait_until_stopped(0):
                    controller.start(settings, commands_active=True)
                else:
                    evidence.record(
                        "control_rejected", reason="previous_session_active"
                    )
            elif command == "standby":
                controller.set_commands_active(
                    False, source="gui", reason="explicit_control"
                )
            elif command == "off":
                controller.request_stop(source="gui", reason="explicit_microphone_off")
            elif command == "snapshot":
                samples.append(
                    {"t_s": elapsed, "diagnostics": controller.listening_diagnostics()}
                )
                print("SNAPSHOT_RECORDED", flush=True)
            elif command == "tts":
                evidence.record("synthetic_tts_requested", enabled=saved.tts_enabled)
                accepted = speaker.submit(
                    PresentedResponse(
                        None,
                        None,
                        "This is a local listening stability test. You can speak now.",
                        ResponseChannel.TEXT_AND_VOICE,
                        "en",
                    )
                )
                if not accepted:
                    evidence.record("tts_error", error="response_queue_rejected")
                    failure = failure or "tts_queue_rejected"
                    print("TTS_QUEUE_REJECTED", flush=True)
            else:
                parts = command.split()
                if (
                    len(parts) == 2
                    and parts[0] in {"pass", "fail", "skip"}
                    and parts[1] in outcomes
                ):
                    scenario_counts[parts[1]][parts[0]] += 1
                    if parts[0] == "fail" or outcomes[parts[1]] not in {"fail", "pass"}:
                        outcomes[parts[1]] = parts[0]
                    evidence.record(
                        "owner_scenario", scenario=parts[1], result=parts[0]
                    )
                else:
                    print("UNKNOWN_CONTROL (input discarded)", flush=True)
            observe_status()
    except (OSError, RuntimeError, ValueError, KeyboardInterrupt) as exc:
        failure = type(exc).__name__
    finally:
        test_seconds = monotonic() - started
        children.sample()
        pre_stop = controller.listening_diagnostics()
        controller.request_stop(source="acceptance", reason="bounded_run_end")
        cleanup = controller.wait_until_stopped(30)
        try:
            speaker.interrupt()
            released = synthesizer.close()
            speaker.close(timeout_s=5)
            cleanup = cleanup and released
        except (RuntimeError, OSError) as exc:
            cleanup = False
            failure = failure or type(exc).__name__
        observe_status()
        quiescent = resources.is_quiescent()
        remaining_children = children.remaining()
        cleanup = (
            cleanup
            and quiescent
            and not remaining_children
            and not children.errors
            and not children.unverified
            and not children.truncated
        )
        if not cleanup:
            failure = failure or "cleanup_unconfirmed"
        if "fail" in outcomes.values():
            failure = failure or "owner_scenario_failed"
        try:
            after = source_snapshot()
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            failure = failure or type(exc).__name__
            after = {"probe_error": type(exc).__name__, "stable_during_capture": False}
        report = {
            "schema": "L01-live-v1",
            "run_id": uuid4().hex,
            "ended_utc": datetime.now(UTC).isoformat(),
            "status": "live_evidence_pending_review",
            "error": failure,
            "planned_seconds": args.seconds,
            "cycle_seconds": args.cycle_seconds,
            "cycles_started": last_cue // len(CUES) + 1 if last_cue >= 0 else 0,
            "cycles_completed_by_time": int(test_seconds // args.cycle_seconds),
            "actual_seconds_including_cleanup": monotonic() - started,
            "actual_test_seconds": test_seconds,
            "source_before": initial,
            "source_after": after,
            "source_unchanged": (
                initial.get("stable_during_capture") is True
                and after.get("stable_during_capture") is True
                and initial == after
            ),
            "python": sys.version,
            "settings_sha256": fingerprint(
                json.loads(json.dumps(asdict(saved), default=str))
            ),
            "effective_settings_sha256": fingerprint(
                json.loads(json.dumps(asdict(settings), default=str))
            ),
            "stt": {
                "backend": saved.stt.backend,
                "model": saved.stt.model_path.name,
                "requested_device": saved.stt.device.value,
            }
            if saved.stt
            else None,
            "command_model": {
                "model": saved.command_model.model,
                "requested_device": saved.command_model.device.value,
            }
            if saved.command_model
            else None,
            "tts": {
                "backend": saved.tts.backend,
                "device": saved.tts.device.value,
                "model": saved.tts.model_path.name if saved.tts.model_path else None,
                "enabled": saved.tts_enabled,
            },
            "duplex_requested": args.duplex,
            "desktop": "dry_run_no_executor_no_portal",
            "history": False,
            "scenarios": outcomes,
            "scenario_counts": scenario_counts,
            "observations": evidence.snapshot(),
            "samples_recent_256": list(samples),
            "pre_stop": pre_stop,
            "final": controller.listening_diagnostics(),
            "resources_final": resources.snapshot(),
            "tts_final": speaker.snapshot(),
            "cleanup_confirmed": cleanup,
            "resource_admission_quiescent": quiescent,
            "sampled_owned_children": len(children.observed),
            "sampled_owned_children_remaining": remaining_children,
            "child_audit_errors": dict(children.errors),
            "child_audit_unverified": sorted(children.unverified),
            "child_audit_truncated": children.truncated,
            "pid": os.getpid(),
        }
        args.output.write_text(json.dumps(report, indent=2, default=str) + "\n")
        print(f"REPORT: {args.output}", flush=True)
    return int(failure is not None or not cleanup)


if __name__ == "__main__":
    raise SystemExit(main())
