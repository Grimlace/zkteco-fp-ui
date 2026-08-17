"""Background workers: connect, capture, create users and generic device actions.

Device write operations run on a *separate* connection so they never interfere
with the live-capture socket; ``DeviceActionWorker`` and ``CreateUserWorker``
try TCP first and then fall back to UDP.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from ..config import DeviceConfig
from ..device import ZKDevice

ENROLL_PENDING = "pending"
"""Sentinel returned when a device operation is queued until the live capture
has fully stopped (single-socket devices)."""


def _with_fallback(
    config: DeviceConfig,
    progress: Callable[[str], None],
    operation: Callable[[Any], None],
) -> None:
    """Run ``operation(conn)`` trying TCP first and then UDP. Raises on failure."""
    transports = ((False, "TCP"), (True, "UDP"))
    last_error: str | None = None
    for force_udp, transport in transports:
        cfg = dataclasses.replace(config, force_udp=force_udp)
        device = ZKDevice(cfg)
        try:
            device.connect()
            progress(f"Conectando al dispositivo ({transport})...")
            operation(device._conn)  # type: ignore[union-attr]
            return
        except Exception as exc:  # noqa: BLE001
            last_error = f"{transport}: {exc}"
        finally:
            try:
                device.disconnect()
            except Exception:  # noqa: BLE001 - best effort
                pass
    raise RuntimeError(last_error or "sin respuesta del dispositivo")


class ConnectWorker(QThread):
    """Connects to the device in the background."""

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


class DeviceActionWorker(QThread):
    """Runs a device operation on its own connection.

    ``action`` receives a fresh pyzk connection (``ZK._conn``) and returns the
    result. ``ok`` emits the result, ``failed`` emits the error message.
    """

    ok = Signal(object)
    failed = Signal(str)

    def __init__(self, config: DeviceConfig, action: Callable[[Any], Any]) -> None:
        super().__init__()
        self.config = config
        self.action = action

    def run(self) -> None:
        try:
            _with_fallback(
                self.config,
                lambda _msg: None,
                lambda conn: self.ok.emit(self.action(conn)),
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class CreateUserWorker(QThread):
    """Create the user record on the device (ID + name).

    Computes the next free UID, writes the user with ``set_user`` and emits
    ``created(user_id, uid)``. The fingerprint is registered manually on the
    device afterwards (see the NewUserDialog instructions).
    """

    progress = Signal(str)
    created = Signal(str, int)
    failed = Signal(str)

    def __init__(
        self, config: DeviceConfig, name: str, user_id: str | None = None
    ) -> None:
        super().__init__()
        self.config = config
        self.name = name
        self.user_id = user_id
        self.uid: int | None = None
        self.badge: str | None = None

    def run(self) -> None:
        def operation(conn: Any) -> None:
            try:
                conn.cancel_capture()
            except Exception:  # noqa: BLE001 - best effort cleanup
                pass
            uids = [u.uid for u in conn.get_users()]
            next_uid = (max(uids) + 1) if uids else 1
            badge = self.user_id or str(next_uid)
            self.uid = next_uid
            self.badge = badge
            self.progress.emit(f"Creando el usuario {self.name} en el dispositivo...")
            conn.set_user(
                uid=next_uid,
                name=self.name,
                privilege=0,
                password="",
                group_id="",
                user_id=badge,
                card=0,
            )
            self.progress.emit(
                f"Usuario {self.name} (ID {badge}, UID {next_uid}) creado en el dispositivo."
            )

        try:
            _with_fallback(self.config, self.progress.emit, operation)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        self.created.emit(self.badge or "", self.uid or 0)