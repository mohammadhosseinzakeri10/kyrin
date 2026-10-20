"""OpenGL renderer for the dashboard's two-dimensional particle animation."""

from array import array

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from kyrin.app.qt.dashboard import CosmicDashboard

_VERTEX = """
#ifdef GL_ES
precision highp float;
#endif
attribute vec2 startPosition;
attribute vec2 targetPosition;
attribute vec3 pointColor;
attribute float delayMs;
attribute float durationMs;
attribute float pointSize;
uniform float phaseMs;
varying vec3 color;
float ease(float value) {
    float t = clamp(value, 0.0, 1.0);
    return t * t * (3.0 - 2.0 * t);
}
void main() {
    float amount;
    if (phaseMs < 3500.0) {
        amount = ease((phaseMs - delayMs) / durationMs);
    } else if (phaseMs < 5000.0) {
        amount = 1.0;
    } else if (phaseMs < 6750.0) {
        amount = 1.0 - ease((phaseMs - 5000.0 - delayMs * 0.10) / 1550.0);
    } else {
        amount = 0.0;
    }
    vec2 position = mix(startPosition, targetPosition, amount);
    gl_Position = vec4(position.x * 2.0 - 1.0,
                       1.0 - position.y * 2.0, 0.0, 1.0);
    gl_PointSize = pointSize;
    color = pointColor * (0.20 + 0.80 * amount);
}
"""

_FRAGMENT = """
#ifdef GL_ES
precision mediump float;
#endif
varying vec3 color;
void main() {
    float distanceFromCenter = length(gl_PointCoord - vec2(0.5));
    float alpha = 1.0 - smoothstep(0.18, 0.5, distanceFromCenter);
    gl_FragColor = vec4(color, alpha);
}
"""

_BACKGROUND_VERTEX = """
attribute vec2 corner;
varying vec2 uv;
void main() {
    gl_Position = vec4(corner, 0.0, 1.0);
    uv = vec2((corner.x + 1.0) * 0.5, (1.0 - corner.y) * 0.5);
}
"""

_BACKGROUND_FRAGMENT = """
#ifdef GL_ES
precision highp float;
#endif
varying vec2 uv;
uniform float screenWidth;
uniform float screenHeight;
uniform float leftEdge;
uniform float topEdge;
uniform float emblemSide;
uniform float strength;
void main() {
    vec2 pixel = uv * vec2(screenWidth, screenHeight);
    vec2 blueCenter = vec2(leftEdge + emblemSide * 0.34,
                           topEdge + emblemSide * 0.43);
    vec2 purpleCenter = vec2(leftEdge + emblemSide * 0.69,
                             topEdge + emblemSide * 0.54);
    float blue = pow(max(0.0, 1.0 - distance(pixel, blueCenter) /
                     (emblemSide * 0.62)), 2.0);
    float purple = pow(max(0.0, 1.0 - distance(pixel, purpleCenter) /
                       (emblemSide * 0.58)), 2.0);
    vec3 color = vec3(0.020, 0.031, 0.094);
    color += vec3(0.025, 0.20, 0.48) * blue * strength;
    color += vec3(0.31, 0.035, 0.46) * purple * strength;
    vec2 center = vec2(leftEdge + emblemSide * 0.50,
                       topEdge + emblemSide * 0.53);
    float hole = 1.0 - smoothstep(emblemSide * 0.145,
                                  emblemSide * 0.151,
                                  distance(pixel, center));
    color = mix(color, vec3(0.008, 0.012, 0.047), hole * strength);
    gl_FragColor = vec4(color, 1.0);
}
"""


