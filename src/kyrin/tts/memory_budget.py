"""Conservative Linux address-space limit for CPU-only Qwen speech workers."""

import sys
from pathlib import Path

_GIB = 1024**3
_MIN_BUDGET = 4 * _GIB


def cpu_qwen_budget(total_bytes: int, available_bytes: int) -> int:
    """Leave at least half of current available RAM outside the worker."""
    if total_bytes <= 0 or available_bytes <= 0:
        raise ValueError("System memory information is unavailable")
    budget = min(total_bytes // 2, available_bytes // 2)
    if budget < _MIN_BUDGET:
        raise ValueError(
            "Not enough free RAM to start Qwen3-TTS on CPU safely; "
            "select GPU or free memory"
        )
    return budget


def _linux_memory() -> tuple[int, int]:
    try:
        values = {}
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            name, _, amount = line.partition(":")
            if name in {"MemTotal", "MemAvailable"}:
                values[name] = int(amount.strip().split()[0]) * 1024
        return values["MemTotal"], values["MemAvailable"]
    except (OSError, UnicodeError, KeyError, ValueError, IndexError) as exc:
        raise ValueError("System memory information is unavailable") from exc


def limit_cpu_qwen_worker() -> int | None:
    """Bound one Linux worker before loading weights; other OSes need own adapter."""
    if sys.platform != "linux":
        return None
    import resource

    budget = cpu_qwen_budget(*_linux_memory())
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    if hard != resource.RLIM_INFINITY:
        budget = min(budget, hard)
    if budget < _MIN_BUDGET:
        raise ValueError("CPU TTS worker memory limit is too low")
    try:
        resource.setrlimit(resource.RLIMIT_AS, (budget, hard))
    except (OSError, ValueError) as exc:
        raise ValueError("Could not set a safe CPU TTS memory limit") from exc
    return budget
