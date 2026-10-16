from kyrin.actions.telegram_verification import (
    chat_header_visible,
    saved_messages_header_visible,
    search_choices,
    unique_search_result,
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
    assert not chat_header_visible(observation, "telegram.desktop", 123, "Alice")


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
        "telegram.desktop", 123,
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
        "telegram.desktop", 123,
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
        "telegram.desktop", 123,
        OcrResult(spans, "eng", OcrDevice.CPU, "fake"),
        (1853, 1048),
    )
    choices = search_choices(observation, "telegram.desktop", 123, "My Mother")
    assert choices is not None
    assert tuple(row.top for row in choices.local_results) == (92, 154)
    assert tuple(row.top for row in choices.global_results) == (244,)
    assert (
        unique_search_result(observation, "telegram.desktop", 123, "My Mother")
        is None
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
        "telegram.desktop", 123,
        OcrResult(spans, "eng", OcrDevice.CPU, "fake"),
        (1853, 1048),
    )
    choices = search_choices(observation, "telegram.desktop", 123, "My Mother")
    assert choices is not None
    assert tuple(row.top for row in choices.local_results) == (92, 154, 216)
    assert tuple(row.top for row in choices.global_results) == (306,)
    assert (
        unique_search_result(observation, "telegram.desktop", 123, "My Mother")
        is None
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
        "telegram.desktop", 123,
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
        "telegram.desktop", 123,
        OcrResult(spans, "eng", OcrDevice.CPU, "fake"),
        (1920, 1080),
    )
    choices = search_choices(observation, "telegram.desktop", 123, "My Mother")
    assert choices is not None
    assert choices.local_results == ()
    assert tuple(row.top for row in choices.global_results) == (244,)
    assert choices.global_section_verified

    without_heading = IdentifiedWindowText(
        "telegram.desktop", 123,
        OcrResult(spans[3:], "eng", OcrDevice.CPU, "fake"),
        (1920, 1080),
    )
    assert search_choices(
        without_heading, "telegram.desktop", 123, "My Mother"
    ) is None

    missed_query = IdentifiedWindowText(
        "telegram.desktop", 123,
        OcrResult(spans[2:], "eng", OcrDevice.CPU, "fake"),
        (1920, 1080),
    )
    choices = search_choices(
        missed_query, "telegram.desktop", 123, "My Mother"
    )
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
