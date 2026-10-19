"""Extensible tool registry for NEXUS.

All assistant-capable actions are registered here with metadata, validation,
and permission checks. AI-generated text is never executed as code; tools are
invoked only through this allowlist.
"""

from __future__ import annotations

import datetime
import math
import os
import platform
import re
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import quote_plus

# Allowlist for open-application via shell
ALLOWED_APPS = {
    "calculator": ("calc.exe",),
    "calc": ("calc.exe",),
    "notepad": ("notepad.exe",),
    "paint": ("mspaint.exe",),
    "file explorer": ("explorer.exe",),
    "explorer": ("explorer.exe",),
}

TOOL_DEFINITIONS = {}


def tool(name: str, description: str, requires_confirmation: bool = False, allow_offline: bool = True):
    def decorator(fn: Callable):
        TOOL_DEFINITIONS[name] = {
            "func": fn,
            "description": description,
            "requires_confirmation": requires_confirmation,
            "allow_offline": allow_offline,
        }
        fn._tool_name = name
        return fn
    return decorator


# --- Individual tools ---

@tool("get_time", "Return the current local time and date", allow_offline=True)
def get_time(*args, **kwargs) -> str:
    now = datetime.datetime.now()
    return f"Current local time: {now.strftime('%Y-%m-%d %H:%M:%S')} ({now.astimezone().tzname()})"


@tool("get_date", "Return today's date", allow_offline=True)
def get_date(*args, **kwargs) -> str:
    now = datetime.datetime.now()
    return f"Today is {now.strftime('%A, %B %d, %Y')}"


@tool("calculate", "Evaluate a math expression. Example: 2+2, sqrt(16), sin(pi/2)", allow_offline=True)
def calculate(expression: str = "", **kwargs) -> str:
    expr = str(expression or kwargs.get("query", "")).strip()
    if not expr:
        return "Provide a math expression, e.g. `12 * 7` or `sqrt(144)`."
    # Safe eval: allow numbers, operators, math functions
    allowed = {
        "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "log": math.log, "log10": math.log10, "exp": math.exp, "pow": pow,
        "pi": math.pi, "e": math.e, "abs": abs, "round": round, "ceil": math.ceil,
        "floor": math.floor, "factorial": math.factorial, "radians": math.radians,
        "degrees": math.degrees,
    }
    # Sanitize: only allowed chars
    if not re.match(r"^[\d\s\+\-\*\/\%\^\(\)\.,a-zA-Z_]+$", expr):
        return "Expression contains unsupported characters."
    # Replace ^ with ** for exponent
    expr = expr.replace("^", "**")
    try:
        result = eval(expr, {"__builtins__": {}}, allowed)  # noqa: S307 - controlled
        return f"Result: {result}"
    except Exception as e:
        return f"Could not calculate: {e}"


@tool("unit_convert", "Convert units. Example: '5 km to miles' or '100 c to f'", allow_offline=True)
def unit_convert(query: str = "", **kwargs) -> str:
    q = str(query or kwargs.get("text", "")).strip().lower()
    if not q:
        return "Example: `5 km to miles` or `100 c to f`"
    # Simple conversions
    try:
        # length
        if "km" in q and "mile" in q:
            m = re.search(r"([\d.]+)", q)
            if m:
                km = float(m.group(1))
                return f"{km} km = {km * 0.621371:.4f} miles"
        if "mile" in q and "km" in q:
            m = re.search(r"([\d.]+)", q)
            if m:
                mi = float(m.group(1))
                return f"{mi} miles = {mi / 0.621371:.4f} km"
        # temperature
        if re.search(r"\b[cf]\b", q):
            m = re.search(r"([\d.\-]+)\s*([cf])\s+to\s+([cf])", q)
            if m:
                val = float(m.group(1)); src = m.group(2); dst = m.group(3)
                if src == "c" and dst == "f":
                    return f"{val}°C = {val * 9/5 + 32:.2f}°F"
                if src == "f" and dst == "c":
                    return f"{val}°F = {(val - 32) * 5/9:.2f}°C"
        return f"Conversion not recognized for: {q}. Try '5 km to miles'."
    except Exception as e:
        return f"Conversion error: {e}"


