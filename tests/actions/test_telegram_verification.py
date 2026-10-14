from kyrin.actions.telegram_verification import (
    chat_header_visible,
    saved_messages_header_visible,
    unique_search_result,
)
from kyrin.vision.ocr.contracts import OcrDevice, OcrResult, RecognizedText, TextBox
from kyrin.vision.text_reader import IdentifiedWindowText


def _observation(
    *, left: int = 700, top: int = 40, duplicate: bool = False
) -> IdentifiedWindowText:
    spans = (
        RecognizedText("Saved", TextBox(left, top, 60, 24), 0.88),
        RecognizedText("Messages", TextBox(left + 67, top, 105, 24), 0.82),
    )
    if duplicate:
        spans += (
            RecognizedText("Saved", TextBox(20, 200, 60, 24), 0.9),
            RecognizedText("Messages", TextBox(87, 200, 105, 24), 0.9),
        )
    return IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(spans, "eng", OcrDevice.CPU, "fake"),
        (1600, 900),
    )


def test_header_requires_right_window_and_unique_upper_pane_title() -> None:
    assert saved_messages_header_visible(_observation(), "telegram.desktop", 123)
    assert not saved_messages_header_visible(
        _observation(left=70), "telegram.desktop", 123
    )
    assert not saved_messages_header_visible(
        _observation(top=400), "telegram.desktop", 123
    )
    assert not saved_messages_header_visible(
        _observation(duplicate=True), "telegram.desktop", 123
    )
    assert not saved_messages_header_visible(_observation(), "other.desktop", 123)
    assert not saved_messages_header_visible(_observation(), "telegram.desktop", 456)


def test_generic_header_requires_exact_target() -> None:
    observation = _observation()
    assert chat_header_visible(observation, "telegram.desktop", 123, "Saved Messages")
    assert not chat_header_visible(observation, "telegram.desktop", 123, "Alice")


def test_search_result_requires_one_exact_left_pane_match() -> None:
    observation = _observation(left=60, top=210)
    match = unique_search_result(observation, "telegram.desktop", 123, "Saved Messages")
    assert match is not None
    assert (match.left, match.top, match.image_width, match.image_height) == (
        60,
        210,
        1600,
        900,
    )
    assert (
        unique_search_result(_observation(), "telegram.desktop", 123, "Saved Messages")
        is None
    )
    assert (
        unique_search_result(
            _observation(left=60, top=50), "telegram.desktop", 123, "Saved Messages"
        )
        is None
    )
    assert (
        unique_search_result(observation, "other.desktop", 123, "Saved Messages")
        is None
    )
    assert unique_search_result(observation, "telegram.desktop", 123, "Alice") is None


def test_search_result_rejects_ambiguous_matches() -> None:
    observation = _observation(left=60, top=210, duplicate=True)
    assert (
        unique_search_result(observation, "telegram.desktop", 123, "Saved Messages")
        is None
    )
