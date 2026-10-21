"""NEXUS design system: colour tokens, light/dark palettes and the application stylesheet.

Every colour in the interface comes from a :class:`Palette`. Widgets never hard-code
colours; they use object names styled here, or ask :func:`current_palette` when they paint.
:class:`ThemeManager` owns the active palette and tells painted widgets when it changes.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QImage, QPainter, QPainterPath, QPen

DEFAULT_ACCENT = "#45d9ff"
THEME_MODES = ("dark", "light", "system")
ACCENT_PRESETS = (
    ("Cyan", "#45d9ff"),
    ("Violet", "#8b7bff"),
    ("Mint", "#34d6a4"),
    ("Coral", "#ff7a6b"),
    ("Amber", "#f5b84a"),
    ("Rose", "#f472b6"),
)

# Voice-state colours are part of the NEXUS identity and stay the same in both themes.
STATE_COLORS = {
    "listening": "#2fe3a5",
    "thinking": "#a48bff",
    "speaking": "#5aa8ff",
}


# ----------------------------------------------------------------------------- colour helpers
def _luminance(color: QColor) -> float:
    def channel(value: float) -> float:
        value /= 255.0
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(color.red()) + 0.7152 * channel(color.green()) + 0.0722 * channel(color.blue())


def contrast(a: QColor, b: QColor) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def mix(a: str | QColor, b: str | QColor, amount: float) -> str:
    """Blend colour ``b`` into ``a`` by ``amount`` (0 = a, 1 = b) and return a hex string."""
    ca, cb = QColor(a), QColor(b)
    t = max(0.0, min(1.0, amount))
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * t),
        round(ca.green() + (cb.green() - ca.green()) * t),
        round(ca.blue() + (cb.blue() - ca.blue()) * t),
    ).name()


def rgba(color: str | QColor, alpha: float) -> str:
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {max(0, min(255, round(alpha * 255)))})"


def _readable_on(background: str, color: QColor, minimum: float = 4.5) -> str:
    """Darken (or lighten) ``color`` until it is readable on ``background``."""
    bg = QColor(background)
    c = QColor(color)
    lighten = _luminance(bg) < 0.4
    for _ in range(24):
        if contrast(c, bg) >= minimum:
            break
        c = c.lighter(108) if lighten else c.darker(112)
    return c.name()


# ----------------------------------------------------------------------------- palette
@dataclass(frozen=True)
class Palette:
    mode: str
    bg: str
    sidebar: str
    surface: str
    surface_2: str
    surface_3: str
    border: str
    border_strong: str
    text: str
    text_2: str
    text_3: str
    accent: str
    accent_text: str
    accent_hover: str
    on_accent: str
    accent_soft: str
    accent_softer: str
    success: str
    warning: str
    danger: str
    danger_soft: str
    code_bg: str
    shadow: str

    @property
    def is_dark(self) -> bool:
        return self.mode == "dark"


def build_palette(mode: str = "dark", accent: str | QColor = DEFAULT_ACCENT) -> Palette:
    accent_color = QColor(accent)
    if not accent_color.isValid():
        accent_color = QColor(DEFAULT_ACCENT)
    a = accent_color.name()
    if mode == "light":
        base = dict(
            mode="light",
            bg="#f4f6fa",
            sidebar="#eceff5",
            surface="#ffffff",
            surface_2="#f2f4f8",
            surface_3="#e6eaf1",
            border="#e1e5ed",
            border_strong="#c9d0dc",
            text="#111827",
            text_2="#4b5565",
            text_3="#7b8597",
            success="#0f9d6e",
            warning="#b7791f",
            danger="#d93b3b",
            code_bg="#f3f5f9",
            shadow="rgba(15, 23, 42, 30)",
        )
        accent_text = _readable_on("#ffffff", accent_color)
        accent_soft = mix("#ffffff", a, 0.14)
        accent_softer = mix("#ffffff", a, 0.07)
        danger_soft = mix("#ffffff", base["danger"], 0.10)
    else:
        base = dict(
            mode="dark",
            bg="#0a0e15",
            sidebar="#0d121b",
            surface="#111825",
            surface_2="#161f2e",
            surface_3="#1c2738",
            border="#1f2a3b",
            border_strong="#2b3850",
            text="#e9eef6",
            text_2="#a3aec2",
            text_3="#6b778d",
            success="#3ddc97",
            warning="#f4c152",
            danger="#ff7676",
            code_bg="#0c121c",
            shadow="rgba(0, 0, 0, 120)",
        )
        accent_text = _readable_on(base["surface"], accent_color)
        accent_soft = mix(base["surface"], a, 0.18)
        accent_softer = mix(base["surface"], a, 0.09)
        danger_soft = mix(base["surface"], base["danger"], 0.14)
    dark_ink, light_ink = QColor("#06121a"), QColor("#ffffff")
    on_accent = "#06121a" if contrast(dark_ink, accent_color) >= contrast(light_ink, accent_color) else "#ffffff"
    hover = accent_color.lighter(112) if base["mode"] == "dark" else accent_color.darker(108)
    return Palette(
        accent=a,
        accent_text=accent_text,
        accent_hover=hover.name(),
        on_accent=on_accent,
        accent_soft=accent_soft,
        accent_softer=accent_softer,
        danger_soft=danger_soft,
        **base,
    )


# ----------------------------------------------------------------------------- generated images
def _asset_dir() -> Path:
    path = Path(tempfile.gettempdir()) / "nexus-ui-assets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save(image: QImage, name: str) -> str:
    target = _asset_dir() / name
    image.save(str(target), "PNG")
    return target.as_posix()


def _canvas(width: int, height: int) -> tuple[QImage, QPainter]:
    image = QImage(width * 2, height * 2, QImage.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(2.0)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    return image, painter


def _switch_image(track: str, knob: str, on: bool, key: str) -> str:
    image, p = _canvas(36, 20)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(track))
    p.drawRoundedRect(QRectF(0, 0, 36, 20), 10, 10)
    p.setBrush(QColor(knob))
    p.drawEllipse(QPointF(26 if on else 10, 10), 7, 7)
    p.end()
    return _save(image, f"switch-{key}.png")


def _chevron_image(color: str, direction: str, key: str) -> str:
    image, p = _canvas(12, 12)
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    path = QPainterPath()
    if direction == "down":
        path.moveTo(3, 4.5)
        path.lineTo(6, 7.5)
        path.lineTo(9, 4.5)
    else:
        path.moveTo(3, 7.5)
        path.lineTo(6, 4.5)
        path.lineTo(9, 7.5)
    p.drawPath(path)
    p.end()
    return _save(image, f"chevron-{direction}-{key}.png")


def _radio_image(border: str, fill: str, on: bool, key: str) -> str:
    image, p = _canvas(18, 18)
    p.setPen(QPen(QColor(fill if on else border), 1.5))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(9, 9), 7.5, 7.5)
    if on:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(fill))
        p.drawEllipse(QPointF(9, 9), 4, 4)
    p.end()
    return _save(image, f"radio-{key}.png")


def _assets(p: Palette) -> dict:
    key = f"{p.mode}-{p.accent.lstrip('#')}"
    return {
        "switch_off": _switch_image(p.surface_3 if p.is_dark else p.border_strong, p.text_3 if p.is_dark else "#ffffff", False, f"off-{key}"),
        "switch_on": _switch_image(p.accent, p.on_accent if p.is_dark else "#ffffff", True, f"on-{key}"),
        "switch_off_disabled": _switch_image(p.surface_2, p.border_strong, False, f"offd-{key}"),
        "switch_on_disabled": _switch_image(p.accent_soft, p.surface, True, f"ond-{key}"),
        "chevron_down": _chevron_image(p.text_2, "down", key),
        "chevron_up": _chevron_image(p.text_2, "up", key),
        "radio_off": _radio_image(p.border_strong, p.accent, False, f"off-{key}"),
        "radio_on": _radio_image(p.border_strong, p.accent, True, f"on-{key}"),
    }


# ----------------------------------------------------------------------------- fonts
def ui_font_family() -> str:
    families = set(QFontDatabase.families())
    for name in ("Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Text", "Helvetica Neue", "Arial"):
        if name in families:
            return name
    return QFont().defaultFamily()


def display_font_family() -> str:
    families = set(QFontDatabase.families())
    for name in ("Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI", "Inter"):
        if name in families:
            return name
    return ui_font_family()


def mono_font_family() -> str:
    families = set(QFontDatabase.families())
    for name in ("Cascadia Code", "Cascadia Mono", "Consolas", "JetBrains Mono", "Menlo", "Courier New"):
        if name in families:
            return name
    return "monospace"


# ----------------------------------------------------------------------------- stylesheet
def build_stylesheet(p: Palette) -> str:
    img = _assets(p)
    font = ui_font_family()
    display = display_font_family()
    mono = mono_font_family()
    selection = rgba(p.accent, 0.35)
    return f"""
