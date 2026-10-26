"""Measure synthetic conversation-history I/O on the selected XDG data drive."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from kyrin.memory.history import (
    ConversationTurn,
    SqliteConversationHistory,
    default_history_path,
)


def _summary(samples_ns: list[int]) -> dict[str, float]:
    ordered = sorted(samples_ns)
    return {
        "median_ms": round(median(ordered) / 1_000_000, 3),
        "p95_ms": round(ordered[(len(ordered) * 95 - 1) // 100] / 1_000_000, 3),
        "max_ms": round(ordered[-1] / 1_000_000, 3),
    }


def benchmark(turns: int, reads: int, root: Path) -> dict[str, object]:
    if turns < 1 or reads < 1:
        raise ValueError("turns and reads must be positive")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="history-bench-", dir=root) as directory:
        history = SqliteConversationHistory(Path(directory) / "conversation.sqlite3")
        try:
            append_times: list[int] = []
            read_times: list[int] = []
            for segment in range(turns):
                start = perf_counter_ns()
                history.append(
                    ConversationTurn(
                        "Synthetic command for storage benchmark",
                        "en",
                        datetime.now(UTC),
                        "benchmark",
                        0,
                        segment,
                    )
                )
                append_times.append(perf_counter_ns() - start)
            for _ in range(reads):
                start = perf_counter_ns()
                history.recent(limit=6)
                read_times.append(perf_counter_ns() - start)
        finally:
            history.close()
    return {
        "turns": turns,
        "reads": reads,
        "directory": str(root.resolve()),
        "append": _summary(append_times),
        "recent_six": _summary(read_times),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turns", type=int, default=300)
    parser.add_argument("--reads", type=int, default=300)
    arguments = parser.parse_args()
    result = benchmark(arguments.turns, arguments.reads, default_history_path().parent)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