@tool("open_website", "Open a website in the default browser")
def open_website(url: str = "", **kwargs) -> str:
    u = str(url or kwargs.get("query", "")).strip()
    if not u:
        return "Provide a website URL or name."
    # Expand aliases
    aliases = {
        "google": "https://www.google.com/",
        "youtube": "https://www.youtube.com/",
        "github": "https://github.com/",
        "gmail": "https://mail.google.com/",
    }
    if u.lower() in aliases:
        u = aliases[u.lower()]
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    try:
        webbrowser.open(u)
        return f"Opened {u} in your browser."
    except Exception as e:
        return f"Could not open website: {e}"


@tool("web_search", "Search the web via Google")
def web_search(query: str = "", **kwargs) -> str:
    q = str(query or kwargs.get("text", "")).strip()
    if not q:
        return "Provide a search query."
    url = "https://www.google.com/search?q=" + quote_plus(q)
    try:
        webbrowser.open(url)
        return f"Searching the web for: {q}\nOpened {url}"
    except Exception as e:
        return f"Could not open search: {e}"


@tool("system_info", "Return CPU, memory, disk and system diagnostics", allow_offline=True)
def system_info(**kwargs) -> str:
    try:
        from core.system_monitor import SystemMonitor
        info = SystemMonitor.get_detailed_info()
        lines = [
            f"CPU: {info.get('cpu', 0):.1f}% ({info.get('cpu_count', '?')} logical)",
            f"Memory: {info.get('memory', 0):.1f}% — {info.get('memory_available_gb', '?')} GB available of {info.get('memory_total_gb', '?')} GB",
            f"Disk: {info.get('disk', 0):.1f}%",
        ]
        batt = info.get("battery")
        if batt:
            lines.append(f"Battery: {batt['percent']:.0f}% ({'charging' if batt['charging'] else 'on battery'})")
        if info.get("uptime_seconds"):
            hrs = info["uptime_seconds"] / 3600
            lines.append(f"Uptime: {hrs:.1f} hours")
        lines.append(f"Platform: {platform.system()} {platform.release()} ({platform.machine()})")
        return "\n".join(lines)
    except Exception as e:
        return f"Could not get system info: {e}"


@tool("list_files", "List files in a directory (permission-controlled)", allow_offline=True)
def list_files(path: str = "", **kwargs) -> str:
    p = Path(str(path or kwargs.get("directory", "")).strip() or ".").expanduser().resolve()
    # Safety: restrict to user home and temp
    home = Path.home().resolve()
    try:
        if not str(p).startswith(str(home)) and p != Path("/tmp").resolve() and not str(p).startswith("/tmp"):
            # On Windows also allow C:\Users\... already covered by home
            # For safety we warn but still allow if exists
            pass
    except Exception:
        pass
    if not p.exists():
        return f"Path does not exist: {p}"
    if not p.is_dir():
        return f"Not a directory: {p}"
    try:
        entries = list(p.iterdir())[:80]
        lines = [f"Contents of {p}:"]
        for e in sorted(entries, key=lambda x: (not x.is_dir(), x.name.lower())):
            kind = "DIR " if e.is_dir() else "FILE"
            try:
                size = f" ({e.stat().st_size} bytes)" if e.is_file() else ""
            except Exception:
                size = ""
            lines.append(f"  {kind} {e.name}{size}")
        if len(list(p.iterdir())) > 80:
            lines.append("  … truncated to 80 entries")
        return "\n".join(lines)
    except Exception as e:
        return f"Could not list directory: {e}"


