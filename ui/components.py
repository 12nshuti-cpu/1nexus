"""Reusable NEXUS interface components.

Everything here takes its colours from :mod:`ui.theme`, so the same widgets work in the
light and dark themes and repaint when the theme or accent colour changes.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone


from markdown import markdown
from PySide6.QtCore import (
    QByteArray,
    QElapsedTimer,
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QGuiApplication,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QTextCursor,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.theme import STATE_COLORS, current_palette, mix, mono_font_family, theme

VOICE_LANGUAGES = (
    ("auto", "Auto language"),
    ("en", "English"),
    ("fr", "French"),
    ("sw", "Swahili"),
    ("es", "Spanish"),
    ("de", "German"),
    ("it", "Italian"),
    ("pt", "Portuguese"),
    ("rw", "Kinyarwanda"),
)


def repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


# ============================================================================= icons
def _gear_path() -> str:
    points = []
    teeth = 8
    for i in range(teeth * 4):
        angle = (i / (teeth * 4)) * math.tau - math.pi / 2
        radius = 8.6 if (i % 4) in (1, 2) else 6.6
        points.append((12 + radius * math.cos(angle), 12 + radius * math.sin(angle)))
    d = "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in points) + " Z"
    return f'<path d="{d}"/><circle cx="12" cy="12" r="2.8"/>'


_ICONS = {
    "home": '<path d="M3.5 10.5 12 3.8l8.5 6.7"/><path d="M5.5 9v10.5h13V9"/><path d="M10 19.5v-5.5h4v5.5"/>',
    "chat": '<path d="M5 4.5h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-8l-4.5 3.5v-3.5H5a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2z"/>',
    "bell": '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 1.5h-15z"/><path d="M10 20.5a2.2 2.2 0 0 0 4 0"/>',
    "memory": '<path d="M5 18.5V5a1.5 1.5 0 0 1 1.5-1.5H19v14H6.5A1.5 1.5 0 0 0 5 19a1.5 1.5 0 0 0 1.5 1.5H19"/><path d="M9.5 7.5h5.5M9.5 11h3.5"/>',
    "system": '<rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9.5" y="9.5" width="5" height="5" rx="1"/>'
              '<path d="M9.5 3v3M14.5 3v3M9.5 18v3M14.5 18v3M3 9.5h3M3 14.5h3M18 9.5h3M18 14.5h3"/>',
    "activity": '<path d="M3 12h4l2.5-6.5 5 13L17 12h4"/>',
    "settings": _gear_path(),
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
    "mic": '<rect x="9" y="3" width="6" height="11.5" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0"/><path d="M12 17.5V21M8.5 21h7"/>',
    "send": '<path d="M12 19V5M6 11l6-6 6 6"/>',
    "stop": '<rect x="7" y="7" width="10" height="10" rx="2" fill="COLOR"/>',
    "paperclip": '<path d="M20 11.5 12.2 19.3a4.6 4.6 0 0 1-6.5-6.5l7.8-7.8a3.1 3.1 0 0 1 4.4 4.4l-7.6 7.6a1.55 1.55 0 0 1-2.2-2.2l7-7"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>',
    "moon": '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    "trash": '<path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13M10 11v5.5M14 11v5.5"/>',
    "copy": '<rect x="8.5" y="8.5" width="11.5" height="11.5" rx="2"/><path d="M15.5 8.5V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7.5a2 2 0 0 0 2 2h2.5"/>',
    "check": '<path d="M5 12.5 10 17.5 19.5 7"/>',
    "check_circle": '<circle cx="12" cy="12" r="8.5"/><path d="m8.2 12.3 2.6 2.6 5-5.2"/>',
    "circle": '<circle cx="12" cy="12" r="8.5"/>',
    "edit": '<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    "x": '<path d="M6 6l12 12M18 6 6 18"/>',
    "chevron_left": '<path d="M14.5 6 8.5 12l6 6"/>',
    "chevron_right": '<path d="M9.5 6l6 6-6 6"/>',
    "chevron_down": '<path d="M6 9.5l6 6 6-6"/>',
    "sidebar": '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M9.5 4.5v15"/>',
    "volume": '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/>',
    "volume_off": '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M16 9.5l5 5M21 9.5l-5 5"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "refresh": '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4.5v4.5H15"/>',
    "file": '<path d="M14 3.5H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.5z"/><path d="M14 3.5v5h5M9 13h6M9 16.5h4"/>',
    "sparkle": '<path d="M12 3.5c.6 4.2 2.3 5.9 6.5 6.5-4.2.6-5.9 2.3-6.5 6.5-.6-4.2-2.3-5.9-6.5-6.5 4.2-.6 5.9-2.3 6.5-6.5z"/>'
               '<path d="M18.5 15.5c.25 1.6.9 2.25 2.5 2.5-1.6.25-2.25.9-2.5 2.5-.25-1.6-.9-2.25-2.5-2.5 1.6-.25 2.25-.9 2.5-2.5z"/>',
    "more": '<circle cx="6" cy="12" r="1.3" fill="COLOR"/><circle cx="12" cy="12" r="1.3" fill="COLOR"/><circle cx="18" cy="12" r="1.3" fill="COLOR"/>',
    "battery": '<rect x="3" y="7.5" width="16" height="9" rx="2"/><path d="M21.5 10.5v3M6.5 10.5v3"/>',
    "storage": '<ellipse cx="12" cy="6.5" rx="7.5" ry="3"/><path d="M4.5 6.5v11c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-11"/><path d="M4.5 12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3"/>',
    "ram": '<rect x="3" y="7" width="18" height="10" rx="1.5"/><path d="M7 10.5v3M11 10.5v3M15 10.5v3M6.5 17v2.5M17.5 17v2.5"/>',
    "network": '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.5 3.5 5.5 3.5 8.5s-1 6-3.5 8.5c-2.5-2.5-3.5-5.5-3.5-8.5s1-6 3.5-8.5z"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.8v.1"/>',
    "alert": '<path d="M12 4 21 19.5H3z"/><path d="M12 10v4.5M12 17.3v.1"/>',
    "user": '<circle cx="12" cy="8.5" r="3.8"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/>',
    "bolt": '<path d="M13 3 5 13.5h6L10.5 21 19 10.5h-6z"/>',
    "terminal": '<rect x="3" y="4.5" width="18" height="15" rx="2.5"/><path d="M7 9.5l3 2.5-3 2.5M12.5 15h4.5"/>',
    "download": '<path d="M12 4v11M7 10.5l5 5 5-5M5 20h14"/>',
    "wave": '<path d="M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4"/>',
    "calendar": '<rect x="3.5" y="5" width="17" height="15" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    "keyboard": '<rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6 10h.01M9.5 10h.01M13 10h.01M16.5 10h.01M8 14h8"/>',
}
_ICON_CACHE: dict[tuple, QIcon] = {}


def _svg(kind: str, color: str, stroke: float) -> QByteArray:
    body = _ICONS.get(kind, _ICONS["circle"]).replace("COLOR", color)
    return QByteArray(
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
        ).encode("utf-8")
    )


def icon_pixmap(kind: str, color: str, size: int = 20, stroke: float = 1.7) -> QPixmap:
    ratio = 2.0
    app = QGuiApplication.instance()
    if app is not None:
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            ratio = max(2.0, screen.devicePixelRatio())
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.fill(Qt.transparent)
    renderer = QSvgRenderer(_svg(kind, color, stroke))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * ratio, size * ratio))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def make_icon(kind: str, color: str, size: int = 20, *, checked_color: str | None = None,
              disabled_color: str | None = None, stroke: float = 1.7) -> QIcon:
    key = (kind, color, size, checked_color, disabled_color, stroke)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached
    icon = QIcon()
    icon.addPixmap(icon_pixmap(kind, color, size, stroke), QIcon.Normal, QIcon.Off)
    icon.addPixmap(icon_pixmap(kind, color, size, stroke), QIcon.Active, QIcon.Off)
    on = checked_color or color
    icon.addPixmap(icon_pixmap(kind, on, size, stroke), QIcon.Normal, QIcon.On)
    icon.addPixmap(icon_pixmap(kind, on, size, stroke), QIcon.Active, QIcon.On)
    if disabled_color:
        icon.addPixmap(icon_pixmap(kind, disabled_color, size, stroke), QIcon.Disabled, QIcon.Off)
        icon.addPixmap(icon_pixmap(kind, disabled_color, size, stroke), QIcon.Disabled, QIcon.On)
    _ICON_CACHE[key] = icon
    return icon


def _role_color(role: str) -> str:
    p = current_palette()
    if role.startswith("#"):
        return role
    return {
        "text": p.text, "muted": p.text_2, "faint": p.text_3, "accent": p.accent_text,
        "on_accent": p.on_accent, "danger": p.danger, "success": p.success, "warning": p.warning,
        "listening": STATE_COLORS["listening"], "thinking": STATE_COLORS["thinking"],
        "speaking": STATE_COLORS["speaking"],
    }.get(role, p.text_2)


class IconLabel(QLabel):
    """A painted icon that follows the theme."""

    def __init__(self, kind: str, size: int = 18, role: str = "muted", parent=None):
        super().__init__(parent)
        self._kind, self._size, self._role = kind, size, role
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        theme().changed.connect(self._refresh)
        self._refresh()

    def set_kind(self, kind: str, role: str | None = None):
        self._kind = kind
        if role is not None:
            self._role = role
        self._refresh()

    def _refresh(self, *_):
        self.setPixmap(icon_pixmap(self._kind, _role_color(self._role), self._size))


class IconButton(QToolButton):
    """Compact icon-only button with a tooltip and an accessible name."""

    def __init__(self, kind: str, tooltip: str, *, size: int = 34, icon_size: int = 18,
                 role: str = "muted", checked_role: str = "accent", object_name: str = "iconButton",
                 checkable: bool = False, parent=None):
        super().__init__(parent)
        self._kind, self._role, self._checked_role = kind, role, checked_role
        self.setObjectName(object_name)
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(size, size)
        self.setIconSize(QSize(icon_size, icon_size))
        self.setCheckable(checkable)
        self.setFocusPolicy(Qt.StrongFocus)
        theme().changed.connect(self._refresh)
        self._refresh()

    def set_kind(self, kind: str, role: str | None = None):
        self._kind = kind
        if role is not None:
            self._role = role
        self._refresh()

    def _refresh(self, *_):
        self.setIcon(make_icon(
            self._kind, _role_color(self._role), self.iconSize().width(),
            checked_color=_role_color(self._checked_role), disabled_color=current_palette().text_3,
        ))


class NavButton(QPushButton):
    """Sidebar navigation entry; collapses to an icon with a tooltip."""

    def __init__(self, kind: str, text: str, shortcut_hint: str = "", parent=None):
        super().__init__(text, parent)
        self._kind, self._text = kind, text
        self.setObjectName("navButton")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(18, 18))
        self.setMinimumHeight(38)
        self.setToolTip(f"{text}  ({shortcut_hint})" if shortcut_hint else text)
        self.setAccessibleName(text)
        theme().changed.connect(self._refresh)
        self._refresh()

    def set_collapsed(self, collapsed: bool):
        self.setText("" if collapsed else self._text)
        self.setProperty("collapsed", "true" if collapsed else "false")
        repolish(self)

    def _refresh(self, *_):
        p = current_palette()
        self.setIcon(make_icon(self._kind, p.text_2, 18, checked_color=p.accent_text))


# ============================================================================= orb
class NexusOrb(QWidget):
    """The NEXUS voice orb: the assistant's face.

    It breathes while idle, ripples while listening, orbits while thinking and pulses while
    speaking. Clicking it (or pressing Space/Enter while it has focus) emits ``clicked``.
    """

    clicked = Signal()
    STATE_COLORS = {
        "sleeping": QColor("#45d9ff"),
        "listening": QColor(STATE_COLORS["listening"]),
        "thinking": QColor(STATE_COLORS["thinking"]),
        "speaking": QColor(STATE_COLORS["speaking"]),
    }

    def __init__(self, size: int = 220, interactive: bool = True, parent=None):
        super().__init__(parent)
        self.state = "sleeping"
        self.state_colors = dict(self.STATE_COLORS)
        self.state_colors["sleeping"] = QColor(current_palette().accent)
        self.phase = 0.0
        self._t = 0.0
        self._hover = 0.0
        self._hovering = False
        self._interactive = interactive
        self._clock = QElapsedTimer()
        self._clock.start()
        self._last = 0
        self.setMinimumSize(size, size)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        if interactive:
            self.setCursor(Qt.PointingHandCursor)
            self.setFocusPolicy(Qt.StrongFocus)
            self.setAccessibleName("NEXUS voice orb")
            self.setAccessibleDescription("Press to talk to NEXUS")
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.advance)
        self.animation_timer.start(33)
        theme().changed.connect(self._theme_changed)

    def sizeHint(self):
        return self.minimumSize()

    def _theme_changed(self, palette):
        self.state_colors["sleeping"] = QColor(palette.accent)
        self.update()

    def set_state(self, state):
        state = str(state or "sleeping").strip().lower()
        if state == "idle":
            state = "sleeping"
        if state not in self.STATE_COLORS:
            state = "sleeping"
        if state != self.state:
            self.state = state
            self.animation_timer.setInterval(33 if state == "sleeping" else 16)
            self.update()

    def set_state_color(self, state, color):
        qcolor = QColor(color)
        if state in self.STATE_COLORS and qcolor.isValid():
            self.state_colors[state] = qcolor
            self.update()

    def advance(self):
        now = self._clock.elapsed()
        dt = min(0.1, max(0.0, (now - self._last) / 1000.0)) if self._last else 0.033
        self._last = now
        self._t += dt
        self.phase = (self.phase + dt) % (math.pi * 2)
        target = 1.0 if self._hovering else 0.0
        self._hover += (target - self._hover) * min(1.0, dt * 10)
        self.update()

    # ---- interaction
    def showEvent(self, event):
        self._last = 0
        self.animation_timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.animation_timer.stop()
        super().hideEvent(event)

    def enterEvent(self, event):
        self._hovering = self._interactive
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovering = False
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._interactive and event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if self._interactive and event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.clicked.emit()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event):
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.update()
        super().focusOutEvent(event)

    # ---- painting
    def paintEvent(self, event):  # noqa: ARG002
        p = current_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        size = min(w, h)
        c = QPointF(w / 2, h / 2)
        t = self._t
        state = self.state
        color = QColor(self.state_colors.get(state, self.state_colors["sleeping"]))
        partner = QColor("#8b7bff") if state in ("sleeping", "speaking", "listening") else QColor("#ff8bd1")
        if state == "listening":
            partner = QColor("#45d9ff")
        radius = size * 0.245 * (1 + 0.035 * self._hover)
        if state == "sleeping":
            radius *= 1 + 0.018 * math.sin(t * 1.4)

        # Soft glow behind the orb.
        energy = {"sleeping": 0.55, "listening": 0.95, "thinking": 0.8, "speaking": 0.85}[state]
        if state == "speaking":
            energy *= 0.75 + 0.25 * abs(math.sin(t * 5.2))
        glow = QRadialGradient(c, radius * 1.95)
        glow_color = QColor(color)
        glow_color.setAlpha(int((70 if p.is_dark else 55) * energy))
        glow.setColorAt(0.35, glow_color)
        glow_color.setAlpha(0)
        glow.setColorAt(1.0, glow_color)
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(c, radius * 1.95, radius * 1.95)

        # Listening: ripples travelling outwards.
        if state == "listening":
            for i in range(3):
                progress = (t * 0.55 + i / 3.0) % 1.0
                ring = QColor(color)
                ring.setAlpha(int(150 * (1 - progress) ** 1.6))
                painter.setPen(QPen(ring, max(1.2, size * 0.008)))
                painter.setBrush(Qt.NoBrush)
                r = radius * (1.05 + 0.62 * progress)
                painter.drawEllipse(c, r, r)

        # Thinking: two arcs orbiting the core.
        if state == "thinking":
            r = radius * 1.24
            rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
            gradient = QConicalGradient(c, -math.degrees(t * 2.4))
            arc = QColor(color)
            gradient.setColorAt(0.0, arc)
            arc.setAlpha(0)
            gradient.setColorAt(0.45, arc)
            gradient.setColorAt(1.0, QColor(color))
            pen = QPen(gradient, max(2.0, size * 0.014))
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            start = int(math.degrees(t * 2.4) * 16)
            painter.drawArc(rect, start, 100 * 16)
            painter.drawArc(rect, start + 180 * 16, 60 * 16)

        # The organic body.
        amp = {"sleeping": 0.022, "listening": 0.04, "thinking": 0.03, "speaking": 0.05}[state]
        if state == "speaking":
            amp += 0.045 * (0.5 + 0.5 * math.sin(t * 9.0)) * (0.5 + 0.5 * math.sin(t * 3.3 + 1))
        speed = 1.0 if state == "sleeping" else 1.9
        path = QPainterPath()
        steps = 96
        for i in range(steps + 1):
            theta = (i / steps) * math.tau
            wobble = (0.55 * math.sin(3 * theta + t * 1.3 * speed)
                      + 0.30 * math.sin(5 * theta - t * 1.7 * speed)
                      + 0.15 * math.sin(7 * theta + t * 2.6 * speed))
            r = radius * (1 + amp * wobble)
            point = QPointF(c.x() + r * math.cos(theta), c.y() + r * math.sin(theta))
            if i == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        path.closeSubpath()

        swirl = t * (0.35 if state == "sleeping" else 0.9)
        focal = QPointF(c.x() - radius * 0.35 * math.cos(swirl) - radius * 0.1,
                        c.y() - radius * 0.40 - radius * 0.12 * math.sin(swirl))
        body = QRadialGradient(c, radius * 1.25, focal)
        body.setColorAt(0.0, QColor(mix(color, "#ffffff", 0.62)))
        body.setColorAt(0.38, color)
        body.setColorAt(1.0, QColor(mix(partner, "#05070c", 0.25 if p.is_dark else 0.05)))
        painter.setPen(Qt.NoPen)
        painter.setBrush(body)
        painter.drawPath(path)

        # Glassy rim and sheen for depth.
        rim = QColor(mix(color, "#ffffff", 0.5))
        rim.setAlpha(90)
        painter.setPen(QPen(rim, 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        sheen = QRadialGradient(QPointF(c.x() - radius * 0.32, c.y() - radius * 0.42), radius * 0.55)
        sheen.setColorAt(0.0, QColor(255, 255, 255, 80))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(sheen)
        painter.drawEllipse(QPointF(c.x() - radius * 0.32, c.y() - radius * 0.42), radius * 0.55, radius * 0.4)

        if self._interactive and self.hasFocus():
            ring = QColor(p.accent)
            ring.setAlpha(200)
            pen = QPen(ring, 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(c, radius * 1.5, radius * 1.5)
        painter.end()


class OrbMark(QWidget):
    """A small static orb used as the NEXUS logo and avatar."""

    def _theme_repaint(self, *_):
        self.update()

    def __init__(self, size: int = 28, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        theme().changed.connect(self._theme_repaint)

    def paintEvent(self, event):  # noqa: ARG002
        from ui.brand import paint_mark

        painter = QPainter(self)
        paint_mark(painter, QRectF(self.rect()), current_palette().accent)
        painter.end()


# ============================================================================= status
class StatusPill(QLabel):
    """Shows what NEXUS is doing ("Ready", "Thinking…").

    The rest of the window reports state with the long-standing ``"● THINKING"`` style
    strings; this widget accepts them, shows friendly wording and colours itself by state.
    ``text()`` keeps returning the value that was set, so existing checks keep working.
    """

    LABELS = {
        "ready": "Ready", "thinking": "Thinking…", "listening": "Listening…", "speaking": "Speaking…",
        "executing": "Running command…", "error": "Needs attention",
    }

    def __init__(self, text: str = "● READY", parent=None):
        super().__init__(parent)
        self.setObjectName("statusPill")
        self._raw = ""
        self.state = "ready"
        self.mirrors: list[StatusPill] = []
        self.setText(text)

    def setText(self, text):  # noqa: N802 - Qt naming
        self._raw = str(text)
        state = re.sub(r"[^a-z]", "", self._raw.lower()) or "ready"
        self.state = state if state in self.LABELS else "ready"
        super().setText("●  " + self.LABELS.get(self.state, self._raw))
        self.setProperty("state", self.state)
        self.setAccessibleName(f"Status: {self.LABELS.get(self.state)}")
        repolish(self)
        for mirror in getattr(self, "mirrors", []):
            mirror.setText(self._raw)

    def text(self):  # noqa: D401 - mirrors QLabel.text
        return self._raw


# ============================================================================= cards & layout helpers
class Card(QFrame):
    def __init__(self, title: str = "", *, icon: str | None = None, action_text: str | None = None,
                 action=None, object_name: str = "card", padding: int = 18, parent=None):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding - 2, padding, padding)
        self.body.setSpacing(10)
        self.action_button = None
        if title:
            header = QHBoxLayout()
            header.setSpacing(8)
            if icon:
                header.addWidget(IconLabel(icon, 16, "muted"))
            label = QLabel(title)
            label.setObjectName("cardTitle")
            header.addWidget(label)
            header.addStretch(1)
            if action_text:
                self.action_button = QPushButton(action_text)
                self.action_button.setObjectName("linkButton")
                self.action_button.setCursor(Qt.PointingHandCursor)
                if action is not None:
                    self.action_button.clicked.connect(action)
                header.addWidget(self.action_button)
            self.body.addLayout(header)


class EmptyState(QWidget):
    def __init__(self, icon: str, title: str, body: str = "", button_text: str = "", action=None,
                 compact: bool = False, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12 if compact else 28, 8, 12 if compact else 28)
        layout.setSpacing(6 if compact else 8)
        holder = QFrame()
        holder.setObjectName("cardFlat")
        size = 40 if compact else 52
        holder.setFixedSize(size, size)
        holder.setStyleSheet(f"QFrame#cardFlat {{ border-radius: {size // 2}px; }}")
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        holder_layout.addWidget(IconLabel(icon, 18 if compact else 22, "muted"), 0, Qt.AlignCenter)
        layout.addWidget(holder, 0, Qt.AlignHCenter)
        heading = QLabel(title)
        heading.setObjectName("emptyTitle")
        heading.setAlignment(Qt.AlignCenter)
        if compact:
            heading.setStyleSheet("font-size: 14px;")
        layout.addWidget(heading)
        if body:
            text = QLabel(body)
            text.setObjectName("emptyBody")
            text.setAlignment(Qt.AlignCenter)
            text.setWordWrap(True)
            text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            layout.addWidget(text)
        if button_text and action is not None:
            button = QPushButton(button_text)
            button.setObjectName("secondaryButton")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(action)
            layout.addSpacing(4)
            layout.addWidget(button, 0, Qt.AlignHCenter)


class ResponsiveGrid(QWidget):
    """Lays out cards in as many columns as the width allows."""

    def __init__(self, min_column_width: int = 320, max_columns: int = 3, spacing: int = 16, parent=None):
        super().__init__(parent)
        self._items: list[tuple[QWidget, int]] = []
        self._min, self._max = min_column_width, max_columns
        self._columns = 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(spacing)

    def add(self, widget: QWidget, span: int = 1):
        self._items.append((widget, span))
        self._relayout(force=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self, force: bool = False):
        columns = max(1, min(self._max, (self.width() + self.grid.spacing()) // (self._min + self.grid.spacing())))
        if columns == self._columns and not force:
            return
        self._columns = columns
        for widget, _ in self._items:
            self.grid.removeWidget(widget)
        for column in range(self._max):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        row = col = 0
        for widget, span in self._items:
            span = min(span, columns)
            if col + span > columns:
                row, col = row + 1, 0
            self.grid.addWidget(widget, row, col, 1, span)
            col += span
            if col >= columns:
                row, col = row + 1, 0


class Segmented(QFrame):
    """A small segmented control (e.g. Dark / Light / System)."""

    changed = Signal(str)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.setObjectName("segmented")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self.buttons = {}
        for value, label in options:
            button = QPushButton(label)
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, v=value: self.set_value(v, emit=True))
            layout.addWidget(button)
            self.buttons[value] = button

    def set_value(self, value, emit=False):
        for key, button in self.buttons.items():
            button.setChecked(key == value)
        if emit:
            self.changed.emit(value)

    def value(self):
        for key, button in self.buttons.items():
            if button.isChecked():
                return key
        return None


# ============================================================================= graphs
class UsageGraph(QWidget):
    """Smooth line chart for a few percentage series (0-100)."""

    def _theme_repaint(self, *_):
        self.update()

    def __init__(self, series_colors: dict[str, str], height: int = 170, parent=None):
        super().__init__(parent)
        self.series_colors = dict(series_colors)
        self.data = {name: [] for name in series_colors}
        self.setMinimumHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        theme().changed.connect(self._theme_repaint)

    def set_series(self, name, values):
        self.data[name] = list(values or [])
        self.update()

    def paintEvent(self, event):  # noqa: ARG002
        p = current_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(46, 10, -6, -12)
        grid = QColor(p.border)
        painter.setPen(QPen(grid, 1, Qt.DashLine))
        painter.setFont(self.font())
        for value in (0, 25, 50, 75, 100):
            y = rect.bottom() - rect.height() * value / 100
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.setPen(QColor(p.text_3))
            painter.drawText(QRectF(0, y - 8, 38, 16), Qt.AlignRight | Qt.AlignVCenter, f"{value}%")
            painter.setPen(QPen(grid, 1, Qt.DashLine))
        for name, color in self.series_colors.items():
            values = self.data.get(name) or []
            if len(values) < 2:
                continue
            count = max(len(values), 2)
            step = rect.width() / (count - 1)
            points = [
                QPointF(rect.left() + i * step, rect.bottom() - rect.height() * max(0.0, min(100.0, float(v))) / 100)
                for i, v in enumerate(values)
            ]
            path = QPainterPath(points[0])
            for a, b in zip(points, points[1:]):
                mid = (a.x() + b.x()) / 2
                path.cubicTo(QPointF(mid, a.y()), QPointF(mid, b.y()), b)
            fill = QPainterPath(path)
            fill.lineTo(points[-1].x(), rect.bottom())
            fill.lineTo(points[0].x(), rect.bottom())
            fill.closeSubpath()
            fill_color = QColor(color)
            fill_color.setAlpha(38)
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill_color)
            painter.drawPath(fill)
            painter.setPen(QPen(QColor(color), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
        painter.end()


class Sparkline(QWidget):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.color = color
        self.values: list[float] = []
        self.setFixedHeight(28)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setData(self, values):  # noqa: N802 - matches the old widget API
        self.values = list(values or [])[-40:]
        self.update()

    def paintEvent(self, event):  # noqa: ARG002
        if len(self.values) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 2, -1, -2)
        step = rect.width() / (len(self.values) - 1)
        path = QPainterPath()
        for i, value in enumerate(self.values):
            point = QPointF(rect.left() + i * step, rect.bottom() - rect.height() * max(0.0, min(100.0, float(value))) / 100)
            path.moveTo(point) if i == 0 else path.lineTo(point)
        painter.setPen(QPen(QColor(self.color), 1.6))
        painter.drawPath(path)
        painter.end()


# ============================================================================= time helpers
def parse_timestamp(value) -> datetime | None:
    """Parse a stored timestamp. SQLite's CURRENT_TIMESTAMP is UTC without a zone marker."""
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone().replace(tzinfo=None)


