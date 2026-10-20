import pytest

from kyrin.actions.telegram_verification import (
    assess_visible_chat_choices,
    chat_header_visible,
    saved_messages_header_visible,
    search_choices,
    telegram_left_label,
    telegram_menu_item,
    telegram_search_query_visible,
    telegram_settings_header,
    telegram_settings_item,
    telegram_view_title_visible,
    unique_search_result,
    visible_chat_choices,
)
from kyrin.vision.ocr.contracts import OcrDevice, OcrResult, RecognizedText, TextBox
from kyrin.vision.text_reader import IdentifiedWindowText


def _observation(
    *, left: int = 700, top: int = 40, duplicate: bool = False, query: bool = False
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
    if query:
        spans += (
            RecognizedText("Saved", TextBox(60, 45, 60, 13), 0.9),
            RecognizedText("Messages", TextBox(127, 45, 105, 13), 0.9),
        )
    return IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(spans, "eng", OcrDevice.CPU, "fake"),
        (1600, 900),
    )


def test_header_requires_right_window_and_unique_header_title() -> None:
    assert saved_messages_header_visible(_observation(), "telegram.desktop", 123)
    assert not saved_messages_header_visible(
        _observation(left=70), "telegram.desktop", 123
    )
    assert not saved_messages_header_visible(
        _observation(top=400), "telegram.desktop", 123
    )
    assert saved_messages_header_visible(
        _observation(duplicate=True), "telegram.desktop", 123
    )
    assert not saved_messages_header_visible(_observation(), "other.desktop", 123)
    assert not saved_messages_header_visible(_observation(), "telegram.desktop", 456)


def test_generic_header_requires_exact_target() -> None:
    observation = _observation()
    assert chat_header_visible(observation, "telegram.desktop", 123, "Saved Messages")
    assert chat_header_visible(observation, "telegram.desktop", 123, "savedmessages")
    assert not chat_header_visible(observation, "telegram.desktop", 123, "Alice")
    assert not chat_header_visible(
        observation, "telegram.desktop", 123, "Saved Message"
    )


def test_visible_chat_titles_require_time_and_preview_anchors() -> None:
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(
            (
                RecognizedText("Chats", TextBox(20, 35, 60, 16), 0.90),
                RecognizedText("Search", TextBox(60, 45, 70, 16), 0.90),
                RecognizedText("My", TextBox(70, 200, 25, 18), 0.92),
                RecognizedText("Mother", TextBox(100, 200, 65, 18), 0.91),
                RecognizedText("8:12", TextBox(455, 200, 42, 16), 0.82),
                RecognizedText("Hello", TextBox(70, 227, 60, 15), 0.88),
                RecognizedText("My", TextBox(70, 280, 25, 18), 0.91),
                RecognizedText("Mother", TextBox(100, 280, 65, 18), 0.90),
                RecognizedText("7:30", TextBox(455, 280, 42, 16), 0.84),
                RecognizedText("Yesterday", TextBox(70, 307, 80, 15), 0.85),
            ),
            "eng", OcrDevice.CPU, "fake",
        ),
        (1600, 900),
    )
    choices = visible_chat_choices(observation, "telegram.desktop", 123, "My Mother")
    assert choices is not None
    assert choices.source == "visible"
    assert tuple(item.top for item in choices.local_results) == (200, 280)
    lower_case_choices = visible_chat_choices(
        observation, "telegram.desktop", 123, "my mother"
    )
    assert lower_case_choices == choices
    joined_name_choices = visible_chat_choices(
        observation, "telegram.desktop", 123, "MyMother"
    )
    assert joined_name_choices == choices
    assessment = assess_visible_chat_choices(
        observation, "telegram.desktop", 123, "my mother"
    )
    assert assessment.choices == choices
    assert assessment.status == "classified_local_2"
    assert visible_chat_choices(observation, "other.desktop", 123, "My Mother") is None


