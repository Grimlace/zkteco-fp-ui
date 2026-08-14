"""Session-based per-user time tracking backed by SQLite.

Every fingerprint event toggles that user's clock:

- user is *out*  -> clock *in*: a new ``sessions`` row is created (open session);
- user is *in*   -> clock *out*: the open session is closed, recording the
  clock-out timestamp and the session's elapsed time.

Cumulative time per user is always the sum of all their closed sessions plus
any currently running session, so time naturally continues from before on
re-entry and survives restarts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .db import Database


@dataclass
class ToggleResult:
    user_id: str
    state: str  # "in" | "out"
    at: datetime
    session_seconds: Optional[float] = None
    total_seconds: float = 0.0


class TimeTracker:
    """Tracks sessions for an arbitrary number of users simultaneously."""

    def __init__(self, db_path: Path | str) -> None:
        self.db = Database(db_path)

    def close(self) -> None:
        self.db.close()

    def sync_user(self, user_id: str, name: str) -> None:
        self.db.upsert_user(user_id, name)

    def toggle(self, user_id: str, at: Optional[datetime] = None) -> ToggleResult:
        """Clock the user in or out depending on their current state."""
        at = at or datetime.now()
        open_row = self.db.open_session(user_id)
        if open_row is not None:
            closed = self.db.clock_out(user_id, at)
            return ToggleResult(
                user_id=user_id,
                state="out",
                at=at,
                session_seconds=closed["session_seconds"] if closed else 0.0,
                total_seconds=self.total_seconds(user_id),
            )
        self.db.clock_in(user_id, at)
        return ToggleResult(
            user_id=user_id,
            state="in",
            at=at,
            total_seconds=self.total_seconds(user_id),
        )

    def total_seconds(self, user_id: str, now: Optional[datetime] = None) -> float:
        """Sum of all closed sessions plus the running session, if any."""
        now = now or datetime.now()
        row = self.db.open_session(user_id)
        running = 0.0
        if row is not None:
            running = max((now - datetime.fromisoformat(row["clock_in_at"])).total_seconds(), 0.0)
        return self._sum_sessions(user_id) + running

    def _sum_sessions(self, user_id: str) -> float:
        return self.db.session_sum(user_id)

    def seed_attendance(self, user_id: str, stamps: list[datetime]) -> int:
        """Insert past in/out pairs as sessions. Returns number of sessions added."""
        stamps = sorted(stamps)
        added = 0
        for i in range(1, len(stamps), 2):
            clock_in, clock_out = stamps[i - 1], stamps[i]
            if clock_out > clock_in:
                self.db.add_session(user_id, clock_in, clock_out)
                added += 1
        return added

    def overview(self, now: Optional[datetime] = None) -> list[dict]:
        return self.db.live_overview(now or datetime.now())

    def sessions(self, user_id: Optional[str] = None, day=None) -> list:
        return self.db.sessions_for(user_id=user_id, day=day)