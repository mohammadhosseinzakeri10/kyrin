"""A capture's explicit geometry determines the only safe OCR-to-desktop map."""

import pytest

from kyrin.vision.capture_geometry import CaptureGeometry, coordinate_to_desktop


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
def test_explicit_scale_maps_image_pixels_to_logical_desktop(scale: float) -> None:
    geometry = CaptureGeometry(
        coordinate_space="logical_desktop",
        monitor_id=1,
        logical_rect=(-1200, 40, 800, 600),
        image_size=(round(800 * scale), round(600 * scale)),
        scale_x=scale,
        scale_y=scale,
        padding=(0, 0, 0, 0),
        crop_origin=(0, 0),
        ocr_resize=(1, 1),
        window_token="window-7",
        capture_id="capture-1",
        captured_at=100.0,
    )
    assert coordinate_to_desktop(geometry, (100 * scale, 80 * scale)) == (-1100, 120)


def test_shadow_padding_crop_and_ocr_resize_compose_once() -> None:
    geometry = CaptureGeometry(
        coordinate_space="logical_desktop",
        monitor_id=0,
        logical_rect=(10, 20, 400, 300),
        image_size=(520, 395),
        scale_x=1.25,
        scale_y=1.25,
        padding=(10, 10, 10, 10),
        crop_origin=(50, 30),
        ocr_resize=(2, 2),
        window_token="window-7",
        capture_id="capture-1",
        captured_at=100.0,
    )
    assert coordinate_to_desktop(geometry, (170, 120)) == (110, 84)
    assert coordinate_to_desktop(geometry, (-1, 0)) is None


def test_invalid_or_outside_geometry_never_yields_a_click_point() -> None:
    with pytest.raises(ValueError):
        CaptureGeometry(
            coordinate_space="logical_desktop",
            monitor_id=0,
            logical_rect=(0, 0, 400, 400),
            image_size=(500, 500),
            scale_x=1.25,
            scale_y=1.25,
            padding=(50, 50, 50, 50),
            crop_origin=(0, 0),
            ocr_resize=(1, 1),
            window_token="window-7",
            capture_id="capture-1",
            captured_at=100.0,
        )


def test_rounded_dispatch_point_must_remain_inside_target() -> None:
    geometry = CaptureGeometry(
        "logical_desktop",
        0,
        (0, 0, 100, 100),
        (200, 200),
        2,
        2,
        (0, 0, 0, 0),
        (0, 0),
        (1, 1),
        "window-7",
        "capture-1",
        100.0,
    )
    assert (
        coordinate_to_desktop(
            geometry, (3, 3), image_pixels=True, target_box=(2, 2, 2, 2)
        )
        is None
    )