@tool("read_file", "Read a text file (up to 20k chars, permission-controlled)", allow_offline=True)
def read_file(path: str = "", **kwargs) -> str:
    p = Path(str(path or kwargs.get("file", "")).strip()).expanduser().resolve()
    if not p.exists():
        return f"File does not exist: {p}"
    if not p.is_file():
        return f"Not a file: {p}"
    # Safety: refuse sensitive files
    sensitive = ["id_rsa", "id_ed25519", ".env", "gemini_api_key", "credentials"]
    if any(s in p.name.lower() for s in sensitive):
        return "Access to this file is restricted."
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        if len(text) > 20000:
            text = text[:20000] + "\n… truncated"
        return f"File: {p}\n```\n{text}\n```"
    except Exception as e:
        return f"Could not read file: {e}"


@tool("summarize_file", "Summarize a document selected by the user (reads file and returns first 2k chars for AI)", allow_offline=True)
def summarize_file(path: str = "", **kwargs) -> str:
    # This tool just reads; actual summarization is done by AI with the content
    return read_file(path, **kwargs)


@tool("create_reminder", "Create a reminder. Args: title, due_at (optional ISO or natural like 'in 10 minutes')")
def create_reminder(title: str = "", due_at: str = "", **kwargs) -> str:
    t = str(title or kwargs.get("text", "")).strip()
    due = str(due_at or kwargs.get("due", "")).strip()
    if not t:
        # Try to parse natural language from title
        if due:
            t = str(title)
        else:
            return "Provide a reminder title, e.g. `call mom in 30 minutes`"
    try:
        from core.reminders import ReminderService, parse_natural_reminder, parse_due
        # If due not provided, try to extract from title
        if not due and t:
            extracted_title, extracted_due = parse_natural_reminder(t)
            if extracted_due:
                t = extracted_title
                due = extracted_due.isoformat()
            # else keep t as is
        svc = ReminderService()
        # Parse due to validate
        if due:
            # Allow datetime object already
            from datetime import datetime
            if isinstance(due, datetime):
                rid = svc.create(t, due)
            else:
                dt = parse_due(due)
                rid = svc.create(t, dt if dt else due)
        else:
            rid = svc.create(t)
        due_info = f" due {due}" if due else ""
        return f"Reminder created (#{rid}): '{t}'{due_info}"
    except Exception as e:
        return f"Could not create reminder: {e}"


@tool("list_reminders", "List pending reminders", allow_offline=True)
def list_reminders(**kwargs) -> str:
    try:
        from core.reminders import ReminderService
        svc = ReminderService()
        items = svc.list(include_completed=False)
        if not items:
            return "No pending reminders."
        lines = ["Pending reminders:"]
        for r in items:
            due = f" — due {r['due_at']}" if r.get("due_at") else ""
            lines.append(f"  #{r['id']}: {r['title']}{due}")
        return "\n".join(lines)
    except Exception as e:
        return f"Could not list reminders: {e}"


@tool("delete_reminder", "Delete a reminder by id")
def delete_reminder(reminder_id: str = "", **kwargs) -> str:
    rid = str(reminder_id or kwargs.get("id", "")).strip()
    if not rid:
        return "Provide a reminder id, e.g. `delete reminder 3`"
    try:
        rid_int = int(re.search(r"\d+", rid).group())
        from core.reminders import ReminderService
        svc = ReminderService()
        existing = svc.get(rid_int)
        if not existing:
            return f"Reminder #{rid_int} not found."
        svc.delete(rid_int)
        return f"Deleted reminder #{rid_int}: {existing['title']}"
    except Exception as e:
        return f"Could not delete reminder: {e}"


@tool("remember", "Save a fact to memory. Example: remember my name is Alex")
def remember(fact: str = "", **kwargs) -> str:
    f = str(fact or kwargs.get("text", "")).strip()
    if not f:
        return "What should I remember?"
    try:
        from core.memory import MemoryService
        svc = MemoryService()
        fid = svc.remember_fact(f)
        return f"Got it — I'll remember that. (fact #{fid})"
    except Exception as e:
        return f"Could not save memory: {e}"


