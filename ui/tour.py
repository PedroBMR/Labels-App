"""Reusable guided tour utilities for the label editor UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from qt_compat import (
    QCheckBox,
    QColor,
    QDialog,
    QEvent,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMargins,
    QObject,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPushButton,
    QRect,
    QTimer,
    Qt,
    QVBoxLayout,
    QWidget,
    QPoint,
    QSize,
)


@dataclass(slots=True)
class TourStep:
    """Single onboarding step describing a portion of the interface."""

    title: str
    body: str
    anchor: QWidget | None
    highlight_padding: int = 16
    screenshot: QPixmap | None = None

    def ensure_screenshot(self) -> None:
        """Grab a lightweight preview of the anchor widget."""

        if self.anchor is None or self.screenshot is not None:
            return
        if not self.anchor.isVisible():
            return
        try:
            pixmap = self.anchor.grab()
        except RuntimeError:
            return
        if pixmap and not pixmap.isNull():
            self.screenshot = pixmap


class GuidedTourDialog(QDialog):
    """Overlay dialog that guides the user through the editor features."""

    def __init__(
        self,
        parent: QWidget,
        steps: Sequence[TourStep],
        *,
        dont_show_checked: bool = False,
    ) -> None:
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self._steps: list[TourStep] = list(steps)
        self._current_index = 0
        self._highlight_rect: QRect | None = None
        self._completed = False

        self._card = QFrame(self)
        self._card.setObjectName("GuidedTourCard")
        self._card.setFrameShape(QFrame.StyledPanel)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(12)

        self._title_label = QLabel()
        self._title_label.setObjectName("GuidedTourTitle")
        self._title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card_layout.addWidget(self._title_label)

        self._body_label = QLabel()
        self._body_label.setWordWrap(True)
        self._body_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card_layout.addWidget(self._body_label)

        self._screenshot_label = QLabel()
        self._screenshot_label.setObjectName("GuidedTourScreenshot")
        self._screenshot_label.setAlignment(Qt.AlignCenter)
        self._screenshot_label.setVisible(False)
        card_layout.addWidget(self._screenshot_label)

        footer = QHBoxLayout()
        footer.setSpacing(8)

        self._dont_show_checkbox = QCheckBox("Não mostrar novamente")
        self._dont_show_checkbox.setChecked(dont_show_checked)
        footer.addWidget(self._dont_show_checkbox)
        footer.addStretch(1)

        self._prev_button = QPushButton("Anterior")
        self._prev_button.clicked.connect(self._go_previous)
        footer.addWidget(self._prev_button)

        self._next_button = QPushButton("Próximo")
        self._next_button.clicked.connect(self._go_next)
        footer.addWidget(self._next_button)

        self._close_button = QPushButton("Pular")
        self._close_button.clicked.connect(self.reject)
        footer.addWidget(self._close_button)

        card_layout.addLayout(footer)

        self._card.setStyleSheet(
            "#GuidedTourCard {"
            "  background: rgba(30, 30, 30, 215);"
            "  color: white;"
            "  border-radius: 12px;"
            "}"
            "#GuidedTourTitle {"
            "  font-weight: 600;"
            "  font-size: 16px;"
            "}"
            "#GuidedTourScreenshot {"
            "  background: rgba(255, 255, 255, 0.15);"
            "  border-radius: 8px;"
            "  padding: 8px;"
            "}"
            "QPushButton {"
            "  background: rgba(255, 255, 255, 0.12);"
            "  border: 1px solid rgba(255, 255, 255, 0.35);"
            "  border-radius: 6px;"
            "  color: white;"
            "  padding: 6px 14px;"
            "}"
            "QPushButton:disabled {"
            "  background: rgba(255, 255, 255, 0.05);"
            "  border-color: rgba(255, 255, 255, 0.12);"
            "  color: rgba(255, 255, 255, 0.4);"
            "}"
        )

        parent.installEventFilter(self)

    # ------------------------------------------------------------------
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.parent() and event.type() in {QEvent.Resize, QEvent.Move}:
            QTimer.singleShot(0, self._sync_geometry)
        return super().eventFilter(watched, event)

    # ------------------------------------------------------------------
    def exec(self) -> int:  # noqa: D401 - Qt API
        if not self._steps:
            return QDialog.Rejected
        for step in self._steps:
            step.ensure_screenshot()
        self._sync_geometry()
        self._update_step()
        return super().exec()

    # ------------------------------------------------------------------
    @property
    def dont_show_again(self) -> bool:
        return self._dont_show_checkbox.isChecked()

    # ------------------------------------------------------------------
    @property
    def completed(self) -> bool:
        return self._completed

    # ------------------------------------------------------------------
    def _sync_geometry(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        origin = parent.mapToGlobal(parent.rect().topLeft())
        self.setGeometry(QRect(origin, parent.size()))
        self._position_card()
        self._update_highlight()

    # ------------------------------------------------------------------
    def _update_step(self) -> None:
        step = self._steps[self._current_index]
        self._title_label.setText(step.title)
        self._body_label.setText(step.body)

        screenshot = step.screenshot
        if screenshot is not None and not screenshot.isNull():
            max_width = 360
            max_height = 220
            scaled = screenshot.scaled(
                QSize(max_width, max_height),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self._screenshot_label.setPixmap(scaled)
            self._screenshot_label.setVisible(True)
        else:
            self._screenshot_label.clear()
            self._screenshot_label.setVisible(False)

        self._prev_button.setEnabled(self._current_index > 0)
        is_last = self._current_index == len(self._steps) - 1
        self._next_button.setText("Concluir" if is_last else "Próximo")
        self._close_button.setVisible(not is_last)
        self._update_highlight()
        self._position_card()

    # ------------------------------------------------------------------
    def _update_highlight(self) -> None:
        if not self._steps:
            return
        step = self._steps[self._current_index]
        if step.anchor is None or not step.anchor.isVisible():
            self._highlight_rect = None
            self.update()
            return
        rect = step.anchor.rect()
        top_left = step.anchor.mapToGlobal(rect.topLeft())
        bottom_right = step.anchor.mapToGlobal(rect.bottomRight())
        mapped_top_left = self.mapFromGlobal(top_left)
        mapped_bottom_right = self.mapFromGlobal(bottom_right)
        highlight = QRect(mapped_top_left, mapped_bottom_right)
        highlight = highlight.normalized()
        highlight = highlight.marginsAdded(
            QMargins(
                step.highlight_padding,
                step.highlight_padding,
                step.highlight_padding,
                step.highlight_padding,
            )
        )
        highlight = highlight.intersected(self.rect())
        if highlight.isNull():
            self._highlight_rect = None
        else:
            self._highlight_rect = highlight
        self.update()

    # ------------------------------------------------------------------
    def _position_card(self) -> None:
        if not self._steps:
            return
        self._card.adjustSize()
        card_size = self._card.size()
        margin = 24
        available_rect = self.rect().adjusted(margin, margin, -margin, -margin)

        if self._highlight_rect:
            highlight = self._highlight_rect
            positions: list[QPoint] = []
            right_pos = QPoint(highlight.right() + margin, highlight.top())
            left_pos = QPoint(highlight.left() - card_size.width() - margin, highlight.top())
            bottom_pos = QPoint(highlight.left(), highlight.bottom() + margin)
            top_pos = QPoint(highlight.left(), highlight.top() - card_size.height() - margin)
            positions.extend([right_pos, left_pos, bottom_pos, top_pos])

            for pos in positions:
                candidate = QRect(pos, card_size)
                if available_rect.contains(candidate):
                    self._card.move(candidate.topLeft())
                    return

            fallback_x = min(
                max(available_rect.left(), highlight.center().x() - card_size.width() // 2),
                available_rect.right() - card_size.width(),
            )
            fallback_y = min(
                max(available_rect.top(), highlight.bottom() + margin),
                available_rect.bottom() - card_size.height(),
            )
            self._card.move(fallback_x, fallback_y)
            return

        center_x = available_rect.center().x() - card_size.width() // 2
        center_y = available_rect.center().y() - card_size.height() // 2
        self._card.move(max(available_rect.left(), center_x), max(available_rect.top(), center_y))

    # ------------------------------------------------------------------
    def _go_previous(self) -> None:
        if self._current_index <= 0:
            return
        self._current_index -= 1
        self._update_step()

    # ------------------------------------------------------------------
    def _go_next(self) -> None:
        if self._current_index >= len(self._steps) - 1:
            self._completed = True
            self.accept()
            return
        self._current_index += 1
        self._update_step()

    # ------------------------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: D401 - Qt API
        if event.key() in (Qt.Key_Escape,):
            self.reject()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self._go_next()
            return
        if event.key() in (Qt.Key_Left, Qt.Key_Backspace):
            self._go_previous()
            return
        if event.key() == Qt.Key_Right:
            self._go_next()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: D401 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        overlay_color = QColor(0, 0, 0, 180)
        full_path = QPainterPath()
        full_path.addRect(self.rect())
        if self._highlight_rect:
            highlight_path = QPainterPath()
            highlight_path.addRoundedRect(self._highlight_rect, 10, 10)
            full_path = full_path.subtracted(highlight_path)
            painter.fillPath(full_path, overlay_color)
            painter.setPen(QPen(QColor(255, 255, 255, 220), 2))
            painter.drawRoundedRect(self._highlight_rect, 10, 10)
        else:
            painter.fillRect(self.rect(), overlay_color)

    # ------------------------------------------------------------------
    def reject(self) -> None:  # noqa: D401 - Qt API
        self._completed = False
        super().reject()


__all__ = ["GuidedTourDialog", "TourStep"]