* {{ font-family: "{font}"; font-size: 13px; }}
QWidget {{ color: {p.text}; selection-background-color: {selection}; selection-color: {p.text}; }}
QMainWindow, QDialog, QWizard, QMessageBox, QInputDialog, QColorDialog, QFileDialog {{ background: {p.bg}; }}
QWidget#appRoot, QStackedWidget#pageStack {{ background: {p.bg}; }}
QToolTip {{ background: {p.surface_3}; color: {p.text}; border: 1px solid {p.border_strong}; border-radius: 6px; padding: 6px 8px; }}

/* ---------- typography ---------- */
QLabel {{ background: transparent; }}
QLabel#pageTitle {{ font-family: "{display}"; font-size: 24px; font-weight: 600; color: {p.text}; }}
QLabel#pageSubtitle, QLabel#mutedText {{ color: {p.text_2}; }}
QLabel#faintText {{ color: {p.text_3}; font-size: 12px; }}
QLabel#heroGreeting {{ font-family: "{display}"; font-size: 30px; font-weight: 600; color: {p.text}; }}
QLabel#heroSubtitle {{ color: {p.text_2}; font-size: 14px; }}
QLabel#cardTitle {{ color: {p.text}; font-size: 14px; font-weight: 600; }}
QLabel#sectionLabel {{ color: {p.text_3}; font-size: 11px; font-weight: 600; letter-spacing: 0.6px; }}
QLabel#statValue {{ font-family: "{display}"; font-size: 26px; font-weight: 600; color: {p.text}; }}
QLabel#statLabel {{ color: {p.text_2}; font-size: 12px; }}
QLabel#orbCaption {{ color: {p.text_2}; font-size: 13px; }}
QLabel#orbState {{ font-family: "{display}"; font-size: 17px; font-weight: 600; color: {p.text}; }}
QLabel#kbdHint {{ color: {p.text_3}; font-size: 11px; }}
QLabel#linkLabel {{ color: {p.accent_text}; }}
QLabel#errorText {{ color: {p.danger}; }}
QLabel#successText, QLabel#online {{ color: {p.success}; }}
QLabel#emptyTitle {{ font-family: "{display}"; font-size: 16px; font-weight: 600; color: {p.text}; }}
QLabel#emptyBody {{ color: {p.text_2}; }}

