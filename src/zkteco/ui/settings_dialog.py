"""Settings dialog opened from the configuration (gear) button."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from .theme import set_button_icon


class SettingsDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Configuración")
        self.setMinimumWidth(340)

        form = QFormLayout()
        self.host_edit = QLineEdit(window.config.host)
        self.port_edit = QLineEdit(str(window.config.port))
        self.timeout_edit = QLineEdit(str(window.config.timeout))
        form.addRow("IP del dispositivo:", self.host_edit)
        form.addRow("Puerto:", self.port_edit)
        form.addRow("Tiempo de espera (s):", self.timeout_edit)

        self.status_label = QLabel(window.last_status or "Desconectado")
        self.status_label.setWordWrap(True)

        self.connect_btn = QPushButton("Conectar" if not window.connected else "Desconectar")
        set_button_icon(self.connect_btn, "settings", 18)
        self.connect_btn.clicked.connect(self.toggle_connect)

        self.sync_btn = QPushButton("Sincronizar hora del dispositivo")
        self.sync_btn.clicked.connect(self.window.sync_device_time)

        self.capture_btn = QPushButton(
            "Detener captura" if window.capturing else "Iniciar captura"
        )
        self.capture_btn.clicked.connect(self.toggle_capture)

        self.save_btn = QPushButton("Guardar y cerrar")
        self.save_btn.clicked.connect(self.save_and_close)

        row = QHBoxLayout()
        row.addWidget(self.connect_btn)
        row.addWidget(self.sync_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status_label)
        layout.addLayout(row)
        layout.addWidget(self.capture_btn)
        layout.addWidget(self.save_btn)

        window.status_changed.connect(self.status_label.setText)

    def toggle_connect(self) -> None:
        if self.window.connected:
            self.window.disconnect_device()
        else:
            self.apply_fields()
            self.window.connect_device()

    def toggle_capture(self) -> None:
        if self.window.capturing:
            self.window.stop_capture()
        else:
            self.window.start_capture()

    def apply_fields(self) -> None:
        self.window.config.host = self.host_edit.text().strip()
        self.window.config.port = int(self.port_edit.text().strip() or 4370)
        self.window.config.timeout = int(self.timeout_edit.text().strip() or 5)

    def save_and_close(self) -> None:
        self.apply_fields()
        self.accept()