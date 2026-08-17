"""Export to Excel dialog with a date-range filter."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..excel_export import build_workbook
from .theme import set_button_icon


class ExportDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Exportar a Excel")
        self.setMinimumWidth(420)

        oldest = self.window.db.min_session_date() or date.today()
        today = date.today()

        self.from_date = QDateEdit(calendarPopup=True)
        self.from_date.setDate(oldest)
        self.to_date = QDateEdit(calendarPopup=True)
        self.to_date.setDate(today)

        from_row = QHBoxLayout()
        from_row.addWidget(QLabel("Desde:"))
        from_row.addWidget(self.from_date)
        from_row.addWidget(QLabel("Hasta:"))
        from_row.addWidget(self.to_date)

        self.hint = QLabel(
            "El reporte incluye una hoja de resumen, la matriz general de "
            "semanas y una hoja por usuario con su historial y gráfico.\n"
            "El filtro de fechas acota las sesiones usadas para las hojas "
            "de cada usuario y la matriz general."
        )
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #64748b;")

        export_btn = QPushButton("Exportar")
        set_button_icon(export_btn, "export", 20)
        export_btn.setObjectName("primaryButton")
        export_btn.clicked.connect(self.do_export)
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(export_btn)
        btn_row.addWidget(cancel_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Rango de fechas para el reporte:"))
        layout.addLayout(from_row)
        layout.addWidget(self.hint)
        layout.addLayout(btn_row)

    def do_export(self) -> None:
        start = self.from_date.date().toPython()
        end = self.to_date.date().toPython()
        if start > end:
            QMessageBox.warning(self, "Exportar", "La fecha 'Desde' debe ser anterior a 'Hasta'.")
            return

        default = Path.home() / f"asistencia_{datetime.now():%Y%m%d_%H%M}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar reporte Excel", str(default), "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            wb = build_workbook(self.window.db, start, end)
            wb.save(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Exportar", f"No se pudo exportar: {exc}")
            return
        QMessageBox.information(
            self,
            "Exportar",
            f"Reporte exportado a:\n{path}\n\n"
            f"Usuarios: {len(self.window.db.all_users())} · "
            f"Rango: {start:%d/%m/%Y} – {end:%d/%m/%Y}",
        )
        self.accept()
