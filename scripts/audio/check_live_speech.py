"""Short local microphone diagnostic for KYRIN's live audio pipelines.

Run ``python scripts/audio/check_live_speech.py --help`` for options. This tool
prints events and never records audio or executes recognized commands. In
commands mode it can speak responses through the local offline voice service.
"""

import argparse
import sys
from contextlib import closing
from pathlib import Path
from threading import Timer
from time import monotonic

import numpy as np

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import ActionDecision, ActionNotice, ActionRequest
from kyrin.audio.activity.silero_vad import SileroVad
from kyrin.audio.activity.speech_activity_monitor import SpeechActivityFrame
from kyrin.audio.audio_backlog import BacklogNotice
from kyrin.audio.audio_errors import AudioCaptureStopError, AudioError
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.continuous_audio_pipeline import ContinuousAudioPipeline
from kyrin.audio.live_speech_pipeline import LiveSpeechEvent, LiveSpeechPipeline
from kyrin.audio.microphone.errors import MicrophoneError
from kyrin.audio.playback_guard import PlaybackGuardInput
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import (
    CommandCandidateUpdate,
    CommandEvent,
    CommandKind,
    CommandPlanResolution,
    CommandResolution,
    ResponseChannel,
    ResponseRequest,
)
from kyrin.desktop.active_app import ActiveAppObserver
from kyrin.desktop.command_bridge import observe_command_update
from kyrin.desktop.platforms.gnome import GnomeShellActiveAppObserver
from kyrin.desktop.platforms.xdg import XdgDesktopAppCatalog
from kyrin.desktop.spoken_app_names import CatalogSpokenAppResolver
from kyrin.responses.models import SystemNotice, SystemNoticeKind
from kyrin.responses.presenter import PresentedResponse, ResponsePresenter
from kyrin.responses.speech import (
    ResponseSpeaker,
    SpeechDispatcherSynthesizer,
    SpeechSynthesisError,
)
from kyrin.responses.system_notices import (
    notice_for_backlog,
    notice_for_error,
)
from kyrin.runtime.speech_sessions import (
    SpeechRecoveryPolicy,
    SpeechSessionController,
    SpeechSessionEnded,
)
from kyrin.stt.backends.vosk import VoskEngine
from kyrin.stt.backends.whisper import WhisperEngine
from kyrin.stt.contracts import SpeechToTextEngine
from kyrin.stt.errors import SpeechToTextError
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