def friendly_time(value, with_time: bool = True) -> str:
    parsed = parse_timestamp(value)
    if parsed is None:
        return ""
    now = datetime.now()
    clock = parsed.strftime("%H:%M")
    if parsed.date() == now.date():
        return clock if with_time else "Today"
    delta_days = (now.date() - parsed.date()).days
    if delta_days == 1:
        return f"Yesterday {clock}" if with_time else "Yesterday"
    if 0 < delta_days < 7:
        return parsed.strftime("%A")
    return parsed.strftime("%d %b %Y" if parsed.year != now.year else "%d %b")


# ============================================================================= markdown
def _soft_wrap(text: str, limit: int = 36) -> str:
    return re.sub(rf"(\S{{{limit}}})(?=\S)", lambda m: m.group(1) + "​", text)


def _soft_wrap_outside_code(text: str) -> str:
    parts = re.split(r"(```.*?```)", str(text or ""), flags=re.S)
    return "".join(part if part.startswith("```") else _soft_wrap(part) for part in parts)


def markdown_to_html(text: str) -> str:
    """Render assistant markdown as Qt rich text styled for the current theme."""
    p = current_palette()
    mono = mono_font_family()
    html = markdown(_soft_wrap_outside_code(text), extensions=["fenced_code", "tables", "sane_lists"])

    def code_block(match):
        body = match.group(2)
        return (
            f"<table width='100%' cellspacing='0' cellpadding='10' style='background-color:{p.code_bg}; "
            f"border:1px solid {p.border}; margin-top:4px; margin-bottom:8px;'><tr><td>"
            f"<pre style='font-family:\"{mono}\"; font-size:12px; color:{p.text}; margin:0;'>{body}</pre>"
            f"</td></tr></table>"
        )

    html = re.sub(r"<pre><code( class=\"[^\"]*\")?>(.*?)</code></pre>", code_block, html, flags=re.S)
    html = re.sub(
        r"<code>(.*?)</code>",
        lambda m: f"<code style='font-family:\"{mono}\"; background-color:{p.surface_3}; color:{p.text};'>&nbsp;{m.group(1)}&nbsp;</code>",
        html, flags=re.S,
    )
    html = html.replace("<p>", "<p style='margin-top:0; margin-bottom:9px;'>")
    for tag, size in (("h1", 19), ("h2", 17), ("h3", 15), ("h4", 14)):
        html = html.replace(f"<{tag}>", f"<{tag} style='font-size:{size}px; font-weight:600; margin-top:8px; margin-bottom:6px;'>")
    html = html.replace("<ul>", "<ul style='margin-top:0; margin-bottom:8px; margin-left:-12px;'>")
    html = html.replace("<ol>", "<ol style='margin-top:0; margin-bottom:8px; margin-left:-12px;'>")
    html = html.replace("<li>", "<li style='margin-bottom:3px;'>")
    html = html.replace("<blockquote>", f"<blockquote style='color:{p.text_2}; margin-left:12px;'>")
    html = html.replace("<a ", f"<a style='color:{p.accent_text};' ")
    html = html.replace(
        "<table>",
        f"<table cellspacing='0' cellpadding='7' border='1' style='border-color:{p.border_strong}; border-style:solid; margin-top:4px; margin-bottom:8px;'>",
    )
    html = html.replace("<th>", f"<th style='background-color:{p.surface_2}; text-align:left;'>")
    html = html.replace("<hr />", f"<hr style='color:{p.border};' />")
    return f"<div style='line-height:150%;'>{html}</div>"


