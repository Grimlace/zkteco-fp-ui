"""Background workers: connect, capture fingerprint events, enroll users."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..config import DeviceConfig
from ..device import ZKDevice


class ConnectWorker(QThread):
    """Connects to the device in the background.

    On success emits ``connected(device_name)``; otherwise ``failed(reason)``.
    """

    connected = Signal(str)
    failed = Signal(str)

    def __init__(self, config: DeviceConfig) -> None:
        super().__init__()
        self.config = config
        self.device: ZKDevice | None = None

    def run(self) -> None:
        try:
            device = ZKDevice(self.config)
            device.connect()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        self.device = device
        self.connected.emit(device.device_name)


class CaptureWorker(QThread):
    """Runs ``device.live_capture()`` in a background thread."""

    event = Signal(object)
    error = Signal(str)
    stopped = Signal()

    def __init__(self, device: ZKDevice) -> None:
        super().__init__()
        self._device = device
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        try:
            for ev in self._device.live_capture():
                if ev is not None:
                    self.event.emit(ev)
                if not self._running:
                    break
        except Exception as exc:  # noqa: BLE001 - report to UI
            self.error.emit(str(exc))
        finally:
            try:
                self._device.disconnect()
            except Exception:  # noqa: BLE001 - best effort
                pass
            self.stopped.emit()


class EnrollWorker(QThread):
    """Enrolls a new fingerprint on the device.

    Steps: enroll the finger (device lights up), create the user record on the
    device, then persist the template.
    """

    progress = Signal(str)
    enrolled = Signal(str)  # user_id (badge) that was enrolled
    failed = Signal(str)

    def __init__(self, device: ZKDevice, uid: int, user_id: str, name: str) -> None:
        super().__init__()
        self.device = device
        self.uid = uid
        self.user_id = user_id
        self.name = name

    def run(self) -> None:
        conn = self.device._conn  # type: ignore[union-attr]
        try:
            self.progress.emit("Coloca tu dedo en el sensor...")
            ok = conn.enroll_user(uid=self.uid, temp_id=0, user_id=self.user_id)
            if not ok:
                self.failed.emit("No se pudo registrar la huella (intenta de nuevo).")
                return
            self.progress.emit("Huella registrada, guardando usuario...")
            conn.set_user(
                uid=self.uid,
                name=self.name,
                privilege=0,
                password="",
                group_id="",
                user_id=self.user_id,
                card=0,
            )
            conn.save_user_template(uid=self.uid, temp_id=0, user_id=self.user_id)
            self.enrolled.emit(self.user_id)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))