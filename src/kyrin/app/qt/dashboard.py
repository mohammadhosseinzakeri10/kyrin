"""A short particle reveal of KYRIN's cosmic emblem on the dashboard."""

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QHideEvent,
    QImage,
    QLinearGradient,
    QPainter,
    QPaintEvent,
    QPen,
    QRadialGradient,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import QLabel

if TYPE_CHECKING:
    from kyrin.app.qt.dashboard_gl import DashboardGL

REFERENCE = Path(__file__).with_name("assets") / "dashboard_reference.png"
PARTICLES = Path(__file__).with_name("assets") / "dashboard_particles.json"
CPU_EMBLEM_POINTS = 29_999
GPU_LIGHT_EMBLEM_POINTS = CPU_EMBLEM_POINTS
GPU_MEDIUM_EMBLEM_POINTS = 59_999
GPU_HEAVY_EMBLEM_POINTS = 800_000
FORM_MS = 3500
HOLD_MS = 1500
DISPERSE_MS = 1750
SCATTER_MS = 500
CYCLE_MS = FORM_MS + HOLD_MS + DISPERSE_MS + SCATTER_MS


@dataclass(frozen=True)
class _Particle:
    x: float
    y: float
    palette_index: int
    color_rgb: int
    start_x: float
    start_y: float
    delay_ms: int


@dataclass(frozen=True)
class _TextParticle:
    x: float
    y: float
    start_x: float
    start_y: float
    color: QColor
    delay_ms: int


