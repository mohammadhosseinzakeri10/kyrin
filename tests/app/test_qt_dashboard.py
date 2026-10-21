"""Dashboard particles remain visible and cycle while their page is shown."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from kyrin.app.qt.dashboard import (  # noqa: E402
    CPU_EMBLEM_POINTS,
    CYCLE_MS,
    DISPERSE_MS,
    FORM_MS,
    GPU_HEAVY_EMBLEM_POINTS,
    GPU_LIGHT_EMBLEM_POINTS,
    GPU_MEDIUM_EMBLEM_POINTS,
    HOLD_MS,
    _load_particles,
)
from kyrin.app.qt.dashboard_page import DashboardPage  # noqa: E402
from kyrin.app.qt.theme import CONTROL_WINDOW_STYLE  # noqa: E402
from kyrin.app.qt.translations import ENGLISH  # noqa: E402


def test_light_dashboard_uses_committed_particle_artwork() -> None:
    particles, palette = _load_particles(CPU_EMBLEM_POINTS)
    assert len(particles) == CPU_EMBLEM_POINTS
    assert (particles[0].x, particles[0].y, particles[0].color_rgb) == (
        0.052,
        0.002,
        0x00010F,
    )
    assert palette[particles[0].palette_index][0].alpha() == 145


def test_heavy_dashboard_breaks_the_regular_sample_grid() -> None:
    particles, _ = _load_particles(GPU_HEAVY_EMBLEM_POINTS)
    assert len(particles) == GPU_HEAVY_EMBLEM_POINTS
    offsets = {
        (round((dot.x * 895) % 1, 2), round((dot.y * 895) % 1, 2))
        for dot in particles[:100]
    }
    assert len(offsets) > 90


def test_static_dashboard_skips_particle_loading_until_animation_starts() -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    page = DashboardPage(lambda key: QLabel(ENGLISH[key]))
    dashboard = page.cosmic_dashboard
    dashboard.set_animation_enabled(False)
    dashboard.set_renderer("gpu_heavy")
    page.resize(850, 500)
    page.show()
    app.processEvents()
    assert not dashboard._particles
    assert dashboard._gpu_layer is None
    assert dashboard._static_image is not None
    dashboard.set_renderer("cpu")
    dashboard.set_animation_enabled(True)
    assert len(dashboard._particles) == CPU_EMBLEM_POINTS
    page.close()


def test_dashboard_repeats_with_readable_point_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    page = DashboardPage(lambda key: QLabel(ENGLISH[key]))
    page.setStyleSheet(CONTROL_WINDOW_STYLE)
    page.resize(850, 500)
    page.show()
    app.processEvents()

    dashboard = page.cosmic_dashboard
    assert dashboard._timer.isActive()
    assert dashboard._text_points()
    assert min(dot.start_x for dot in dashboard._text_points()) < 0.45
    assert max(dot.start_x for dot in dashboard._text_points()) > 0.55
    assert all(dot.delay_ms < 800 for dot in dashboard._text_points())
    assert len(dashboard._particles) == CPU_EMBLEM_POINTS
    assert "Welcome to KYRIN" in dashboard.accessibleDescription()

    dashboard.set_animation_enabled(False)
    assert not dashboard._timer.isActive()
    assert dashboard._animation_enabled is False
    assert not dashboard._particles
    assert not dashboard._palette
    assert not page.grab().isNull()
    assert dashboard._static_image is not None
    page.welcome_label.setText("A translated greeting")
    dashboard.refresh_scene()
    assert dashboard._static_image is None
    page.grab()
    assert "A translated greeting" in dashboard.accessibleDescription()
    page.welcome_label.setText("Welcome to KYRIN")
    dashboard.refresh_scene()
    dashboard.set_animation_enabled(True)
    assert dashboard._timer.isActive()
    assert len(dashboard._particles) == CPU_EMBLEM_POINTS

    dashboard._elapsed_ms = FORM_MS + 100
    dashboard._elapsed.start()
    dashboard._advance()
    app.processEvents()
    assert dashboard._timer.isActive()
    assert dashboard._amount(FORM_MS + 100, 0, 2700) == 1
    assert all(
        not label.isVisible() and label.sizePolicy().retainSizeWhenHidden()
        for label in (
            page.welcome_label,
            page.welcome_caption_label,
            page.scene_hint_label,
        )
    )

    halfway = FORM_MS + HOLD_MS + DISPERSE_MS // 2
    assert 0 < dashboard._amount(halfway, 0, 2700) < 1
    dashboard._elapsed_ms = CYCLE_MS + FORM_MS // 2
    dashboard._elapsed.start()
    dashboard._advance()
    app.processEvents()
    assert dashboard._timer.isActive()
    assert page.welcome_label.text() == "Welcome to KYRIN"
    assert page.scene_hint_label.text() == "Created by KAILARIN"
    assert not page.grab().isNull()
    page.welcome_label.setText("Another greeting")
    dashboard._text_points()
    assert "Another greeting" in dashboard.accessibleDescription()
    page.hide()
    assert not dashboard._timer.isActive()
    page.close()


def test_dashboard_switches_between_two_dimensional_renderers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    page = DashboardPage(lambda key: QLabel(ENGLISH[key]))
    page.resize(850, 500)
    page.show()
    dashboard = page.cosmic_dashboard
    assert len(dashboard._particles) == CPU_EMBLEM_POINTS
    dashboard.set_renderer("gpu")
    assert dashboard._gpu_layer is not None
    assert len(dashboard._particles) == GPU_LIGHT_EMBLEM_POINTS
    dashboard.set_renderer("gpu_medium")
    assert len(dashboard._particles) == GPU_MEDIUM_EMBLEM_POINTS
    dashboard.set_renderer("gpu_heavy")
    assert len(dashboard._particles) == GPU_HEAVY_EMBLEM_POINTS
    assert min(dot.start_x for dot in dashboard._text_points()) < 0.45
    dashboard.set_renderer("gpu_medium")
    assert len(dashboard._particles) == GPU_MEDIUM_EMBLEM_POINTS
    dashboard.set_renderer("gpu")
    assert len(dashboard._particles) == GPU_LIGHT_EMBLEM_POINTS
    dashboard.set_renderer("gpu_heavy")
    assert len(dashboard._particles) == GPU_HEAVY_EMBLEM_POINTS
    dashboard._gpu_layer._fallback()
    assert len(dashboard._particles) == CPU_EMBLEM_POINTS
    dashboard.set_renderer("gpu")
    assert len(dashboard._particles) == GPU_LIGHT_EMBLEM_POINTS
    dashboard.set_renderer("cpu")
    assert dashboard._gpu_layer is None
    assert len(dashboard._particles) == CPU_EMBLEM_POINTS
    dashboard.set_renderer("gpu_heavy")
    dashboard.set_animation_enabled(False)
    assert dashboard._gpu_layer is None
    assert not dashboard._particles
    dashboard.set_renderer("gpu_medium")
    assert not dashboard._particles
    dashboard.set_animation_enabled(True)
    assert dashboard._gpu_layer is not None
    assert len(dashboard._particles) == GPU_MEDIUM_EMBLEM_POINTS
    assert dashboard._timer.isActive()
    page.close()
