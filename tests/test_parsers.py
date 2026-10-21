"""Time expressions, reminders sentences, calculator and unit conversion."""
from datetime import datetime, timedelta

import pytest

from core import safe_math
from core.safe_math import MathError
from core.timeparse import describe_due, parse_reminder, parse_time

NOW = datetime(2026, 10, 21, 12, 0, 0)   # a Wednesday, noon


@pytest.mark.parametrize("text,expected", [
    ("in 10 minutes", NOW + timedelta(minutes=10)),
    ("in 2 hours", NOW + timedelta(hours=2)),
    ("in half an hour", NOW + timedelta(minutes=30)),
    ("in 1 day", NOW + timedelta(days=1)),
    ("tomorrow at 9am", datetime(2026, 10, 22, 9, 0)),
    ("tomorrow", datetime(2026, 10, 22, 9, 0)),
    ("at 5pm", datetime(2026, 10, 21, 17, 0)),
    ("at 17:30", datetime(2026, 10, 21, 17, 30)),
    ("at 11am", datetime(2026, 10, 22, 11, 0)),     # already past today -> next occurrence
    ("at noon", datetime(2026, 10, 22, 12, 0)),
    ("next friday at 3pm", datetime(2026, 10, 23, 15, 0)),
    ("on monday at 8", datetime(2026, 10, 26, 8, 0)),
])
def test_parse_time(text, expected):
    assert parse_time(text, NOW).due == expected


@pytest.mark.parametrize("text", ["blah", "in 0 minutes", "at 25:00", ""])
def test_unparseable_times_return_none_not_a_guess(text):
    assert parse_time(text, NOW) is None


@pytest.mark.parametrize("sentence,message,due", [
    ("remind me to call mum in 10 minutes", "call mum", NOW + timedelta(minutes=10)),
    ("remind me to submit the form tomorrow at 9am", "submit the form", datetime(2026, 10, 22, 9, 0)),
    ("remind me at 5pm to stretch", "stretch", datetime(2026, 10, 21, 17, 0)),
])
def test_parse_reminder(sentence, message, due):
    parsed = parse_reminder(sentence, NOW)
    assert (parsed.message, parsed.due) == (message, due)


@pytest.mark.parametrize("sentence", ["remind me", "remind me to", "remind me to call mum", "what time is it"])
def test_reminder_without_message_or_time_is_rejected(sentence):
    assert parse_reminder(sentence, NOW) is None


def test_describe_due():
    assert describe_due(datetime(2026, 10, 21, 17, 30), NOW) == "today at 17:30"
    assert describe_due(datetime(2026, 10, 22, 9, 0), NOW) == "tomorrow at 09:00"
    assert describe_due(datetime(2026, 10, 24, 9, 0), NOW) == "Saturday at 09:00"
    assert describe_due(datetime(2026, 12, 1, 9, 0), NOW) == "Tue 01 Dec at 09:00"


# ----------------------------------------------------------------------- maths
@pytest.mark.parametrize("expression,shown", [
    ("2+3*4", "14"), ("(3+4)*2", "14"), ("sqrt(144)", "12"), ("15% of 80", "12"),
    ("10/4", "2.5"), ("2^10", "1024"), ("1,000+1", "1001"), ("3 x 4", "12"),
    ("10 % 3", "1"), ("abs(-3)", "3"), ("what is 7 plus 8", "15"),
])
def test_calculate(expression, shown):
    assert safe_math.format_number(safe_math.calculate(expression)) == shown


@pytest.mark.parametrize("expression,shown", [("5!", "120"), ("calculate 5!", "120"), ("10!", "3628800"), ("0!", "1")])
def test_factorial_is_not_silently_dropped(expression, shown):
    """Regression: the trailing '!' used to be stripped as punctuation, so 5! gave 5."""
    # format_number groups large integers (10000+) with thousands separators.
    assert safe_math.format_number(safe_math.calculate(expression)).replace(",", "") == shown


@pytest.mark.parametrize("expression,message", [
    ("1/0", "Cannot divide by zero."),
    ("2**10000", "exponent is too large"),
    ("__import__('os').system('x')", "not supported"),
    ("open('/etc/passwd')", "not supported"),
    ("().__class__", "not supported"),
    ("lambda: 1", "not supported"),
    ("'a'*10**9", "Only numbers"),
    ("x + 1", "Unknown name"),
    ("", "something to calculate"),
    ("1+" * 200 + "1", "too long"),
    ("171!", "between 0 and 170"),
])
def test_calculator_refuses_unsafe_or_invalid_input(expression, message):
    with pytest.raises(MathError, match=message):
        safe_math.calculate(expression)


@pytest.mark.parametrize("value,src,dst,expected", [
    (100, "celsius", "fahrenheit", "100 c = 212 f"),
    (1, "gb", "mb", "1 gb = 1000 mb"),
    (10, "km", "miles", "10 km = 6.213712 mi"),
])
def test_unit_conversion(value, src, dst, expected):
    assert safe_math.convert(value, src, dst).describe() == expected


def test_unit_conversion_errors_are_explained():
    with pytest.raises(MathError, match="can't convert length to mass"):
        safe_math.convert(1, "km", "kg")
    with pytest.raises(MathError, match="don't know the unit 'foo'"):
        safe_math.convert(1, "foo", "bar")
