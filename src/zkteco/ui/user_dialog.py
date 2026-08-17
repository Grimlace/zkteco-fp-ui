"""Dialog for creating a new user.

The user record (name + ID) is created on the device through ``set_user``.
The fingerprint can *not* be registered remotely on the K30, so after
creating the user the dialog shows detailed instructions for adding the
fingerprint manually on the device itself.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .worker import ENROLL_PENDING, CreateUserWorker


class NewUserDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self.worker: CreateUserWorker | None = None

        self.setWindowTitle("Nuevo usuario")
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Nombre y apellido")
        form.addRow("Nombre:", self.name_edit)
        self.user_id_edit = QLineEdit()
        self.user_id_edit.setPlaceholderText("auto")
        form.addRow("ID de usuario:", self.user_id_edit)
        self._uid_label = QLabel("")
        self._uid_label.setStyleSheet("color: #64748b; font-weight: 600;")
        self._uid_label.setMinimumHeight(20)

        self.user_btn = QPushButton("Crear usuario en el dispositivo")
        self.user_btn.setObjectName("primaryButton")
        self.user_btn.clicked.connect(self.create_user)

        self.status_label = QLabel(
            "El usuario se crea aquí (nombre e ID). Para agregar la huella, "
            "sigue las instrucciones del recuadro de abajo.",
        )
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(40)
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        self.help_label = QLabel(
            self._instructions_text()
        )
        self.help_label.setWordWrap(True)
        self.help_label.setStyleSheet(
            "background: #eff6ff; border: 1px solid #bfdbfe; "
            "border-radius: 10px; padding: 12px; color: #1e3a8a;"
        )

        self.close_btn = QPushButton("Cerrar")
        self.close_btn.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Crear el usuario en el dispositivo"))
        layout.addLayout(form)
        layout.addWidget(self._uid_label)
        layout.addWidget(self.user_btn)
        layout.addWidget(self.status_label)
        layout.addWidget(QLabel("Cómo registrar la huella en el dispositivo:"))
        layout.addWidget(self.help_label)
        layout.addWidget(self.close_btn)

    @staticmethod
    def _instructions_text() -> str:
        return (
            "1. Mantén apretado el botón <b>M/OK</b> del dispositivo hasta que "
            "se abra el menú.\n"
            "2. Busca la opción <b>Usuarios</b> y pulsa <b>OK</b>.\n"
            "3. Pulsa el botón de la <b>flecha hacia abajo</b> y luego <b>OK</b>.\n"
            "4. Ahí está la <b>lista de usuarios</b>. Mueve el cursor con las "
            "flechas de arriba y abajo.\n"
            "5. Colócate sobre el usuario recién creado y pulsar <b>OK</b> "
            "para editarlo.\n"
            "6. Navega hasta <b>Añadir huella</b> y pulsa <b>OK</b>. Coloca el "
            "dedo en el sensor cuando lo pida.\n"
            "7. Cuando termine, ve al <b>OK</b> que aparece en la pantalla y "
            "pulsa el botón <b>OK</b> del dispositivo.\n"
            "8. Para volver a la pantalla principal, pulsa <b>ESC</b> varias "
            "veces hasta que veas la hora."
        )

    # -- create user ----------------------------------------------------
    def create_user(self) -> None:
        if not self.window.connected:
            QMessageBox.warning(self, "Sin conexión", "Conecta el dispositivo primero.")
            return
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Nombre", "Escribe el nombre del usuario.")
            return
        user_id = self.user_id_edit.text().strip() or None
        self.user_btn.setEnabled(False)

        result = self.window.create_device_user(
            name,
            user_id,
            on_progress=self.status_label.setText,
            on_created=self.on_user_created,
            on_failed=lambda msg: (
                self.user_btn.setEnabled(True),
                self.on_failed(msg),
            ),
        )
        if result is None:
            QMessageBox.warning(self, "Sin conexión", "Conecta el dispositivo primero.")
            self.user_btn.setEnabled(True)
        elif result is ENROLL_PENDING:
            self.status_label.setText(
                "Deteniendo la captura en vivo para liberar el dispositivo…"
            )
        else:
            self.worker = result

    def on_user_created(self, badge: str, uid: int) -> None:
        self._uid_label.setText(
            f"Usuario creado · ID {badge} · UID {uid} · "
            f"{self.name_edit.text().strip()}"
        )
        self.user_btn.setText("Usuario creado ✓")
        self.user_btn.setEnabled(False)
        self.window.tracker.db.create_user(badge, self.name_edit.text().strip())
        self.window.refresh_all()
        self.status_label.setText(
            f"Usuario {self.name_edit.text().strip()} creado en el dispositivo. "
            "Ahora sigue el recuadro de abajo para registrar su huella "
            "directamente en el equipo."
        )

    def on_failed(self, message: str) -> None:
        self.status_label.setText(
            f"{message}  Para reintentar, pulsa de nuevo el botón."
        )
        QMessageBox.warning(self, "Dispositivo", message)

    def closeEvent(self, event):  # noqa: N802
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(3000)
        super().closeEvent(event)