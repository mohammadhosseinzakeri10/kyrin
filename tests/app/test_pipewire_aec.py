"""Optional AEC fails closed when PipeWire tools are absent."""

import json
import subprocess

import pytest

from kyrin.app.platforms.pipewire_aec import PipeWireEchoCancellation


def test_missing_pipewire_tools_leave_echo_cancellation_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: None)
    session = PipeWireEchoCancellation()
    assert not session.start()
    session.close()


def test_stale_cleanup_preserves_sources_owned_by_a_running_kyrin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = [
        {
            "id": 1,
            "info": {
                "props": {
                    "node.name": "kyrin-echo-1001-abcdef12",
                    "client.id": 3,
                }
            },
        },
        {
            "id": 2,
            "info": {
                "props": {
                    "node.name": "kyrin-echo-1002-abcdef12",
                    "client.id": 4,
                }
            },
        },
        {"id": 3, "info": {"props": {"pipewire.sec.pid": 2001}}},
        {"id": 4, "info": {"props": {"pipewire.sec.pid": 2002}}},
    ]
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, json.dumps(graph), ""
        ),
    )
    monkeypatch.setattr(
        PipeWireEchoCancellation,
        "_is_live_kyrin",
        lambda pid: pid == 1001,
    )
    terminated: list[int] = []
    monkeypatch.setattr(
        PipeWireEchoCancellation,
        "_terminate_owned_process",
        lambda pid, executable: terminated.append(pid),
    )
    PipeWireEchoCancellation._cleanup_stale_sources("pw-dump")
    assert terminated == [2002]


@pytest.mark.parametrize(
    "key,props",
    [
        (
            '["ALSA","USB Mic (hw:2,0)"]',
            {"api.alsa.pcm.card": "2", "api.alsa.pcm.device": "0"},
        ),
        ('["PulseAudio","USB Mic"]', {"node.description": "USB Mic"}),
    ],
)
def test_selected_input_maps_only_to_unique_capture_node(
    key: str, props: dict[str, str]
) -> None:
    graph = [
        {
            "id": 42,
            "info": {
                "props": {
                    "media.class": "Audio/Source",
                    "node.name": "alsa_input.usb",
                    **props,
                }
            },
        }
    ]
    assert PipeWireEchoCancellation.resolve_target(key, graph) == "alsa_input.usb"
    assert PipeWireEchoCancellation.resolve_target(key, graph * 2) is None
    graph[0]["info"]["props"]["media.class"] = "Audio/Sink"
    assert PipeWireEchoCancellation.resolve_target(key, graph) is None


def test_unmapped_selected_microphone_never_uses_default() -> None:
    assert PipeWireEchoCancellation.resolve_target('["ALSA","unknown"]', []) is None


def test_start_pins_capture_and_disallows_default_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil
    from io import StringIO

    graph = [
        {
            "info": {
                "props": {
                    "media.class": "Audio/Source",
                    "node.name": 'mic"name',
                    "api.alsa.pcm.card": 2,
                    "api.alsa.pcm.device": 0,
                }
            }
        }
    ]

    class Process:
        stdin = StringIO()

        def poll(self):
            return None

        def wait(self, timeout):
            return 0

    process = Process()
    monkeypatch.setattr(shutil, "which", lambda name: name)
    monkeypatch.setattr(
        PipeWireEchoCancellation, "_cleanup_stale_sources", staticmethod(lambda _: None)
    )
    monkeypatch.setattr(
        PipeWireEchoCancellation, "_source_exists", lambda self, _: True
    )
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            json.dumps(graph),
            "",
        ),
    )
    aec = PipeWireEchoCancellation()
    assert aec.start('["ALSA","USB Mic (hw:2,0)"]')
    command = process.stdin.getvalue()
    assert 'target.object = "mic\\"name"' in command
    assert "node.dont-fallback = true" in command
    assert "node.dont-reconnect = true" in command
    aec.close()


def test_unmapped_selection_does_not_create_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: name)
    monkeypatch.setattr(
        PipeWireEchoCancellation, "_cleanup_stale_sources", staticmethod(lambda _: None)
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            "[]",
            "",
        ),
    )
    monkeypatch.setattr(
        subprocess, "Popen", lambda *args, **kwargs: pytest.fail("unmapped input")
    )
    assert not PipeWireEchoCancellation().start('["ALSA","unknown"]')


@pytest.mark.parametrize(
    "linked,wrong_target", [(False, False), (True, True), (True, False)]
)
def test_ready_requires_capture_and_speaker_reference_links(
    monkeypatch: pytest.MonkeyPatch,
    linked: bool,
    wrong_target: bool,
) -> None:
    aec = PipeWireEchoCancellation()
    aec._target = "selected-mic"
    graph = [
        {
            "id": i,
            "type": "PipeWire:Interface:Node",
            "info": {
                "props": {
                    "node.name": name,
                    "media.class": cls,
                }
            },
        }
        for i, name, cls in (
            (1, aec._source_name, "Audio/Source"),
            (2, aec._source_name + "-capture", "Stream/Input/Audio"),
            (3, aec._source_name + "-monitor", "Stream/Input/Audio"),
            (4, "other-mic" if wrong_target else "selected-mic", "Audio/Source"),
            (5, "speaker", "Audio/Sink"),
        )
    ]
    if linked:
        graph += [
            {
                "type": "PipeWire:Interface:Link",
                "info": {
                    "output-node-id": output,
                    "input-node-id": target,
                    "state": "paused",
                },
            }
            for output, target in ((4, 2), (5, 3))
        ]
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            json.dumps(graph),
            "",
        ),
    )
    assert aec._source_exists("pw-dump") is (linked and not wrong_target)


@pytest.mark.parametrize("name", ["pulse", "pipewire"])
@pytest.mark.parametrize("value", ['{"name":"chosen"}', {"name": "chosen"}])
def test_default_bridge_maps_to_metadata_source_not_arbitrary_device(
    name: str,
    value: object,
) -> None:
    graph = [
        {
            "type": "PipeWire:Interface:Metadata",
            "metadata": [
                {
                    "key": "default.audio.source",
                    "value": value,
                }
            ],
        },
        {"info": {"props": {"media.class": "Audio/Source", "node.name": "chosen"}}},
        {"info": {"props": {"media.class": "Audio/Source", "node.name": "other"}}},
    ]
    assert (
        PipeWireEchoCancellation.resolve_target(json.dumps(["ALSA", name]), graph)
        == "chosen"
    )
    assert (
        PipeWireEchoCancellation.resolve_target(json.dumps(["ALSA", name]), graph[1:])
        is None
    )
