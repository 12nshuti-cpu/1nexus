"""Natural-language routing -> validated tools, with honest results."""
from core.assistant import AssistantEngine, build_greeting


def test_time_question_uses_real_clock(engine):
    reply = engine.handle("what time is it?")
    assert reply and reply.startswith("It is ")
    from datetime import datetime
    assert datetime.now().strftime("%Y") in reply


def test_unrelated_text_falls_through_to_ai(engine):
    assert engine.handle("tell me a story about dragons") is None
    assert not engine.can_handle("who won the world cup in 2010")


def test_reminder_is_really_saved_and_listed(engine):
    reply = engine.handle("remind me to call mum in 10 minutes")
    assert "saved" in reply and "call mum" in reply
    assert len(engine.reminders.list()) == 1
    listing = engine.handle("show my reminders")
    assert "call mum" in listing


def test_unparseable_reminder_reports_failure_and_saves_nothing(engine):
    reply = engine.handle("remind me about the thing")
    assert "couldn't save" in reply
    assert engine.reminders.list() == []


def test_alarm_not_pretended(engine):
    assert "only reminders" in engine.handle("set an alarm")
    assert engine.reminders.list() == []


def test_complete_and_delete_reminder(engine):
    engine.handle("remind me to stretch in 5 minutes")
    rid = engine.reminders.list()[0].id
    assert "done" in engine.handle(f"complete reminder {rid}")
    assert "Deleted" in engine.handle(f"delete reminder {rid}")
    assert "no reminder number" in engine.handle(f"delete reminder {rid}")


def test_clear_completed_requires_typed_confirmation(engine):
    engine.handle("remind me to stretch in 5 minutes")
    rid = engine.reminders.list()[0].id
    engine.handle(f"complete reminder {rid}")
    prompt = engine.handle("clear completed reminders")
    assert "confirm" in prompt.lower() and engine.awaiting_confirmation
    assert len(engine.reminders.list(include_done=True)) == 1  # not yet deleted
    assert "Removed 1" in engine.handle("yes")
    assert engine.reminders.list(include_done=True) == []


def test_confirmation_can_be_declined(engine):
    engine.memory.add("likes tea")
    engine.handle("forget everything")
    assert "cancelled" in engine.handle("no").lower()
    assert len(engine.memory.list()) == 1


def test_other_message_abandons_pending_confirmation(engine):
    engine.memory.add("likes tea")
    engine.handle("forget everything")
    engine.handle("what time is it")          # unrelated message
    assert not engine.awaiting_confirmation
    assert engine.handle("yes") is None        # a late "yes" must not delete anything
    assert len(engine.memory.list()) == 1


def test_stale_confirmation_expires(engine, monkeypatch):
    engine.memory.add("likes tea")
    engine.handle("forget everything")
    engine._pending_at -= engine.CONFIRMATION_WINDOW + 1
    assert not engine.awaiting_confirmation
    assert len(engine.memory.list()) == 1


def test_memory_roundtrip(engine):
    assert "I'll remember that" in engine.handle("remember that my sister is Aline")
    assert any("Aline" in m.content for m in engine.memory.list())
    assert "Aline" in engine.handle("what do you remember about me")
    mid = engine.memory.list()[0].id
    assert "Forgot" in engine.handle(f"forget memory {mid}")
    assert engine.memory.list() == []


def test_personalization_off_blocks_saving_and_prompt_context(engine, settings):
    settings.personalization_enabled = False
    reply = engine.handle("remember that I like jazz")
    assert "turned off" in reply.lower()
    assert engine.memory.list() == []
    engine.memory.add("likes tea")
    assert engine.memory_context(online=False) == ""


def test_memory_not_sent_online_unless_allowed(engine, settings):
    engine.memory.add("likes tea")
    assert engine.memory_context(online=False) != ""
    assert engine.memory_context(online=True) == ""   # default: never shared
    settings.share_memory_with_online = True
    assert "likes tea" in engine.memory_context(online=True)


def test_calculator_and_units(engine):
    assert engine.handle("calculate 15% of 80").endswith("= 12")
    assert "= 4" in engine.handle("what is 2+2")
    assert engine.handle("convert 10 km to miles") == "10 km = 6.213712 mi"


def test_calculator_rejects_code(engine):
    assert engine.handle("calculate __import__('os').system('echo hi')") == "That function is not supported."
    assert engine.handle("calculate 1/0") == "Cannot divide by zero."
    assert engine.handle("calc 9**9**9") == "That exponent is too large."


def test_ordinary_what_is_question_is_left_for_ai(engine):
    assert engine.handle("what is the capital of France") is None


def test_diagnostics_makes_no_claims_about_unconfigured_online(engine):
    reply = engine.handle("diagnostics")
    assert "Online AI key | not configured" in reply


def test_greeting_uses_given_clock():
    from datetime import datetime
    text = build_greeting("Ana", datetime(2026, 10, 21, 8, 5))
    assert text == "Good morning, Ana. It's Wednesday, 21 October, 08:05."
    assert build_greeting("", datetime(2026, 1, 2, 19, 30)).startswith("Good evening.")
