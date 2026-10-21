from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import requests

from config import settings as app_settings
from config.settings import NEXUSSettings


@dataclass(slots=True)
class CheckResult:
    name: str
    success: bool
    details: str
    required: bool = True


class NEXUSSystemChecker:
    """Startup checks that follow the user's chosen AI mode.

    * **Local** - Ollama and the configured model are required.
    * **Online** - a Gemini API key is required; Ollama is optional.
    * **Automatic** - at least one AI backend must be usable. Ollama is required
      only when no Gemini key is configured.

    Microphone, speech output and similar checks are always optional, and a
    failing check never permanently blocks the application (see the dialog).
    """

    BASE_MODEL = app_settings.BASE_MODEL

    def __init__(self, settings: NEXUSSettings | None = None, http_get=None):
        self.base_dir = Path(app_settings.RESOURCE_ROOT)
        self.settings = settings or NEXUSSettings()
        self._get = http_get or requests.get

    # ------------------------------------------------------------------ helpers
    @property
    def ollama_url(self) -> str:
        return app_settings.OLLAMA_BASE_URL

    @staticmethod
    def _gemini_ready() -> bool:
        try:
            from core.gemini_engine import gemini_is_configured

            return bool(gemini_is_configured())
        except Exception:  # noqa: BLE001
            return False

    def local_required(self) -> bool:
        engine = self.settings.ai_engine
        if engine == "local":
            return True
        if engine == "automatic":
            return not self._gemini_ready()
        return False

    def online_required(self) -> bool:
        return self.settings.ai_engine == "online"

    def _configured_model(self) -> str:
        return (self.settings.ai_model or app_settings.NEXUS_MODEL).strip()

    def run_all_checks(self):
        return [
            self.check_application(),
            self.check_ollama(),
            self.check_ollama_model(),
            self.check_nexus_model(),
            self.check_online_ai(),
            self.check_speech_output(),
            self.check_microphone(),
            self.check_database(),
        ]

    # ------------------------------------------------------------------- checks
    def check_application(self):
        try:
            if not self.base_dir.exists():
                return CheckResult("NEXUS application", False, "Application directory was not found.")
            return CheckResult("NEXUS application", True, "Application files are available.")
        except Exception as error:  # noqa: BLE001
            return CheckResult("NEXUS application", False, str(error))

    def check_ollama(self):
        required = self.local_required()
        hint = "" if required else " Local AI is optional with your current settings."
        try:
            response = self._get(self.ollama_url, timeout=2.0)
            if response.ok:
                return CheckResult("Ollama", True, "Ollama is running.", required)
            return CheckResult("Ollama", False, f"Ollama responded with HTTP {response.status_code}.{hint}", required)
        except requests.exceptions.ConnectionError:
            return CheckResult("Ollama", False, "Ollama is not running or is not installed." + hint, required)
        except requests.exceptions.Timeout:
            return CheckResult("Ollama", False, "Ollama did not respond in time." + hint, required)
        except Exception as error:  # noqa: BLE001
            return CheckResult("Ollama", False, f"{error}{hint}", required)

    def _ollama_models(self):
        response = self._get(f"{self.ollama_url}/api/tags", timeout=4.0)
        response.raise_for_status()
        payload = response.json()
        return [str(item.get("name", "")).strip() for item in payload.get("models", [])]

    @staticmethod
    def _has_model(names, wanted: str) -> bool:
        wanted = wanted.lower()
        names = {name.lower() for name in names}
        return wanted in names or f"{wanted}:latest" in names or any(n.startswith(wanted + ":") for n in names)

    def check_ollama_model(self):
        required = self.local_required()
        try:
            if self._has_model(self._ollama_models(), self.BASE_MODEL):
                return CheckResult(self.BASE_MODEL, True, "Base Ollama model is available.", required)
            return CheckResult(
                self.BASE_MODEL, False,
                f"The base Ollama model was not found. Install it with: ollama pull {self.BASE_MODEL}", required,
            )
        except requests.exceptions.RequestException:
            return CheckResult(self.BASE_MODEL, False, "Could not be checked because Ollama is not reachable.", required)
        except Exception as error:  # noqa: BLE001
            return CheckResult(self.BASE_MODEL, False, f"Could not verify the Ollama model: {error}", required)

    def check_nexus_model(self):
        required = self.local_required()
        wanted = self._configured_model()
        try:
            names = self._ollama_models()
            if self._has_model(names, wanted):
                return CheckResult("NEXUS local model", True, f"The configured model '{wanted}' is available.", required)
            modelfile = self.base_dir / "models" / "Modelfile"
            if wanted == app_settings.NEXUS_MODEL and modelfile.is_file():
                return CheckResult(
                    "NEXUS local model", False,
                    "The customized 'nexus' model has not been created yet. After 'ollama pull "
                    f"{self.BASE_MODEL}', run: ollama create nexus -f \"{modelfile}\"", required,
                )
            return CheckResult(
                "NEXUS local model", False,
                f"The configured model '{wanted}' is not installed in Ollama (change it in Settings or run: ollama pull {wanted}).",
                required,
            )
        except requests.exceptions.RequestException:
            return CheckResult("NEXUS local model", False, "Could not be checked because Ollama is not reachable.", required)
        except Exception as error:  # noqa: BLE001
            return CheckResult("NEXUS local model", False, f"Could not verify the NEXUS model: {error}", required)

    def check_online_ai(self):
        required = self.online_required()
        if self._gemini_ready():
            return CheckResult("Online AI (Gemini)", True, "A Gemini API key is configured (no network call was made).", required)
        return CheckResult(
            "Online AI (Gemini)", False,
            "No Gemini API key is configured. Add one in Settings to use online AI and live voice."
            + ("" if required else " Online AI is optional with your current settings."),
            required,
        )

    def check_speech_output(self):
        try:
            from core.speech import SpeechManager

            status = SpeechManager(self.settings).status()
            if status.get("kokoro_installed"):
                return CheckResult("Speech output", True, "Kokoro is installed.", required=False)
            if status.get("fallback_available"):
                return CheckResult(
                    "Speech output", True,
                    "Kokoro is not installed; NEXUS will use the Windows voice. See the Voice guide to install Kokoro.",
                    required=False,
                )
            return CheckResult("Speech output", False, "No speech engine is available. Replies will be text only.", required=False)
        except Exception as error:  # noqa: BLE001
            return CheckResult("Speech output", False, str(error), required=False)

    def check_microphone(self):
        try:
            import sounddevice as sd

            devices = sd.query_devices()
            microphones = [device for device in devices if device.get("max_input_channels", 0) > 0]
            if not microphones:
                return CheckResult("Microphone", False, "No microphone was detected.", required=False)
            return CheckResult("Microphone", True, f"{len(microphones)} microphone device(s) detected.", required=False)
        except Exception as error:  # noqa: BLE001
            return CheckResult("Microphone", False, str(error), required=False)

    def check_database(self):
        try:
            from database.database import Database

            database = Database()
            path = database.db_path
            with database.connect() as connection:
                connection.execute("SELECT 1 FROM conversations LIMIT 1").fetchone()
            return CheckResult("SQLite database", True, f"Database is ready at {path}")
        except Exception as error:  # noqa: BLE001
            return CheckResult("SQLite database", False, str(error))