def _parse_app_bindings(
    values: list[str], parser: argparse.ArgumentParser, option: str
) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for value in values:
        desktop_id, separator, app_id = value.partition("=")
        if not separator or not desktop_id.strip() or not app_id.strip():
            parser.error(f"{option} must be DESKTOP_ID=KYRIN_APP_ID")
        if desktop_id in bindings:
            parser.error(f"duplicate {option} desktop ID: {desktop_id}")
        bindings[desktop_id] = app_id
    return bindings


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
    parser.add_argument(
        "--retries", type=int, default=2, help="STT/commands retry limit"
    )
    parser.add_argument(
        "--retry-delay", type=float, default=1.0, help="retry delay in seconds"
    )
    parser.add_argument("--stt-backend", choices=("vosk", "whisper"), default="vosk")
    parser.add_argument("--model-path", type=Path, help="local STT model path")
    parser.add_argument(
        "--whisper-server", type=Path, help="local whisper.cpp server executable"
    )
    parser.add_argument("--whisper-threads", type=int, default=4)
    parser.add_argument("--language", help="language code of the supplied model")
    parser.add_argument(
        "--response-language",
        help="preferred response language; defaults to the model language",
    )
    parser.add_argument(
        "--no-voice-responses",
        action="store_true",
        help="print responses without speaking them in commands mode",
    )
    parser.add_argument(
        "--active-app-binding",
        action="append",
        default=[],
        metavar="DESKTOP_ID=KYRIN_APP_ID",
        help="in commands mode, map an exact GNOME desktop ID to a KYRIN app ID",
    )
    parser.add_argument(
        "--spoken-app-binding",
        action="append",
        default=[],
        metavar="DESKTOP_ID=KYRIN_APP_ID",
        help="allow a registered app to be recognized by its display name",
    )
    parser.add_argument(
        "--spoken-app-alias",
        action="append",
        default=[],
        metavar="KYRIN_APP_ID=PHRASE",
        help="add a spoken name for a bound app; may be repeated",
    )
    args = parser.parse_args(argv)
    if not 0 < args.seconds <= 120:
        parser.error("--seconds must be greater than 0 and at most 120")
    if args.chunk_ms <= 0:
        parser.error("--chunk-ms must be positive")
    try:
        args.recovery_policy = SpeechRecoveryPolicy(args.retries, args.retry_delay)
    except ValueError as exc:
        parser.error(str(exc))
    if args.sample_rate is not None and args.sample_rate <= 0:
        parser.error("--sample-rate must be positive")
    if args.mode != "vad" and (args.model_path is None or not args.language):
        parser.error("STT and commands modes require --model-path and --language")
    if args.mode != "vad" and args.stt_backend == "whisper":
        if args.whisper_server is None:
            parser.error("Whisper requires --whisper-server")
        if args.whisper_threads <= 0:
            parser.error("--whisper-threads must be positive")
    if (
        args.active_app_binding or args.spoken_app_binding or args.spoken_app_alias
    ) and args.mode != "commands":
        parser.error("app bindings and aliases require --mode commands")
    args.active_app_bindings = _parse_app_bindings(
        args.active_app_binding, parser, "--active-app-binding"
    )
    args.spoken_app_bindings = _parse_app_bindings(
        args.spoken_app_binding, parser, "--spoken-app-binding"
    )
    aliases: dict[str, list[str]] = {}
    for value in args.spoken_app_alias:
        app_id, separator, phrase = value.partition("=")
        if not separator or not app_id.strip() or not phrase.strip():
            parser.error("--spoken-app-alias must be KYRIN_APP_ID=PHRASE")
        if app_id not in args.spoken_app_bindings.values():
            parser.error("--spoken-app-alias requires a matching --spoken-app-binding")
        aliases.setdefault(app_id, []).append(phrase)
    args.spoken_app_aliases = aliases
    return args


def microphone_settings(args: argparse.Namespace) -> tuple[int, AudioFormat, int]:
    try:
        import sounddevice as sd  # type: ignore[import-untyped]
    except Exception as exc:  # PortAudioError may be raised during module import.
        raise MicrophoneError("audio runtime could not start") from exc
    device = args.device
    if device is None:
        try:
            device = int(sd.default.device[0])
        except sd.PortAudioError as exc:
            raise MicrophoneError("default microphone is unavailable") from exc
    if device < 0:
        raise ValueError("no default microphone is configured; pass --device")
    try:
        details = sd.query_devices(device, "input")
    except sd.PortAudioError as exc:
        raise MicrophoneError("microphone device is unavailable") from exc
    sample_rate = args.sample_rate or int(round(details["default_samplerate"]))
    try:
        sd.check_input_settings(
            device=device, channels=1, dtype="int16", samplerate=sample_rate
        )
    except sd.PortAudioError as exc:
        raise MicrophoneError("microphone settings are unavailable") from exc
    frames_per_chunk = max(1, round(sample_rate * args.chunk_ms / 1000))
    return (
        device,
        AudioFormat(sample_rate, 1, AudioSampleFormat.INT16),
        frames_per_chunk,
    )


def _speak_if_requested(
    response: PresentedResponse, speaker: ResponseSpeaker | None
) -> None:
    if speaker is not None and response.channel is ResponseChannel.TEXT_AND_VOICE:
        if not speaker.submit(response):
            print("Voice response queue is full; text was displayed.", file=sys.stderr)


def print_live_event(
    event: LiveSpeechEvent,
    elapsed_s: float,
    presenter: ResponsePresenter,
    speaker: ResponseSpeaker | None = None,
) -> None:
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
        response = presenter.present(notice_for_backlog(event))
        print(
            f"{prefix} backlog {event.state.value} ({event.pending_ms} ms): "
            f"{response.text} [{response.channel.value}, {response.language}]",
            flush=True,
        )
        _speak_if_requested(response, speaker)


