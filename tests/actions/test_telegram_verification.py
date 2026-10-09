from kyrin.actions.telegram_verification import saved_messages_header_visible
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
