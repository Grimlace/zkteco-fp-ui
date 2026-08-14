"""Modern light theme: application stylesheet, fonts and SVG icons."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QPushButton, QTableWidget, QToolButton

ASSETS_DIR = Path(__file__).parent / "assets"

FONT_FAMILY = "Inter"


def load_icon(name: str) -> QIcon:
    return QIcon(str(ASSETS_DIR / f"{name}.svg"))


def set_button_icon(button: QPushButton | QToolButton, name: str, size: int = 20) -> None:
    button.setIcon(load_icon(name))
    button.setIconSize(QSize(size, size))


def style_table(table: QTableWidget) -> None:
    table.setAlternatingRowColors(True)
    table.verticalHeader().setDefaultSectionSize(54)
    table.setShowGrid(False)


QSS = """
* {
    font-family: 'Inter', 'Segoe UI', 'Ubuntu', sans-serif;
    font-size: 15px;
}

QMainWindow, QDialog {
    background: #f1f5f9;
}

QWidget {
    color: #1e293b;
}

QLabel {
    color: #1e293b;
}

QLabel#titleLabel {
    font-size: 18px;
    font-weight: 700;
}

QToolButton {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 8px;
}
QToolButton:hover {
    background: #e2e8f0;
}
QToolButton:pressed {
    background: #cbd5e1;
}

QPushButton {
    background: #eef2f7;
    border: 1px solid #dbe3ec;
    border-radius: 10px;
    padding: 9px 16px;
    font-weight: 600;
    color: #1e293b;
}
QPushButton:hover {
    background: #e2e8f0;
    border-color: #cbd5e1;
}
QPushButton:pressed {
    background: #cbd5e1;
}
QPushButton:disabled {
    background: #e2e8f0;
    color: #94a3b8;
    border-color: #e2e8f0;
}
QPushButton#primaryButton {
    background: #2563eb;
    border: none;
    color: #ffffff;
}
QPushButton#primaryButton:hover {
    background: #1d4ed8;
}
QPushButton#dangerButton {
    background: #ffffff;
    border: 1px solid #fecaca;
    color: #dc2626;
}
QPushButton#dangerButton:hover {
    background: #fef2f2;
}

QLineEdit, QComboBox, QDateEdit {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 8px 12px;
    selection-background-color: #bfdbfe;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus {
    border: 2px solid #2563eb;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    selection-background-color: #bfdbfe;
    selection-color: #1e3a8a;
}

QTableWidget {
    background: #ffffff;
    alternate-background-color: #f8fafc;
    gridline-color: transparent;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    outline: none;
    selection-background-color: transparent;
    selection-color: #1e3a8a;
}
QTableWidget::item {
    padding: 8px 12px;
    border-bottom: 1px solid #eef2f7;
    color: #1e293b;
}
QTableWidget::item:selected {
    background-color: #dbeafe;
    border-radius: 8px;
}
QHeaderView::section {
    background: #f1f5f9;
    color: #475569;
    font-weight: 700;
    font-size: 13px;
    padding: 12px 12px;
    border: none;
    border-bottom: 2px solid #e2e8f0;
}
QTableCornerButton::section {
    background: #f1f5f9;
    border: none;
}

QProgressBar {
    background: #e2e8f0;
    border: none;
    border-radius: 8px;
    min-height: 12px;
    max-height: 12px;
}

QTabWidget::pane {
    border: none;
    background: #ffffff;
    border-radius: 12px;
}

QMessageBox {
    background: #f1f5f9;
}

QScrollBar:vertical {
    background: #f1f5f9;
    width: 12px;
    border-radius: 6px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 6px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""


def apply_theme(app: QApplication) -> None:
    font = QFont()
    font.setFamily(FONT_FAMILY)
    font.setPointSize(11)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)
    app.setStyleSheet(QSS)