/* ---------- surfaces ---------- */
QFrame#card, QFrame#dashboardPanel {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 14px; }}
QFrame#cardFlat {{ background: {p.surface_2}; border: 1px solid {p.border}; border-radius: 12px; }}
QFrame#heroCard {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 20px; }}
QFrame#divider {{ background: {p.border}; border: none; max-height: 1px; min-height: 1px; }}
QFrame#settingsRow {{ background: transparent; border: none; border-top: 1px solid {p.border}; }}
QScrollArea, QScrollArea > QWidget > QWidget#scrollContent {{ background: transparent; border: none; }}
QWidget#scrollContent, QWidget#transparent {{ background: transparent; }}

/* ---------- sidebar ---------- */
QFrame#sidebar {{ background: {p.sidebar}; border: none; border-right: 1px solid {p.border}; }}
QLabel#brandWordmark {{ font-family: "{display}"; font-size: 17px; font-weight: 700; letter-spacing: 3px; color: {p.text}; }}
QLabel#brandTagline {{ color: {p.text_3}; font-size: 11px; }}
QPushButton#navButton {{
    background: transparent; color: {p.text_2}; border: none; border-radius: 9px;
    padding: 8px 10px; text-align: left; font-size: 13px; font-weight: 500;
}}
QPushButton#navButton:hover {{ background: {p.surface_2}; color: {p.text}; }}
QPushButton#navButton:checked {{ background: {p.accent_soft}; color: {p.text}; font-weight: 600; }}
QPushButton#navButton:focus {{ outline: none; border: 1px solid {p.accent}; }}
QPushButton#navButton[collapsed="true"] {{ text-align: center; padding: 8px 0; }}
QLabel#navBadge {{ background: {p.accent}; color: {p.on_accent}; border-radius: 8px; padding: 0 6px; font-size: 10px; font-weight: 700; min-height: 16px; }}
QListWidget#conversationList {{ background: transparent; border: none; outline: none; padding: 0; }}
QListWidget#conversationList::item {{ border-radius: 8px; padding: 0; margin: 1px 0; color: transparent; }}
QListWidget#conversationList::item:hover {{ background: {p.surface_2}; }}
QListWidget#conversationList::item:selected {{ background: {p.surface_3}; }}
QLabel#conversationRowTitle {{ color: {p.text}; font-size: 13px; }}
QLabel#conversationRowStamp {{ color: {p.text_3}; font-size: 11px; }}
QLineEdit#searchInput {{ background: {p.surface_2}; border: 1px solid {p.border}; border-radius: 9px; padding: 6px 10px 6px 30px; color: {p.text}; }}
QLineEdit#searchInput:focus {{ border-color: {p.accent}; }}
QLabel#engineDot[state="ok"] {{ color: {p.success}; }}
QLabel#engineDot[state="warn"] {{ color: {p.warning}; }}

