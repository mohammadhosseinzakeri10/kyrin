"""Preview/export mascot design stages 1-7 without loading the live extension."""

import argparse
import json
import sys
import time
from pathlib import Path

from PySide6.QtCore import QByteArray, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QColor, QFont, QImage, QPainter, QPaintEvent
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from scripts.desktop.mascot_preview_model import ASSETS, Baseline, RunCycle

_DARK = QColor("#101426")
_LIGHT = QColor("#f4f6fc")


def render_svg(source: bytes, pixels: int) -> QImage:
    renderer = QSvgRenderer(QByteArray(source))
    if not renderer.isValid():
        raise ValueError("Invalid prototype SVG")
    renderer.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
    image = QImage(pixels, pixels, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, pixels, pixels))
    painter.end()
    return image


def label(painter: QPainter, text: str, rect: QRect, *, light: bool = False) -> None:
    painter.setPen(QColor("#182342" if light else "#e5edff"))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


def comparison(
    cycle: RunCycle,
    baseline: Baseline,
    milliseconds: float,
    duration: int,
    pixels: int = 224,
    *,
    light: bool = False,
) -> QImage:
    """Same logical size and elapsed time; current on right, candidate on left."""
    column = max(260, pixels + 44)
    width = column * 2
    height = pixels + 70
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(_LIGHT if light else _DARK)
    painter = QPainter(image)
    painter.setFont(QFont("DejaVu Sans", 12))
    label(painter, "دویدن اصلاح‌شده؛ روبه‌رو", QRect(0, 5, column, 32), light=light)
    label(painter, "حرکت فعلی", QRect(column, 5, column, 32), light=light)
    candidate = render_svg(cycle.svg(milliseconds / duration), pixels)
    # Start inside the steady periodic loop, rather than the startup transition.
    current = render_svg(baseline.svg(1920 + milliseconds), pixels)
    painter.drawImage((column - pixels) // 2, 40, candidate)
    painter.drawImage(column + (column - pixels) // 2, 40, current)
    painter.setFont(QFont("DejaVu Sans", 10))
    label(
        painter,
        f"چرخهٔ پیشنهادی: {duration} میلی‌ثانیه · اندازه: {pixels} پیکسل",
        QRect(0, height - 27, width, 24),
        light=light,
    )
    painter.end()
    return image


def save(image: QImage, path: Path) -> None:
    if not image.save(str(path)):
        raise OSError(f"Could not save {path}")


def export(cycle: RunCycle, baseline: Baseline, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    duration = cycle.duration_ms
    for pixels in (112, 224):
        for light, theme in ((False, "dark"), (True, "light")):
            save(
                comparison(cycle, baseline, 0, duration, pixels, light=light),
                output / f"comparison-{pixels}-{theme}.png",
            )
    sheet = QImage(840, 390, QImage.Format.Format_ARGB32_Premultiplied)
    sheet.fill(_DARK)
    painter = QPainter(sheet)
    painter.fillRect(0, 195, 840, 195, _LIGHT)
    painter.setFont(QFont("DejaVu Sans", 10))
    phases = ("تماس چپ", "تکیهٔ چپ", "پرواز", "تماس راست", "تکیهٔ راست", "پرواز")
    for index, text in enumerate(phases):
        x = (5 - index) * 140
        for light, y in ((False, 0), (True, 195)):
            label(painter, text, QRect(x, y + 6, 140, 26), light=light)
            painter.drawImage(x + 14, y + 39, render_svg(cycle.svg(index / 6), 112))
            label(painter, f"{index + 1} / 6", QRect(x, y + 156, 140, 28), light=light)
    painter.end()
    save(sheet, output / "six-keyposes.png")
    # 1920 ms is a complete common period of 640 ms and the old 480 ms loop.
    frames = output / "comparison-frames"
    frames.mkdir(exist_ok=True)
    for index in range(60):
        save(
            comparison(cycle, baseline, index * 32, duration),
            frames / f"{index:03}.png",
        )
    for cadence in cycle.data["comparison_durations_ms"]:
        folder = output / f"cadence-{cadence}"
        folder.mkdir(exist_ok=True)
        for index in range(24):
            canvas = QImage(280, 290, QImage.Format.Format_ARGB32_Premultiplied)
            canvas.fill(_DARK)
            painter = QPainter(canvas)
            painter.setFont(QFont("DejaVu Sans", 12))
            label(painter, f"چرخهٔ {cadence} میلی‌ثانیه", QRect(0, 4, 280, 30))
            painter.drawImage(28, 40, render_svg(cycle.svg(index / 24), 224))
            painter.end()
            save(canvas, folder / f"{index:03}.png")
    (output / "export.json").write_text(
        json.dumps(
            {
                "status": "prototype_pending_owner_visual_acceptance",
                "default_duration_ms": duration,
                "view": cycle.data["view"],
                "source": str(ASSETS),
                "comparison": {"frames": 60, "total_ms": 1920, "sample_step_ms": 32},
                "cadences": cycle.data["comparison_durations_ms"],
                "baseline_sha256": baseline.data["sha256"],
                "native_gnome_rendering_tested": False,
                "resource_benchmark_performed": False,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Exported prototype comparison and poses to {output}")


class ComparisonCanvas(QWidget):
    def __init__(self, cycle: RunCycle, baseline: Baseline) -> None:
        super().__init__()
        self.cycle = cycle
        self.baseline = baseline
        self.milliseconds = 0.0
        self.duration = cycle.duration_ms
        self.pixels = 224
        self.setMinimumSize(540, 600)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        for light, y in ((False, 0), (True, self.pixels + 70)):
            image = comparison(
                self.cycle,
                self.baseline,
                self.milliseconds,
                self.duration,
                self.pixels,
                light=light,
            )
            painter.drawImage((self.width() - image.width()) // 2, y, image)
        painter.end()


class Preview(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("پیش‌نمایش طراحی حرکت KYRIN؛ مراحل ۱ تا ۷")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.cycle = RunCycle.load()
        self.canvas = ComparisonCanvas(self.cycle, Baseline())
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.started = 0.0
        self.offset_ms = 0.0
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("مقایسهٔ حرکت فعلی و دویدن پیشنهادی؛ زمینهٔ روشن و تیره"))
        controls = QHBoxLayout()
        self.play = QPushButton("پخش ۶ چرخه")
        self.play.clicked.connect(self._play)
        self.pause = QPushButton("توقف")
        self.pause.clicked.connect(self.timer.stop)
        self.cadence = QComboBox()
        self.cadence.setAccessibleName("مدت یک چرخهٔ دویدن")
        for duration in self.cycle.data["comparison_durations_ms"]:
            self.cadence.addItem(f"{duration} میلی‌ثانیه", duration)
        self.cadence.setCurrentIndex(1)
        self.cadence.currentIndexChanged.connect(self._change_cadence)
        self.size_choice = QComboBox()
        self.size_choice.setAccessibleName("اندازهٔ نمایش کاراکتر")
        self.size_choice.addItem("اندازهٔ واقعی: ۱۱۲ پیکسل", 112)
        self.size_choice.addItem("بزرگ‌نمایی: ۲۲۴ پیکسل", 224)
        self.size_choice.setCurrentIndex(1)
        self.size_choice.currentIndexChanged.connect(self._change_size)
        for widget in (self.play, self.pause, self.cadence, self.size_choice):
            controls.addWidget(widget)
        layout.addLayout(controls)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setAccessibleName("موقعیت در چرخهٔ حرکت پیشنهادی")
        self.slider.valueChanged.connect(self._scrub)
        layout.addWidget(self.slider)
        layout.addWidget(self.canvas)
        layout.addWidget(QLabel("نمونهٔ مستقل؛ هنوز به وضعیت‌های برنامه متصل نشده است."))
        self.resize(800, 770)

    def _play(self) -> None:
        self.offset_ms = self.canvas.milliseconds
        self.started = time.monotonic()
        self.timer.start()

    def _tick(self) -> None:
        delta = (time.monotonic() - self.started) * 1000
        self.canvas.milliseconds = self.offset_ms + min(delta, self.canvas.duration * 6)
        self.slider.blockSignals(True)
        self.slider.setValue(
            round((self.canvas.milliseconds / self.canvas.duration % 1) * 1000)
        )
        self.slider.blockSignals(False)
        self.canvas.update()
        if delta >= self.canvas.duration * 6:
            self.timer.stop()

    def _scrub(self, position: int) -> None:
        self.timer.stop()
        self.canvas.milliseconds = position / 1000 * self.canvas.duration
        self.canvas.update()

    def _change_cadence(self, index: int) -> None:
        del index
        phase = self.canvas.milliseconds / self.canvas.duration
        self.timer.stop()
        self.canvas.duration = int(self.cadence.currentData())
        self.canvas.milliseconds = phase * self.canvas.duration
        self.canvas.update()

    def _change_size(self, index: int) -> None:
        del index
        self.canvas.pixels = int(self.size_choice.currentData())
        self.canvas.setMinimumHeight((self.canvas.pixels + 70) * 2)
        self.canvas.update()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.timer.stop()
        super().closeEvent(event)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, help="Export PNG evidence and exit")
    args = parser.parse_args()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    if args.export is not None:
        export(RunCycle.load(), Baseline(), args.export)
        return
    preview = Preview()
    preview.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
