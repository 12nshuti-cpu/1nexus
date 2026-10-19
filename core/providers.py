"""Modular AI provider interface for NEXUS.

Separates online (Gemini) and local (Ollama) providers behind a common
contract so the UI and conversation engine remain provider-agnostic.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generator, List, Optional

import requests

from config import settings
from config.settings import NEXUSSettings


@dataclass
class ProviderResult:
    text: str
    provider: str
    model: str
    is_fallback: bool = False


class AIProvider(ABC):
    """Common contract for all AI backends."""

    name: str

    @abstractmethod
    def is_available(self) -> tuple[bool, str]:
        """Return (available, reason)."""

    @abstractmethod
    def generate(self, messages: list[dict], **kwargs) -> str:
        """Generate a complete response (non-streaming)."""

    def stream(self, messages: list[dict], **kwargs) -> Generator[str, None, None]:
        """Optional streaming; default falls back to generate."""
        yield self.generate(messages, **kwargs)

    @abstractmethod
    def model_name(self) -> str:
        """Return the active model identifier."""


class OllamaProvider(AIProvider):
    """Local Ollama provider - works offline when Ollama is installed."""

    name = "ollama"

    def __init__(self, settings_obj: NEXUSSettings | None = None):
        self.cfg = settings_obj or NEXUSSettings()
        self.url = settings.OLLAMA_CHAT_URL
        self.session = requests.Session()
        self.session.trust_env = False

    def model_name(self) -> str:
        return str(self.cfg.ai_model or settings.NEXUS_MODEL).strip()

    def is_available(self) -> tuple[bool, str]:
        try:
            resp = requests.get(settings.OLLAMA_TAGS_URL, timeout=2)
            if resp.ok:
                return True, f"Ollama reachable at {settings.OLLAMA_BASE_URL}"
            return False, f"Ollama returned HTTP {resp.status_code}"
        except requests.RequestException as e:
            return False, f"Ollama not reachable: {e}"

    def _payload(self, messages, model=None, stream=False, **opts):
        chosen = str(model or self.model_name())
        return {
            "model": chosen,
            "messages": messages,
            "stream": stream,
            "keep_alive": settings.MODEL_KEEP_ALIVE,
            "options": {
                "temperature": opts.get("temperature", settings.MODEL_TEMPERATURE),
                "top_p": settings.MODEL_TOP_P,
                "top_k": settings.MODEL_TOP_K,
                "repeat_penalty": settings.MODEL_REPEAT_PENALTY,
                "num_ctx": settings.MODEL_CONTEXT,
                "num_predict": opts.get("num_predict", settings.MODEL_NUM_PREDICT),
            },
        }

    def generate(self, messages, **kwargs) -> str:
        payload = self._payload(messages, stream=False, **kwargs)
        try:
            resp = self.session.post(self.url, json=payload, timeout=(3.0, kwargs.get("timeout", 120)))
            resp.raise_for_status()
            data = resp.json()
            answer = data.get("message", {}).get("content", "") or data.get("response", "")
            return _clean(answer)
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError("Ollama is not running. Start Ollama and ensure the NEXUS model is installed.") from e
        except requests.exceptions.Timeout as e:
            raise RuntimeError("Ollama took too long to respond.") from e
        except requests.exceptions.HTTPError as e:
            try:
                detail = resp.json()
            except Exception:
                detail = getattr(resp, "text", str(e))
            raise RuntimeError(f"Ollama error: {detail}") from e

    def stream(self, messages, **kwargs) -> Generator[str, None, None]:
        payload = self._payload(messages, stream=True, **kwargs)
        resp = None
        try:
            resp = self.session.post(self.url, json=payload, timeout=(3.0, kwargs.get("timeout", 120)))
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except (TypeError, json.JSONDecodeError):
                    continue
                if item.get("error"):
                    raise RuntimeError(str(item["error"]))
                token = (item.get("message") or {}).get("content", "") or item.get("response", "")
                if token:
                    yield str(token)
                if item.get("done"):
                    break
        finally:
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass

    def list_models(self) -> list[str]:
        try:
            resp = requests.get(settings.OLLAMA_TAGS_URL, timeout=5)
            resp.raise_for_status()
            return [str(m.get("name", "")).strip() for m in resp.json().get("models", [])]
        except Exception:
            return []


class GeminiProvider(AIProvider):
    """Online Google Gemini provider."""

    name = "gemini"

    def __init__(self, settings_obj: NEXUSSettings | None = None):
        self.cfg = settings_obj or NEXUSSettings()

    def model_name(self) -> str:
        return str(self.cfg.gemini_text_model or settings.GEMINI_TEXT_MODEL).strip()

    def is_available(self) -> tuple[bool, str]:
        from core.gemini_engine import gemini_is_configured
        if gemini_is_configured():
            return True, f"Gemini configured (model: {self.model_name()})"
        return False, "Gemini API key not configured. Add it in Settings."

    def generate(self, messages, **kwargs) -> str:
        from core.gemini_engine import generate_text, gemini_is_configured, GeminiUnavailable
        if not gemini_is_configured():
            raise GeminiUnavailable("Gemini API key not configured.")
        # Convert Ollama-style messages to Gemini prompt
        # Gemini engine handles conversation formatting
        system = kwargs.get("system_prompt") or settings.load_system_prompt()
        # Flatten messages to last user prompt + history
        if not messages:
            raise ValueError("No messages provided")
        last_user = ""
        history = []
        for m in messages:
            if m.get("role") == "user":
                # keep previous as history, last as current
                if history or last_user:
                    # push previous user if exists
                    pass
                # We accumulate; simpler: all but last are history
                history.append(m)
            elif m.get("role") == "assistant":
                history.append(m)
        # Last user message is the actual prompt
        user_messages = [m for m in messages if m.get("role") == "user"]
        if user_messages:
            last_user = user_messages[-1].get("content", "")
            # history = all messages except last user
            idx = len(messages) - 1 - next(i for i, m in enumerate(reversed(messages)) if m.get("role") == "user")
            # Simpler: history = messages[:-1] if last is user else messages
            if messages[-1].get("role") == "user":
                history = messages[:-1]
            else:
                history = messages
        else:
            last_user = messages[-1].get("content", "") if messages else ""
            history = messages[:-1]

        return generate_text(last_user, history, system, self.model_name())


def _clean(text: str) -> str:
    """Remove tool markers and trim."""
    if not text:
        return ""
    # Remove NEXUS_TOOL markers that should not be shown to user
    text = re.sub(r"<NEXUS_TOOL>.*?</NEXUS_TOOL>", "", text, flags=re.DOTALL)
    return text.strip()


class ProviderRegistry:
    """Selects and routes to the appropriate provider based on settings and availability."""

    def __init__(self, settings_obj: NEXUSSettings | None = None):
        self.cfg = settings_obj or NEXUSSettings()
        self.ollama = OllamaProvider(self.cfg)
        self.gemini = GeminiProvider(self.cfg)

    def select(self, message: str = "", prefer_online: bool | None = None) -> AIProvider:
        """Choose provider based on engine setting and message type."""
        engine = self.cfg.ai_engine  # automatic | online | local
        if engine == "local":
            return self.ollama
        if engine == "online":
            avail, _ = self.gemini.is_available()
            return self.gemini if avail else self.ollama

        # automatic
        # If prefer_online explicitly set, honor it
        from core.ai import AIService as _AIS  # to reuse heuristics
        # Reuse existing logic: local tools stay local
        # We instantiate a lightweight check
        if prefer_online is not None:
            if prefer_online:
                avail, _ = self.gemini.is_available()
                return self.gemini if avail else self.ollama
            return self.ollama

        # Heuristic: use local for system/tool commands
        tmp = _AIS()
        # Reuse its private methods via instance (they are stateless regarding provider)
        if tmp._requires_local_tools(message):
            return self.ollama
        if message and tmp._prefer_online(message):
            avail, _ = self.gemini.is_available()
            if avail:
                return self.gemini
        return self.ollama

    def status_summary(self) -> dict:
        ollama_ok, ollama_msg = self.ollama.is_available()
        gemini_ok, gemini_msg = self.gemini.is_available()
        return {
            "engine": self.cfg.ai_engine,
            "ollama": {"available": ollama_ok, "detail": ollama_msg, "model": self.ollama.model_name()},
            "gemini": {"available": gemini_ok, "detail": gemini_msg, "model": self.gemini.model_name()},
        }
