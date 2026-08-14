"""Reusable UI widgets: progress cells and the weekly history graph."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from ..report import WEEKLY_REQUIREMENT_SECONDS, format_compact, week_label

COLOR_OK = QColor("#2e7d32")
COLOR_BAD = QColor("#c62828")
COLOR_CURRENT = QColor("#1565c0")
COLOR_EMPTY = QColor("#cfd8dc")
COLOR_TEXT = QColor("#212121")


class ProgressCell(QWidget):
    """A compact progress bar plus a ``percentage + time / 30h`` label."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.label = QLabel("0%")
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)  # one decimal point of percentage
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(14)
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
                border-radius: 6px;
                min-height: 10px;
                max-height: 10px;
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: 6px;
            }}
            """
        )


class WeeklyHistoryWidget(QWidget):
    """Graph of completed (green) vs incomplete (red) weeks per user.

    Each block is one week, from the user's first session to the current week.
    Hovering over a block shows a tooltip with year, month and last day (Sunday).
    """

    BLOCK = 20
    GAP = 4

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._weeks: list[dict] = []
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.setMouseTracking(True)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self.summary)
        self.setMinimumHeight(self.BLOCK + 28)

    def set_weeks(self, weeks: list[dict]) -> None:
        self._weeks = list(weeks)
        completed = sum(1 for w in weeks if w["met"])
        if weeks:
            self.summary.setText(
                f"Semanas: {completed} de {len(weeks)} completadas "
                f"(meta 30h semanales)"
            )
        else:
            self.summary.setText("Sin sesiones registradas.")
        self.update()

    def sizeHint(self):  # noqa: N802
        from PySide6.QtCore import QSize

        cols = max(1, len(self._weeks))
        return QSize(cols * (self.BLOCK + self.GAP) + 20, self.BLOCK + 32)

    def _week_at(self, pos) -> int | None:
        for i in range(len(self._weeks)):
            x = 8 + i * (self.BLOCK + self.GAP)
            if x <= pos.x() <= x + self.BLOCK:
                return i
        return None

    def mouseMoveEvent(self, event):  # noqa: N802
        idx = self._week_at(event.pos())
        if idx is not None:
            week = self._weeks[idx]
            label = week_label(week["week_start"])
            state = (
                "Completada"
                if week["met"]
                else ("En curso" if week["current"] else "No completada")
            )
            self.setToolTip(
                f"{label}\n{format_compact(week['total_seconds'])} / 30h — {state}"
            )
        super().mouseMoveEvent(event)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        y = self.BLOCK + 4
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
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.setBrush(color)
            painter.drawRoundedRect(x, 4, self.BLOCK, self.BLOCK, 3, 3)
        legend = [
            ("Completada", COLOR_OK),
            ("No completada", COLOR_BAD),
            ("En curso", COLOR_CURRENT),
            ("Sin horas", COLOR_EMPTY),
        ]
        painter.setPen(QPen(COLOR_TEXT, 1))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        for j, (text, color) in enumerate(legend):
            x = 8 + j * 130
            painter.setPen(QPen(color, 1))
            painter.setBrush(color)
            painter.drawRoundedRect(x, y, 10, 10, 2, 2)
            painter.setPen(QPen(COLOR_TEXT, 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawText(x + 14, y + 9, text)
        painter.end()