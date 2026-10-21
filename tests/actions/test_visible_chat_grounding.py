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
    assert assessment.status == "similar_0_titles_2"
