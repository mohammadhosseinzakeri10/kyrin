"""Complete chat contract for tests that implement only their expected operations."""

from kyrin.actions.telegram_verification import ChatSearchChoices, ChatSearchMatch
from kyrin.actions.visible_control import VisibleControlTarget, VisibleTextOption


class StubChatVerifier:
    def ready(self) -> bool:
        raise AssertionError("Unexpected chat verification call: ready")

    def list_visible_text(self, app_id: str, pid: int) -> tuple[VisibleTextOption, ...]:
        raise AssertionError("Unexpected chat verification call: list_visible_text")

    def find_visible_control(
        self, app_id: str, pid: int, label: str
    ) -> VisibleControlTarget | None:
        raise AssertionError("Unexpected chat verification call: find_visible_control")

    def find_search_result(
        self, app_id: str, pid: int, target: str
    ) -> ChatSearchMatch | None:
        raise AssertionError("Unexpected chat verification call: find_search_result")

    def find_search_choices(
        self, app_id: str, pid: int, target: str
    ) -> ChatSearchChoices | None:
        raise AssertionError("Unexpected chat verification call: find_search_choices")

    def find_visible_chat_choices(
        self, app_id: str, pid: int, target: str
    ) -> ChatSearchChoices | None:
        raise AssertionError(
            "Unexpected chat verification call: find_visible_chat_choices"
        )

    def choice_status(self) -> str:
        raise AssertionError("Unexpected chat verification call: choice_status")

    def verify(self, app_id: str, pid: int, target: str = "Saved Messages") -> bool:
        raise AssertionError("Unexpected chat verification call: verify")

    def find_left_label(
        self, app_id: str, pid: int, label: str, *, menu: bool = False
    ) -> ChatSearchMatch | None:
        raise AssertionError("Unexpected chat verification call: find_left_label")

    def find_settings_item(
        self, app_id: str, pid: int, label: str
    ) -> ChatSearchMatch | None:
        raise AssertionError("Unexpected chat verification call: find_settings_item")

    def settings_page_header(self, app_id: str, pid: int) -> str | None:
        raise AssertionError("Unexpected chat verification call: settings_page_header")

    def has_view_title(self, app_id: str, pid: int, title: str) -> bool:
        raise AssertionError("Unexpected chat verification call: has_view_title")

    def has_search_query(self, app_id: str, pid: int, query: str) -> bool:
        raise AssertionError("Unexpected chat verification call: has_search_query")
