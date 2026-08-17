"""Reusable UI widgets: progress cells, donut chart and weekly history graph."""

from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..report import WEEKLY_REQUIREMENT_SECONDS, format_compact, format_duration, week_label

COLOR_OK = QColor("#2e7d32")
COLOR_BAD = QColor("#c62828")
COLOR_CURRENT = QColor("#1565c0")
COLOR_EMPTY = QColor("#cfd8dc")
COLOR_TEXT = QColor("#334155")


class ProgressCell(QWidget):
    """A compact progress bar plus a ``percentage + time / 30h`` label."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.label = QLabel("0%")
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)  # one decimal point of percentage
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.addWidget(self.bar)
        layout.addWidget(self.label)
        self.set_seconds(0.0)

    def set_seconds(self, seconds: float) -> None:
        percent = seconds / WEEKLY_REQUIREMENT_SECONDS * 100.0
        self.bar.setValue(int(round(percent * 10)))
        self.label.setText(f"{percent:.1f}%  ({format_compact(seconds)} / 30h)")
        ok = percent >= 100.0
        color = "#2e7d32" if ok else "#c62828"
        self.bar.setStyleSheet(
            f"""
            QProgressBar {{
                background: #e2e8f0;
                border: none;
                border-radius: 5px;
                min-height: 10px;
                max-height: 10px;
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: 5px;
            }}
            """
        )


class DonutChart(QWidget):
    """Donut showing completed (>=30h) vs not completed weeks."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(136, 136)
        self.completed = 0
        self.total = 0

    def set_stats(self, completed: int, total: int) -> None:
        self.completed = completed
        self.total = total
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(18, 18, -18, -18)
        pen = QPen()
        pen.setWidth(16)
        pen.setCapStyle(Qt.RoundCap)
        if self.total == 0:
            pen.setColor(COLOR_EMPTY)
            painter.setPen(pen)
            painter.drawArc(rect, 0, 360 * 16)
        else:
            pen.setColor(COLOR_OK)
            painter.setPen(pen)
            painter.drawArc(rect, 90 * 16, -int(self.completed / self.total * 360) * 16)
            pen.setColor(COLOR_BAD)
            painter.setPen(pen)
            painter.drawArc(
                rect, 90 * 16, -int((1 - self.completed / self.total) * 360) * 16
            )
        percent = round(self.completed / self.total * 100) if self.total else 0
        painter.setPen(QPen(COLOR_TEXT, 1))
        big = QFont(self.font())
        big.setPointSize(16)
        big.setBold(True)
        painter.setFont(big)
        painter.drawText(
            self.rect(), Qt.AlignCenter, f"{percent}%"
        )
        small = QFont(self.font())
        small.setPointSize(8)
        painter.setFont(small)
        painter.drawText(
            self.rect().adjusted(0, 22, 0, 0), Qt.AlignCenter, f"{self.completed}/{self.total} sem."
        )
        painter.end()


class WeekBlocksWidget(QWidget):
    """Horizontal row of colored blocks, one per week (scrollable)."""

    BLOCK = 18
    GAP = 4

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._weeks: list[dict] = []
        self.setMouseTracking(True)
        self.setFixedHeight(self.BLOCK + 8)

    def set_weeks(self, weeks: list[dict]) -> None:
        self._weeks = list(weeks)
        self.setFixedWidth(len(weeks) * (self.BLOCK + self.GAP) + 16)
        self.update()

    def _week_at(self, x: int) -> int | None:
        if x < 8:
            return None
        idx = (x - 8) // (self.BLOCK + self.GAP)
        return idx if 0 <= idx < len(self._weeks) else None

    def mouseMoveEvent(self, event):  # noqa: N802
        idx = self._week_at(event.pos().x())
        if idx is not None:
            week = self._weeks[idx]
            state = (
                "Completada"
                if week["met"]
                else ("En curso" if week["current"] else "No completada")
            )
            self.setToolTip(
                f"{week_label(week['week_start'])}\n"
                f"{format_duration(week['total_seconds'])} / 30h — {state}"
            )
        super().mouseMoveEvent(event)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for i, week in enumerate(self._weeks):
            x = 8 + i * (self.BLOCK + self.GAP)
            if week["current"]:
                color = COLOR_CURRENT
            elif week["met"]:
                color = COLOR_OK
            elif week["total_seconds"] > 0:
                color = COLOR_BAD
            else:
                color = COLOR_EMPTY
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(x, 4, self.BLOCK, self.BLOCK, 3, 3)
        painter.end()


def _legend_chip(parent: QWidget, color: QColor, text: str) -> QWidget:
    box = QLabel(" ")
    box.setFixedSize(14, 14)
    box.setStyleSheet(
        f"background: {color.name()}; border-radius: 4px;"
    )
    label = QLabel(text)
    holder = QWidget(parent)
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    row.addWidget(box)
    row.addWidget(label)
    return holder


class WeeklyHistoryWidget(QWidget):
    """Summary + donut + scrollable week blocks + legend, with no overlap:

    each piece is its own widget managed by layouts (no manual painting on top).
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.summary = QLabel("")
        self.summary.setStyleSheet("font-weight: 600;")
        self.donut = DonutChart()
        self.blocks = WeekBlocksWidget()

        header = QHBoxLayout()
        header.addWidget(self.summary, 1)
        header.addStretch(1)
        header.addWidget(self.donut)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidget(self.blocks)
        self.scroll.setFixedHeight(self.blocks.BLOCK + 20)

        legend = QHBoxLayout()
        legend.setSpacing(16)
        legend.addWidget(_legend_chip(self, COLOR_OK, "Completada (≥30h)"))
        legend.addWidget(_legend_chip(self, COLOR_BAD, "No completada"))
        legend.addWidget(_legend_chip(self, COLOR_CURRENT, "En curso"))
        legend.addWidget(_legend_chip(self, COLOR_EMPTY, "Sin horas"))
        legend.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addWidget(self.scroll)
        layout.addLayout(legend)

    def set_weeks(self, weeks: list[dict]) -> None:
        completed = sum(1 for w in weeks if w["met"])
        if weeks:
            self.summary.setText(
                f"Semanas: {completed} de {len(weeks)} completadas (meta 30h semanales)"
            )
        else:
            self.summary.setText("Sin sesiones registradas.")
        self.donut.set_stats(completed, len(weeks))
        self.blocks.set_weeks(weeks)