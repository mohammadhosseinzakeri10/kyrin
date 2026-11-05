"""The display worker delivers current captions rather than replaying old phases."""

import subprocess
from types import SimpleNamespace

import pytest

from kyrin.backend_protocol import BackendStatus
from kyrin.responses import gnome_status
from kyrin.responses.visual_status import VisualPresentation, VisualStatus


class EndWorker(BaseException):
    """Stop the otherwise permanent worker without a live thread or IPC."""


@pytest.fixture
def sink(monkeypatch: pytest.MonkeyPatch) -> gnome_status.GnomeVisualStatusSink:
    monkeypatch.setattr(
        gnome_status, "Thread", lambda **_: SimpleNamespace(start=lambda: None)
    )
    return gnome_status.GnomeVisualStatusSink()


def test_caption_burst_retains_only_the_latest_pending_state(
    sink: gnome_status.GnomeVisualStatusSink,
) -> None:
    for status in (
        VisualStatus.LISTENING,
        VisualStatus.PROCESSING,
        VisualStatus.CONVERSATION,
    ):
        latest = VisualPresentation(status, status.value)
        sink.publish(latest)
    assert sink._updates.qsize() == 1
    assert sink._updates.get_nowait() == latest


def test_caption_superseded_during_handshake_is_not_sent(
    sink: gnome_status.GnomeVisualStatusSink, monkeypatch: pytest.MonkeyPatch
) -> None:
    sink.publish(VisualPresentation(VisualStatus.PROCESSING, "Understanding request…"))
    latest = VisualPresentation(
        VisualStatus.READY, "Standby. Say Start listening to speak."
    )
    sent: list[list[str]] = []

    def probe(*_args: object, **_kwargs: object) -> BackendStatus:
        sink.publish(latest)
        return BackendStatus(True, "ready")

    def dispatch(arguments: list[str], **_kwargs: object) -> None:
        sent.append(arguments)
        raise EndWorker()

    monkeypatch.setattr(gnome_status, "probe_gnome", probe)
    monkeypatch.setattr(subprocess, "run", dispatch)
    with pytest.raises(EndWorker):
        sink._run()
    assert sent[0][-2:] == [latest.status.value, latest.caption]


def test_updates_during_one_inflight_call_coalesce_before_the_next_call(
    sink: gnome_status.GnomeVisualStatusSink, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = VisualPresentation(VisualStatus.EXECUTING, "Minimizing telegram…")
    latest = VisualPresentation(VisualStatus.CONFIRMED, "Minimize telegram — Done.")
    sink.publish(first)
    sent: list[list[str]] = []

    def dispatch(
        arguments: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        sent.append(arguments)
        if len(sent) == 2:
            raise EndWorker()
        sink.publish(
            VisualPresentation(VisualStatus.PROCESSING, "Older processing phase")
        )
        sink.publish(latest)
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(
        gnome_status,
        "probe_gnome",
        lambda *_args, **_kwargs: BackendStatus(True, "ready"),
    )
    monkeypatch.setattr(subprocess, "run", dispatch)
    with pytest.raises(EndWorker):
        sink._run()
    assert [arguments[-2:] for arguments in sent] == [
        [first.status.value, first.caption],
        [latest.status.value, latest.caption],
    ]
