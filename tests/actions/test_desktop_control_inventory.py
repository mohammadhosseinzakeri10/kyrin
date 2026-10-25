"""A model may only choose unique options observed in the same focused window."""

import subprocess
from time import monotonic

import pytest

from kyrin.actions.platforms import desktop_control_inventory
from kyrin.actions.visible_control import VisibleTextOption, visible_ocr_labels
from kyrin.vision.capture_geometry import CaptureGeometry
from kyrin.vision.ocr.contracts import OcrDevice, OcrResult, RecognizedText, TextBox
from kyrin.vision.text_reader import IdentifiedWindowText


def _geometry() -> CaptureGeometry:
    return CaptureGeometry(
        "logical_desktop",
        0,
        (0, 0, 800, 1000),
        (800, 1000),
        1,
        1,
        (0, 0, 0, 0),
        (0, 0),
        (1, 1),
        "window-7",
        "capture-1",
        monotonic(),
        (0, 0, 800, 1000),
    )


class Reader:
    def ready(self) -> bool:
        return True

    def list_visible_text(self, app_id: str, pid: int) -> tuple[VisibleTextOption, ...]:
        assert (app_id, pid) == ("example.desktop", 42)
        return tuple(
            VisibleTextOption(label, (30, index * 20), _geometry())
            for index, label in enumerate(
                ("Settings", "Advanced", "Advanced", "Sound"), start=1
            )
        )


def test_inventory_prefers_unique_accessible_options_and_rejects_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args,
            0,
            '[{"label":"Settings","role":"button","checked":null,"x":50,"y":20},'
            '{"label":"Search","role":"icon","checked":null,"x":60,"y":20},'
            '{"label":"Search","role":"icon","checked":null,"x":80,"y":20}]',
            "",
        )

    monkeypatch.setattr(subprocess, "run", run)
    inventory = desktop_control_inventory.DesktopControlInventory(
        lambda: ("example.desktop", 42), Reader(), token_reader=lambda: "window-7"
    )

    options = inventory.read_options("example.desktop")
    assert [(item.option_id, item.label, item.source) for item in options] == [
        ("1", "Settings", "accessibility"),
        ("2", "Sound", "ocr"),
    ]
    assert options[0].anchor == (50, 20)


def test_inventory_discards_snapshot_when_focus_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **_kwargs: subprocess.CompletedProcess(args, 0, "[]", ""),
    )
    identities = iter((("example.desktop", 42), ("other.desktop", 1)))
    inventory = desktop_control_inventory.DesktopControlInventory(
        lambda: next(identities), Reader(), token_reader=lambda: "window-7"
    )
    assert inventory.read_options("example.desktop") == ()


def test_exact_accessible_name_avoids_ocr_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **_kwargs: subprocess.CompletedProcess(
            args,
            0,
            '[{"label":"Search","role":"icon","checked":null,"x":20,"y":30}]',
            "",
        ),
    )

    class NoOcrReader(Reader):
        def list_visible_text(
            self, app_id: str, pid: int
        ) -> tuple[VisibleTextOption, ...]:
            pytest.fail("OCR is unnecessary for this named icon")

    inventory = desktop_control_inventory.DesktopControlInventory(
        lambda: ("example.desktop", 42), NoOcrReader(), token_reader=lambda: "window-7"
    )
    assert [
        option.label
        for option in inventory.read_options(
            "example.desktop", "Could you click Search?"
        )
    ] == ["Search"]


def test_matching_option_near_bottom_survives_catalog_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **_kwargs: subprocess.CompletedProcess(args, 0, "[]", ""),
    )

    class LongReader(Reader):
        def list_visible_text(
            self, app_id: str, pid: int
        ) -> tuple[VisibleTextOption, ...]:
            return tuple(
                VisibleTextOption(f"Item {index}", (20, index), _geometry())
                for index in range(150)
            ) + (VisibleTextOption("Sound Settings", (80, 900), _geometry()),)

    inventory = desktop_control_inventory.DesktopControlInventory(
        lambda: ("example.desktop", 42), LongReader(), token_reader=lambda: "window-7"
    )
    labels = [
        option.label
        for option in inventory.read_options(
            "example.desktop", "Could you open Sound Settings?"
        )
    ]
    assert len(labels) <= 100
    assert "Sound Settings" in labels