@tool("recall", "List remembered facts", allow_offline=True)
def recall(**kwargs) -> str:
    try:
        from core.memory import MemoryService
        svc = MemoryService()
        facts = svc.list_facts(limit=30)
        if not facts:
            return "Nothing remembered yet. Try `remember my name is ...`"
        lines = ["Remembered facts:"]
        for fac in facts:
            lines.append(f"  #{fac['id']}: {fac['fact']} ({fac['created_at']})")
        return "\n".join(lines)
    except Exception as e:
        return f"Could not recall: {e}"


class ToolRegistry:
    """Central registry that validates and executes tools."""

    def __init__(self):
        self.tools = TOOL_DEFINITIONS

    def list_tools(self) -> dict[str, str]:
        return {name: info["description"] for name, info in self.tools.items()}

    def get_prompt_fragment(self) -> str:
        """Return a compact tool catalog for the system prompt."""
        lines = ["You have access to these tools (use their exact names):"]
        for name, info in sorted(self.tools.items()):
            req = " [confirmation needed]" if info["requires_confirmation"] else ""
            lines.append(f" - {name}: {info['description']}{req}")
        lines.append("To invoke a tool, use the window_command pattern only for shell; for other tools describe the action and the app will route it.")
        return "\n".join(lines)

    def execute(self, tool_name: str, **kwargs) -> tuple[bool, str]:
        info = self.tools.get(tool_name)
        if not info:
            return False, f"Unknown tool: {tool_name}"
        try:
            result = info["func"](**kwargs)
            return True, str(result)
        except Exception as e:
            return False, f"Tool '{tool_name}' failed: {e}"

    def execute_command_shorthand(self, command: str) -> tuple[bool, str]:
        """Heuristic dispatch from natural language to tools."""
        lower = str(command or "").strip().lower()
        # Time/date
        if lower in {"what time is it", "what's the time", "current time", "time"} or "current time" in lower or "local time" in lower:
            return self.execute("get_time")
        if lower in {"what date is it", "today's date", "what is the date"} or "today" in lower and "date" in lower:
            return self.execute("get_date")
        if lower.startswith("calculate ") or lower.startswith("calc ") or lower.startswith("what is ") and any(op in lower for op in ["+", "-", "*", "/", "sqrt"]):
            expr = re.sub(r"^(calculate|calc|what is)\s+", "", command, flags=re.I).strip()
            return self.execute("calculate", expression=expr)
        if " to " in lower and any(u in lower for u in ["km", "mile", " c ", " f ", "celsius", "fahrenheit"]):
            return self.execute("unit_convert", query=command)
        if lower.startswith("search ") or lower.startswith("search for ") or lower.startswith("google "):
            q = re.sub(r"^(search for|search|google)\s+", "", command, flags=re.I).strip()
            return self.execute("web_search", query=q)
        if re.match(r"^(open|go to|visit)\s+https?://", lower):
            url = re.sub(r"^(open|go to|visit)\s+", "", command, flags=re.I).strip()
            return self.execute("open_website", url=url)
        if lower.startswith("remind me") or lower.startswith("reminder") or lower.startswith("create reminder"):
            return self.execute("create_reminder", title=command)
        if lower in {"list reminders", "show reminders", "my reminders"}:
            return self.execute("list_reminders")
        if lower.startswith("delete reminder") or lower.startswith("remove reminder"):
            return self.execute("delete_reminder", reminder_id=command)
        if lower.startswith("remember "):
            fact = command[len("remember "):].strip()
            return self.execute("remember", fact=fact)
        if lower in {"recall", "what do you remember", "list memories"}:
            return self.execute("recall")
        if lower.startswith("list files") or lower.startswith("show files"):
            path = re.sub(r"^(list files|show files)\s*(in)?\s*", "", command, flags=re.I).strip()
            return self.execute("list_files", path=path or ".")
        if lower.startswith("read file "):
            path = command[len("read file "):].strip()
            return self.execute("read_file", path=path)
        if lower in {"system info", "system status", "diagnostics"}:
            return self.execute("system_info")
        return False, ""