# ============================================================================= chat
_SOURCE_TAG = re.compile(r"^\s*\[(LOCAL|GEMINI[^:\]]*)(?::\s*([^\]]*))?\]\s*", re.I)


def split_source(text: str) -> tuple[str, str]:
    """Separate the engine tag NEXUS puts at the start of answers ("[LOCAL: nexus]")."""
    match = _SOURCE_TAG.match(str(text or ""))
    if not match:
        return "", str(text or "")
    kind = match.group(1).strip().lower()
    detail = (match.group(2) or "").strip()
    label = ("On this PC" if kind == "local" else "Gemini" if kind == "gemini" else match.group(1).strip().title())
    return (f"{label} · {detail}" if detail else label), str(text)[match.end():]


ERROR_PREFIXES = ("Nexus could not complete", "NEXUS could not complete", "Windows command execution failed")


class TypingIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._step = 0
        self.setFixedSize(46, 22)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setAccessibleName("NEXUS is thinking")

    def showEvent(self, event):
        self._timer.start(140)
        super().showEvent(event)

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self):
        self._step = (self._step + 1) % 12
        self.update()

    def paintEvent(self, event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        base = QColor(STATE_COLORS["thinking"])
        for i in range(3):
            phase = math.sin((self._step / 12.0) * math.tau - i * 0.9)
            color = QColor(base)
            color.setAlpha(int(110 + 145 * (0.5 + 0.5 * phase)))
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(9 + i * 14, 11 - 2.5 * max(0.0, phase)), 4, 4)
        painter.end()


