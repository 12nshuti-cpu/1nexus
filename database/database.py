import os
import shutil
import sqlite3
import sys
from pathlib import Path


class _ClosingConnection(sqlite3.Connection):
    """``with db.connect() as c:`` commits/rolls back *and closes* the connection.

    The stock sqlite3 context manager leaves the connection open, which leaks
    file handles (and on Windows keeps the database file locked).
    """

    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


class Database:

    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir) if data_dir else self.get_data_directory()

        self.data_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.db_path = self.data_dir / "nexus.db"

        self.seed_database_if_needed()

        self.initialize()

    # ========================================================
    # USER DATA DIRECTORY
    # ========================================================

    @staticmethod
    def get_data_directory():

        override = os.environ.get("NEXUS_DATA_DIR")

        if override:

            return Path(override) / "data"

        local_app_data = os.environ.get("LOCALAPPDATA")

        if local_app_data:

            return Path(local_app_data) / "NEXUS" / "data"

        return Path.home() / ".nexus" / "data"

    # ========================================================
    # BUNDLED DATABASE
    # ========================================================

    @staticmethod
    def get_bundled_database():

        if getattr(
            sys,
            "frozen",
            False,
        ):

            base_path = Path(sys._MEIPASS)

        else:

            base_path = Path(__file__).resolve().parent.parent

        return base_path / "data" / "nexus.db"

    # ========================================================
    # COPY DEVELOPMENT DATABASE
    # ========================================================

    def seed_database_if_needed(self):
        """Intentionally does nothing.

        Earlier builds copied a bundled ``data/nexus.db`` (the developer's own
        conversations) into every new installation. User data must never ship
        inside the application, so a fresh install always starts empty.
        """
        return

    # ========================================================
    # DATABASE CONNECTION
    # ========================================================

    def connect(self):

        connection = sqlite3.connect(
            self.db_path,
            timeout=30,
            check_same_thread=False,
            factory=_ClosingConnection,
        )

        connection.row_factory = sqlite3.Row

        connection.execute("PRAGMA foreign_keys = ON")

        connection.execute("PRAGMA journal_mode = WAL")

        return connection

    # ========================================================
    # INITIALIZE DATABASE
    # ========================================================

    def initialize(self):

        with self.connect() as connection:

            cursor = connection.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL
                        DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL
                        DEFAULT CURRENT_TIMESTAMP
                )
                """)

            columns = {
                row["name"]
                for row in cursor.execute("PRAGMA table_info(conversations)").fetchall()
            }

            if "updated_at" not in columns:

                cursor.execute("""
                    ALTER TABLE conversations
                    ADD COLUMN updated_at TEXT
                    """)

                cursor.execute("""
                    UPDATE conversations
                    SET updated_at = created_at
                    WHERE updated_at IS NULL
                    """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                        DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (conversation_id)
                        REFERENCES conversations(id)
                        ON DELETE CASCADE
                )
                """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_messages_conversation
                ON messages(conversation_id, id)
                """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_conversations_updated
                ON conversations(updated_at DESC)
                """)

            connection.commit()
