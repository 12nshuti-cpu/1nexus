"""Allowlist policy for shell commands that the *AI model* asks NEXUS to run.

Why this exists
---------------
Language-model output is untrusted text. It can be wrong, and it can be steered
by content the model has read (a pasted document, a web page, a file). The old
guard was a blacklist of "dangerous" words, which cannot be made complete:
``Invoke-Expression``, ``Start-Process``, encoded commands, script blocks and
countless other routes were not covered.

The rule is now inverted. An AI-originated command may run *without asking the
user* only if it is a plain pipeline of known **read-only** inspection commands
with simple arguments. Anything else is refused, and the user is told how to run
it themselves (``run <command>``), which goes through the interactive
confirmation dialog.

Commands the user types themselves are *not* evaluated here - they use
``ShellExecutor.is_risky`` and the confirmation dialog.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Verdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.verdict is Verdict.ALLOW


# Read-only PowerShell commands (compared case-insensitively).
POWERSHELL_ALLOWED = frozenset(
    name.lower()
    for name in (
        "Get-Process", "Get-Service", "Get-ComputerInfo", "Get-NetIPConfiguration",
        "Get-NetAdapter", "Get-NetIPAddress", "Get-PSDrive", "Get-Volume", "Get-Date",
        "Get-CimInstance", "Get-Counter", "Get-Uptime", "Get-Location", "Get-ChildItem",
        "Get-HotFix", "Get-TimeZone", "Get-Culture", "Get-LocalUser", "Get-Disk",
        "Get-Partition", "Get-NetTCPConnection", "Test-Connection",
        # pipeline helpers that only reshape output
        "Select-Object", "Sort-Object", "Where-Object", "Format-Table", "Format-List",
        "ConvertTo-Json", "Measure-Object", "Out-String", "Group-Object",
    )
)

# Read-only CMD / console programs.
CMD_ALLOWED = frozenset(
    ("ipconfig", "systeminfo", "tasklist", "hostname", "whoami", "ver", "netstat", "getmac", "vol", "date", "time", "ping")
)

_FORBIDDEN_CHARS = re.compile(r"[;&<>`${}()\r\n\x00]")
_UNC_OR_URL = re.compile(r"(^|\s)\\\\|://", re.IGNORECASE)
_SAFE_ARG = re.compile(r"""^[\w\-\./:\\\*\?'"=,@+ %]+$""")
_MAX_LENGTH = 400


def _split_pipeline(command: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote = ""
    for char in command:
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
            current.append(char)
        elif char == "|":
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    parts.append("".join(current).strip())
    return parts


def evaluate_ai_command(command: str, shell: str = "powershell") -> Decision:
    """Decide whether an AI-originated command may run without asking the user."""
    text = str(command or "").strip()
    if not text:
        return Decision(Verdict.DENY, "The command is empty.")
    if len(text) > _MAX_LENGTH:
        return Decision(Verdict.DENY, "The command is unusually long.")
    if _FORBIDDEN_CHARS.search(text):
        return Decision(
            Verdict.DENY,
            "It uses shell features (chaining, redirection, variables, sub-expressions or script blocks) "
            "that cannot be verified as read-only.",
        )
    if _UNC_OR_URL.search(text):
        return Decision(Verdict.DENY, "It refers to a network path or URL.")

    shell = "cmd" if str(shell).lower() == "cmd" else "powershell"
    segments = _split_pipeline(text)
    if any(not segment for segment in segments):
        return Decision(Verdict.DENY, "It contains an empty pipeline step.")

    if shell == "cmd" and len(segments) != 1:
        return Decision(Verdict.DENY, "Command Prompt pipelines are not allowed for automatic execution.")

    for segment in segments:
        head, _, rest = segment.partition(" ")
        name = head.strip().lower()
        if shell == "cmd":
            if name.removesuffix(".exe") not in CMD_ALLOWED:
                return Decision(Verdict.DENY, f"'{head}' is not on the read-only command list.")
        elif name not in POWERSHELL_ALLOWED:
            return Decision(Verdict.DENY, f"'{head}' is not on the read-only command list.")
        if rest.strip() and not _SAFE_ARG.match(rest.strip()):
            return Decision(Verdict.DENY, f"The arguments of '{head}' contain characters that cannot be verified as safe.")

    return Decision(Verdict.ALLOW, "Read-only inspection command.")