def test_visible_chat_rejects_preview_and_active_search_field() -> None:
    spans = (
        RecognizedText("Search", TextBox(60, 45, 70, 16), 0.90),
        RecognizedText("Alice", TextBox(70, 200, 55, 18), 0.90),
        RecognizedText("8:12", TextBox(455, 200, 42, 16), 0.82),
        RecognizedText("My", TextBox(70, 227, 25, 15), 0.92),
        RecognizedText("Mother", TextBox(100, 227, 65, 15), 0.91),
        RecognizedText("second", TextBox(70, 247, 60, 15), 0.88),
    )
    observation = IdentifiedWindowText(
        "telegram.desktop", 123, OcrResult(spans, "eng", OcrDevice.CPU, "fake"),
        (1600, 900),
    )
    assert (
        visible_chat_choices(observation, "telegram.desktop", 123, "My Mother")
        is None
    )
    assessment = assess_visible_chat_choices(
        observation, "telegram.desktop", 123, "My Mother"
    )
    assert assessment.status == "rows_1_low_0_time_1_preview_0"
    searched = IdentifiedWindowText(
        "telegram.desktop", 123,
        OcrResult(
            (RecognizedText("Alice", TextBox(180, 45, 50, 16), 0.90), *spans),
            "eng", OcrDevice.CPU, "fake",
        ),
        (1600, 900),
    )
    assert visible_chat_choices(searched, "telegram.desktop", 123, "Alice") is None
    results_heading = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(
            (
                *spans,
                RecognizedText(
                    "Global Search Results", TextBox(30, 170, 200, 18), 0.88
                ),
            ),
            "eng", OcrDevice.CPU, "fake",
        ),
        (1600, 900),
    )
    assert (
        assess_visible_chat_choices(
            results_heading, "telegram.desktop", 123, "Alice"
        ).status
        == "search_field_active"
    )


def test_visible_chat_keeps_ocr_spacing_variants_as_two_choices() -> None:
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(
            (
                RecognizedText("Search", TextBox(60, 45, 70, 16), 0.90),
                RecognizedText("My", TextBox(70, 200, 25, 18), 0.92),
                RecognizedText("Mother", TextBox(100, 200, 65, 18), 0.91),
                RecognizedText("8:12", TextBox(455, 200, 42, 16), 0.82),
                RecognizedText("Hello", TextBox(70, 227, 60, 15), 0.88),
                RecognizedText("MyMother", TextBox(70, 280, 95, 18), 0.91),
                RecognizedText("7:30", TextBox(455, 280, 42, 16), 0.84),
                RecognizedText("Yesterday", TextBox(70, 307, 80, 15), 0.85),
            ),
            "eng", OcrDevice.CPU, "fake",
        ),
        (1600, 900),
    )
    choices = visible_chat_choices(observation, "telegram.desktop", 123, "My Mother")
    assert choices is not None
    assert tuple(item.top for item in choices.local_results) == (200, 280)


@pytest.mark.parametrize(
    ("second_time_visible", "status"),
    (
        (True, "classified_local_2"),
        (False, "classified_local_2_time_fallback_1"),
    ),
)
def test_visible_chat_ignores_same_name_in_preview_title_column_boundary(
    second_time_visible: bool, status: str
) -> None:
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(
            (
                RecognizedText("Chats", TextBox(20, 35, 60, 16), 0.90),
                RecognizedText("My Mother", TextBox(89, 251, 110, 18), 0.92),
                RecognizedText("8:12", TextBox(600, 251, 42, 16), 0.82),
                RecognizedText("Hello", TextBox(89, 278, 60, 15), 0.88),
                RecognizedText("My Mother", TextBox(350, 275, 110, 16), 0.74),
                RecognizedText("My Mother", TextBox(69, 747, 110, 18), 0.96),
                *(
                    (RecognizedText("7:30", TextBox(600, 747, 42, 16), 0.84),)
                    if second_time_visible
                    else ()
                ),
                RecognizedText("Yesterday", TextBox(69, 775, 80, 15), 0.85),
            ),
            "eng", OcrDevice.CPU, "fake",
        ),
        (1853, 1048),
    )
    assessment = assess_visible_chat_choices(
        observation, "telegram.desktop", 123, "my mother"
    )
    assert assessment.status == status
    assert assessment.choices is not None
    assert tuple(item.top for item in assessment.choices.local_results) == (251, 747)


def test_missing_time_fallback_never_promotes_previous_rows_preview() -> None:
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(
            (
                RecognizedText("My Mother", TextBox(69, 200, 110, 18), 0.95),
                RecognizedText("8:12", TextBox(600, 200, 42, 16), 0.82),
                RecognizedText("My Mother", TextBox(69, 227, 110, 18), 0.95),
                RecognizedText("second", TextBox(69, 254, 60, 15), 0.88),
            ),
            "eng", OcrDevice.CPU, "fake",
        ),
        (1853, 1048),
    )
    assessment = assess_visible_chat_choices(
        observation, "telegram.desktop", 123, "my mother"
    )
    assert assessment.choices is None
    assert assessment.status == "rows_2_low_0_time_1_preview_0"