class DashboardGL(QOpenGLWidget):
    """Keep two-dimensional particle positions on the GPU between frames."""

    failed = Signal()

    def __init__(self, dashboard: CosmicDashboard) -> None:
        super().__init__(dashboard)
        self.dashboard = dashboard
        self.ready = False
        self._program: QOpenGLShaderProgram | None = None
        self._buffer: QOpenGLBuffer | None = None
        self._vao: QOpenGLVertexArrayObject | None = None
        self._background_program: QOpenGLShaderProgram | None = None
        self._background_buffer: QOpenGLBuffer | None = None
        self._background_vao: QOpenGLVertexArrayObject | None = None
        self._signature: tuple[object, ...] | None = None
        self._point_count = 0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        QTimer.singleShot(100, self._check_context)

    def _check_context(self) -> None:
        if self.isVisible() and not self.ready and not self.isValid():
            self._fallback()

    def initializeGL(self) -> None:
        program = QOpenGLShaderProgram(self)
        if not (
            program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, _VERTEX)
            and program.addShaderFromSourceCode(
                QOpenGLShader.ShaderTypeBit.Fragment, _FRAGMENT
            )
            and program.link()
        ):
            QTimer.singleShot(0, self._fallback)
            return
        background = QOpenGLShaderProgram(self)
        if not (
            background.addShaderFromSourceCode(
                QOpenGLShader.ShaderTypeBit.Vertex, _BACKGROUND_VERTEX
            )
            and background.addShaderFromSourceCode(
                QOpenGLShader.ShaderTypeBit.Fragment, _BACKGROUND_FRAGMENT
            )
            and background.link()
        ):
            QTimer.singleShot(0, self._fallback)
            return
        buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        vao = QOpenGLVertexArrayObject(self)
        background_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        background_vao = QOpenGLVertexArrayObject(self)
        if not (
            buffer.create() and vao.create()
            and background_buffer.create() and background_vao.create()
        ):
            QTimer.singleShot(0, self._fallback)
            return
        vertices = array("f", (-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1))
        payload = vertices.tobytes()
        background_buffer.bind()
        background_buffer.allocate(payload, len(payload))
        background_buffer.release()
        self._program = program
        self._buffer = buffer
        self._vao = vao
        self._background_program = background
        self._background_buffer = background_buffer
        self._background_vao = background_vao
        self.ready = True

    def _fallback(self) -> None:
        self.ready = False
        self.hide()
        self.dashboard._use_cpu_particles()
        self.dashboard.update()
        self.failed.emit()

    def _upload_points(self) -> None:
        dashboard = self.dashboard
        width = max(1, dashboard.width())
        height = max(1, dashboard.height())
        text_points = dashboard._text_points()
        signature: tuple[object, ...] = (
            width, height, dashboard._text_signature, len(dashboard._particles)
        )
        if signature == self._signature:
            return
        side = min(height * 0.94, width * 0.52)
        left = max(12.0, (width * 0.52 - side) / 2)
        top = (height - side) / 2
        data = array("f")
        for dot in dashboard._particles:
            color = dashboard._palette[dot.palette_index][0]
            data.extend((
                dot.start_x, dot.start_y,
                (left + dot.x * side) / width,
                (top + dot.y * side) / height,
                color.redF(), color.greenF(), color.blueF(),
                float(dot.delay_ms), 2700.0, 2.5,
            ))
        for text_dot in text_points:
            data.extend((
                text_dot.start_x, text_dot.start_y,
                text_dot.x / width, text_dot.y / height,
                text_dot.color.redF(), text_dot.color.greenF(),
                text_dot.color.blueF(),
                float(text_dot.delay_ms), 1200.0, 2.8,
            ))
        assert self._buffer is not None
        if not self._buffer.bind():
            self._fallback()
            return
        payload = data.tobytes()
        self._buffer.allocate(payload, len(payload))
        self._buffer.release()
        self._point_count = len(data) // 10
        self._signature = signature

    def paintGL(self) -> None:
        if not self.ready:
            return
        dashboard = self.dashboard
        width = self.width()
        height = self.height()
        phase = dashboard.current_phase()
        strength = dashboard._amount(phase, 0, 2700)
        side = min(height * 0.94, width * 0.52)
        left = max(12.0, (width * 0.52 - side) / 2)
        top = (height - side) / 2
        background = self._background_program
        background_buffer = self._background_buffer
        background_vao = self._background_vao
        assert background is not None and background_buffer is not None
        assert background_vao is not None
        background.bind()
        background_vao.bind()
        background_buffer.bind()
        for name, value in (
            ("screenWidth", width), ("screenHeight", height),
            ("leftEdge", left), ("topEdge", top),
            ("emblemSide", side), ("strength", strength),
        ):
            background.setUniformValue1f(
                background.uniformLocation(name), float(value)
            )
        corner = background.attributeLocation("corner")
        background.enableAttributeArray(corner)
        background.setAttributeBuffer(corner, 0x1406, 0, 2, 8)
        self.context().functions().glDrawArrays(0x0004, 0, 6)  # GL_TRIANGLES
        background_buffer.release()
        background_vao.release()
        background.release()

        self._upload_points()
        if not self.ready:
            return
        program = self._program
        buffer = self._buffer
        vao = self._vao
        assert program is not None and buffer is not None and vao is not None
        if not program.bind():
            self._fallback()
            return
        vao.bind()
        if not buffer.bind():
            vao.release()
            program.release()
            self._fallback()
            return
        program.setUniformValue1f(program.uniformLocation("phaseMs"), float(phase))
        stride = 10 * 4
        for name, offset, count in (
            ("startPosition", 0, 2),
            ("targetPosition", 2, 2),
            ("pointColor", 4, 3),
            ("delayMs", 7, 1),
            ("durationMs", 8, 1),
            ("pointSize", 9, 1),
        ):
            attribute = program.attributeLocation(name)
            program.enableAttributeArray(attribute)
            program.setAttributeBuffer(attribute, 0x1406, offset * 4, count, stride)
        functions = self.context().functions()
        functions.glEnable(0x0BE2)  # GL_BLEND
        if not self.context().isOpenGLES():
            functions.glEnable(0x8642)  # GL_PROGRAM_POINT_SIZE
        functions.glBlendFunc(0x0302, 0x0303)  # SRC_ALPHA, ONE_MINUS_SRC_ALPHA
        functions.glDrawArrays(0x0000, 0, self._point_count)  # GL_POINTS
        buffer.release()
        vao.release()
        program.release()
