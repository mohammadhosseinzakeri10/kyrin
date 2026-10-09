from kyrin.vision.ocr.contracts import OcrDevice, OcrResult, RecognizedText, TextBox
from kyrin.vision.text_targets import find_exact_phrases


def _span(text: str, left: int, top: int, confidence: float = 0.9) -> RecognizedText:
    return RecognizedText(text, TextBox(left, top, 45, 18), confidence)


def _result(*spans: RecognizedText) -> OcrResult:
    return OcrResult(spans, "eng", OcrDevice.CPU, "test")


def test_exact_phrase_is_bounded_to_one_line() -> None:
    result = _result(_span("Saved", 10, 20), _span("Messages", 62, 20))
    matches = find_exact_phrases(result, "saved messages")
    assert len(matches) == 1
    assert matches[0].box == TextBox(10, 20, 97, 18)
    assert matches[0].lowest_confidence == 0.9

    split_rows = _result(_span("Saved", 10, 20), _span("Messages", 10, 60))
    assert find_exact_phrases(split_rows, "Saved Messages") == ()


def test_duplicate_names_are_not_silently_reduced_to_one_match() -> None:
    result = _result(_span("Ali", 10, 20), _span("Ali", 10, 60))
    assert len(find_exact_phrases(result, "Ali")) == 2


def test_different_or_distant_words_do_not_match() -> None:
    result = _result(_span("Saved", 10, 20), _span("Messages", 300, 20))
    assert find_exact_phrases(result, "Saved Messages") == ()
    assert find_exact_phrases(result, "Saved Message") == ()
