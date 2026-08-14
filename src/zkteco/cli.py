"""Interfaz de línea de comandos: conecta al dispositivo y registra tiempo.

Uso:
    zkteco [--host HOST] [--port PORT] [--seed-from-attendance] [--sync-time]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from .config import DeviceConfig
from .db import Database
from .device import ZKDevice
from .report import WeeklyVerifier, format_duration, week_label, week_start_for
from .tracker import TimeTracker

DEFAULT_DB = Path("tracker.db")


def seed_from_attendance(device: ZKDevice, tracker: TimeTracker) -> int:
    """Carga sesiones pasadas desde la asistencia guardada en el dispositivo."""
    by_user: dict[str, list[datetime]] = {}
    for rec in device.attendance():
        user_id, ts = device.event_to_record(rec)
        by_user.setdefault(user_id, []).append(ts)
    total = 0
    for user_id, stamps in by_user.items():
        total += tracker.seed_attendance(user_id, stamps)
    return total


def sync_user_names(device: ZKDevice, tracker: TimeTracker) -> None:
    for u in device._conn.get_users():  # type: ignore[union-attr]
        tracker.sync_user(str(u.user_id), u.name)


def print_report(tracker: TimeTracker) -> None:
    print("\n=== Reporte de tiempo (sesiones, guardado en DB) ===")
    for row in tracker.overview():
        marker = " (en curso)" if row["state"] == "in" else ""
        print(f"{row['user_id']:<12} {format_duration(row['total_seconds'])}{marker}")
    print("==================================================")


def print_weekly(tracker: TimeTracker, db: Database) -> None:
    verifier = WeeklyVerifier(db)
    generated = verifier.generate_previous_week_if_due(datetime.now())
    week = week_start_for(datetime.now())
    verifier.generate(week)
    print(f"\n=== Reporte semanal (meta 30h) - {week_label(week)} ===")
    for row in db.weekly_report(week):
        status = "OK" if row["met_requirement"] else "POR DEBAJO de 30h"
        print(f"{row['user_id']:<12} {format_duration(row['total_seconds']):>12}  {status}")
    if generated:
        print(f"(reporte de la semana terminada {week_label(generated)} generado automáticamente)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zkteco", description=__doc__)
    parser.add_argument("--host", help="IP/host del dispositivo (o variable ZK_HOST)")
    parser.add_argument("--port", type=int, help="puerto del dispositivo (por defecto 4370)")
    parser.add_argument("--timeout", type=int, help="tiempo de espera de conexión (segundos)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="ruta de la base SQLite")
    parser.add_argument(
        "--seed-from-attendance",
        action="store_true",
        help="cargar sesiones pasadas desde la asistencia del dispositivo",
    )
    parser.add_argument(
        "--sync-time",
        action="store_true",
        help="ajustar el reloj del dispositivo a la hora de esta computadora",
    )
    parser.add_argument("--no-capture", action="store_true", help="conectar, mostrar reporte y salir")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    config = DeviceConfig()
    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port
    if args.timeout:
        config.timeout = args.timeout

    tracker = TimeTracker(args.db)

    try:
        with ZKDevice(config) as device:
            print(f"Conectado a {device.device_name}")
            for key, value in device.info().items():
                print(f"  {key}: {value}")

            if args.sync_time:
                device._conn.set_time(datetime.now())  # type: ignore[union-attr]
                print("Hora del dispositivo sincronizada.")

            sync_user_names(device, tracker)

            if args.seed_from_attendance:
                count = seed_from_attendance(device, tracker)
                print(f"Se cargaron {count} sesiones pasadas desde la asistencia.")

            if args.no_capture:
                print_report(tracker)
                print_weekly(tracker, tracker.db)
                return 0

            try:
                for event in device.live_capture():
                    if event is None:
                        continue
                    user_id, ts = device.event_to_record(event)
                    result = tracker.toggle(user_id, ts)
                    total = result.total_seconds
                    print(
                        f"[{ts:%H:%M:%S}] usuario {user_id}: "
                        f"{'entró' if result.state == 'in' else 'salió'} "
                        f"(sesión {format_duration(result.session_seconds or 0)} "
                        f"| total {format_duration(total)})"
                    )
            except KeyboardInterrupt:
                print("\nDeteniendo captura.")
    except Exception as exc:  # noqa: BLE001 - mostrar el error al usuario
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print_report(tracker)
    print_weekly(tracker, tracker.db)
    print(f"Datos guardados en {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
