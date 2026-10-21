from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from PySide6.QtCore import QSettings


APP_NAME = "NEXUS"
APP_VERSION = "0.5.0"
APP_PUBLISHER = "NEXUS"
APP_URL = "https://github.com/12nshuti-cpu/1nexus"

# ------------------------------------------------------------
# Paths
# ------------------------------------------------------------

def _resource_root() -> Path:
    """Locate packaged/project resources in both source and PyInstaller builds."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


RESOURCE_ROOT = _resource_root()
CONFIG_DIR = RESOURCE_ROOT / "config"
MODELS_DIR = RESOURCE_ROOT / "models"
MODELFILE_PATH = MODELS_DIR / "Modelfile"
ASSETS_DIR = RESOURCE_ROOT / "assets"

def _user_data_dir() -> Path:
    override = os.environ.get("NEXUS_DATA_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "NEXUS"
    if os.name == "nt":
        return Path.home() / "AppData" / "Local" / "NEXUS"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "NEXUS"


USER_DATA_DIR = _user_data_dir()
USER_CONFIG_DIR = USER_DATA_DIR / "config"
USER_LOG_DIR = USER_DATA_DIR / "logs"
USER_DB_DIR = USER_DATA_DIR / "data"

for _directory in (USER_CONFIG_DIR, USER_LOG_DIR, USER_DB_DIR):
    try:
        _directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

# ------------------------------------------------------------
# Ollama / local AI
# ------------------------------------------------------------

OLLAMA_BASE_URL = os.environ.get(
    "NEXUS_OLLAMA_URL",
    "http://127.0.0.1:11434",
).rstrip("/")
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"

BASE_MODEL = os.environ.get("NEXUS_BASE_MODEL", "llama3.1:8b")
NEXUS_MODEL = os.environ.get("NEXUS_MODEL", "nexus")

MODEL_TEMPERATURE = float(os.environ.get("NEXUS_TEMPERATURE", "0.7"))
MODEL_TOP_P = float(os.environ.get("NEXUS_TOP_P", "0.9"))
MODEL_TOP_K = int(os.environ.get("NEXUS_TOP_K", "40"))
MODEL_REPEAT_PENALTY = float(os.environ.get("NEXUS_REPEAT_PENALTY", "1.1"))
MODEL_CONTEXT = int(os.environ.get("NEXUS_NUM_CTX", "8192"))
MODEL_NUM_PREDICT = int(os.environ.get("NEXUS_NUM_PREDICT", "768"))
MODEL_KEEP_ALIVE = os.environ.get("NEXUS_KEEP_ALIVE", "30m")

# Gemini is optional. Credentials are read only when an online route is chosen.
GEMINI_TEXT_MODEL = os.environ.get("NEXUS_GEMINI_TEXT_MODEL", "gemini-3.8-flash")
GEMINI_LIVE_MODEL = os.environ.get("NEXUS_GEMINI_LIVE_MODEL", "gemini-3.8-live")
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"

# ------------------------------------------------------------
# Online voice
# ------------------------------------------------------------

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_MODEL_TRANSCRIPTION = os.environ.get("NEXUS_STT_MODEL", "gpt-transcribe")
OPENAI_MODEL_TTS = os.environ.get("NEXUS_TTS_MODEL", "gpt-4o-mini-tts")
OPENAI_TTS_VOICE = os.environ.get("NEXUS_TTS_VOICE", "marin")

# ------------------------------------------------------------
# System / conversation behavior
# ------------------------------------------------------------

MAX_HISTORY_MESSAGES = 12
MAX_HISTORY_CHARS = 18000

DEFAULT_SYSTEM_PROMPT = """You are NEXUS, a capable local Windows desktop AI assistant created by NSHUTI Emmanuel.

Your purpose is to help the user naturally, intelligently, and efficiently.

