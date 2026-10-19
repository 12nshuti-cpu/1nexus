"""Tiny Windows resident hotkey helper for NEXUS.

This process is intentionally independent from the NEXUS GUI/background voice
process. It keeps Ctrl+Alt+N registered even when the main NEXUS application
is closed. The helper launches NEXUS with --activate; the NEXUS process then
brings an existing instance forward or opens a new instance.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import time
import sys
from pathlib import Path


HOTKEY_ID = 0x4E58
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
VK_N = 0x4E
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
ERROR_ALREADY_EXISTS = 183


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
    ]


def resource_path(relative: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / relative
    return Path(__file__).resolve().parent / relative


def nexus_executable() -> Path:
    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    candidates = (
        base / "NEXUS.exe",
        base.parent / "NEXUS.exe",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def activate_nexus():
    executable = nexus_executable()
    if not executable.exists():
        return

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(
            [str(executable), "--activate"],
            cwd=str(executable.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    except Exception:
        pass


def single_instance():
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, "NEXUS_GLOBAL_HOTKEY_HELPER_2026")
    already = kernel32.GetLastError() == ERROR_ALREADY_EXISTS
    return mutex, not already


def main():
    if os.name != "nt":
        return 0

    mutex, first = single_instance()
    if not first:
        _ = mutex
        return 0

    user32 = ctypes.windll.user32
    registered = bool(
        user32.RegisterHotKey(
            None,
            HOTKEY_ID,
            MOD_CONTROL | MOD_ALT,
            VK_N,
        )
    )
    if not registered:
        # Another process may own Ctrl+Alt+N at startup. Retry briefly rather
        # than silently losing the global shortcut for the whole session.
        for _ in range(20):
            time.sleep(0.5)
            registered = bool(
                user32.RegisterHotKey(
                    None,
                    HOTKEY_ID,
                    MOD_CONTROL | MOD_ALT,
                    VK_N,
                )
            )
            if registered:
                break
        if not registered:
            return 1

    try:
        message = MSG()
        while True:
            result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
            if result == 0 or result == -1:
                break

            if message.message == WM_HOTKEY and message.wParam == HOTKEY_ID:
                activate_nexus()
    finally:
        user32.UnregisterHotKey(None, HOTKEY_ID)
        _ = mutex

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
