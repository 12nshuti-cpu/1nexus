"""Safe arithmetic and unit conversion for NEXUS tools.

Nothing here uses ``eval``/``exec``. Expressions are parsed with :mod:`ast`
and only a small, explicit set of node types, operators and functions is
evaluated, with limits that stop runaway computations (huge exponents,
giant factorials, overlong input).
"""
from __future__ import annotations

import ast
import math
import operator
import re
from dataclasses import dataclass

MAX_EXPRESSION_LENGTH = 200
MAX_ABS_VALUE = 1e100
MAX_EXPONENT = 1000


class MathError(ValueError):
    """A user-facing calculation problem (bad syntax, divide by zero, too large)."""


_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

_CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _factorial(value):
    if value != int(value) or value < 0 or value > 170:
        raise MathError("factorial needs a whole number between 0 and 170.")
    return math.factorial(int(value))


_FUNCTIONS = {
    "sqrt": math.sqrt,
    "sin": lambda x: math.sin(math.radians(x)),
    "cos": lambda x: math.cos(math.radians(x)),
    "tan": lambda x: math.tan(math.radians(x)),
    "asin": lambda x: math.degrees(math.asin(x)),
    "acos": lambda x: math.degrees(math.acos(x)),
    "atan": lambda x: math.degrees(math.atan(x)),
    "log": math.log10,
    "log10": math.log10,
    "log2": math.log2,
    "ln": math.log,
    "exp": math.exp,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "factorial": _factorial,
    "min": min,
    "max": max,
}


def _check(value):
    if isinstance(value, complex):
        raise MathError("That result is not a real number.")
    if isinstance(value, (int, float)) and (
        math.isnan(value) or math.isinf(value) or abs(value) > MAX_ABS_VALUE
    ):
        raise MathError("That number is too large to calculate.")
    return value


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise MathError("Only numbers are allowed in calculations.")
        return _check(node.value)
    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise MathError(f"Unknown name '{node.id}'.")
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise MathError("That operator is not supported.")
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise MathError("That exponent is too large.")
        try:
            return _check(op(left, right))
        except ZeroDivisionError as error:
            raise MathError("Cannot divide by zero.") from error
        except OverflowError as error:
            raise MathError("That number is too large to calculate.") from error
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise MathError("That operator is not supported.")
        return _check(op(_eval(node.operand)))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
            raise MathError("That function is not supported.")
        if node.keywords or len(node.args) > 4:
            raise MathError("Unsupported function arguments.")
        args = [_eval(arg) for arg in node.args]
        try:
            return _check(_FUNCTIONS[node.func.id](*args))
        except MathError:
            raise
        except (ValueError, TypeError, OverflowError) as error:
            raise MathError(f"Cannot compute {node.func.id}() for that input.") from error
    raise MathError("That expression is not supported.")


_PERCENT_OF = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*of\s*", re.IGNORECASE)
_WORD_OPS = (
    (re.compile(r"\bto the power of\b", re.IGNORECASE), "**"),
    (re.compile(r"\bdivided by\b", re.IGNORECASE), "/"),
    (re.compile(r"\bmultiplied by\b", re.IGNORECASE), "*"),
    (re.compile(r"\btimes\b", re.IGNORECASE), "*"),
    (re.compile(r"\bplus\b", re.IGNORECASE), "+"),
    (re.compile(r"\bminus\b", re.IGNORECASE), "-"),
    (re.compile(r"\bmod(?:ulo)?\b", re.IGNORECASE), "%"),
    (re.compile(r"(?<=\d)\s*[x×]\s*(?=\d)"), "*"),
    (re.compile(r"÷"), "/"),
)


def normalize_expression(text: str) -> str:
    value = str(text or "").strip().rstrip("?=.! ").strip()
    value = re.sub(r"^(?:what(?:'s| is)|calculate|compute|calc|how much is|solve)\s+", "", value, flags=re.IGNORECASE)
    value = _PERCENT_OF.sub(lambda m: f"({m.group(1)}/100)*", value)
    for pattern, replacement in _WORD_OPS:
        value = pattern.sub(f" {replacement} " if replacement in {"+", "-", "*", "/", "%", "**"} else replacement, value)
    value = value.replace("^", "**").replace(",", "")
    return re.sub(r"\s+", " ", value).strip()


