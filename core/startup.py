"""Start-with-Windows support (per-user, reversible, opt-in).

NEXUS registers itself under ``HKEY_CURRENT_USER\\...\\CurrentVersion\\Run``.
That needs no administrator rights, affects only the current Windows user, and
is removed again when the user turns the option off. Nothing here runs unless
the user changes the setting.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "NEXUS"


class StartupError(RuntimeError):
    pass


def startup_command(*, frozen: bool | None = None, executable: str | None = None, script: str | None = None) -> str:
    """Command line Windows should run at sign-in (starts NEXUS in the tray)."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    exe = executable or sys.executable
    if frozen:
        return f'"{exe}" --background'
    pythonw = Path(exe).with_name("pythonw.exe")
    interpreter = str(pythonw) if pythonw.is_file() else exe
    entry = script or str(Path(__file__).resolve().parents[1] / "app.py")
    return f'"{interpreter}" "{entry}" --background'


def _winreg(module=None):
    if module is not None:
        return module
    if os.name != "nt":
        raise StartupError("Start with Windows is only available on Windows.")
    import winreg

    return winreg


def is_enabled(winreg_module=None) -> bool:
    reg = _winreg(winreg_module)
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_READ) as key:
            value, _kind = reg.QueryValueEx(key, VALUE_NAME)
            return bool(str(value).strip())
    except FileNotFoundError:
        return False
    except OSError:
        return False


def set_enabled(enabled: bool, *, winreg_module=None, command: str | None = None) -> None:
    """Add or remove the Run entry. Raises :class:`StartupError` on failure."""
    reg = _winreg(winreg_module)
    try:
        if enabled:
            with reg.CreateKey(reg.HKEY_CURRENT_USER, RUN_KEY) as key:
                reg.SetValueEx(key, VALUE_NAME, 0, reg.REG_SZ, command or startup_command())
        else:
            try:
                with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
                    reg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass  # already off
    except OSError as error:
        raise StartupError(f"Windows refused the startup change: {error}") from error