/* ---------- buttons ---------- */
QPushButton {{ background: {p.surface_2}; color: {p.text}; border: 1px solid {p.border}; border-radius: 9px; padding: 7px 14px; font-weight: 500; }}
QPushButton:hover {{ background: {p.surface_3}; border-color: {p.border_strong}; }}
QPushButton:pressed {{ background: {p.border}; }}
QPushButton:disabled {{ color: {p.text_3}; background: {p.surface_2}; border-color: {p.border}; }}
QPushButton:focus {{ outline: none; border-color: {p.accent}; }}
QPushButton#primaryButton, QPushButton#newChatButton, QPushButton#systemContinue {{
    background: {p.accent}; color: {p.on_accent}; border: 1px solid {p.accent}; font-weight: 600;
}}
QPushButton#primaryButton:hover, QPushButton#newChatButton:hover, QPushButton#systemContinue:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
QPushButton#primaryButton:disabled, QPushButton#systemContinue:disabled {{ background: {p.accent_soft}; color: {p.text_3}; border-color: {p.accent_soft}; }}
QPushButton#primaryButton:focus, QPushButton#newChatButton:focus {{ border: 2px solid {p.text}; }}
QPushButton#secondaryButton, QPushButton#systemRetry, QPushButton#systemFix {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border_strong}; }}
QPushButton#secondaryButton:hover, QPushButton#systemRetry:hover, QPushButton#systemFix:hover {{ background: {p.surface_2}; }}
QPushButton#ghostButton {{ background: transparent; border: 1px solid transparent; color: {p.text_2}; padding: 6px 10px; }}
QPushButton#ghostButton:hover {{ background: {p.surface_2}; color: {p.text}; }}
QPushButton#ghostButton:focus {{ border-color: {p.accent}; }}
QPushButton#linkButton {{ background: transparent; border: none; color: {p.accent_text}; padding: 2px 4px; font-weight: 600; }}
QPushButton#linkButton:hover {{ text-decoration: underline; }}
QPushButton#dangerButton {{ background: {p.danger_soft}; color: {p.danger}; border: 1px solid {mix(p.surface, p.danger, 0.35)}; }}
QPushButton#dangerButton:hover {{ background: {mix(p.surface, p.danger, 0.22)}; }}
QPushButton#chip {{ background: {p.surface}; color: {p.text_2}; border: 1px solid {p.border}; border-radius: 16px; padding: 7px 14px; font-weight: 500; }}
QPushButton#chip:hover {{ border-color: {p.accent}; color: {p.text}; background: {p.accent_softer}; }}
QPushButton#segment {{ background: transparent; border: none; border-radius: 7px; color: {p.text_2}; padding: 6px 14px; }}
QPushButton#segment:checked {{ background: {p.surface}; color: {p.text}; font-weight: 600; border: 1px solid {p.border_strong}; }}
QPushButton#segment:hover:!checked {{ color: {p.text}; }}
QFrame#segmented {{ background: {p.surface_2}; border: 1px solid {p.border}; border-radius: 9px; }}
QPushButton#swatch {{ border-radius: 14px; min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; padding: 0; border: 2px solid transparent; }}
QPushButton#swatch:checked {{ border: 2px solid {p.text}; }}

