"""Short local microphone diagnostic for KYRIN's live audio pipelines.

Run ``python scripts/audio/check_live_speech.py --help`` for options. This tool
prints events and never records audio or executes recognized commands.
"""

import argparse
import sys
from pathlib import Path
from threading import Timer
from time import monotonic

import numpy as np
import sounddevice as sd  # type: ignore[import-untyped]

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import ActionDecision, ActionNotice, ActionRequest
from kyrin.audio.activity.silero_vad import SileroVad
from kyrin.audio.activity.speech_activity_monitor import SpeechActivityFrame
from kyrin.audio.audio_backlog import BacklogNotice
from kyrin.audio.audio_errors import AudioError
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.continuous_audio_pipeline import ContinuousAudioPipeline
from kyrin.audio.live_speech_pipeline import LiveSpeechEvent, LiveSpeechPipeline
from kyrin.audio.microphone.input import MicrophoneInput
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import (
    CommandCandidateUpdate,
    CommandEvent,
    CommandResolution,
    ResponseRequest,
)
from kyrin.stt.backends.vosk import VoskEngine
from kyrin.stt.errors import SpeechToTextError
from kyrin.stt.transcript import TranscriptUpdate


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("vad", "stt", "commands"), default="stt")
    parser.add_argument(
        "--device", type=int, help="input device ID; default input if absent"
    )
    parser.add_argument(
        "--sample-rate", type=int, help="source rate; device default if absent"
    )
    parser.add_argument("--chunk-ms", type=int, default=20)
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--model-path", type=Path, help="local Vosk model directory")
    parser.add_argument("--language", help="language code of the supplied model")
    args = parser.parse_args(argv)
    if not 0 < args.seconds <= 120:
        parser.error("--seconds must be greater than 0 and at most 120")
    if args.chunk_ms <= 0:
        parser.error("--chunk-ms must be positive")
    if args.sample_rate is not None and args.sample_rate <= 0:
        parser.error("--sample-rate must be positive")
    if args.mode != "vad" and (args.model_path is None or not args.language):
        parser.error("STT and commands modes require --model-path and --language")
    return args


def microphone_settings(args: argparse.Namespace) -> tuple[int, AudioFormat, int]:
    device = args.device
    if device is None:
        device = int(sd.default.device[0])
    if device < 0:
        raise ValueError("no default microphone is configured; pass --device")
    details = sd.query_devices(device, "input")
    sample_rate = args.sample_rate or int(round(details["default_samplerate"]))
    sd.check_input_settings(
        device=device, channels=1, dtype="int16", samplerate=sample_rate
    )
    frames_per_chunk = max(1, round(sample_rate * args.chunk_ms / 1000))
    return (
        device,
        AudioFormat(sample_rate, 1, AudioSampleFormat.INT16),
        frames_per_chunk,
    )


def print_live_event(event: LiveSpeechEvent, elapsed_s: float) -> None:
    prefix = f"[{elapsed_s:7.2f}s]"
    if isinstance(event, SpeechActivityFrame):
        transition = event.transition
        if transition is not None:
            print(f"{prefix} speech {transition.value}", flush=True)
    elif isinstance(event, TranscriptUpdate):
        print(
            f"{prefix} {event.status.value} #{event.segment_id}: "
            f"{event.text or '<empty>'}",
            flush=True,
        )
    elif isinstance(event, BacklogNotice):
        print(
            f"{prefix} backlog {event.state.value} ({event.pending_ms} ms)",
            flush=True,
        )


def print_command_event(event: CommandEvent, elapsed_s: float) -> None:
    prefix = f"[{elapsed_s:7.2f}s] command {event.stream_id}:{event.segment_id}"
    if isinstance(event, ResponseRequest):
        print(f"{prefix} response [{event.channel.value}]: {event.text}", flush=True)
        return
    if isinstance(event, CommandCandidateUpdate):
        label = "candidate" if event.intent is not None else "candidate retracted"
    elif isinstance(event, CommandResolution):
        label = "final decision" if event.intent is not None else "no command"
    if event.intent is None:
        print(f"{prefix} {label}", flush=True)
        return
    intent = event.intent
    app = f", app={intent.app}" if intent.app is not None else ""
    print(
        f"{prefix} {label}: {intent.kind.value} target={intent.target}{app}",
        flush=True,
    )


def print_action_decision(decision: ActionDecision, elapsed_s: float) -> None:
    prefix = (
        f"[{elapsed_s:7.2f}s] action {decision.key.stream_id}:{decision.key.segment_id}"
    )
    if isinstance(decision, ActionNotice):
        print(f"{prefix} blocked: {decision.reason.value}", flush=True)
    elif isinstance(decision, ActionRequest):
        app = f", app={decision.intent.app}" if decision.intent.app is not None else ""
        print(
            f"{prefix} authorized dry-run request: {decision.intent.kind.value} "
            f"target={decision.intent.target}{app} (not executed)",
            flush=True,
        )


def run(args: argparse.Namespace) -> None:
    device, audio_format, frames_per_chunk = microphone_settings(args)
    source = MicrophoneInput(device, audio_format, frames_per_chunk)
    detector = SileroVad()
    print(
        f"Microphone {device}, {audio_format.sample_rate} Hz, "
        f"{frames_per_chunk} frames/chunk, {args.seconds:g} seconds."
    )
    print("No audio is saved and no recognized command is executed.", flush=True)

    if args.mode == "vad":
        vad_pipeline = ContinuousAudioPipeline(source, audio_format, detector)
        with vad_pipeline.open() as stream:
            start = monotonic()
            timer = Timer(args.seconds, source.stop_capture)
            timer.start()
            windows = 0
            peak = 0
            try:
                for frame in stream:
                    windows += 1
                    samples = np.frombuffer(frame.audio.data, dtype=np.int16)
                    if samples.size:
                        peak = max(peak, int(np.max(np.abs(samples.astype(np.int32)))))
                    if frame.transition is not None:
                        print_live_event(frame, monotonic() - start)
            finally:
                timer.cancel()
        print(f"VAD windows: {windows}; peak PCM amplitude: {peak}")
        return

    assert args.model_path is not None
    assert args.language is not None
    coordinator = (
        CommandCoordinator(DemoCommandInterpreter())
        if args.mode == "commands"
        else None
    )
    gate = (
        ActionGate(
            ActionPolicy(
                allowed_apps=frozenset({"telegram", "browser"}),
                allowed_chat_apps=frozenset({"telegram"}),
            )
        )
        if coordinator is not None
        else None
    )
    if coordinator is not None:
        print(
            "Command and action-gate decisions are a limited dry run. "
            "Telegram and browser are allowlisted for inspection only; "
            "no application state is assumed, and no action or voice response "
            "is performed.",
            flush=True,
        )
    engine = VoskEngine(args.model_path, language=args.language)
    try:
        live_pipeline = LiveSpeechPipeline(source, audio_format, detector, engine)
        with live_pipeline.open() as stream:
            start = monotonic()
            timer = Timer(args.seconds, source.stop_capture)
            timer.start()
            try:
                for event in stream:
                    observed_at = monotonic()
                    print_live_event(event, observed_at - start)
                    if coordinator is not None and isinstance(event, TranscriptUpdate):
                        assert gate is not None
                        for decision in coordinator.observe(event):
                            print_command_event(decision, monotonic() - start)
                            action = gate.observe(decision)
                            if action is not None:
                                print_action_decision(action, monotonic() - start)
            finally:
                timer.cancel()
    finally:
        engine.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        run(args)
    except (AudioError, SpeechToTextError, ValueError, sd.PortAudioError) as exc:
        print(f"Diagnostic failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
