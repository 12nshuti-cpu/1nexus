"""Startup helpers: greeting, autostart, tray behavior."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from config.settings import NEXUSSettings


def greeting_text(settings: NEXUSSettings | None = None) -> str:
    cfg = settings or NEXUSSettings()
    name = str(cfg.get("user_name", "") or "").strip()
    now = datetime.now()
    hour = now.hour
    if 5 <= hour < 12:
        part = "Good morning"
    elif 12 <= hour < 17:
        part = "Good afternoon"
    elif 17 <= hour < 22:
        part = "Good evening"
    else:
        part = "Good night"
    date_str = now.strftime("%A, %B %d, %Y")
    if name:
        return f"{part}, {name}! Today is {date_str}. How can I help?"
    return f"{part}! Today is {date_str}. I'm NEXUS, ready to help."


def is_autostart_enabled() -> bool:
    if os.name != "nt":
        # Linux autostart via .desktop file
        autostart = Path.home() / ".config" / "autostart" / "nexus.desktop"
        return autostart.exists()
    # Windows registry check
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, "NEXUS")
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def set_autostart(enabled: bool, executable: str | None = None):
    """Enable/disable autostart. Requires user permission; never call silently."""
    if os.name != "nt":
        autostart_dir = Path.home() / ".config" / "autostart"
        autostart_dir.mkdir(parents=True, exist_ok=True)
        desktop = autostart_dir / "nexus.desktop"
        if enabled:
            exe = executable or sys.executable
            desktop.write_text(
                f"[Desktop Entry]\nType=Application\nName=NEXUS\nExec={exe} {Path(__file__).resolve().parents[1] / 'app.py'}\nX-GNOME-Autostart-enabled=true\n",
                encoding="utf-8",
            )
        else:
            try:
                desktop.unlink(missing_ok=True)
            except Exception:
                pass
        return

    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        try:
            if enabled:
                exe = executable or sys.executable
                # Use --background so NEXUS starts to tray
                winreg.SetValueEx(key, "NEXUS", 0, winreg.REG_SZ, f'"{exe}" "{Path(__file__).resolve().parents[1] / "app.py"}" --background')
            else:
                try:
                    winreg.DeleteValue(key, "NEXUS")
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        raise RuntimeError(f"Could not update startup setting: {e}") from e
