"""Record one consented command prompt into a local, Git-ignored WAV file.

This diagnostic never starts the microphone merely by importing the module or
showing --help. Run it once per prompt ID after the speaker is ready.
"""

import argparse
import csv
import re
import shutil
import tempfile
import wave
from array import array
from math import sqrt
from pathlib import Path
from sys import byteorder
from time import sleep

from kyrin.audio.microphone.errors import MicrophoneError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "datasets" / "stt"
TEMPLATE = DATA_ROOT / "manifest.template.csv"
MULTILINGUAL_TEMPLATE = DATA_ROOT / "manifest.multilingual.template.csv"
GERMAN_TEMPLATE = DATA_ROOT / "manifest.german.template.csv"
SAFETY_TEMPLATE = DATA_ROOT / "manifest.safety.template.csv"
TEMPLATES = (TEMPLATE, MULTILINGUAL_TEMPLATE, GERMAN_TEMPLATE, SAFETY_TEMPLATE)
SPEAKER_ID_PATTERN = re.compile(r"speaker-[a-z0-9][a-z0-9_-]{0,31}")


def recording_destination(prompt_id: str, speaker_id: str | None) -> Path:
    """Keep repeat prompts from different speakers in separate local paths."""
    if speaker_id is None:
        return DATA_ROOT / "recordings" / f"{prompt_id}.wav"
    if SPEAKER_ID_PATTERN.fullmatch(speaker_id) is None:
        raise ValueError("speaker ID must match speaker-[a-z0-9_-] and be short")
    return DATA_ROOT / "recordings" / "speakers" / speaker_id / f"{prompt_id}.wav"


def prompt_catalog() -> dict[str, tuple[str, Path]]:
    catalog: dict[str, tuple[str, Path]] = {}
    for template in TEMPLATES:
        with template.open(encoding="utf-8", newline="") as source:
            for row in csv.DictReader(source):
                if row["id"] in catalog:
                    raise ValueError(f"duplicate prompt ID: {row['id']}")
                catalog[row["id"]] = (row["reference"], template)
    return catalog


def main(argv: list[str] | None = None) -> int:
    catalog = prompt_catalog()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True, choices=sorted(catalog))
    parser.add_argument("--device", type=int, required=True, help="input device ID")
    parser.add_argument("--sample-rate", type=int, help="device default if absent")
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--countdown", type=int, default=3)
    parser.add_argument(
        "--speaker-id",
        help="pseudonymous speaker ID, e.g. speaker-02; omitting preserves legacy path",
    )
    args = parser.parse_args(argv)
    prompt, template = catalog[args.id]
    if not 2 <= args.seconds <= 30:
        parser.error("--seconds must be between 2 and 30")
    if args.countdown < 0 or args.countdown > 10:
        parser.error("--countdown must be between 0 and 10")
    if args.sample_rate is not None and args.sample_rate <= 0:
        parser.error("--sample-rate must be positive")

    try:
        destination = recording_destination(args.id, args.speaker_id)
    except ValueError as exc:
        parser.error(str(exc))
    recordings = destination.parent
    if destination.exists():
        parser.error(
            f"recording already exists and will not be overwritten: {destination}"
        )

    try:
        import sounddevice as sd  # type: ignore[import-untyped]
    except (ImportError, OSError) as exc:
        parser.exit(2, f"Audio runtime is unavailable: {exc}\n")

    try:
        if args.device < 0:
            raise MicrophoneError("no default input device")
        details = sd.query_devices(args.device, "input")
        sample_rate = args.sample_rate or int(round(details["default_samplerate"]))
        sd.check_input_settings(
            device=args.device, channels=1, dtype="int16", samplerate=sample_rate
        )
    except sd.PortAudioError as exc:
        parser.exit(2, f"Microphone is unavailable: {exc}\n")
    except MicrophoneError as exc:
        parser.exit(2, f"Microphone is unavailable: {exc}\n")

    recordings.mkdir(parents=True, exist_ok=True)
    print(f"جملهٔ {args.id}: {prompt}", flush=True)
    for count in range(args.countdown, 0, -1):
        print(count, flush=True)
        sleep(1)

    temporary_path: Path | None = None
    try:
        sample_count = 0
        sum_squares = 0
        peak = 0
        with tempfile.NamedTemporaryFile(
            dir=recordings, prefix=f".{args.id}-", suffix=".wav", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        with wave.open(str(temporary_path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            frames_remaining = round(args.seconds * sample_rate)
            chunk_frames = max(1, round(sample_rate * 0.02))
            with sd.RawInputStream(
                device=args.device,
                samplerate=sample_rate,
                channels=1,
                dtype="int16",
            ) as stream:
                print("شروع کن", flush=True)
                while frames_remaining > 0:
                    frames = min(chunk_frames, frames_remaining)
                    data, overflowed = stream.read(frames)
                    if overflowed:
                        raise MicrophoneError("microphone input overflowed")
                    chunk = bytes(data)
                    samples = array("h")
                    samples.frombytes(chunk)
                    if byteorder != "little":
                        samples.byteswap()
                    sample_count += len(samples)
                    sum_squares += sum(sample * sample for sample in samples)
                    chunk_peak = max((abs(sample) for sample in samples), default=0)
                    peak = max(peak, chunk_peak)
                    output.writeframes(chunk)
                    frames_remaining -= frames
        if temporary_path.stat().st_size <= 44:
            raise MicrophoneError("no audio samples were captured")
        rms = sqrt(sum_squares / sample_count)
        print(f"سطح صدا: RMS={rms:.1f}, peak={peak}", flush=True)
        if rms < 20 and peak < 300:
            raise MicrophoneError("recording is nearly silent; WAV was not saved")
        temporary_path.replace(destination)
        temporary_path = None
    except (MicrophoneError, OSError, sd.PortAudioError) as exc:
        parser.exit(2, f"Recording failed: {exc}\n")
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    if args.speaker_id is None:
        with template.open(encoding="utf-8", newline="") as source:
            expected = tuple(row["path"] for row in csv.DictReader(source))
        manifest_names = {
            TEMPLATE: "manifest.csv",
            MULTILINGUAL_TEMPLATE: "manifest.multilingual.csv",
            GERMAN_TEMPLATE: "manifest.german.csv",
            SAFETY_TEMPLATE: "manifest.safety.csv",
        }
        manifest = DATA_ROOT / manifest_names[template]
        if (
            all((DATA_ROOT / path).is_file() for path in expected)
            and not manifest.exists()
        ):
            shutil.copyfile(template, manifest)
            print(f"همهٔ فایل‌ها آماده‌اند. متن‌های مرجع را در {manifest} بررسی کن.")
    else:
        print("این ضبط فقط پس از تأیید متنِ واقعاً گفته‌شده وارد مجموعهٔ ارزیابی شود.")
    print(f"ضبط در {destination} ذخیره شد.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
