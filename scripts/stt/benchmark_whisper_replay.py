"""Replay a WAV at recorded speed through overlapping Whisper CPU requests.

This is an isolated diagnostic, not a SpeechToTextEngine implementation. It
never accesses the microphone or executes a recognized command. It starts a
loopback-only whisper.cpp server so model load is paid once per run.
"""

import argparse
import io
import json
import socket
import subprocess
import tempfile
import wave
from collections.abc import Iterator
from pathlib import Path
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

from kyrin.audio.audio_data import AudioData
from kyrin.audio.audio_format import AudioFormat, AudioSampleFormat
from kyrin.audio.sample_rate_converter import SampleRateConverter
from kyrin.stt.evaluation import edit_distance, normalize_text

SAMPLE_RATE = 16_000
LOCAL_HTTP = build_opener(ProxyHandler({}))


def read_pcm16_mono(path: Path) -> bytes:
    """Read PCM WAV and use KYRIN's stream resampler when needed."""
    with wave.open(str(path), "rb") as audio:
        if (
            audio.getcomptype() != "NONE"
            or audio.getnchannels() != 1
            or audio.getsampwidth() != 2
        ):
            raise ValueError("WAV must be uncompressed mono 16-bit PCM")
        source_format = AudioFormat(audio.getframerate(), 1, AudioSampleFormat.INT16)

        def chunks() -> Iterator[AudioData]:
            while data := audio.readframes(4096):
                yield AudioData(data, source_format)

        converter = SampleRateConverter(source_format, SAMPLE_RATE)
        return b"".join(chunk.data for chunk in converter.convert(chunks()))


def wav_bytes(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm)
    return buffer.getvalue()


def request_transcript(port: int, pcm: bytes, language: str) -> str:
    """Send one 16 kHz WAV window to the local server without extra packages."""
    boundary = uuid4().hex
    fields = {"language": language, "response_format": "json", "no_timestamps": "true"}
    body = bytearray()
    for name, value in fields.items():
        body.extend(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode()
        )
    body.extend(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        'filename="window.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
    )
    body.extend(wav_bytes(pcm))
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    request = Request(
        f"http://127.0.0.1:{port}/inference",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with LOCAL_HTTP.open(request, timeout=120) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("whisper-server returned an unexpected JSON response")
    text = payload.get("text")
    if not isinstance(text, str):
        raise ValueError("whisper-server returned an unexpected JSON response")
    return text.strip()


def wait_for_server(process: subprocess.Popen[bytes], port: int) -> None:
    deadline = monotonic() + 30
    while monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"whisper-server exited with status {process.returncode}"
            )
        try:
            with LOCAL_HTTP.open(f"http://127.0.0.1:{port}/", timeout=0.5):
                return
        except OSError, URLError:
            sleep(0.1)
    raise TimeoutError("whisper-server did not become ready within 30 seconds")