def print_command_event(
    event: CommandEvent,
    elapsed_s: float,
    presenter: ResponsePresenter,
    speaker: ResponseSpeaker | None = None,
) -> None:
    prefix = f"[{elapsed_s:7.2f}s] command {event.stream_id}:{event.segment_id}"
    if isinstance(event, ResponseRequest):
        response = presenter.present(event)
        print(
            f"{prefix} response [{response.channel.value}, {response.language}]: "
            f"{response.text}",
            flush=True,
        )
        _speak_if_requested(response, speaker)
        return
    if isinstance(event, CommandCandidateUpdate):
        label = "candidate" if event.intent is not None else "candidate retracted"
    elif isinstance(event, CommandPlanResolution):
        steps = ", ".join(
            f"{index + 1}:{step.kind.value} target={step.target}"
            for index, step in enumerate(event.plan.steps)
        )
        print(f"{prefix} final plan: {steps}", flush=True)
        return
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


def print_action_decision(
    decision: ActionDecision,
    elapsed_s: float,
    presenter: ResponsePresenter,
    speaker: ResponseSpeaker | None = None,
) -> None:
    prefix = (
        f"[{elapsed_s:7.2f}s] action {decision.key.stream_id}:"
        f"{decision.key.segment_id} step {decision.key.step_index + 1}"
    )
    if isinstance(decision, ActionNotice):
        response = presenter.present(decision)
        print(
            f"{prefix} blocked ({decision.reason.value}): "
            f"{response.text} [{response.channel.value}]",
            flush=True,
        )
        _speak_if_requested(response, speaker)
    elif isinstance(decision, ActionRequest):
        app = f", app={decision.intent.app}" if decision.intent.app is not None else ""
        print(
            f"{prefix} authorized dry-run request: {decision.intent.kind.value} "
            f"target={decision.intent.target}{app} (not executed)",
            flush=True,
        )


