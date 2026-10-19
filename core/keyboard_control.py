from __future__ import annotations

import ctypes
import os
import time


class KeyboardController:
    """
    Controlled Windows keyboard interaction for NEXUS.

    Supports:
    - Typing text
    - Common individual keys
    - Common keyboard shortcuts
    - Windows shortcuts

    This does not execute arbitrary shell commands.
    """

    KEY_CODES = {
        "backspace": 0x08,
        "tab": 0x09,
        "enter": 0x0D,
        "return": 0x0D,
        "shift": 0x10,
        "ctrl": 0x11,
        "control": 0x11,
        "alt": 0x12,
        "pause": 0x13,
        "capslock": 0x14,
        "escape": 0x1B,
        "esc": 0x1B,
        "space": 0x20,
        "pageup": 0x21,
        "pagedown": 0x22,
        "end": 0x23,
        "home": 0x24,
        "left": 0x25,
        "up": 0x26,
        "right": 0x27,
        "down": 0x28,
        "insert": 0x2D,
        "delete": 0x2E,

        "0": 0x30,
        "1": 0x31,
        "2": 0x32,
        "3": 0x33,
        "4": 0x34,
        "5": 0x35,
        "6": 0x36,
        "7": 0x37,
        "8": 0x38,
        "9": 0x39,

        "a": 0x41,
        "b": 0x42,
        "c": 0x43,
        "d": 0x44,
        "e": 0x45,
        "f": 0x46,
        "g": 0x47,
        "h": 0x48,
        "i": 0x49,
        "j": 0x4A,
        "k": 0x4B,
        "l": 0x4C,
        "m": 0x4D,
        "n": 0x4E,
        "o": 0x4F,
        "p": 0x50,
        "q": 0x51,
        "r": 0x52,
        "s": 0x53,
        "t": 0x54,
        "u": 0x55,
        "v": 0x56,
        "w": 0x57,
        "x": 0x58,
        "y": 0x59,
        "z": 0x5A,

        "f1": 0x70,
        "f2": 0x71,
        "f3": 0x72,
        "f4": 0x73,
        "f5": 0x74,
        "f6": 0x75,
        "f7": 0x76,
        "f8": 0x77,
        "f9": 0x78,
        "f10": 0x79,
        "f11": 0x7A,
        "f12": 0x7B,

        "win": 0x5B,
        "windows": 0x5B,
    }

    SHORTCUTS = {
        "ctrl+c": ("ctrl", "c"),
        "ctrl+v": ("ctrl", "v"),
        "ctrl+x": ("ctrl", "x"),
        "ctrl+z": ("ctrl", "z"),
        "ctrl+y": ("ctrl", "y"),
        "ctrl+a": ("ctrl", "a"),
        "ctrl+s": ("ctrl", "s"),
        "ctrl+f": ("ctrl", "f"),
        "ctrl+n": ("ctrl", "n"),
        "ctrl+o": ("ctrl", "o"),
        "ctrl+p": ("ctrl", "p"),

        "alt+tab": ("alt", "tab"),
        "alt+f4": ("alt", "f4"),

        "win+d": ("win", "d"),
        "win+e": ("win", "e"),
        "win+r": ("win", "r"),
        "win+l": ("win", "l"),

        "ctrl+shift+esc": ("ctrl", "shift", "esc"),
    }

    def __init__(self):
        if os.name != "nt":
            raise RuntimeError(
                "Keyboard control is currently supported on Windows only."
            )

        self.user32 = ctypes.windll.user32

        self.KEYEVENTF_KEYUP = 0x0002

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    def type_text(self, text: str) -> str:
        """
        Type text into the currently focused application.
        """

        text = str(text or "")

        if not text:
            return "There is no text to type."

        for character in text:
            self._type_character(character)

        return f"Typed: {text}"

    def press_key(self, key: str) -> str:
        """
        Press one keyboard key.
        """

        key = self._normalize_key(key)

        if key not in self.KEY_CODES:
            return f"I don't recognize the key '{key}'."

        self._key_down(key)
        self._key_up(key)

        return f"Pressed {key}."

    def press_shortcut(self, shortcut: str) -> str:
        """
        Press a controlled keyboard shortcut.
        """

        shortcut = self._normalize_shortcut(shortcut)

        keys = self.SHORTCUTS.get(shortcut)

        if keys is None:
            return f"I don't support the shortcut '{shortcut}' yet."

        pressed = []

        try:
            for key in keys:
                self._key_down(key)
                pressed.append(key)

            return f"Pressed {shortcut}."

        finally:
            for key in reversed(pressed):
                self._key_up(key)

    # ---------------------------------------------------------
    # INTERNAL KEYBOARD METHODS
    # ---------------------------------------------------------

    def _normalize_key(self, key: str) -> str:
        key = str(key or "").strip().lower()

        aliases = {
            "return": "enter",
            "escape": "esc",
            "control": "ctrl",
            "windows": "win",
            "windows key": "win",
            "spacebar": "space",
            "del": "delete",
            "pgup": "pageup",
            "pgdn": "pagedown",
        }

        return aliases.get(key, key)

    def _normalize_shortcut(self, shortcut: str) -> str:
        shortcut = str(shortcut or "").strip().lower()

        shortcut = shortcut.replace(" ", "")

        shortcut = shortcut.replace("control+", "ctrl+")
        shortcut = shortcut.replace("windows+", "win+")

        return shortcut

    def _key_down(self, key: str):
        normalized = self._normalize_key(key)

        if normalized not in self.KEY_CODES:
            raise ValueError(f"Unknown key: {key}")

        vk = self.KEY_CODES[normalized]

        self.user32.keybd_event(
            vk,
            0,
            0,
            0,
        )

        time.sleep(0.015)

    def _key_up(self, key: str):
        normalized = self._normalize_key(key)

        if normalized not in self.KEY_CODES:
            raise ValueError(f"Unknown key: {key}")

        vk = self.KEY_CODES[normalized]

        self.user32.keybd_event(
            vk,
            0,
            self.KEYEVENTF_KEYUP,
            0,
        )

        time.sleep(0.015)

    def _type_character(self, character: str):
        """
        Type Unicode text using the Windows Unicode input mechanism.

        This supports characters that cannot be represented by a simple
        virtual-key lookup.
        """

        if character == "\n":
            self.press_key("enter")
            return

        if character == "\r":
            return

        if character == "\t":
            self.press_key("tab")
            return

        scan = self.user32.VkKeyScanW(ord(character))

        if scan == -1:
            self._unicode_character(character)
            return

        vk = scan & 0xFF
        shift_state = (scan >> 8) & 0xFF

        modifiers = []

        if shift_state & 1:
            modifiers.append("shift")

        if shift_state & 2:
            modifiers.append("ctrl")

        if shift_state & 4:
            modifiers.append("alt")

        for modifier in modifiers:
            self._key_down(modifier)

        self.user32.keybd_event(
            vk,
            0,
            0,
            0,
        )

        self.user32.keybd_event(
            vk,
            0,
            self.KEYEVENTF_KEYUP,
            0,
        )

        for modifier in reversed(modifiers):
            self._key_up(modifier)

    def _unicode_character(self, character: str):
        """
        Send a Unicode character through KEYEVENTF_UNICODE.
        """

        KEYEVENTF_UNICODE = 0x0004

        codepoint = ord(character)

        self.user32.keybd_event(
            0,
            codepoint,
            KEYEVENTF_UNICODE,
            0,
        )

        self.user32.keybd_event(
            0,
            codepoint,
            KEYEVENTF_UNICODE | self.KEYEVENTF_KEYUP,
            0,
        )