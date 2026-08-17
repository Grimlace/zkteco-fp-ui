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
from ..report import WeeklyVerifier, format_duration
from ..tracker import TimeTracker
from .settings_dialog import SettingsDialog
from .theme import set_button_icon
from .user_dialog import NewUserDialog
from .views import LiveView, UserDetailView
from .worker import (
    ENROLL_PENDING,
    CaptureWorker,
    ConnectWorker,
    CreateUserWorker,
    DeviceActionWorker,
)


class MainWindow(QMainWindow):
    status_changed = Signal(str)

    def __init__(self, db_path="tracker.db", config: DeviceConfig | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Control de asistencia ZKTeco")
        self.resize(1024, 640)

        self.config = config or DeviceConfig()
        self.tracker = TimeTracker(db_path)
        self.db: Database = self.tracker.db
        self.device: ZKDevice | None = None
        self.worker: CaptureWorker | None = None
        self.connect_worker: ConnectWorker | None = None
        self.new_user_dialog: NewUserDialog | None = None
        self.action_worker: DeviceActionWorker | None = None
        self.capturing = False
        self.connected = False
        self.last_status = "Desconectado"
        self._restart_capture_after_action = False
        self._pending_action: tuple[str, tuple] | None = None
        self._device_action_on_success = None
        self._device_action_on_failed = None
        self._closing = False
        self._workers: set = set()
        self._create_worker = None
        self._weekly_warning_week = None
        self._capture_error_message: str | None = None
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._do_reconnect)

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

        self.export_btn = QPushButton("Exportar a Excel")
        set_button_icon(self.export_btn, "export", 20)
        self.export_btn.setToolTip("Exportar reporte semanal a Excel")
        self.export_btn.clicked.connect(self.open_export)

        self.connection_label = QLabel("Conectando...")
        self.connection_label.setStyleSheet(
            "font-weight: 600; padding: 6px 14px; border-radius: 14px;"
            " background: #e2e8f0; color: #475569;"
        )

        self.retry_btn = QPushButton("Reintentar")
        self.retry_btn.setObjectName("dangerButton")
        set_button_icon(self.retry_btn, "retry", 18)
        self.retry_btn.setToolTip("Volver a intentar la conexión")
        self.retry_btn.hide()
        self.retry_btn.clicked.connect(self.retry_connect)

        self.settings_btn = QToolButton()
        set_button_icon(self.settings_btn, "settings", 22)
        self.settings_btn.setToolTip("Configuración")
        self.settings_btn.setFixedSize(44, 44)
        self.settings_btn.clicked.connect(self.open_settings)

        tl.addWidget(title)
        tl.addStretch(1)
        tl.addWidget(self.new_user_btn)
        tl.addWidget(self.export_btn)
        tl.addWidget(self.connection_label)
        tl.addWidget(self.retry_btn)
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
        self.banner = QLabel("")
        self.banner.setObjectName("noticeBanner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        layout.addWidget(self.banner)
        layout.addWidget(self.stack)
        self.setCentralWidget(central)

        self._banner_timer = QTimer(self)
        self._banner_timer.setSingleShot(True)
        self._banner_timer.timeout.connect(self.banner.hide)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_live)
        self.refresh_timer.start(1000)

    def set_status(self, text: str) -> None:
        self.last_status = text
        self.status_changed.emit(text)

    def _spawn(self, worker: QThread) -> None:
        """Keep a reference to every worker thread so it is never garbage-
        collected while still running. Finished workers are retained (a few
        lightweight QThread objects); they are never deleted, so their C++
        wrappers stay valid for attribute checks like ``isRunning()``."""
        self._workers.add(worker)

    def _show_banner(self, text: str, seconds: int = 10) -> None:
        self.banner.setText(f"⚠ {text}")
        self.banner.show()
        self._banner_timer.start(seconds * 1000)

    # -- navigation -----------------------------------------------------
    def show_live(self) -> None:
        self.stack.setCurrentWidget(self.live_view)
        self.refresh_all()

    def show_user(self, user_id: str) -> None:
        self.detail_view.show_user(user_id)
        self.stack.setCurrentWidget(self.detail_view)

    # -- connection -----------------------------------------------------
    def on_connected(self, name: str) -> None:
        self._reconnect_timer.stop()
        if self.connect_worker is not None and self.connect_worker.device is not None:
            self.device = self.connect_worker.device
        if self.device is None:
            self.on_connect_failed("dispositivo inválido")
            return
        self.connected = True
        self._capture_error_message = None
        self.sync_users_from_device()
        self._sync_device_time_silent()
        self.connection_label.setText(f"Conectado: {name} ({self.config.host})")
        self.connection_label.setStyleSheet(
            "font-weight: 600; padding: 6px 14px; border-radius: 14px;"
            " background: #dcfce7; color: #166534;"
        )
        self.set_status(f"Conexión exitosa: {name}")
        self.retry_btn.hide()
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
        self.retry_btn.show()
        self._schedule_reconnect()

    def disconnect_device(self) -> None:
        self._reconnect_timer.stop()
        if self.capturing:
            self.stop_capture()
        if self.device is not None:
            self.device.disconnect()
        self.device = None
        self.connected = False
        self._capture_error_message = None
        self.retry_btn.hide()
        self.connection_label.setText("Desconectado")
        self.connection_label.setStyleSheet("font-weight: bold;")
        self.set_status("Desconectado")

    # -- auto-reconnect -------------------------------------------------
    def _schedule_reconnect(self) -> None:
        """Queue a reconnection attempt in a few seconds (idempotent)."""
        if self._closing or not self.config.host:
            return
        if self.connected:
            return
        if self.connect_worker is not None and self.connect_worker.isRunning():
            return
        if not self._reconnect_timer.isActive():
            self.set_status("Conexión perdida; reintentando automáticamente...")
            self._reconnect_timer.start(3000)

    def _do_reconnect(self) -> None:
        if self._closing or not self.config.host:
            return
        if self.connected:
            return
        if self.connect_worker is not None and self.connect_worker.isRunning():
            return
        self.auto_connect()

    def auto_connect(self) -> None:
        if not self.config.host:
            self.connection_label.setText("Sin IP configurada (ve a ⚙)")
            self.set_status("Sin IP configurada")
            return
        self.connection_label.setText("Conectando...")
        self.set_status("Conectando...")
        self.retry_btn.hide()
        self.connect_worker = ConnectWorker(self.config)
        self.connect_worker.connected.connect(self.on_connected)
        self.connect_worker.failed.connect(self.on_connect_failed)
        self._spawn(self.connect_worker)
        self.connect_worker.start()

    def retry_connect(self) -> None:
        if self.connect_worker is not None and self.connect_worker.isRunning():
            return
        self._reconnect_timer.stop()
        self.auto_connect()

    def connect_device(self) -> None:
        if self.connected:
            self.disconnect_device()
            return
        self.auto_connect()

    def sync_users_from_device(self) -> None:
        if self.device is None:
            return
        try:
            for u in self.device.users():
                self.tracker.sync_user(str(u.user_id), u.name)
        except Exception as exc:  # noqa: BLE001
            self.set_status(f"No se pudo leer usuarios: {exc}")

    def sync_device_time(self) -> None:
        if not self.connected:
            QMessageBox.warning(self, "Sincronizar hora", "Conecta el dispositivo primero.")
            return

        def action(conn):
            conn.set_time(datetime.now())

        self.run_device_action(
            action,
            on_success=lambda _: QMessageBox.information(
                self, "Sincronizar hora", "Hora del dispositivo actualizada."
            ),
            on_failed=lambda msg: QMessageBox.critical(self, "Sincronizar hora", msg),
        )

    def _sync_device_time_silent(self) -> None:
        if self.device is None or self.device._conn is None:  # type: ignore[union-attr]
            return
        try:
            self.device._conn.set_time(datetime.now())  # type: ignore[union-attr]
            self.set_status("Hora del dispositivo sincronizada")
        except Exception as exc:  # noqa: BLE001
            self.set_status(f"No se pudo sincronizar la hora: {exc}")

    # -- device actions on a separate connection ------------------------
    def _busy_with_device_op(self) -> bool:
        if self._pending_action is not None:
            return True
        if self.action_worker is not None and self.action_worker.isRunning():
            return True
        return self._busy_with_user_op()

    def run_device_action(self, action, on_success=None, on_failed=None) -> bool:
        if not self.connected:
            QMessageBox.warning(self, "Dispositivo", "Conecta el dispositivo primero.")
            return False
        if self._busy_with_device_op():
            QMessageBox.warning(
                self, "Dispositivo", "Espera a que termine la operación en curso."
            )
            return False
        if self.capturing:
            self._restart_capture_after_action = True
            self.stop_capture()
            self._pending_action = ("device", (action, on_success, on_failed))
            self.set_status("Esperando a que la captura se detenga...")
            return True
        self._launch_device_action(action, on_success, on_failed)
        return True

    def _launch_device_action(self, action, on_success, on_failed) -> None:
        self._device_action_on_success = on_success
        self._device_action_on_failed = on_failed
        self.action_worker = DeviceActionWorker(self.config, action)
        self.action_worker.ok.connect(self._on_device_action_ok)
        self.action_worker.failed.connect(self._on_device_action_failed)
        self._spawn(self.action_worker)
        self.action_worker.start()

    def _on_device_action_ok(self, result) -> None:
        cb = self._device_action_on_success
        self._device_action_on_success = None
        self._device_action_on_failed = None
        self.action_worker = None
        self._after_device_action()
        if cb is not None:
            cb(result)

    def _on_device_action_failed(self, message: str) -> None:
        cb = self._device_action_on_failed
        self._device_action_on_success = None
        self._device_action_on_failed = None
        self.action_worker = None
        self._after_device_action()
        if cb is not None:
            cb(message)

    def _after_device_action(self) -> None:
        if self._restart_capture_after_action:
            self._restart_capture_after_action = False
            if not self._closing and self.connected and self.device is not None:
                self.start_capture()

    # -- user creation ---------------------------------------------------
    def _busy_with_user_op(self) -> bool:
        return self._create_worker is not None and self._create_worker.isRunning()

    def create_device_user(self, name: str, user_id: str | None, on_progress, on_created, on_failed) -> CreateUserWorker | str | None:
        """Create the user record on the device (ID + name)."""
        if not self.connected:
            return None
        if self._busy_with_device_op() or self._busy_with_user_op():
            QMessageBox.warning(
                self, "Nuevo usuario", "Espera a que termine la operación en curso."
            )
            return None
        if self.capturing:
            self._restart_capture_after_action = True
            self.stop_capture()
            self._pending_action = ("create", (name, user_id, on_progress, on_created, on_failed))
            self.set_status("Esperando a que la captura se detenga...")
            return ENROLL_PENDING
        return self._launch_create(name, user_id, on_progress, on_created, on_failed)

    def _launch_create(self, name, user_id, on_progress, on_created, on_failed) -> CreateUserWorker:
        worker = CreateUserWorker(self.config, name, user_id)

        def handle_ok(badge: str, uid: int) -> None:
            self._after_device_action()
            on_created(badge, uid)

        def handle_bad(message: str) -> None:
            self._after_device_action()
            on_failed(message)

        worker.progress.connect(on_progress)
        worker.created.connect(handle_ok)
        worker.failed.connect(handle_bad)
        self._create_worker = worker
        self._spawn(worker)
        worker.start()
        return worker

    def _dispatch_pending_action(self) -> None:
        pending = self._pending_action
        self._pending_action = None
        if pending is None:
            return
        kind, data = pending
        self.set_status("Iniciando operación en el dispositivo...")
        if kind == "device":
            action, on_ok, on_fail = data
            self._launch_device_action(action, on_ok, on_fail)
        elif kind == "create":
            name, user_id, on_prog, on_created, on_fail = data
            self._launch_create(name, user_id, on_prog, on_created, on_fail)

    def delete_user_from_app(self, user_id: str) -> None:
        def on_device_delete(_result) -> None:
            self.tracker.db.remove_user(user_id)
            self.refresh_all()
            self.show_live()
            self.set_status(f"Usuario {user_id} eliminado")

        def on_device_delete_failed(message: str) -> None:
            QMessageBox.critical(
                self,
                "Eliminar usuario",
                f"No se pudo eliminar al usuario {user_id} del dispositivo: {message}",
            )

        if not self.connected or self.device is None:
            self.tracker.db.remove_user(user_id)
            self.refresh_all()
            self.show_live()
            self.set_status(f"Usuario {user_id} eliminado")
            return

        def action(conn):
            # ``delete_user_template`` over TCP is broken in pyzk on Python 3
            # (packs a str instead of bytes), so template cleanup is best
            # effort; the user deletion itself is the critical part.
            try:
                for tid in range(10):
                    try:
                        ok = conn.delete_user_template(uid=0, temp_id=tid, user_id=user_id)
                    except Exception:  # noqa: BLE001
                        break
                    if not ok:
                        break
            except Exception:  # noqa: BLE001
                pass
            conn.delete_user(uid=0, user_id=user_id)

        self.run_device_action(action, on_success=on_device_delete, on_failed=on_device_delete_failed)

    # -- capture --------------------------------------------------------
    def start_capture(self) -> None:
        if self._closing:
            return
        if self.device is None or not self.connected:
            QMessageBox.warning(self, "Captura", "Conecta el dispositivo primero.")
            return
        if self.worker is not None:
            return
        self.worker = CaptureWorker(self.device)
        self.worker.event.connect(self.on_event)
        self.worker.error.connect(self.on_capture_error)
        self.worker.stopped.connect(self.on_capture_stopped)
        self._spawn(self.worker)
        self.worker.start()
        self.capturing = True
        self.set_status("Captura iniciada")

    def stop_capture(self) -> None:
        if self.worker is not None:
            self.worker.stop()

    def on_capture_error(self, message: str) -> None:
        self._capture_error_message = message
        self.set_status(f"Error de captura: {message}")
        self._on_device_lost(message)

    def _on_device_lost(self, message: str) -> None:
        """The device connection died (e.g. reboot, cable, power). Mark it as
        disconnected in real time and schedule an automatic reconnection."""
        self.connected = False
        self._pending_action = None
        self._restart_capture_after_action = False
        if self.device is not None:
            try:
                self.device.disconnect()
            except Exception:  # noqa: BLE001 - best effort
                pass
        self.device = None
        self.connection_label.setText("Sin conexión")
        self.connection_label.setStyleSheet(
            "font-weight: 600; padding: 6px 14px; border-radius: 14px;"
            " background: #fee2e2; color: #b91c1c;"
        )
        self.connection_label.setToolTip(message)
        self.retry_btn.show()
        self.set_status(f"Conexión perdida: {message}")
        self._schedule_reconnect()

    def on_capture_stopped(self) -> None:
        self.capturing = False
        self.worker = None
        if self._capture_error_message is not None:
            self._capture_error_message = None
            return
        self.set_status("Captura detenida")
        had_pending = self._pending_action is not None
        self._dispatch_pending_action()
        if not had_pending:
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
        self.new_user_dialog = NewUserDialog(self)
        self.new_user_dialog.exec()

    def open_export(self) -> None:
        from .export_dialog import ExportDialog

        ExportDialog(self).exec()

    # -- weekly ---------------------------------------------------------
    def _check_weekly_on_startup(self) -> None:
        if self._weekly_warning_week is not None:
            return
        week = WeeklyVerifier(self.db).generate_previous_week_if_due(datetime.now())
        if week is None:
            return
        self._weekly_warning_week = week
        # Wait a moment for the auto-connect + device user sync so the banner
        # shows user names (not just badge IDs); the display only runs once
        # per generated week, so it never reappears on every app open.
        QTimer.singleShot(1500, self._maybe_show_weekly_warning)

    def _maybe_show_weekly_warning(self) -> None:
        week = self._weekly_warning_week
        if week is None:
            return
        self._weekly_warning_week = None
        under = WeeklyVerifier(self.db).under_requirement(week)
        if not under:
            return
        names = ", ".join(
            self.db.user_name(r["user_id"]) or str(r["user_id"]) for r in under
        )
        self._show_banner(
            f"No completaron las 30 horas la semana pasada: {names}. "
            "Consulta el historial para más detalle.",
            seconds=10,
        )

    # -- refresh --------------------------------------------------------
    def refresh_all(self) -> None:
        self.refresh_live()

    def refresh_live(self) -> None:
        if self._closing:
            return
        if hasattr(self, "stack") and self.stack.currentWidget() is self.live_view:
            self.live_view.refresh()

    def closeEvent(self, event):  # noqa: N802
        self._closing = True
        self.refresh_timer.stop()
        if self.worker is not None:
            self.worker.stop()
        for worker in tuple(self._workers):
            if worker.isRunning():
                worker.wait(5000)
        self.tracker.close()
        super().closeEvent(event)