def free_loopback_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def replay(
    pcm: bytes,
    *,
    port: int,
    language: str,
    step_seconds: float,
    window_seconds: float,
    reference: str | None,
) -> dict[str, object]:
    """Pace window availability; report lateness rather than claiming streaming STT."""
    duration = len(pcm) / (SAMPLE_RATE * 2)
    if duration < 0.5:
        raise ValueError("WAV needs at least 0.5 seconds of audio")
    started = monotonic()
    windows: list[dict[str, float | str | bool]] = []
    first_text_seconds: float | None = None
    first_reference_match_seconds: float | None = None
    previous_text = ""
    end_seconds = min(step_seconds, duration)
    while True:
        sleep(max(0.0, started + end_seconds - monotonic()))
        request_started = monotonic()
        start_seconds = max(0.0, end_seconds - window_seconds)
        start_byte = round(start_seconds * SAMPLE_RATE) * 2
        end_byte = round(end_seconds * SAMPLE_RATE) * 2
        text = request_transcript(port, pcm[start_byte:end_byte], language)
        completed = monotonic()
        observed_at = completed - started
        if text and first_text_seconds is None:
            first_text_seconds = observed_at
        if (
            reference
            and first_reference_match_seconds is None
            and normalize_text(text) == normalize_text(reference)
        ):
            first_reference_match_seconds = observed_at
        windows.append(
            {
                "audio_start_seconds": round(start_seconds, 3),
                "audio_end_seconds": round(end_seconds, 3),
                "request_seconds": round(completed - request_started, 3),
                "dispatch_lag_seconds": round(
                    max(0.0, request_started - started - end_seconds), 3
                ),
                "completion_lag_seconds": round(observed_at - end_seconds, 3),
                "text": text,
                "changed_from_previous": bool(previous_text and text != previous_text),
            }
        )
        previous_text = text
        if end_seconds >= duration:
            break
        end_seconds = min(duration, end_seconds + step_seconds)
    final_text = str(windows[-1]["text"])
    match_key = "first_exact_reference_match_seconds_from_file_start"
    report: dict[str, object] = {
        "audio_seconds": round(duration, 3),
        "elapsed_seconds": round(monotonic() - started, 3),
        "first_nonempty_text_seconds_from_file_start": first_text_seconds,
        match_key: first_reference_match_seconds,
        "max_dispatch_lag_seconds": max(
            float(w["dispatch_lag_seconds"]) for w in windows
        ),
        "max_completion_lag_seconds": max(
            float(w["completion_lag_seconds"]) for w in windows
        ),
        "changed_windows": sum(bool(w["changed_from_previous"]) for w in windows),
        "last_window_text": final_text,
        "windows": windows,
    }
    if reference is not None:
        normalized_reference = normalize_text(reference)
        report["reference"] = reference
        report["last_window_cer"] = (
            edit_distance(normalized_reference, normalize_text(final_text))
            / len(normalized_reference)
            if duration <= window_seconds
            else None
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wav", required=True, type=Path)
    parser.add_argument("--server", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--language", default="auto")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--step-seconds", type=float, default=1.0)
    parser.add_argument("--window-seconds", type=float, default=5.0)
    parser.add_argument("--reference")
    parser.add_argument(
        "--output", type=Path, help="optional JSON report; never overwritten"
    )
    args = parser.parse_args(argv)
    if (
        args.threads <= 0
        or args.step_seconds <= 0
        or args.window_seconds < args.step_seconds
    ):
        parser.error("threads and step must be positive; window must be at least step")
    if args.reference is not None and not normalize_text(args.reference):
        parser.error("reference must contain scorable text")
    for path in (args.wav, args.server, args.model):
        if not path.is_file():
            parser.error(f"file does not exist: {path}")
    if args.output is not None and args.output.exists():
        parser.error(f"report already exists: {args.output}")
    try:
        pcm = read_pcm16_mono(args.wav)
        port = free_loopback_port()
        with tempfile.TemporaryFile() as server_log:
            model_loading_started = monotonic()
            process = subprocess.Popen(
                [
                    str(args.server.resolve()),
                    "--model",
                    str(args.model.resolve()),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--threads",
                    str(args.threads),
                    "--no-gpu",
                ],
                stdin=subprocess.DEVNULL,
                stdout=server_log,
                stderr=subprocess.STDOUT,
            )
            try:
                wait_for_server(process, port)
                model_load_seconds = monotonic() - model_loading_started
                report = replay(
                    pcm,
                    port=port,
                    language=args.language,
                    step_seconds=args.step_seconds,
                    window_seconds=args.window_seconds,
                    reference=args.reference,
                )
            except OSError, RuntimeError, TimeoutError:
                server_log.seek(0)
                print(server_log.read().decode(errors="replace")[-3000:])
                raise
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    except (
        OSError,
        ValueError,
        wave.Error,
        HTTPError,
        URLError,
        RuntimeError,
        TimeoutError,
    ) as exc:
        parser.exit(2, f"Whisper replay failed: {exc}\n")
    report.update(
        {
            "model": str(args.model),
            "language": args.language,
            "cpu_threads": args.threads,
            "step_seconds": args.step_seconds,
            "window_seconds": args.window_seconds,
            "model_load_seconds": round(model_load_seconds, 3),
            "note": (
                "Rolling-window replay, not a native streaming STT adapter "
                "or command trigger"
            ),
        }
    )
    formatted = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as destination:
            destination.write(formatted + "\n")
    print(formatted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
