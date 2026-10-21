"""Tool registry: validation, permissions, confirmation and honest failures."""
import pytest

from core.tools import Permission, Tool, ToolParam, ToolRegistry


def _registry():
    calls = []

    def echo(text: str, times: int = 1):
        calls.append((text, times))
        return text * times

    def boom():
        raise RuntimeError("disk on fire")

    def risky():
        calls.append("risky")
        return "deleted"

    reg = ToolRegistry()
    reg.register(Tool(
        "echo", "Echo text", echo,
        params=(ToolParam("text", "string", max_length=10),
                ToolParam("times", "integer", required=False, minimum=1, maximum=3, default=1)),
    ))
    reg.register(Tool("boom", "always fails", boom))
    reg.register(Tool("risky", "needs confirm", risky, permission=Permission.SYSTEM, confirm=True,
                      confirm_prompt="Really?"))
    reg.register(Tool("off", "disabled", lambda: "x", unavailable=lambda: "Turned off in Settings."))
    return reg, calls


def test_valid_call_runs_and_coerces_types():
    reg, calls = _registry()
    result = reg.execute("echo", {"text": "ab", "times": "2"})
    assert result.ok and result.output == "abab"
    assert calls == [("ab", 2)]


@pytest.mark.parametrize("args,fragment", [
    ({}, "Missing required argument 'text'"),
    ({"text": "x" * 11}, "too long"),
    ({"text": 5}, "must be text"),
    ({"text": "a", "times": 9}, "at most"),
    ({"text": "a", "times": 0}, "at least"),
    ({"text": "a", "times": True}, "whole number"),
    ({"text": "a", "extra": 1}, "Unexpected argument"),
    ({"text": "a\x00b"}, "invalid characters"),
    ({"text": "   "}, "cannot be empty"),
])
def test_invalid_arguments_are_rejected_without_running(args, fragment):
    reg, calls = _registry()
    result = reg.execute("echo", args)
    assert not result.ok
    assert fragment in result.output
    assert calls == []


def test_unknown_tool_is_reported_not_invented():
    reg, _ = _registry()
    result = reg.execute("format_c_drive", {})
    assert not result.ok and "no tool called" in result.output


def test_handler_exception_becomes_failure_never_success():
    reg, _ = _registry()
    result = reg.execute("boom")
    assert not result.ok
    assert "disk on fire" in result.output


def test_consequential_tool_requires_confirmation():
    reg, calls = _registry()
    first = reg.execute("risky")
    assert not first.ok and first.needs_confirmation and first.output == "Really?"
    assert calls == []  # nothing ran yet
    second = reg.execute("risky", confirmed=True)
    assert second.ok and calls == ["risky"]


def test_unavailable_tool_explains_why():
    reg, _ = _registry()
    result = reg.execute("off")
    assert not result.ok and result.output == "Turned off in Settings."


def test_duplicate_and_bad_names_rejected():
    reg, _ = _registry()
    with pytest.raises(ValueError):
        reg.register(Tool("echo", "dup", lambda: ""))
    with pytest.raises(ValueError):
        reg.register(Tool("bad name!", "x", lambda: ""))


def test_catalogue_lists_every_tool():
    reg, _ = _registry()
    names = {t["name"] for t in reg.describe()}
    assert names == {"echo", "boom", "risky", "off"}


def test_default_registry_has_expected_tools(engine):
    names = set(engine.registry.names())
    assert {"get_datetime", "calculate", "convert_units", "reminder_create", "reminder_list",
            "reminder_complete", "reminder_delete", "reminder_update", "memory_save",
            "memory_list", "memory_delete", "memory_clear", "diagnostics"} <= names
    # No tool exposes a shell, file deletion or arbitrary code execution.
    assert not {n for n in names if "shell" in n or "exec" in n or "eval" in n}
