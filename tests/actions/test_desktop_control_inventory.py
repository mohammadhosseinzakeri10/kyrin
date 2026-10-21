"""A model may only choose unique options observed in the same focused window."""

import subprocess

import pytest

from kyrin.actions.platforms import desktop_control_inventory
from kyrin.actions.visible_control import VisibleTextOption, visible_ocr_labels
from kyrin.vision.ocr.contracts import OcrDevice, OcrResult, RecognizedText, TextBox
from kyrin.vision.text_reader import IdentifiedWindowText


class Reader:
    def ready(self) -> bool:
        return True

    def list_visible_text(self, app_id: str, pid: int) -> tuple[VisibleTextOption, ...]:
        assert (app_id, pid) == ("example.desktop", 42)
        return tuple(
            VisibleTextOption(label, (30, index * 20))
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

    monkeypatch.setattr(desktop_control_inventory.subprocess, "run", run)
    inventory = desktop_control_inventory.DesktopControlInventory(
        lambda: ("example.desktop", 42), Reader()
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
        desktop_control_inventory.subprocess,
        "run",
        lambda args, **_kwargs: subprocess.CompletedProcess(args, 0, "[]", ""),
    )
    identities = iter((("example.desktop", 42), ("other.desktop", 1)))
    inventory = desktop_control_inventory.DesktopControlInventory(
        lambda: next(identities), Reader()
    )
    assert inventory.read_options("example.desktop") == ()


def test_exact_accessible_name_avoids_ocr_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        desktop_control_inventory.subprocess,
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
        lambda: ("example.desktop", 42), NoOcrReader()
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
        desktop_control_inventory.subprocess,
        "run",
        lambda args, **_kwargs: subprocess.CompletedProcess(args, 0, "[]", ""),
    )

    class LongReader(Reader):
        def list_visible_text(
            self, app_id: str, pid: int
        ) -> tuple[VisibleTextOption, ...]:
            return tuple(
                VisibleTextOption(f"Item {index}", (20, index)) for index in range(150)
            ) + (VisibleTextOption("Sound Settings", (80, 900)),)

    inventory = desktop_control_inventory.DesktopControlInventory(
        lambda: ("example.desktop", 42), LongReader()
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
