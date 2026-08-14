"""Weekly verification and formatting helpers.

A work week runs Monday -> Sunday (ISO). At the end of each week the program
verifies that every user who logged sessions that week reached the weekly
requirement (default 30 hours) and flags those who did not.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import Optional

WEEKLY_REQUIREMENT_SECONDS = float(30 * 3600)

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def week_start_for(value: datetime | date) -> date:
    """Return the Monday of the week containing ``value``."""
    return value.date() - timedelta(days=value.weekday())


def week_end_for(value: datetime | date) -> date:
    """Return the Sunday of the week containing ``value``."""
    return week_start_for(value) + timedelta(days=6)


def week_label(value: datetime | date) -> str:
    """Spanish label for a week, e.g. ``"Agosto 2026 (del 3 al 9)"``."""
    start = week_start_for(value)
    end = week_end_for(value)
    return f"{MESES_ES[end.month - 1].capitalize()} {end.year} (del {start.day} al {end.day})"


def format_duration(total_seconds: float) -> str:
    total_seconds = int(total_seconds)
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_compact(total_seconds: float) -> str:
    """Return like ``37:12`` (hours:minutes)."""
    total_seconds = int(total_seconds)
    hours, rem = divmod(total_seconds, 3600)
    minutes = rem // 60
    return f"{hours:02d}:{minutes:02d}"


class WeeklyVerifier:
    """Generates and inspects the weekly requirement report."""

    def __init__(self, db, requirement: float = WEEKLY_REQUIREMENT_SECONDS) -> None:
        self.db = db
        self.requirement = requirement

    def generate(self, week_start: date) -> None:
        totals = self.db.week_totals(week_start)
        self.db.save_weekly_report(week_start, totals, self.requirement)

    def generate_previous_week_if_due(self, now: datetime) -> Optional[date]:
        """On the first run of a new week, generate the report for the
        just-finished week. Returns the generated week, or None."""
        current_start = week_start_for(now)
        previous_start = current_start - timedelta(days=7)
        last = self.db.last_report_week()
        if last is not None and last >= current_start:
            return None
        self.generate(previous_start)
        return previous_start

    def under_requirement(self, week_start: date) -> list[sqlite3.Row]:
        return [r for r in self.db.weekly_report(week_start) if not r["met_requirement"]]