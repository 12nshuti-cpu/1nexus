from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import re
from typing import Optional, Tuple


class MouseController:
    """Safe Windows mouse-control layer for NEXUS."""

    LEFTDOWN = 0x0002
    LEFTUP = 0x0004
    RIGHTDOWN = 0x0008
    RIGHTUP = 0x0010
    WHEEL = 0x0800

    WHEEL_DELTA = 120

    def __init__(self):
        if os.name != "nt":
            raise RuntimeError("Mouse control is currently supported on Windows only.")

        self.user32 = ctypes.windll.user32

    def move_to(self, x: int, y: int) -> str:
        x, y = self._clamp_coordinates(x, y)
        if not self.user32.SetCursorPos(x, y):
            return f"Could not move the mouse to ({x}, {y})."
        return f"Mouse moved to ({x}, {y})."

    def move_relative(self, dx: int, dy: int) -> str:
        current_x, current_y = self.position()
        return self.move_to(current_x + dx, current_y + dy)

    def click(self) -> str:
        self._mouse_event(self.LEFTDOWN)
        self._mouse_event(self.LEFTUP)
        return "Left click performed."

    def double_click(self) -> str:
        self.click()
        self.click()
        return "Double-click performed."

    def right_click(self) -> str:
        self._mouse_event(self.RIGHTDOWN)
        self._mouse_event(self.RIGHTUP)
        return "Right click performed."

    def scroll(self, amount: int) -> str:
        amount = int(amount)
        if amount == 0:
            return "Scroll amount must not be zero."

        delta = amount * self.WHEEL_DELTA
        self._mouse_event(self.WHEEL, data=delta)

        direction = "up" if amount > 0 else "down"
        count = abs(amount)
        unit = "notch" if count == 1 else "notches"
        return f"Scrolled {direction} {count} {unit}."

    def position(self) -> Tuple[int, int]:
        point = wintypes.POINT()
        if not self.user32.GetCursorPos(ctypes.byref(point)):
            return 0, 0
        return int(point.x), int(point.y)

    def _clamp_coordinates(self, x: int, y: int) -> Tuple[int, int]:
        width = self.user32.GetSystemMetrics(0)
        height = self.user32.GetSystemMetrics(1)

        x = max(0, min(int(x), max(width - 1, 0)))
        y = max(0, min(int(y), max(height - 1, 0)))
        return x, y

    def _mouse_event(self, flags: int, data: int = 0) -> None:
        self.user32.mouse_event(flags, 0, 0, data, 0)

    @staticmethod
    def parse_coordinates(text: str) -> Optional[Tuple[int, int]]:
        match = re.search(r"(-?\d+)\s*[, ]\s*(-?\d+)", text)
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))
