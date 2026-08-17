"""Connection wrapper around pyzk's ``ZK`` client."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterator, Optional

from zk import ZK

from .config import DeviceConfig

logger = logging.getLogger(__name__)


class ZKDevice:
    """Context manager managing a connection to a ZKTeco device."""

    def __init__(self, config: DeviceConfig) -> None:
        config.validate()
        self.config = config
        self._zk = ZK(
            config.host,
            port=config.port,
            timeout=config.timeout,
            password=config.password,
            force_udp=config.force_udp,
        )
        self._conn = None

    def __enter__(self) -> "ZKDevice":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.disconnect()

    def connect(self) -> None:
        """Open the connection to the device."""
        logger.info("connecting to %s:%s ...", self.config.host, self.config.port)
        self._conn = self._zk.connect()
        logger.info("connected to %s", self.device_name)

    def disconnect(self) -> None:
        if self._conn is not None:
            try:
                self._conn.disconnect()
            except Exception:  # noqa: BLE001 - best effort on shutdown
                logger.exception("error while disconnecting")
            finally:
                self._conn = None

    @property
    def connected(self) -> bool:
        return self._conn is not None

    @property
    def device_name(self) -> str:
        if self._conn is None:
            return "<not connected>"
        return self._conn.get_device_name()

    def info(self) -> dict[str, Optional[str]]:
        """Return basic device information as a dict of name -> value."""
        if self._conn is None:
            raise RuntimeError("not connected")
        return {
            "name": self.device_name,
            "serial": self._conn.get_serialnumber(),
            "platform": self._conn.get_platform(),
            "firmware": self._conn.get_firmware_version(),
            "fingerprint_ver": self._conn.get_fp_version(),
            "mac": self._conn.get_mac(),
            "device_time": str(self._conn.get_time()),
        }

    def users(self) -> list:
        """Return the device's enrolled users (each has ``uid``, ``name``, ``user_id``)."""
        if self._conn is None:
            raise RuntimeError("not connected")
        return self._conn.get_users()

    def attendance(self) -> Iterator[object]:
        """Yield stored attendance records (each has ``user_id`` and ``timestamp``)."""
        if self._conn is None:
            raise RuntimeError("not connected")
        yield from self._conn.get_attendance()

    def live_capture(self) -> Iterator[Optional[object]]:
        """Yield live fingerprint events; ``None`` on receive timeouts.

        Each yielded event has ``user_id`` (str) and ``timestamp`` (datetime).
        """
        if self._conn is None:
            raise RuntimeError("not connected")
        logger.info("waiting for fingerprint events (Ctrl+C to stop and show report)")
        yield from self._conn.live_capture()

    def event_to_record(self, event: object) -> tuple[str, datetime]:
        """Extract ``(user_id, timestamp)`` from an attendance/event object."""
        return str(event.user_id), event.timestamp