def test_visible_chat_does_not_ignore_a_second_unclassified_name() -> None:
    observation = IdentifiedWindowText(
        "telegram.desktop", 123,
        OcrResult(
            (
                RecognizedText("Search", TextBox(60, 45, 70, 16), 0.90),
                RecognizedText("My", TextBox(70, 200, 25, 18), 0.92),
                RecognizedText("Mother", TextBox(100, 200, 65, 18), 0.91),
                RecognizedText("8:12", TextBox(455, 200, 42, 16), 0.82),
                RecognizedText("Hello", TextBox(70, 227, 60, 15), 0.88),
                RecognizedText("Alice", TextBox(70, 280, 55, 18), 0.90),
                RecognizedText("7:30", TextBox(455, 280, 42, 16), 0.84),
                RecognizedText("My", TextBox(70, 307, 25, 15), 0.92),
                RecognizedText("Mother", TextBox(100, 307, 65, 15), 0.91),
            ),
            "eng", OcrDevice.CPU, "fake",
        ),
        (1600, 900),
    )
    assert (
        visible_chat_choices(observation, "telegram.desktop", 123, "My Mother")
        is None
    )


def test_left_label_requires_unique_title_in_expected_telegram_window() -> None:
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(
            (RecognizedText("Settings", TextBox(75, 92, 95, 24), 0.91),),
            "eng",
            OcrDevice.CPU,
            "fake",
        ),
        (1600, 900),
    )
    assert (
        telegram_left_label(observation, "telegram.desktop", 123, "settings", menu=True)
        is not None
    )
    assert (
        telegram_left_label(observation, "other.desktop", 123, "Settings", menu=True)
        is None
    )
    assert telegram_menu_item(observation, "telegram.desktop", 123, "Settings") is None


def test_menu_item_needs_a_second_menu_label_in_same_frame() -> None:
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(
            (
                RecognizedText("Settings", TextBox(75, 150, 95, 24), 0.91),
                RecognizedText("New", TextBox(75, 92, 45, 24), 0.90),
                RecognizedText("Group", TextBox(126, 92, 65, 24), 0.90),
            ),
            "eng",
            OcrDevice.CPU,
            "fake",
        ),
        (1600, 900),
    )
    assert telegram_menu_item(observation, "telegram.desktop", 123, "Settings")


def test_menu_item_rejects_chat_named_settings_without_menu_context() -> None:
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(
            (RecognizedText("Settings", TextBox(75, 100, 90, 22), 0.9),),
            "eng",
            OcrDevice.CPU,
            "fake",
        ),
        (1600, 900),
    )
    assert telegram_menu_item(observation, "telegram.desktop", 123, "Settings") is None
    assert not telegram_view_title_visible(
        observation, "telegram.desktop", 123, "Settings"
    )


def test_settings_item_requires_heading_unique_row_and_same_window() -> None:
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(
            (
                RecognizedText("Settings", TextBox(510, 45, 95, 24), 0.91),
                RecognizedText("Privacy", TextBox(540, 205, 75, 24), 0.91),
                RecognizedText("and", TextBox(620, 205, 35, 24), 0.91),
                RecognizedText("Security", TextBox(660, 205, 85, 24), 0.91),
            ),
            "eng",
            OcrDevice.CPU,
            "fake",
        ),
        (1600, 900),
    )
    assert telegram_settings_item(
        observation, "telegram.desktop", 123, "Privacy and Security"
    ) is not None
    assert telegram_settings_item(
        observation, "telegram.desktop", 123, "privacyandsecurity"
    ) is not None
    assert telegram_view_title_visible(observation, "telegram.desktop", 123, "Settings")
    assert telegram_settings_item(
        observation, "other.desktop", 123, "Privacy and Security"
    ) is None
    assert telegram_settings_item(
        observation, "telegram.desktop", 123, "Language"
    ) is None


