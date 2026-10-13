"""The local history records text and never acts as an execution authority."""

import sqlite3
from datetime import UTC, datetime
from threading import Thread

from kyrin.memory.history import ConversationTurn, SqliteConversationHistory


def test_history_persists_bounded_final_text_and_can_be_cleared(tmp_path) -> None:
    path = tmp_path / "memory" / "conversation.sqlite3"
    history = SqliteConversationHistory(path, max_turns=2)
    for segment in range(3):
        history.append(
            ConversationTurn(
                f"utterance {segment}",
                "en",
                datetime.now(UTC),
                "session",
                0,
                segment,
            )
        )
    history.append(
        ConversationTurn("utterance 2", "en", datetime.now(UTC), "session", 0, 2)
    )
    assert [turn.text for turn in history.recent()] == ["utterance 1", "utterance 2"]
    history.close()
    assert path.stat().st_mode & 0o777 == 0o600

    reopened = SqliteConversationHistory(path)
    assert len(reopened.recent()) == 2
    reopened.clear()
    assert reopened.recent() == ()
    reopened.close()


def test_history_is_safe_across_ui_and_runtime_threads(tmp_path) -> None:
    history = SqliteConversationHistory(tmp_path / "conversation.sqlite3")
    errors: list[Exception] = []

    def use_on_runtime_thread() -> None:
        try:
            history.append(
                ConversationTurn(
                    "Open Telegram", "en", datetime.now(UTC), "session", 0, 0
                )
            )
            assert len(history.recent()) == 1
        except Exception as exc:
            errors.append(exc)

    worker = Thread(target=use_on_runtime_thread)
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert not errors
    history.close()


def test_legacy_history_can_be_archived_without_losing_turns(tmp_path) -> None:
    path = tmp_path / "conversation.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE turns (
                id INTEGER PRIMARY KEY, text TEXT NOT NULL, language TEXT,
                recorded_at TEXT NOT NULL, session_id TEXT NOT NULL,
                stream_id INTEGER NOT NULL, segment_id INTEGER NOT NULL,
                UNIQUE(session_id, stream_id, segment_id)
            )"""
        )
        connection.execute(
            "INSERT INTO turns (text, recorded_at, session_id, stream_id, segment_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("possibly real", datetime.now(UTC).isoformat(), "old", 0, 0),
        )

    history = SqliteConversationHistory(path, max_turns=1)
    assert history.archive_active() == 1
    assert history.archived_count() == 1
    assert history.recent() == ()
    history.append(ConversationTurn("new", "en", datetime.now(UTC), "new", 0, 0))
    assert [turn.text for turn in history.recent()] == ["new"]
    assert history.archived_count() == 1
    history.clear()
    assert history.recent() == ()
    assert history.archived_count() == 1
    history.close()

    reopened = SqliteConversationHistory(path, max_turns=2)
    assert reopened.archived_count() == 1
    assert reopened.restore_archived() == 1
    assert [turn.text for turn in reopened.recent()] == ["possibly real"]
    reopened.close()


def test_archived_turns_are_paged_and_restored_one_at_a_time(tmp_path) -> None:
    history = SqliteConversationHistory(tmp_path / "conversation.sqlite3", max_turns=3)
    for index in range(4):
        history.append(
            ConversationTurn(
                f"utterance {index}", "en", datetime.now(UTC), "old", 0, index
            )
        )
    assert history.archive_active() == 3
    newest = history.archived_page(limit=2)
    assert [turn.text for turn in newest] == ["utterance 3", "utterance 2"]
    assert [
        turn.text for turn in history.archived_page(limit=2, before_id=newest[-1].id)
    ] == ["utterance 1"]
    assert history.restore_archived_turn(newest[0].id)
    assert not history.restore_archived_turn(newest[0].id)
    assert [turn.text for turn in history.recent()] == ["utterance 3"]
    assert history.archived_count() == 2
    history.close()