QToolButton#iconButton {{ background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 5px; }}
QToolButton#iconButton:hover {{ background: {p.surface_2}; }}
QToolButton#iconButton:pressed {{ background: {p.surface_3}; }}
QToolButton#iconButton:checked {{ background: {p.accent_soft}; }}
QToolButton#iconButton:focus {{ border-color: {p.accent}; }}
QToolButton#iconButton:disabled {{ background: transparent; }}
QToolButton#sendButton {{ background: {p.accent}; border: none; border-radius: 17px; padding: 0; }}
QToolButton#sendButton:hover {{ background: {p.accent_hover}; }}
QToolButton#sendButton:disabled {{ background: {p.surface_3}; }}
QToolButton#sendButton:focus {{ border: 2px solid {p.text}; }}
QToolButton#micButton {{ background: {p.surface_2}; border: 1px solid {p.border_strong}; border-radius: 17px; padding: 0; }}
QToolButton#micButton:hover {{ background: {p.surface_3}; border-color: {p.accent}; }}
QToolButton#micButton:focus {{ border: 2px solid {p.accent}; }}
QToolButton#micButton[listening="true"] {{ background: {STATE_COLORS["listening"]}; border-color: {STATE_COLORS["listening"]}; }}

/* ---------- inputs ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{
    background: {p.surface}; color: {p.text}; border: 1px solid {p.border_strong}; border-radius: 9px; padding: 7px 10px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {p.accent}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {p.text_3}; background: {p.surface_2}; }}
QLineEdit[readOnly="true"] {{ background: {p.surface_2}; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {{ background: transparent; border: none; width: 18px; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({img["chevron_up"]}); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({img["chevron_down"]}); width: 10px; height: 10px; }}
QComboBox {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border_strong}; border-radius: 9px; padding: 6px 30px 6px 10px; min-height: 20px; }}
QComboBox:hover {{ border-color: {p.text_3}; }}
QComboBox:focus {{ border-color: {p.accent}; }}
QComboBox::drop-down {{ border: none; width: 26px; subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url({img["chevron_down"]}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border_strong}; border-radius: 8px; padding: 4px; outline: none; selection-background-color: {p.accent_soft}; selection-color: {p.text}; }}
QComboBox#compactCombo {{ background: transparent; border: 1px solid transparent; color: {p.text_2}; padding: 4px 24px 4px 8px; }}
QComboBox#compactCombo:hover {{ background: {p.surface_2}; }}
QComboBox#compactCombo:focus {{ border-color: {p.accent}; }}

QCheckBox {{ spacing: 10px; color: {p.text}; background: transparent; }}
QCheckBox::indicator {{ width: 36px; height: 20px; }}
QCheckBox::indicator:unchecked {{ image: url({img["switch_off"]}); }}
QCheckBox::indicator:checked {{ image: url({img["switch_on"]}); }}
QCheckBox::indicator:unchecked:disabled {{ image: url({img["switch_off_disabled"]}); }}
QCheckBox::indicator:checked:disabled {{ image: url({img["switch_on_disabled"]}); }}
QCheckBox:focus {{ outline: none; }}
QRadioButton {{ spacing: 8px; background: transparent; }}
QRadioButton::indicator {{ width: 18px; height: 18px; }}
QRadioButton::indicator:unchecked {{ image: url({img["radio_off"]}); }}
QRadioButton::indicator:checked {{ image: url({img["radio_on"]}); }}

/* ---------- composer ---------- */
QFrame#composer {{ background: {p.surface}; border: 1px solid {p.border_strong}; border-radius: 18px; }}
QFrame#composer[focused="true"] {{ border: 1px solid {p.accent}; }}
QPlainTextEdit#composerInput {{ background: transparent; border: none; padding: 2px 4px; font-size: 14px; color: {p.text}; }}
QFrame#attachmentChip {{ background: {p.surface_2}; border: 1px solid {p.border}; border-radius: 9px; }}