def test_settings_header_distinguishes_nested_page_from_root() -> None:
    def observation(title: str) -> IdentifiedWindowText:
        return IdentifiedWindowText(
            "telegram.desktop",
            123,
            OcrResult(
                (
                    RecognizedText("<", TextBox(750, 86, 12, 14), 0.42),
                    RecognizedText(title, TextBox(790, 86, 90, 16), 0.97),
                    RecognizedText("Connection", TextBox(790, 174, 85, 15), 0.9),
                ),
                "eng",
                OcrDevice.CPU,
                "fake",
            ),
            (1853, 1048),
        )

    assert (
        telegram_settings_header(observation("Advanced"), "telegram.desktop", 123)
        == "advanced"
    )
    assert (
        telegram_settings_header(observation("Settings"), "telegram.desktop", 123)
        == "settings"
    )
    assert (
        telegram_settings_header(observation("Advanced"), "other.desktop", 123)
        is None
    )


def test_search_query_requires_exact_text_in_left_input_field() -> None:
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(
            (
                RecognizedText("My", TextBox(60, 42, 26, 13), 0.05),
                RecognizedText("Mother", TextBox(91, 42, 58, 13), 0.08),
                RecognizedText("My", TextBox(68, 182, 26, 13), 0.95),
                RecognizedText("Mother", TextBox(99, 182, 58, 13), 0.95),
            ),
            "eng",
            OcrDevice.CPU,
            "fake",
        ),
        (1600, 900),
    )
    assert telegram_search_query_visible(
        observation, "telegram.desktop", 123, "my mother"
    )
    assert not telegram_search_query_visible(
        observation, "other.desktop", 123, "my mother"
    )
    assert not telegram_search_query_visible(
        observation, "telegram.desktop", 123, "alice"
    )


def test_chat_title_matching_ignores_latin_letter_case() -> None:
    spans = (
        RecognizedText("My", TextBox(700, 40, 35, 24), 0.9),
        RecognizedText("Mother", TextBox(742, 40, 85, 24), 0.9),
    )
    header = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(spans, "eng", OcrDevice.CPU, "fake"),
        (1600, 900),
    )
    search = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(
            (
                RecognizedText("MY", TextBox(60, 45, 35, 13), 0.9),
                RecognizedText("mother", TextBox(102, 45, 85, 13), 0.9),
                RecognizedText("My", TextBox(60, 92, 35, 13), 0.9),
                RecognizedText("Mother", TextBox(102, 92, 85, 13), 0.9),
            ),
            "eng",
            OcrDevice.CPU,
            "fake",
        ),
        (1600, 900),
    )

    assert chat_header_visible(header, "telegram.desktop", 123, "my mother")
    assert unique_search_result(search, "telegram.desktop", 123, "My Mother")


def test_search_result_requires_one_exact_left_pane_match() -> None:
    observation = _observation(left=60, top=92, query=True)
    match = unique_search_result(observation, "telegram.desktop", 123, "Saved Messages")
    assert match is not None
    assert (match.left, match.top, match.image_width, match.image_height) == (
        60,
        92,
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
    assert (
        unique_search_result(
            _observation(left=60, top=92), "telegram.desktop", 123, "Saved Messages"
        )
        is None
    )


def test_search_result_rejects_ocr_without_confidence() -> None:
    original = _observation(left=60, top=92, query=True)
    no_score = IdentifiedWindowText(
        original.platform_app_id,
        original.process_id,
        OcrResult(
            tuple(
                RecognizedText(span.text, span.box, None)
                for span in original.result.spans
            ),
            "eng",
            OcrDevice.CPU,
            "paddle_vl16",
        ),
        original.image_size,
    )
    assert (
        unique_search_result(no_score, "telegram.desktop", 123, "Saved Messages")
        is None
    )


def test_search_result_rejects_ambiguous_matches() -> None:
    observation = _observation(left=60, top=92, duplicate=True, query=True)
    choices = search_choices(observation, "telegram.desktop", 123, "Saved Messages")
    assert choices is not None
    assert choices.own_chat is not None
    assert tuple(item.top for item in choices.global_results) == (200,)
    assert (
        unique_search_result(observation, "telegram.desktop", 123, "Saved Messages")
        == choices.own_chat
    )

    observation = _observation(left=60, top=92, query=True)
    spans = observation.result.spans + (
        RecognizedText("Saved", TextBox(250, 95, 60, 13), 0.9),
        RecognizedText("Messages", TextBox(317, 95, 105, 13), 0.9),
    )
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(spans, "eng", OcrDevice.CPU, "fake"),
        (1600, 900),
    )
    assert (
        unique_search_result(observation, "telegram.desktop", 123, "Saved Messages")
        is None
    )


