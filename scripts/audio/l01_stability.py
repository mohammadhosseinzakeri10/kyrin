"""Bounded synthetic L01 cycles. Logical audio time is NOT live acceptance."""

import argparse
import json
from collections.abc import Iterator
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic

from kyrin.actions.gate import ActionGate, ActionPolicy
from kyrin.actions.models import ActionRequest
from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.live_speech_pipeline import LiveSpeechPipeline
from kyrin.audio.playback_guard import PlaybackGuardInput
from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.demo_interpreter import DemoCommandInterpreter
from kyrin.commands.models import CommandKind
from kyrin.model_resources import MemorySnapshot, ModelResources, Workload
from kyrin.runtime.command_runtime import LiveCommandRuntime
from kyrin.runtime.speech_sessions import SpeechSessionController
from kyrin.runtime.voice_control import VoiceMode, VoiceModeChanged
from kyrin.stt.backends.whisper import WhisperSession
from kyrin.stt.capabilities import SpeechToTextCapabilities
from kyrin.stt.contracts import SpeechToTextSession
from kyrin.stt.device import ComputeDevice, SpeechToTextOptions
from kyrin.stt.resources import ManagedSttEngine

FORMAT = AudioFormat(16000, 1, AudioSampleFormat.INT16)
ROOT = Path(__file__).resolve().parents[2]


class LogicalClock:
    def __init__(self) -> None:
        self.ns = 0
        self.lock = Lock()

    def read(self) -> int:
        with self.lock:
            return self.ns

    def advance(self) -> None:
        with self.lock:
            self.ns += 10_000_000


