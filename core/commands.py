from datetime import datetime
import platform

from core.system_monitor import SystemMonitor
from core.ai import AIService
from core.pc_control import PCController
from core.shell_executor import ShellExecutor
from config.settings import APP_VERSION
from core.assistant import AssistantEngine


class CommandEngine:

    NEXUS_OPEN_COMMANDS = {
        "open nexus",
        "open up nexus",
        "open nexus up",
        "start nexus",
        "launch nexus",
        "show nexus",
        "bring up nexus",
        "bring nexus up",
        "open",
        "open up",
    }

    def __init__(self):
        # The assistant layer (reminders, memory, calculator, ...) owns persistent
        # stores and a pending-confirmation state, so it survives
        # reload_configuration().
        self.assistant = AssistantEngine()
        self.ai = self._new_ai()
        self.pc = PCController()
        self.shell = ShellExecutor()

    def _new_ai(self):
        ai = AIService()
        ai.memory_provider = self.assistant.memory_context
        return ai

    def is_assistant_command(self, command):
        return self.assistant.can_handle(command)

    def is_shell_command(self, command):
        return self.shell.is_shell_command(command)

    def execute_shell(self, command):
        request = self.shell.prepare(command)
        if request is None:
            return "Not a shell command."

        result = self.shell.run(request)
        return self.shell.format_result(result, max_chars=30000)

    def reload_configuration(self):
        """Reload services so newly saved NEXUS settings take effect."""
        self.ai = self._new_ai()
        self.shell = ShellExecutor()

    def shell_requires_confirmation(self, command):
        """Return True when a shell command is marked as risk-sensitive."""
        return bool(
            self.shell.settings.confirm_risky_commands
            and self.shell.is_risky(command)
        )

    def is_pc_command(self, command):
        """Return True when the command belongs to the local PC-control layer."""
        command_lower = str(command or "").strip().lower()
        if command_lower in self.NEXUS_OPEN_COMMANDS:
            return True
        if self.is_shell_command(command):
            return True
        if self.is_assistant_command(command):
            return True
        return self.pc.can_handle(command)

    def execute(self, command):
        command = command.strip()

        if not command:
            return "Please enter a command."

        command_lower = command.lower()

        # NEXUS itself is handled above the normal PC application layer.
        if command_lower in self.NEXUS_OPEN_COMMANDS:
            return "__OPEN_NEXUS__"

        # Reminders, memory, calculator, units, diagnostics, date/time. These run
        # through the validated tool registry and report real outcomes.
        assistant_reply = self.assistant.handle(command)
        if assistant_reply is not None:
            return assistant_reply

        if self.is_shell_command(command) and not self.pc.can_handle(command):
            if self.shell.settings.confirm_risky_commands and self.shell.is_risky(command):
                return (
                    "This shell command is marked as risk-sensitive. "
                    "Run it from the desktop Assistant so NEXUS can ask for confirmation."
                )
            return self.execute_shell(command)

        # ---------------------------------------------------------
        # PHASE 5: PC CONTROL
        # ---------------------------------------------------------

        handled, response = self.pc.execute(command)

        if handled:
            return response

        # ---------------------------------------------------------
        # Built-in NEXUS commands
        # ---------------------------------------------------------

        if command_lower == "help":
            return self.help()

        if command_lower == "status":
            return self.status()

        if command_lower == "system":
            return self.system()

        if command_lower == "battery":
            return self.battery()

        if command_lower == "time":
            return self.time()

        if command_lower == "about":
            return self.about()

        if command_lower == "new":
            self.ai.clear_conversation()
            return "New conversation started."

        if command_lower == "clear":
            return "__CLEAR__"

        # Everything else goes to the local AI
        return self.ai.ask(command)

    def help(self):
        return (
            "## Available Commands\n\n"
            "| Command | Description |\n"
            "|---|---|\n"
            "| `help` | Show available commands |\n"
            "| `status` | Show system status |\n"
            "| `system` | Show computer information |\n"
            "| `battery` | Show battery status |\n"
            "| `time` | Show current time |\n"
            "| `about` | About Nexus |\n"
            "| `new` | Start a new AI conversation |\n"
            "| `clear` | Clear the activity console |\n\n"
            "### NEXUS Activation\n\n"
            "| Example | Action |\n"
            "|---|---|\n"
            "| `open NEXUS` | Bring the NEXUS window to the foreground |\n"
            "| `launch NEXUS` | Bring NEXUS to the foreground |\n"
            "| `start NEXUS` | Bring NEXUS to the foreground |\n\n"
            "### Voice Wake\n\n"
            "Say `Hey NEXUS`, `Hey NEXUS open`, `NEXUS open up`, or `open`. The wake phrase is detected locally; the actual command is sent to online speech recognition.\n\n"
            "### PC Control\n\n"
            "| Example | Action |\n"
            "|---|---|\n"
            "| `open Calculator` | Launch Calculator |\n"
            "| `open VS Code` | Launch Visual Studio Code |\n"
            "| `open Chrome` | Launch Google Chrome |\n"
            "| `open Documents` | Open Documents folder |\n"
            "| `open Downloads` | Open Downloads folder |\n"
            "| `open github.com` | Open GitHub |\n"
            "| `go to youtube.com` | Open YouTube in the browser |\n"
            "| `search for Python tutorials` | Search the web |\n"
            "| `show desktop` | Show the Windows desktop |\n\n"
            "| `minimize this window` | Minimize the active window |\n"
            "| `maximize this window` | Maximize the active window |\n"
            "| `restore this window` | Restore the active window |\n"
            "| `close this window` | Close the active window |\n"
            "| `switch to Chrome` | Switch to an open Chrome window |\n"
            "| `switch to VS Code` | Switch to an open VS Code window |\n"
            "| `focus Notepad` | Focus an open Notepad window |\n\n"
            "| `type hello world` | Type text into the active application |\n"
            "| `press enter` | Press Enter |\n"
            "| `press escape` | Press Escape |\n"
            "| `press tab` | Press Tab |\n"
            "| `press ctrl+c` | Copy selected content |\n"
            "| `press ctrl+v` | Paste copied content |\n"
            "| `press ctrl+s` | Save the current document |\n"
            "| `press alt+tab` | Switch between applications |\n\n"
            "### Shell execution\n\n"
            "Use `run ...`, `execute ...`, `powershell ...`, `cmd ...`, `terminal ...`, or `shell ...` "
            "for explicit Windows command execution. You can also ask NEXUS natural-language questions "
            "that require real Windows information; the AI can use the Windows tool when enabled in Settings. "
            "Risk-sensitive commands are blocked until explicitly confirmed."
        )

    def status(self):
        info = SystemMonitor.get_system_info()

        return (
            "## SYSTEM STATUS\n\n"
            "| Metric | Value |\n"
            "|---|---:|\n"
            f"| CPU | {info['cpu']:.1f}% |\n"
            f"| Memory | {info['memory']:.1f}% |\n"
            f"| Storage | {info['disk']:.1f}% |"
        )

    def system(self):
        return (
            "## SYSTEM INFORMATION\n\n"
            "| Field | Value |\n"
            "|---|---|\n"
            f"| OS | {platform.system()} |\n"
            f"| Version | {platform.version()} |\n"
            f"| Machine | {platform.machine()} |\n"
            f"| Processor | {platform.processor()} |"
        )

    def battery(self):
        battery = SystemMonitor.get_battery()

        if battery is None:
            return "Battery information is unavailable."

        charging = "Charging" if battery["charging"] else "Not charging"

        return (
            "## BATTERY\n\n"
            "| Metric | Value |\n"
            "|---|---:|\n"
            f"| Level | {battery['percent']:.1f}% |\n"
            f"| Status | {charging} |"
        )

    def time(self):
        current_time = datetime.now().strftime("%H:%M:%S")
        return "## CURRENT TIME\n\n" f"{current_time}"

    def about(self):
        return (
            "## ABOUT Nexus\n\n"
            "| Field | Value |\n"
            "|---|---|\n"
            "| Type | Personal Digital Command Center |\n"
            f"| Version | {APP_VERSION} |\n\n"
            "Nexus is being built as a modular desktop and online assistant."
        )
