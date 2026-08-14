"""Device connection configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class DeviceConfig:
    """Connection settings for a ZKTeco device.

    Values are read from environment variables when not passed explicitly:

    - ``ZKTEco_HOST`` / ``ZK_HOST``: device IP or hostname (required)
    - ``ZKTEco_PORT`` / ``ZK_PORT``: UDP/TCP port (default 4370)
    - ``ZKTEco_TIMEOUT`` / ``ZK_TIMEOUT``: connection timeout in seconds (default 5)
    - ``ZKTEco_PASSWORD``: device comm password (default 0)
    """

    host: str = field(
        default_factory=lambda: os.getenv("ZKTEco_HOST", os.getenv("ZK_HOST", "192.168.20.201"))
    )
    port: int = field(
        default_factory=lambda: int(os.getenv("ZKTEco_PORT", os.getenv("ZK_PORT", "4370")))
    )
    timeout: int = field(
        default_factory=lambda: int(
            os.getenv("ZKTEco_TIMEOUT", os.getenv("ZK_TIMEOUT", "5"))
        )
    )
    password: int = field(
        default_factory=lambda: int(
            os.getenv("ZKTEco_PASSWORD", os.getenv("ZK_PASSWORD", "0"))
        )
    )

    def validate(self) -> None:
        if not self.host:
            raise ValueError(
                "device host is not configured; set ZK_HOST (or ZKTEco_HOST) or pass host=..."
            )