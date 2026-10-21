"""Extensible tool registry for NEXUS.

A *tool* is a named capability with a declared, validated argument schema, a
permission level and (optionally) a confirmation requirement. The conversation
engine, voice pipeline or UI never call handlers directly; they go through
:meth:`ToolRegistry.execute`, which

* rejects unknown tools and unknown / missing / wrongly-typed arguments,
* enforces length limits and allowed values,
* refuses consequential tools until the user has confirmed, and
* turns *every* failure into an honest :class:`ToolResult` (``ok=False``) so a
  failure can never be reported as a success.

New capabilities are added by registering another :class:`Tool`; nothing else
needs to change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class Permission(str, Enum):
    READ = "read"            # reads information only
    WRITE = "write"          # changes NEXUS's own data (reminders, memory)
    SYSTEM = "system"        # touches the operating system / files / apps


class ToolError(ValueError):
    """Invalid tool call (unknown tool, bad arguments)."""


@dataclass(frozen=True)
class ToolParam:
    name: str
    type: str = "string"            # string | integer | number | boolean
    description: str = ""
    required: bool = True
    max_length: int = 2000
    choices: Optional[tuple] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    default: Any = None


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    handler: Callable[..., str]
    params: tuple[ToolParam, ...] = ()
    permission: Permission = Permission.READ
    confirm: bool = False
    confirm_prompt: str = ""
    # Returns a reason string when the tool is currently unavailable/disabled.
    unavailable: Optional[Callable[[], Optional[str]]] = None


@dataclass
class ToolResult:
    ok: bool
    output: str
    needs_confirmation: bool = False
    tool: str = ""
    data: dict = field(default_factory=dict)


_TRUE = {"true", "yes", "1", "on"}
_FALSE = {"false", "no", "0", "off"}


def _coerce(param: ToolParam, value: Any) -> Any:
    kind = param.type
    if kind == "string":
        if not isinstance(value, str):
            raise ToolError(f"'{param.name}' must be text.")
        text = value.strip()
        if param.required and not text:
            raise ToolError(f"'{param.name}' cannot be empty.")
        if len(text) > param.max_length:
            raise ToolError(f"'{param.name}' is too long (limit {param.max_length} characters).")
        if "\x00" in text:
            raise ToolError(f"'{param.name}' contains invalid characters.")
        if param.choices is not None and text.lower() not in param.choices:
            raise ToolError(f"'{param.name}' must be one of: {', '.join(param.choices)}.")
        return text.lower() if param.choices is not None else text
    if kind == "integer":
        if isinstance(value, bool):
            raise ToolError(f"'{param.name}' must be a whole number.")
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            value = int(value.strip())
        if not isinstance(value, int):
            raise ToolError(f"'{param.name}' must be a whole number.")
    elif kind == "number":
        if isinstance(value, bool):
            raise ToolError(f"'{param.name}' must be a number.")
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ToolError(f"'{param.name}' must be a number.") from None
    elif kind == "boolean":
        if isinstance(value, str) and value.strip().lower() in _TRUE | _FALSE:
            value = value.strip().lower() in _TRUE
        if not isinstance(value, bool):
            raise ToolError(f"'{param.name}' must be true or false.")
        return value
    else:  # pragma: no cover - programmer error
        raise ToolError(f"Unsupported parameter type '{kind}'.")
    if param.minimum is not None and value < param.minimum:
        raise ToolError(f"'{param.name}' must be at least {param.minimum:g}.")
    if param.maximum is not None and value > param.maximum:
        raise ToolError(f"'{param.name}' must be at most {param.maximum:g}.")
    return value


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    # ------------------------------------------------------------------ registry
    def register(self, tool: Tool) -> Tool:
        if not tool.name or not tool.name.replace("_", "").isalnum():
            raise ValueError(f"Invalid tool name: {tool.name!r}")
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered.")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[str(name)]
        except KeyError:
            raise ToolError(f"There is no tool called '{name}'.") from None

    def names(self) -> list[str]:
        return sorted(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def describe(self) -> list[dict]:
        """Machine-readable catalogue (used for prompts, docs and tests)."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "permission": t.permission.value,
                "confirm": t.confirm,
                "params": [
                    {"name": p.name, "type": p.type, "required": p.required, "description": p.description}
                    for p in t.params
                ],
            }
            for t in (self._tools[n] for n in self.names())
        ]

    # ---------------------------------------------------------------- validation
    def validate(self, name: str, arguments: Optional[dict]) -> dict:
        tool = self.get(name)
        arguments = dict(arguments or {})
        known = {p.name for p in tool.params}
        unknown = sorted(set(arguments) - known)
        if unknown:
            raise ToolError(f"Unexpected argument(s) for {name}: {', '.join(unknown)}.")
        cleaned: dict[str, Any] = {}
        for param in tool.params:
            if param.name in arguments and arguments[param.name] is not None:
                cleaned[param.name] = _coerce(param, arguments[param.name])
            elif param.required:
                raise ToolError(f"Missing required argument '{param.name}'.")
            elif param.default is not None:
                cleaned[param.name] = param.default
        return cleaned

    # ----------------------------------------------------------------- execution
    def execute(self, name: str, arguments: Optional[dict] = None, *, confirmed: bool = False) -> ToolResult:
        try:
            tool = self.get(name)
            cleaned = self.validate(name, arguments)
        except ToolError as error:
            return ToolResult(False, str(error), tool=str(name))

        if tool.unavailable is not None:
            try:
                reason = tool.unavailable()
            except Exception:  # noqa: BLE001
                reason = "This feature is currently unavailable."
            if reason:
                return ToolResult(False, reason, tool=name)

        if tool.confirm and not confirmed:
            return ToolResult(
                False,
                tool.confirm_prompt or f"'{tool.name}' needs your confirmation before it runs.",
                needs_confirmation=True,
                tool=name,
            )

        try:
            output = tool.handler(**cleaned)
        except ToolError as error:
            return ToolResult(False, str(error), tool=name)
        except ValueError as error:  # domain errors raised by stores / parsers
            return ToolResult(False, str(error), tool=name)
        except Exception as error:  # noqa: BLE001 - never crash the UI, never claim success
            return ToolResult(False, f"{tool.name} failed: {type(error).__name__}: {error}", tool=name)
        return ToolResult(True, str(output), tool=name)
