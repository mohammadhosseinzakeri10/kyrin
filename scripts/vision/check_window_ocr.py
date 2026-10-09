"""Read one user-selected window, without executing an action or saving pixels."""

import argparse
from pathlib import Path

from kyrin.vision.ocr.backends.tesseract import (
    OcrInferenceError,
    OcrUnavailableError,
    TesseractOcrEngine,
)
from kyrin.vision.ocr.contracts import OcrDevicePreference, OcrOptions
from kyrin.vision.platforms.ubuntu_portal import UbuntuPortalScreenCapture
from kyrin.vision.text_reader import WindowTextReader


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tessdata-dir", required=True, type=Path)
    parser.add_argument("--executable", default="tesseract")
    parser.add_argument("--language", default="eng")
    parser.add_argument(
        "--device", choices=[item.value for item in OcrDevicePreference], default="auto"
    )
    parser.add_argument("--show-text", action="store_true")
    args = parser.parse_args()
    try:
        engine = TesseractOcrEngine(args.tessdata_dir, executable=args.executable)
        reader = WindowTextReader(UbuntuPortalScreenCapture(), engine)
        result = reader.read_selected_window(
            OcrOptions(args.language, OcrDevicePreference(args.device))
        )
    except (OcrUnavailableError, OcrInferenceError, ValueError) as exc:
        parser.exit(2, f"OCR unavailable: {exc}\n")
    if result is None:
        parser.exit(2, "Window capture unavailable or cancelled.\n")
    print(
        f"Engine: {result.engine_id}; device: {result.device}; "
        f"words: {len(result.spans)}"
    )
    if args.show_text:
        for span in result.spans:
            print(f"({span.box.left},{span.box.top}) {span.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
