"""Misheard names may suggest observed rows but never authorize a click."""

import pytest

from kyrin.actions.visible_chat_grounding import (
    assess_visible_chat_grounding,
    suggest_visible_chat_choices,
)
from kyrin.vision.ocr.contracts import OcrDevice, OcrResult, RecognizedText, TextBox
from kyrin.vision.text_reader import IdentifiedWindowText


def _window(title: str, *, preview_only: bool = False) -> IdentifiedWindowText:
    top = 227 if preview_only else 200
    spans = (
        RecognizedText(title, TextBox(70, top, 130, 18), 0.95),
        RecognizedText("8:12", TextBox(455, 200, 42, 16), 0.9),
        RecognizedText("Hello", TextBox(70, 227, 60, 15), 0.9),
    )
    return IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(spans, "fas+eng", OcrDevice.CPU, "fake"),
        (1600, 900),
    )


@pytest.mark.parametrize(
    ("heard", "title"),
    [
        ("martin", "matin"),
        ("visionet", "Visonate فارسی"),
        ("visionet", "ربات فروشگاه VizoNet"),
        ("visionate", "ربات فروشگاه VizoNet"),
        ("visionnate", "ربات فروشگاه VizoNet"),
        ("a bullfazle a body", "ابوالفضل عبادی"),
        ("abolfazl ebadi", "ابوالفضل عبادی"),
    ],
)
def test_misheard_visible_title_is_grounded_to_ocr_row(heard: str, title: str) -> None:
    choices = suggest_visible_chat_choices(
        _window(title), "telegram.desktop", 123, heard
    )
    assert choices is not None
    assert choices.grounded_titles == (title,)
    assert tuple(row.top for row in choices.local_results) == (200,)


def test_grounding_rejects_preview_and_different_window() -> None:
    preview = _window("matin", preview_only=True)
    assert (
        suggest_visible_chat_choices(preview, "telegram.desktop", 123, "martin") is None
    )
    assert (
        suggest_visible_chat_choices(_window("matin"), "other.desktop", 123, "martin")
        is None
    )


def test_mixed_direction_title_split_across_ocr_spans() -> None:
    observation = IdentifiedWindowText(
        "telegram.desktop", 123,
        OcrResult(
            (
                RecognizedText("ربات", TextBox(190, 200, 35, 18), 0.95),
                RecognizedText("فروشگاه", TextBox(120, 200, 65, 18), 0.95),
                RecognizedText("VizoNet", TextBox(60, 200, 55, 18), 0.95),
                RecognizedText("8:12", TextBox(455, 200, 42, 16), 0.9),
                RecognizedText("سلام", TextBox(70, 227, 60, 15), 0.9),
            ),
            "fas+eng", OcrDevice.CPU, "fake",
        ),
        (1600, 900),
    )
    choices = suggest_visible_chat_choices(
        observation, "telegram.desktop", 123, "visionet"
    )
    assert choices is not None
    assert choices.grounded_titles == ("ربات فروشگاه VizoNet",)
    assert tuple(row.top for row in choices.local_results) == (200,)


def test_mixed_title_can_be_grounded_with_unreadable_persian_preview() -> None:
    observation = IdentifiedWindowText(
        "telegram.desktop", 123,
        OcrResult(
            (
                RecognizedText("previous preview", TextBox(70, 665, 90, 10), 0.88),
                RecognizedText("10/4/26", TextBox(455, 665, 45, 9), 0.92),
                RecognizedText(
                    "ربات فروشگاه VizoNet", TextBox(70, 692, 210, 20), 0.94
                ),
                RecognizedText("10/3/26", TextBox(455, 700, 45, 9), 0.96),
                RecognizedText("سلام", TextBox(70, 724, 60, 10), 0.29),
            ),
            "fas+eng", OcrDevice.CPU, "fake",
        ),
        (1600, 900),
    )
    choices = suggest_visible_chat_choices(
        observation, "telegram.desktop", 123, "visionet"
    )
    assert choices is not None
    assert choices.grounded_titles == ("ربات فروشگاه VizoNet",)


def test_grounding_keeps_two_similar_titles_in_screen_order() -> None:
    spans = (
        RecognizedText("matin", TextBox(70, 200, 80, 18), 0.95),
        RecognizedText("8:12", TextBox(455, 200, 42, 16), 0.9),
        RecognizedText("Hello", TextBox(70, 227, 60, 15), 0.9),
        RecognizedText("martin", TextBox(70, 280, 80, 18), 0.95),
        RecognizedText("8:15", TextBox(455, 280, 42, 16), 0.9),
        RecognizedText("Hello", TextBox(70, 307, 60, 15), 0.9),
    )
    window = IdentifiedWindowText(
        "telegram.desktop", 123,
        OcrResult(spans, "eng", OcrDevice.CPU, "fake"),
        (1600, 900),
    )
    choices = suggest_visible_chat_choices(window, "telegram.desktop", 123, "martin")
    assert choices is not None
    assert choices.grounded_titles == ("matin", "martin")
    assert tuple(row.top for row in choices.local_results) == (200, 280)


def test_grounding_diagnostic_reports_counts_without_chat_titles() -> None:
    assessment = assess_visible_chat_grounding(
        _window("Alice"), "telegram.desktop", 123, "martin"
    )
    assert assessment.choices is None
    assert assessment.status == "similar_0_titles_2_best_0"
