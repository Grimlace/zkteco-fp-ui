"""Dialog for creating a new user in two steps:

1. Create the user on the device (name + ID) -> ``set_user``.
2. Register the fingerprint by activating the device scanner -> ``enroll_user``.
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

from .worker import ENROLL_PENDING, EnrollWorker, CreateUserWorker


class NewUserDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self.worker: EnrollWorker | CreateUserWorker | None = None
        self.user_uid: int | None = None
        self.badge: str | None = None

        self.setWindowTitle("Nuevo usuario")
        self.setMinimumWidth(380)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        step1 = QLabel("Paso 1 · Crear el usuario en el dispositivo")
        step1.setStyleSheet("font-weight: 700; color: #2563eb;")
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

        step2 = QLabel("Paso 2 · Registrar la huella")
        step2.setStyleSheet("font-weight: 700; color: #2563eb;")
        self.enroll_btn = QPushButton("Registrar huella en el dispositivo")
        self.enroll_btn.setEnabled(False)
        self.enroll_btn.clicked.connect(self.start_enroll)

        self.status_label = QLabel(
            "Paso 1: crea el usuario (nombre e ID) en el dispositivo. "
            "Paso 2: activa el lector para registrar su huella."
        )
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(40)
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        self.close_btn = QPushButton("Cerrar")
        self.close_btn.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(step1)
        layout.addLayout(form)
        layout.addWidget(self._uid_label)
        layout.addWidget(self.user_btn)
        layout.addWidget(step2)
        layout.addWidget(self.enroll_btn)
        layout.addWidget(self.status_label)
        layout.addWidget(self.close_btn)

    # -- step 1 -------------------------------------------------------
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
        self.user_uid = uid
        self.badge = badge
        self._uid_label.setText(f"Usuario creado · ID {badge} · UID {uid}")
        self.enroll_btn.setEnabled(True)
        self.user_btn.setText("Usuario creado ✓")
        self.user_btn.setEnabled(False)
        self.window.tracker.db.create_user(badge, self.name_edit.text().strip())
        self.window.refresh_all()
        self.status_label.setText(
            f"Usuario {self.name_edit.text().strip()} creado. "
            "Pulsa \"Registrar huella\" y coloca el dedo en el sensor."
        )

    # -- step 2 -------------------------------------------------------
    def start_enroll(self) -> None:
        if not self.window.connected:
            QMessageBox.warning(self, "Sin conexión", "Conecta el dispositivo primero.")
            return
        if self.user_uid is None or self.badge is None:
            return
        self.enroll_btn.setEnabled(False)

        result = self.window.enroll_fingerprint(
            self.user_uid,
            self.badge,
            on_progress=self.status_label.setText,
            on_enrolled=self.on_enrolled,
            on_failed=lambda msg: (
                self.enroll_btn.setEnabled(True),
                self.on_failed(msg),
            ),
        )
        if result is None:
            QMessageBox.warning(self, "Sin conexión", "Conecta el dispositivo primero.")
            self.enroll_btn.setEnabled(True)
        elif result is ENROLL_PENDING:
            self.status_label.setText(
                "Deteniendo la captura en vivo para liberar el dispositivo…"
            )
        else:
            self.worker = result

    def on_enrolled(self, badge: str, uid: int) -> None:
        self.enroll_btn.setText("Huella registrada ✓")
        self.enroll_btn.setEnabled(False)
        self.status_label.setText(
            f"Huella registrada para el usuario {badge}. "
            "Puedes cerrar la ventana."
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