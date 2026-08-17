"""SQLite storage for sessions, users and weekly reports."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from .report import week_start_for

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id    TEXT PRIMARY KEY,
    name       TEXT,
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL,
    clock_in_at     TEXT NOT NULL,
    clock_out_at    TEXT,
    session_seconds REAL,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_clock_in ON sessions(clock_in_at);

CREATE TABLE IF NOT EXISTS weekly_reports (
    week_start      TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    total_seconds   REAL NOT NULL,
    met_requirement INTEGER NOT NULL,
    generated_at    TEXT NOT NULL,
    PRIMARY KEY (week_start, user_id)
);
"""

USER_COLUMNS = ("user_id", "name", "active", "created_at")


def iso(dt: datetime) -> str:
    return dt.isoformat()


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


class Database:
    """Thin wrapper around an SQLite database holding all tracker data.

    Datetimes are stored as ISO strings. All access is single-threaded
    (the capture worker only emits events; toggles run on the caller thread).
    """

    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(users)")}
        if "active" not in cols:
            self._conn.execute("ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
        if "created_at" not in cols:
            self._conn.execute("ALTER TABLE users ADD COLUMN created_at TEXT")

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- users ----------------------------------------------------------
    def upsert_user(self, user_id: str, name: str, active: Optional[bool] = None) -> None:
        """Insert a user, or update its name if it already exists.

        ``active`` is only applied on insert so deactivation is never
        accidentally undone by a device sync.
        """
        existing = self._conn.execute(
            "SELECT active FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if existing is None:
            self._conn.execute(
                "INSERT INTO users(user_id, name, active, created_at) VALUES(?, ?, ?, ?)",
                (user_id, name, 1 if active is not False else 1, iso(datetime.now())),
            )
        else:
            self._conn.execute(
                "UPDATE users SET name = ? WHERE user_id = ?", (name, user_id)
            )
        self._conn.commit()

    def create_user(self, user_id: str, name: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO users(user_id, name, active, created_at) "
            "VALUES(?, ?, 1, ?)",
            (user_id, name, iso(datetime.now())),
        )
        self._conn.commit()

    def ensure_user(self, user_id: str) -> None:
        """Insert the user if missing, without touching its existing name/active."""
        if self._conn.execute(
            "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
        ).fetchone() is None:
            self._conn.execute(
                "INSERT INTO users(user_id, name, active, created_at) VALUES(?, ?, 1, ?)",
                (user_id, user_id, iso(datetime.now())),
            )
            self._conn.commit()

    def user_name(self, user_id: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT name FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["name"] if row else None

    def all_users(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM users ORDER BY active DESC, name COLLATE NOCASE ASC"
        ).fetchall()

    def set_user_active(self, user_id: str, active: bool) -> None:
        self._conn.execute(
            "UPDATE users SET active = ? WHERE user_id = ?", (1 if active else 0, user_id)
        )
        self._conn.commit()

    def remove_user(self, user_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            self._conn.execute("DELETE FROM weekly_reports WHERE user_id = ?", (user_id,))
            self._conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

    # -- sessions -------------------------------------------------------
    def open_session(self, user_id: str) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM sessions WHERE user_id = ? AND clock_out_at IS NULL "
            "ORDER BY clock_in_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()

    def clock_in(self, user_id: str, when: datetime) -> int:
        self.ensure_user(user_id)
        cur = self._conn.execute(
            "INSERT INTO sessions(user_id, clock_in_at) VALUES(?, ?)",
            (user_id, iso(when)),
        )
        self._conn.commit()
        return cur.lastrowid

    def clock_out(self, user_id: str, when: datetime) -> Optional[sqlite3.Row]:
        row = self.open_session(user_id)
        if row is None:
            return None
        seconds = max((when - parse_iso(row["clock_in_at"])).total_seconds(), 0.0)
        self._conn.execute(
            "UPDATE sessions SET clock_out_at = ?, session_seconds = ? WHERE id = ?",
            (iso(when), seconds, row["id"]),
        )
        self._conn.commit()
        return self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (row["id"],)
        ).fetchone()

    def add_session(
        self, user_id: str, clock_in_at: datetime, clock_out_at: datetime
    ) -> None:
        seconds = max((clock_out_at - clock_in_at).total_seconds(), 0.0)
        self._conn.execute(
            "INSERT INTO sessions(user_id, clock_in_at, clock_out_at, session_seconds) "
            "VALUES(?, ?, ?, ?)",
            (user_id, iso(clock_in_at), iso(clock_out_at), seconds),
        )
        self._conn.commit()

    def sessions_for(
        self, user_id: Optional[str] = None, day: Optional[date] = None
    ) -> list[sqlite3.Row]:
        where, params = [], []
        if user_id:
            where.append("user_id = ?")
            params.append(user_id)
        if day:
            where.append("date(clock_in_at) = date(?)")
            params.append(iso(datetime(day.year, day.month, day.day)))
        query = "SELECT * FROM sessions"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY clock_in_at ASC"
        return self._conn.execute(query, params).fetchall()

    def sessions_in_range(
        self, start: date, end: date
    ) -> list[sqlite3.Row]:
        """Sessions whose clock-in falls in ``[start, end]`` inclusive."""
        return self._conn.execute(
            "SELECT * FROM sessions WHERE date(clock_in_at) >= date(?) "
            "AND date(clock_in_at) <= date(?) ORDER BY clock_in_at ASC",
            (start.isoformat(), end.isoformat()),
        ).fetchall()

    def min_session_date(self) -> Optional[date]:
        row = self._conn.execute(
            "SELECT MIN(clock_in_at) m FROM sessions"
        ).fetchone()
        if row and row["m"]:
            return parse_iso(row["m"]).date()
        return None

    def all_open_sessions(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM sessions WHERE clock_out_at IS NULL ORDER BY clock_in_at ASC"
        ).fetchall()

    def session_sum(self, user_id: str) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(session_seconds), 0) total FROM sessions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return float(row["total"])

    def live_overview(self, now: datetime) -> list[dict]:
        """Per-user live overview including users with zero hours.

        Rows: ``user_id, name, active, state, clock_in_at, today_seconds,
        week_seconds, total_seconds``.
        """
        today_iso = date(now.year, now.month, now.day).isoformat()
        week_iso = week_start_for(now).isoformat()
        rows = []
        for u in self.all_users():
            user_id = u["user_id"]
            open_row = self.open_session(user_id)
            running = 0.0
            if open_row is not None:
                running = max(
                    (now - parse_iso(open_row["clock_in_at"])).total_seconds(), 0.0
                )
            tod = self._conn.execute(
                "SELECT COALESCE(SUM(session_seconds), 0) total FROM sessions "
                "WHERE user_id = ? AND date(clock_in_at) = date(?)",
                (user_id, today_iso),
            ).fetchone()["total"]
            week = self._conn.execute(
                "SELECT COALESCE(SUM(session_seconds), 0) total FROM sessions "
                "WHERE user_id = ? AND date(clock_in_at) >= date(?)",
                (user_id, week_iso),
            ).fetchone()["total"]
            rows.append(
                {
                    "user_id": user_id,
                    "name": u["name"] or user_id,
                    "active": bool(u["active"]),
                    "state": "in" if open_row is not None else "out",
                    "clock_in_at": parse_iso(open_row["clock_in_at"]) if open_row else None,
                    "today_seconds": tod + running,
                    "week_seconds": week + running,
                    "total_seconds": self.session_sum(user_id) + running,
                }
            )
        rows.sort(key=lambda r: (not r["active"], -r["week_seconds"]))
        return rows

    # -- weekly ---------------------------------------------------------
    def week_totals(self, week_start: date) -> dict[str, float]:
        start_iso = week_start.isoformat()
        end_iso = (week_start + timedelta(days=7)).isoformat()
        query = (
            "SELECT user_id, COALESCE(SUM(session_seconds), 0) total FROM sessions "
            "WHERE clock_in_at >= ? AND clock_in_at < ? GROUP BY user_id"
        )
        return {r["user_id"]: r["total"] for r in self._conn.execute(query, (start_iso, end_iso))}

    def user_weekly_history(self, user_id: str) -> list[dict]:
        """Weekly totals per user from their first session until now."""
        stamps: dict[date, float] = {}
        for s in self.sessions_for(user_id=user_id):
            wk = week_start_for(parse_iso(s["clock_in_at"]))
            stamps[wk] = stamps.get(wk, 0.0) + float(s["session_seconds"] or 0.0)
        open_row = self.open_session(user_id)
        if open_row is not None:
            wk = week_start_for(datetime.now())
            running = max(
                (datetime.now() - parse_iso(open_row["clock_in_at"])).total_seconds(), 0.0
            )
            stamps[wk] = stamps.get(wk, 0.0) + running
        current = week_start_for(datetime.now())
        weeks = sorted(set(stamps) | {current})
        if not weeks:
            return []
        first, last = weeks[0], weeks[-1]
        step = timedelta(days=7)
        out = []
        wk = first
        while wk <= last:
            total = stamps.get(wk, 0.0)
            out.append(
                {
                    "week_start": wk,
                    "total_seconds": total,
                    "met": total >= self.weekly_requirement,
                    "current": wk == current,
                }
            )
            wk += step
        return out

    @property
    def weekly_requirement(self) -> float:
        from .report import WEEKLY_REQUIREMENT_SECONDS

        return WEEKLY_REQUIREMENT_SECONDS

    def save_weekly_report(self, week_start: date, totals: dict[str, float], threshold: float) -> None:
        generated = datetime.now().isoformat()
        with self._conn:
            self._conn.execute("DELETE FROM weekly_reports WHERE week_start = ?", (week_start.isoformat(),))
            for user_id, total in totals.items():
                self._conn.execute(
                    "INSERT INTO weekly_reports(week_start, user_id, total_seconds, "
                    "met_requirement, generated_at) VALUES(?, ?, ?, ?, ?)",
                    (week_start.isoformat(), user_id, total, 1 if total >= threshold else 0, generated),
                )

    def weekly_report(self, week_start: date) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM weekly_reports WHERE week_start = ? ORDER BY total_seconds DESC",
            (week_start.isoformat(),),
        ).fetchall()

    def last_report_week(self) -> Optional[date]:
        row = self._conn.execute(
            "SELECT MAX(week_start) week_start FROM weekly_reports"
        ).fetchone()
        if row and row["week_start"]:
            return date.fromisoformat(row["week_start"])
        return None