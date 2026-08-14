"""Application views: live user list and per-user detail."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..report import format_duration
from .theme import set_button_icon, style_table
from .widgets import ProgressCell, WeeklyHistoryWidget

LIVE_COLUMNS = ["#", "Nombre", "ID", "Estado", "Esta semana", "Progreso (30h)", "Total"]
DETAIL_COLUMNS = ["Fecha", "Entrada", "Salida", "Duración"]


def _make_table(columns: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.verticalHeader().setVisible(False)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.Stretch)
    header.setMinimumSectionSize(100)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    style_table(table)
    return table


class LiveView(QWidget):
    user_selected = Signal(str)

    def __init__(self, window) -> None:
        super().__init__()
        self.window = window
        self.table = _make_table(LIVE_COLUMNS)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)
        self.table.cellDoubleClicked.connect(self._on_double_click)

    def _on_double_click(self, row: int, _col: int) -> None:
        item = self.table.item(row, 2)
        if item is not None:
            self.user_selected.emit(item.text())

    def refresh(self) -> None:
        rows = self.window.tracker.overview()
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            state = "Activo" if row["active"] else "Inactivo"
            if row["state"] == "in":
                state += " · Trabajando"
            values = [
                str(r + 1),
                row["name"] + ("" if row["active"] else " (inactivo)"),
                row["user_id"],
                state,
                format_duration(row["week_seconds"]),
            ]
            for c, text in enumerate(values):
                item = QTableWidgetItem(text)
                if not row["active"]:
                    item.setForeground(QColor("#9e9e9e"))
                self.table.setItem(r, c, item)
            cell = ProgressCell()
            cell.set_seconds(row["week_seconds"])
            self.table.setCellWidget(r, 5, cell)
            total = QTableWidgetItem(format_duration(row["total_seconds"]))
            if not row["active"]:
                total.setForeground(QColor("#9e9e9e"))
            self.table.setItem(r, 6, total)


class UserDetailView(QWidget):
    back_requested = Signal()

    def __init__(self, window) -> None:
        super().__init__()
        self.window = window
        self.user_id: str | None = None

        self.title = QLabel("")
        self.title.setStyleSheet("font-size: 20px; font-weight: 700;")
        back_btn = QPushButton("Volver")
        set_button_icon(back_btn, "back", 20)
        back_btn.clicked.connect(self.back_requested)

        self.activate_btn = QPushButton("")
        self.activate_btn.clicked.connect(self.toggle_active)
        delete_btn = QPushButton("Eliminar")
        delete_btn.setObjectName("dangerButton")
        set_button_icon(delete_btn, "delete", 20)
        delete_btn.clicked.connect(self.delete_user)

        header = QHBoxLayout()
        header.addWidget(back_btn)
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.activate_btn)
        header.addWidget(delete_btn)

        self.weekly = WeeklyHistoryWidget()

        self.table = _make_table(DETAIL_COLUMNS)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(header)
        layout.addWidget(QLabel("Historial semanal:"))
        layout.addWidget(self.weekly)
        layout.addWidget(QLabel("Sesiones:"))
        layout.addWidget(self.table)

    def show_user(self, user_id: str) -> None:
        from PySide6.QtWidgets import QMessageBox

        self.user_id = user_id
        name = self.window.tracker.db.user_name(user_id) or user_id
        self.title.setText(f"{name}  ·  ID {user_id}")
        active_row = self.window.tracker.db._conn.execute(
            "SELECT active FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        active = bool(active_row and active_row["active"]) if active_row else True
        self.activate_btn.setText("Desactivar" if active else "Activar")
        self.weekly.set_weeks(self.window.tracker.db.user_weekly_history(user_id))
        self.refresh_sessions()

    def refresh_sessions(self) -> None:
        if self.user_id is None:
            return
        rows = self.window.tracker.db.sessions_for(user_id=self.user_id)
        self.table.setRowCount(len(rows))
        for r, s in enumerate(reversed(rows)):
            clock_in = datetime.fromisoformat(s["clock_in_at"])
            out = s["clock_out_at"]
            out_dt = datetime.fromisoformat(out) if out else None
            fecha = f"{clock_in:%Y-%m-%d}"
            self.table.setItem(r, 0, QTableWidgetItem(fecha))
            self.table.setItem(r, 1, QTableWidgetItem(f"{clock_in:%H:%M:%S}"))
            self.table.setItem(r, 2, QTableWidgetItem(f"{out_dt:%H:%M:%S}" if out_dt else "en curso"))
            self.table.setItem(r, 3, QTableWidgetItem(format_duration(s["session_seconds"] or 0)))

    def toggle_active(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        if self.user_id is None:
            return
        row = self.window.tracker.db._conn.execute(
            "SELECT active FROM users WHERE user_id = ?", (self.user_id,)
        ).fetchone()
        active = bool(row["active"]) if row else True
        self.window.tracker.db.set_user_active(self.user_id, not active)
        self.window.refresh_all()
        self.show_user(self.user_id)

    def delete_user(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        if self.user_id is None:
            return
        name = self.window.tracker.db.user_name(self.user_id) or self.user_id
        answer = QMessageBox.question(
            self,
            "Eliminar usuario",
            f"¿Eliminar a {name} y todas sus sesiones? Esta acción no se puede deshacer.",
        )
        if answer == QMessageBox.Yes:
            self.window.tracker.db.remove_user(self.user_id)
            self.window.refresh_all()
            self.back_requested.emit()