/* ---------- chat ---------- */
QWidget#chatColumn {{ background: transparent; }}
QFrame#userBubble {{ background: {p.accent_soft}; border: none; border-radius: 16px; }}
QLabel#userText {{ color: {p.text}; font-size: 14px; }}
QLabel#assistantText {{ color: {p.text}; font-size: 14px; }}
QLabel#messageMeta {{ color: {p.text_3}; font-size: 11px; }}
QLabel#messageName {{ color: {p.text}; font-size: 13px; font-weight: 600; }}
QFrame#errorBubble {{ background: {p.danger_soft}; border: 1px solid {mix(p.surface, p.danger, 0.35)}; border-radius: 12px; }}
QFrame#voiceBar {{ background: {p.surface}; border: 1px solid {p.border_strong}; border-radius: 14px; }}
QLabel#voiceBarTitle {{ font-weight: 600; color: {p.text}; }}

/* ---------- status pill ---------- */
QLabel#statusPill {{ border-radius: 11px; padding: 3px 10px; font-size: 12px; font-weight: 600; background: {p.surface_2}; color: {p.text_2}; border: 1px solid {p.border}; }}
QLabel#statusPill[state="ready"] {{ color: {p.success}; }}
QLabel#statusPill[state="thinking"], QLabel#statusPill[state="executing"] {{ color: {STATE_COLORS["thinking"]}; border-color: {rgba(STATE_COLORS["thinking"], 0.45)}; }}
QLabel#statusPill[state="listening"] {{ color: {STATE_COLORS["listening"]}; border-color: {rgba(STATE_COLORS["listening"], 0.45)}; }}
QLabel#statusPill[state="speaking"] {{ color: {STATE_COLORS["speaking"]}; border-color: {rgba(STATE_COLORS["speaking"], 0.45)}; }}
QLabel#statusPill[state="error"] {{ color: {p.danger}; background: {p.danger_soft}; border-color: {mix(p.surface, p.danger, 0.35)}; }}
QLabel#badge, QLabel#statusBadge, QLabel#modelBadge {{ background: {p.surface_2}; color: {p.text_2}; border: 1px solid {p.border}; border-radius: 11px; padding: 3px 10px; font-size: 12px; }}

