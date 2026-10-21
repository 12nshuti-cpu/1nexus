"""Built-in NEXUS tools, registered on a :class:`core.tools.ToolRegistry`.

Every handler returns a *truthful* message about what actually happened, and
raises ``ValueError`` (surfaced as a failed ToolResult) when it cannot do what
was asked. Handlers only touch NEXUS's own data stores; nothing here reaches
the operating system, the network or the user's files.
"""
from __future__ import annotations

from datetime import datetime

from config.settings import APP_NAME, APP_VERSION, NEXUSSettings
from core import safe_math
from core.memory import MemoryStore
from core.reminders import Reminder, ReminderStore
from core.timeparse import describe_due, parse_time
from core.tools import Permission, Tool, ToolParam, ToolRegistry


def _reminder_line(reminder: Reminder, now: datetime) -> str:
    when = describe_due(reminder.due_at, now)
    if reminder.status == "done":
        return f"- #{reminder.id} ✓ {reminder.message} (done)"
    if reminder.status == "fired":
        return f"- #{reminder.id} ⏰ {reminder.message} (was due {when} - say \"complete reminder {reminder.id}\")"
    return f"- #{reminder.id} {reminder.message} - {when}"


def build_default_registry(
    reminders: ReminderStore,
    memory: MemoryStore,
    settings: NEXUSSettings | None = None,
) -> ToolRegistry:
    settings = settings or NEXUSSettings()
    registry = ToolRegistry()

    # ------------------------------------------------------------ time & maths
    def get_datetime() -> str:
        now = datetime.now().astimezone()
        zone = now.tzname() or "local time"
        return f"It is {now.strftime('%A, %d %B %Y')}, {now.strftime('%H:%M')} ({zone})."

    def calculate(expression: str) -> str:
        result = safe_math.calculate(expression)
        shown = safe_math.normalize_expression(expression)
        return f"{shown} = {safe_math.format_number(result)}"

    def convert_units(value: float, from_unit: str, to_unit: str) -> str:
        return safe_math.convert(float(value), from_unit, to_unit).describe()

    registry.register(Tool("get_datetime", "Tell the current local date and time.", get_datetime))
    registry.register(Tool(
        "calculate", "Evaluate an arithmetic expression (no code is executed).", calculate,
        params=(ToolParam("expression", "string", "e.g. 15% of 80, (3+4)*2, sqrt(144)", max_length=200),),
    ))
    registry.register(Tool(
        "convert_units", "Convert between common units (length, mass, volume, speed, time, data, area, temperature).",
        convert_units,
        params=(
            ToolParam("value", "number", "amount to convert"),
            ToolParam("from_unit", "string", "e.g. km, lb, celsius", max_length=40),
            ToolParam("to_unit", "string", "e.g. miles, kg, fahrenheit", max_length=40),
        ),
    ))

    # --------------------------------------------------------------- reminders
    def reminder_create(message: str, when: str) -> str:
        parsed = parse_time(when)
        if parsed is None:
            raise ValueError(
                "I couldn't work out when that should be. Try \"in 10 minutes\", \"at 5pm\" or \"tomorrow at 9am\"."
            )
        reminder = reminders.create(message, parsed.due)
        return f"Reminder #{reminder.id} saved: \"{reminder.message}\" - {describe_due(reminder.due_at)}."

    def reminder_list(include_done: bool = False) -> str:
        items = reminders.list(include_done=include_done)
        if not items:
            return "You have no reminders."
        now = datetime.now()
        return "## Reminders\n\n" + "\n".join(_reminder_line(r, now) for r in items)

    def reminder_complete(id: int) -> str:  # noqa: A002 - mirrors the user-facing wording
        reminder = reminders.complete(id)
        return f"Marked reminder #{reminder.id} (\"{reminder.message}\") as done."

    def reminder_delete(id: int) -> str:  # noqa: A002
        reminder = reminders.delete(id)
        return f"Deleted reminder #{reminder.id} (\"{reminder.message}\")."

    def reminder_update(id: int, message: str = "", when: str = "") -> str:  # noqa: A002
        if not message and not when:
            raise ValueError("Tell me what to change: the text, the time, or both.")
        due = None
        if when:
            parsed = parse_time(when)
            if parsed is None:
                raise ValueError("I couldn't understand the new time.")
            due = parsed.due
        reminder = reminders.update(id, message or None, due)
        return f"Updated reminder #{reminder.id}: \"{reminder.message}\" - {describe_due(reminder.due_at)}."

    def reminder_clear_completed() -> str:
        count = reminders.clear_completed()
        return f"Removed {count} completed reminder{'s' if count != 1 else ''}."

    id_param = ToolParam("id", "integer", "reminder number", minimum=1)
    registry.register(Tool(
        "reminder_create", "Create a reminder that notifies while NEXUS is running.", reminder_create,
        params=(ToolParam("message", "string", "what to be reminded of", max_length=500),
                ToolParam("when", "string", "time expression, e.g. 'in 10 minutes' or 'tomorrow at 9am'", max_length=100)),
        permission=Permission.WRITE,
    ))
    registry.register(Tool(
        "reminder_list", "List reminders.", reminder_list,
        params=(ToolParam("include_done", "boolean", "also show completed reminders", required=False),),
    ))
    registry.register(Tool("reminder_complete", "Mark a reminder as done.", reminder_complete,
                           params=(id_param,), permission=Permission.WRITE))
    registry.register(Tool("reminder_delete", "Delete one reminder.", reminder_delete,
                           params=(id_param,), permission=Permission.WRITE))
    registry.register(Tool(
        "reminder_update", "Change a reminder's text and/or time.", reminder_update,
        params=(id_param,
                ToolParam("message", "string", "new text", required=False, max_length=500),
                ToolParam("when", "string", "new time expression", required=False, max_length=100)),
        permission=Permission.WRITE,
    ))
    registry.register(Tool(
        "reminder_clear_completed", "Delete all completed reminders.", reminder_clear_completed,
        permission=Permission.WRITE, confirm=True,
        confirm_prompt="This will permanently delete every completed reminder. Say **yes** to confirm or **cancel**.",
    ))

    # ------------------------------------------------------------------ memory
    def _personalization_off() -> str | None:
        if not settings.personalization_enabled:
            return "Personalization is turned off in Settings, so I haven't saved or changed any memories."
        return None

    def memory_save(content: str) -> str:
        item = memory.add(content)
        return f"Okay, I'll remember that (memory #{item.id}): {item.content}"

    def memory_list() -> str:
        items = memory.list()
        if not items:
            return "I don't have anything saved. Say \"remember that ...\" and I'll keep it."
        return "## What I remember\n\n" + "\n".join(f"- #{m.id} {m.content}" for m in items)

    def memory_search(query: str) -> str:
        items = memory.search(query)
        if not items:
            return f"I don't have anything saved about \"{query}\"."
        return "\n".join(f"- #{m.id} {m.content}" for m in items)

    def memory_update(id: int, content: str) -> str:  # noqa: A002
        item = memory.update(id, content)
        return f"Updated memory #{item.id}: {item.content}"

    def memory_delete(id: int) -> str:  # noqa: A002
        item = memory.delete(id)
        return f"Forgot memory #{item.id}: {item.content}"

    def memory_clear() -> str:
        count = memory.clear()
        return f"Forgot everything - {count} memor{'ies' if count != 1 else 'y'} deleted."

    mem_id = ToolParam("id", "integer", "memory number", minimum=1)
    registry.register(Tool(
        "memory_save", "Save a fact the user explicitly asked NEXUS to remember.", memory_save,
        params=(ToolParam("content", "string", "the fact", max_length=400),),
        permission=Permission.WRITE, unavailable=_personalization_off,
    ))
    registry.register(Tool("memory_list", "List everything NEXUS remembers.", memory_list))
    registry.register(Tool("memory_search", "Find saved memories.", memory_search,
                           params=(ToolParam("query", "string", "words to look for", max_length=200),)))
    registry.register(Tool("memory_update", "Edit a saved memory.", memory_update,
                           params=(mem_id, ToolParam("content", "string", "new text", max_length=400)),
                           permission=Permission.WRITE, unavailable=_personalization_off))
    registry.register(Tool("memory_delete", "Delete one saved memory.", memory_delete,
                           params=(mem_id,), permission=Permission.WRITE))
    registry.register(Tool(
        "memory_clear", "Delete ALL saved memories.", memory_clear,
        permission=Permission.WRITE, confirm=True,
        confirm_prompt="This will permanently delete everything I remember about you. Say **yes** to confirm or **cancel**.",
    ))

    # -------------------------------------------------------------- diagnostics
    def diagnostics() -> str:
        from core.credentials import backend_description
        from core.gemini_engine import gemini_is_configured

        pending = [r for r in reminders.list() if r.status == "pending"]
        rows = [
            ("App", f"{APP_NAME} {APP_VERSION}"),
            ("AI mode", settings.ai_engine),
            ("Local model", settings.ai_model),
            ("Online AI key", "configured" if gemini_is_configured() else "not configured"),
            ("Credentials stored in", backend_description()),
            ("Voice replies", "on" if settings.voice_enabled else "off"),
            ("Personalization", "on" if settings.personalization_enabled else "off"),
            ("Saved memories", str(len(memory.list()))),
            ("Pending reminders", str(len(pending))),
        ]
        body = "\n".join(f"| {k} | {v} |" for k, v in rows)
        return (
            "## NEXUS diagnostics\n\n| Item | Status |\n|---|---|\n" + body +
            "\n\nThis is a configuration summary and makes no network calls. "
            "Open **System Check** for live connection and microphone tests."
        )

    registry.register(Tool("diagnostics", "Summarise NEXUS configuration and state (no network calls).", diagnostics))
    return registry
