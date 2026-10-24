"""Inventory labels and action lookup share literal OCR phrase semantics."""

import pytest

from kyrin.actions.visible_control import unique_visible_target, visible_ocr_labels
from kyrin.vision.ocr.contracts import OcrDevice, OcrResult, RecognizedText, TextBox
from kyrin.vision.text_reader import IdentifiedWindowText
from kyrin.vision.text_targets import find_literal_phrases


def _span(
    text: str, left: int, top: int = 20, confidence: float | None = 0.9
) -> RecognizedText:
    return RecognizedText(text, TextBox(left, top, 45, 18), confidence)


def _observation(*spans: RecognizedText) -> IdentifiedWindowText:
    return IdentifiedWindowText(
        "example.desktop",
        42,
        OcrResult(spans, "fas+eng", OcrDevice.CPU, "test"),
        (800, 600),
    )


@pytest.mark.parametrize(
    ("spans", "label"),
    [
        ((_span("تنظیمات", 70), _span("صدا", 10)), "تنظیمات صدا"),
        ((_span("Sound", 10), _span("Settings", 70)), "Sound Settings"),
        (
            (_span("تنظیمات", 130), _span("Audio", 70), _span("صدا", 10)),
            "تنظیمات Audio صدا",
        ),
        # Logical OCR order, with an LTR run embedded in an RTL phrase.
        (
            (
                _span("تنظیمات", 190),
                _span("Sound", 70),
                _span("Settings", 130),
                _span("صدا", 10),
            ),
            "تنظیمات Sound Settings صدا",
        ),
        (
            (
                _span("Sound", 10),
                _span("تنظیمات", 130),
                _span("صدا", 70),
                _span("Settings", 190),
            ),
            "Sound تنظیمات صدا Settings",
        ),
        ((_span("Sound Settings", 10),), "Sound Settings"),
        ((_span("Sound\u00a0Settings", 10),), "Sound Settings"),
        ((_span("‘Ｓｏｕｎｄ", 10), _span("Settings’", 70)), "sound settings"),
        ((_span("كارت صدا", 10),), "کارت صدا"),
        ((_span("تنظیمات\u200cصدا", 10),), "تنظیماتصدا"),
        ((_span("تنظیمات Sound", 10),), "تنظیمات Sound"),
        ((_span("  ‘Sound\t Settings’  ", 10),), "Sound Settings"),
        ((_span("تنظيمات", 70), _span("صدا", 10)), "تنظیمات صدا"),
        # Inventory must not retain its former four-span limit.
        (
            tuple(
                _span(word, 10 + index * 50)
                for index, word in enumerate(["One", "Two", "Three", "Four", "Five"])
            ),
            "One Two Three Four Five",
        ),
        (
            (
                RecognizedText("Select", TextBox(589, 212, 49, 10), 0.94),
                RecognizedText("All", TextBox(627, 203, 14, 28), 0.96),
            ),
            "Select All",
        ),
    ],
)
def test_inventory_and_locator_agree_on_full_phrase(
    spans: tuple[RecognizedText, ...], label: str
) -> None:
    observation = _observation(*spans)
    matches = find_literal_phrases(observation.result, label)
    assert len(matches) == 1
    target = unique_visible_target(observation, "example.desktop", 42, label)
    assert target is not None
    box = matches[0].box
    assert (target.left, target.top, target.width, target.height) == (
        box.left,
        box.top,
        box.width,
        box.height,
    )
    labels = visible_ocr_labels(observation, "example.desktop", 42)
    # Display keeps OCR spelling; lookup uses the same normalization.
    observed_label = " ".join(" ".join(span.text.split()) for span in spans)
    matching = [item for item in labels if item.label == observed_label]
    assert len(matching) == 1
    assert matching[0].anchor == (box.left + box.width // 2, box.top + box.height // 2)
    assert (
        unique_visible_target(observation, "example.desktop", 42, matching[0].label)
        == target
    )


@pytest.mark.parametrize(
    "spans",
    [
        (_span("Sound", 10), _span("Settings", 200)),
        (_span("Sound", 10), _span("Settings", 70, 60)),
        (_span("Sound\nSettings", 10),),
        (
            RecognizedText("Select", TextBox(589, 212, 49, 10), 0.94),
            RecognizedText("All", TextBox(625, 203, 14, 28), 0.96),
        ),
    ],
)
def test_unrelated_or_multiline_spans_do_not_form_a_label(
    spans: tuple[RecognizedText, ...],
) -> None:
    observation = _observation(*spans)
    label = "Select All" if spans[0].text == "Select" else "Sound Settings"
    assert find_literal_phrases(observation.result, label) == ()
    assert label not in {
        " ".join(item.label.split())
        for item in visible_ocr_labels(observation, "example.desktop", 42)
    }
    assert unique_visible_target(observation, "example.desktop", 42, label) is None


@pytest.mark.parametrize("confidence", [None, 0.0, 0.64, 0.65, 0.9])
def test_confidence_is_not_invented_or_filtered_before_assembly(
    confidence: float | None,
) -> None:
    observation = _observation(
        _span("Sound", 10),
        RecognizedText("and", TextBox(57, 20, 10, 18), confidence),
        _span("Settings", 70),
    )
    matches = find_literal_phrases(observation.result, "Sound and Settings")
    assert len(matches) == 1
    assert matches[0].lowest_confidence == confidence
    labels = {
        item.label for item in visible_ocr_labels(observation, "example.desktop", 42)
    }
    accepted = confidence is not None and confidence >= 0.65
    assert ("Sound and Settings" in labels) is accepted
    assert (
        unique_visible_target(observation, "example.desktop", 42, "Sound and Settings")
        is not None
    ) is accepted
    # A rejected middle span must never disappear and join its neighbours.
    assert "Sound Settings" not in labels
    assert find_literal_phrases(observation.result, "Sound Settings") == ()


def test_duplicate_full_phrases_keep_distinct_locations_and_refuse_click() -> None:
    observation = _observation(
        _span("تنظیمات", 70),
        _span("صدا", 10),
        _span("تنظیمات", 70, 80),
        _span("صدا", 10, 80),
    )
    label = "تنظیمات صدا"
    assert len(find_literal_phrases(observation.result, label)) == 2
    options = [
        item
        for item in visible_ocr_labels(observation, "example.desktop", 42)
        if item.label == label
    ]
    assert [item.anchor for item in options] == [(62, 29), (62, 89)]
    assert unique_visible_target(observation, "example.desktop", 42, label) is None


@pytest.mark.parametrize("confidence", [None, 0.0, 0.64])
def test_single_line_span_requires_known_sufficient_confidence(
    confidence: float | None,
) -> None:
    observation = _observation(_span("Sound Settings", 10, confidence=confidence))
    matches = find_literal_phrases(observation.result, "Sound Settings")
    assert len(matches) == 1
    assert matches[0].lowest_confidence == confidence
    assert visible_ocr_labels(observation, "example.desktop", 42) == ()
    assert (
        unique_visible_target(observation, "example.desktop", 42, "Sound Settings")
        is None
    )


def test_line_span_does_not_match_only_part_of_its_text() -> None:
    observation = _observation(_span("Sound Settings", 10))
    assert find_literal_phrases(observation.result, "Sound") == ()
    assert unique_visible_target(observation, "example.desktop", 42, "Sound") is None
