from __future__ import annotations

import ctypes
import os
import time
from typing import Optional


class WindowController:
    """
    Safe Windows window-control layer for NEXUS.

    Supported:
    - Minimize active window
    - Maximize active window
    - Restore active window
    - Close active window normally
    - Show desktop
    - Switch/focus an open window by title
    - Focus a window belonging to a launched process

    This does not force-kill processes.
    """

    SW_MINIMIZE = 6
    SW_MAXIMIZE = 3
    SW_RESTORE = 9

    VK_LWIN = 0x5B
    VK_D = 0x44
    KEYEVENTF_KEYUP = 0x0002

    WM_CLOSE = 0x0010

    def __init__(self):
        if os.name != "nt":
            raise RuntimeError(
                "Window control is currently supported on Windows only."
            )

        self.user32 = ctypes.windll.user32

    def minimize_active(self):
        hwnd = self._foreground_window()
        if not hwnd:
            return "There is no active window to minimize."
        self.user32.ShowWindow(hwnd, self.SW_MINIMIZE)
        return "Active window minimized."

    def maximize_active(self):
        hwnd = self._foreground_window()
        if not hwnd:
            return "There is no active window to maximize."
        self.user32.ShowWindow(hwnd, self.SW_MAXIMIZE)
        return "Active window maximized."

    def restore_active(self):
        hwnd = self._foreground_window()
        if not hwnd:
            return "There is no active window to restore."
        self.user32.ShowWindow(hwnd, self.SW_RESTORE)
        return "Active window restored."

    def close_active(self):
        hwnd = self._foreground_window()
        if not hwnd:
            return "There is no active window to close."
        self.user32.PostMessageW(hwnd, self.WM_CLOSE, 0, 0)
        return "Close request sent to the active window."

    def show_desktop(self):
        self.user32.keybd_event(self.VK_LWIN, 0, 0, 0)
        self.user32.keybd_event(self.VK_D, 0, 0, 0)
        self.user32.keybd_event(self.VK_D, 0, self.KEYEVENTF_KEYUP, 0)
        self.user32.keybd_event(self.VK_LWIN, 0, self.KEYEVENTF_KEYUP, 0)
        return "Desktop displayed."

    def switch_to(self, target):
        target = str(target or "").strip().lower()
        if not target:
            return "Tell me which application you want me to switch to."

        matches = []
        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )

        def callback(hwnd, _lparam):
            if not self.user32.IsWindowVisible(hwnd):
                return True

            length = self.user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True

            buffer = ctypes.create_unicode_buffer(length + 1)
            self.user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value.strip()

            if title and target in title.lower():
                matches.append((hwnd, title))

            return True

        self.user32.EnumWindows(EnumWindowsProc(callback), 0)

        if not matches:
            return f"I couldn't find an open window matching '{target}'."

        hwnd, title = matches[0]

        if self.user32.IsIconic(hwnd):
            self.user32.ShowWindow(hwnd, self.SW_RESTORE)

        self.user32.SetForegroundWindow(hwnd)

        return f"Switched to {title}."

    def focus_process(self, pid, timeout=5.0):
        """
        Find and focus the first visible top-level window belonging to pid.
        Returns True when focused, otherwise False.
        """
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return False

        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            hwnd = self._find_window_for_process(pid)

            if hwnd:
                if self.user32.IsIconic(hwnd):
                    self.user32.ShowWindow(hwnd, self.SW_RESTORE)

                self.user32.SetForegroundWindow(hwnd)

                # Give Windows a moment to apply foreground focus.
                time.sleep(0.05)

                if self._foreground_window() == hwnd:
                    return True

                # One more foreground attempt can help with Windows focus timing.
                self.user32.SetForegroundWindow(hwnd)
                time.sleep(0.05)

                if self._foreground_window() == hwnd:
                    return True

            time.sleep(0.1)

        return False

    def _find_window_for_process(self, pid):
        result = []

        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )

        def callback(hwnd, _lparam):
            if not self.user32.IsWindowVisible(hwnd):
                return True

            window_pid = ctypes.c_ulong()
            self.user32.GetWindowThreadProcessId(
                hwnd,
                ctypes.byref(window_pid),
            )

            if int(window_pid.value) != pid:
                return True

            length = self.user32.GetWindowTextLengthW(hwnd)

            # Ignore invisible/untitled helper windows.
            if length <= 0:
                return True

            result.append(int(hwnd))
            return False

        self.user32.EnumWindows(EnumWindowsProc(callback), 0)

        return result[0] if result else None

    def _foreground_window(self) -> Optional[int]:
        hwnd = self.user32.GetForegroundWindow()
        if not hwnd:
            return None
        return int(hwnd)