/* ---------- lists & rows ---------- */
QFrame#listRow {{ background: transparent; border: none; border-radius: 10px; }}
QPushButton#homeRow {{ background: transparent; border: none; border-radius: 9px; padding: 0; text-align: left; }}
QPushButton#homeRow:hover {{ background: {p.surface_2}; }}
QPushButton#homeRow:focus {{ border: 1px solid {p.accent}; }}
QFrame#listRow:hover {{ background: {p.surface_2}; }}
QFrame#listRow[done="true"] QLabel#rowTitle {{ color: {p.text_3}; text-decoration: line-through; }}
QLabel#rowTitle {{ color: {p.text}; font-size: 13px; }}
QLabel#rowMeta {{ color: {p.text_3}; font-size: 12px; }}
QLabel#rowMeta[overdue="true"] {{ color: {p.danger}; }}
QListWidget {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; padding: 4px; outline: none; }}
QListWidget::item {{ padding: 8px; border-radius: 7px; }}
QListWidget::item:selected {{ background: {p.accent_soft}; color: {p.text}; }}
QListWidget::item:hover {{ background: {p.surface_2}; }}
QTabWidget::pane {{ border: 1px solid {p.border}; border-radius: 10px; background: {p.surface}; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {p.text_2}; padding: 8px 14px; border: none; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {p.text}; border-bottom: 2px solid {p.accent}; }}
QTabBar::tab:hover {{ color: {p.text}; }}

QProgressBar {{ background: {p.surface_3}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {p.accent}; border-radius: 3px; }}
QProgressBar[level="warn"]::chunk {{ background: {p.warning}; }}
QProgressBar[level="high"]::chunk {{ background: {p.danger}; }}