def run(args: argparse.Namespace) -> None:
    presenter = ResponsePresenter(args.response_language or args.language or "en")
    detector = SileroVad()
    print("No audio is saved and no recognized command is executed.", flush=True)

    if args.mode == "vad":
        device, audio_format, frames_per_chunk = microphone_settings(args)
        from kyrin.audio.microphone.input import MicrophoneInput

        source = MicrophoneInput(device, audio_format, frames_per_chunk)
        vad_pipeline = ContinuousAudioPipeline(source, audio_format, detector)
        with vad_pipeline.open() as vad_stream:
            start = monotonic()
            timer = Timer(args.seconds, source.stop_capture)
            timer.start()
            windows = 0
            peak = 0
            try:
                for frame in vad_stream:
                    windows += 1
                    samples = np.frombuffer(frame.audio.data, dtype=np.int16)
                    if samples.size:
                        peak = max(peak, int(np.max(np.abs(samples.astype(np.int32)))))
                    if frame.transition is not None:
                        print_live_event(frame, monotonic() - start, presenter)
            finally:
                timer.cancel()
        print(f"VAD windows: {windows}; peak PCM amplitude: {peak}")
        return

    assert args.model_path is not None
    assert args.language is not None
    spoken_names = (
        CatalogSpokenAppResolver(
            XdgDesktopAppCatalog(),
            args.spoken_app_bindings,
            args.spoken_app_aliases,
        )
        if args.mode == "commands" and args.spoken_app_bindings
        else None
    )
    coordinator = (
        CommandCoordinator(DemoCommandInterpreter(spoken_names))
        if args.mode == "commands"
        else None
    )
    observer: ActiveAppObserver | None = None
    if coordinator is not None and args.active_app_bindings:
        observer = GnomeShellActiveAppObserver(
            args.active_app_bindings, catalog=XdgDesktopAppCatalog()
        )
    gate = (
        ActionGate(
            ActionPolicy(
                allowed_apps=frozenset({"telegram", "browser"})
                | frozenset(args.spoken_app_bindings.values()),
                allowed_chat_apps=frozenset({"telegram"}),
                supported_kinds=frozenset({CommandKind.OPEN_APP}),
            )
        )
        if coordinator is not None
        else None
    )
    if coordinator is not None:
        context_note = (
            "Fresh active-app context is read on final transcripts only. "
            if observer is not None
            else "No application state is assumed. "
        )
        print(
            "Command and action-gate decisions are a limited dry run. "
            "Configured applications are allowlisted for inspection only; "
            f"{context_note}No action is performed.",
            flush=True,
        )
    engine: SpeechToTextEngine
    if args.stt_backend == "whisper":
        assert args.whisper_server is not None
        engine = WhisperEngine(
            args.whisper_server,
            args.model_path,
            language=args.language,
            threads=args.whisper_threads,
        )
    else:
        engine = VoskEngine(args.model_path, language=args.language)
    speaker: ResponseSpeaker | None = None
    if coordinator is not None and not args.no_voice_responses:
        try:
            speech_backend = SpeechDispatcherSynthesizer()
            speaker = ResponseSpeaker(
                speech_backend,
                on_error=lambda exc: print(
                    f"Voice response unavailable ({exc}); text was displayed.",
                    file=sys.stderr,
                    flush=True,
                ),
            )
        except SpeechSynthesisError as exc:
            print(
                f"Voice response unavailable ({exc}); text remains on.",
                file=sys.stderr,
            )

    def create_pipeline() -> LiveSpeechPipeline:
        device, audio_format, frames_per_chunk = microphone_settings(args)
        from kyrin.audio.microphone.input import MicrophoneInput

        source = MicrophoneInput(device, audio_format, frames_per_chunk)
        guarded_source = PlaybackGuardInput(source, speaker) if speaker else source
        print(
            f"Microphone {device}, {audio_format.sample_rate} Hz, "
            f"{frames_per_chunk} frames/chunk.",
            flush=True,
        )
        return LiveSpeechPipeline(guarded_source, audio_format, detector, engine)

    controller = SpeechSessionController(create_pipeline, args.recovery_policy)
    start = monotonic()
    timer = Timer(args.seconds, controller.stop)
    safe_to_close_engine = True
    try:
        timer.start()
        with closing(controller.events()) as recovery_stream:
            for event in recovery_stream:
                if isinstance(event, SpeechSessionEnded):
                    if coordinator is not None:
                        for decision in coordinator.start_new_stream():
                            print_command_event(
                                decision, monotonic() - start, presenter, speaker
                            )
                    if event.retry_delay_s is not None and event.error is not None:
                        response = presenter.present(notice_for_error(event.error))
                        print(response.text, flush=True)
                        _speak_if_requested(response, speaker)
                        notice = SystemNotice(
                            SystemNoticeKind.LISTENING_RETRY,
                            ResponseChannel.TEXT_ONLY,
                        )
                        print(presenter.present(notice).text, flush=True)
                    continue
                print_live_event(event, monotonic() - start, presenter, speaker)
                if coordinator is not None and isinstance(event, TranscriptUpdate):
                    assert gate is not None
                    active_app, decisions = observe_command_update(
                        coordinator, event, observer
                    )
                    if observer is not None and event.status is TranscriptStatus.FINAL:
                        print(
                            f"[{monotonic() - start:7.2f}s] active app: "
                            f"{active_app or 'unknown'}",
                            flush=True,
                        )
                    for decision in decisions:
                        print_command_event(
                            decision, monotonic() - start, presenter, speaker
                        )
                        if isinstance(decision, CommandPlanResolution):
                            for index, step in enumerate(decision.plan.steps):
                                action = gate.observe(
                                    CommandResolution(
                                        decision.segment_id,
                                        step,
                                        stream_id=decision.stream_id,
                                        language=decision.language,
                                        step_index=index,
                                    )
                                )
                                if action is not None:
                                    print_action_decision(
                                        action, monotonic() - start, presenter, speaker
                                    )
                                    if isinstance(action, ActionNotice):
                                        break
                        else:
                            action = gate.observe(decision)
                            if action is not None:
                                print_action_decision(
                                    action, monotonic() - start, presenter, speaker
                                )
    except AudioCaptureStopError:
        # A native worker may still own the model; do not close/reuse it here.
        safe_to_close_engine = False
        raise
    finally:
        timer.cancel()
        if coordinator is not None:
            for decision in coordinator.start_new_stream():
                print_command_event(decision, monotonic() - start, presenter)
        try:
            if speaker is not None:
                if not speaker.wait_until_idle(12):
                    print(
                        "Voice playback did not finish before shutdown; "
                        "text was displayed.",
                        file=sys.stderr,
                    )
                speaker.close()
        finally:
            if safe_to_close_engine:
                engine.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        run(args)
    except (
        AudioError,
        SpeechToTextError,
        FileNotFoundError,
        RuntimeError,
        ValueError,
    ) as exc:
        notice = notice_for_error(exc)
        presenter = ResponsePresenter(args.response_language or args.language or "en")
        print(presenter.present(notice).text, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