def test_search_result_rejects_global_results_without_first_chat_row() -> None:
    observation = _observation(left=60, top=182, query=True)
    choices = search_choices(observation, "telegram.desktop", 123, "Saved Messages")
    assert choices is not None
    assert choices.own_chat is None
    assert tuple(item.top for item in choices.global_results) == (182,)
    assert (
        unique_search_result(observation, "telegram.desktop", 123, "Saved Messages")
        is None
    )


def test_observed_telegram_geometry_keeps_global_rows_numbered() -> None:
    rows = (45, 92, 182, 244, 368, 492)
    spans = tuple(
        word
        for top in rows
        for word in (
            RecognizedText("My", TextBox(67, top, 17, 13), 0.92),
            RecognizedText("Mother", TextBox(91, top, 44, 13), 0.90),
        )
    )
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(spans, "eng", OcrDevice.CPU, "fake"),
        (1853, 1048),
    )
    choices = search_choices(observation, "telegram.desktop", 123, "my mother")
    assert choices is not None
    assert choices.own_chat is not None
    assert choices.own_chat.top == 92
    assert tuple(row.top for row in choices.global_results) == (182, 244, 368, 492)
    assert (
        unique_search_result(observation, "telegram.desktop", 123, "My Mother")
        == choices.own_chat
    )


def test_low_confidence_query_still_locates_high_confidence_rows() -> None:
    spans = (
        RecognizedText("My", TextBox(67, 42, 17, 13), 0.05),
        RecognizedText("Mother", TextBox(91, 42, 44, 13), 0.08),
        RecognizedText("My", TextBox(69, 92, 17, 13), 0.94),
        RecognizedText("Mother", TextBox(91, 92, 44, 13), 0.95),
        RecognizedText("My", TextBox(155, 244, 17, 13), 0.94),
        RecognizedText("Mother", TextBox(177, 244, 44, 13), 0.95),
    )
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(spans, "eng", OcrDevice.CPU, "fake"),
        (1853, 1048),
    )
    choices = search_choices(observation, "telegram.desktop", 123, "my mother")
    assert choices is not None
    assert choices.own_chat is not None
    assert tuple(row.top for row in choices.global_results) == (244,)


def test_missing_query_ocr_can_use_unique_first_chat_row() -> None:
    spans = (
        RecognizedText("My", TextBox(69, 92, 17, 13), 0.94),
        RecognizedText("Mother", TextBox(91, 92, 44, 13), 0.95),
        RecognizedText("My", TextBox(155, 244, 17, 13), 0.94),
        RecognizedText("Mother", TextBox(177, 244, 44, 13), 0.95),
    )
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(spans, "eng", OcrDevice.CPU, "fake"),
        (1853, 1048),
    )
    choices = search_choices(observation, "telegram.desktop", 123, "my mother")
    assert choices is not None
    assert choices.own_chat is not None
    assert tuple(row.top for row in choices.global_results) == (244,)


def test_two_local_chats_are_separated_from_global_results_by_section_header() -> None:
    spans = (
        RecognizedText("My", TextBox(67, 42, 17, 13), 0.9),
        RecognizedText("Mother", TextBox(91, 42, 44, 13), 0.9),
        RecognizedText("My", TextBox(69, 92, 17, 13), 0.94),
        RecognizedText("Mother", TextBox(91, 92, 44, 13), 0.95),
        RecognizedText("My", TextBox(69, 154, 17, 13), 0.94),
        RecognizedText("Mother", TextBox(91, 154, 44, 13), 0.95),
        RecognizedText("Search", TextBox(63, 210, 40, 13), 0.9),
        RecognizedText("Results", TextBox(109, 210, 45, 13), 0.9),
        RecognizedText("My", TextBox(87, 244, 17, 13), 0.94),
        RecognizedText("Mother", TextBox(109, 244, 44, 13), 0.95),
    )
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(spans, "eng", OcrDevice.CPU, "fake"),
        (1853, 1048),
    )
    choices = search_choices(observation, "telegram.desktop", 123, "My Mother")
    assert choices is not None
    assert tuple(row.top for row in choices.local_results) == (92, 154)
    assert tuple(row.top for row in choices.global_results) == (244,)
    assert (
        unique_search_result(observation, "telegram.desktop", 123, "My Mother") is None
    )


