"""Conservative OCR checks for Telegram chat navigation."""

from dataclasses import dataclass
from hashlib import sha256

from kyrin.vision.text_reader import IdentifiedWindowText
from kyrin.vision.text_targets import VisiblePhrase, find_exact_phrases


@dataclass(frozen=True, slots=True)
class ChatSearchMatch:
    """A single visible result in window-image coordinates, not a click grant."""

    left: int
    top: int
    width: int
    height: int
    image_width: int
    image_height: int


@dataclass(frozen=True, slots=True)
class ChatSearchChoices:
    """Observed local and global rows; no choice authorizes a click."""

    own_chat: ChatSearchMatch | None
    global_results: tuple[ChatSearchMatch, ...]
    other_local_results: tuple[ChatSearchMatch, ...] = ()
    global_section_verified: bool = False
    view_signature: str = ""

    @property
    def local_results(self) -> tuple[ChatSearchMatch, ...]:
        return (
            (self.own_chat, *self.other_local_results)
            if self.own_chat is not None
            else ()
        )

    @property
    def selectable_results(self) -> tuple[ChatSearchMatch, ...]:
        return self.local_results or self.global_results


def _same_window(
    observation: IdentifiedWindowText, expected_app_id: str, expected_pid: int
) -> bool:
    return (
        observation.platform_app_id == expected_app_id
        and observation.process_id == expected_pid
        and observation.image_size is not None
    )


def search_choices(
    observation: IdentifiedWindowText,
    expected_app_id: str,
    expected_pid: int,
    target: str,
) -> ChatSearchChoices | None:
    """Separate local and global rows, tolerating a missed query OCR read."""
    if not _same_window(observation, expected_app_id, expected_pid):
        return None
    assert observation.image_size is not None
    width, height = observation.image_size
    # A short digest lets bounded paging detect an unchanged results viewport
    # without retaining OCR text or message previews in selection state.
    visible_text = "\n".join(
        f"{span.box.top // 4}:{span.text}"
        for span in observation.result.spans
        if span.box.left < width * 0.3
        and height * 0.075 < span.box.top < height * 0.75
        and span.confidence is not None
        and span.confidence >= 0.65
    )
    view_signature = sha256(visible_text.encode("utf-8")).hexdigest()
    visible = [
        match
        for match in find_exact_phrases(observation.result, target)
        if match.lowest_confidence is not None
        and match.box.left >= 0
        and match.box.left + match.box.width < width * 0.3
    ]
    # The query is text KYRIN just typed. Its OCR confidence can be low even
    # when the exact phrase is visible; row confidence stays stricter below.
    queries = [match for match in visible if match.box.top < height * 0.075]
    if len(queries) > 1:
        return None
    matches = [
        match
        for match in visible
        if match.lowest_confidence is not None and match.lowest_confidence >= 0.75
    ]
    query_bottom = queries[0].box.top + queries[0].box.height if queries else None
    section_headers = [
        match
        for match in find_exact_phrases(observation.result, "Search Results")
        if height * 0.1 < match.box.top < height * 0.75 and match.box.left < width * 0.3
    ]
    if not section_headers:
        # Telegram may render "Global Search Results" while OCR keeps only
        # its final word. The heading starts close to the left edge.
        section_headers = [
            match
            for match in find_exact_phrases(observation.result, "Results")
            if match.lowest_confidence is not None
            and match.lowest_confidence >= 0.65
            and height * 0.1 < match.box.top < height * 0.75
            and match.box.left < width * 0.15
        ]
    section_top = min((match.box.top for match in section_headers), default=None)
    row_candidates = sorted(
        (
            match
            for match in matches
            if height * 0.075 < match.box.top < height * 0.75
            and width * 0.025 <= match.box.left < width * 0.15
            and (query_bottom is None or query_bottom + height * 0.015 < match.box.top)
        ),
        key=lambda match: match.box.top,
    )
    # Two titles in the same row are ambiguous. Text farther right and below
    # a title belongs to its preview, not to another numbered chat.
    if any(
        abs(other.box.top - title.box.top) < height * 0.012
        and abs(other.box.left - title.box.left) > width * 0.04
        for title in row_candidates
        for other in matches
        if other is not title
    ):
        return None
    if section_top is not None:
        local_candidates = [
            match for match in row_candidates if match.box.top < section_top
        ]
    else:
        # When OCR misses the section title, a fixed top-of-window cutoff
        # hides the second or third local chat. Extend the first row only
        # through adjacent, similarly aligned result rows.
        local_candidates = []
        for match in row_candidates:
            if not local_candidates:
                if match.box.top < height * 0.16:
                    local_candidates.append(match)
                continue
            previous = local_candidates[-1]
            if (
                match.box.top - previous.box.top <= height * 0.07
                and abs(match.box.left - local_candidates[0].box.left) <= width * 0.04
            ):
                local_candidates.append(match)
            else:
                break
    if not queries and not local_candidates and section_top is None:
        return None
    globals_ = sorted(
        (
            match
            for match in matches
            if match.box.left < width * 0.15
            and (
                (section_top is not None and match.box.top > section_top)
                or (
                    section_top is None
                    and match not in local_candidates
                    and match.box.top >= height * 0.16
                )
            )
        ),
        key=lambda match: match.box.top,
    )
    if any(
        second.box.top - first.box.top < height * 0.025
        for first, second in zip(globals_, globals_[1:], strict=False)
    ):
        return None

    def as_box(match: VisiblePhrase) -> ChatSearchMatch:
        box = match.box
        return ChatSearchMatch(box.left, box.top, box.width, box.height, width, height)

    return ChatSearchChoices(
        as_box(local_candidates[0]) if local_candidates else None,
        tuple(as_box(match) for match in globals_),
        tuple(as_box(match) for match in local_candidates[1:]),
        section_top is not None,
        view_signature,
    )


