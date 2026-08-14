"""Main window: toolbar, stacked views, auto-connect and capture control."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..config import DeviceConfig
from ..db import Database
from ..device import ZKDevice
from ..report import WEEKLY_REQUIREMENT_SECONDS, WeeklyVerifier, format_duration, week_start_for
from ..tracker import TimeTracker
from .settings_dialog import SettingsDialog
from .theme import set_button_icon
from .user_dialog import NewUserDialog
from .views import LiveView, UserDetailView
from .worker import CaptureWorker, ConnectWorker


class MainWindow(QMainWindow):
    status_changed = Signal(str)

    def __init__(self, db_path="tracker.db", config: DeviceConfig | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Control de asistencia ZKTeco")
        self.resize(1000, 640)

        self.config = config or DeviceConfig()
        self.tracker = TimeTracker(db_path)
        self.db: Database = self.tracker.db
        self.device: ZKDevice | None = None
        self.worker: CaptureWorker | None = None
        self.connect_worker: ConnectWorker | None = None
        self.enroll_dialog: NewUserDialog | None = None
        self.capturing = False
        self.connected = False
        self.last_status = "Desconectado"

        self._build_ui()
        self._check_weekly_on_startup()
        self.refresh_all()
        self.auto_connect()

    # -- UI -------------------------------------------------------------
    def _build_ui(self) -> None:
        self.toolbar = QWidget()
        self.toolbar.setObjectName("toolbar")
        tl = QHBoxLayout(self.toolbar)
        tl.setContentsMargins(16, 12, 16, 12)
        tl.setSpacing(12)

        title = QLabel("Control de asistencia")
        title.setObjectName("titleLabel")

        self.new_user_btn = QPushButton("Nuevo usuario")
        self.new_user_btn.setObjectName("primaryButton")
        set_button_icon(self.new_user_btn, "user-add", 20)
        self.new_user_btn.clicked.connect(self.open_new_user)

        self.connection_label = QLabel("Conectando...")
        self.connection_label.setStyleSheet(
            "font-weight: 600; padding: 6px 14px; border-radius: 14px;"
            " background: #e2e8f0; color: #475569;"
        )

        self.settings_btn = QToolButton()
        set_button_icon(self.settings_btn, "settings", 22)
        self.settings_btn.setToolTip("Configuración")
        self.settings_btn.setFixedSize(44, 44)
        self.settings_btn.clicked.connect(self.open_settings)

        tl.addWidget(title)
        tl.addStretch(1)
        tl.addWidget(self.new_user_btn)
        tl.addWidget(self.connection_label)
        tl.addWidget(self.settings_btn)

        self.stack = QStackedWidget()
        self.live_view = LiveView(self)
        self.detail_view = UserDetailView(self)
        self.stack.addWidget(self.live_view)
        self.stack.addWidget(self.detail_view)

        self.live_view.user_selected.connect(self.show_user)
        self.detail_view.back_requested.connect(self.show_live)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.stack)
        self.setCentralWidget(central)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_live)
        self.refresh_timer.start(1000)

    def set_status(self, text: str) -> None:
        self.last_status = text
        self.status_changed.emit(text)

    # -- navigation -----------------------------------------------------
    def show_live(self) -> None:
        self.stack.setCurrentWidget(self.live_view)
        self.refresh_all()

    def show_user(self, user_id: str) -> None:
        self.detail_view.show_user(user_id)
        self.stack.setCurrentWidget(self.detail_view)

    # -- connection -----------------------------------------------------
    def auto_connect(self) -> None:
        if not self.config.host:
            self.connection_label.setText("Sin IP configurada (ve a ⚙)")
            self.set_status("Sin IP configurada")
            return
        self.connection_label.setText("Conectando...")
        self.set_status("Conectando...")
        self.connect_worker = ConnectWorker(self.config)
        self.connect_worker.connected.connect(self.on_connected)
        self.connect_worker.failed.connect(self.on_connect_failed)
        self.connect_worker.start()

    def connect_device(self) -> None:
        if self.connected:
            self.disconnect_device()
            return
        self.auto_connect()

    def on_connected(self, name: str) -> None:
        if self.connect_worker is not None and self.connect_worker.device is not None:
            self.device = self.connect_worker.device
        if self.device is None:
            self.on_connect_failed("dispositivo inválido")
            return
        self.connected = True
        self.sync_users_from_device()
        self.connection_label.setText(f"Conectado: {name} ({self.config.host})")
        self.connection_label.setStyleSheet(
            "font-weight: 600; padding: 6px 14px; border-radius: 14px;"
            " background: #dcfce7; color: #166534;"
        )
        self.set_status(f"Conexión exitosa: {name}")
        self.refresh_all()
        self.start_capture()

    def on_connect_failed(self, reason: str) -> None:
        self.connected = False
        self.device = None
        self.connection_label.setText("Sin conexión")
        self.connection_label.setStyleSheet(
            "font-weight: 600; padding: 6px 14px; border-radius: 14px;"
            " background: #fee2e2; color: #b91c1c;"
        )
        self.set_status(f"No se pudo conectar: {reason}")
        self.connection_label.setToolTip(reason)

    def disconnect_device(self) -> None:
        if self.capturing:
            self.stop_capture()
        if self.device is not None:
            self.device.disconnect()
        self.device = None
        self.connected = False
        self.connection_label.setText("Desconectado")
        self.connection_label.setStyleSheet("font-weight: bold;")
        self.set_status("Desconectado")

    def sync_users_from_device(self) -> None:
        if self.device is None:
            return
        try:
            for u in self.device.users():
                self.tracker.sync_user(str(u.user_id), u.name)
        except Exception as exc:  # noqa: BLE001
            self.set_status(f"No se pudo leer usuarios: {exc}")

    def sync_device_time(self) -> None:
        if self.device is None or not self.connected:
            QMessageBox.warning(self, "Sincronizar hora", "Conecta el dispositivo primero.")
            return
        try:
            self.device._conn.set_time(datetime.now())  # type: ignore[union-attr]
            QMessageBox.information(
                self, "Sincronizar hora", "Hora del dispositivo actualizada."
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Sincronizar hora", str(exc))

    # -- capture --------------------------------------------------------
    def start_capture(self) -> None:
        if self.device is None or not self.connected:
            QMessageBox.warning(self, "Captura", "Conecta el dispositivo primero.")
            return
        if self.worker is not None:
            return
        self.worker = CaptureWorker(self.device)
        self.worker.event.connect(self.on_event)
        self.worker.error.connect(self.on_capture_error)
        self.worker.stopped.connect(self.on_capture_stopped)
        self.worker.start()
        self.capturing = True
        self.set_status("Captura iniciada")

    def stop_capture(self) -> None:
        if self.worker is not None:
            self.worker.stop()

    def on_capture_error(self, message: str) -> None:
        self.set_status(f"Error de captura: {message}")

    def on_capture_stopped(self) -> None:
        self.capturing = False
        self.worker = None
        self.set_status("Captura detenida")
        self._check_weekly_on_startup()
        self.refresh_all()

    def on_event(self, event) -> None:
        if self.device is None:
            return
        user_id, ts = self.device.event_to_record(event)
        result = self.tracker.toggle(user_id, ts)
        self.refresh_live()
        self.set_status(
            f"[{ts:%H:%M:%S}] {user_id} entró" if result.state == "in"
            else f"[{ts:%H:%M:%S}] {user_id} salió "
                 f"(sesión {format_duration(result.session_seconds or 0)})"
        )

    # -- dialogs --------------------------------------------------------
    def open_settings(self) -> None:
        SettingsDialog(self).exec()

    def open_new_user(self) -> None:
        self.enroll_dialog = NewUserDialog(self)
        self.enroll_dialog.exec()

    # -- weekly ---------------------------------------------------------
    def _check_weekly_on_startup(self) -> None:
        verifier = WeeklyVerifier(self.db)
        generated = verifier.generate_previous_week_if_due(datetime.now())
        if generated is None:
            return
        under = verifier.under_requirement(generated)
        if under:
            lines = "\n".join(
                f"  • {self.db.user_name(r['user_id']) or r['user_id']}: "
                f"{format_duration(r['total_seconds'])} (< 30h)"
                for r in under
            )
            QMessageBox.warning(
                self,
                "Semana sin completar",
                f"Los siguientes usuarios no completaron 30 horas en la semana "
                f"{week_start_for(generated)}:\n\n{lines}",
            )

    # -- refresh --------------------------------------------------------
    def refresh_all(self) -> None:
        self.refresh_live()

    def refresh_live(self) -> None:
        if self.stack.currentWidget() is self.live_view:
            self.live_view.refresh()

    def closeEvent(self, event):  # noqa: N802
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(3000)
        if self.connect_worker is not None and self.connect_worker.isRunning():
            self.connect_worker.wait(3000)
        self.tracker.close()
        super().closeEvent(event)