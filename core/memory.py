"""User-controlled persistent memory for NEXUS.

Stores:
- user preferences (name, language, theme)
- explicit facts the user asked to remember
- session stats

All data is local SQLite; nothing is uploaded unless an online provider is used
and the user sends a message.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from database.database import Database


class MemoryService:
    def __init__(self, db: Database | None = None):
        self.db = db or Database()
        self._ensure_tables()

    def _ensure_tables(self):
        with self.db.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_memory (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS app_stats (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.commit()

    # --- key/value preferences ---
    def set(self, key: str, value: Any):
        key = str(key).strip()
        if not key:
            raise ValueError("Memory key cannot be empty")
        serialized = json.dumps(value, ensure_ascii=False)
        with self.db.connect() as conn:
            conn.execute("""
                INSERT INTO user_memory (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
            """, (key, serialized))
            conn.commit()

    def get(self, key: str, default=None):
        with self.db.connect() as conn:
            row = conn.execute("SELECT value FROM user_memory WHERE key=?", (str(key),)).fetchone()
            if row is None:
                return default
            try:
                return json.loads(row["value"])
            except Exception:
                return row["value"]

    def delete(self, key: str):
        with self.db.connect() as conn:
            conn.execute("DELETE FROM user_memory WHERE key=?", (str(key),))
            conn.commit()

    def all_preferences(self) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT key, value FROM user_memory ORDER BY key").fetchall()
            out = {}
            for r in rows:
                try:
                    out[r["key"]] = json.loads(r["value"])
                except Exception:
                    out[r["key"]] = r["value"]
            return out

    # --- facts ---
    def remember_fact(self, fact: str) -> int:
        fact = str(fact).strip()
        if not fact:
            raise ValueError("Fact cannot be empty")
        if len(fact) > 2000:
            fact = fact[:2000]
        with self.db.connect() as conn:
            cur = conn.execute("INSERT INTO user_facts (fact) VALUES (?)", (fact,))
            conn.commit()
            return int(cur.lastrowid)

    def list_facts(self, limit: int = 100) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT id, fact, created_at FROM user_facts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def delete_fact(self, fact_id: int):
        with self.db.connect() as conn:
            conn.execute("DELETE FROM user_facts WHERE id=?", (int(fact_id),))
            conn.commit()

    def clear_facts(self):
        with self.db.connect() as conn:
            conn.execute("DELETE FROM user_facts")
            conn.commit()

    def export_data(self) -> dict:
        """Export all user data for backup."""
        return {
            "preferences": self.all_preferences(),
            "facts": self.list_facts(limit=1000),
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    def build_context_snippet(self, max_chars: int = 1500) -> str:
        """Build a short context string for the system prompt."""
        prefs = self.all_preferences()
        facts = self.list_facts(limit=20)
        parts = []
        if prefs.get("user_name"):
            parts.append(f"User's name: {prefs['user_name']}")
        if prefs.get("preferred_language") and prefs["preferred_language"] != "auto":
            parts.append(f"Preferred language: {prefs['preferred_language']}")
        # Include recent facts
        for f in reversed(facts):  # oldest first for context
            frag = f"Remembered: {f['fact']}"
            parts.append(frag)
        snippet = "\n".join(parts)
        if len(snippet) > max_chars:
            snippet = snippet[:max_chars] + "…"
        return snippet
