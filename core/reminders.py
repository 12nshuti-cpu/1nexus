"""Persistent reminder / scheduler service for NEXUS.

- Stores reminders in SQLite (via Database)
- Provides due-checking and notification callback
- Background scheduler thread runs while NEXUS is alive
- Limitations are documented: reminders require NEXUS running; OS sleep will delay

Schema:
  reminders(id, title, description, due_at, created_at, completed, notified)

due_at is ISO8601 UTC or local time string; we store as text and parse flexibly.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional

from database.database import Database


@dataclass
class Reminder:
    id: int
    title: str
    description: str
    due_at: str
    created_at: str
    completed: bool
    notified: bool

    @property
    def due_datetime(self) -> Optional[datetime]:
        return parse_due(self.due_at)


def parse_due(value: str) -> Optional[datetime]:
    """Parse a due_at string in various common formats."""
    if not value:
        return None
    value = str(value).strip()
    # Try ISO8601
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    # Try ISO with timezone stripped
    try:
        # Remove trailing Z
        v = value.rstrip("Z")
        # Python 3.11 fromisoformat handles microseconds
        return datetime.fromisoformat(v)
    except Exception:
        pass
    return None


def format_due(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def parse_natural_reminder(text: str) -> tuple[str, Optional[datetime]]:
    """Extract title and optional due time from natural language like:
       'remind me to call mom in 10 minutes' or 'remind me tomorrow at 9am to ...'
    Returns (title, due_datetime|None)
    """
    original = str(text or "").strip()
    lower = original.lower()

    # Pattern: in X minutes/hours/days
    m = re.search(r"in\s+(\d+)\s*(minute|minutes|min|hour|hours|hr|hrs|day|days)\b", lower)
    if m:
        qty = int(m.group(1))
        unit = m.group(2)
        if unit.startswith("min"):
            due = datetime.now() + timedelta(minutes=qty)
        elif unit.startswith("hour") or unit.startswith("hr"):
            due = datetime.now() + timedelta(hours=qty)
        else:
            due = datetime.now() + timedelta(days=qty)
        # Extract title: after "to" or after reminder phrase
        title = _extract_title(original)
        return title, due

    # Pattern: tomorrow at HH(:MM) am/pm
    m = re.search(r"tomorrow\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", lower)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2) or 0)
        ap = (m.group(3) or "").lower()
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        due = (datetime.now() + timedelta(days=1)).replace(hour=h, minute=mi, second=0, microsecond=0)
        title = _extract_title(original)
        return title, due

    # Pattern: at HH:MM today/tomorrow
    m = re.search(r"at\s+(\d{1,2}):(\d{2})\s*(am|pm)?", lower)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2))
        ap = (m.group(3) or "").lower()
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        due = datetime.now().replace(hour=h, minute=mi, second=0, microsecond=0)
        # If time already passed, assume tomorrow
        if due <= datetime.now():
            due += timedelta(days=1)
        title = _extract_title(original)
        return title, due

    return _extract_title(original), None


def _extract_title(text: str) -> str:
    t = str(text or "").strip()
    # Remove leading "remind me to", "reminder", etc.
    t = re.sub(r"(?i)^\s*(please\s+)?(remind\s+me\s+to|reminder\s*:?|remind\s+me\s*:?)\s*", "", t).strip()
    # Remove trailing time clauses we already parsed
    t = re.sub(r"(?i)\s+in\s+\d+\s*(minutes?|hours?|days?|mins?|hrs?)\s*$", "", t).strip()
    t = re.sub(r"(?i)\s+tomorrow\s+at\s+.*$", "", t).strip()
    t = re.sub(r"(?i)\s+at\s+\d{1,2}:\d{2}.*$", "", t).strip()
    return t or "Untitled reminder"


class ReminderService:
    def __init__(self, db: Database | None = None, on_due: Callable[[Reminder], None] | None = None):
        self.db = db or Database()
        self.on_due = on_due
        self._ensure_tables()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._poll_interval = 30  # seconds

    def _ensure_tables(self):
        with self.db.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    due_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed INTEGER NOT NULL DEFAULT 0,
                    notified INTEGER NOT NULL DEFAULT 0
                )
            """)
            # Migrate if needed
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(reminders)").fetchall()}
            if "description" not in cols:
                conn.execute("ALTER TABLE reminders ADD COLUMN description TEXT NOT NULL DEFAULT ''")
            if "notified" not in cols:
                conn.execute("ALTER TABLE reminders ADD COLUMN notified INTEGER NOT NULL DEFAULT 0")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_at)")
            conn.commit()

    # CRUD
    def create(self, title: str, due_at: str | datetime | None = None, description: str = "") -> int:
        title = str(title or "").strip() or "Untitled reminder"
        if len(title) > 300:
            title = title[:300]
        description = str(description or "")
        if isinstance(due_at, datetime):
            due_str = format_due(due_at)
        elif due_at:
            # Try to parse; if fails, store as-is
            dt = parse_due(str(due_at))
            due_str = format_due(dt) if dt else str(due_at).strip()
        else:
            due_str = None  # no due date

        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO reminders (title, description, due_at) VALUES (?, ?, ?)",
                (title, description, due_str),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list(self, include_completed: bool = False, limit: int = 100) -> list[dict]:
        q = "SELECT id, title, description, due_at, created_at, completed, notified FROM reminders"
        if not include_completed:
            q += " WHERE completed=0"
        q += " ORDER BY CASE WHEN due_at IS NULL THEN 1 ELSE 0 END, due_at ASC, id DESC LIMIT ?"
        with self.db.connect() as conn:
            rows = conn.execute(q, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get(self, rid: int) -> Optional[dict]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT id, title, description, due_at, created_at, completed, notified FROM reminders WHERE id=?", (int(rid),)).fetchone()
            return dict(row) if row else None

    def complete(self, rid: int):
        with self.db.connect() as conn:
            conn.execute("UPDATE reminders SET completed=1 WHERE id=?", (int(rid),))
            conn.commit()

    def uncomplete(self, rid: int):
        with self.db.connect() as conn:
            conn.execute("UPDATE reminders SET completed=0 WHERE id=?", (int(rid),))
            conn.commit()

    def delete(self, rid: int):
        with self.db.connect() as conn:
            conn.execute("DELETE FROM reminders WHERE id=?", (int(rid),))
            conn.commit()

    def update(self, rid: int, title: str | None = None, due_at: str | datetime | None = None, description: str | None = None):
        fields = []
        params = []
        if title is not None:
            fields.append("title=?")
            params.append(str(title).strip() or "Untitled reminder")
        if description is not None:
            fields.append("description=?")
            params.append(str(description))
        if due_at is not None:
            if isinstance(due_at, datetime):
                due_str = format_due(due_at)
            else:
                dt = parse_due(str(due_at))
                due_str = format_due(dt) if dt else str(due_at).strip()
            fields.append("due_at=?")
            params.append(due_str)
        if not fields:
            return
        params.append(int(rid))
        with self.db.connect() as conn:
            conn.execute(f"UPDATE reminders SET {', '.join(fields)} WHERE id=?", params)
            conn.commit()

    def due_now(self) -> list[dict]:
        now_str = format_due(datetime.now())
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, title, description, due_at, created_at, completed, notified FROM reminders "
                "WHERE completed=0 AND notified=0 AND due_at IS NOT NULL AND due_at <= ? ORDER BY due_at ASC",
                (now_str,),
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_notified(self, rid: int):
        with self.db.connect() as conn:
            conn.execute("UPDATE reminders SET notified=1 WHERE id=?", (int(rid),))
            conn.commit()

    # Scheduler
    def start_scheduler(self, interval: int = 30):
        self._poll_interval = max(10, int(interval))
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._scheduler_loop, name="NEXUS-Reminders", daemon=True)
        self._thread.start()

    def stop_scheduler(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=1.5)

    def _scheduler_loop(self):
        while not self._stop_event.is_set():
            try:
                for row in self.due_now():
                    rid = row["id"]
                    # Avoid double notify
                    self.mark_notified(rid)
                    if callable(self.on_due):
                        try:
                            # Convert to Reminder dataclass
                            rem = Reminder(
                                id=row["id"],
                                title=row["title"],
                                description=row["description"],
                                due_at=row["due_at"] or "",
                                created_at=row["created_at"],
                                completed=bool(row["completed"]),
                                notified=bool(row["notified"]),
                            )
                            self.on_due(rem)
                        except Exception:
                            pass
            except Exception:
                pass
            self._stop_event.wait(self._poll_interval)

    def check_now(self):
        """For tests: run one due-check synchronously."""
        notified = []
        for row in self.due_now():
            self.mark_notified(row["id"])
            notified.append(row)
            if callable(self.on_due):
                try:
                    rem = Reminder(
                        id=row["id"], title=row["title"], description=row["description"],
                        due_at=row["due_at"] or "", created_at=row["created_at"],
                        completed=bool(row["completed"]), notified=False
                    )
                    self.on_due(rem)
                except Exception:
                    pass
        return notified
