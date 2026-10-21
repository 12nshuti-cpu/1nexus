"""Export, backup and erase of the user's NEXUS data.

Everything NEXUS stores about the user lives in one SQLite file in the
per-user data folder. This module lets the user take a copy of it (JSON for
reading, a raw database copy for restoring) or erase parts of it.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from config.settings import APP_NAME, APP_VERSION
from core.memory import MemoryStore
from core.reminders import ReminderStore
from database.database import Database

EXPORT_FORMAT = 1


def collect(database: Database | None = None) -> dict:
    """Return all user data as plain JSON-serialisable structures."""
    database = database or Database()
    with database.connect() as connection:
        conversations = []
        for row in connection.execute("SELECT id, title, created_at, updated_at FROM conversations ORDER BY id"):
            messages = connection.execute(
                "SELECT role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id",
                (row["id"],),
            ).fetchall()
            conversations.append({**dict(row), "messages": [dict(m) for m in messages]})
    return {
        "format": EXPORT_FORMAT,
        "app": f"{APP_NAME} {APP_VERSION}",
        "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "conversations": conversations,
        "reminders": ReminderStore(database).export(),
        "memories": MemoryStore(database).export(),
    }


def export_json(path: str | Path, database: Database | None = None) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(collect(database), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def backup_database(path: str | Path, database: Database | None = None) -> Path:
    """Consistent copy of the live database (safe while NEXUS is running)."""
    database = database or Database()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    source = sqlite3.connect(database.db_path)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return target


def delete_conversations(database: Database | None = None) -> int:
    database = database or Database()
    with database.connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        connection.execute("DELETE FROM messages")
        connection.execute("DELETE FROM conversations")
        connection.commit()
    return int(count)