def calculate(expression: str) -> float | int:
    """Evaluate an arithmetic expression safely."""
    value = normalize_expression(expression)
    if not value:
        raise MathError("Please give me something to calculate.")
    if len(value) > MAX_EXPRESSION_LENGTH:
        raise MathError("That expression is too long.")
    try:
        tree = ast.parse(value, mode="eval")
    except SyntaxError as error:
        raise MathError("I couldn't understand that calculation.") from error
    return _eval(tree)


def format_number(value) -> str:
    if isinstance(value, int):
        return f"{value:,}" if abs(value) >= 10000 else str(value)
    if float(value).is_integer() and abs(value) < 1e15:
        return format_number(int(value))
    text = f"{value:.10g}"
    if "e" in text:
        return text
    return text


# ----------------------------------------------------------------------
# Unit conversion
# ----------------------------------------------------------------------

# category -> {canonical unit: factor to the category's base unit}
_UNITS: dict[str, dict[str, float]] = {
    "length": {  # base: metre
        "mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0,
        "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344,
    },
    "mass": {  # base: kilogram
        "mg": 1e-6, "g": 0.001, "kg": 1.0, "t": 1000.0,
        "oz": 0.028349523125, "lb": 0.45359237, "st": 6.35029318,
    },
    "volume": {  # base: litre
        "ml": 0.001, "l": 1.0, "tsp": 0.00492892159375, "tbsp": 0.01478676478125,
        "floz": 0.0295735295625, "cup": 0.2365882365, "pt": 0.473176473,
        "qt": 0.946352946, "gal": 3.785411784,
    },
    "speed": {  # base: metre/second
        "m/s": 1.0, "km/h": 1 / 3.6, "mph": 0.44704, "kn": 0.514444, "ft/s": 0.3048,
    },
    "time": {  # base: second
        "s": 1.0, "min": 60.0, "h": 3600.0, "d": 86400.0, "wk": 604800.0,
    },
    "data": {  # base: byte (decimal units)
        "b": 1.0, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12,
    },
    "area": {  # base: square metre
        "m2": 1.0, "km2": 1e6, "cm2": 1e-4, "ft2": 0.09290304, "ac": 4046.8564224, "ha": 10000.0,
    },
}
_TEMPERATURE = {"c", "f", "k"}

_ALIASES = {
    "millimeter": "mm", "millimeters": "mm", "millimetre": "mm", "millimetres": "mm",
    "centimeter": "cm", "centimeters": "cm", "centimetre": "cm", "centimetres": "cm",
    "meter": "m", "meters": "m", "metre": "m", "metres": "m",
    "kilometer": "km", "kilometers": "km", "kilometre": "km", "kilometres": "km", "kms": "km",
    "inch": "in", "inches": "in", "foot": "ft", "feet": "ft", "yard": "yd", "yards": "yd",
    "mile": "mi", "miles": "mi",
    "milligram": "mg", "milligrams": "mg", "gram": "g", "grams": "g",
    "kilogram": "kg", "kilograms": "kg", "kilo": "kg", "kilos": "kg",
    "tonne": "t", "tonnes": "t", "ounce": "oz", "ounces": "oz",
    "pound": "lb", "pounds": "lb", "lbs": "lb", "stone": "st",
    "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml",
    "liter": "l", "liters": "l", "litre": "l", "litres": "l",
    "teaspoon": "tsp", "teaspoons": "tsp", "tablespoon": "tbsp", "tablespoons": "tbsp",
    "fluid ounce": "floz", "fluid ounces": "floz", "fl oz": "floz",
    "cups": "cup", "pint": "pt", "pints": "pt", "quart": "qt", "quarts": "qt",
    "gallon": "gal", "gallons": "gal",
    "kph": "km/h", "kmh": "km/h", "kmph": "km/h", "knot": "kn", "knots": "kn",
    "second": "s", "seconds": "s", "sec": "s", "secs": "s",
    "minute": "min", "minutes": "min", "mins": "min",
    "hour": "h", "hours": "h", "hr": "h", "hrs": "h",
    "day": "d", "days": "d", "week": "wk", "weeks": "wk",
    "byte": "b", "bytes": "b", "kilobyte": "kb", "kilobytes": "kb",
    "megabyte": "mb", "megabytes": "mb", "gigabyte": "gb", "gigabytes": "gb",
    "terabyte": "tb", "terabytes": "tb",
    "sq m": "m2", "square meter": "m2", "square meters": "m2", "square metres": "m2",
    "square kilometer": "km2", "square kilometers": "km2", "sq km": "km2",
    "square foot": "ft2", "square feet": "ft2", "sq ft": "ft2",
    "acre": "ac", "acres": "ac", "hectare": "ha", "hectares": "ha",
    "celsius": "c", "centigrade": "c", "°c": "c", "degc": "c",
    "fahrenheit": "f", "°f": "f", "degf": "f",
    "kelvin": "k",
}


