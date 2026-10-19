from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

import requests


@dataclass(slots=True)
class CheckResult:
    name: str
    success: bool
    details: str
    required: bool = True


class NEXUSSystemChecker:
    """Startup checks for the current NEXUS architecture.

    Voice checks intentionally use the current online STT/TTS stack and the
    local Faster-Whisper wake detector. There is no Vosk dependency here.
    """

    OLLAMA_URL = "http://127.0.0.1:11434"
    REQUIRED_MODEL = "llama3.1:8b"
    NEXUS_MODEL = "nexus:latest"

    def __init__(self):
        self.base_dir = Path(__file__).resolve().parent.parent

    def run_all_checks(self):
        return [
            self.check_application(),
            self.check_ollama(),
            self.check_ollama_model(),
            self.check_nexus_model(),
            self.check_microphone(),
            self.check_online_voice(),
            self.check_wake_detector(),
            self.check_database(),
        ]

    def check_application(self):
        try:
            if not self.base_dir.exists():
                return CheckResult("NEXUS application", False, "Application directory was not found.")
            return CheckResult("NEXUS application", True, "Application files are available.")
        except Exception as error:
            return CheckResult("NEXUS application", False, str(error))

    def check_ollama(self):
        try:
            response = requests.get(self.OLLAMA_URL, timeout=2.0)
            if response.ok:
                return CheckResult("Ollama", True, "Ollama is running.")
            return CheckResult("Ollama", False, f"Ollama responded with HTTP {response.status_code}.")
        except requests.exceptions.ConnectionError:
            return CheckResult("Ollama", False, "Ollama is not running or is not installed.")
        except requests.exceptions.Timeout:
            return CheckResult("Ollama", False, "Ollama did not respond in time.")
        except Exception as error:
            return CheckResult("Ollama", False, str(error))

    def _ollama_models(self):
        response = requests.get(f"{self.OLLAMA_URL}/api/tags", timeout=4.0)
        response.raise_for_status()
        payload = response.json()
        return [str(item.get("name", "")).strip() for item in payload.get("models", [])]

    def check_ollama_model(self):
        try:
            names = {name.lower() for name in self._ollama_models()}
            wanted = self.REQUIRED_MODEL.lower()
            if wanted in names or any(name.startswith(wanted + ":") for name in names):
                return CheckResult(self.REQUIRED_MODEL, True, "Required Ollama base model is available.")
            return CheckResult(self.REQUIRED_MODEL, False, "The required Ollama base model was not found.")
        except Exception as error:
            return CheckResult(self.REQUIRED_MODEL, False, f"Could not verify the Ollama model: {error}")

    def check_nexus_model(self):
        try:
            names = {name.lower() for name in self._ollama_models()}
            if self.NEXUS_MODEL.lower() in names:
                return CheckResult("NEXUS local model", True, "The customized NEXUS Ollama model is available.")
            modelfile = self.base_dir / "models" / "Modelfile"
            if modelfile.is_file():
                return CheckResult(
                    "NEXUS local model",
                    False,
                    "models/Modelfile is present, but the customized 'nexus' model has not been created yet.",
                )
            return CheckResult("NEXUS local model", False, "models/Modelfile is missing.")
        except Exception as error:
            return CheckResult("NEXUS local model", False, f"Could not verify the NEXUS model: {error}")

    def check_microphone(self):
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            microphones = [device for device in devices if device.get("max_input_channels", 0) > 0]
            if not microphones:
                return CheckResult("Microphone", False, "No microphone was detected.", required=False)
            return CheckResult("Microphone", True, f"{len(microphones)} microphone device(s) detected.", required=False)
        except Exception as error:
            return CheckResult("Microphone", False, str(error), required=False)

    def check_online_voice(self):
        try:
            from core.voice import VoiceService
            if not VoiceService.has_api_key():
                return CheckResult(
                    "Online voice",
                    False,
                    "No OpenAI API key is configured for STT/TTS. Voice can be enabled after a key is added.",
                    required=False,
                )
            return CheckResult(
                "Online voice",
                True,
                "OpenAI voice credentials are configured for speech recognition and speech output.",
                required=False,
            )
        except Exception as error:
            return CheckResult("Online voice", False, str(error), required=False)

    def check_wake_detector(self):
        try:
            from core.wake_detector import WakeWordDetector
            try:
                import faster_whisper  # noqa: F401
            except Exception as error:
                return CheckResult(
                    "Local wake detector",
                    False,
                    f"Faster-Whisper is unavailable: {error}",
                    required=False,
                )
            cache = WakeWordDetector._model_cache_dir()
            return CheckResult(
                "Local wake detector",
                True,
                f"Local wake detection is available; model cache: {cache}",
                required=False,
            )
        except Exception as error:
            return CheckResult("Local wake detector", False, str(error), required=False)

    def check_database(self):
        try:
            from database.database import Database
            database = Database()
            path = database.db_path
            with database.connect() as connection:
                connection.execute("SELECT 1 FROM conversations LIMIT 1").fetchone()
            return CheckResult("SQLite database", True, f"Database is ready at {path}")
        except Exception as error:
            return CheckResult("SQLite database", False, str(error))

