"""Explicit, user-triggered connectivity tests used by the first-run wizard and Settings.

Nothing here runs automatically: every function is called only when the user
presses a "Test" button. Each returns an :class:`Outcome` that states exactly
what was (and was not) verified, so a green result can never be a guess.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import requests

from config import settings as app_settings
from config.settings import NEXUSSettings


@dataclass(frozen=True)
class Outcome:
    ok: bool
    message: str


def check_ollama(settings: NEXUSSettings | None = None, http_get: Callable = requests.get) -> Outcome:
    """Is Ollama running, and is the configured model installed?"""
    settings = settings or NEXUSSettings()
    base = app_settings.OLLAMA_BASE_URL
    try:
        response = http_get(f"{base}/api/tags", timeout=4.0)
        response.raise_for_status()
        names = [str(item.get("name", "")).lower() for item in response.json().get("models", [])]
    except requests.exceptions.ConnectionError:
        return Outcome(False, "Ollama is not running. Install it from https://ollama.com/download and start it, "
                              "or choose Online AI instead.")
    except requests.exceptions.Timeout:
        return Outcome(False, "Ollama did not answer in time.")
    except (requests.exceptions.RequestException, ValueError, AttributeError) as error:
        return Outcome(False, f"Ollama answered, but not as expected: {error}")

    wanted = (settings.ai_model or app_settings.NEXUS_MODEL).lower()
    if wanted in names or f"{wanted}:latest" in names or any(n.startswith(wanted + ":") for n in names):
        return Outcome(True, f"Ollama is running and the model '{wanted}' is installed.")
    return Outcome(False, f"Ollama is running, but the model '{wanted}' is not installed. "
                          f"Run: ollama pull {wanted}   (or pick another model in Settings).")


def check_gemini(settings: NEXUSSettings | None = None, generate: Callable | None = None) -> Outcome:
    """Send one tiny request to Gemini to prove the key and model work (uses a little quota)."""
    settings = settings or NEXUSSettings()
    from core import gemini_engine

    if not gemini_engine.gemini_is_configured():
        return Outcome(False, "No Gemini API key is saved yet.")
    generate = generate or gemini_engine.generate_text
    try:
        answer = generate("Reply with the single word: ready", [], "You are a connection test.", settings.gemini_text_model)
    except gemini_engine.GeminiUnavailable as error:
        return Outcome(False, str(error))
    except Exception as error:  # noqa: BLE001 - SDK errors vary; never leak details such as keys
        return Outcome(False, gemini_engine.redact_secrets(f"Gemini test failed: {type(error).__name__}"))
    text = answer if isinstance(answer, str) else getattr(answer, "text", "") or str(answer or "")
    if not text.strip():
        return Outcome(False, "Gemini answered with an empty response.")
    return Outcome(True, f"Gemini ({settings.gemini_text_model}) responded.")


def check_microphone(query_devices: Callable | None = None) -> Outcome:
    """Is at least one input device present? (This does not record any audio.)"""
    try:
        if query_devices is None:
            import sounddevice as sd

            query_devices = sd.query_devices
        devices = [d for d in query_devices() if d.get("max_input_channels", 0) > 0]
    except Exception as error:  # noqa: BLE001 - PortAudio errors vary by platform
        return Outcome(False, f"The audio system could not be queried: {error}")
    if not devices:
        return Outcome(False, "No microphone was found. Connect one, or check Windows Settings > Privacy > Microphone.")
    names = ", ".join(str(d.get("name", "unnamed")) for d in devices[:3])
    return Outcome(True, f"{len(devices)} microphone(s) found: {names}.")
