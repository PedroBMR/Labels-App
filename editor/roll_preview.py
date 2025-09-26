"""Animated preview widget simulating a continuous label roll."""

from __future__ import annotations

from typing import Any, Mapping

from PIL.ImageQt import ImageQt

from qt_compat import (
    QColor,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPainter,
    QPointF,
    QPixmap,
    QSlider,
    QStackedWidget,
    Qt,
    QTimer,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class PrinterRollPreviewWidget(QWidget):
    """Display a label preview animating through a simulated roll."""

    _REPEAT_COUNT = 4
    _TIMER_INTERVAL_MS = 16

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[QGraphicsPixmapItem] = []
        self._gap_px = 0.0
        self._label_height_px = 0.0
        self._loop_height = 0.0
        self._pixels_per_mm = 1.0
        self._speed_px_per_sec = 80.0

        self._timer = QTimer(self)
        self._timer.setInterval(self._TIMER_INTERVAL_MS)
        self._timer.timeout.connect(self._advance_animation)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        controls = QHBoxLayout()
        controls.setSpacing(6)

        self.play_button = QToolButton(self)
        self.play_button.setText("Iniciar")
        self.play_button.setCheckable(True)
        self.play_button.toggled.connect(self._toggle_animation)
        controls.addWidget(self.play_button)

        self.speed_slider = QSlider(Qt.Horizontal, self)
        self.speed_slider.setRange(10, 400)
        self.speed_slider.setSingleStep(10)
        self.speed_slider.setValue(int(self._speed_px_per_sec))
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        controls.addWidget(self.speed_slider, 1)

        self.speed_label = QLabel(self)
        controls.addWidget(self.speed_label)

        layout.addLayout(controls)

        self.scene = QGraphicsScene(self)
        self.scene.setBackgroundBrush(QColor("#f0f0f0"))
        self.view = QGraphicsView(self.scene, self)
        self.view.setRenderHints(self.view.renderHints() | QPainter.Antialiasing)
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.placeholder = QLabel("Simulação do rolo", self)
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet("background: #fff; border: 1px solid #ccc;")

        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.placeholder)
        self.stack.addWidget(self.view)
        self.stack.setCurrentWidget(self.placeholder)

        layout.addWidget(self.stack, 1)

        self._on_speed_changed(self.speed_slider.value())
        self._update_controls_enabled(False)

    # ------------------------------------------------------------------
    def set_image(self, image, metadata: Mapping[str, Any] | None = None) -> None:
        if image is None:
            self._clear()
            return

        qimage = ImageQt(image)
        pixmap = QPixmap.fromImage(qimage)

        self._pixels_per_mm = self._calculate_pixels_per_mm(pixmap.height(), metadata)
        self._gap_px = self._calculate_gap_px(metadata)
        self._label_height_px = float(pixmap.height())

        self.scene.clear()
        self._items = []

        spacing = self._label_height_px + self._gap_px
        for index in range(self._REPEAT_COUNT):
            item = QGraphicsPixmapItem(pixmap)
            self.scene.addItem(item)
            item.setPos(QPointF(0.0, index * spacing))
            self._items.append(item)

        width = pixmap.width()
        self._loop_height = spacing * len(self._items)
        self.scene.setSceneRect(0, 0, width, self._loop_height)
        self.view.centerOn(width / 2, self._label_height_px / 2)

        self._timer.stop()
        self.play_button.blockSignals(True)
        self.play_button.setChecked(False)
        self.play_button.blockSignals(False)
        self.play_button.setText("Iniciar")

        self.stack.setCurrentWidget(self.view)
        self._update_controls_enabled(True)

    # ------------------------------------------------------------------
    def _clear(self) -> None:
        self._timer.stop()
        self.play_button.setChecked(False)
        self.scene.clear()
        self._items = []
        self.stack.setCurrentWidget(self.placeholder)
        self._update_controls_enabled(False)

    def _toggle_animation(self, checked: bool) -> None:
        if not self._items:
            self.play_button.blockSignals(True)
            self.play_button.setChecked(False)
            self.play_button.blockSignals(False)
            return
        if checked:
            self.play_button.setText("Pausar")
            if not self._timer.isActive():
                self._timer.start()
        else:
            self.play_button.setText("Iniciar")
            self._timer.stop()

    def _on_speed_changed(self, value: int) -> None:
        self._speed_px_per_sec = float(max(value, 1))
        speed_mm = self._speed_px_per_sec / max(self._pixels_per_mm, 1.0)
        self.speed_label.setText(f"{speed_mm:.1f} mm/s")

    def _advance_animation(self) -> None:
        if not self._items:
            return
        delta = self._speed_px_per_sec * (self._TIMER_INTERVAL_MS / 1000.0)
        spacing = self._label_height_px + self._gap_px
        loop_height = self._loop_height or spacing
        for item in self._items:
            item.moveBy(0.0, -delta)
            if item.y() + self._label_height_px < 0.0:
                item.setY(item.y() + loop_height)

    def _calculate_gap_px(self, metadata: Mapping[str, Any] | None) -> float:
        if not metadata:
            return 0.0
        gap = metadata.get("gap_px")
        if gap is not None:
            try:
                return max(float(gap), 0.0)
            except (TypeError, ValueError):
                return 0.0
        gap_mm = metadata.get("gap_mm")
        if gap_mm in (None, ""):
            return 0.0
        try:
            gap_mm_float = float(gap_mm)
        except (TypeError, ValueError):
            return 0.0
        return max(gap_mm_float * self._pixels_per_mm, 0.0)

    def _calculate_pixels_per_mm(
        self, height_px: int, metadata: Mapping[str, Any] | None
    ) -> float:
        if not metadata:
            return 1.0
        height_mm = metadata.get("height_mm")
        if height_mm not in (None, ""):
            try:
                return height_px / max(float(height_mm), 1e-3)
            except (TypeError, ValueError):
                pass
        dots_per_mm = metadata.get("dots_per_mm")
        if dots_per_mm not in (None, ""):
            try:
                return float(dots_per_mm)
            except (TypeError, ValueError):
                pass
        dpi = metadata.get("dpi")
        if dpi not in (None, ""):
            try:
                return float(dpi) / 25.4
            except (TypeError, ValueError):
                pass
        return 1.0

    def _update_controls_enabled(self, enabled: bool) -> None:
        for widget in (self.play_button, self.speed_slider):
            widget.setEnabled(enabled)
        if not enabled:
            self.play_button.setText("Iniciar")

