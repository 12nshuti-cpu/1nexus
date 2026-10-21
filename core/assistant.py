"""NEXUS assistant layer: natural language -> validated tool calls.

This is the bridge between what the user types or says ("remind me to call mum
in 10 minutes") and the tool registry in :mod:`core.builtin_tools`.

Design rules
------------
* Routing is **deterministic** (anchored patterns). A language model never gets
  to invent that a reminder was saved - only the registry's real result is shown.
* Every call goes through :meth:`core.tools.ToolRegistry.execute`, so arguments
  are validated, consequential actions need a typed confirmation, and failures
  are reported as failures.
* Anything that does not clearly match is left alone (``handle`` returns
  ``None``) and flows on to the normal AI path.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from config.settings import NEXUSSettings
from core import safe_math
from core.builtin_tools import build_default_registry
from core.logger import get_logger
from core.memory import MemoryStore
from core.reminders import ReminderStore
from core.tools import ToolRegistry, ToolResult
from database.database import Database

log = get_logger("assistant")

_YES = {"yes", "y", "yep", "yeah", "confirm", "confirmed", "do it", "go ahead", "ok", "okay", "sure"}
_NO = {"no", "n", "nope", "cancel", "stop", "never mind", "nevermind", "abort", "don't", "dont"}


@dataclass
class Intent:
    tool: str
    arguments: dict = field(default_factory=dict)
    # soft intents fall through to the AI instead of reporting an error when
    # the tool rejects them (e.g. "what is the capital of France").
    soft: bool = False


def _norm(text: str) -> str:
    return " ".join(str(text or "").strip().rstrip("?!. ").split())


_REMIND_ANYWHERE = re.compile(
    r"\bremind\s+me\b|\b(?:set|create|add|make)\s+(?:me\s+)?(?:a\s+|an\s+)?(?:reminder|alarm|timer)\b",
    re.IGNORECASE,
)

_RE_TIME = re.compile(
    r"^(?:what(?:'s|\s+is)?\s+(?:the\s+)?(?:current\s+)?(?:time|date|day)(?:\s+is\s+it)?(?:\s+(?:now|today|right now))?"
    r"|what\s+time\s+is\s+it(?:\s+now|\s+right now)?"
    r"|(?:what(?:'s|\s+is)\s+)?today'?s\s+date"
    r"|what\s+day\s+is\s+(?:it|today)"
    r"|tell\s+me\s+the\s+(?:time|date)"
    r"|current\s+(?:time|date)|date\s+and\s+time|date|today)$",
    re.IGNORECASE,
)
_RE_REM_LIST = re.compile(
    r"^(?:(?:show|list|see|view|display|check|get)\s+(?:me\s+)?(?:all\s+)?(?:of\s+)?(?:my\s+)?(?P<all>all\s+|completed\s+|done\s+)?reminders?"
    r"|what(?:'s|\s+are|\s+is)?\s+(?:my\s+)?(?:upcoming\s+)?reminders?"
    r"|(?:do\s+i\s+have|have\s+i\s+got)\s+(?:any\s+)?reminders?"
    r"|(?:my\s+)?reminders?)$",
    re.IGNORECASE,
)
_RE_REM_COMPLETE = re.compile(
    r"^(?:(?:complete|finish|done\s+with|tick\s+off)\s+reminder\s*#?(?P<a>\d+)"
    r"|mark\s+reminder\s*#?(?P<b>\d+)\s+(?:as\s+)?(?:done|complete|completed|finished))$",
    re.IGNORECASE,
)
_RE_REM_DELETE = re.compile(r"^(?:delete|remove|cancel)\s+reminder\s*#?(?P<id>\d+)$", re.IGNORECASE)
_RE_REM_UPDATE = re.compile(
    r"^(?:change|reschedule|move|update|snooze)\s+reminder\s*#?(?P<id>\d+)\s+(?:to|for|until)\s+(?P<when>.+)$",
    re.IGNORECASE,
)
_RE_REM_CLEAR = re.compile(
    r"^(?:clear|delete|remove)\s+(?:all\s+)?(?:completed|done|finished)\s+reminders?$", re.IGNORECASE
)
_RE_MEM_SAVE = re.compile(r"^(?:please\s+)?remember\s+(?:that\s+)?(?P<c>(?!when\b).+)$", re.IGNORECASE)
_RE_MEM_LIST = re.compile(
    r"^(?:what\s+do\s+you\s+(?:remember|know)(?:\s+about\s+me)?"
    r"|(?:show|list|view|display)\s+(?:me\s+)?(?:all\s+)?(?:my\s+)?(?:saved\s+)?memor(?:y|ies)"
    r"|what\s+have\s+i\s+asked\s+you\s+to\s+remember)$",
    re.IGNORECASE,
)
_RE_MEM_SEARCH = re.compile(r"^what\s+do\s+you\s+remember\s+about\s+(?P<q>.+)$", re.IGNORECASE)
_RE_MEM_FORGET_ALL = re.compile(
    r"^forget\s+(?:everything|all(?:\s+(?:of\s+)?(?:my\s+)?memories)?|all\s+about\s+me)$", re.IGNORECASE
)
_RE_MEM_FORGET = re.compile(r"^forget\s+(?:memory\s*)?#?(?P<id>\d+)$", re.IGNORECASE)
_RE_MEM_UPDATE = re.compile(
    r"^(?:change|update|edit)\s+memory\s*#?(?P<id>\d+)\s+(?:to|:)\s*(?P<c>.+)$", re.IGNORECASE
)
_RE_CALC = re.compile(
    r"^(?P<lead>calculate|calc|compute|evaluate|what(?:'s|\s+is)|how\s+much\s+is|whats)\s+(?P<expr>.+)$",
    re.IGNORECASE,
)
_RE_CONVERT = re.compile(
    r"^(?P<lead>convert\s+)?(?P<v>-?\d[\d,]*(?:\.\d+)?)\s*(?P<f>[a-zA-Z°/²³ ]+?)\s+(?:to|into|in)\s+(?P<t>[a-zA-Z°/²³ ]+)$",
    re.IGNORECASE,
)
_RE_DIAG = re.compile(r"^(?:run\s+)?(?:nexus\s+)?(?:app\s+)?diagnostics?$|^diagnose\s+nexus$", re.IGNORECASE)
_RE_MATHY = re.compile(r"^[\d\s+\-*/^().,%×÷xX]+$|\bsqrt\b|\d\s*%|\bpercent\b|\bof\b.*\d|\d.*\bof\b", re.IGNORECASE)


class AssistantEngine:
    """Owns the stores and the tool registry; routes text to tools."""

    def __init__(
        self,
        database: Database | None = None,
        settings: NEXUSSettings | None = None,
        registry: ToolRegistry | None = None,
    ):
        self.database = database or Database()
        self.settings = settings or NEXUSSettings()
        self.reminders = ReminderStore(self.database)
        self.memory = MemoryStore(self.database)
        self.registry = registry or build_default_registry(self.reminders, self.memory, self.settings)
        self._pending: Optional[Intent] = None
        self._pending_at = 0.0
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ routing
    CONFIRMATION_WINDOW = 60.0  # seconds a "say yes to confirm" prompt stays valid

    def _pending_valid(self) -> bool:
        if self._pending is None:
            return False
        if time.monotonic() - self._pending_at > self.CONFIRMATION_WINDOW:
            self._pending = None  # a stale prompt must never be confirmed later
            return False
        return True

    @property
    def awaiting_confirmation(self) -> bool:
        return self._pending_valid()

    def match(self, text: str) -> Optional[Intent]:
        """Pure pattern match - never executes anything."""
        raw = str(text or "").strip()
        value = _norm(raw)
        if not value:
            return None

        if _RE_TIME.match(value):
            return Intent("get_datetime")
        if _RE_DIAG.match(value):
            return Intent("diagnostics")

        # --- reminders ---------------------------------------------------
        if m := _RE_REM_LIST.match(value):
            flag = (m.groupdict().get("all") or "").strip().lower()
            return Intent("reminder_list", {"include_done": bool(flag)})
        if m := _RE_REM_COMPLETE.match(value):
            return Intent("reminder_complete", {"id": int(m.group("a") or m.group("b"))})
        if m := _RE_REM_DELETE.match(value):
            return Intent("reminder_delete", {"id": int(m.group("id"))})
        if m := _RE_REM_UPDATE.match(value):
            return Intent("reminder_update", {"id": int(m.group("id")), "when": m.group("when")})
        if _RE_REM_CLEAR.match(value):
            return Intent("reminder_clear_completed")
        if _REMIND_ANYWHERE.search(value):
            return Intent("reminder_create", {"__sentence__": value})

        # --- memory ------------------------------------------------------
        if _RE_MEM_FORGET_ALL.match(value):
            return Intent("memory_clear")
        if m := _RE_MEM_FORGET.match(value):
            return Intent("memory_delete", {"id": int(m.group("id"))})
        if m := _RE_MEM_UPDATE.match(value):
            return Intent("memory_update", {"id": int(m.group("id")), "content": m.group("c")})
        if _RE_MEM_LIST.match(value):
            return Intent("memory_list")
        if m := _RE_MEM_SEARCH.match(value):
            query = m.group("q").strip()
            if query.lower() in {"me", "myself"}:
                return Intent("memory_list")
            return Intent("memory_search", {"query": query})
        if m := _RE_MEM_SAVE.match(value):
            return Intent("memory_save", {"content": m.group("c")})

        # --- maths / units (soft: ordinary questions fall through to the AI)
        if m := _RE_CONVERT.match(value):
            explicit = bool(m.group("lead"))
            try:
                number = float(m.group("v").replace(",", ""))
            except ValueError:
                number = None
            if number is not None:
                return Intent(
                    "convert_units",
                    {"value": number, "from_unit": m.group("f").strip(), "to_unit": m.group("t").strip()},
                    soft=not explicit,
                )
        if m := _RE_CALC.match(value):
            lead = m.group("lead").lower()
            expr = m.group("expr").strip()
            explicit = lead in {"calculate", "calc", "compute", "evaluate"}
            if explicit or _RE_MATHY.search(expr):
                return Intent("calculate", {"expression": expr}, soft=not explicit)
        return None

    def can_handle(self, text: str) -> bool:
        if self._pending_valid() and _norm(text).lower() in (_YES | _NO):
            return True
        return self.match(text) is not None

    # ---------------------------------------------------------------- execution
    def _run(self, intent: Intent, *, confirmed: bool = False) -> ToolResult:
        arguments = dict(intent.arguments)
        if intent.tool == "reminder_create":
            sentence = arguments.pop("__sentence__", "")
            from core.timeparse import parse_reminder

            parsed = parse_reminder(sentence)
            if parsed is None:
                return ToolResult(
                    False,
                    "I couldn't save that reminder because I couldn't tell **what** or **when**. "
                    "Try: \"remind me to call mum in 10 minutes\", \"remind me to submit the form tomorrow at 9am\", "
                    "or \"remind me at 5pm to stretch\". (I don't have alarms or timers - only reminders.)",
                    tool="reminder_create",
                )
            arguments = {"message": parsed.message, "when": sentence}
        return self.registry.execute(intent.tool, arguments, confirmed=confirmed)

    def handle(self, text: str) -> Optional[str]:
        """Run the request if it is an assistant command; return ``None`` otherwise."""
        value = _norm(text).lower()
        with self._lock:
            if self._pending_valid():
                pending, self._pending = self._pending, None
                if value in _YES:
                    result = self._run(pending, confirmed=True)
                    log.info("confirmed tool %s ok=%s", result.tool, result.ok)
                    return result.output if result.ok else f"That didn't work: {result.output}"
                if value in _NO:
                    return "Okay, cancelled. Nothing was changed."
                # any other message abandons the pending confirmation

            intent = self.match(text)
            if intent is None:
                return None

            result = self._run(intent)
            log.info("tool %s ok=%s confirm=%s", result.tool, result.ok, result.needs_confirmation)
            if result.needs_confirmation:
                self._pending = intent
                self._pending_at = time.monotonic()
                return result.output
            if result.ok:
                return result.output
            if intent.soft:
                return None  # not really for us - let the AI answer
            return result.output

    def cancel_pending(self) -> None:
        with self._lock:
            self._pending = None

    # ------------------------------------------------------------------ helpers
    def memory_context(self, *, online: bool) -> str:
        """Memory text for the model prompt, honouring the privacy settings."""
        try:
            if not self.settings.personalization_enabled:
                return ""
            if online and not self.settings.share_memory_with_online:
                return ""
            return self.memory.context_block()
        except Exception:  # noqa: BLE001 - personalisation must never break chat
            log.exception("could not build memory context")
            return ""


def build_greeting(name: str = "", now=None) -> str:
    """Startup greeting that uses the real local date and time."""
    from datetime import datetime

    now = now or datetime.now()
    hour = now.hour
    part = "Good morning" if 5 <= hour < 12 else "Good afternoon" if 12 <= hour < 18 else "Good evening"
    who = f", {name.strip()}" if name and name.strip() else ""
    return f"{part}{who}. It's {now.strftime('%A')}, {now.day} {now.strftime('%B')}, {now.strftime('%H:%M')}."


# Helper for the UI: keep ``safe_math`` importable from here for tests/docs.
MathError = safe_math.MathError
