"""User-controlled persistent memory.

Only things the user explicitly asks NEXUS to remember are stored ("remember
that my sister's name is Aline"). Nothing is inferred or harvested from
conversations. Everything can be listed, edited, deleted, exported, or turned
off entirely with the *personalization* setting.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from database.database import Database

MAX_MEMORY_LENGTH = 400
MAX_MEMORIES = 500


class MemoryStoreError(ValueError):
    """Invalid memory input or unknown memory id."""



@dataclass(frozen=True)
class Memory:
    id: int
    content: str
    created_at: str
    updated_at: str

    def as_dict(self) -> dict:
        return asdict(self)


def _row(row) -> Memory:
    return Memory(row["id"], row["content"], row["created_at"], row["updated_at"])


class MemoryStore:
    def __init__(self, database: Database | None = None):
        self.database = database or Database()
        with self.database.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()

    @staticmethod
    def _clean(content: str) -> str:
        value = " ".join(str(content or "").split())
        if not value:
            raise MemoryStoreError("There is nothing to remember.")
        if len(value) > MAX_MEMORY_LENGTH:
            raise MemoryStoreError(f"Memories are limited to {MAX_MEMORY_LENGTH} characters.")
        return value

    def add(self, content: str) -> Memory:
        value = self._clean(content)
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM memories WHERE lower(content) = lower(?)", (value,)
            ).fetchone()
            if existing:  # saving the same fact twice is a no-op
                return _row(existing)
            count = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            if count >= MAX_MEMORIES:
                raise MemoryStoreError(f"Memory is full ({MAX_MEMORIES} items). Delete some first.")
            cursor = connection.execute("INSERT INTO memories (content) VALUES (?)", (value,))
            connection.commit()
            return _row(connection.execute("SELECT * FROM memories WHERE id = ?", (cursor.lastrowid,)).fetchone())

    def list(self) -> list[Memory]:
        with self.database.connect() as connection:
            return [_row(r) for r in connection.execute("SELECT * FROM memories ORDER BY id").fetchall()]

    def get(self, memory_id: int) -> Memory:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM memories WHERE id = ?", (int(memory_id),)).fetchone()
        if row is None:
            raise MemoryStoreError(f"There is no memory number {memory_id}.")
        return _row(row)

    def search(self, query: str) -> list[Memory]:
        needle = " ".join(str(query or "").lower().split())
        if not needle:
            return self.list()
        words = [w for w in needle.split() if len(w) > 2] or [needle]
        results = []
        for memory in self.list():
            haystack = memory.content.lower()
            if needle in haystack or any(word in haystack for word in words):
                results.append(memory)
        return results

    def update(self, memory_id: int, content: str) -> Memory:
        value = self._clean(content)
        self.get(memory_id)
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE memories SET content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (value, int(memory_id)),
            )
            connection.commit()
        return self.get(memory_id)

    def delete(self, memory_id: int) -> Memory:
        existing = self.get(memory_id)
        with self.database.connect() as connection:
            connection.execute("DELETE FROM memories WHERE id = ?", (int(memory_id),))
            connection.commit()
        return existing

    def clear(self) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM memories")
            connection.commit()
            return cursor.rowcount

    def export(self) -> list[dict]:
        return [memory.as_dict() for memory in self.list()]

    def context_block(self, max_chars: int = 1500) -> str:
        """Text for the model's context: only user-approved facts, clearly labelled."""
        items = self.list()
        if not items:
            return ""
        lines: list[str] = []
        used = 0
        for memory in items:
            line = f"- {memory.content}"
            if used + len(line) > max_chars:
                break
            lines.append(line)
            used += len(line) + 1
        return (
            "Facts the user explicitly asked NEXUS to remember (treat as true unless the user "
            "corrects them; never invent additional personal facts):\n" + "\n".join(lines)
        )