def test_ocr_inventory_includes_adjacent_words_but_not_wrong_window() -> None:
    observation = IdentifiedWindowText(
        "example.desktop",
        42,
        OcrResult(
            (
                RecognizedText("Sound", TextBox(30, 20, 50, 18), 0.96),
                RecognizedText("Settings", TextBox(84, 20, 70, 18), 0.93),
                RecognizedText("noise", TextBox(30, 80, 60, 18), 0.2),
            ),
            "eng",
            OcrDevice.CPU,
            "test",
        ),
        (800, 600),
    )
    labels = visible_ocr_labels(observation, "example.desktop", 42)
    assert VisibleTextOption("Sound Settings", (92, 29)) in labels
    assert "noise" not in {item.label for item in labels}
    assert visible_ocr_labels(observation, "other.desktop", 42) == ()


def test_inventory_rejects_same_process_window_switch_during_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = ["window-7"]

    def scan(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        assert args[-1] == "window-7"
        token[0] = "window-8"
        return subprocess.CompletedProcess(
            args,
            0,
            '[{"label":"Search","role":"icon","checked":null,"x":20,"y":30}]',
            "",
        )

    monkeypatch.setattr(subprocess, "run", scan)
    inventory = desktop_control_inventory.DesktopControlInventory(
        lambda: ("example.desktop", 42),
        Reader(),
        token_reader=lambda: token[0],
    )
    assert inventory.read_options("example.desktop", "click Search") == ()


def test_missing_token_does_not_fall_back_to_app_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_k: pytest.fail("no scan without identity"),
    )
    inventory = desktop_control_inventory.DesktopControlInventory(
        lambda: ("example.desktop", 42),
        Reader(),
        token_reader=lambda: None,
    )
    assert inventory.read_options("example.desktop", "click Search") == ()


def test_accessible_inventory_works_when_ocr_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **_kw: subprocess.CompletedProcess(
            args,
            0,
            '[{"label":"Settings","role":"button","checked":null,"x":20,"y":30}]',
            "",
        ),
    )

    class OffReader(Reader):
        def ready(self) -> bool:
            return False

        def list_visible_text(self, *_args: object) -> tuple[VisibleTextOption, ...]:
            pytest.fail("OCR is off")

    inventory = desktop_control_inventory.DesktopControlInventory(
        lambda: ("example.desktop", 42), OffReader(), token_reader=lambda: "window-7"
    )
    assert [item.label for item in inventory.read_options("example.desktop")] == [
        "Settings"
    ]


def test_inventory_preserves_role_ancestry_for_action_without_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    from kyrin.desktop.accessibility_target import AccessibilityTarget

    structure = AccessibilityTarget(((0, "FRAME", "Main"), (1, "BUTTON", "Settings")))
    payload = [
        {
            "label": "Settings",
            "role": "BUTTON",
            "checked": None,
            "x": None,
            "y": None,
            "accessibility": structure.to_json(),
        }
    ]
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **_kw: subprocess.CompletedProcess(
            args, 0, json.dumps(payload), ""
        ),
    )

    class OffReader(Reader):
        def ready(self) -> bool:
            return False

    inventory = desktop_control_inventory.DesktopControlInventory(
        lambda: ("example.desktop", 42), OffReader(), token_reader=lambda: "window-7"
    )
    (option,) = inventory.read_options("example.desktop")
    assert option.accessibility == structure
    assert option.role == "BUTTON" and option.anchor is None


def test_inventory_rejects_ocr_duplicates_under_locator_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "subprocess.run",
        lambda args, **_kwargs: subprocess.CompletedProcess(args, 0, "[]", ""),
    )

    class NormalizedDuplicates(Reader):
        def list_visible_text(
            self, app_id: str, pid: int
        ) -> tuple[VisibleTextOption, ...]:
            return (
                VisibleTextOption("تنظيمات صدا", (40, 20), _geometry()),
                VisibleTextOption("تنظیمات صدا", (40, 80), _geometry()),
                VisibleTextOption("‘Sound Settings’", (40, 140), _geometry()),
                VisibleTextOption("Sound Settings", (40, 200), _geometry()),
                VisibleTextOption("Unique", (40, 260), _geometry()),
            )

    inventory = desktop_control_inventory.DesktopControlInventory(
        lambda: ("example.desktop", 42),
        NormalizedDuplicates(),
        token_reader=lambda: "window-7",
    )
    assert [item.label for item in inventory.read_options("example.desktop")] == [
        "Unique"
    ]
