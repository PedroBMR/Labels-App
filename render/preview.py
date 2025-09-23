"""Scene preview renderer based on Pillow."""
from __future__ import annotations

from typing import Tuple

from PIL import Image

from qt_compat import QLabel, QObject, QEvent, QImage, QPainter, QPixmap, Qt, QTimer

from editor.scene import LabelScene


class PreviewRenderer(QObject):
    """Renders a ``LabelScene`` into a ``QLabel`` using Pillow for scaling."""

    def __init__(self, scene: LabelScene, target: QLabel, dpi: float | None = None) -> None:
        super().__init__(target)
        self._scene = scene
        self._target = target
        self._dpi = dpi or scene.dpi
        self._buffer: bytes | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._render)
        scene.changed.connect(self.schedule)
        scene.templateChanged.connect(self.schedule)
        target.installEventFilter(self)
        self.schedule()

    # ------------------------------------------------------------------
    def schedule(self) -> None:
        """Throttle rendering to avoid excessive redraws."""
        if not self._timer.isActive():
            self._timer.start()

    def eventFilter(self, obj, event):  # noqa: D401 - Qt API
        if obj is self._target and event.type() == QEvent.Resize:
            self.schedule()
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    def _render(self) -> None:
        rect = self._scene.sceneRect()
        width = max(1, int(rect.width()))
        height = max(1, int(rect.height()))
        image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        self._scene.render(painter)
        painter.end()

        ptr = image.bits()
        ptr.setsize(image.byteCount())
        buffer = bytes(ptr)
        pil = Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1)
        pil.info["dpi"] = (self._dpi, self._dpi)
        target_size = self._target_size(width, height)
        if target_size != (width, height):
            pil = pil.resize(target_size, Image.LANCZOS)
        self._buffer = pil.tobytes("raw", "RGBA")
        qimage = QImage(self._buffer, pil.width, pil.height, QImage.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimage)
        self._target.setPixmap(pixmap)
        self._target.setAlignment(Qt.AlignCenter)

    def _target_size(self, width: int, height: int) -> Tuple[int, int]:
        avail_w = max(1, self._target.width() - 10)
        avail_h = max(1, self._target.height() - 10)
        if avail_w <= 1 or avail_h <= 1:
            avail_w = avail_h = max(width, height, 200)
        scale = min(avail_w / width, avail_h / height)
        scale = max(scale, 0.1)
        scale = min(scale, 4.0)
        scaled_w = max(1, int(width * scale))
        scaled_h = max(1, int(height * scale))
        return scaled_w, scaled_h

*** End Patch