PERSONALITY
- Speak naturally, like a highly capable personal assistant.
- Be friendly, calm, confident, and conversational.
- Do not sound robotic, repetitive, or unnecessarily formal.
- Do not constantly remind the user that you are an AI.
- Avoid canned openings such as “Certainly” or “As an AI” unless they genuinely fit.
- Understand casual language, incomplete sentences, slang, and typos.
- Adapt your tone to the user's situation.
- Be concise when the request is simple and detailed when the task requires depth.
- Ask a clarifying question only when it is genuinely necessary.
- Your name is NEXUS.
- You are running locally on the user's Windows computer.

REASONING
- Think carefully before answering.
- Break difficult tasks into manageable steps.
- Do not invent facts or actions.
- Clearly distinguish facts from assumptions.
- When solving technical problems, inspect the available information before suggesting changes.
- Prefer practical solutions over unnecessary theory.

PROGRAMMING
- Act as an experienced programming assistant.
- Help debug code systematically and explain why an error occurs.
- Provide complete working code when appropriate.
- Preserve the user's existing architecture unless there is a good reason to change it.
- Consider edge cases, validation, and error handling.

CONVERSATION
- Maintain context throughout the current conversation.
- Resolve references such as “that”, “it”, “this”, and “the previous one” from available context.
- Do not ask the user to repeat information that is already available.

NEXUS BEHAVIOR
- NEXUS is the reasoning and conversational core of a desktop assistant, not merely a chatbot.
- When a real tool result is available, use it instead of pretending to know the result.
- Never claim that you performed an action unless the application actually performed it.
- Never claim to have accessed a file, website, application, device, or system resource unless the application actually provided that information.
- When an action cannot be performed, explain the limitation and provide the most useful alternative.

RESPONSE STYLE
- Use natural language.
- Use Markdown when it improves readability.
- Use bullets for lists and code blocks for code.
- Avoid excessive headings for simple requests.
- Match the complexity of the answer to the user's request.

