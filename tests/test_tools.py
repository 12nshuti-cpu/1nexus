import pytest
from core.tools import ToolRegistry, calculate, unit_convert, get_time
from core.reminders import ReminderService, parse_natural_reminder, parse_due
from core.memory import MemoryService
from core.providers import OllamaProvider, GeminiProvider
from database.database import Database


def test_tool_registry_time():
    reg = ToolRegistry()
    ok, out = reg.execute("get_time")
    assert "Current local time" in out

def test_calculate():
    assert "Result: 4" in calculate("2+2")
    assert "invalid" not in calculate("2+2")
    assert "Provide" in calculate("") or "Could not" in calculate("")
    # safe eval blocks builtins - should be rejected
    out = calculate("__import__('os').system('echo hi')")
    assert "Unsupported" in out or "Could not" in out or "unsupported" in out.lower() or "Expression contains" in out

def test_unit_convert_km_miles():
    out = unit_convert("5 km to miles")
    assert "miles" in out
    out2 = unit_convert("32 f to c")
    assert "°C" in out2 or "C" in out2

def test_tool_shorthand_time():
    reg = ToolRegistry()
    ok, out = reg.execute_command_shorthand("what time is it")
    assert ok
    assert "Current" in out

def test_reminder_parse_natural():
    title, due = parse_natural_reminder("remind me to call mom in 5 minutes")
    assert "call mom" in title
    assert due is not None
    title2, due2 = parse_natural_reminder("test no time")
    assert title2 == "test no time"
    assert due2 is None

def test_reminder_service_create_list(tmp_path=None):
    # Use in-memory DB via temp dir monkeypatch not needed; Database uses LOCALAPPDATA
    # We create a temp DB by overriding env
    import os, tempfile
    from pathlib import Path
    td = tempfile.mkdtemp()
    os.environ["LOCALAPPDATA"] = td
    svc = ReminderService()
    # Need to reinitialize with new env dir
    # Database will pick new path
    rid = svc.create("test reminder", None)
    assert rid > 0
    items = svc.list()
    assert any(i["title"] == "test reminder" for i in items)
    svc.delete(rid)
    assert svc.get(rid) is None

def test_parse_due_iso():
    from datetime import datetime
    dt = parse_due("2025-12-31T23:59:00")
    assert dt and dt.year == 2025
    assert parse_due("not a date") is None

def test_memory_service(tmp_path=None):
    import os, tempfile
    td = tempfile.mkdtemp()
    os.environ["LOCALAPPDATA"] = td
    svc = MemoryService()
    svc.set("user_name", "Alex")
    assert svc.get("user_name") == "Alex"
    fid = svc.remember_fact("I love Python")
    facts = svc.list_facts()
    assert any("I love Python" in f["fact"] for f in facts)
    svc.delete_fact(fid)
    assert not any(f["id"] == fid for f in svc.list_facts())

def test_provider_status():
    from config.settings import NEXUSSettings
    cfg = NEXUSSettings()
    p = OllamaProvider(cfg)
    avail, msg = p.is_available()
    # Should not crash; may be unavailable in CI
    assert isinstance(avail, bool)
    assert isinstance(msg, str)
    g = GeminiProvider(cfg)
    avail2, msg2 = g.is_available()
    assert isinstance(avail2, bool)

def test_system_monitor_cross_platform():
    from core.system_monitor import SystemMonitor
    info = SystemMonitor.get_system_info()
    assert "cpu" in info
    assert "disk" in info
    assert 0 <= info["cpu"] <= 100
    assert 0 <= info["disk"] <= 100

def test_database_conversation():
    import os, tempfile
    td = tempfile.mkdtemp()
    os.environ["LOCALAPPDATA"] = td
    from core.conversation_manager import ConversationManager
    cm = ConversationManager()
    cid = cm.create_conversation("Test")
    assert cid
    cm.add_message(cid, "user", "hello")
    msgs = cm.get_messages(cid)
    assert len(msgs) == 1
    assert msgs[0]["content"] == "hello"
    cm.delete_conversation(cid)
    assert cm.get_conversation(cid) is None
