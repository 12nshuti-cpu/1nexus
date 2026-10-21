from __future__ import annotations

from core.window_control import WindowController
from core.keyboard_control import KeyboardController
from core.mouse_control import MouseController

import ctypes
import os
import re
import shutil
import subprocess
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus


class _UnavailableController:
    """Returned in place of a controller that could not be initialised."""

    def __init__(self, label: str, reason: str):
        self._label = label
        self._reason = reason

    def __getattr__(self, _name):
        def _unavailable(*_args, **_kwargs) -> str:
            return f"{self._label} is not available on this computer. {self._reason}".strip()

        return _unavailable


class PCController:
    """
    Controlled Windows PC-control layer for NEXUS.

    Phase 5A supports non-destructive actions:
    opening approved applications, folders, websites, web searches,
    and showing the desktop.

    It does not execute arbitrary shell commands or terminate processes.
    Explicit system actions are implemented through controlled Windows APIs,
    and file deletion uses the Windows Recycle Bin.
    """
    
    def __init__(self):
        self.window = self._safe_controller(WindowController, "Window control")
        self.keyboard = self._safe_controller(KeyboardController, "Keyboard control")
        self.mouse = self._safe_controller(MouseController, "Mouse control")
        self.last_process_id = None
        self.last_folder_path = None
        self.last_browser = None
        self.user_home = Path.home().resolve()

    APP_ALIASES = {
        "calculator": ("calc.exe",),
        "calc": ("calc.exe",),
        "notepad": ("notepad.exe",),
        "text editor": ("notepad.exe",),
        "paint": ("mspaint.exe",),
        "microsoft paint": ("mspaint.exe",),
        "command prompt": ("cmd.exe",),
        "cmd": ("cmd.exe",),
        "powershell": ("powershell.exe",),
        "windows powershell": ("powershell.exe",),
        "task manager": ("taskmgr.exe",),
        "file explorer": ("explorer.exe",),
        "explorer": ("explorer.exe",),
        "control panel": ("control.exe",),
    }

    WEBSITE_ALIASES = {
        "google": "https://www.google.com/",
        "youtube": "https://www.youtube.com/",
        "github": "https://github.com/",
        "chatgpt": "https://chatgpt.com/",
        "gmail": "https://mail.google.com/",
        "google drive": "https://drive.google.com/",
        "stackoverflow": "https://stackoverflow.com/",
    }

    FOLDER_ALIASES = {
        "home": Path.home(),
        "user folder": Path.home(),
        "user home": Path.home(),
        "desktop": Path.home() / "Desktop",
        "documents": Path.home() / "Documents",
        "my documents": Path.home() / "Documents",
        "downloads": Path.home() / "Downloads",
        "my downloads": Path.home() / "Downloads",
        "pictures": Path.home() / "Pictures",
        "my pictures": Path.home() / "Pictures",
        "music": Path.home() / "Music",
        "my music": Path.home() / "Music",
        "videos": Path.home() / "Videos",
        "my videos": Path.home() / "Videos",
    }
    
    WINDOW_COMMANDS = {
        "minimize window": "minimize",
        "minimize this window": "minimize",
        "minimize active window": "minimize",

        "minimise window": "minimize",
        "minimise this window": "minimize",

        "maximize window": "maximize",
        "maximize this window": "maximize",
        "maximize active window": "maximize",

        "maximise window": "maximize",
        "maximise this window": "maximize",

        "restore window": "restore",
        "restore this window": "restore",
        "restore active window": "restore",

        "close window": "close",
        "close this window": "close",
        "close active window": "close",

        "show desktop": "desktop",
        "show my desktop": "desktop",
        "minimize all windows": "desktop",
    }
    
    KEY_COMMANDS = {
        "press enter": "enter",
        "press return": "enter",
        "press escape": "esc",
        "press esc": "esc",
        "press tab": "tab",
        "press space": "space",
        "press backspace": "backspace",
        "press delete": "delete",
        "press home": "home",
        "press end": "end",
        "press left": "left",
        "press right": "right",
        "press up": "up",
        "press down": "down",
        "press page up": "pageup",
        "press page down": "pagedown",
        "press f1": "f1",
        "press f2": "f2",
        "press f3": "f3",
        "press f4": "f4",
        "press f5": "f5",
        "press f6": "f6",
        "press f7": "f7",
        "press f8": "f8",
        "press f9": "f9",
        "press f10": "f10",
        "press f11": "f11",
        "press f12": "f12",
    }

    KEY_SHORTCUTS = {
        "press ctrl+c": "ctrl+c",
        "press ctrl+v": "ctrl+v",
        "press ctrl+x": "ctrl+x",
        "press ctrl+z": "ctrl+z",
        "press ctrl+y": "ctrl+y",
        "press ctrl+a": "ctrl+a",
        "press ctrl+s": "ctrl+s",
        "press ctrl+f": "ctrl+f",
        "press ctrl+n": "ctrl+n",
        "press ctrl+o": "ctrl+o",
        "press ctrl+p": "ctrl+p",

        "press alt+tab": "alt+tab",
        "press alt+f4": "alt+f4",

        "press win+d": "win+d",
        "press win+e": "win+e",
        "press win+r": "win+r",
        "press win+l": "win+l",

        "press ctrl+shift+esc": "ctrl+shift+esc",
    }
    

    OPEN_PREFIXES = (
        "open ",
        "launch ",
        "start ",
        "run ",
    )

    NAV_PREFIXES = (
        "go to ",
        "goto ",
        "visit ",
    )

    SEARCH_PREFIXES = (
        "search for ",
        "search ",
        "look up ",
        "look for ",
    )

    BROWSER_NAV_PREFIXES = (
        "navigate browser to ",
        "browser go to ",
        "browser navigate to ",
        "navigate chrome to ",
        "chrome go to ",
        "navigate edge to ",
        "edge go to ",
    )

    EXPLORER_NAV_PREFIXES = (
        "navigate file explorer to ",
        "file explorer go to ",
        "explorer go to ",
        "navigate explorer to ",
    )

    def is_windows(self) -> bool:
        return os.name == "nt"

    @staticmethod
    def _safe_controller(factory, label: str):
        """Build a Windows controller, or an honest 'unavailable' stand-in.

        One unavailable controller (non-Windows host, missing API) must not
        take down the whole command engine. The stand-in never pretends an
        action succeeded: every call returns a plain explanation instead.
        """
        try:
            return factory()
        except Exception as error:  # noqa: BLE001
            return _UnavailableController(label, str(error))

    @staticmethod
    def _clean_target(text: str) -> str:
        text = str(text or "").strip()
        text = re.sub(r"\s+", " ", text)
        return text.strip(" .!?")

    def can_handle(self, command: str) -> bool:
        
        command_lower = str(command or "").strip().lower()

        if self._is_natural_language_command(command):
            return True

        if self._is_system_command(command):
            return True

        if self._is_file_action(command):
            return True

        if self._is_application_action(command):
            return True
        
        if command_lower in self.KEY_COMMANDS:
            return True

        if command_lower in self.KEY_SHORTCUTS:
            return True

        if command_lower.startswith("type "):
            text = command[5:].strip()

            if text:
                return True

        if self._is_mouse_command(command):
            return True

        if command_lower in self.WINDOW_COMMANDS:
           return True

        if (
           command_lower.startswith("switch to ")
           or command_lower.startswith("switch over to ")
           or command_lower.startswith("focus ")
        ):
           return True
       
        """Return True only for commands recognized by this local layer."""
        if not self.is_windows():
            return False

        text = self._clean_target(command)
        lower = text.lower()

        if lower in {"show desktop", "minimize all windows"}:
            return True

        for prefix in self.OPEN_PREFIXES:
            if lower.startswith(prefix) and len(lower) > len(prefix):
                target = self._clean_target(text[len(prefix):]).lower()
                if target in self.APP_ALIASES:
                    return True
                if target in self.FOLDER_ALIASES:
                    return True
                if target in self.WEBSITE_ALIASES:
                    return True
                if target in {
                    "visual studio code",
                    "vs code",
                    "vscode",
                    "code",
                    "chrome",
                    "google chrome",
                    "edge",
                    "microsoft edge",
                    "settings",
                    "windows settings",
                    "this pc",
                    "computer",
                }:
                    return True
                if self._looks_like_url(target):
                    return True

        for prefix in self.NAV_PREFIXES:
            if lower.startswith(prefix) and len(lower) > len(prefix):
                return True

        for prefix in self.SEARCH_PREFIXES:
            if lower.startswith(prefix) and len(lower) > len(prefix):
                return True

        return False

    def execute(self, command: str) -> tuple[bool, str]:
        
        command = str(command or "").strip()

        # Allow the assistant name at the beginning of a spoken command.
        command = re.sub(r"^nexus[\\s,:-]+", "", command, flags=re.I).strip()
        command_lower = command.lower()

        # ---------------------------------------------------------
        # PHASE 5F: NATURAL-LANGUAGE PC AGENT
        # ---------------------------------------------------------
        natural_handled, natural_response = self._execute_natural_language(command)
        if natural_handled:
            return True, natural_response

        # ---------------------------------------------------------
        # PHASE 6: SYSTEM + FILE ACTIONS
        # ---------------------------------------------------------
        system_handled, system_response = self._execute_system_command(command)
        if system_handled:
            return True, system_response

        file_handled, file_response = self._execute_file_action(command)
        if file_handled:
            return True, file_response

        # ---------------------------------------------------------
        # PHASE 5E: APPLICATION ACTIONS
        # ---------------------------------------------------------
        application_handled, application_response = self._execute_application_action(command)
        if application_handled:
            return True, application_response
        
        # ---------------------------------------------------------
        # PHASE 5C: KEYBOARD CONTROL
        # ---------------------------------------------------------

        key = self.KEY_COMMANDS.get(command_lower)

        if key:
            try:
                self._focus_last_target()
                return True, self.keyboard.press_key(key)
            except Exception as error:
                return True, f"Keyboard action failed: {error}"

        shortcut = self.KEY_SHORTCUTS.get(command_lower)

        if shortcut:
            try:
                self._focus_last_target()
                return True, self.keyboard.press_shortcut(shortcut)
            except Exception as error:
                return True, f"Keyboard shortcut failed: {error}"

        if command_lower.startswith("type "):
            text = command[5:].strip()

            if not text:
                return True, "Tell me what you want me to type."

            try:
                self._focus_last_target()
                return True, self.keyboard.type_text(text)
            except Exception as error:
                return True, f"Typing failed: {error}"

        # ---------------------------------------------------------
        # PHASE 5D: MOUSE CONTROL
        # ---------------------------------------------------------

        mouse_handled, mouse_response = self._execute_mouse(command)
        if mouse_handled:
            return True, mouse_response

        window_action = self.WINDOW_COMMANDS.get(command_lower)

        if window_action == "minimize":
            return True, self.window.minimize_active()

        if window_action == "maximize":
            return True, self.window.maximize_active()

        if window_action == "restore":
            return True, self.window.restore_active()

        if window_action == "close":
            return True, self.window.close_active()

        if window_action == "desktop":
            return True, self.window.show_desktop()

        if command_lower.startswith("switch over to "):
            target = command[len("switch over to "):].strip()
            return True, self.window.switch_to(target)

        if command_lower.startswith("switch to "):
            target = command[len("switch to "):].strip()
            return True, self.window.switch_to(target)

        if command_lower.startswith("focus "):
            target = command[len("focus "):].strip()
            return True, self.window.switch_to(target)
        
        """
        Execute one supported PC action.

        Returns:
            (handled, response)
        """
        if not self.is_windows():
            return False, "PC control is currently available only on Windows."

        text = self._clean_target(command)
        lower = text.lower()

        if lower in {"show desktop", "minimize all windows"}:
            try:
                self._show_desktop()
                return True, "Desktop displayed."
            except Exception as error:
                return True, f"Could not show the desktop: {error}"

        for prefix in self.OPEN_PREFIXES:
            if lower.startswith(prefix):
                target = self._clean_target(text[len(prefix):])
                return True, self._open_target(target)

        for prefix in self.NAV_PREFIXES:
            if lower.startswith(prefix):
                target = self._clean_target(text[len(prefix):])
                return True, self._open_destination(target)

        for prefix in self.SEARCH_PREFIXES:
            if lower.startswith(prefix):
                query = self._clean_target(text[len(prefix):])
                if not query:
                    return True, "Tell me what you want me to search for."

                url = "https://www.google.com/search?q=" + quote_plus(query)

                if self.last_browser == "chrome":
                    return True, self._launch_chrome(url)

                if self.last_browser == "edge":
                    return True, self._launch_edge(url)

                webbrowser.open(url)
                return True, f"Searching the web for: {query}"

        return False, ""

    SYSTEM_COMMANDS = {
        # Direct forms
        "shutdown": "shutdown",
        "shut down": "shutdown",
        "shutdown pc": "shutdown",
        "shut down pc": "shutdown",
        "power off": "shutdown",
        "power off pc": "shutdown",
        "turn off pc": "shutdown",
        "turn off the pc": "shutdown",
        "restart": "restart",
        "restart pc": "restart",
        "reboot": "restart",
        "reboot pc": "restart",
        "lock": "lock",
        "lock pc": "lock",
        "lock computer": "lock",
        "lock screen": "lock",
        "sleep": "sleep",
        "sleep pc": "sleep",
        "hibernate": "hibernate",
        "hibernate pc": "hibernate",
        "sign out": "signout",
        "log out": "signout",
        "sign out of windows": "signout",
        "cancel shutdown": "cancel_shutdown",
        "cancel restart": "cancel_shutdown",
        "abort shutdown": "cancel_shutdown",
    }

    SYSTEM_COMMAND_PATTERNS = (
        # Shutdown / power off
        (r"^(?:please\s+)?(?:shut\s*down|shutdown)(?:\s+(?:my|the|this)\s+(?:pc|computer|laptop))?$", "shutdown"),
        (r"^(?:please\s+)?(?:turn\s+off|power\s+off)(?:\s+(?:my|the|this)\s+(?:pc|computer|laptop))?$", "shutdown"),
        (r"^(?:please\s+)?(?:switch\s+off)(?:\s+(?:my|the|this)\s+(?:pc|computer|laptop))?$", "shutdown"),

        # Restart / reboot
        (r"^(?:please\s+)?(?:restart|reboot)(?:\s+(?:my|the|this)\s+(?:pc|computer|laptop))?$", "restart"),
        (r"^(?:please\s+)?(?:start\s+my\s+(?:pc|computer|laptop)\s+again)$", "restart"),

        # Lock
        (r"^(?:please\s+)?(?:lock)(?:\s+(?:my|the|this)\s+(?:pc|computer|laptop|screen))?$", "lock"),
        (r"^(?:please\s+)?(?:lock\s+(?:my|the|this)\s+(?:pc|computer|laptop|screen))$", "lock"),
        (r"^(?:please\s+)?(?:secure|lock)\s+(?:my|the)\s+computer$", "lock"),

        # Sleep
        (r"^(?:please\s+)?(?:sleep)(?:\s+(?:my|the|this)\s+(?:pc|computer|laptop))?$", "sleep"),
        (r"^(?:please\s+)?(?:put|send)\s+(?:my|the|this)\s+(?:pc|computer|laptop)\s+(?:to|into)\s+sleep$", "sleep"),
        (r"^(?:please\s+)?put\s+(?:my|the|this)\s+computer\s+to\s+sleep$", "sleep"),

        # Hibernate
        (r"^(?:please\s+)?(?:hibernate)(?:\s+(?:my|the|this)\s+(?:pc|computer|laptop))?$", "hibernate"),
        (r"^(?:please\s+)?put\s+(?:my|the|this)\s+(?:pc|computer|laptop)\s+(?:into|in)\s+hibernate$", "hibernate"),

        # Sign out
        (r"^(?:please\s+)?(?:sign|log)\s+(?:me\s+)?out(?:\s+of\s+(?:windows|my\s+pc|my\s+computer))?$", "signout"),
        (r"^(?:please\s+)?sign\s+me\s+out\s+of\s+windows$", "signout"),

        # Cancel power operation
        (r"^(?:please\s+)?(?:cancel|abort|stop)\s+(?:the\s+)?(?:pending\s+)?(?:shutdown|restart|reboot)$", "cancel_shutdown"),
        (r"^(?:please\s+)?cancel\s+(?:the\s+)?scheduled\s+(?:shutdown|restart)$", "cancel_shutdown"),
    )

    def _get_system_action(self, command: str):
        text = str(command or "").strip()
        lower = text.lower()

        direct = self.SYSTEM_COMMANDS.get(lower)
        if direct:
            return direct

        for pattern, action in self.SYSTEM_COMMAND_PATTERNS:
            if re.match(pattern, text, re.I):
                return action

        return None

    def _is_system_command(self, command: str) -> bool:
        return self._get_system_action(command) is not None

    def _execute_system_command(self, command: str) -> tuple[bool, str]:
        action = self._get_system_action(command)
        if not action:
            return False, ""

        if not self.is_windows():
            return True, "System power control is currently available only on Windows."

        try:
            if action == "shutdown":
                subprocess.Popen(["shutdown.exe", "/s", "/t", "0"], close_fds=True)
                return True, "Shutting down Windows."

            if action == "restart":
                subprocess.Popen(["shutdown.exe", "/r", "/t", "0"], close_fds=True)
                return True, "Restarting Windows."

            if action == "cancel_shutdown":
                subprocess.Popen(["shutdown.exe", "/a"], close_fds=True)
                return True, "Pending shutdown or restart cancelled."

            if action == "lock":
                ctypes.windll.user32.LockWorkStation()
                return True, "Windows locked."

            if action == "sleep":
                ctypes.windll.powrprof.SetSuspendState(False, True, False)
                return True, "Putting the PC to sleep."

            if action == "hibernate":
                ctypes.windll.powrprof.SetSuspendState(True, True, False)
                return True, "Hibernating the PC."

            if action == "signout":
                subprocess.Popen(["shutdown.exe", "/l"], close_fds=True)
                return True, "Signing out of Windows."

            return True, "Unknown system action."
        except Exception as error:
            return True, f"System action failed: {error}"

    def _is_file_action(self, command: str) -> bool:
        text = str(command or "").strip()
        lower = text.lower()
        patterns = (
            r"^(?:create|make)\s+(?:a\s+)?file\s+.+$",
            r"^(?:create|make)\s+(?:a\s+)?folder\s+.+$",
            r"^mkdir\s+.+$",
            r"^open\s+file\s+.+$",
            r"^delete\s+(?:the\s+)?file\s+.+$",
            r"^remove\s+(?:the\s+)?file\s+.+$",
            r"^rename\s+(?:the\s+)?file\s+.+\s+to\s+.+$",
            r"^copy\s+(?:the\s+)?file\s+.+\s+to\s+.+$",
            r"^move\s+(?:the\s+)?file\s+.+\s+to\s+.+$",
        )
        return any(re.match(pattern, text, re.I) for pattern in patterns)

    _DELETE_FILE = re.compile(r"^(?:delete|remove)\s+(?:the\s+)?file\s+(.+)$", re.IGNORECASE)

    def confirmation_prompt(self, command: str) -> str | None:
        """Text to show the user when ``command`` is consequential and must be confirmed first.

        Deleting a file is recoverable (Recycle Bin) but still needs a yes: a mis-heard voice
        command or a typo must not remove anything on its own.
        """
        match = self._DELETE_FILE.match(str(command or "").strip())
        if not match:
            return None
        try:
            target = str(self._safe_user_path(match.group(1)))
        except ValueError:
            target = self._strip_file_command(match.group(1))
        return f"NEXUS is about to move this file to the Recycle Bin:\n\n{target}\n\nContinue?"

    @staticmethod
    def _strip_file_command(value: str) -> str:
        value = str(value or "").strip()
        return PCController._strip_wrapping_quotes(value)

    def _safe_user_path(self, value: str) -> Path:
        raw = self._strip_file_command(value)
        path = Path(os.path.expandvars(os.path.expanduser(raw))).resolve()
        try:
            path.relative_to(self.user_home)
        except ValueError:
            raise ValueError("For safety, file actions are limited to your user folder.")
        return path

    def _execute_file_action(self, command: str) -> tuple[bool, str]:
        text = str(command or "").strip()

        match = re.match(r"^(?:create|make)\s+(?:a\s+)?file\s+(.+)$", text, re.I)
        if match:
            try:
                path = self._safe_user_path(match.group(1))
                if path.exists():
                    return True, f"That file already exists: {path}"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
                return True, f"Created file: {path}"
            except Exception as error:
                return True, f"Could not create the file: {error}"

        match = re.match(r"^(?:create|make)\s+(?:a\s+)?folder\s+(.+)$", text, re.I)
        if not match:
            match = re.match(r"^mkdir\s+(.+)$", text, re.I)
        if match:
            try:
                path = self._safe_user_path(match.group(1))
                path.mkdir(parents=True, exist_ok=True)
                return True, f"Created folder: {path}"
            except Exception as error:
                return True, f"Could not create the folder: {error}"

        match = re.match(r"^open\s+file\s+(.+)$", text, re.I)
        if match:
            try:
                path = self._safe_user_path(match.group(1))
                if not path.exists() or not path.is_file():
                    return True, f"File not found: {path}"
                os.startfile(str(path))
                return True, f"Opened file: {path.name}"
            except Exception as error:
                return True, f"Could not open the file: {error}"

        match = re.match(r"^(?:delete|remove)\s+(?:the\s+)?file\s+(.+)$", text, re.I)
        if match:
            try:
                path = self._safe_user_path(match.group(1))
                if not path.exists() or not path.is_file():
                    return True, f"File not found: {path}"
                self._send_to_recycle_bin(path)
                return True, f"Moved to the Recycle Bin: {path.name}"
            except Exception as error:
                return True, f"Could not delete the file: {error}"

        match = re.match(r"^rename\s+(?:the\s+)?file\s+(.+?)\s+to\s+(.+)$", text, re.I)
        if match:
            try:
                source = self._safe_user_path(match.group(1))
                destination = self._safe_user_path(match.group(2))
                if not source.exists() or not source.is_file():
                    return True, f"File not found: {source}"
                if destination.exists():
                    return True, f"Destination already exists: {destination}"
                destination.parent.mkdir(parents=True, exist_ok=True)
                source.rename(destination)
                return True, f"Renamed {source.name} to {destination.name}."
            except Exception as error:
                return True, f"Could not rename the file: {error}"

        for verb in ("copy", "move"):
            match = re.match(rf"^{verb}\s+(?:the\s+)?file\s+(.+?)\s+to\s+(.+)$", text, re.I)
            if match:
                try:
                    source = self._safe_user_path(match.group(1))
                    destination = self._safe_user_path(match.group(2))
                    if not source.exists() or not source.is_file():
                        return True, f"File not found: {source}"
                    if destination.exists():
                        return True, f"Destination already exists: {destination}"
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if verb == "copy":
                        shutil.copy2(source, destination)
                    else:
                        shutil.move(str(source), str(destination))
                    return True, f"{verb.title()}ed {source.name} to {destination}."
                except Exception as error:
                    return True, f"Could not {verb} the file: {error}"

        return False, ""

    @staticmethod
    def _send_to_recycle_bin(path: Path) -> None:
        if os.name != "nt":
            raise RuntimeError("Recycle Bin support is currently available only on Windows.")

        import ctypes.wintypes as wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", wintypes.UINT),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", wintypes.LPVOID),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        FOF_SILENT = 0x0004
        FOF_NOCONFIRMATION = 0x0010
        FOF_ALLOWUNDO = 0x0040
        FO_DELETE = 0x0003

        source = str(path) + "\0\0"
        operation = SHFILEOPSTRUCTW(
            None,
            FO_DELETE,
            source,
            None,
            FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO,
            False,
            None,
            None,
        )

        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
        if result != 0 or operation.fAnyOperationsAborted:
            raise RuntimeError(f"Windows file operation returned code {result}.")

    @staticmethod
    def _is_mouse_command(command: str) -> bool:
        lower = str(command or "").strip().lower()

        return (
            bool(re.match(r"^(move mouse|move cursor)( to)?\s+-?\d+\s*[, ]\s*-?\d+$", lower))
            or bool(re.match(r"^(move mouse|move cursor)\s+(left|right|up|down)(\s+-?\d+)?$", lower))
            or lower in {
                "click",
                "left click",
                "double click",
                "double-click",
                "right click",
                "right-click",
                "scroll up",
                "scroll down",
            }
            or bool(re.match(r"^(click|left click|double click|double-click|right click|right-click)\s+at\s+-?\d+\s*[, ]\s*-?\d+$", lower))
            or bool(re.match(r"^scroll\s+(up|down)(\s+\d+)?$", lower))
            or bool(re.match(r"^scroll\s+-?\d+$", lower))
        )

    def _execute_mouse(self, command: str) -> tuple[bool, str]:
        lower = str(command or "").strip().lower()

        # Absolute movement
        if lower.startswith("move mouse") or lower.startswith("move cursor"):
            coordinates = MouseController.parse_coordinates(command)
            if coordinates:
                return True, self.mouse.move_to(*coordinates)

            match = re.match(
                r"^(?:move mouse|move cursor)\s+(left|right|up|down)(?:\s+(-?\d+))?$",
                lower,
            )
            if match:
                direction = match.group(1)
                amount = int(match.group(2) or 100)
                dx = dy = 0
                if direction == "left":
                    dx = -amount
                elif direction == "right":
                    dx = amount
                elif direction == "up":
                    dy = -amount
                else:
                    dy = amount
                return True, self.mouse.move_relative(dx, dy)

        coordinate_action = re.match(
            r"^(click|left click|double click|double-click|right click|right-click)\s+at\s+(.+)$",
            command,
            re.I,
        )
        if coordinate_action:
            action = coordinate_action.group(1).lower()
            coordinates = MouseController.parse_coordinates(coordinate_action.group(2))
            if not coordinates:
                return True, "Use coordinates like: click at 500, 300."

            self.mouse.move_to(*coordinates)

            if action in {"double click", "double-click"}:
                return True, self.mouse.double_click()
            if action in {"right click", "right-click"}:
                return True, self.mouse.right_click()
            return True, self.mouse.click()

        if lower in {"click", "left click"}:
            return True, self.mouse.click()

        if lower in {"double click", "double-click"}:
            return True, self.mouse.double_click()

        if lower in {"right click", "right-click"}:
            return True, self.mouse.right_click()

        match = re.match(r"^scroll\s+(up|down)(?:\s+(\d+))?$", lower)
        if match:
            amount = int(match.group(2) or 1)
            if match.group(1) == "down":
                amount = -amount
            return True, self.mouse.scroll(amount)

        match = re.match(r"^scroll\s+(-?\d+)$", lower)
        if match:
            return True, self.mouse.scroll(int(match.group(1)))

        return False, ""

    def _is_natural_language_command(self, command: str) -> bool:
        """
        Detect multi-step natural-language PC requests.

        Supported examples:
        - NEXUS, open VS Code and open my NEXUS project.
        - Open Chrome and search for Python tutorials.
        - Open Downloads and show me the latest file.
        """
        text = str(command or "").strip()
        text = re.sub(r"^nexus[\s,:-]+", "", text, flags=re.I).strip()
        lower = text.lower()

        if " and " in lower:
            return True

        return bool(
            re.match(
                r"^(?:open|launch|start)\s+(?:my|the)\s+nexus\s+project\s*$",
                text,
                re.I,
            )
            or re.match(
                r"^show\s+(?:me\s+)?(?:the\s+)?latest\s+file\s*$",
                text,
                re.I,
            )
        )

    def _split_natural_steps(self, command: str) -> list[str]:
        """
        Split a multi-action command only when 'and' introduces
        another recognizable action, avoiding splits such as
        'search for cats and dogs'.
        """
        pattern = re.compile(
            r"\s+and\s+(?="
            r"open\b|launch\b|start\b|run\b|go\s+to\b|goto\b|visit\b|"
            r"search\b|look\s+up\b|look\s+for\b|navigate\b|"
            r"type\b|write\b|press\b|click\b|double[- ]click\b|"
            r"right[- ]click\b|scroll\b|show\b|focus\b|switch\b"
            r")",
            re.I,
        )
        return [part.strip() for part in pattern.split(command) if part.strip()]

    def _execute_natural_language(self, command: str) -> tuple[bool, str]:
        text = str(command or "").strip()
        text = re.sub(r"^nexus[\s,:-]+", "", text, flags=re.I).strip()

        # Direct natural-language NEXUS project request.
        if re.match(
            r"^(?:open|launch|start)\s+(?:my|the)\s+nexus\s+project\s*$",
            text,
            re.I,
        ):
            return True, self._open_project_in_vscode(str(self._nexus_project_path()))

        # "show me the latest file" uses the most recently opened local folder.
        if re.match(
            r"^show\s+(?:me\s+)?(?:the\s+)?latest\s+file\s*$",
            text,
            re.I,
        ):
            return True, self._show_latest_file()

        steps = self._split_natural_steps(text)

        if len(steps) < 2:
            return False, ""

        results = []

        for step in steps:
            # Context-aware shorthand: after "open VS Code", interpret
            # "open my NEXUS project" as the current NEXUS project.
            if re.match(
                r"^(?:open|launch|start)\s+(?:my|the)\s+nexus\s+project\s*$",
                step,
                re.I,
            ):
                response = self._open_project_in_vscode(
                    str(self._nexus_project_path())
                )
            elif re.match(
                r"^show\s+(?:me\s+)?(?:the\s+)?latest\s+file\s*$",
                step,
                re.I,
            ):
                response = self._show_latest_file()
            else:
                handled, response = self.execute(step)
                if not handled:
                    return False, ""

            results.append(response)

        return True, " ".join(results)

    @staticmethod
    def _nexus_project_path() -> Path:
        return Path(__file__).resolve().parent.parent

    def _show_latest_file(self) -> str:
        folder = Path(self.last_folder_path) if self.last_folder_path else Path.home() / "Downloads"

        if not folder.exists() or not folder.is_dir():
            return f"I couldn't access the folder: {folder}"

        files = [item for item in folder.iterdir() if item.is_file()]

        if not files:
            return f"There are no files in {folder.name or folder}."

        latest = max(files, key=lambda item: item.stat().st_mtime)

        try:
            subprocess.Popen(
                ["explorer.exe", "/select,", str(latest)],
                close_fds=True,
            )
            return f"Latest file: {latest.name}"
        except Exception as error:
            return f"Could not show the latest file: {error}"

    def _is_application_action(self, command: str) -> bool:
        """Return True for Phase 5E application-specific actions."""
        text = str(command or "").strip()
        lower = text.lower()

        if any(lower.startswith(prefix) for prefix in self.BROWSER_NAV_PREFIXES):
            return len(text.split(None, 3)) >= 4

        if any(lower.startswith(prefix) for prefix in self.EXPLORER_NAV_PREFIXES):
            return len(text.split(None, 3)) >= 4

        if re.match(r"^open\s+project\s+.+\s+in\s+vs\s*code\s*$", text, re.I):
            return True

        if re.match(r"^open\s+.+\s+in\s+vs\s*code\s*$", text, re.I):
            return True

        if re.match(r"^(?:open|launch|start)\s+project\s+.+$", text, re.I):
            return True

        if re.match(r"^(?:type|write)\s+.+\s+in\s+notepad\s*$", text, re.I):
            return True

        return False

    @staticmethod
    def _strip_wrapping_quotes(value: str) -> str:
        value = str(value or "").strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            return value[1:-1].strip()
        return value

    @staticmethod
    def _normalize_url(value: str) -> str:
        value = PCController._strip_wrapping_quotes(value)
        if re.match(r"^[a-z][a-z0-9+.-]*://", value, re.I):
            return value
        if value.lower().startswith("www."):
            return f"https://{value}"
        return f"https://{value}"

    def _execute_application_action(self, command: str) -> tuple[bool, str]:
        """Handle application-aware actions without enabling arbitrary commands."""
        text = str(command or "").strip()
        lower = text.lower()

        # VS Code: open a project/folder.
        match = re.match(
            r"^open\s+project\s+(.+?)(?:\s+in\s+vs\s*code)?\s*$",
            text,
            re.I,
        )
        if match:
            project_path = self._strip_wrapping_quotes(match.group(1))
            return True, self._open_project_in_vscode(project_path)

        match = re.match(
            r"^open\s+(.+?)\s+in\s+vs\s*code\s*$",
            text,
            re.I,
        )
        if match:
            project_path = self._strip_wrapping_quotes(match.group(1))
            return True, self._open_project_in_vscode(project_path)

        # Browser navigation.
        for prefix in self.BROWSER_NAV_PREFIXES:
            if lower.startswith(prefix):
                target = text[len(prefix):].strip()
                if not target:
                    return True, "Tell me which website you want the browser to open."
                url = self._normalize_url(target)
                try:
                    webbrowser.open_new_tab(url)
                    return True, f"Browser navigated to {url}."
                except Exception as error:
                    return True, f"Could not navigate the browser: {error}"

        # File Explorer navigation.
        for prefix in self.EXPLORER_NAV_PREFIXES:
            if lower.startswith(prefix):
                target = self._strip_wrapping_quotes(text[len(prefix):].strip())
                return True, self._navigate_file_explorer(target)

        # Notepad-specific typing.
        match = re.match(r"^(?:type|write)\s+(.+?)\s+in\s+notepad\s*$", text, re.I)
        if match:
            content = self._strip_wrapping_quotes(match.group(1))
            try:
                switched = self.window.switch_to("notepad")
                if switched.lower().startswith("i couldn't"):
                    return True, "Notepad is not open. Use 'open Notepad' first."
                time.sleep(0.15)
                return True, self.keyboard.type_text(content)
            except Exception as error:
                return True, f"Could not type into Notepad: {error}"

        return False, ""

    def _open_project_in_vscode(self, project_path: str) -> str:
        """Open an existing folder/project in Visual Studio Code."""
        path = Path(os.path.expandvars(os.path.expanduser(project_path))).resolve()

        if not path.exists():
            return f"The project path does not exist: {project_path}"

        if path.is_file():
            target = str(path)
        else:
            target = str(path)

        candidates = [
            shutil.which("code"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft VS Code\Code.exe"),
        ]

        for candidate in candidates:
            if not candidate:
                continue

            try:
                process = subprocess.Popen([candidate, target], close_fds=True)
                self.last_process_id = process.pid
                time.sleep(0.5)
                try:
                    self.window.switch_to("Visual Studio Code")
                except Exception:
                    pass
                return f"Opened {path.name if path.name else path} in Visual Studio Code."
            except FileNotFoundError:
                continue
            except Exception as error:
                return f"Could not open the project in Visual Studio Code: {error}"

        return (
            "Visual Studio Code was not found. "
            "Install it or add the 'code' command to PATH."
        )

    def _navigate_file_explorer(self, target: str) -> str:
        """Navigate File Explorer to a safe local folder/path."""
        if not target:
            return "Tell me which folder File Explorer should open."

        normalized = target.lower()
        if normalized in self.FOLDER_ALIASES:
            path = self.FOLDER_ALIASES[normalized]
        else:
            path = Path(os.path.expandvars(os.path.expanduser(target))).resolve()

        if not path.exists():
            return f"The path does not exist: {target}"

        if path.is_file():
            path = path.parent

        try:
            subprocess.Popen(["explorer.exe", str(path)], close_fds=True)
            self.last_folder_path = path
            time.sleep(0.3)
            try:
                self.window.switch_to(path.name or "File Explorer")
            except Exception:
                pass
            return f"File Explorer navigated to {path}."
        except Exception as error:
            return f"Could not navigate File Explorer: {error}"

    def _open_target(self, target: str) -> str:
        normalized = target.lower()

        if normalized in self.APP_ALIASES:
            return self._launch_application(normalized)

        if normalized in self.FOLDER_ALIASES:
            return self._open_folder(normalized)

        if normalized in self.WEBSITE_ALIASES:
            webbrowser.open(self.WEBSITE_ALIASES[normalized])
            return f"Opened {target}."

        if normalized in {"visual studio code", "vs code", "vscode", "code"}:
            return self._launch_vscode()

        if normalized in {"chrome", "google chrome"}:
            return self._launch_chrome()

        if normalized in {"microsoft edge", "edge"}:
            return self._launch_edge()

        if normalized in {"windows settings", "settings"}:
            try:
                os.startfile("ms-settings:")
                return "Opened Windows Settings."
            except Exception as error:
                return f"Could not open Windows Settings: {error}"

        if normalized in {"this pc", "computer"}:
            try:
                subprocess.Popen(["explorer.exe", "shell:MyComputerFolder"])
                return "Opened This PC."
            except Exception as error:
                return f"Could not open This PC: {error}"

        if self._looks_like_url(target):
            url = (
                target
                if re.match(r"^[a-z][a-z0-9+.-]*://", target, re.I)
                else f"https://{target}"
            )
            webbrowser.open(url)
            return f"Opened {url}."

        return (
            f"I don't have a safe PC action for '{target}' yet. "
            "Try 'open Calculator', 'open VS Code', 'open Documents', "
            "or 'open github.com'."
        )

    def _open_destination(self, target: str) -> str:
        normalized = target.lower()

        if normalized in self.WEBSITE_ALIASES:
            webbrowser.open(self.WEBSITE_ALIASES[normalized])
            return f"Opened {target}."

        if normalized in self.FOLDER_ALIASES:
            return self._open_folder(normalized)

        if normalized in {"settings", "windows settings"}:
            try:
                os.startfile("ms-settings:")
                return "Opened Windows Settings."
            except Exception as error:
                return f"Could not open Windows Settings: {error}"

        if self._looks_like_url(target):
            url = (
                target
                if re.match(r"^[a-z][a-z0-9+.-]*://", target, re.I)
                else f"https://{target}"
            )
            webbrowser.open(url)
            return f"Opened {url}."

        if "." in target and " " not in target:
            url = f"https://{target}"
            webbrowser.open(url)
            return f"Opened {url}."

        return (
            f"I couldn't determine where '{target}' should open. "
            "Use a website such as github.com or a folder such as Documents."
        )

    def _open_folder(self, alias: str) -> str:
        path = self.FOLDER_ALIASES.get(alias.lower())

        if path is None:
            return f"I don't know that folder: {alias}."

        try:
            path = Path(path)

            if not path.exists():
                return f"The {alias} folder does not exist on this PC."

            os.startfile(str(path))
            self.last_folder_path = path
            return f"Opened {alias}."
        except Exception as error:
            return f"Could not open {alias}: {error}"

    def _launch_application(self, alias: str) -> str:
        commands = self.APP_ALIASES.get(alias)

        if not commands:
            return f"I don't know how to launch {alias} safely yet."

        for executable in commands:
            try:
                process = subprocess.Popen([executable], close_fds=True)
                self.last_process_id = process.pid
                self._focus_last_target()
                return f"Launched {alias}."
            except FileNotFoundError:
                continue
            except Exception as error:
                return f"Could not launch {alias}: {error}"

        return f"{alias.title()} is not available on this PC."

    def _launch_vscode(self) -> str:
        candidates = [
            shutil.which("code"),
            os.path.expandvars(
                r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"
            ),
            os.path.expandvars(r"%ProgramFiles%\Microsoft VS Code\Code.exe"),
        ]

        for candidate in candidates:
            if not candidate:
                continue

            try:
                process = subprocess.Popen([candidate], close_fds=True)
                self.last_process_id = process.pid
                self._focus_last_target()
                return "Launched Visual Studio Code."
            except FileNotFoundError:
                continue
            except Exception as error:
                return f"Could not launch Visual Studio Code: {error}"

        return (
            "Visual Studio Code was not found. "
            "Install it or add the 'code' command to PATH."
        )

    def _launch_chrome(self, url: str | None = None) -> str:
        candidates = [
            shutil.which("chrome"),
            os.path.expandvars(
                r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"
            ),
            os.path.expandvars(
                r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
            ),
            os.path.expandvars(
                r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
            ),
        ]

        for candidate in candidates:
            if not candidate:
                continue

            try:
                command = [candidate]
                if url:
                    command.append(url)

                process = subprocess.Popen(command, close_fds=True)
                self.last_process_id = process.pid
                self.last_browser = "chrome"
                self._focus_last_target()
                return "Launched Google Chrome." if not url else f"Searching the web in Chrome for: {url.split('q=', 1)[-1]}"
            except FileNotFoundError:
                continue
            except Exception as error:
                return f"Could not launch Google Chrome: {error}"

        return "Google Chrome was not found on this PC."

    def _launch_edge(self, url: str | None = None) -> str:
        candidates = [
            shutil.which("msedge"),
            os.path.expandvars(
                r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
            ),
            os.path.expandvars(
                r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
            ),
        ]

        for candidate in candidates:
            if not candidate:
                continue

            try:
                command = [candidate]
                if url:
                    command.append(url)

                process = subprocess.Popen(command, close_fds=True)
                self.last_process_id = process.pid
                self.last_browser = "edge"
                self._focus_last_target()
                return "Launched Microsoft Edge." if not url else f"Searching the web in Edge for: {url.split('q=', 1)[-1]}"
            except FileNotFoundError:
                continue
            except Exception as error:
                return f"Could not launch Microsoft Edge: {error}"

        return "Microsoft Edge was not found on this PC."

    def _focus_last_target(self) -> bool:
        """Return keyboard focus to the last external app controlled by NEXUS."""
        if not self.last_process_id:
            return False

        try:
            return self.window.focus_process(self.last_process_id)
        except Exception:
            return False

    @staticmethod
    def _looks_like_url(value: str) -> bool:
        value = str(value or "").strip()
        return bool(
            re.match(r"^(https?://|www\.)", value, re.I)
            or (("." in value) and (" " not in value))
        )

    @staticmethod
    def _show_desktop() -> None:
        """Use Win+D through the Windows API without a third-party dependency."""
        import ctypes

        user32 = ctypes.windll.user32

        VK_LWIN = 0x5B
        VK_D = 0x44
        KEYEVENTF_KEYUP = 0x0002

        user32.keybd_event(VK_LWIN, 0, 0, 0)
        user32.keybd_event(VK_D, 0, 0, 0)
        user32.keybd_event(VK_D, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)
