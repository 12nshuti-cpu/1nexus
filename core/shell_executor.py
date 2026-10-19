from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from config.settings import NEXUSSettings


@dataclass(frozen=True)
class ShellRequest:
    shell: str
    command: str
    executable: str


@dataclass(frozen=True)
class ShellResult:
    shell: str
    command: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def output(self) -> str:
        parts = []
        if self.stdout.strip():
            parts.append(self.stdout.strip())
        if self.stderr.strip():
            parts.append(f"[stderr]\n{self.stderr.strip()}")
        return "\n\n".join(parts) if parts else "(no output)"


class ShellExecutor:
    """Windows CMD/PowerShell execution used by explicit commands and AI tools."""

    PREFIXES = (
        ("powershell ", "powershell"),
        ("power shell ", "powershell"),
        ("pwsh ", "powershell"),
        ("ps ", "powershell"),
        ("cmd ", "cmd"),
        ("command prompt ", "cmd"),
        ("terminal ", None),
        ("shell ", None),
        ("run command ", None),
        ("execute command ", None),
        ("run ", None),
        ("execute ", None),
    )

    RISK_PATTERNS = (
        r"\b(remove-item|ri|rm)\b",
        r"\b(del|erase|rd|rmdir)\b",
        r"\b(format|diskpart)\b",
        r"\b(shutdown|stop-computer|restart-computer)\b",
        r"\b(stop-process|taskkill)\b",
        r"\b(reg\s+(delete|add))\b",
        r"\b(bcdedit)\b",
        r"\b(takeown|icacls)\b",
        r"\b(clear-disk|clear-partition)\b",
        r"\b(set-executionpolicy)\b",
        r"\b(set-mppreference)\b",
        r"\b(disable-windowsoptionalfeature)\b",
        r"\b(winget\s+uninstall)\b",
        r"\b(net\s+user)\b",
        r"\b(sc\s+delete)\b",
        r"\b(schtasks\s+/delete)\b",
    )

    def __init__(self, settings: NEXUSSettings | None = None):
        self.settings = settings or NEXUSSettings()

    def is_shell_command(self, text: str) -> bool:
        if not self.settings.execution_enabled:
            return False

        value = str(text or "").strip()
        lowered = value.lower()
        return any(
            lowered.startswith(prefix) and len(value) > len(prefix)
            for prefix, _ in self.PREFIXES
        )

    def prepare(self, text: str, *, default_shell: str | None = None) -> ShellRequest | None:
        value = str(text or "").strip()
        if not value:
            return None

        lowered = value.lower()
        selected_shell = None
        command = value

        for prefix, explicit_shell in self.PREFIXES:
            if lowered.startswith(prefix) and len(value) > len(prefix):
                selected_shell = explicit_shell or default_shell or self.settings.shell
                command = value[len(prefix):].strip()
                break

        # AI tool calls use this function too, but may pass a raw command rather
        # than an explicit user prefix.
        if selected_shell is None:
            selected_shell = default_shell or self.settings.shell
            command = value

        if not command:
            return None

        selected_shell = "cmd" if selected_shell == "cmd" else "powershell"

        if selected_shell == "cmd":
            executable = shutil.which("cmd.exe") or "cmd.exe"
        else:
            executable = (
                shutil.which("pwsh.exe")
                or shutil.which("pwsh")
                or shutil.which("powershell.exe")
                or "powershell.exe"
            )

        return ShellRequest(
            shell=selected_shell,
            command=command,
            executable=executable,
        )

    @classmethod
    def is_risky(cls, command: str) -> bool:
        value = str(command or "")
        return any(
            re.search(pattern, value, flags=re.IGNORECASE)
            for pattern in cls.RISK_PATTERNS
        )

    def run(
        self,
        request: ShellRequest,
        *,
        timeout: int | None = None,
        working_directory: Path | None = None,
    ) -> ShellResult:
        """Execute a prepared request and return its complete result."""
        if request is None:
            raise ValueError("A shell request is required.")

        cwd = working_directory or self.settings.working_directory
        timeout_value = timeout if timeout is not None else self.settings.command_timeout

        try:
            if request.shell == "cmd":
                result = subprocess.run(
                    [request.executable, "/d", "/c", request.command],
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_value,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            else:
                result = subprocess.run(
                    [
                        request.executable,
                        "-NoLogo",
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        request.command,
                    ],
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_value,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout or ""
            stderr = error.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            return ShellResult(
                shell=request.shell,
                command=request.command,
                returncode=-1,
                stdout=stdout,
                stderr=stderr,
                timed_out=True,
            )
        except OSError as error:
            return ShellResult(
                shell=request.shell,
                command=request.command,
                returncode=-1,
                stdout="",
                stderr=str(error),
            )

        return ShellResult(
            shell=request.shell,
            command=request.command,
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            timed_out=False,
        )

    @staticmethod
    def format_result(result: ShellResult, max_chars: int = 24000) -> str:
        output = result.output
        if len(output) > max_chars:
            output = output[:max_chars] + "\n\n[Output truncated by NEXUS]"

        if result.timed_out:
            status = "Timed out"
        else:
            status = f"Exit code: {result.returncode}"

        shell_name = "PowerShell" if result.shell == "powershell" else "Command Prompt"
        return (
            f"### {shell_name}\n\n"
            f"Command: `{result.command}`\n\n"
            f"```text\n{output}\n```\n\n"
            f"{status}"
        )

    @staticmethod
    def display_shell(request: ShellRequest) -> str:
        return "PowerShell" if request.shell == "powershell" else "Command Prompt"