class MessageWidget(QWidget):
    copyRequested = Signal(str)
    speakRequested = Signal(str)
    settingsRequested = Signal()

    def __init__(self, role: str, content: str, stamp: str = "", streaming: bool = False, parent=None):
        super().__init__(parent)
        self.role = role
        self.content = str(content or "")
        self.streaming = streaming
        self.setObjectName("transparent")
        self.setAttribute(Qt.WA_StyledBackground, True)
        outer = QHBoxLayout(self)
        # A little more air before a new question than between a question and its answer.
        outer.setContentsMargins(0, 10 if role == "user" else 4, 0, 2)
        outer.setSpacing(12)
        if role == "user":
            outer.addStretch(1)
            self.bubble = QFrame()
            self.bubble.setObjectName("userBubble")
            bubble_layout = QVBoxLayout(self.bubble)
            bubble_layout.setContentsMargins(14, 10, 14, 10)
            self.label = QLabel()
            self.label.setObjectName("userText")
            self.label.setTextFormat(Qt.PlainText)
            self.label.setWordWrap(True)
            self.label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            bubble_layout.addWidget(self.label)
            outer.addWidget(self.bubble, 0, Qt.AlignRight)
            self.set_content(self.content)
            self.bubble.setToolTip(stamp)
            return

        avatar = OrbMark(28)
        outer.addWidget(avatar, 0, Qt.AlignTop)
        column = QVBoxLayout()
        column.setSpacing(4)
        header = QHBoxLayout()
        header.setSpacing(8)
        name = QLabel("NEXUS")
        name.setObjectName("messageName")
        header.addWidget(name)
        self.meta = QLabel(stamp)
        self.meta.setObjectName("messageMeta")
        header.addWidget(self.meta)
        header.addStretch(1)
        column.addLayout(header)

        self.is_error = self.content.startswith(ERROR_PREFIXES)
        self.label = QLabel()
        self.label.setObjectName("assistantText")
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.RichText)
        self.label.setOpenExternalLinks(True)
        self.label.setTextInteractionFlags(Qt.TextBrowserInteraction | Qt.TextSelectableByKeyboard)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        if self.is_error:
            frame = QFrame()
            frame.setObjectName("errorBubble")
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(12, 10, 12, 10)
            frame_layout.setSpacing(8)
            top = QHBoxLayout()
            top.addWidget(IconLabel("alert", 16, "danger"), 0, Qt.AlignTop)
            top.addWidget(self.label, 1)
            frame_layout.addLayout(top)
            hint = QLabel("Check that your AI engine is running (Ollama for local mode, a Gemini key for online), "
                          "or switch engines in Settings.")
            hint.setObjectName("mutedText")
            hint.setWordWrap(True)
            frame_layout.addWidget(hint)
            open_settings = QPushButton("Open AI settings")
            open_settings.setObjectName("secondaryButton")
            open_settings.setCursor(Qt.PointingHandCursor)
            open_settings.clicked.connect(self.settingsRequested.emit)
            frame_layout.addWidget(open_settings, 0, Qt.AlignLeft)
            column.addWidget(frame)
        else:
            column.addWidget(self.label)

        self.actions = QWidget()
        actions = QHBoxLayout(self.actions)
        actions.setContentsMargins(0, 2, 0, 0)
        actions.setSpacing(2)
        copy = IconButton("copy", "Copy response", size=28, icon_size=15, role="faint")
        copy.clicked.connect(lambda: self.copyRequested.emit(split_source(self.content)[1]))
        actions.addWidget(copy)
        speak = IconButton("volume", "Read aloud", size=28, icon_size=15, role="faint")
        speak.clicked.connect(lambda: self.speakRequested.emit(split_source(self.content)[1]))
        actions.addWidget(speak)
        actions.addStretch(1)
        self.actions.setVisible(not streaming)
        # Copy / read-aloud stay out of the way until the message is hovered or a button
        # gets keyboard focus; the space is kept so nothing shifts when they appear.
        self._actions_effect = QGraphicsOpacityEffect(self.actions)
        self._actions_effect.setOpacity(0.0)
        self.actions.setGraphicsEffect(self._actions_effect)
        self._pinned = False
        for button in (copy, speak):
            # Reachable with Tab, but clicking them must not pull focus out of the message box.
            button.setFocusPolicy(Qt.TabFocus)
            button.installEventFilter(self)
        column.addWidget(self.actions)
        outer.addLayout(column, 1)
        self.set_content(self.content)

    def set_content(self, content: str):
        self.content = str(content or "")
        if self.role == "user":
            self.label.setText(_soft_wrap(self.content, 30))
        else:
            # No trailing "cursor" glyph while streaming: Qt's text layout has crashed when a
            # block-element character (needing font fallback) ends text that changes rapidly.
            # The header says "writing…" instead. The engine tag moves into the header too.
            source, body = split_source(self.content)
            if source and hasattr(self, "meta") and not self.streaming:
                stamp = self.meta.text().split("  ·  ")[0]
                self.meta.setText(f"{stamp}  ·  {source}")
            self.label.setText(markdown_to_html(body))

    def set_actions_pinned(self, pinned: bool):
        """The newest reply keeps its actions visible."""
        if self.role == "user" or not hasattr(self, "_actions_effect"):
            return
        self._pinned = pinned
        self._actions_effect.setOpacity(1.0 if pinned else 0.0)

    def enterEvent(self, event):
        if hasattr(self, "_actions_effect"):
            self._actions_effect.setOpacity(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if hasattr(self, "_actions_effect") and not self._pinned:
            self._actions_effect.setOpacity(0.0)
        super().leaveEvent(event)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.FocusIn:
            self._actions_effect.setOpacity(1.0)
        elif event.type() == QEvent.FocusOut and not self._pinned and not self.underMouse():
            self._actions_effect.setOpacity(0.0)
        return super().eventFilter(watched, event)

    def set_bubble_width(self, width: int):
        if self.role != "user":
            return
        width = max(220, width)
        self.bubble.setMaximumWidth(width)
        # A word-wrapped QLabel otherwise prefers a narrow width; ask for the width the
        # longest line needs (up to the bubble's maximum) so short messages stay on one line.
        metrics = self.label.fontMetrics()
        longest = max((metrics.horizontalAdvance(line) for line in self.content.splitlines() or [""]), default=0)
        self.label.setMinimumWidth(min(longest + 4, width - 28))

    def finish_streaming(self):
        self.streaming = False
        if hasattr(self, "actions"):
            self.actions.setVisible(True)
        self.set_content(self.content)


class ChatView(QScrollArea):
    """Scrollable conversation transcript built from message widgets.

    ``show_conversation`` is cheap to call repeatedly: it only appends what is new, and
    streamed text updates a single live message instead of re-rendering the transcript.
    """

    copyRequested = Signal(str)
    speakRequested = Signal(str)
    suggestionChosen = Signal(str)
    settingsRequested = Signal()

    def __init__(self, suggestions=(), parent=None):
        super().__init__(parent)
        self.setObjectName("chatScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._suggestions = list(suggestions)
        self._conversation_key = object()
        self._keys: list = []
        self._widgets: list[MessageWidget] = []
        self._live: MessageWidget | None = None

        container = QWidget()
        container.setObjectName("scrollContent")
        row = QHBoxLayout(container)
        row.setContentsMargins(24, 18, 24, 18)
        row.addStretch(1)
        self.column = QWidget()
        self.column.setObjectName("chatColumn")
        self.column.setMaximumWidth(820)
        self.column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.layout_ = QVBoxLayout(self.column)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(6)
        row.addWidget(self.column, 100)
        row.addStretch(1)
        self.setWidget(container)

        self.empty = self._build_empty()
        self.layout_.addWidget(self.empty)
        self.typing = QWidget()
        typing_row = QHBoxLayout(self.typing)
        typing_row.setContentsMargins(0, 6, 0, 6)
        typing_row.setSpacing(12)
        typing_row.addWidget(OrbMark(28), 0, Qt.AlignTop)
        typing_text = QVBoxLayout()
        typing_name = QLabel("NEXUS")
        typing_name.setObjectName("messageName")
        typing_text.addWidget(typing_name)
        typing_text.addWidget(TypingIndicator())
        typing_row.addLayout(typing_text)
        typing_row.addStretch(1)
        self.typing.hide()
        self.layout_.addWidget(self.typing)
        self.layout_.addStretch(1)
        self.verticalScrollBar().rangeChanged.connect(self._range_changed)
        self._stick_to_bottom = True
        theme().changed.connect(self._theme_changed)

    def _build_empty(self):
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 60, 0, 20)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignHCenter)
        layout.addWidget(OrbMark(54), 0, Qt.AlignHCenter)
        title = QLabel("How can I help?")
        title.setObjectName("heroGreeting")
        title.setStyleSheet("font-size: 24px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        body = QLabel("Ask a question, set a reminder, or tell NEXUS something to remember. "
                      "Press the microphone to talk.")
        body.setObjectName("mutedText")
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignCenter)
        body.setMaximumWidth(460)
        layout.addWidget(body, 0, Qt.AlignHCenter)
        if self._suggestions:
            chips = QGridLayout()
            chips.setSpacing(8)
            for index, (label, prompt) in enumerate(self._suggestions[:4]):
                chip = QPushButton(label)
                chip.setObjectName("chip")
                chip.setCursor(Qt.PointingHandCursor)
                chip.clicked.connect(lambda _=False, text=prompt: self.suggestionChosen.emit(text))
                chips.addWidget(chip, index // 2, index % 2)
            holder = QWidget()
            holder.setLayout(chips)
            layout.addSpacing(8)
            layout.addWidget(holder, 0, Qt.AlignHCenter)
        return box

    # ---- public API
    def show_conversation(self, key, messages, live_text: str = "", thinking: bool = False, force_scroll=False,
                          live_stamp: str = "writing…"):
        messages = [m for m in messages if str(m.get("role")) in ("user", "assistant")]
        keys = [(m.get("id"), m.get("role"), len(str(m.get("content", "")))) for m in messages]
        was_at_bottom = self._at_bottom()
        if key != self._conversation_key or keys[: len(self._keys)] != self._keys:
            self._clear_messages()
            self._conversation_key = key
            start = 0
            force_scroll = True
        else:
            start = len(self._keys)
        if self._live is not None and not live_text and len(messages) > len(self._keys):
            # The streamed reply has been saved: retire the live widget *before* the saved
            # message is added. (Re-using it for the final text crashed Qt's text layout.)
            self._remove_live()
        for message in messages[start:]:
            role, content = str(message.get("role")), str(message.get("content", ""))
            self._insert(MessageWidget(role, content, friendly_time(message.get("created_at"))))
        self._keys = keys

        if live_text:
            if self._live is None:
                self._live = MessageWidget("assistant", live_text, live_stamp, streaming=True)
                self._connect(self._live)
                self.layout_.insertWidget(self.layout_.count() - 2, self._live)
            else:
                self._live.set_content(live_text)
        elif self._live is not None:
            self._remove_live()

        assistant = [w for w in self._widgets if w.role == "assistant"]
        for widget in assistant:
            widget.set_actions_pinned(widget is assistant[-1] and self._live is None)
        self.typing.setVisible(bool(thinking and not live_text))
        self.empty.setVisible(not messages and not live_text and not thinking)
        self._resize_bubbles()
        if force_scroll or was_at_bottom:
            self._stick_to_bottom = True
            QTimer.singleShot(0, self.scroll_to_bottom)

    def scroll_to_bottom(self):
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def message_count(self) -> int:
        return len(self._widgets)

    def toPlainText(self) -> str:  # noqa: N802 - compatibility with the old QTextEdit transcript
        return "\n\n".join(w.content for w in self._widgets)

    # ---- internals
    def _connect(self, widget: MessageWidget):
        widget.copyRequested.connect(self.copyRequested.emit)
        widget.speakRequested.connect(self.speakRequested.emit)
        widget.settingsRequested.connect(self.settingsRequested.emit)

    def _insert(self, widget: MessageWidget):
        self._connect(widget)
        self._widgets.append(widget)
        # Messages go before the live message (if any), the typing row and the final stretch.
        index = self.layout_.count() - 2
        if self._live is not None:
            index -= 1
        self.layout_.insertWidget(index, widget)

    def _discard(self, widget):
        # Never delete the widget that holds keyboard focus: Qt would hand focus around the
        # transcript while it is being rebuilt. Park focus on the transcript first.
        focused = QApplication.focusWidget()
        if focused is not None and (focused is widget or widget.isAncestorOf(focused)):
            self.setFocus(Qt.OtherFocusReason)
        # Keep the parent until Qt deletes the widget from the event loop. Re-parenting to
        # None would hand ownership to Python and destroy it immediately, mid-update.
        widget.hide()
        self.layout_.removeWidget(widget)
        widget.deleteLater()

    def _remove_live(self):
        self._discard(self._live)
        self._live = None

    def _clear_messages(self):
        for widget in self._widgets:
            self._discard(widget)
        self._widgets = []
        self._keys = []
        if self._live is not None:
            self._remove_live()

    def _at_bottom(self) -> bool:
        bar = self.verticalScrollBar()
        return bar.value() >= bar.maximum() - 60

    def _range_changed(self, _minimum, _maximum):
        if self._stick_to_bottom:
            self.scroll_to_bottom()
            QTimer.singleShot(60, self._release_stick)

    def _release_stick(self):
        self._stick_to_bottom = False

    def _resize_bubbles(self):
        width = int(self.column.width() * 0.8) if self.column.width() > 0 else 560
        for widget in self._widgets:
            widget.set_bubble_width(width)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_bubbles()

    def _theme_changed(self, *_):
        for widget in self._widgets + ([self._live] if self._live else []):
            widget.set_content(widget.content)


# ============================================================================= input
class TerminalInput(QPlainTextEdit):
    """Message input: Enter sends, Shift+Enter adds a line, Up/Down recalls history."""

    sendRequested = Signal(str)
    clearRequested = Signal()
    newConversationRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.command_history: list[str] = []
        self.history_index = -1
        self.setPlaceholderText("Ask NEXUS anything…")
        self.setTabChangesFocus(True)

    def keyPressEvent(self, event):
        modifiers = event.modifiers()
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if modifiers & Qt.ShiftModifier:
                super().keyPressEvent(event)
                return
            text = self.toPlainText().strip()
            if text:
                self.add_to_history(text)
                self.clear()
                self.history_index = -1
                self.sendRequested.emit(text)
            return
        if key == Qt.Key_L and modifiers & Qt.ControlModifier:
            self.clear()
            self.clearRequested.emit()
            return
        if key == Qt.Key_N and modifiers & Qt.ControlModifier:
            self.newConversationRequested.emit()
            return
        if key == Qt.Key_Escape:
            handler = getattr(self.window(), "interrupt_voice_output", None)
            if not callable(handler) or not handler():
                self.clear()
            return
        # History recall only when the cursor is on the first/last line, so multi-line
        # editing with the arrow keys still works.
        cursor = self.textCursor()
        if key == Qt.Key_Up and self.command_history and cursor.blockNumber() == 0:
            if self.history_index == -1:
                self.history_index = len(self.command_history) - 1
            elif self.history_index > 0:
                self.history_index -= 1
            self.setPlainText(self.command_history[self.history_index])
            self.moveCursor(QTextCursor.End)
            return
        if key == Qt.Key_Down and self.history_index != -1 and cursor.blockNumber() == self.document().blockCount() - 1:
            if self.history_index < len(self.command_history) - 1:
                self.history_index += 1
                self.setPlainText(self.command_history[self.history_index])
                self.moveCursor(QTextCursor.End)
            else:
                self.history_index = -1
                self.clear()
            return
        super().keyPressEvent(event)

    def add_to_history(self, command):
        from core.gemini_engine import redact_secrets

        command = redact_secrets(command).strip()
        if not command or (self.command_history and self.command_history[-1] == command):
            return
        self.command_history.append(command)
        if len(self.command_history) > 100:
            self.command_history.pop(0)


class Composer(QFrame):
    """The message box shared by the home and chat screens."""

    def __init__(self, placeholder: str = "Ask NEXUS anything…", *, show_language: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("composer")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 10, 10)
        layout.setSpacing(6)

        self.attachment_chip = QFrame()
        self.attachment_chip.setObjectName("attachmentChip")
        chip_layout = QHBoxLayout(self.attachment_chip)
        chip_layout.setContentsMargins(8, 4, 4, 4)
        chip_layout.setSpacing(6)
        chip_layout.addWidget(IconLabel("file", 15, "accent"))
        self.attachment_label = QLabel()
        self.attachment_label.setObjectName("rowTitle")
        chip_layout.addWidget(self.attachment_label)
        self.remove_attachment_button = IconButton("x", "Remove attached file", size=24, icon_size=13)
        chip_layout.addWidget(self.remove_attachment_button)
        self.attachment_chip.hide()
        layout.addWidget(self.attachment_chip, 0, Qt.AlignLeft)

        self.input = TerminalInput()
        self.input.setObjectName("composerInput")
        self.input.setPlaceholderText(placeholder)
        self.input.setAccessibleName("Message NEXUS")
        self.input.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.input.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.input.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.input.document().setDocumentMargin(2)
        self.input.installEventFilter(self)
        self.input.document().contentsChanged.connect(self._auto_height)
        layout.addWidget(self.input)

        tools = QHBoxLayout()
        tools.setSpacing(4)
        self.attach_button = IconButton("paperclip", "Attach a text or code file", size=32, icon_size=17)
        tools.addWidget(self.attach_button)
        self.language_combo = QComboBox()
        self.language_combo.setObjectName("compactCombo")
        self.language_combo.setToolTip("Language for speech recognition and spoken replies")
        self.language_combo.setAccessibleName("Voice language")
        for code, label in VOICE_LANGUAGES:
            self.language_combo.addItem(label, code)
        self.language_combo.setVisible(show_language)
        tools.addWidget(self.language_combo)
        self.voice_toggle = IconButton("volume_off", "Spoken replies are off — click to turn on",
                                       size=32, icon_size=17, checkable=True)
        self.voice_toggle.toggled.connect(self._voice_toggled)
        tools.addWidget(self.voice_toggle)
        tools.addStretch(1)
        self.mic_button = IconButton("mic", "Talk to NEXUS (Ctrl+M)", size=34, icon_size=18,
                                     role="text", object_name="micButton")
        tools.addWidget(self.mic_button)
        self.send_button = IconButton("send", "Send message (Enter)", size=34, icon_size=18,
                                      role="on_accent", object_name="sendButton")
        self.send_button.setEnabled(False)
        tools.addWidget(self.send_button)
        layout.addLayout(tools)

        self.send_button.clicked.connect(self._send_clicked)
        self.input.textChanged.connect(self._update_send_state)
        self._auto_height()

    # ---- behaviour
    def _send_clicked(self):
        text = self.input.toPlainText().strip()
        if text:
            self.input.add_to_history(text)
        self.input.clear()
        self.input.sendRequested.emit(text)

    def _update_send_state(self):
        self.send_button.setEnabled(bool(self.input.toPlainText().strip()) or self.attachment_chip.isVisible())

    def _voice_toggled(self, on: bool):
        self.voice_toggle.set_kind("volume" if on else "volume_off")
        tip = "Spoken replies are on — click to turn off" if on else "Spoken replies are off — click to turn on"
        self.voice_toggle.setToolTip(tip)
        self.voice_toggle.setAccessibleName(tip)

    def set_attachment(self, name: str | None):
        if name:
            self.attachment_label.setText(name)
            self.attachment_chip.show()
        else:
            self.attachment_label.setText("")
            self.attachment_chip.hide()
        self._update_send_state()

    def set_listening(self, listening: bool, enabled: bool = True):
        self.mic_button.setProperty("listening", "true" if listening else "false")
        self.mic_button.set_kind("stop" if listening else "mic", "#06121a" if listening else "text")
        tip = "Stop listening (Esc cancels)" if listening else "Talk to NEXUS (Ctrl+M)"
        self.mic_button.setToolTip(tip)
        self.mic_button.setAccessibleName(tip)
        self.mic_button.setEnabled(enabled)
        repolish(self.mic_button)

    def _auto_height(self):
        # QPlainTextEdit reports its document height in (wrapped) lines.
        lines = max(1, int(self.input.document().size().height()))
        wanted = lines * self.input.fontMetrics().lineSpacing() + 14
        self.input.setFixedHeight(min(150, wanted))
        self.input.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if wanted > 150 else Qt.ScrollBarAlwaysOff)

    def eventFilter(self, watched, event):
        if watched is self.input and event.type() in (QEvent.FocusIn, QEvent.FocusOut):
            self.setProperty("focused", "true" if event.type() == QEvent.FocusIn else "false")
            repolish(self)
        return super().eventFilter(watched, event)