/* ---------- menus & scrollbars ---------- */
QMenu {{ background: {p.surface}; border: 1px solid {p.border_strong}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 26px 7px 12px; border-radius: 6px; color: {p.text}; }}
QMenu::item:selected {{ background: {p.surface_3}; }}
QMenu::item:disabled {{ color: {p.text_3}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 5px 6px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border_strong}; border-radius: 3px; min-height: 32px; margin: 0 2px; }}
QScrollBar::handle:vertical:hover {{ background: {p.text_3}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p.border_strong}; border-radius: 3px; min-width: 32px; margin: 2px 0; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- toast ---------- */
QFrame#toast {{ background: {p.surface_3}; border: 1px solid {p.border_strong}; border-radius: 12px; }}
QFrame#toast[kind="error"] {{ border-color: {p.danger}; }}
QFrame#toast[kind="success"] {{ border-color: {p.success}; }}
QLabel#toastText {{ color: {p.text}; }}

/* ---------- startup check ---------- */
#systemCheckOverlay {{ background: {rgba(p.bg, 0.92)}; }}
QFrame#systemCheckCard {{ background: {p.surface}; border: 1px solid {p.border_strong}; border-radius: 20px; }}
QLabel#systemBrand {{ color: {p.text}; font-family: "{display}"; font-size: 14px; font-weight: 700; letter-spacing: 3px; }}
QLabel#systemBadge {{ color: {p.text_2}; background: {p.surface_2}; border: 1px solid {p.border}; border-radius: 10px; padding: 4px 10px; font-size: 11px; }}
QLabel#systemTitle {{ color: {p.text}; font-family: "{display}"; font-size: 26px; font-weight: 600; }}
QLabel#systemStatus {{ color: {p.text_2}; font-size: 13px; }}
QFrame#systemLine {{ background: {p.border}; border: none; }}
QScrollArea#systemResultsScroll, QScrollArea#systemResultsScroll QWidget {{ background: transparent; }}
QLabel#checkName {{ color: {p.text}; font-size: 13px; font-weight: 600; }}
QLabel#checkDetails {{ color: {p.text_2}; font-size: 12px; }}
QFrame#checkFrame {{ background: {p.surface_2}; border: 1px solid {p.border}; border-radius: 12px; }}
QLabel#checkStatusGood {{ color: {p.success}; background: {mix(p.surface, p.success, 0.14)}; border-radius: 9px; font-size: 15px; font-weight: 700; }}
QLabel#checkStatusBad {{ color: {p.danger}; background: {p.danger_soft}; border-radius: 9px; font-size: 15px; font-weight: 700; }}
QLabel#checkStatusOptional {{ color: {p.warning}; background: {mix(p.surface, p.warning, 0.14)}; border-radius: 9px; font-size: 15px; font-weight: 700; }}
QLabel#systemHint {{ color: {p.text_3}; font-size: 12px; }}
QLabel#checkAction {{ color: {p.warning}; font-size: 12px; }}

/* ---------- code ---------- */
QPlainTextEdit#logView, QTextEdit#logView {{ font-family: "{mono}"; font-size: 12px; background: {p.code_bg}; }}
"""


# ----------------------------------------------------------------------------- manager
class ThemeManager(QObject):
    """Owns the active palette. Painted widgets connect to :attr:`changed`."""

    changed = Signal(object)
    _instance: "ThemeManager | None" = None

    def __init__(self):
        super().__init__()
        self.mode = "dark"
        self.accent = DEFAULT_ACCENT
        self.palette = build_palette("dark", DEFAULT_ACCENT)
        self._watching_system = False

    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    @staticmethod
    def system_prefers_dark() -> bool:
        app = QGuiApplication.instance()
        try:
            scheme = app.styleHints().colorScheme() if app is not None else None
            if scheme == Qt.ColorScheme.Light:
                return False
            if scheme == Qt.ColorScheme.Dark:
                return True
        except Exception:  # noqa: BLE001 - older Qt or no platform theme
            pass
        return True

    def resolved_mode(self) -> str:
        if self.mode == "system":
            return "dark" if self.system_prefers_dark() else "light"
        return "light" if self.mode == "light" else "dark"

    def configure(self, mode: str | None = None, accent: str | None = None) -> Palette:
        if mode is not None:
            self.mode = mode if mode in THEME_MODES else "dark"
        if accent is not None and QColor(accent).isValid():
            self.accent = QColor(accent).name()
        self.palette = build_palette(self.resolved_mode(), self.accent)
        self._watch_system()
        return self.palette

    def apply(self, app=None, mode: str | None = None, accent: str | None = None) -> Palette:
        palette = self.configure(mode, accent)
        app = app or QGuiApplication.instance()
        if app is not None and hasattr(app, "setStyleSheet"):
            app.setStyleSheet(build_stylesheet(palette))
        self.changed.emit(palette)
        return palette

    def _watch_system(self):
        if self._watching_system:
            return
        app = QGuiApplication.instance()
        try:
            app.styleHints().colorSchemeChanged.connect(self._system_scheme_changed)
            self._watching_system = True
        except Exception:  # noqa: BLE001
            pass

    def _system_scheme_changed(self, *_):
        if self.mode == "system":
            self.apply()


def theme() -> ThemeManager:
    return ThemeManager.instance()


def current_palette() -> Palette:
    return ThemeManager.instance().palette


def stylesheet_for(mode: str = "dark", accent: str = DEFAULT_ACCENT) -> str:
    return build_stylesheet(build_palette(mode, accent))


__all__ = [
    "ACCENT_PRESETS", "DEFAULT_ACCENT", "STATE_COLORS", "THEME_MODES", "Palette", "ThemeManager",
    "build_palette", "build_stylesheet", "contrast", "current_palette", "display_font_family", "mix",
    "mono_font_family", "rgba", "stylesheet_for", "theme", "ui_font_family",
]
