"""Compatibility shim.

The NEXUS stylesheet is generated from colour tokens in :mod:`ui.theme`, which supports
light and dark themes and a custom accent colour. ``DARK_THEME`` / ``LIGHT_THEME`` are
built on first use (fonts can only be queried once a QApplication exists).
"""
from ui.theme import stylesheet_for


def __getattr__(name):
    if name == "DARK_THEME":
        return stylesheet_for("dark")
    if name == "LIGHT_THEME":
        return stylesheet_for("light")
    raise AttributeError(name)
