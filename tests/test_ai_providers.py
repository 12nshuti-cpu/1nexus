"""Online (Gemini) and local (Ollama) providers: success and every failure mode, no network."""
import types

import pytest
import requests

from core import ai as ai_module
from core import gemini_engine
from core.connection_tests import check_gemini, check_microphone, check_ollama
from core.gemini_engine import GeminiUnavailable


class FakeAPIError(Exception):
    def __init__(self, code, message="boom key=AIzaSyA1234567890abcdefghijklmnopqrstu"):
        super().__init__(message)
        self.code = code


class FakeClient:
    """Stands in for google.genai.Client; ``script`` is a list of results/exceptions."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.models = types.SimpleNamespace(generate_content=self._generate)

    def _generate(self, **_kwargs):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _reply(text):
    return types.SimpleNamespace(text=text)


@pytest.fixture()
def with_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-1234567890")


@pytest.fixture()
def no_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(gemini_engine.time, "sleep", lambda s: sleeps.append(s))
    return sleeps


def _install(monkeypatch, client):
    monkeypatch.setattr(gemini_engine, "_client", lambda key: client)


# ------------------------------------------------------------- online provider
def test_missing_key_gives_actionable_error(monkeypatch):
    with pytest.raises(GeminiUnavailable, match="API key"):
        gemini_engine.generate_text("hi", [], "sys", "m")


def test_success_returns_text(with_key, monkeypatch):
    client = FakeClient([_reply("  Hello there  ")])
    _install(monkeypatch, client)
    assert gemini_engine.generate_text("hi", [{"role": "user", "content": "a"}], "sys", "m") == "Hello there"
    assert client.calls == 1


def test_auth_failure_not_retried_and_no_secret_leak(with_key, monkeypatch, no_sleep):
    client = FakeClient([FakeAPIError(401), _reply("never")])
    _install(monkeypatch, client)
    with pytest.raises(GeminiUnavailable) as info:
        gemini_engine.generate_text("hi", [], "sys", "m")
    assert client.calls == 1 and no_sleep == []
    assert "rejected the API key" in str(info.value)
    assert "AIza" not in str(info.value)


def test_rate_limit_retried_then_succeeds(with_key, monkeypatch, no_sleep):
    client = FakeClient([FakeAPIError(429), FakeAPIError(503), _reply("ok")])
    _install(monkeypatch, client)
    assert gemini_engine.generate_text("hi", [], "sys", "m") == "ok"
    assert client.calls == 3 and len(no_sleep) == 2


def test_retries_are_bounded_never_infinite(with_key, monkeypatch, no_sleep):
    client = FakeClient([FakeAPIError(503)] * 10)
    _install(monkeypatch, client)
    with pytest.raises(GeminiUnavailable, match="temporarily unavailable"):
        gemini_engine.generate_text("hi", [], "sys", "m")
    assert client.calls == gemini_engine.MAX_ATTEMPTS


def test_rate_limit_message_after_exhaustion(with_key, monkeypatch, no_sleep):
    _install(monkeypatch, FakeClient([FakeAPIError(429)] * 3))
    with pytest.raises(GeminiUnavailable, match="rate limited"):
        gemini_engine.generate_text("hi", [], "sys", "m")


@pytest.mark.parametrize("bad", [_reply(""), _reply(None), _reply("   ")])
def test_empty_or_malformed_response_is_an_error_not_an_answer(with_key, monkeypatch, bad):
    _install(monkeypatch, FakeClient([bad]))
    with pytest.raises(GeminiUnavailable, match="empty response"):
        gemini_engine.generate_text("hi", [], "sys", "m")


def test_blocked_response_whose_text_property_raises(with_key, monkeypatch):
    class Blocked:
        @property
        def text(self):
            raise ValueError("blocked by safety filter")

    _install(monkeypatch, FakeClient([Blocked()]))
    with pytest.raises(GeminiUnavailable, match="empty response"):
        gemini_engine.generate_text("hi", [], "sys", "m")


def test_secrets_in_prompt_are_redacted_before_leaving_the_pc(with_key, monkeypatch):
    sent = {}

    class Spy(FakeClient):
        def _generate(self, **kwargs):
            sent.update(kwargs)
            return _reply("ok")

    client = Spy([])
    client.models = types.SimpleNamespace(generate_content=client._generate)
    _install(monkeypatch, client)
    gemini_engine.generate_text("my key is AIzaSyA1234567890abcdefghijklmnopqrstu", [], "sys", "m")
    text = sent["contents"][-1].parts[0].text
    assert "AIzaSy" not in text and "[redacted secret]" in text


# --------------------------------------------------------------- routing / AIService
@pytest.fixture()
def service(settings):
    return ai_module.AIService()


def test_local_mode_never_calls_cloud(service, settings, monkeypatch):
    settings.ai_engine = "local"
    monkeypatch.setattr(ai_module, "gemini_is_configured", lambda: True)
    monkeypatch.setattr(ai_module, "generate_text", lambda *a, **k: pytest.fail("cloud was called in Local mode"))
    monkeypatch.setattr(service, "_ask_local", lambda m, c=None: "local answer")
    reply = service.ask("research the latest GPUs")
    assert "local answer" in reply and reply.startswith("[LOCAL")


def test_online_mode_uses_cloud_and_labels_it(service, settings, monkeypatch):
    settings.ai_engine = "online"
    monkeypatch.setattr(ai_module, "generate_text", lambda *a, **k: "cloud answer")
    monkeypatch.setattr(service, "_ask_local", lambda m, c=None: pytest.fail("local used unexpectedly"))
    reply = service.ask("hello there")
    assert reply == "[GEMINI: processed online]\n\ncloud answer"


def test_online_failure_with_fallback_says_so(service, settings, monkeypatch):
    settings.ai_engine = "online"
    settings.online_fallback_enabled = True

    def down(*a, **k):
        raise GeminiUnavailable("Gemini is temporarily unavailable. Try again shortly.")

    monkeypatch.setattr(ai_module, "generate_text", down)
    monkeypatch.setattr(service, "_ask_local", lambda m, c=None: "local answer")
    reply = service.ask("hello there")
    assert reply.startswith("[GEMINI UNAVAILABLE: answered locally")
    assert "local answer" in reply


def test_online_failure_without_fallback_raises_clear_error(service, settings, monkeypatch):
    settings.ai_engine = "online"
    settings.online_fallback_enabled = False

    def down(*a, **k):
        raise GeminiUnavailable("Gemini rejected the API key or project access. Check the key and enabled API.")

    monkeypatch.setattr(ai_module, "generate_text", down)
    with pytest.raises(RuntimeError, match="rejected the API key"):
        service.ask("hello there")


def test_both_backends_down_reports_both(service, settings, monkeypatch):
    settings.ai_engine = "online"
    settings.online_fallback_enabled = True
    monkeypatch.setattr(ai_module, "generate_text", lambda *a, **k: (_ for _ in ()).throw(GeminiUnavailable("cloud down")))
    monkeypatch.setattr(service, "_ask_local", lambda m, c=None: (_ for _ in ()).throw(RuntimeError("Ollama is not running.")))
    with pytest.raises(RuntimeError) as info:
        service.ask("hello there")
    assert "cloud down" in str(info.value) and "Ollama is not running" in str(info.value)


def test_windows_tasks_never_leave_the_pc_even_in_online_mode(service, settings, monkeypatch):
    settings.ai_engine = "online"
    monkeypatch.setattr(ai_module, "generate_text", lambda *a, **k: pytest.fail("local task was sent to the cloud"))
    monkeypatch.setattr(service, "_ask_local", lambda m, c=None: "local result")
    assert "LOCAL: Windows tools" in service.ask("what processes are running on my PC")


def test_automatic_mode_stays_local_for_ordinary_chat(service, settings, monkeypatch):
    settings.ai_engine = "automatic"
    monkeypatch.setattr(ai_module, "gemini_is_configured", lambda: True)
    monkeypatch.setattr(ai_module, "generate_text", lambda *a, **k: pytest.fail("cloud used for ordinary chat"))
    monkeypatch.setattr(service, "_ask_local", lambda m, c=None: "local")
    assert service.ask("tell me a joke").startswith("[LOCAL")


def test_empty_message_does_not_call_any_backend(service, monkeypatch):
    monkeypatch.setattr(service, "_ask_local", lambda *a, **k: pytest.fail("called"))
    assert service.ask("   ") == "Please enter a message."


def test_ollama_down_is_a_readable_error(service, monkeypatch):
    def refuse(*a, **k):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(service.session, "post", refuse)
    with pytest.raises(RuntimeError, match="Ollama is not running"):
        service._post({"model": "x"})


def test_ollama_timeout_is_a_readable_error(service, monkeypatch):
    monkeypatch.setattr(service.session, "post", lambda *a, **k: (_ for _ in ()).throw(requests.exceptions.Timeout()))
    with pytest.raises(RuntimeError, match="too long"):
        service._post({"model": "x"})


def test_history_is_bounded(service):
    history = [{"role": "user", "content": "x" * 5000} for _ in range(50)]
    trimmed = service._trim_history(history)
    assert len(trimmed) <= 12 and sum(len(m["content"]) for m in trimmed) <= 18000


# ------------------------------------------------------ explicit connection tests
class _Resp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code}")

    def json(self):
        return self._payload


def test_ollama_check_ok_missing_model_and_down(settings):
    settings.ai_model = "nexus"
    ok = check_ollama(settings, http_get=lambda *a, **k: _Resp({"models": [{"name": "nexus:latest"}]}))
    assert ok.ok
    missing = check_ollama(settings, http_get=lambda *a, **k: _Resp({"models": [{"name": "llama3:8b"}]}))
    assert not missing.ok and "ollama pull nexus" in missing.message

    def down(*a, **k):
        raise requests.exceptions.ConnectionError()

    assert "not running" in check_ollama(settings, http_get=down).message
    garbled = check_ollama(settings, http_get=lambda *a, **k: _Resp(["not", "a", "dict"]))
    assert not garbled.ok


def test_gemini_check_states(settings, monkeypatch):
    assert not check_gemini(settings).ok                            # no key
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-1234567890")
    assert check_gemini(settings, generate=lambda *a: "ready").ok
    assert not check_gemini(settings, generate=lambda *a: "  ").ok

    def reject(*a):
        raise GeminiUnavailable("Gemini rejected the API key or project access.")

    assert "rejected" in check_gemini(settings, generate=reject).message

    def weird(*a):
        raise KeyError("AIzaSyA1234567890abcdefghijklmnopqrstu")

    assert "AIza" not in check_gemini(settings, generate=weird).message


def test_microphone_check_states():
    assert check_microphone(lambda: [{"name": "Mic", "max_input_channels": 1}]).ok
    assert "No microphone" in check_microphone(lambda: [{"name": "Spk", "max_input_channels": 0}]).message

    def broken():
        raise OSError("PortAudio not found")

    assert "could not be queried" in check_microphone(broken).message
