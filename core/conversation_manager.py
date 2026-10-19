from database.database import Database


class ConversationManager:

    def __init__(self):
        self.database = Database()

    def create_conversation(self, title="New Conversation"):
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO conversations (title)
                VALUES (?)
                """,
                (title,),
            )

            connection.commit()

            return cursor.lastrowid

    def get_conversations(self):
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                WHERE EXISTS (
                    SELECT 1
                    FROM messages
                    WHERE messages.conversation_id = conversations.id
                )
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()

            return [dict(row) for row in rows]

    def get_conversation(self, conversation_id):
        if conversation_id is None:
            return None

        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()

            return dict(row) if row else None

    def conversation_exists(self, conversation_id):
        if conversation_id is None:
            return False

        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM conversations
                WHERE id = ?
                LIMIT 1
                """,
                (conversation_id,),
            ).fetchone()

            return row is not None

    def update_title(self, conversation_id, title):
        title = title.strip() or "New Conversation"

        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE conversations
                SET title = ?
                WHERE id = ?
                """,
                (title, conversation_id),
            )

            connection.commit()

    def create_title_from_message(self, message):
        title = " ".join(message.strip().split())

        if not title:
            return "New Conversation"

        if len(title) > 45:
            return title[:45].rstrip() + "..."

        return title

    def add_message(self, conversation_id, role, content):
        if not self.conversation_exists(conversation_id):
            return False

        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO messages (
                    conversation_id,
                    role,
                    content
                )
                VALUES (?, ?, ?)
                """,
                (
                    conversation_id,
                    role,
                    content,
                ),
            )

            connection.execute(
                """
                UPDATE conversations
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (conversation_id,),
            )

            connection.commit()

            return True

    def get_messages(self, conversation_id):
        if conversation_id is None:
            return []

        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    conversation_id,
                    role,
                    content,
                    created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id ASC
                """,
                (conversation_id,),
            ).fetchall()

            return [dict(row) for row in rows]

    def delete_conversation(self, conversation_id):
        if conversation_id is None:
            return

        with self.database.connect() as connection:
            connection.execute(
                """
                DELETE FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            )

            connection.commit()