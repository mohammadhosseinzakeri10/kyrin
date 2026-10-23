from kyrin.vision.ocr.contracts import OcrDevice, OcrResult, RecognizedText, TextBox
from kyrin.vision.text_targets import (
    find_compact_phrases,
    find_exact_phrases,
    find_literal_phrases,
)


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


def test_ocr_leading_curly_quote_does_not_hide_exact_label() -> None:
    result = _result(
        _span("‘Speakers", 10, 20),
        _span("and", 62, 20),
        _span("Camera", 114, 20),
    )
    assert len(find_exact_phrases(result, "Speakers and Camera")) == 1


def test_different_or_distant_words_do_not_match() -> None:
    result = _result(_span("Saved", 10, 20), _span("Messages", 300, 20))
    assert find_exact_phrases(result, "Saved Messages") == ()
    assert find_exact_phrases(result, "Saved Message") == ()


def test_adjacent_words_allow_small_ocr_box_overlap() -> None:
    result = _result(
        RecognizedText("Select", TextBox(589, 212, 49, 10), 0.94),
        RecognizedText("All", TextBox(627, 203, 14, 28), 0.96),
    )
    matches = find_literal_phrases(result, "Select All", allow_joined_words=True)
    assert len(matches) == 1
    assert matches[0].lowest_confidence == 0.94
    assert matches[0].box == TextBox(589, 203, 52, 28)

    too_much_overlap = _result(
        RecognizedText("Select", TextBox(589, 212, 49, 10), 0.94),
        RecognizedText("All", TextBox(625, 203, 14, 28), 0.96),
    )
    assert find_literal_phrases(too_much_overlap, "Select All") == ()


def test_compact_phrase_matches_only_adjacent_full_words() -> None:
    result = _result(_span("My", 10, 20), _span("Mother", 62, 20))
    assert len(find_compact_phrases(result, "mymother")) == 1
    joined_result = _result(_span("MyMother", 10, 20))
    assert len(find_compact_phrases(joined_result, "My Mother")) == 1
    assert find_compact_phrases(result, "mymothers") == ()
    assert find_compact_phrases(
        _result(_span("My", 10, 20), _span("Mother", 10, 60)), "mymother"
    ) == ()


def test_literal_phrase_matcher_keeps_duplicates_without_double_counting() -> None:
    result = _result(
        _span("My", 10, 20),
        _span("Mother", 62, 20),
        _span("MyMother", 10, 60),
    )
    assert len(find_literal_phrases(result, "My Mother")) == 1
    assert len(
        find_literal_phrases(result, "My Mother", allow_joined_words=True)
    ) == 2
