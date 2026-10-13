"""Small, bounded conversation history independent of speech and command engines."""

import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
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


def default_history_path() -> Path:
    """Use XDG data storage; the owner's XDG directory links to AI-Projects."""
    configured = os.environ.get("XDG_DATA_HOME")
    root = Path(configured) if configured else Path.home() / ".local" / "share"
    if not root.is_absolute():
        root = Path.home() / ".local" / "share"
    return root / "kyrin" / "memory" / "conversation.sqlite3"


class SqliteConversationHistory:
    """Persist finalized text only; reads are ordered and explicitly bounded."""

    def __init__(self, path: Path, *, max_turns: int = 2000) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be positive")
        self._path = path
        self._max_turns = max_turns
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
            self._connection.execute(
                "DELETE FROM turns WHERE archived = 0 AND id NOT IN "
                "(SELECT id FROM turns WHERE archived = 0 ORDER BY id DESC LIMIT ?)",
                (self._max_turns,),
            )

    def recent(self, *, limit: int = 8) -> tuple[ConversationTurn, ...]:
        if limit < 0 or limit > 50:
            raise ValueError("limit must be between 0 and 50")
        with self._lock:
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
        """Exclude existing turns from context without deleting their text."""
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "UPDATE turns SET archived = 1 WHERE archived = 0"
            )
            return cursor.rowcount

    def restore_archived(self) -> int:
        """Make archived turns available to bounded recent reads again."""
        with self._lock, self._connection:
            total = self._connection.execute("SELECT COUNT(*) FROM turns").fetchone()
            assert total is not None
            if total[0] > self._max_turns:
                raise ValueError("restoring archived turns exceeds the active limit")
            cursor = self._connection.execute(
                "UPDATE turns SET archived = 0 WHERE archived = 1"
            )
            return cursor.rowcount

    def archived_count(self) -> int:
        with self._lock:
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
        with self._lock:
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
            active = self._connection.execute(
                "SELECT COUNT(*) FROM turns WHERE archived = 0"
            ).fetchone()
            assert active is not None
            if active[0] >= self._max_turns:
                raise ValueError("restoring archived turn exceeds the active limit")
            cursor = self._connection.execute(
                "UPDATE turns SET archived = 0 WHERE archived = 1 AND id = ?",
                (turn_id,),
            )
            return cursor.rowcount == 1

    def clear(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM turns WHERE archived = 0")

    def close(self) -> None:
        with self._lock:
            self._connection.close()
