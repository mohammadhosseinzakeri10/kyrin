"""Retention and deletion operate only on injected temporary databases."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kyrin.memory import history as memory


def _turn(index: int, when: datetime) -> memory.ConversationTurn:
    return memory.ConversationTurn(f"text {index}", "fa", when, "test", 0, index)


def test_retention_uses_injected_clock_and_independent_active_archive_limits(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 10, 24, tzinfo=UTC)
    policy = memory.HistoryRetention(
        active_max_turns=2,
        active_max_age_days=2,
        archived_max_turns=2,
        archived_max_age_days=10,
    )
    history = memory.SqliteConversationHistory(
        tmp_path / "history.sqlite3", retention=policy, clock=lambda: now
    )
    try:
        for index in range(3):
            history.append(_turn(index, now))
            history.archive_active()
        assert history.archived_count() == 2
        for index in range(3, 6):
            history.append(_turn(index, now))
        assert [turn.text for turn in history.recent()] == ["text 4", "text 5"]
        now += timedelta(days=2)
        assert len(history.recent()) == 2  # cutoff equality is retained
        now += timedelta(microseconds=1)
        assert history.recent() == ()
        assert history.archived_count() == 2
        now += timedelta(days=8)
        assert history.archived_page() == ()
    finally:
        history.close()


def test_opening_existing_database_does_not_prune_but_explicit_retention_does(
    tmp_path: Path,
) -> None:
    path = tmp_path / "history.sqlite3"
    now = datetime(2026, 10, 24, tzinfo=UTC)
    history = memory.SqliteConversationHistory(path)
    for index, age in enumerate((40, 10, 5)):
        history.append(_turn(index, now - timedelta(days=age)))
    history.archive_active()
    for index, age in enumerate((9, 2, 0), start=3):
        history.append(_turn(index, now - timedelta(days=age)))
    history.close()
    before = path.read_bytes()
    policy = memory.HistoryRetention(
        active_max_turns=1,
        active_max_age_days=3,
        archived_max_turns=2,
        archived_max_age_days=20,
    )
    history = memory.SqliteConversationHistory(
        path, retention=policy, clock=lambda: now
    )
    try:
        assert path.read_bytes() == before
        history.apply_retention()
        assert [turn.text for turn in history.recent()] == ["text 5"]
        assert [turn.text for turn in history.archived_page()] == ["text 2", "text 1"]
    finally:
        history.close()


def test_archive_delete_active_and_delete_all_have_distinct_scopes(
    tmp_path: Path,
) -> None:
    history = memory.SqliteConversationHistory(tmp_path / "history.sqlite3")
    try:
        now = datetime.now(UTC)
        history.append(_turn(0, now))
        assert history.archive_active() == 1
        assert history.recent() == ()
        assert history.archived_count() == 1
        history.append(_turn(1, now))
        history.clear_active()
        assert history.recent() == ()
        assert history.archived_count() == 1
        history.append(_turn(2, now))
        history.clear_all()
        assert history.recent() == ()
        assert history.archived_count() == 0
    finally:
        history.close()


def test_restoring_cannot_evict_active_text_or_revive_expired_text(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 10, 24, tzinfo=UTC)
    history = memory.SqliteConversationHistory(
        tmp_path / "history.sqlite3",
        retention=memory.HistoryRetention(active_max_turns=1, active_max_age_days=2),
        clock=lambda: now,
    )
    try:
        history.append(_turn(0, now))
        history.archive_active()
        history.append(_turn(1, now))
        archived = history.archived_page()[0]
        with pytest.raises(ValueError, match="active limit"):
            history.restore_archived_turn(archived.id)
        assert [turn.text for turn in history.recent()] == ["text 1"]
        now += timedelta(days=3)
        with pytest.raises(ValueError, match="age"):
            history.restore_archived_turn(archived.id)
        assert history.archived_count() == 1
        assert history.recent() == ()
    finally:
        history.close()


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2"])
@pytest.mark.parametrize(
    "field",
    [
        "active_max_turns",
        "active_max_age_days",
        "archived_max_turns",
        "archived_max_age_days",
    ],
)
def test_retention_rejects_invalid_limits(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        memory.HistoryRetention(**{field: value})  # type: ignore[arg-type]