def _canonical_unit(name: str) -> str:
    key = re.sub(r"\s+", " ", str(name or "").strip().lower().rstrip(".")).replace("degrees ", "")
    key = _ALIASES.get(key, key)
    return key


def _category(unit: str) -> str | None:
    if unit in _TEMPERATURE:
        return "temperature"
    for category, table in _UNITS.items():
        if unit in table:
            return category
    return None


@dataclass(frozen=True)
class Conversion:
    value: float
    from_unit: str
    to_unit: str
    result: float

    def describe(self) -> str:
        return f"{format_number(self.value)} {self.from_unit} = {format_number(round(self.result, 6))} {self.to_unit}"


def _to_celsius(value: float, unit: str) -> float:
    if unit == "c":
        return value
    if unit == "f":
        return (value - 32) * 5 / 9
    return value - 273.15


def _from_celsius(value: float, unit: str) -> float:
    if unit == "c":
        return value
    if unit == "f":
        return value * 9 / 5 + 32
    return value + 273.15


def convert(value: float, from_unit: str, to_unit: str) -> Conversion:
    source, target = _canonical_unit(from_unit), _canonical_unit(to_unit)
    source_category, target_category = _category(source), _category(target)
    if source_category is None:
        raise MathError(f"I don't know the unit '{from_unit}'.")
    if target_category is None:
        raise MathError(f"I don't know the unit '{to_unit}'.")
    if source_category != target_category:
        raise MathError(f"I can't convert {source_category} to {target_category}.")

    if source_category == "temperature":
        if source == "k" and value < 0 or source == "c" and value < -273.15 or source == "f" and value < -459.67:
            raise MathError("That temperature is below absolute zero.")
        result = _from_celsius(_to_celsius(value, source), target)
    else:
        table = _UNITS[source_category]
        result = value * table[source] / table[target]
    return Conversion(value, source, target, _check(result))


_CONVERT_PATTERNS = (
    re.compile(r"^(?:please\s+)?convert\s+(?P<v>-?[\d.,]+)\s*(?P<a>[^\d]+?)\s+(?:to|into|in)\s+(?P<b>.+)$", re.IGNORECASE),
    re.compile(r"^how many\s+(?P<b>.+?)\s+(?:are\s+)?(?:in|is)\s+(?:a|an)?\s*(?P<v>-?[\d.,]*)\s*(?P<a>[^\d]+)$", re.IGNORECASE),
    re.compile(r"^(?:what(?:'s| is)\s+)?(?P<v>-?[\d.,]+)\s*(?P<a>[^\d]+?)\s+(?:to|into|in)\s+(?P<b>.+)$", re.IGNORECASE),
)


def parse_conversion(text: str) -> Conversion | None:
    """Parse phrases like ``convert 5 km to miles`` or ``how many oz in 2 kg``."""
    value_text = str(text or "").strip().rstrip("?.! ")
    for pattern in _CONVERT_PATTERNS:
        match = pattern.match(value_text)
        if not match:
            continue
        raw = match.group("v").replace(",", "").strip()
        try:
            amount = float(raw) if raw not in {"", "-", "."} else 1.0
        except ValueError:
            continue
        from_unit, to_unit = match.group("a").strip(), match.group("b").strip()
        if _category(_canonical_unit(from_unit)) is None or _category(_canonical_unit(to_unit)) is None:
            continue
        return convert(amount, from_unit, to_unit)
    return None