def run_cycle(silence_seconds: int, *, aec: bool) -> dict[str, object]:
    clock = LogicalClock()
    resources = ModelResources(memory=lambda: MemorySnapshot())
    ready, admitted, processed, stopped = (Event() for _ in range(4))
    phases = [Event() for _ in range(4)]
    errors: list[str] = []
    texts = iter(
        ("start listening", "open telegram", "stop listening", "turn microphone off")
    )
    modes: list[str] = []
    inferred: list[int] = []

    class Playback:
        is_playing = True

    playback = Playback()

    class Source:
        def capture(self) -> Iterator[AudioData]:
            # Echo must be guarded in half duplex. AEC supplies synthetic residual
            # silence; real cancellation quality is exclusively an owner test.
            with resources.use(Workload.TTS, "synthetic-tts"):
                yield AudioData(bytes(320) if aec else b"\x01\x00" * 160, FORMAT)
            playback.is_playing = False
            yield AudioData(bytes(320 * 100 * silence_seconds), FORMAT)
            for phase in phases:
                yield AudioData(bytes(320) + b"\x01\x00" * 320 + bytes(640), FORMAT)
                if not phase.wait(10):
                    raise RuntimeError("synthetic phase did not complete")

        def stop_capture(self) -> None:
            stopped.set()
            for phase in phases:
                phase.set()

    class Detector:
        input_format = FORMAT
        frames_per_window = 160
        count = 0

        def reset(self) -> None:
            self.count = 0

        def detect(self, window: AudioData) -> bool:
            clock.advance()
            self.count += 1
            if self.count == 1 + 100 * silence_seconds + 5:
                processed.set()
            return any(window.data)

    def infer(pcm: bytes, language: str) -> str:
        # Exact byte sequence proves that the beginning of each turn survived.
        assert pcm == bytes(320) + b"\x01\x00" * 320 + bytes(640)
        inferred.append(len(pcm))
        return next(texts)

    class Engine:
        capabilities = SpeechToTextCapabilities(
            frozenset({ComputeDevice.CPU}), frozenset({"en"}), True, False
        )

        def open_session(self, options: SpeechToTextOptions) -> SpeechToTextSession:
            return WhisperSession(infer, "en", lambda: None, emit_partials=False)

        def close(self) -> None:
            pass

    engine = ManagedSttEngine(Engine, resources, "synthetic-stt")
    before = resources.snapshot()

    def audio_ready() -> None:
        ready.set()
        if not admitted.wait(10):
            raise RuntimeError("synthetic command owner not admitted")

    def mode(event: VoiceModeChanged) -> None:
        modes.append(event.mode.value)
        phases[
            {VoiceMode.ACTIVE: 0, VoiceMode.STANDBY: 2, VoiceMode.OFF: 3}[event.mode]
        ].set()

    source = Source()
    runtime: LiveCommandRuntime

    def pipeline() -> LiveSpeechPipeline:
        return LiveSpeechPipeline(
            source if aec else PlaybackGuardInput(source, playback),
            FORMAT,
            Detector(),
            engine,
            start_confirm_ms=10,
            pause_confirm_ms=20,
            idle_preroll_ms=20,
            on_audio_ready=audio_ready,
            clock_ns=clock.read,
            diagnostics=runtime.listening_diagnostics,
            on_speech_started=lambda: setattr(playback, "is_playing", False),
        )

    def action(output: object) -> None:
        if isinstance(output, ActionRequest):
            phases[1].set()

    runtime = LiveCommandRuntime(
        SpeechSessionController(pipeline),
        coordinator=CommandCoordinator(DemoCommandInterpreter()),
        gate=ActionGate(
            ActionPolicy(
                allowed_apps=frozenset({"telegram"}),
                supported_kinds=frozenset({CommandKind.OPEN_APP}),
            )
        ),
        observer=None,
        executor=None,
        on_live_event=lambda _: None,
        on_command_event=lambda _: None,
        on_action_output=action,
        on_session_end=lambda _: None,
        voice_standby=True,
        on_voice_mode=mode,
        clock_ns=clock.read,
    )
    runtime.listening_diagnostics.attach("resources", resources.snapshot)

    def run() -> None:
        try:
            runtime.run()
        except Exception as exc:
            errors.append(type(exc).__name__)

    runner = Thread(target=run)
    runner.start()
    during: tuple[str, ...] = ()
    try:
        assert ready.wait(10)
        with resources.use(Workload.COMMAND, "synthetic-command"):
            admitted.set()
            assert processed.wait(10)
            during = runtime.listening_diagnostics.snapshot()
        runner.join(10)
        assert not runner.is_alive()
        assert not errors, errors
        assert modes == ["active", "standby", "off"], modes
        assert len(inferred) == 4
        assert stopped.is_set()
    finally:
        admitted.set()
        if runner.is_alive():
            runtime.stop()
            runner.join(10)
        engine.close()
    after = resources.snapshot()
    assert "active=none" in after[0] and "residents=0" in after[0]
    assert "waiting=0" in after[1]
    final = runtime.listening_diagnostics.snapshot()
    assert any(
        "finished=True" in row for row in final if row.startswith("understanding_queue")
    )
    return {
        "aec_simulated": aec,
        "logical_seconds": clock.read() / 1e9,
        "before": before,
        "during": during,
        "after": after,
        "final": final,
        "turns": len(inferred),
        "modes": modes,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, default=25)
    parser.add_argument("--silence-seconds", type=int, default=90)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.cycles <= 1000 or not 1 <= args.silence_seconds <= 100:
        parser.error("cycles: 1..1000; logical silence seconds: 1..100")
    if not args.output.resolve().is_relative_to(ROOT / "local-data"):
        parser.error("output must be under local-data")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = monotonic()
    with args.output.open("x") as output:
        for cycle in range(args.cycles):
            result = run_cycle(args.silence_seconds, aec=bool(cycle % 2))
            output.write(json.dumps({"cycle": cycle, **result}) + "\n")
            output.flush()
        output.write(
            json.dumps(
                {
                    "kind": "synthetic_only",
                    "cycles": args.cycles,
                    "actual_seconds": monotonic() - started,
                }
            )
            + "\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
