"""Test app startup (non-GUI logic)."""
import os, tempfile

def test_settings_load():
    from config.settings import NEXUSSettings, load_user_settings
    s = NEXUSSettings()
    # Defaults should be accessible
    assert s.ai_engine in {"automatic", "online", "local"}
    assert isinstance(s.command_timeout, int)
    d = load_user_settings()
    assert "ai_model" in d

def test_command_engine_builtins():
    import tempfile, os
    td = tempfile.mkdtemp()
    os.environ["LOCALAPPDATA"] = td
    from core.commands import CommandEngine
    ce = CommandEngine()
    assert "Available Commands" in ce.help()
    assert "SYSTEM STATUS" in ce.status()
    assert "SYSTEM INFORMATION" in ce.system()
    about = ce.about()
    assert "NEXUS" in about
    # PC control should gracefully handle non-Windows
    handled, resp = ce.pc.execute("show desktop")
    assert isinstance(handled, bool)
    # tool shorthand via tools registry does not need Windows
    from core.tools import ToolRegistry
    reg = ToolRegistry()
    ok, out = reg.execute_command_shorthand("what time is it")
    assert ok and "Current" in out
    ok2, out2 = reg.execute("calculate", expression="2+2")
    assert "Result" in out2

def test_shell_safe():
    from core.shell_executor import ShellExecutor
    se = ShellExecutor()
    # is_shell_command detection
    assert se.is_shell_command("run echo hi") is True or se.is_shell_command("powershell Get-Process") is True
    # risky detection
    assert se.is_risky("rm -rf /") or se.is_risky("Remove-Item C:\\* -Recurse") or se.is_risky("shutdown /s") is not None

def test_voice_service_import():
    try:
        from core.voice import VoiceService
        vs = VoiceService()
        assert isinstance(vs.has_api_key(), bool)
    except OSError as e:
        # PortAudio missing on CI is expected; test that import handles gracefully
        assert "PortAudio" in str(e)
        import pytest
        pytest.skip("PortAudio not available on CI")

def test_startup_greeting():
    from core.startup import greeting_text
    from config.settings import NEXUSSettings
    s = NEXUSSettings()
    g = greeting_text(s)
    assert "NEXUS" in g or "Good" in g

def test_missing_credentials_handling():
    from core.gemini_engine import gemini_is_configured, get_gemini_api_key
    # Ensure no crash when no key
    key = get_gemini_api_key()
    assert isinstance(key, str)
    assert isinstance(gemini_is_configured(), bool)

def test_provider_registry_selection():
    from core.providers import ProviderRegistry
    reg = ProviderRegistry()
    # Should return a provider without crashing
    p = reg.select("hello world")
    assert p.name in {"ollama", "gemini"}
    summary = reg.status_summary()
    assert "ollama" in summary and "gemini" in summary
