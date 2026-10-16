"""Read one user-selected window, without executing an action or saving pixels."""

import argparse
from pathlib import Path

from kyrin.actions.telegram_verification import search_choices
from kyrin.vision.ocr.backends.tesseract import (
    OcrInferenceError,
    OcrUnavailableError,
    TesseractOcrEngine,
)
from kyrin.vision.ocr.contracts import OcrDevicePreference, OcrOptions
from kyrin.vision.platforms.ubuntu_portal import UbuntuPortalScreenCapture
from kyrin.vision.text_reader import IdentifiedWindowText
from kyrin.vision.text_targets import find_exact_phrases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tessdata-dir", required=True, type=Path)
    parser.add_argument("--executable", default="tesseract")
    parser.add_argument("--language", default="eng")
    parser.add_argument(
        "--device", choices=[item.value for item in OcrDevicePreference], default="auto"
    )
    parser.add_argument("--show-text", action="store_true")
    parser.add_argument(
        "--search-context",
        action="store_true",
        help="show only search-field text and common search-mode labels",
    )
    parser.add_argument(
        "--match-phrase",
        help="report only matching phrase boxes; do not print other recognized text",
    )
    parser.add_argument(
        "--classify-chat",
        action="store_true",
        help="report whether the current Telegram geometry yields chat choices",
    )
    args = parser.parse_args()
    try:
        engine = TesseractOcrEngine(args.tessdata_dir, executable=args.executable)
        image = UbuntuPortalScreenCapture().capture_window()
        result = (
            engine.recognize(
                image, OcrOptions(args.language, OcrDevicePreference(args.device))
            )
            if image is not None
            else None
        )
    except (OcrUnavailableError, OcrInferenceError, ValueError) as exc:
        parser.exit(2, f"OCR unavailable: {exc}\n")
    if result is None:
        parser.exit(2, "Window capture unavailable or cancelled.\n")
    assert image is not None
    width = int.from_bytes(image[16:20], "big")
    height = int.from_bytes(image[20:24], "big")
    print(f"Image size: {width}x{height}")
    print(
        f"Engine: {result.engine_id}; device: {result.device}; "
        f"words: {len(result.spans)}"
    )
    if args.match_phrase:
        matches = find_exact_phrases(result, args.match_phrase)
        print(f"Phrase matches: {len(matches)}")
        for match in matches:
            box = match.box
            print(
                f"box=({box.left},{box.top},{box.width},{box.height}); "
                f"confidence={match.lowest_confidence}"
            )
        for index, word in enumerate(args.match_phrase.split(), start=1):
            word_matches = find_exact_phrases(result, word)
            boxes = tuple(
                (match.box.left, match.box.top, match.box.width, match.box.height)
                for match in word_matches[:12]
            )
            print(f"Target word {index}: matches={len(word_matches)}; boxes={boxes}")
        if args.classify_chat:
            observation = IdentifiedWindowText(
                "diagnostic", 1, result, (width, height)
            )
            choices = search_choices(observation, "diagnostic", 1, args.match_phrase)
            summary = (
                "uncertain"
                if choices is None
                else f"local_rows={tuple(row.top for row in choices.local_results)}; "
                f"global_rows={tuple(row.top for row in choices.global_results)}"
            )
            print(f"Chat choices: {summary}")
    if args.show_text:
        for span in result.spans:
            print(f"({span.box.left},{span.box.top}) {span.text}")
    if args.search_context:
        markers = {"search", "global", "results", "messages", "chats", "in", "found"}
        for span in result.spans:
            in_search_field = (
                span.box.left < width * 0.3
                and span.box.top < height * 0.075
            )
            if in_search_field or span.text.casefold().strip(":") in markers:
                print(f"Search UI ({span.box.left},{span.box.top}): {span.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
