from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

import requests

from config import settings
from models import BASE_MODEL, MODELFILE_PATH, NEXUS_MODEL


class NexusDependencyManager:
    """Check local Ollama readiness without downloading software or model weights."""

    OLLAMA_SETUP_SCRIPT = "https://ollama.com/install.ps1"

    def __init__(self, status_callback: Optional[Callable[[str], None]] = None):
        self.status_callback = status_callback
        self.ollama_process = None

    def ensure(self) -> tuple[bool, str]:
        try:
            self._status("Checking Ollama installation...")
            ollama = self.find_ollama()

            if ollama is None:
                return False, "Ollama is not installed. Install it manually to enable local AI; NEXUS will not download software or model weights automatically."

            self._status("Checking the Ollama service...")
            if not self.wait_for_server(5.0):
                self.start_ollama_server(ollama)
                if not self.wait_for_server(45.0):
                    return False, "Ollama is installed, but its local service did not start."

            self._status(f"Checking base model {BASE_MODEL}...")
            if not self.model_installed(BASE_MODEL):
                return False, f"The local base model {BASE_MODEL} is missing. Install it manually with Ollama; NEXUS will not download model weights automatically."

            self._status(f"Checking NEXUS model {NEXUS_MODEL}...")
            if not self.model_installed(NEXUS_MODEL):
                return False, f"The NEXUS local model {NEXUS_MODEL} is missing. Restore/build it manually; startup will not pull or replace weights."

            self._status("NEXUS local AI is ready.")
            return True, (
                f"Ollama is ready with {BASE_MODEL} and "
                f"the NEXUS model {NEXUS_MODEL}."
            )
        except Exception as error:  # noqa: BLE001
            return False, str(error)

    # ------------------------------------------------------------
    # Ollama discovery/install
    # ------------------------------------------------------------

    @staticmethod
    def _candidate_paths() -> list[Path]:
        candidates: list[Path] = []
        path_value = shutil.which("ollama")
        if path_value:
            candidates.append(Path(path_value))

        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            base = Path(local_app_data)
            candidates.extend(
                [
                    base / "Programs" / "Ollama" / "ollama.exe",
                    base / "Ollama" / "ollama.exe",
                ]
            )
        return candidates

    @classmethod
    def find_ollama(cls) -> Optional[Path]:
        for candidate in cls._candidate_paths():
            try:
                if candidate.is_file():
                    return candidate
            except OSError:
                continue
        return None

    def install_ollama(self) -> None:
        if os.name != "nt":
            raise RuntimeError("Automatic Ollama installation is currently implemented for Windows.")

        powershell = (
            Path(os.environ.get("SystemRoot", r"C:\Windows"))
            / "System32"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe"
        )
        if not powershell.exists():
            raise RuntimeError("Windows PowerShell could not be located.")

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        command = (
            "$ErrorActionPreference='Stop'; "
            f"irm '{self.OLLAMA_SETUP_SCRIPT}' | iex"
        )
        result = subprocess.run(
            [
                str(powershell),
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            check=False,
            timeout=600,
            creationflags=creation_flags,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError("Ollama installation failed" + (f": {detail[-700:]}" if detail else "."))

        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if self.find_ollama() is not None:
                return
            time.sleep(0.5)
        raise RuntimeError("Ollama installation completed, but ollama.exe was not found.")

    # ------------------------------------------------------------
    # Service
    # ------------------------------------------------------------

    def server_available(self) -> bool:
        try:
            response = requests.get(settings.OLLAMA_TAGS_URL, timeout=2)
            return response.ok
        except requests.RequestException:
            return False

    def wait_for_server(self, timeout: float = 30.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.server_available():
                return True
            time.sleep(0.5)
        return self.server_available()

    def start_ollama_server(self, ollama: Path) -> None:
        if self.server_available():
            return
        self._status("Starting Ollama in the background...")
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.ollama_process = subprocess.Popen(
            [str(ollama), "serve"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )

    # ------------------------------------------------------------
    # Models
    # ------------------------------------------------------------

    @staticmethod
    def _normalized(name: str) -> str:
        value = str(name).strip().lower()
        return value if ":" in value else f"{value}:latest"

    def installed_models(self) -> list[str]:
        try:
            response = requests.get(settings.OLLAMA_TAGS_URL, timeout=5)
            response.raise_for_status()
            payload = response.json()
            return [str(item.get("name", "")).strip() for item in payload.get("models", [])]
        except (requests.RequestException, ValueError, TypeError):
            return []

    def model_installed(self, model_name: str) -> bool:
        target = self._normalized(model_name)
        return any(self._normalized(name) == target for name in self.installed_models())

    def pull_model(self, ollama: Path, model_name: str) -> None:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            [str(ollama), "pull", model_name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation_flags,
        )

        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if line:
                self._status(f"Downloading {model_name}: {line[:140]}")

        return_code = process.wait(timeout=3600)
        if return_code != 0:
            raise RuntimeError(f"Ollama could not download {model_name}. Exit code: {return_code}.")

    def create_nexus_model(self, ollama: Path) -> None:
        if not MODELFILE_PATH.exists():
            raise RuntimeError(f"NEXUS Modelfile not found:\n{MODELFILE_PATH}")

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            [str(ollama), "create", NEXUS_MODEL, "-f", str(MODELFILE_PATH)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation_flags,
        )

        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if line:
                self._status(f"Building NEXUS model: {line[:140]}")

        return_code = process.wait(timeout=3600)
        if return_code != 0:
            raise RuntimeError(
                f"Ollama could not create {NEXUS_MODEL} from the NEXUS Modelfile. "
                f"Exit code: {return_code}."
            )

    def _status(self, message: str) -> None:
        if callable(self.status_callback):
            try:
                self.status_callback(str(message))
            except Exception:
                pass

