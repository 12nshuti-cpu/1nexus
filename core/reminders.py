"""Persistent reminders for NEXUS.

* :class:`ReminderStore` – SQLite persistence (lives in the user's NEXUS database,
  never inside the installation folder, so upgrades keep reminders).
* :class:`ReminderScheduler` – a Qt timer that fires reminders while NEXUS is
  running (including minimised / hidden in the tray).

Lifecycle:  ``pending`` -> ``fired`` (notified) -> ``done`` (completed by user).

Limitation (by design, documented in the user guide): reminders can only
notify while NEXUS is running. A reminder that came due while NEXUS was closed
is delivered at the next launch and flagged as *missed*.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Optional

from database.database import Database

MAX_MESSAGE_LENGTH = 500
MISSED_GRACE = timedelta(minutes=2)
_ISO = "%Y-%m-%d %H:%M:%S"


class ReminderError(ValueError):
    """Invalid reminder input or an unknown reminder id."""


@dataclass(frozen=True)
class Reminder:
    id: int
    message: str
    due_at: datetime
    status: str  # pending | fired | done
    created_at: str
    notified_at: Optional[str] = None

    def as_dict(self) -> dict:
        data = asdict(self)
        data["due_at"] = self.due_at.strftime(_ISO)
        return data


def _row_to_reminder(row) -> Reminder:
    return Reminder(
        id=row["id"],
        message=row["message"],
        due_at=datetime.strptime(row["due_at"], _ISO),
        status=row["status"],
        created_at=row["created_at"],
        notified_at=row["notified_at"],
    )


class ReminderStore:
    def __init__(self, database: Database | None = None):
        self.database = database or Database()
        self._initialize()

    def _initialize(self) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'fired', 'done')),
                    notified_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(status, due_at)"
            )
            connection.commit()

    # ------------------------------------------------------------------

    @staticmethod
    def _clean_message(message: str) -> str:
        value = " ".join(str(message or "").split())
        if not value:
            raise ReminderError("A reminder needs some text.")
        if len(value) > MAX_MESSAGE_LENGTH:
            raise ReminderError(f"Reminders are limited to {MAX_MESSAGE_LENGTH} characters.")
        return value

    def create(self, message: str, due_at: datetime) -> Reminder:
        text = self._clean_message(message)
        if not isinstance(due_at, datetime):
            raise ReminderError("A valid date and time is required.")
        with self.database.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO reminders (message, due_at) VALUES (?, ?)",
                (text, due_at.strftime(_ISO)),
            )
            connection.commit()
            return self._get(connection, cursor.lastrowid)

    @staticmethod
    def _get(connection, reminder_id: int) -> Reminder:
        row = connection.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        if row is None:
            raise ReminderError(f"There is no reminder number {reminder_id}.")
        return _row_to_reminder(row)

    def get(self, reminder_id: int) -> Reminder:
        with self.database.connect() as connection:
            return self._get(connection, int(reminder_id))

    def list(self, include_done: bool = False) -> list[Reminder]:
        query = "SELECT * FROM reminders"
        if not include_done:
            query += " WHERE status != 'done'"
        query += " ORDER BY due_at ASC, id ASC"
        with self.database.connect() as connection:
            return [_row_to_reminder(row) for row in connection.execute(query).fetchall()]

    def complete(self, reminder_id: int) -> Reminder:
        with self.database.connect() as connection:
            self._get(connection, int(reminder_id))
            connection.execute("UPDATE reminders SET status = 'done' WHERE id = ?", (int(reminder_id),))
            connection.commit()
            return self._get(connection, int(reminder_id))

    def delete(self, reminder_id: int) -> Reminder:
        with self.database.connect() as connection:
            existing = self._get(connection, int(reminder_id))
            connection.execute("DELETE FROM reminders WHERE id = ?", (int(reminder_id),))
            connection.commit()
            return existing

    def update(self, reminder_id: int, message: str | None = None, due_at: datetime | None = None) -> Reminder:
        with self.database.connect() as connection:
            existing = self._get(connection, int(reminder_id))
            new_message = self._clean_message(message) if message is not None else existing.message
            new_due = due_at if due_at is not None else existing.due_at
            # Rescheduling re-arms a reminder that already fired.
            status = "pending" if (due_at is not None and existing.status != "done") else existing.status
            connection.execute(
                "UPDATE reminders SET message = ?, due_at = ?, status = ?, notified_at = "
                "CASE WHEN ? = 'pending' THEN NULL ELSE notified_at END WHERE id = ?",
                (new_message, new_due.strftime(_ISO), status, status, int(reminder_id)),
            )
            connection.commit()
            return self._get(connection, int(reminder_id))

    def clear_completed(self) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM reminders WHERE status = 'done'")
            connection.commit()
            return cursor.rowcount

    def due(self, now: datetime | None = None) -> list[Reminder]:
        now = now or datetime.now()
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM reminders WHERE status = 'pending' AND due_at <= ? ORDER BY due_at, id",
                (now.strftime(_ISO),),
            ).fetchall()
        return [_row_to_reminder(row) for row in rows]

    def mark_fired(self, reminder_id: int, now: datetime | None = None) -> None:
        stamp = (now or datetime.now()).strftime(_ISO)
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE reminders SET status = 'fired', notified_at = ? WHERE id = ? AND status = 'pending'",
                (stamp, int(reminder_id)),
            )
            connection.commit()

    def export(self) -> list[dict]:
        return [reminder.as_dict() for reminder in self.list(include_done=True)]


# ----------------------------------------------------------------------
# Scheduler (Qt)
# ----------------------------------------------------------------------

try:  # Qt is only needed for the live scheduler, not for the store.
    from PySide6.QtCore import QObject, QTimer, Signal
except Exception:  # pragma: no cover - exercised only without PySide6
    QObject = object  # type: ignore[assignment,misc]
    QTimer = None  # type: ignore[assignment]
    Signal = None  # type: ignore[assignment]


if QTimer is not None:

    class ReminderScheduler(QObject):
        """Checks for due reminders on a timer and emits :attr:`reminder_due`.

        ``reminder_due(reminder_dict, missed)`` – ``missed`` is True when the
        reminder came due more than two minutes before it was noticed (for
        example because NEXUS was closed or the PC was asleep).
        """

        reminder_due = Signal(dict, bool)

        def __init__(self, store: ReminderStore, interval_seconds: int = 10, parent=None):
            super().__init__(parent)
            self.store = store
            self._timer = QTimer(self)
            self._timer.setInterval(max(1, int(interval_seconds)) * 1000)
            self._timer.timeout.connect(self.check_now)

        def start(self) -> None:
            self.check_now()  # deliver anything that came due while closed
            self._timer.start()

        def stop(self) -> None:
            self._timer.stop()

        @property
        def running(self) -> bool:
            return self._timer.isActive()

        def check_now(self, now: datetime | None = None) -> int:
            """Fire every due reminder exactly once. Returns how many fired."""
            now = now or datetime.now()
            fired = 0
            try:
                due = self.store.due(now)
            except Exception:  # noqa: BLE001 - never let a DB hiccup kill the timer
                return 0
            for reminder in due:
                missed = (now - reminder.due_at) > MISSED_GRACE
                try:
                    self.store.mark_fired(reminder.id, now)  # mark first => never double-fires
                except Exception:  # noqa: BLE001
                    continue
                self.reminder_due.emit(reminder.as_dict(), missed)
                fired += 1
            return fired