class VoiceBar(QFrame):
    """Shown above the chat composer while NEXUS listens, thinks or speaks."""

    doneRequested = Signal()
    cancelRequested = Signal()

    TEXT = {
        "listening": ("Listening…", "Speak now. Click Done when you finish, or press Esc to cancel."),
        "thinking": ("Thinking…", "NEXUS is working on your request."),
        "speaking": ("Speaking…", "Press Esc or Stop to silence NEXUS."),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("voiceBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)
        self.orb = NexusOrb(44, interactive=False)
        self.orb.setFixedSize(44, 44)
        layout.addWidget(self.orb)
        text = QVBoxLayout()
        text.setSpacing(0)
        self.title = QLabel()
        self.title.setObjectName("voiceBarTitle")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("faintText")
        self.subtitle.setWordWrap(True)
        text.addWidget(self.title)
        text.addWidget(self.subtitle)
        layout.addLayout(text, 1)
        self.done_button = QPushButton("Done")
        self.done_button.setObjectName("primaryButton")
        self.done_button.setCursor(Qt.PointingHandCursor)
        self.done_button.clicked.connect(self.doneRequested.emit)
        layout.addWidget(self.done_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("secondaryButton")
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        self.cancel_button.clicked.connect(self.cancelRequested.emit)
        layout.addWidget(self.cancel_button)
        self.hide()

    def set_state(self, state: str, can_finish: bool = True):
        if state not in self.TEXT:
            self.hide()
            self.orb.set_state("sleeping")
            return
        title, subtitle = self.TEXT[state]
        self.title.setText(title)
        self.subtitle.setText(subtitle if (state != "listening" or can_finish)
                              else "Speak now. NEXUS replies when you stop talking.")
        self.orb.set_state(state)
        self.done_button.setVisible(state == "listening" and can_finish)
        self.cancel_button.setVisible(state in ("listening", "speaking"))
        self.cancel_button.setText("Stop" if state == "speaking" else "Cancel")
        self.show()


# ============================================================================= toast
class Toast(QFrame):
    """A brief, non-blocking confirmation shown at the bottom of the window."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 16, 10)
        layout.setSpacing(10)
        self.icon = IconLabel("check_circle", 17, "success")
        layout.addWidget(self.icon)
        self.label = QLabel()
        self.label.setObjectName("toastText")
        self.label.setWordWrap(True)
        layout.addWidget(self.label, 1)
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.animation = QPropertyAnimation(self.effect, b"opacity", self)
        self.animation.setDuration(220)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.finished.connect(self._animation_finished)
        self._fading_out = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._fade_out)
        self.hide()

    def show_message(self, text: str, kind: str = "success", msecs: int = 2600):
        icon = {"success": ("check_circle", "success"), "error": ("alert", "danger"), "info": ("info", "accent")}
        name, role = icon.get(kind, icon["info"])
        self.icon.set_kind(name, role)
        self.setProperty("kind", kind)
        repolish(self)
        self.label.setText(text)
        self.setMaximumWidth(min(520, self.parentWidget().width() - 40))
        self.adjustSize()
        self._place()
        self.raise_()
        self.show()
        self.animation.stop()
        self._fading_out = False
        self.animation.setStartValue(self.effect.opacity() if self.isVisible() else 0.0)
        self.animation.setEndValue(1.0)
        self.animation.start()
        self.timer.start(msecs)

    def _place(self):
        parent = self.parentWidget()
        self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 28)

    def _fade_out(self):
        self.animation.stop()
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)
        self._fading_out = True
        self.animation.start()

    def _animation_finished(self):
        if self._fading_out:
            self.hide()


def fade_in(widget: QWidget, duration: int = 160):
    """Briefly fade a page in. The effect is removed afterwards so it costs nothing at rest."""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.OutCubic)
    animation.finished.connect(lambda: widget.setGraphicsEffect(None))
    animation.start(QPropertyAnimation.DeleteWhenStopped)
    return animation


# ============================================================================= layout utilities
class FlowLayout(QLayout):
    """Wraps child widgets onto new lines, like words in a paragraph (used for suggestion chips)."""

    def __init__(self, parent=None, spacing: int = 8, center: bool = True):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self._center = center
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):  # noqa: N802 - Qt API
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientations(0)

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, width):  # noqa: N802
        return self._layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):  # noqa: N802
        super().setGeometry(rect)
        self._layout(rect, apply=True)

    def sizeHint(self):  # noqa: N802
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _layout(self, rect, apply):
        lines, line, line_width = [], [], 0
        for item in self._items:
            hint = item.sizeHint()
            needed = hint.width() + (self._spacing if line else 0)
            if line and line_width + needed > rect.width():
                lines.append((line, line_width))
                line, line_width = [], 0
                needed = hint.width()
            line.append(item)
            line_width += needed
        if line:
            lines.append((line, line_width))
        y = rect.y()
        for items, width in lines:
            height = max(item.sizeHint().height() for item in items)
            x = rect.x() + (max(0, (rect.width() - width) // 2) if self._center else 0)
            for item in items:
                hint = item.sizeHint()
                if apply:
                    item.setGeometry(QRect(QPoint(x, y), hint))
                x += hint.width() + self._spacing
            y += height + self._spacing
        return max(0, y - rect.y() - self._spacing)


class ElidedLabel(QLabel):
    """Single-line label that ends with an ellipsis instead of stretching its parent."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full = ""
        self.setMinimumWidth(10)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setText(text)

    def setText(self, text):  # noqa: N802
        self._full = str(text or "")
        self.setToolTip(self._full)
        self._elide()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self):
        metrics = self.fontMetrics()
        super().setText(metrics.elidedText(self._full, Qt.ElideRight, max(10, self.width())))
