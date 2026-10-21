"""Reminders, memory, conversations, export: data survives restarts."""
import json
import sqlite3
from datetime import datetime, timedelta

import pytest

from core import data_export
from core.conversation_manager import ConversationManager
from core.memory import MAX_MEMORIES, MemoryStore, MemoryStoreError
from core.reminders import MISSED_GRACE, ReminderError, ReminderScheduler, ReminderStore
from database.database import Database

NOW = datetime(2026, 10, 21, 12, 0, 0)


# ------------------------------------------------------------------ reminders
def test_reminder_survives_restart(tmp_path):
    first = ReminderStore(Database(tmp_path))
    created = first.create("pay rent", NOW + timedelta(hours=1))
    second = ReminderStore(Database(tmp_path))          # "restart": new objects, same file
    assert [r.message for r in second.list()] == ["pay rent"]
    assert second.get(created.id).due_at == NOW + timedelta(hours=1)


def test_reminder_validation(db):
    store = ReminderStore(db)
    with pytest.raises(ReminderError):
        store.create("   ", NOW)
    with pytest.raises(ReminderError):
        store.create("x" * 501, NOW)
    with pytest.raises(ReminderError):
        store.create("ok", "tomorrow")  # not a datetime
    with pytest.raises(ReminderError):
        store.get(999)


def test_reminder_sql_injection_is_inert(db):
    store = ReminderStore(db)
    store.create("x'); DROP TABLE reminders;--", NOW)
    assert len(store.list()) == 1


def test_reschedule_rearms_fired_reminder(db):
    store = ReminderStore(db)
    r = store.create("call", NOW - timedelta(minutes=1))
    store.mark_fired(r.id, NOW)
    assert store.get(r.id).status == "fired"
    updated = store.update(r.id, due_at=NOW + timedelta(hours=2))
    assert updated.status == "pending" and updated.notified_at is None


def test_scheduler_fires_each_reminder_exactly_once(db, qapp):
    store = ReminderStore(db)
    store.create("due now", NOW - timedelta(seconds=5))
    store.create("later", NOW + timedelta(hours=1))
    scheduler = ReminderScheduler(store, interval_seconds=60)
    seen = []
    scheduler.reminder_due.connect(lambda payload, missed: seen.append((payload["message"], missed)))
    assert scheduler.check_now(NOW) == 1
    assert scheduler.check_now(NOW) == 0                 # never double-fires
    assert seen == [("due now", False)]
    assert scheduler.check_now(NOW + timedelta(hours=2)) == 1
    assert seen[-1] == ("later", True)                    # noticed >2 min late -> flagged missed


def test_reminder_missed_while_closed_is_flagged_at_next_launch(db, qapp):
    store = ReminderStore(db)
    store.create("meeting", NOW - MISSED_GRACE - timedelta(minutes=30))
    scheduler = ReminderScheduler(store)
    seen = []
    scheduler.reminder_due.connect(lambda payload, missed: seen.append(missed))
    scheduler.check_now(NOW)
    assert seen == [True]


def test_scheduler_timer_starts_and_stops(db, qapp):
    scheduler = ReminderScheduler(ReminderStore(db), interval_seconds=30)
    scheduler.start()
    assert scheduler.running
    scheduler.stop()
    assert not scheduler.running


def test_scheduler_survives_database_failure(db, qapp, monkeypatch):
    store = ReminderStore(db)
    scheduler = ReminderScheduler(store)
    monkeypatch.setattr(store, "due", lambda now: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
    assert scheduler.check_now(NOW) == 0                 # no exception escapes into the Qt timer


# --------------------------------------------------------------------- memory
def test_memory_survives_restart_and_dedupes(tmp_path):
    MemoryStore(Database(tmp_path)).add("Likes Tea")
    again = MemoryStore(Database(tmp_path))
    again.add("likes tea")                               # same fact, different case
    assert [m.content for m in again.list()] == ["Likes Tea"]


def test_memory_limits_and_editing(db):
    store = MemoryStore(db)
    with pytest.raises(MemoryStoreError):
        store.add("")
    with pytest.raises(MemoryStoreError):
        store.add("y" * 401)
    item = store.add("a")
    assert store.update(item.id, "b").content == "b"
    store.delete(item.id)
    with pytest.raises(MemoryStoreError):
        store.get(item.id)


def test_memory_capacity_enforced(db):
    store = MemoryStore(db)
    with db.connect() as c:
        c.executemany("INSERT INTO memories (content) VALUES (?)", [(f"m{i}",) for i in range(MAX_MEMORIES)])
        c.commit()
    with pytest.raises(MemoryStoreError, match="full"):
        store.add("one too many")


def test_memory_context_only_contains_saved_facts(db):
    store = MemoryStore(db)
    assert store.context_block() == ""
    store.add("my dog is called Rex")
    block = store.context_block()
    assert "my dog is called Rex" in block and "never invent" in block


# ---------------------------------------------------- conversations and export
def test_conversations_persist_and_export(tmp_path):
    db1 = Database(tmp_path)
    cm = ConversationManager()
    cm.database = db1
    cid = cm.create_conversation("Trip")
    cm.add_message(cid, "user", "hello")
    cm.add_message(cid, "assistant", "hi there")
    ReminderStore(db1).create("r", NOW)
    MemoryStore(db1).add("fact")

    cm2 = ConversationManager()
    cm2.database = Database(tmp_path)                    # restart
    assert [m["content"] for m in cm2.get_messages(cid)] == ["hello", "hi there"]

    out = data_export.export_json(tmp_path / "export" / "nexus.json", Database(tmp_path))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["conversations"][0]["messages"][1]["content"] == "hi there"
    assert data["reminders"][0]["message"] == "r" and data["memories"][0]["content"] == "fact"


def test_backup_is_a_valid_standalone_database(tmp_path):
    db1 = Database(tmp_path / "live")
    MemoryStore(db1).add("fact")
    backup = data_export.backup_database(tmp_path / "bk" / "copy.db", db1)
    with sqlite3.connect(backup) as c:
        assert c.execute("SELECT content FROM memories").fetchone()[0] == "fact"


def test_delete_conversations_leaves_reminders_and_memory(tmp_path):
    db1 = Database(tmp_path)
    cm = ConversationManager()
    cm.database = db1
    cid = cm.create_conversation("x")
    cm.add_message(cid, "user", "secret")
    MemoryStore(db1).add("keep me")
    assert data_export.delete_conversations(db1) == 1
    assert cm.get_conversations() == []
    assert len(MemoryStore(db1).list()) == 1


def test_database_never_seeds_from_bundled_copy(tmp_path):
    """A fresh install must start empty (no developer data shipped to users)."""
    fresh = Database(tmp_path / "fresh")
    with fresh.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0


def test_database_connections_are_closed(tmp_path):
    database = Database(tmp_path)
    with database.connect() as connection:
        pass
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")                    # file handle released (matters on Windows)