def test_three_adjacent_local_chats_survive_missing_section_header() -> None:
    rows = ((45, 67), (92, 69), (154, 70), (216, 68), (306, 155))
    spans = tuple(
        word
        for top, left in rows
        for word in (
            RecognizedText("My", TextBox(left, top, 17, 13), 0.92),
            RecognizedText("Mother", TextBox(left + 24, top, 44, 13), 0.91),
        )
    )
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(spans, "eng", OcrDevice.CPU, "fake"),
        (1853, 1048),
    )
    choices = search_choices(observation, "telegram.desktop", 123, "My Mother")
    assert choices is not None
    assert tuple(row.top for row in choices.local_results) == (92, 154, 216)
    assert tuple(row.top for row in choices.global_results) == (306,)
    assert (
        unique_search_result(observation, "telegram.desktop", 123, "My Mother") is None
    )


def test_preview_text_is_not_numbered_as_a_second_chat() -> None:
    rows = ((45, 67), (92, 89), (116, 350), (154, 69), (244, 87))
    spans = tuple(
        word
        for top, left in rows
        for word in (
            RecognizedText("My", TextBox(left, top, 17, 13), 0.93),
            RecognizedText("Mother", TextBox(left + 24, top, 44, 13), 0.92),
        )
    ) + (RecognizedText("results", TextBox(100, 203, 50, 13), 0.9),)
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(spans, "eng", OcrDevice.CPU, "fake"),
        (1920, 1080),
    )
    choices = search_choices(observation, "telegram.desktop", 123, "My Mother")
    assert choices is not None
    assert tuple(row.top for row in choices.local_results) == (92, 154)
    assert tuple(row.top for row in choices.global_results) == (244,)
    assert choices.global_section_verified


def test_global_only_results_require_visible_section_heading() -> None:
    spans = (
        RecognizedText("My", TextBox(67, 45, 17, 13), 0.93),
        RecognizedText("Mother", TextBox(91, 45, 44, 13), 0.92),
        RecognizedText("results", TextBox(100, 203, 50, 13), 0.90),
        RecognizedText("My", TextBox(87, 244, 17, 13), 0.93),
        RecognizedText("Mother", TextBox(111, 244, 44, 13), 0.92),
    )
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(spans, "eng", OcrDevice.CPU, "fake"),
        (1920, 1080),
    )
    choices = search_choices(observation, "telegram.desktop", 123, "My Mother")
    assert choices is not None
    assert choices.local_results == ()
    assert tuple(row.top for row in choices.global_results) == (244,)
    assert choices.global_section_verified

    without_heading = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(spans[3:], "eng", OcrDevice.CPU, "fake"),
        (1920, 1080),
    )
    assert search_choices(without_heading, "telegram.desktop", 123, "My Mother") is None

    missed_query = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(spans[2:], "eng", OcrDevice.CPU, "fake"),
        (1920, 1080),
    )
    choices = search_choices(missed_query, "telegram.desktop", 123, "My Mother")
    assert choices is not None
    assert choices.local_results == ()
    assert tuple(row.top for row in choices.global_results) == (244,)
    assert choices.global_section_verified


def test_header_rejects_two_matching_titles_in_right_header() -> None:
    observation = _observation()
    spans = observation.result.spans + (
        RecognizedText("Saved", TextBox(1000, 40, 60, 24), 0.9),
        RecognizedText("Messages", TextBox(1067, 40, 105, 24), 0.9),
    )
    duplicate_header = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(spans, "eng", OcrDevice.CPU, "fake"),
        (1600, 900),
    )
    assert not saved_messages_header_visible(duplicate_header, "telegram.desktop", 123)


def test_persian_search_result_uses_right_to_left_word_positions() -> None:
    observation = IdentifiedWindowText(
        "telegram.desktop",
        123,
        OcrResult(
            (
                RecognizedText("آموزش", TextBox(270, 45, 80, 13), 0.91),
                RecognizedText("هوش", TextBox(207, 45, 52, 13), 0.90),
                RecognizedText("مصنوعی", TextBox(104, 45, 90, 13), 0.89),
                RecognizedText("آموزش", TextBox(270, 92, 80, 13), 0.91),
                RecognizedText("هوش", TextBox(207, 92, 52, 13), 0.90),
                RecognizedText("مصنوعی", TextBox(104, 92, 90, 13), 0.89),
            ),
            "fas+eng",
            OcrDevice.CPU,
            "fake",
        ),
        (1600, 900),
    )
    match = unique_search_result(
        observation, "telegram.desktop", 123, "آموزش هوش مصنوعی"
    )
    assert match is not None
    assert (match.left, match.top, match.width) == (104, 92, 246)