def unique_search_result(
    observation: IdentifiedWindowText,
    expected_app_id: str,
    expected_pid: int,
    target: str,
) -> ChatSearchMatch | None:
    """Auto-select only when no lower result needs a user choice."""
    if observation.image_size is None:
        return None
    width, height = observation.image_size
    if not any(
        match.box.left >= 0
        and match.box.left + match.box.width < width * 0.3
        and match.box.top < height * 0.075
        for match in find_exact_phrases(observation.result, target)
    ):
        return None
    choices = search_choices(observation, expected_app_id, expected_pid, target)
    if choices is None or len(choices.local_results) != 1:
        return None
    return choices.local_results[0]


def chat_header_visible(
    observation: IdentifiedWindowText,
    expected_app_id: str,
    expected_pid: int,
    target: str,
) -> bool:
    """Confirm one exact title in the upper right chat pane."""
    if not _same_window(observation, expected_app_id, expected_pid):
        return False
    assert observation.image_size is not None
    width, height = observation.image_size
    matches = [
        match
        for match in find_exact_phrases(observation.result, target)
        if match.lowest_confidence is not None
        and match.lowest_confidence >= 0.65
        and match.box.left >= width * 0.3
        and match.box.top <= height * 0.2
    ]
    return len(matches) == 1


def saved_messages_header_visible(
    observation: IdentifiedWindowText, expected_app_id: str, expected_pid: int
) -> bool:
    """Confirm one clear title in Telegram's upper chat pane, not a sidebar name."""
    return chat_header_visible(
        observation, expected_app_id, expected_pid, "Saved Messages"
    )


def telegram_left_label(
    observation: IdentifiedWindowText,
    expected_app_id: str,
    expected_pid: int,
    label: str,
    *,
    menu: bool = False,
) -> ChatSearchMatch | None:
    """Locate exactly one title in Telegram's left pane or open main menu."""
    if not _same_window(observation, expected_app_id, expected_pid):
        return None
    assert observation.image_size is not None
    width, height = observation.image_size
    matches = [
        match
        for match in find_exact_phrases(observation.result, label)
        if match.lowest_confidence is not None
        and match.lowest_confidence >= 0.65
        and width * 0.025 <= match.box.left
        and match.box.left + match.box.width < width * 0.3
        and height * (0.07 if menu else 0.025)
        < match.box.top
        < height * (0.75 if menu else 0.22)
    ]
    if len(matches) != 1:
        return None
    box = matches[0].box
    return ChatSearchMatch(box.left, box.top, box.width, box.height, width, height)


