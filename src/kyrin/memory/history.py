"""Small, bounded conversation history independent of speech and command engines."""

import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    text: str
    language: str | None
    recorded_at: datetime
    session_id: str
    stream_id: int
    segment_id: int


@dataclass(frozen=True, slots=True)
class ArchivedTurn:
    id: int
    text: str
    language: str | None
    recorded_at: datetime


class ConversationHistory(Protocol):
    def append(self, turn: ConversationTurn) -> None: ...

    def recent(self, *, limit: int = 8) -> tuple[ConversationTurn, ...]: ...


@dataclass(frozen=True, slots=True)
class HistoryRetention:
    """Independent limits; None preserves text without an automatic limit.

    Age is measured from the original recorded_at, including after archive
    and restore. Count retains newest insertion IDs, matching recent().
    """

    active_max_turns: int | None = 2000
    active_max_age_days: int | None = None
    archived_max_turns: int | None = None
    archived_max_age_days: int | None = None

    def __post_init__(self) -> None:
        for value in (
            self.active_max_turns,
            self.active_max_age_days,
            self.archived_max_turns,
            self.archived_max_age_days,
        ):
            if value is not None and (type(value) is not int or value < 1):
                raise ValueError("history limits must be positive integers or null")
        for days in (self.active_max_age_days, self.archived_max_age_days):
            if days is not None and days > 365000:
                raise ValueError("history age limit must not exceed 365000 days")
        for count in (self.active_max_turns, self.archived_max_turns):
            if count is not None and count > 2147483647:
                raise ValueError("history count limit must not exceed 2147483647")

    def is_stricter_than(self, previous: HistoryRetention) -> bool:
        return any(
            new is not None and (old is None or new < old)
            for new, old in zip(
                (
                    self.active_max_turns,
                    self.active_max_age_days,
                    self.archived_max_turns,
                    self.archived_max_age_days,
                ),
                (
                    previous.active_max_turns,
                    previous.active_max_age_days,
                    previous.archived_max_turns,
                    previous.archived_max_age_days,
                ),
                strict=True,
            )
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def default_history_path() -> Path:
    """Use XDG data storage; the owner's XDG directory links to AI-Projects."""
    configured = os.environ.get("XDG_DATA_HOME")
    root = Path(configured) if configured else Path.home() / ".local" / "share"
    if not root.is_absolute():
        root = Path.home() / ".local" / "share"
    return root / "kyrin" / "memory" / "conversation.sqlite3"


class SqliteConversationHistory:
    """Persist finalized text only; reads are ordered and explicitly bounded."""

    def __init__(
        self,
        path: Path,
        *,
        max_turns: int = 2000,
        retention: HistoryRetention | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if type(max_turns) is not int or max_turns < 1:
            raise ValueError("max_turns must be positive")
        if retention is not None and max_turns != 2000:
            raise ValueError("supply retention or max_turns, not both")
        self._path = path
        self._retention = retention or HistoryRetention(active_max_turns=max_turns)
        self._clock = clock
        self._lock = Lock()
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.is_symlink():
            raise ValueError("conversation database must not be a symlink")
        if not path.exists():
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        elif not path.is_file():
            raise ValueError("conversation database must be a regular file")
        path.chmod(0o600)
        # The session is assembled on the UI thread and consumed on a worker.
        # Guard the one connection explicitly instead of relying on call order.
        self._connection = sqlite3.connect(path, timeout=2, check_same_thread=False)
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY,
                text TEXT NOT NULL,
                language TEXT,
                recorded_at TEXT NOT NULL,
                session_id TEXT NOT NULL,
                stream_id INTEGER NOT NULL,
                segment_id INTEGER NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0,
                UNIQUE(session_id, stream_id, segment_id)
            )"""
        )
        columns = {
            row[1] for row in self._connection.execute("PRAGMA table_info(turns)")
        }
        if "archived" not in columns:
            self._connection.execute(
                "ALTER TABLE turns ADD COLUMN archived INTEGER NOT NULL DEFAULT 0"
            )
        self._connection.commit()

    def append(self, turn: ConversationTurn) -> None:
        if not turn.text.strip():
            return
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT OR IGNORE INTO turns
                   (text, language, recorded_at, session_id, stream_id, segment_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    turn.text,
                    turn.language,
                    turn.recorded_at.astimezone(UTC).isoformat(),
                    turn.session_id,
                    turn.stream_id,
                    turn.segment_id,
                ),
            )
            self._prune_locked()

    def apply_retention(self) -> None:
        """Apply explicitly selected policy; opening/migrating alone never prunes."""
        with self._lock, self._connection:
            self._prune_locked()

    def _prune_locked(self) -> None:
        now = self._clock().astimezone(UTC)
        for archived, count, days in (
            (0, self._retention.active_max_turns, self._retention.active_max_age_days),
            (
                1,
                self._retention.archived_max_turns,
                self._retention.archived_max_age_days,
            ),
        ):
            if days is not None:
                # Compare normalized UTC timestamps without rounding to seconds.
                cutoff = (now - timedelta(days=days)).isoformat()
                self._connection.execute(
                    "DELETE FROM turns WHERE archived = ? AND recorded_at < ?",
                    (archived, cutoff),
                )
            if count is not None:
                self._connection.execute(
                    "DELETE FROM turns WHERE archived = ? AND id NOT IN "
                    "(SELECT id FROM turns WHERE archived = ? "
                    "ORDER BY id DESC LIMIT ?)",
                    (archived, archived, count),
                )

    def recent(self, *, limit: int = 8) -> tuple[ConversationTurn, ...]:
        if limit < 0 or limit > 50:
            raise ValueError("limit must be between 0 and 50")
        with self._lock, self._connection:
            self._prune_locked()
            rows = self._connection.execute(
                """SELECT text, language, recorded_at, session_id, stream_id, segment_id
                   FROM turns WHERE archived = 0 ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        turns = []
        for row in reversed(rows):
            text, language, recorded_at, session_id, stream_id, segment_id = row
            turns.append(
                ConversationTurn(
                    text,
                    language,
                    datetime.fromisoformat(recorded_at),
                    session_id,
                    stream_id,
                    segment_id,
                )
            )
        return tuple(turns)

    def archive_active(self) -> int:
        """Move text out of context, subject to the selected archive retention."""
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "UPDATE turns SET archived = 1 WHERE archived = 0"
            )
            changed = cursor.rowcount
            self._prune_locked()
            return changed

    def restore_archived(self) -> int:
        """Make archived turns available to bounded recent reads again."""
        with self._lock, self._connection:
            self._prune_locked()
            total = self._connection.execute("SELECT COUNT(*) FROM turns").fetchone()
            assert total is not None
            limit = self._retention.active_max_turns
            if limit is not None and total[0] > limit:
                raise ValueError("restoring archived turns exceeds the active limit")
            self._check_restore_age()
            cursor = self._connection.execute(
                "UPDATE turns SET archived = 0 WHERE archived = 1"
            )
            return cursor.rowcount

    def archived_count(self) -> int:
        with self._lock, self._connection:
            self._prune_locked()
            row = self._connection.execute(
                "SELECT COUNT(*) FROM turns WHERE archived = 1"
            ).fetchone()
        assert row is not None
        return int(row[0])

    def archived_page(
        self, *, limit: int = 50, before_id: int | None = None
    ) -> tuple[ArchivedTurn, ...]:
        """Read one newest-first page without activating archived text."""
        if limit < 1 or limit > 50:
            raise ValueError("limit must be between 1 and 50")
        if before_id is not None and before_id < 1:
            raise ValueError("before_id must be positive")
        with self._lock, self._connection:
            self._prune_locked()
            rows = self._connection.execute(
                """SELECT id, text, language, recorded_at FROM turns
                   WHERE archived = 1 AND (? IS NULL OR id < ?)
                   ORDER BY id DESC LIMIT ?""",
                (before_id, before_id, limit),
            ).fetchall()
        return tuple(
            ArchivedTurn(row[0], row[1], row[2], datetime.fromisoformat(row[3]))
            for row in rows
        )

    def restore_archived_turn(self, turn_id: int) -> bool:
        """Restore only the reviewed row, respecting the active history limit."""
        if turn_id < 1:
            raise ValueError("turn_id must be positive")
        with self._lock, self._connection:
            self._prune_locked()
            active = self._connection.execute(
                "SELECT COUNT(*) FROM turns WHERE archived = 0"
            ).fetchone()
            assert active is not None
            limit = self._retention.active_max_turns
            if limit is not None and active[0] >= limit:
                raise ValueError("restoring archived turn exceeds the active limit")
            self._check_restore_age(turn_id)
            cursor = self._connection.execute(
                "UPDATE turns SET archived = 0 WHERE archived = 1 AND id = ?",
                (turn_id,),
            )
            return cursor.rowcount == 1

    def _check_restore_age(self, turn_id: int | None = None) -> None:
        days = self._retention.active_max_age_days
        if days is not None:
            cutoff = (self._clock().astimezone(UTC) - timedelta(days=days)).isoformat()
            expired = self._connection.execute(
                "SELECT 1 FROM turns WHERE archived = 1 AND recorded_at < ? "
                "AND (? IS NULL OR id = ?) LIMIT 1",
                (cutoff, turn_id, turn_id),
            ).fetchone()
            if expired is not None:
                raise ValueError("archived text exceeds the active age limit")

    def clear_active(self) -> None:
        """Delete active text only; unlike archiving, this is irreversible."""
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM turns WHERE archived = 0")

    def clear(self) -> None:
        """Compatibility alias retaining the historical active-only contract."""
        self.clear_active()

    def clear_all(self) -> None:
        """Delete active and archived rows in this database, not external snapshots."""
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM turns")

    def close(self) -> None:
        with self._lock:
            self._connection.close()
