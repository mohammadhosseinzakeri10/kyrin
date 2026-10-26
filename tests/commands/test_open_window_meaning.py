"""Overview fast path combines meaning slots, not full sentence equality."""

import pytest

from kyrin.commands.open_window_meaning import requests_open_window_overview


@pytest.mark.parametrize(("spoken", "language"), (
    ("Show all open windows", "en"),
    ("Could you display every running application?", "en"),
    ("Let me see all my windows", "en"),
    ("Show all open app", "en"),
    ("Can you show all active applications?", "en"),
    ("List the currently running apps", "en"),
    ("همهٔ پنجره‌های باز را نشان بده", "fa"),
    ("تمام صفحات برنامه‌های باز را نشان بده", "fa"),
    ("تمام برنامه‌های فعال را نمایش دهید", "fa"),
))
def test_different_wording_can_express_same_window_overview(
    spoken: str, language: str
) -> None:
    assert requests_open_window_overview(spoken, language)


@pytest.mark.parametrize(("spoken", "language"), (
    ("Show all installed apps", "en"),
    ("Show all browser tabs", "en"),
    ("Don't show all open windows", "en"),
    ("Show every app", "en"),
    ("Show all windows and close Telegram", "en"),
    ("همه برنامه‌های نصب‌شده را نشان بده", "fa"),
    ("همه پنجره‌ها را نشان نده", "fa"),
    ("لطفاً همه پنجره‌ها را نشان ندهید", "fa"),
    ("همه پنجره‌ها را نشان بده و تلگرام را باز کن", "fa"),
    ("تمام صفحات را نشان بده", "fa"),
))
def test_other_or_ambiguous_requests_are_not_fast_window_overview(
    spoken: str, language: str
) -> None:
    assert not requests_open_window_overview(spoken, language)