Your name is NEXUS.
Your creator is NSHUTI Emmanuel.
"""


# ------------------------------------------------------------
# Persistent application settings
# ------------------------------------------------------------

def open_qsettings(organization: str = "NEXUS", application: str = "NEXUS") -> QSettings:
    """The settings store: the Windows registry normally, or an INI file in
    ``NEXUS_SETTINGS_DIR`` when that is set (the test suite sets it so tests can never
    overwrite a real user's preferences)."""
    folder = os.environ.get("NEXUS_SETTINGS_DIR", "").strip()
    if folder:
        Path(folder).mkdir(parents=True, exist_ok=True)
        return QSettings(str(Path(folder) / f"{organization}-{application}.ini"), QSettings.IniFormat)
    return QSettings(organization, application)


class NEXUSSettings:
    """Persistent NEXUS settings used by the UI and core services."""

    ORGANIZATION = "NEXUS"
    APPLICATION = "NEXUS"

    DEFAULTS = {
        "execution_enabled": True,
        "ai_tool_execution_enabled": True,
        "shell": "powershell",
        "confirm_risky_commands": True,
        "working_directory": str(Path.home()),
        "command_timeout": 120,
        "tool_max_iterations": 2,
        "ai_model": NEXUS_MODEL,
        "ai_engine": "automatic",
        "gemini_text_model": GEMINI_TEXT_MODEL,
        "online_fallback_enabled": True,
        "voice_enabled": False,
        "legacy_openai_voice_enabled": False,
        "voice_language": "auto",
        "user_name": "",
        "ui_accent": "#45d9ff",
        "ui_theme": "dark",            # dark | light | system
        "start_with_windows": False,
        # Personalization / privacy
        "personalization_enabled": True,
        "share_memory_with_online": False,
        # Reminders
        "reminder_notifications": True,
        "speak_reminders": True,
        # Onboarding
        "first_run_completed": False,
        # Speech output (Kokoro with a Windows-voice fallback)
        "tts_engine": "auto",
        "kokoro_voice": "af_heart",
        "kokoro_speed": 1.0,
        # Speech input (local faster-whisper)
        "stt_model": "base",
        "microphone_device": "",       # "" = the Windows default input device
        "push_to_talk": False,         # False: stop when you stop talking; True: click again to stop
        # Window / startup behaviour (all opt-in or reversible)
        "startup_greeting": False,
        "close_to_tray": True,
        "start_minimized": False,
        # Resident Ctrl+Alt+N helper process (keeps running after NEXUS exits), so opt-in.
        "global_hotkey_enabled": False,
    }

    def __init__(self):
        self.store = open_qsettings(self.ORGANIZATION, self.APPLICATION)

    def get(self, key: str, default=None):
        if default is None:
            default = self.DEFAULTS.get(key)
        return self.store.value(key, default)

    def set(self, key: str, value) -> None:
        self.store.setValue(key, value)
        self.store.sync()

    def boolean(self, key: str) -> bool:
        value = self.get(key, self.DEFAULTS.get(key, False))
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def integer(self, key: str) -> int:
        value = self.get(key, self.DEFAULTS.get(key, 0))
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(self.DEFAULTS.get(key, 0))

    @property
    def execution_enabled(self) -> bool:
        return self.boolean("execution_enabled")

    @execution_enabled.setter
    def execution_enabled(self, value: bool) -> None:
        self.set("execution_enabled", bool(value))

    @property
    def ai_tool_execution_enabled(self) -> bool:
        return self.boolean("ai_tool_execution_enabled")

    @ai_tool_execution_enabled.setter
    def ai_tool_execution_enabled(self, value: bool) -> None:
        self.set("ai_tool_execution_enabled", bool(value))

    @property
    def shell(self) -> str:
        value = str(self.get("shell", "powershell") or "powershell").lower()
        return value if value in {"powershell", "cmd"} else "powershell"

    @shell.setter
    def shell(self, value: str) -> None:
        value = str(value or "powershell").lower()
        self.set("shell", value if value in {"powershell", "cmd"} else "powershell")

    @property
    def confirm_risky_commands(self) -> bool:
        return self.boolean("confirm_risky_commands")

    @confirm_risky_commands.setter
    def confirm_risky_commands(self, value: bool) -> None:
        self.set("confirm_risky_commands", bool(value))

    @property
    def working_directory(self) -> Path:
        value = str(self.get("working_directory", str(Path.home())) or Path.home())
        path = Path(value).expanduser()
        return path if path.exists() and path.is_dir() else Path.home()

    @working_directory.setter
    def working_directory(self, value) -> None:
        self.set("working_directory", str(Path(value).expanduser()))

    @property
    def command_timeout(self) -> int:
        value = self.integer("command_timeout")
        return max(5, min(600, value))

    @command_timeout.setter
    def command_timeout(self, value: int) -> None:
        self.set("command_timeout", max(5, min(600, int(value))))

    @property
    def tool_max_iterations(self) -> int:
        value = self.integer("tool_max_iterations")
        return max(1, min(3, value))

    @tool_max_iterations.setter
    def tool_max_iterations(self, value: int) -> None:
        self.set("tool_max_iterations", max(1, min(3, int(value))))

    @property
    def ai_model(self) -> str:
        return str(self.get("ai_model", NEXUS_MODEL) or NEXUS_MODEL).strip()

    @ai_model.setter
    def ai_model(self, value: str) -> None:
        value = str(value or NEXUS_MODEL).strip()
        self.set("ai_model", value or NEXUS_MODEL)

    @property
    def ai_engine(self) -> str:
        value = str(self.get("ai_engine", "automatic") or "automatic").strip().lower()
        return value if value in {"automatic", "online", "local"} else "automatic"

    @ai_engine.setter
    def ai_engine(self, value: str) -> None:
        normalized = str(value or "automatic").strip().lower()
        self.set("ai_engine", normalized if normalized in {"automatic", "online", "local"} else "automatic")

    @property
    def gemini_text_model(self) -> str:
        return str(self.get("gemini_text_model", GEMINI_TEXT_MODEL) or GEMINI_TEXT_MODEL).strip()

    @gemini_text_model.setter
    def gemini_text_model(self, value: str) -> None:
        self.set("gemini_text_model", str(value or GEMINI_TEXT_MODEL).strip() or GEMINI_TEXT_MODEL)

    @property
    def online_fallback_enabled(self) -> bool:
        return self.boolean("online_fallback_enabled")

    @online_fallback_enabled.setter
    def online_fallback_enabled(self, value: bool) -> None:
        self.set("online_fallback_enabled", bool(value))

    @property
    def voice_enabled(self) -> bool:
        return self.boolean("voice_enabled")

    @voice_enabled.setter
    def voice_enabled(self, value: bool) -> None:
        self.set("voice_enabled", bool(value))

    @property
    def legacy_openai_voice_enabled(self) -> bool:
        return self.boolean("legacy_openai_voice_enabled")

    @legacy_openai_voice_enabled.setter
    def legacy_openai_voice_enabled(self, value: bool) -> None:
        self.set("legacy_openai_voice_enabled", bool(value))

    @property
    def voice_language(self) -> str:
        return str(self.get("voice_language", "auto") or "auto")

    @voice_language.setter
    def voice_language(self, value: str) -> None:
        self.set("voice_language", str(value or "auto"))

    @property
    def start_with_windows(self) -> bool:
        return self.boolean("start_with_windows")

    @start_with_windows.setter
    def start_with_windows(self, value: bool) -> None:
        self.set("start_with_windows", bool(value))

    # -- personalization / privacy -------------------------------------
    @property
    def personalization_enabled(self) -> bool:
        """Master switch: when off NEXUS neither saves nor uses memories."""
        return self.boolean("personalization_enabled")

    @personalization_enabled.setter
    def personalization_enabled(self, value: bool) -> None:
        self.set("personalization_enabled", bool(value))

    @property
    def share_memory_with_online(self) -> bool:
        """Off by default: saved memories stay on this PC and are not sent to cloud AI."""
        return self.boolean("share_memory_with_online")

    @share_memory_with_online.setter
    def share_memory_with_online(self, value: bool) -> None:
        self.set("share_memory_with_online", bool(value))

    # -- reminders -------------------------------------------------------
    @property
    def reminder_notifications(self) -> bool:
        return self.boolean("reminder_notifications")

    @reminder_notifications.setter
    def reminder_notifications(self, value: bool) -> None:
        self.set("reminder_notifications", bool(value))

    @property
    def speak_reminders(self) -> bool:
        return self.boolean("speak_reminders")

    @speak_reminders.setter
    def speak_reminders(self, value: bool) -> None:
        self.set("speak_reminders", bool(value))

    # -- onboarding --------------------------------------------------------
    @property
    def first_run_completed(self) -> bool:
        return self.boolean("first_run_completed")

    @first_run_completed.setter
    def first_run_completed(self, value: bool) -> None:
        self.set("first_run_completed", bool(value))

    # -- speech output -----------------------------------------------------
    @property
    def tts_engine(self) -> str:
        """auto = Kokoro, then the Windows voice if Kokoro is unavailable."""
        value = str(self.get("tts_engine", "auto") or "auto").strip().lower()
        return value if value in {"auto", "kokoro", "windows"} else "auto"

    @tts_engine.setter
    def tts_engine(self, value: str) -> None:
        value = str(value or "auto").strip().lower()
        self.set("tts_engine", value if value in {"auto", "kokoro", "windows"} else "auto")

    @property
    def kokoro_voice(self) -> str:
        value = str(self.get("kokoro_voice", "af_heart") or "af_heart").strip()
        return value if re.fullmatch(r"[a-z]{2}_[a-z0-9]{2,20}", value) else "af_heart"

    @kokoro_voice.setter
    def kokoro_voice(self, value: str) -> None:
        value = str(value or "af_heart").strip()
        self.set("kokoro_voice", value if re.fullmatch(r"[a-z]{2}_[a-z0-9]{2,20}", value) else "af_heart")

    @property
    def kokoro_speed(self) -> float:
        try:
            value = float(self.get("kokoro_speed", 1.0))
        except (TypeError, ValueError):
            value = 1.0
        return max(0.5, min(2.0, value))

    @kokoro_speed.setter
    def kokoro_speed(self, value: float) -> None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = 1.0
        self.set("kokoro_speed", max(0.5, min(2.0, number)))

    # -- speech input -------------------------------------------------------
    @property
    def stt_model(self) -> str:
        value = str(self.get("stt_model", "base") or "base").strip()
        return value if value in {"tiny", "tiny.en", "base", "base.en", "small", "small.en"} else "base"

    @stt_model.setter
    def stt_model(self, value: str) -> None:
        value = str(value or "base").strip()
        self.set("stt_model", value if value in {"tiny", "tiny.en", "base", "base.en", "small", "small.en"} else "base")

    @property
    def microphone_device(self) -> int | None:
        """Index of the chosen input device, or None for the system default."""
        value = str(self.get("microphone_device", "") or "").strip()
        return int(value) if value.isdigit() else None

    @microphone_device.setter
    def microphone_device(self, value) -> None:
        self.set("microphone_device", "" if value in (None, "") else str(int(value)))

    @property
    def push_to_talk(self) -> bool:
        return self.boolean("push_to_talk")

    @push_to_talk.setter
    def push_to_talk(self, value: bool) -> None:
        self.set("push_to_talk", bool(value))

    # -- window / startup behaviour -------------------------------------------
    @property
    def startup_greeting(self) -> bool:
        return self.boolean("startup_greeting")

    @startup_greeting.setter
    def startup_greeting(self, value: bool) -> None:
        self.set("startup_greeting", bool(value))

    @property
    def close_to_tray(self) -> bool:
        return self.boolean("close_to_tray")

    @close_to_tray.setter
    def close_to_tray(self, value: bool) -> None:
        self.set("close_to_tray", bool(value))

    @property
    def start_minimized(self) -> bool:
        return self.boolean("start_minimized")

    @start_minimized.setter
    def start_minimized(self, value: bool) -> None:
        self.set("start_minimized", bool(value))

    @property
    def global_hotkey_enabled(self) -> bool:
        return self.boolean("global_hotkey_enabled")

    @global_hotkey_enabled.setter
    def global_hotkey_enabled(self, value: bool) -> None:
        self.set("global_hotkey_enabled", bool(value))

    def reset(self) -> None:
        for key in self.DEFAULTS:
            self.store.remove(key)
        self.store.sync()


def load_user_settings() -> dict:
    """Return persisted settings in the dictionary format used by the UI."""
    config = NEXUSSettings()
    return {
        "execution_enabled": config.execution_enabled,
        "ai_tool_execution_enabled": config.ai_tool_execution_enabled,
        "shell": config.shell,
        "confirm_risky_commands": config.confirm_risky_commands,
        "working_directory": str(config.working_directory),
        "command_timeout": config.command_timeout,
        "tool_max_iterations": config.tool_max_iterations,
        "ai_model": config.ai_model,
        "ai_engine": config.ai_engine,
        "gemini_text_model": config.gemini_text_model,
        "online_fallback_enabled": config.online_fallback_enabled,
        "voice_enabled": config.voice_enabled,
        "legacy_openai_voice_enabled": config.legacy_openai_voice_enabled,
        "voice_language": config.voice_language,
        "start_with_windows": config.start_with_windows,
    }


def _extract_system_block(modelfile_text: str) -> str | None:
    """Extract the SYSTEM triple-quoted block from an Ollama Modelfile."""
    match = re.search(r'(?ms)^SYSTEM\s+"""(.*?)"""\s*$', modelfile_text)
    if not match:
        return None
    prompt = match.group(1).strip()
    return prompt or None


def load_system_prompt() -> str:
    """Load the authoritative NEXUS system prompt from models/Modelfile."""
    try:
        text = MODELFILE_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return DEFAULT_SYSTEM_PROMPT

    prompt = _extract_system_block(text)
    return prompt or DEFAULT_SYSTEM_PROMPT