def telegram_menu_item(
    observation: IdentifiedWindowText,
    expected_app_id: str,
    expected_pid: int,
    label: str,
) -> ChatSearchMatch | None:
    """Require another main-menu label in the same frame before a menu click."""
    target = telegram_left_label(
        observation, expected_app_id, expected_pid, label, menu=True
    )
    if target is None:
        return None
    anchors = (
        "New Group",
        "New Channel",
        "My Profile",
        "Contacts",
        "Calls",
        "Settings",
        "Saved Messages",
    )
    if not any(
        telegram_left_label(
            observation, expected_app_id, expected_pid, anchor, menu=True
        )
        is not None
        for anchor in anchors
        if anchor != label
    ):
        return None
    return target


def telegram_settings_item(
    observation: IdentifiedWindowText,
    expected_app_id: str,
    expected_pid: int,
    label: str,
) -> ChatSearchMatch | None:
    """Find one settings row only beneath a visible Settings heading."""
    if not _same_window(observation, expected_app_id, expected_pid):
        return None
    assert observation.image_size is not None
    width, height = observation.image_size
    headings = [
        item for item in find_exact_phrases(observation.result, "Settings")
        if item.lowest_confidence is not None
        and item.lowest_confidence >= 0.65
        and item.box.top < height * 0.2
        and item.box.left >= width * 0.25
    ]
    if len(headings) != 1:
        return None
    matches = [
        item for item in find_exact_phrases(observation.result, label)
        if item.lowest_confidence is not None
        and item.lowest_confidence >= 0.70
        and width * 0.25 <= item.box.left
        and item.box.left + item.box.width < width * 0.9
        and headings[0].box.top + headings[0].box.height < item.box.top
        and item.box.top < height * 0.86
    ]
    if len(matches) != 1:
        return None
    box = matches[0].box
    return ChatSearchMatch(box.left, box.top, box.width, box.height, width, height)


def telegram_view_title_visible(
    observation: IdentifiedWindowText,
    expected_app_id: str,
    expected_pid: int,
    title: str,
) -> bool:
    """Confirm one high-confidence title near the top of the same window."""
    if not _same_window(observation, expected_app_id, expected_pid):
        return False
    assert observation.image_size is not None
    width, height = observation.image_size
    return len([
        item for item in find_exact_phrases(observation.result, title)
        if item.lowest_confidence is not None
        and item.lowest_confidence >= 0.70
        and item.box.top < height * 0.2
        and item.box.left >= width * 0.25
    ]) == 1


def telegram_settings_header(
    observation: IdentifiedWindowText,
    expected_app_id: str,
    expected_pid: int,
) -> str | None:
    """Read the first word of a centered settings-page heading, not page rows."""
    if not _same_window(observation, expected_app_id, expected_pid):
        return None
    assert observation.image_size is not None
    width, height = observation.image_size
    headings = [
        span
        for span in observation.result.spans
        if span.confidence is not None
        and span.confidence >= 0.65
        and height * 0.06 < span.box.top < height * 0.12
        and width * 0.25 < span.box.left < width * 0.6
        and (word := span.text.strip("‘’'\".,:;!?"))
        and word[0].isalpha()
    ]
    if not headings:
        return None
    first = min(headings, key=lambda span: span.box.left)
    return first.text.strip("‘’'\".,:;!?").casefold()


def telegram_search_query_visible(
    observation: IdentifiedWindowText,
    expected_app_id: str,
    expected_pid: int,
    query: str,
) -> bool:
    """Check only the left search field; result-row text cannot confirm input."""
    if not _same_window(observation, expected_app_id, expected_pid):
        return False
    assert observation.image_size is not None
    width, height = observation.image_size
    return len([
        item for item in find_exact_phrases(observation.result, query)
        if 0 <= item.box.left
        and item.box.left + item.box.width < width * 0.3
        and item.box.top < height * 0.075
    ]) == 1
