"""Supply fresh desktop context to final command decisions only."""

from collections.abc import Callable, Sequence

from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.models import CommandEvent
from kyrin.desktop.active_app import ActiveAppObserver
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


def observe_command_update(
    coordinator: CommandCoordinator,
    update: TranscriptUpdate,
    observer: ActiveAppObserver | None,
    scroll_focus_reader: Callable[[], tuple[str, int] | None] | None = None,
) -> tuple[str | None, Sequence[CommandEvent]]:
    """Never reuse focus from an earlier transcript or query on partial text."""
    active_app = (
        observer.observe_active_app()
        if observer is not None and update.status is TranscriptStatus.FINAL
        else None
    )
    scroll_window = (
        scroll_focus_reader()
        if scroll_focus_reader is not None and update.status is TranscriptStatus.FINAL
        else None
    )
    return active_app, coordinator.observe(
        update,
        observed_active_app=active_app,
        observed_scroll_app=scroll_window[0] if scroll_window is not None else None,
    )
