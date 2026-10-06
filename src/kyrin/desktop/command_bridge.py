"""Supply fresh desktop context to final command decisions only."""

from collections.abc import Sequence

from kyrin.commands.coordinator import CommandCoordinator
from kyrin.commands.models import CommandEvent
from kyrin.desktop.active_app import ActiveAppObserver
from kyrin.stt.transcript import TranscriptStatus, TranscriptUpdate


def observe_command_update(
    coordinator: CommandCoordinator,
    update: TranscriptUpdate,
    observer: ActiveAppObserver | None,
) -> tuple[str | None, Sequence[CommandEvent]]:
    """Never reuse focus from an earlier transcript or query on partial text."""
    active_app = (
        observer.observe_active_app()
        if observer is not None and update.status is TranscriptStatus.FINAL
        else None
    )
    return active_app, coordinator.observe(update, observed_active_app=active_app)