def _load_particles(
    limit: int,
) -> tuple[tuple[_Particle, ...], tuple[tuple[QColor, QColor], ...]]:
    """Use the Git artwork for light modes and the approved image for Heavy."""
    if limit != GPU_HEAVY_EMBLEM_POINTS:
        if limit not in {CPU_EMBLEM_POINTS, GPU_MEDIUM_EMBLEM_POINTS}:
            raise ValueError("Unsupported particle count")
        samples: list[list[int | float]] = json.loads(
            PARTICLES.read_text(encoding="utf-8")
        )
        rng = random.Random(7107)
        particles: list[_Particle] = []
        palette: list[tuple[QColor, QColor]] = []
        palette_indices: dict[tuple[int, int, int], int] = {}
        for x, y, red_value, green_value, blue_value in samples[:limit]:
            red, green, blue = int(red_value), int(green_value), int(blue_value)
            key = red // 32, green // 32, blue // 32
            if key not in palette_indices:
                peak = max(red, green, blue)
                alpha = 215 if peak >= 90 else 145
                color = QColor(
                    min(255, 12 + key[0] * 34),
                    min(255, 12 + key[1] * 34),
                    min(255, 18 + key[2] * 34),
                    alpha,
                )
                glow = QColor(color)
                glow.setAlpha(42 if peak >= 90 else 24)
                palette_indices[key] = len(palette)
                palette.append((color, glow))
            particles.append(
                _Particle(
                    x / 1000,
                    y / 1000,
                    palette_indices[key],
                    (red << 16) | (green << 8) | blue,
                    rng.random(),
                    rng.random(),
                    rng.randrange(0, 800),
                )
            )
        return tuple(particles), tuple(palette)

    source = QImage(str(REFERENCE))
    if source.isNull():
        raise FileNotFoundError(REFERENCE)
    resolution = 895
    image = source.scaled(
        resolution,
        resolution,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    position_rng = random.Random(895_800)
    samples = (
        (
            (x + 0.5 + (position_rng.random() - 0.5) * 0.9) / resolution,
            (y + 0.5 + (position_rng.random() - 0.5) * 0.9) / resolution,
            image.pixel(x, y) & 0xFFFFFF,
        )
        for y in range(resolution)
        for x in range(resolution)
        if (y * resolution + x + 1) * limit // (resolution * resolution)
        > (y * resolution + x) * limit // (resolution * resolution)
    )
    rng = random.Random(7107)
    particles: list[_Particle] = []
    palette: list[tuple[QColor, QColor]] = []
    palette_indices: dict[tuple[int, int, int], int] = {}
    for x, y, rgb in samples:
        red, green, blue = rgb >> 16, (rgb >> 8) & 255, rgb & 255
        palette_index = 0
        particles.append(
            _Particle(
                x,
                y,
                palette_index,
                rgb,
                rng.random(),
                rng.random(),
                rng.randrange(0, 800),
            )
        )
    return tuple(particles), tuple(palette)


def _ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


class CosmicDashboard(QLabel):
    """Cycle a dense particle emblem and translated point-based copy."""

    gpu_fallback = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setAccessibleName("KYRIN particle emblem")
        self._particles: tuple[_Particle, ...] = ()
        self._palette: tuple[tuple[QColor, QColor], ...] = ()
        self._elapsed = QElapsedTimer()
        self._elapsed_ms = 0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._advance)
        self._text_labels: tuple[QLabel, ...] = ()
        self._text_signature: tuple[object, ...] = ()
        self._text_particles: tuple[_TextParticle, ...] = ()
        self._last_phase = ""
        self._animation_enabled = True
        self._renderer = "cpu"
        self._static_image: QImage | None = None
        self._gpu_layer: DashboardGL | None = None

    def set_animation_enabled(self, enabled: bool) -> None:
        if self._animation_enabled == enabled:
            return
        self._animation_enabled = enabled
        self._elapsed_ms = 0
        self._timer.stop()
        if enabled:
            self._static_image = None
            self.set_renderer(self._renderer)
            if self.isVisible():
                self._elapsed.start()
                self._timer.start()
        else:
            self._release_gpu_layer()
            self._particles = ()
            self._palette = ()
            self._text_particles = ()
            self._text_signature = ()
        self.update()

    def set_renderer(self, renderer: str) -> None:
        self._renderer = renderer
        if not self._animation_enabled:
            return
        if renderer in {"gpu", "gpu_medium", "gpu_heavy"}:
            from kyrin.app.qt.dashboard_gl import DashboardGL

            limit = {
                "gpu": GPU_LIGHT_EMBLEM_POINTS,
                "gpu_medium": GPU_MEDIUM_EMBLEM_POINTS,
                "gpu_heavy": GPU_HEAVY_EMBLEM_POINTS,
            }[renderer]
            if len(self._particles) != limit:
                self._particles, self._palette = _load_particles(limit)
            if self._gpu_layer is None:
                self._gpu_layer = DashboardGL(self)
                self._gpu_layer.failed.connect(self.gpu_fallback)
                self._gpu_layer.setGeometry(self.rect())
            self._gpu_layer.show()
            self._gpu_layer.raise_()
            self._gpu_layer.update()
        else:
            self._release_gpu_layer()
            self._use_cpu_particles()
        self.update()

    def _release_gpu_layer(self) -> None:
        if self._gpu_layer is None:
            return
        layer = self._gpu_layer
        self._gpu_layer = None
        layer.cleanup_gl()
        layer.hide()
        layer.deleteLater()

    def _use_cpu_particles(self) -> None:
        if len(self._particles) != CPU_EMBLEM_POINTS:
            self._particles, self._palette = _load_particles(CPU_EMBLEM_POINTS)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._static_image = None
        if self._gpu_layer is not None:
            self._gpu_layer.setGeometry(self.rect())

    def set_text_source(self, labels: tuple[QLabel, ...]) -> None:
        """Reserve copy layout without showing regular QLabel glyphs."""
        self._text_labels = labels
        for label in labels:
            policy = label.sizePolicy()
            policy.setRetainSizeWhenHidden(True)
            label.setSizePolicy(policy)
            label.hide()

    def refresh_scene(self) -> None:
        self._static_image = None
        self.update()
        if self._gpu_layer is not None and self._gpu_layer.isVisible():
            self._gpu_layer.update()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._animation_enabled:
            if not self._particles:
                self.set_renderer(self._renderer)
            self._elapsed.start()
            self._timer.start()

    def hideEvent(self, event: QHideEvent) -> None:
        if self._timer.isActive():
            self._elapsed_ms += self._elapsed.elapsed()
            self._timer.stop()
        super().hideEvent(event)

    def current_phase(self) -> int:
        if not self._animation_enabled:
            return FORM_MS
        return int(
            (
                self._elapsed_ms
                + (self._elapsed.elapsed() if self._timer.isActive() else 0)
            )
            % CYCLE_MS
        )

    def _advance(self) -> None:
        phase = (self._elapsed_ms + self._elapsed.elapsed()) % CYCLE_MS
        if phase < FORM_MS:
            phase_name = "form"
        elif phase < FORM_MS + HOLD_MS:
            phase_name = "hold"
        elif phase < FORM_MS + HOLD_MS + DISPERSE_MS:
            phase_name = "disperse"
        else:
            phase_name = "scatter"
        self._timer.setInterval(33 if phase_name in {"form", "disperse"} else 150)
        if phase_name in {"form", "disperse"} or phase_name != self._last_phase:
            self.update()
            if self._gpu_layer is not None and self._gpu_layer.isVisible():
                self._gpu_layer.update()
        self._last_phase = phase_name

    @staticmethod
    def _amount(phase: int, delay_ms: int, duration_ms: int) -> float:
        if phase < FORM_MS:
            return _ease((phase - delay_ms) / duration_ms)
        if phase < FORM_MS + HOLD_MS:
            return 1.0
        if phase < FORM_MS + HOLD_MS + DISPERSE_MS:
            disperse = phase - FORM_MS - HOLD_MS
            return 1.0 - _ease((disperse - delay_ms * 0.10) / 1550)
        return 0.0

    def _text_points(self) -> tuple[_TextParticle, ...]:
        signature: tuple[object, ...] = tuple(
            (
                label.text(),
                label.font().toString(),
                label.geometry(),
                label.mapTo(self, QPoint()),
            )
            for label in self._text_labels
        )
        if signature == self._text_signature:
            return self._text_particles
        self.setAccessibleDescription(
            " ".join(label.text() for label in self._text_labels)
        )
        rng = random.Random(1912)
        points = []
        for index, label in enumerate(self._text_labels):
            if label.width() <= 0 or label.height() <= 0:
                continue
            image = QImage(
                label.width(),
                label.height(),
                QImage.Format.Format_ARGB32_Premultiplied,
            )
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            painter.setPen(Qt.GlobalColor.white)
            painter.setFont(label.font())
            painter.drawText(
                QRectF(image.rect()),
                int(Qt.AlignmentFlag.AlignLeading | Qt.TextFlag.TextWordWrap),
                label.text(),
            )
            painter.end()
            origin = label.mapTo(self, QPoint())
            color = QColor(244, 242, 255) if index == 0 else QColor(180, 204, 255)
            spacing = 3 if index == 0 else 2
            sampled = 0
            for y in range(0, image.height(), spacing):
                for x in range(0, image.width(), spacing):
                    if image.pixelColor(x, y).alpha() < 90:
                        continue
                    points.append(
                        _TextParticle(
                            origin.x() + x,
                            origin.y() + y,
                            rng.random(),
                            rng.random(),
                            color,
                            rng.randrange(0, 800),
                        )
                    )
                    sampled += 1
                    if (
                        sampled % 2 == 0
                        and x + 1 < image.width()
                        and y + 1 < image.height()
                        and image.pixelColor(x + 1, y + 1).alpha() >= 90
                    ):
                        points.append(
                            _TextParticle(
                                origin.x() + x + 1,
                                origin.y() + y + 1,
                                rng.random(),
                                rng.random(),
                                color,
                                rng.randrange(0, 800),
                            )
                        )
        self._text_signature = signature
        self._text_particles = tuple(points)
        return self._text_particles

    def _make_static_image(self) -> QImage:
        """Compose the approved artwork and current translated copy once."""
        width, height = max(1, self.width()), max(1, self.height())
        scale = self.devicePixelRatioF()
        image = QImage(
            round(width * scale),
            round(height * scale),
            QImage.Format.Format_RGB32,
        )
        image.setDevicePixelRatio(scale)
        image.fill(QColor(0, 0, 4))
        source = QImage(str(REFERENCE))
        if source.isNull():
            raise FileNotFoundError(REFERENCE)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        side = min(height * 0.94, width * 0.52)
        left = max(12.0, (width * 0.52 - side) / 2)
        top = (height - side) / 2
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        painter.drawImage(QRectF(left, top, side, side), source)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.setAccessibleDescription(
            " ".join(label.text() for label in self._text_labels)
        )
        for index, label in enumerate(self._text_labels):
            origin = label.mapTo(self, QPoint())
            painter.setPen(
                QColor(244, 242, 255) if index == 0 else QColor(180, 204, 255)
            )
            painter.setFont(label.font())
            painter.drawText(
                QRectF(origin.x(), origin.y(), label.width(), label.height()),
                int(Qt.AlignmentFlag.AlignLeading | Qt.TextFlag.TextWordWrap),
                label.text(),
            )
        painter.end()
        return image

    def paintEvent(self, event: QPaintEvent) -> None:
        if not self._animation_enabled:
            if self._static_image is None:
                self._static_image = self._make_static_image()
            painter = QPainter(self)
            painter.drawImage(0, 0, self._static_image)
            painter.end()
            return
        if self._gpu_layer is not None and self._gpu_layer.isVisible():
            if not self._gpu_layer.ready:
                painter = QPainter(self)
                painter.fillRect(self.rect(), QColor(0, 0, 4))
                painter.end()
            return
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(5, 8, 24))
        width = self.width()
        height = self.height()
        side = min(height * 0.94, width * 0.52)
        left = max(12.0, (width * 0.52 - side) / 2)
        top = (height - side) / 2
        cx = left + side * 0.50
        cy = top + side * 0.53
        phase = self.current_phase()
        halo_strength = self._amount(phase, 0, 2700)
        painter.setPen(Qt.PenStyle.NoPen)
        for halo_x, halo_y, radius, inner, middle in (
            (
                left + side * 0.34,
                top + side * 0.43,
                side * 0.62,
                QColor(9, 105, 250, int(76 * halo_strength)),
                QColor(6, 57, 176, int(33 * halo_strength)),
            ),
            (
                left + side * 0.69,
                top + side * 0.54,
                side * 0.58,
                QColor(149, 20, 240, int(67 * halo_strength)),
                QColor(84, 14, 159, int(30 * halo_strength)),
            ),
        ):
            halo = QRadialGradient(halo_x, halo_y, radius)
            halo.setColorAt(0, inner)
            halo.setColorAt(0.58, middle)
            halo.setColorAt(1, QColor(5, 8, 24, 0))
            painter.setBrush(halo)
            painter.drawEllipse(QPointF(halo_x, halo_y), radius, radius)

        painter.setBrush(QColor(2, 3, 12, int(245 * halo_strength)))
        painter.drawEllipse(QPointF(cx, cy), side * 0.148, side * 0.148)

        buckets: list[list[QPointF]] = [[] for _ in self._palette]
        for particle in self._particles:
            amount = self._amount(phase, particle.delay_ms, 2700)
            x = (1 - amount) * particle.start_x * width + amount * (
                left + particle.x * side
            )
            y = (1 - amount) * particle.start_y * height + amount * (
                top + particle.y * side
            )
            buckets[particle.palette_index].append(QPointF(x, y))

        # Batch points by color so a much denser emblem remains responsive.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setOpacity(0.20 + 0.80 * halo_strength)
        for (color, glow), points in zip(self._palette, buckets, strict=True):
            if not points:
                continue
            painter.setPen(QPen(glow, 3.4))
            painter.drawPoints(points)
            painter.setPen(QPen(color, 1.55))
            painter.drawPoints(points)
        painter.setOpacity(1.0)

        shade = QLinearGradient(width * 0.51, 0, width, 0)
        shade.setColorAt(0, QColor(5, 8, 24, 0))
        shade.setColorAt(1, QColor(5, 8, 24, int(215 * halo_strength)))
        painter.fillRect(self.rect(), shade)

        text_buckets: dict[int, list[QPointF]] = {}
        text_colors: dict[int, QColor] = {}
        for dot in self._text_points():
            amount = self._amount(phase, dot.delay_ms, 2700)
            point = QPointF(
                (1 - amount) * dot.start_x * width + amount * dot.x,
                (1 - amount) * dot.start_y * height + amount * dot.y,
            )
            key = dot.color.rgb()
            text_colors[key] = dot.color
            text_buckets.setdefault(key, []).append(point)
        painter.setOpacity(0.20 + 0.80 * halo_strength)
        for key, points in text_buckets.items():
            color = text_colors[key]
            core_pen = QPen(color, 2.0 if color.red() > 230 else 1.65)
            core_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(core_pen)
            painter.drawPoints(points)
