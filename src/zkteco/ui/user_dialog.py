"""Dialog for creating a new user (name + fingerprint enrollment on device)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .worker import EnrollWorker


class NewUserDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self.worker: EnrollWorker | None = None
        self.enrolled_user_id: str | None = None
        self.enrolled_uid: int | None = None

        self.setWindowTitle("Nuevo usuario")
        self.setMinimumWidth(360)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        form.addRow("Nombre:", self.name_edit)
        self.user_id_edit = QLineEdit()
        self.user_id_edit.setPlaceholderText("auto")
        form.addRow("ID de usuario:", self.user_id_edit)

        self.enroll_btn = QPushButton("Registrar huella en el dispositivo")
        self.enroll_btn.clicked.connect(self.start_enroll)
        self.save_btn = QPushButton("Guardar usuario")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save_user)

        self.status_label = QLabel(
            "Conecta el dispositivo y pulsa \"Registrar huella\" para que el "
            "usuario ponga el dedo en el sensor."
        )
        self.status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.enroll_btn)
        layout.addWidget(self.status_label)
        layout.addWidget(self.save_btn)

        self._uid_label = QLabel("")
        form.addRow(self._uid_label)

    def start_enroll(self) -> None:
        if self.window.device is None or not self.window.connected:
            QMessageBox.warning(self, "Sin conexión", "Conecta el dispositivo primero.")
            return
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Nombre", "Escribe el nombre del usuario.")
            return
        conn = self.window.device._conn  # type: ignore[union-attr]
        uids = [u.uid for u in conn.get_users()]
        next_uid = (max(uids) + 1) if uids else 1
        user_id = self.user_id_edit.text().strip() or str(next_uid)
        self._uid_label.setText(f"UID en dispositivo: {next_uid} · ID: {user_id}")

        self.worker = EnrollWorker(self.window.device, next_uid, user_id, name)
        self.worker.progress.connect(self.status_label.setText)
        self.worker.failed.connect(lambda msg: (self.status_label.setText(msg),
                                                QMessageBox.warning(self, "Registro", msg)))
        self.worker.enrolled.connect(self.on_enrolled)
        self.enroll_btn.setEnabled(False)
        self.worker.start()

    def on_enrolled(self, user_id: str) -> None:
        self.enrolled_user_id = user_id
        self.enrolled_uid = self.worker.uid
        self.save_btn.setEnabled(True)
        self.status_label.setText("Huella registrada. Pulsa \"Guardar usuario\" para continuar.")

    def save_user(self) -> None:
        if self.enrolled_user_id is None:
            return
        self.window.tracker.db.create_user(
            self.enrolled_user_id, self.name_edit.text().strip()
        )
        self.window.refresh_all()
        self.accept()

    def closeEvent(self, event):  # noqa: N802
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(3000)
        super().closeEvent(event)