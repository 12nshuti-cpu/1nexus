from datetime import datetime
import platform

from core.system_monitor import SystemMonitor
from core.ai import AIService
from core.pc_control import PCController
from core.shell_executor import ShellExecutor
from core.tools import ToolRegistry
from config.settings import NEXUSSettings


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
        self.ai = AIService()
        self.pc = PCController()
        self.shell = ShellExecutor()
        self.tools = ToolRegistry()
        self.settings = NEXUSSettings()

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
        self.ai = AIService()
        self.shell = ShellExecutor()
        self.settings = NEXUSSettings()

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
        return self.pc.can_handle(command)

    def execute(self, command):
        command = str(command or "").strip()
        if not command:
            return "Please enter a command."

        command_lower = command.lower()

        # NEXUS itself is handled above the normal PC application layer.
        if command_lower in self.NEXUS_OPEN_COMMANDS:
            return "__OPEN_NEXUS__"

        if self.is_shell_command(command) and not self.pc.can_handle(command):
            if self.shell.settings.confirm_risky_commands and self.shell.is_risky(command):
                return (
                    "This shell command is marked as risk-sensitive. "
                    "Run it from the desktop Assistant so NEXUS can ask for confirmation."
                )
            return self.execute_shell(command)

        # --- Tool registry shortcuts (no AI needed) ---
        handled, tool_result = self.tools.execute_command_shorthand(command)
        if handled:
            return tool_result

        # ---------------------------------------------------------
        # PC CONTROL
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
        if command_lower == "date":
            return self.date()
        if command_lower == "about":
            return self.about()
        if command_lower == "new":
            self.ai.clear_conversation()
            return "New conversation started."
        if command_lower == "clear":
            return "__CLEAR__"

        # Everything else goes to the AI
        return self.ai.ask(command, conversation=[])

    def execute_with_conversation(self, command, conversation=None):
        """Execute with explicit conversation history (used by UI streaming path)."""
        command = str(command or "").strip()
        if not command:
            return "Please enter a command."
        lower = command.lower()
        if lower in self.NEXUS_OPEN_COMMANDS:
            return "__OPEN_NEXUS__"
        if self.is_shell_command(command) and not self.pc.can_handle(command):
            if self.shell.settings.confirm_risky_commands and self.shell.is_risky(command):
                return (
                    "This shell command is marked as risk-sensitive. "
                    "Please confirm in the UI."
                )
            return self.execute_shell(command)
        handled, tool_result = self.tools.execute_command_shorthand(command)
        if handled:
            return tool_result
        handled, response = self.pc.execute(command)
        if handled:
            return response
        # Built-ins handled via execute() would lose conversation, so we check again
        if lower in {"help", "status", "system", "battery", "time", "date", "about", "clear", "new"}:
            return self.execute(command)
        return self.ai.ask(command, conversation=conversation)

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
            "| `date` | Show current date |\n"
            "| `about` | About NEXUS |\n"
            "| `new` | Start a new AI conversation |\n"
            "| `clear` | Clear the activity console |\n\n"
            "### Assistant Tools\n\n"
            "| Example | Action |\n"
            "|---|---|\n"
            "| `what time is it` | Local time |\n"
            "| `calculate 12*7` | Math evaluation |\n"
            "| `5 km to miles` | Unit conversion |\n"
            "| `search for Python tutorials` | Web search |\n"
            "| `open github.com` | Open website |\n"
            "| `remind me to call mom in 10 minutes` | Create reminder |\n"
            "| `list reminders` | Show reminders |\n"
            "| `delete reminder 2` | Delete reminder |\n"
            "| `remember my name is Alex` | Save memory |\n"
            "| `recall` | Show remembered facts |\n"
            "| `system info` | Diagnostics |\n\n"
            "### PC Control\n\n"
            "| Example | Action |\n"
            "|---|---|\n"
            "| `open Calculator` | Launch Calculator |\n"
            "| `open Chrome` | Launch Google Chrome |\n"
            "| `open Documents` | Open Documents folder |\n"
            "| `show desktop` | Show the Windows desktop |\n"
            "| `type hello world` | Type text |\n"
            "| `press enter` | Press Enter |\n"
            "| `press ctrl+c` | Copy |\n\n"
            "### Shell execution\n\n"
            "Use `run ...`, `powershell ...`, `cmd ...`, `terminal ...` for explicit Windows commands. "
            "Risk-sensitive commands require confirmation in Settings."
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
            return "Battery information is unavailable (desktop or no battery sensor)."
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
        return f"## CURRENT TIME\n\n{current_time}\n\n_{datetime.now().strftime('%A, %B %d, %Y')}_"

    def date(self):
        now = datetime.now()
        return f"## TODAY\n\n{now.strftime('%A, %B %d, %Y')} — {now.strftime('%H:%M')}"

    def about(self):
        from config.settings import APP_VERSION
        return (
            "## ABOUT NEXUS\n\n"
            "| Field | Value |\n"
            "|---|---|\n"
            "| Type | Personal Digital Command Center |\n"
            f"| Version | {APP_VERSION} |\n"
            "| Creator | NSHUTI Emmanuel |\n\n"
            "NEXUS is a modular desktop assistant with local AI (Ollama), optional online AI (Gemini), "
            "voice I/O, reminders, and PC control."
        )
