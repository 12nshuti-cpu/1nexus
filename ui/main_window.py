from html import escape  # noqa: I001
import math
import os
import platform
import socket
import subprocess
import threading
import time
import shutil
from pathlib import Path
from markdown import markdown

try:
    import psutil
except Exception:  # noqa: BLE001
    psutil = None

from PySide6.QtCore import (
    Qt,
    QEvent,
    QThread,
    QTimer,
    QObject,
    QProcess,
    Signal,
    QRectF,
    QPointF,
    QSize,
    QSettings,
)

from PySide6.QtGui import (
    QTextCursor,
    QTextDocument,  # noqa: F401
    QPainter,
    QPen,
    QBrush,
    QFont,
    QFontMetrics,
    QColor,
    QPainterPath,  # noqa: F401
    QTextOption,
)

from PySide6.QtWidgets import (
    QApplication,  # noqa: F401
    QColorDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QDialog,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QGridLayout,
    QComboBox,
    QProgressBar,
    QWidget,
    QInputDialog,
    QMessageBox,
    QMenu,
)

from config.settings import NEXUSSettings
from core.ai_worker import AIWorker
from core.commands import CommandEngine
from core.conversation_manager import ConversationManager
from core.system_monitor import SystemMonitor
from core.system_check import NEXUSSystemChecker
from core.voice_worker import VoiceSpeakWorker
from core.shell_worker import ShellCommandWorker
from config import settings as nexus_settings
from ui.styles import DARK_THEME
from ui.system_check_dialog import SystemCheckDialog
from ui.settings_page import SettingsPage

# ============================================================
# CIRCULAR SYSTEM METER
# ============================================================


class CircularMeter(QWidget):

    def __init__(
        self,
        title="CPU",
        value=0,
        suffix="%",
        color="#45d9ff",
        show_title=True,
        parent=None,
    ):
        super().__init__(parent)

        self.title = title
        self.value = float(value)
        self.suffix = suffix
        self.color = color
        self.show_title = bool(show_title)
        self.center_label = ""

        self.setMinimumSize(145 if self.show_title else 88, 145 if self.show_title else 88)
        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

    def setValue(self, value):
        try:
            self.value = max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            self.value = 0.0

        self.update()

    def paintEvent(self, event):

        painter = QPainter(self)

        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()

        size = min(
            rect.width(),
            rect.height(),
        )

        center = QPointF(rect.center())

        radius = (size / 2) - 15

        # ----------------------------------------------------
        # OUTER GLOW RING
        # ----------------------------------------------------

        glow_pen = QPen(
            QBrush("#10354a"),
            10,
        )

        painter.setPen(glow_pen)
        painter.setBrush(Qt.NoBrush)

        painter.drawEllipse(
            center,
            radius,
            radius,
        )

        # ----------------------------------------------------
        # BACKGROUND RING
        # ----------------------------------------------------

        background_pen = QPen(
            QBrush("#122536"),
            8,
        )

        painter.setPen(background_pen)

        painter.drawEllipse(
            center,
            radius,
            radius,
        )

        # ----------------------------------------------------
        # VALUE ARC
        # ----------------------------------------------------

        value_pen = QPen(
            QBrush(self.color),
            8,
        )

        value_pen.setCapStyle(Qt.RoundCap)

        painter.setPen(value_pen)

        arc_rect = QRectF(
            center.x() - radius,
            center.y() - radius,
            radius * 2,
            radius * 2,
        )

        start_angle = 90 * 16
        span_angle = -(self.value / 100) * 360 * 16

        painter.drawArc(
            arc_rect,
            start_angle,
            span_angle,
        )

        # ----------------------------------------------------
        # INNER CIRCLE
        # ----------------------------------------------------

        inner_radius = radius - 18

        painter.setPen(
            QPen(
                QBrush("#0a1724"),
                1,
            )
        )

        painter.setBrush(QBrush("#0a1724"))

        painter.drawEllipse(
            center,
            inner_radius,
            inner_radius,
        )

        # ----------------------------------------------------
        # VALUE TEXT
        # ----------------------------------------------------

        value_font = QFont(
            "Segoe UI",
            20,
        )

        value_font.setBold(True)

        painter.setFont(value_font)
        painter.setPen(
            QPen(
                QBrush("#e8f6ff"),
                1,
            )
        )

        value_text = f"{self.value:.0f}{self.suffix}"

        value_rect = QRectF(
            center.x() - 50,
            center.y() - 18,
            100,
            36,
        )

        painter.drawText(
            value_rect,
            Qt.AlignCenter,
            value_text,
        )

        if self.center_label:
            caption_font = QFont("Segoe UI", 8)
            caption_font.setBold(False)
            painter.setFont(caption_font)
            painter.setPen(QPen(QColor("#78a7bb"), 1))
            caption_rect = QRectF(
                center.x() - 45,
                center.y() + 13,
                90,
                20,
            )
            painter.drawText(caption_rect, Qt.AlignCenter, str(self.center_label))

        # ----------------------------------------------------
        # TITLE
        # ----------------------------------------------------

        if self.show_title:
            title_font = QFont(
                "Segoe UI",
                8,
            )

            title_font.setBold(True)

            painter.setFont(title_font)
            painter.setPen(
                QPen(
                    QBrush("#5f8298"),
                    1,
                )
            )

            title_rect = QRectF(
                center.x() - 55,
                center.y() + 20,
                110,
                20,
            )

            painter.drawText(
                title_rect,
                Qt.AlignCenter,
                self.title.upper(),
            )

        painter.end()


class HudIcon(QWidget):
    """Small vector-style HUD icon drawn locally with QPainter."""

    def __init__(self, kind="dot", size=24, parent=None):
        super().__init__(parent)
        self.kind = str(kind or "dot")
        self.icon_size = int(size)
        self.setFixedSize(self.icon_size, self.icon_size)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def _pen(self):
        color = self.property("hudColor") or "#61e8ff"
        pen = QPen(QColor(str(color)), max(1.8, self.icon_size / 11))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        return pen

    def paintEvent(self, event):  # noqa: ARG002
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(self._pen())
        p.setBrush(Qt.NoBrush)
        r = QRectF(3, 3, self.width() - 6, self.height() - 6)
        cx = r.center().x()
        cy = r.center().y()
        w = r.width()
        h = r.height()

        kind = self.kind.lower()
        if kind == "menu":
            for offset in (-0.22, 0.0, 0.22):
                y = cy + h * offset
                p.drawLine(cx - w * 0.34, y, cx + w * 0.34, y)
        elif kind == "nexus":
            outer = min(w, h) * 0.37
            p.drawEllipse(QPointF(cx, cy), outer, outer)
            p.drawEllipse(QPointF(cx, cy), outer * 0.58, outer * 0.58)
            p.drawEllipse(QPointF(cx, cy), outer * 0.20, outer * 0.20)
            p.drawEllipse(QPointF(cx, cy), outer * 0.08, outer * 0.08)
            p.drawArc(QRectF(cx - outer * 1.02, cy - outer * 0.55, outer * 2.04, outer * 1.10), 20 * 16, 140 * 16)
            p.drawArc(QRectF(cx - outer * 1.02, cy - outer * 0.55, outer * 2.04, outer * 1.10), 200 * 16, 140 * 16)
        elif kind == "search":
            radius = min(w, h) * 0.31
            p.drawEllipse(QPointF(cx - 2, cy - 2), radius, radius)
            p.drawLine(cx + radius * 0.55, cy + radius * 0.55, r.right() - 1, r.bottom() - 1)
        elif kind == "bell":
            p.drawArc(QRectF(cx - w * .28, cy - h * .30, w * .56, h * .58), 15 * 16, 150 * 16)
            p.drawLine(cx - w * .28, cy + h * .16, cx + w * .28, cy + h * .16)
            p.drawLine(cx - w * .34, cy + h * .26, cx + w * .34, cy + h * .26)
            p.drawEllipse(QPointF(cx, cy + h * .34), w * .06, h * .06)
        elif kind in {"settings", "gear"}:
            p.drawEllipse(QPointF(cx, cy), w * .18, h * .18)
            for i in range(8):
                import math as _math
                a = i * _math.pi / 4
                x1 = cx + _math.cos(a) * w * .25
                y1 = cy + _math.sin(a) * h * .25
                x2 = cx + _math.cos(a) * w * .42
                y2 = cy + _math.sin(a) * h * .42
                p.drawLine(x1, y1, x2, y2)
            p.drawEllipse(QPointF(cx, cy), w * .35, h * .35)
        elif kind == "profile":
            p.drawEllipse(QPointF(cx, cy - h * .18), w * .17, h * .17)
            p.drawArc(QRectF(cx - w * .31, cy + h * .01, w * .62, h * .48), 0, 180 * 16)
        elif kind == "home":
            path = QPainterPath()
            path.moveTo(cx, r.top() + h * .22)
            path.lineTo(r.left() + w * .10, cy)
            path.lineTo(r.left() + w * .10, r.bottom() - h * .04)
            path.lineTo(r.right() - w * .10, r.bottom() - h * .04)
            path.lineTo(r.right() - w * .10, cy)
            path.closeSubpath()
            p.drawPath(path)
            p.drawLine(cx - w * .08, r.bottom() - h * .04, cx - w * .08, cy + h * .10)
            p.drawLine(cx - w * .08, cy + h * .10, cx + w * .10, cy + h * .10)
        elif kind == "assistant":
            p.drawRoundedRect(QRectF(r.left() + 1, r.top() + 2, w - 2, h - 5), 6, 6)
            p.drawLine(cx, r.bottom() - 3, cx - w * .13, r.bottom() + 1)
            for dx in (-w * .16, 0, w * .16):
                p.drawEllipse(QPointF(cx + dx, cy), 1.3, 1.3)
        elif kind in {"system", "monitor"}:
            p.drawRoundedRect(QRectF(r.left() + 1, r.top() + 2, w - 2, h * .60), 3, 3)
            p.drawLine(cx - w * .13, r.bottom() - 3, cx + w * .13, r.bottom() - 3)
            p.drawLine(cx, r.bottom() - h * .10, cx, r.bottom() - 3)
        elif kind == "activity":
            p.drawLine(r.left() + 1, r.bottom() - 3, r.right() - 1, r.bottom() - 3)
            pts = [
                (r.left() + 2, r.bottom() - h * .36),
                (r.left() + w * .23, r.bottom() - h * .18),
                (r.left() + w * .44, r.bottom() - h * .47),
                (r.left() + w * .64, r.bottom() - h * .27),
                (r.right() - 2, r.bottom() - h * .64),
            ]
            for a, b in zip(pts, pts[1:]):
                p.drawLine(QPointF(*a), QPointF(*b))
        elif kind == "chat":
            p.drawRoundedRect(QRectF(r.left() + 1, r.top() + 2, w - 2, h * .66), 5, 5)
            p.drawLine(cx - w * .18, r.top() + h * .66, cx - w * .05, r.bottom() - 2)
        elif kind == "plus":
            p.drawLine(cx, r.top() + 3, cx, r.bottom() - 3)
            p.drawLine(r.left() + 3, cy, r.right() - 3, cy)
        elif kind == "trash":
            p.drawRoundedRect(QRectF(cx - w * .22, cy - h * .08, w * .44, h * .40), 2, 2)
            p.drawLine(cx - w * .28, cy - h * .18, cx + w * .28, cy - h * .18)
            p.drawLine(cx - w * .10, cy - h * .25, cx + w * .10, cy - h * .25)
            p.drawLine(cx - w * .08, cy, cx - w * .08, cy + h * .20)
            p.drawLine(cx + w * .08, cy, cx + w * .08, cy + h * .20)
        elif kind == "send":
            path = QPainterPath()
            path.moveTo(r.left() + 2, r.top() + 3)
            path.lineTo(r.right() - 2, cy)
            path.lineTo(r.left() + 2, r.bottom() - 3)
            path.lineTo(r.left() + w * .18, cy)
            path.closeSubpath()
            p.drawPath(path)
            p.drawLine(r.left() + w * .18, cy, r.right() - 2, cy)
        elif kind == "mic":
            # Clear, conventional microphone shape. Everything is kept inside
            # the widget rect so it cannot touch or overlap the button edge.
            capsule = QRectF(
                cx - w * 0.145,
                r.top() + h * 0.08,
                w * 0.29,
                h * 0.47,
            )
            p.drawRoundedRect(capsule, w * 0.145, w * 0.145)
            p.drawArc(
                QRectF(
                    cx - w * 0.30,
                    r.top() + h * 0.20,
                    w * 0.60,
                    h * 0.49,
                ),
                205 * 16,
                130 * 16,
            )
            p.drawLine(cx, r.top() + h * 0.69, cx, r.top() + h * 0.83)
            p.drawLine(
                cx - w * 0.17,
                r.bottom() - h * 0.08,
                cx + w * 0.17,
                r.bottom() - h * 0.08,
            )
        elif kind == "info":
            p.drawEllipse(QPointF(cx, cy), w * .36, h * .36)
            p.drawLine(cx, cy - h * .05, cx, cy + h * .20)
            p.drawEllipse(QPointF(cx, cy - h * .19), 1.2, 1.2)
        elif kind == "help":
            p.drawEllipse(QPointF(cx, cy), w * .36, h * .36)
            p.drawArc(QRectF(cx - w * .13, cy - h * .17, w * .26, h * .26), 25 * 16, 220 * 16)
            p.drawEllipse(QPointF(cx, cy + h * .19), 1.2, 1.2)
        elif kind == "cpu":
            chip = QRectF(cx - w * .24, cy - h * .24, w * .48, h * .48)
            p.drawRoundedRect(chip, 3, 3)
            p.drawRect(QRectF(cx - w * .11, cy - h * .11, w * .22, h * .22))
            for d in (-.30, 0, .30):
                p.drawLine(cx - w * .43, cy + h * d, cx - w * .26, cy + h * d)
                p.drawLine(cx + w * .26, cy + h * d, cx + w * .43, cy + h * d)
                p.drawLine(cx + w * d, cy - h * .43, cx + w * d, cy - h * .26)
                p.drawLine(cx + w * d, cy + h * .26, cx + w * d, cy + h * .43)
        elif kind == "memory":
            p.drawRoundedRect(QRectF(cx - w * .34, cy - h * .20, w * .68, h * .40), 3, 3)
            for i in range(4):
                x = cx - w * .23 + i * w * .15
                p.drawRect(QRectF(x, cy - h * .09, w * .07, h * .18))
            for i in range(5):
                x = cx - w * .30 + i * w * .15
                p.drawLine(x, cy - h * .31, x, cy - h * .20)
                p.drawLine(x, cy + h * .20, x, cy + h * .31)
        elif kind == "storage":
            p.drawRoundedRect(QRectF(cx - w * .28, cy - h * .34, w * .56, h * .68), 3, 3)
            p.drawLine(cx - w * .18, cy - h * .07, cx + w * .18, cy - h * .07)
            p.drawEllipse(QPointF(cx - w * .13, cy + h * .18), 1.5, 1.5)
            p.drawEllipse(QPointF(cx + w * .13, cy + h * .18), 1.5, 1.5)
        elif kind == "battery":
            p.drawRoundedRect(QRectF(cx - w * .32, cy - h * .20, w * .60, h * .40), 3, 3)
            p.drawRect(QRectF(cx + w * .29, cy - h * .09, w * .10, h * .18))
            p.drawLine(cx - w * .19, cy, cx + w * .15, cy)
        elif kind == "calendar":
            p.drawRoundedRect(QRectF(cx - w * .34, cy - h * .30, w * .68, h * .60), 3, 3)
            p.drawLine(cx - w * .34, cy - h * .08, cx + w * .34, cy - h * .08)
            p.drawLine(cx - w * .17, cy - h * .40, cx - w * .17, cy - h * .24)
            p.drawLine(cx + w * .17, cy - h * .40, cx + w * .17, cy - h * .24)
            p.drawEllipse(QPointF(cx - w * .15, cy + h * .10), 1.3, 1.3)
            p.drawEllipse(QPointF(cx + w * .15, cy + h * .10), 1.3, 1.3)
        elif kind == "download":
            p.drawLine(cx, cy - h * .31, cx, cy + h * .13)
            p.drawLine(cx - w * .15, cy - h * .01, cx, cy + h * .15)
            p.drawLine(cx + w * .15, cy - h * .01, cx, cy + h * .15)
            p.drawLine(cx - w * .30, cy + h * .31, cx + w * .30, cy + h * .31)
        elif kind == "play":
            path = QPainterPath()
            path.moveTo(cx - w * .18, cy - h * .28)
            path.lineTo(cx + w * .28, cy)
            path.lineTo(cx - w * .18, cy + h * .28)
            path.closeSubpath()
            p.drawPath(path)
        elif kind == "bolt":
            path = QPainterPath()
            path.moveTo(cx + w * .12, r.top())
            path.lineTo(cx - w * .13, cy - h * .03)
            path.lineTo(cx + w * .02, cy - h * .03)
            path.lineTo(cx - w * .12, r.bottom())
            path.lineTo(cx + w * .18, cy + h * .02)
            path.lineTo(cx + w * .02, cy + h * .02)
            path.closeSubpath()
            p.drawPath(path)
        elif kind == "chevron":
            p.drawLine(cx - w * .12, cy - h * .22, cx + w * .14, cy)
            p.drawLine(cx + w * .14, cy, cx - w * .12, cy + h * .22)
        elif kind == "thermometer":
            bulb_r = w * 0.16
            p.drawLine(cx, r.top() + h * 0.08, cx, cy + h * 0.17)
            p.drawEllipse(QPointF(cx, cy + h * 0.23), bulb_r, bulb_r)
            p.drawLine(cx - w * 0.10, r.top() + h * 0.20, cx + w * 0.10, r.top() + h * 0.20)
            p.drawLine(cx - w * 0.10, r.top() + h * 0.34, cx + w * 0.10, r.top() + h * 0.34)
        elif kind == "gpu":
            chip = QRectF(cx - w * 0.29, cy - h * 0.22, w * 0.58, h * 0.44)
            p.drawRoundedRect(chip, 3, 3)
            p.drawRect(QRectF(cx - w * 0.15, cy - h * 0.10, w * 0.30, h * 0.20))
            for d in (-0.20, 0.20):
                p.drawLine(cx - w * 0.43, cy + h * d, cx - w * 0.30, cy + h * d)
                p.drawLine(cx + w * 0.30, cy + h * d, cx + w * 0.43, cy + h * d)
                p.drawLine(cx + w * d, cy - h * 0.35, cx + w * d, cy - h * 0.22)
                p.drawLine(cx + w * d, cy + h * 0.22, cx + w * d, cy + h * 0.35)
        elif kind == "upload":
            p.drawLine(cx, cy + h * 0.30, cx, cy - h * 0.14)
            p.drawLine(cx - w * 0.16, cy - h * 0.01, cx, cy - h * 0.17)
            p.drawLine(cx + w * 0.16, cy - h * 0.01, cx, cy - h * 0.17)
            p.drawLine(cx - w * 0.30, cy + h * 0.30, cx + w * 0.30, cy + h * 0.30)
        elif kind in {"network", "wifi"}:
            p.drawArc(QRectF(cx - w * .36, cy - h * .24, w * .72, h * .62), 35 * 16, 110 * 16)
            p.drawArc(QRectF(cx - w * .24, cy - h * .10, w * .48, h * .42), 35 * 16, 110 * 16)
            p.drawEllipse(QPointF(cx, cy + h * .19), w * .06, h * .06)
        elif kind in {"clock", "uptime"}:
            p.drawEllipse(QPointF(cx, cy), w * .35, h * .35)
            p.drawLine(cx, cy, cx, cy - h * .18)
            p.drawLine(cx, cy, cx + w * .14, cy + h * .08)
        elif kind in {"database", "disk"}:
            p.drawEllipse(QPointF(cx, cy - h * .24), w * .28, h * .11)
            p.drawArc(QRectF(cx - w * .28, cy - h * .24, w * .56, h * .48), 180 * 16, 180 * 16)
            p.drawLine(cx - w * .28, cy - h * .24, cx - w * .28, cy + h * .24)
            p.drawLine(cx + w * .28, cy - h * .24, cx + w * .28, cy + h * .24)
            p.drawEllipse(QPointF(cx, cy + h * .24), w * .28, h * .11)
        elif kind == "process":
            p.drawRect(QRectF(cx - w * .26, cy - h * .22, w * .52, h * .44))
            p.drawLine(cx - w * .17, cy - h * .08, cx + w * .17, cy - h * .08)
            p.drawLine(cx - w * .17, cy + h * .08, cx + w * .08, cy + h * .08)
        elif kind == "waveform":
            pts = [
                (r.left(), cy), (r.left() + w * .16, cy),
                (r.left() + w * .23, cy - h * .26),
                (r.left() + w * .32, cy + h * .23),
                (r.left() + w * .41, cy - h * .11),
                (r.left() + w * .52, cy), (r.right(), cy),
            ]
            for a, b in zip(pts, pts[1:]):
                p.drawLine(QPointF(*a), QPointF(*b))
        else:
            p.drawEllipse(QPointF(cx, cy), w * .15, h * .15)

        p.end()

    def setKind(self, kind):
        self.kind = str(kind or "dot")
        self.update()


class CompactProgressBar(QWidget):
    """High-contrast horizontal percentage bar used by the system reference UI."""

    def __init__(self, color="#45d9ff", parent=None):
        super().__init__(parent)
        self.value = 0.0
        self.color = QColor(color)
        self.setMinimumHeight(9)
        self.setMaximumHeight(9)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setValue(self, value):
        try:
            self.value = max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            self.value = 0.0
        self.update()

    def paintEvent(self, event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0, 1, 0, -1)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#0c2a3f"))
        painter.drawRoundedRect(rect, 4, 4)
        fill = rect.width() * (self.value / 100.0)
        if fill > 0:
            painter.setBrush(self.color)
            painter.drawRoundedRect(QRectF(rect.left(), rect.top(), fill, rect.height()), 4, 4)
        painter.end()


class SystemMiniGraphWidget(QWidget):
    """Small two-line live chart matching the reference statistics rail."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cpu_data = []
        self.memory_data = []
        self.setMinimumSize(150, 100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def setData(self, cpu_data, memory_data):
        self.cpu_data = [float(v) for v in (cpu_data or [])][-28:]
        self.memory_data = [float(v) for v in (memory_data or [])][-28:]
        self.update()

    def paintEvent(self, event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        painter.fillRect(rect, QColor("#061522"))
        left, top = rect.left() + 18, rect.top() + 5
        width, height = max(40.0, rect.width() - 24), max(45.0, rect.height() - 21)

        painter.setPen(QPen(QColor("#102d40"), 1))
        for i in range(4):
            y = top + height * i / 3
            painter.drawLine(QPointF(left, y), QPointF(left + width, y))
        for i in range(5):
            x = left + width * i / 4
            painter.drawLine(QPointF(x, top), QPointF(x, top + height))

        painter.setFont(QFont("Segoe UI", 6))
        painter.setPen(QPen(QColor("#4e7387"), 1))
        for label, fraction in (("100", 0), ("50", .5), ("0", 1)):
            y = top + height * fraction
            painter.drawText(0, int(y + 3), 16, 10, Qt.AlignRight, label)

        def draw(data, color):
            if len(data) < 2:
                return
            points = []
            for index, value in enumerate(data):
                x = left + width * index / max(1, len(data) - 1)
                y = top + height - max(0, min(100, value)) / 100.0 * height
                points.append(QPointF(x, y))
            path = QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)
            painter.setPen(QPen(QColor(color), 1.6))
            painter.drawPath(path)

        draw(self.cpu_data, "#35d5ff")
        draw(self.memory_data, "#9663ff")
        painter.end()


class NexusCoreWidget(QWidget):
    """State-aware rotating reactor visual for the NEXUS dashboard."""

    STATE_COLORS = {
        "sleeping": QColor("#157d98"),
        "listening": QColor("#00e7a1"),
        "thinking": QColor("#ffd000"),
        "speaking": QColor("#ff8a00"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.phase = 0.0
        self.state = "sleeping"
        self.state_colors = dict(self.STATE_COLORS)
        self.setMinimumSize(260, 250)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.advance)
        self.animation_timer.start(35)

    def set_state(self, state):
        state = str(state or "sleeping").strip().lower()
        if state not in self.STATE_COLORS:
            state = "sleeping"
        if state != self.state:
            self.state = state
            self.update()

    def set_state_color(self, state, color):
        if state not in self.STATE_COLORS:
            return
        qcolor = QColor(color)
        if qcolor.isValid():
            self.state_colors[state] = qcolor
            self.update()

    def advance(self):
        # The rings keep moving in standby too, but at a calm pace.
        speed = 0.018 if self.state == "sleeping" else 0.043
        self.phase = (self.phase + speed) % (math.pi * 2)
        self.update()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#020b10"))
        color = self.state_colors[self.state]
        width, height = self.width(), self.height()
        center = QPointF(width / 2, height * 0.455)
        radius = max(55.0, min(width * 0.355, height * 0.385))

        # Fine radar grid, quiet crosshair, and the four HUD corner marks.
        painter.setPen(QPen(QColor(8, 73, 91, 75), 1))
        for x in range(10, width, 36):
            painter.drawLine(x, 0, x, height)
        for y in range(8, height, 36):
            painter.drawLine(0, y, width, y)
        painter.setPen(QPen(QColor(11, 96, 115, 115), 1))
        painter.drawLine(0, int(center.y()), width, int(center.y()))
        painter.drawLine(int(center.x()), 0, int(center.x()), height - 44)
        painter.setPen(QPen(QColor(13, 129, 153, 180), 1.2))
        corner = 20
        for x, y, sx, sy in (
            (12, 12, 1, 1), (width - 12, 12, -1, 1),
            (12, height - 12, 1, -1), (width - 12, height - 12, -1, -1),
        ):
            painter.drawLine(x, y, x + sx * corner, y)
            painter.drawLine(x, y, x, y + sy * corner)

        # Multiple broken rings, each rotating at a slightly different rate.
        painter.setBrush(Qt.NoBrush)
        for index, (scale, base_alpha, pen_width) in enumerate(
            ((1.00, 210, 1.35), (0.84, 160, 1.0), (0.64, 135, 1.0), (0.43, 150, 1.1))
        ):
            ring_radius = radius * scale
            ring_rect = QRectF(
                center.x() - ring_radius,
                center.y() - ring_radius,
                ring_radius * 2,
                ring_radius * 2,
            )
            painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), base_alpha), pen_width))
            painter.drawEllipse(ring_rect)
            painter.save()
            painter.translate(center)
            painter.rotate(math.degrees(self.phase * (1 if index % 2 == 0 else -0.72) + index * 37))
            painter.translate(-center)
            painter.setPen(QPen(color, 2.0 if index in (0, 3) else 1.5))
            painter.drawArc(ring_rect, 12 * 16, (70 + index * 13) * 16)
            painter.drawArc(ring_rect, (182 + index * 29) * 16, (43 + index * 11) * 16)
            painter.restore()

        # Radial graduations and highlighted sweep marks.
        outer_radius = radius * 1.075
        for index in range(96):
            angle = self.phase + (math.tau * index / 96)
            major = index % 8 == 0
            inner = outer_radius - (radius * (0.075 if major else 0.032))
            p1 = QPointF(center.x() + math.cos(angle) * inner, center.y() + math.sin(angle) * inner)
            p2 = QPointF(center.x() + math.cos(angle) * outer_radius, center.y() + math.sin(angle) * outer_radius)
            tick_color = color if index % 24 == 0 else QColor(17, 116, 137, 185)
            painter.setPen(QPen(tick_color, 1.35 if major else 0.8))
            painter.drawLine(p1, p2)

        # Core disk and breathing halo.
        disk_radius = radius * 0.36
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), 21))
        painter.drawEllipse(center, disk_radius * 1.36, disk_radius * 1.36)
        painter.setBrush(QColor("#03151d"))
        painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 210), 1.7))
        painter.drawEllipse(center, disk_radius, disk_radius)

        painter.setPen(QPen(QColor("#d5f7ff")))
        brand_font = QFont("Segoe UI", max(16, int(disk_radius * 0.34)))
        brand_font.setBold(True)
        brand_font.setLetterSpacing(QFont.AbsoluteSpacing, 5)
        painter.setFont(brand_font)
        painter.drawText(QRectF(center.x() - disk_radius * 1.5, center.y() - 18, disk_radius * 3, 34), Qt.AlignCenter, "NEXUS")
        painter.setPen(QPen(color))
        painter.setFont(QFont("Consolas", 8, QFont.DemiBold))
        painter.drawText(QRectF(center.x() - disk_radius, center.y() + 15, disk_radius * 2, 20), Qt.AlignCenter, "AI CORE")

        # Animated signal bars and the explicit state label anchor the visual.
        label_y = height - 29
        bars_width = min(width * 0.56, 420)
        bars_left = (width - bars_width) / 2
        bar_count = 42
        gap = 2.0
        bar_width = max(2.0, (bars_width - gap * (bar_count - 1)) / bar_count)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), 145))
        for index in range(bar_count):
            wave = (math.sin(self.phase * 2 + index * 0.53) + 1) / 2
            bar_height = 3 + wave * (8 if self.state != "sleeping" else 3)
            x = bars_left + index * (bar_width + gap)
            painter.drawRect(QRectF(x, height - 12 - bar_height, bar_width, bar_height))
        painter.setPen(QPen(color))
        label_font = QFont("Consolas", 10, QFont.Bold)
        label_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        painter.setFont(label_font)
        painter.drawText(QRectF(0, label_y - 2, width, 20), Qt.AlignCenter, self.state.upper())
        painter.end()


class MiniSparklineWidget(QWidget):
    """Compact telemetry sparkline used by dashboard metric cards."""

    def __init__(self, color="#45d9ff", parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.values = []
        self.setMinimumHeight(28)
        self.setMaximumHeight(34)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setData(self, values):
        self.values = [float(v) for v in (values or [])][-32:]
        self.update()

    def paintEvent(self, event):  # noqa: ARG002
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 4, -2, -4)

        p.fillRect(self.rect(), QColor("#061522"))
        p.setPen(QPen(QColor("#0c2a3d"), 1))
        p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())

        if len(self.values) < 2:
            p.setPen(QPen(QColor("#20465b"), 1))
            p.drawLine(r.left(), r.center().y(), r.right(), r.center().y())
            p.end()
            return

        lo = min(self.values)
        hi = max(self.values)
        span = max(1.0, hi - lo)
        points = []
        for i, value in enumerate(self.values):
            x = r.left() + (r.width() * i / max(1, len(self.values) - 1))
            y = r.bottom() - ((value - lo) / span) * r.height()
            points.append(QPointF(x, y))

        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)

        p.setPen(QPen(self.color, 1.8))
        p.drawPath(path)

        p.setPen(Qt.NoPen)
        p.setBrush(self.color)
        p.drawEllipse(points[-1], 2.1, 2.1)
        p.end()


class VoiceCaptureWorker(QThread):
    """Keeps microphone capture and speech recognition off the interface thread.

    Two routes, chosen by :meth:`route`:

    * ``local``  - record with the microphone, transcribe on this computer with
      faster-whisper, then hand the text to the normal NEXUS pipeline
      (``captured``). Tools, memory and the speech engine all apply.
    * ``gemini`` - the existing Gemini Live voice turn (online, needs a key).
    """

    captured = Signal(str, str)
    geminiCompleted = Signal(str, str, bytes)
    failed = Signal(str)
    status = Signal(str)

    NO_SPEECH = "No speech detected."

    def __init__(self, language="auto", engine="automatic", conversation=None, parent=None, settings=None):
        super().__init__(parent)
        self.language = str(language or "auto")
        self.engine = str(engine or "automatic")
        self.conversation = list(conversation or [])
        self.settings = settings
        self._recorder = None
        self._cancelled = False

    @staticmethod
    def route(engine):
        """'local' (on-device speech recognition) or 'gemini' (Gemini Live)."""
        from core.gemini_engine import gemini_is_configured

        engine = str(engine or "automatic")
        if engine == "local":
            return "local"
        if engine == "automatic" and not gemini_is_configured():
            return "local"
        return "gemini"

    # -- control from the UI thread ------------------------------------------
    def finish_listening(self):
        """Stop recording now and transcribe what was heard."""
        recorder = self._recorder
        if recorder is not None:
            recorder.finish()

    def cancel(self):
        """Stop recording and throw the audio away."""
        self._cancelled = True
        recorder = self._recorder
        if recorder is not None:
            recorder.cancel()

    # -- worker thread ----------------------------------------------------------
    def run(self):
        try:
            if self.route(self.engine) == "local":
                self._run_local()
            else:
                self._run_gemini()
        except Exception as error:  # noqa: BLE001
            self.failed.emit(str(error))

    def _run_local(self):
        from core.stt import EndpointConfig, LocalTranscriber, MicrophoneRecorder

        settings = self.settings
        push_to_talk = bool(settings.push_to_talk) if settings is not None else False
        device = settings.microphone_device if settings is not None else None
        model = settings.stt_model if settings is not None else "base"
        config = EndpointConfig(auto_stop=not push_to_talk, max_seconds=120.0 if push_to_talk else 30.0)

        self.status.emit("Listening - click the microphone again when you are done." if push_to_talk
                         else "Listening - just speak; I will stop when you pause.")
        self._recorder = MicrophoneRecorder(device=device, config=config)
        audio = self._recorder.record()
        self._recorder = None
        if audio is None:
            note = "Listening cancelled." if self._cancelled else ""
            self.captured.emit(f"{self.NO_SPEECH} {note}".strip(), "auto")
            return

        self.status.emit("Transcribing...")
        text, detected = LocalTranscriber(model, status=self.status.emit).transcribe(audio, self.language)
        if not text:
            self.captured.emit(self.NO_SPEECH, "auto")
            return
        self.captured.emit(text, self.language if self.language != "auto" else detected)

    def _run_gemini(self):
        from core.gemini_engine import GeminiUnavailable, gemini_is_configured, live_microphone_turn
        from config import settings as app_settings
        import asyncio

        if not gemini_is_configured():
            raise GeminiUnavailable(
                "Gemini Live voice needs an API key. Add it in Settings or set the GEMINI_API_KEY environment variable. "
                "Choose Automatic or Local mode to use on-device speech recognition instead."
            )
        transcript, answer, audio = asyncio.run(live_microphone_turn(
            app_settings.load_system_prompt(),
            self.conversation,
        ))
        if not answer:
            raise GeminiUnavailable("Gemini Live returned no spoken response. Try again or type your request.")
        self.geminiCompleted.emit(transcript or "Voice message", answer, audio)
        if audio:
            import numpy as np
            import sounddevice as sd
            sd.play(np.frombuffer(audio, dtype=np.int16), samplerate=24000)
            sd.wait()


class DocumentSummaryWorker(QObject):
    """Reads a user-chosen text file and summarises it off the interface thread.

    Runs on a daemon Python thread (not a QThread) on purpose: if the user closes NEXUS while a
    summary is still being written, the thread can be abandoned safely. Killing a thread that is
    running Python code is never safe, and a QThread must not be destroyed while it runs.
    """

    done = Signal(str, str, str)       # file name, summary text, which engine produced it
    failed = Signal(str, bool)         # message, True if it is a problem with the file (not the AI)

    def __init__(self, ai_service, path, parent=None):
        super().__init__(parent)
        self.ai = ai_service
        self.path = path
        self._thread = None
        self._abandoned = False

    # -- QThread-like surface used by the window ------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._run, name="NEXUS-Summary", daemon=True)
        self._thread.start()

    def isRunning(self):
        return self._thread is not None and self._thread.is_alive()

    def wait(self, msecs=30000):
        if self._thread is not None:
            self._thread.join(timeout=msecs / 1000.0)
        return not self.isRunning()

    def abandon(self):
        """The window is closing: finish quietly without signalling anything."""
        self._abandoned = True

    # -- worker thread -------------------------------------------------------------
    def _emit(self, signal, *args):
        if not self._abandoned:
            signal.emit(*args)

    def _run(self):
        from core.documents import DocumentError, read_document
        from core.gemini_engine import redact_secrets

        try:
            document = read_document(self.path)
        except DocumentError as error:
            self._emit(self.failed, str(error), True)
            return
        try:
            summary, where = self.ai.summarize_document(
                document.name, document.text, document.truncated, document.total_chars
            )
            if not summary:
                raise RuntimeError("The model returned an empty summary.")
            if document.truncated:
                summary += (f"\n\n_Only the first {len(document.text):,} of {document.total_chars:,} "
                            "characters were summarised._")
            self._emit(self.done, document.name, redact_secrets(summary), where)
        except Exception as error:  # noqa: BLE001 - shown to the user as a failed request
            self._emit(self.failed, redact_secrets(f"I could not summarise {document.name}: {error}"), False)


# ============================================================
# TERMINAL INPUT
# ============================================================


class TerminalInput(QPlainTextEdit):

    sendRequested = Signal(str)
    clearRequested = Signal()
    newConversationRequested = Signal()

    def __init__(self, parent=None):

        super().__init__(parent)

        self.command_history = []
        self.history_index = -1

        self.setPlaceholderText("Ask Nexus anything...")

        self.setTabChangesFocus(False)

    def keyPressEvent(self, event):

        modifiers = event.modifiers()
        key = event.key()

        # ----------------------------------------------------
        # ENTER
        # ----------------------------------------------------

        if key in (
            Qt.Key_Return,
            Qt.Key_Enter,
        ):

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

        # ----------------------------------------------------
        # CTRL + L
        # ----------------------------------------------------

        if key == Qt.Key_L and modifiers & Qt.ControlModifier:
            self.clear()
            self.clearRequested.emit()
            return

        # ----------------------------------------------------
        # CTRL + N
        # ----------------------------------------------------

        if key == Qt.Key_N and modifiers & Qt.ControlModifier:
            self.newConversationRequested.emit()
            return

        # ----------------------------------------------------
        # ESCAPE
        # ----------------------------------------------------

        if key == Qt.Key_Escape:
            handler = getattr(self.window(), "interrupt_voice_output", None)
            if not callable(handler) or not handler():
                self.clear()
            return

        # ----------------------------------------------------
        # UP
        # ----------------------------------------------------

        if key == Qt.Key_Up:  # noqa: SIM102

            if self.command_history:

                if self.history_index == -1:
                    self.history_index = len(self.command_history) - 1

                elif self.history_index > 0:
                    self.history_index -= 1

                self.setPlainText(self.command_history[self.history_index])

                self.moveCursor(QTextCursor.End)

                return

        # ----------------------------------------------------
        # DOWN
        # ----------------------------------------------------

        if key == Qt.Key_Down:  # noqa: SIM102

            if self.command_history:

                if (
                    self.history_index != -1
                    and self.history_index < len(self.command_history) - 1
                ):
                    self.history_index += 1

                    self.setPlainText(self.command_history[self.history_index])

                else:
                    self.history_index = -1
                    self.clear()

                return

        super().keyPressEvent(event)

    def add_to_history(self, command):

        from core.gemini_engine import redact_secrets
        command = redact_secrets(command).strip()

        if not command:
            return

        if self.command_history and self.command_history[-1] == command:
            return

        self.command_history.append(command)

        if len(self.command_history) > 100:
            self.command_history.pop(0)


# ============================================================
# MAIN WINDOW
# ============================================================


class _SystemCheckBridge(QObject):
    """Carries startup-check results from a worker thread to the UI thread."""

    finished = Signal(list, str)


class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle("NEXUS")

        # Use the native Windows frame. This gives NEXUS the same dependable
        # edge/corner resizing behavior as a normal desktop application while
        # preserving minimize, maximize, and close controls.
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowSystemMenuHint
        )
        self.setAttribute(Qt.WA_NativeWindow, True)
        # Keep the complete dashboard usable on smaller laptop displays. The
        # page itself has responsive side rails, so a wide fixed minimum is
        # unnecessary and can push the native window off-screen.
        self.setMinimumSize(1000, 650)

        self.window_settings = QSettings("NEXUS", "NEXUS")
        self._accent_color = QColor(
            str(self.window_settings.value("ui_accent", "#45d9ff"))
        )
        if not self._accent_color.isValid():
            self._accent_color = QColor("#45d9ff")
        stored_geometry = self.window_settings.value("windowGeometry")
        restored = False
        if stored_geometry is not None:
            try:
                restored = self.restoreGeometry(stored_geometry)
            except Exception:
                restored = False

        # Fit the dashboard to the usable desktop on first launch, and keep a
        # saved geometry from ever exceeding the display after resolution or
        # scaling changes.
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            max_width = max(1000, available.width() - 24)
            max_height = max(650, available.height() - 24)
            if (not restored) or self.width() > max_width or self.height() > max_height:
                self.resize(max_width, max_height)
        elif not restored:
            self.resize(1480, 860)

        self._page_animation = None

        self.setStyleSheet(self.theme_for_accent(self._accent_color))

        # ----------------------------------------------------
        # SYSTEM VALUES
        # ----------------------------------------------------

        self.cpu_value = None
        self.memory_value = None
        self.storage_value = None
        self.battery_value = None

        self.dashboard_cpu = None
        self.dashboard_memory = None
        self.dashboard_storage = None
        self.dashboard_battery = None

        # ----------------------------------------------------
        # GRAPH DATA
        # ----------------------------------------------------

        self.cpu_history = []
        self.memory_history = []
        self.disk_history = []
        self.network_history = []

        self.max_graph_points = 40

        # ----------------------------------------------------
        # CORE SERVICES
        # ----------------------------------------------------

        self.command_engine = CommandEngine()

        self.conversation_manager = ConversationManager()

        # ----------------------------------------------------
        # CONVERSATION STATE
        # ----------------------------------------------------

        self.current_conversation_id = None
        self.activity_events = []

        self.ai_threads = {}
        self.ai_workers = {}

        self.voice_enabled = False
        self.voice_output_active = False
        self.voice_output_interrupted = False
        self.current_voice_language = "auto"
        self.pending_voice_language = "auto"
        self.ai_voice_languages = {}
        self.kokoro_speech_queue = None
        self.kokoro_streamed_conversations = set()
        self._kokoro_unavailable_notified = False

        self._started_at = __import__("datetime").datetime.now()
        self.ai_request_count = 0
        self.pending_ai_requests = 0
        self.ai_success_count = 0
        self.response_times = []
        self.response_started_at = {}
        self._thinking_active = False
        self.streaming_ai_responses = {}

        self.voice_speech_thread = None
        self.voice_speech_worker = None

        self.shell_thread = None
        self.shell_worker = None
        self.shell_conversation_id = None
        self.shell_response_language = "auto"
        self.shell_command = ""

        # ----------------------------------------------------
        # THINKING INDICATOR
        # ----------------------------------------------------

        self.thinking_timer = QTimer(self)
        self.thinking_timer.timeout.connect(self.update_thinking_indicator)
        self.thinking_index = 0
        self.thinking_command = ""

        # ----------------------------------------------------
        # WINDOW DRAG / REAL HARDWARE TELEMETRY
        # ----------------------------------------------------

        self._drag_active = False
        self._drag_start_global = None
        self._drag_start_window = None
        self._drag_targets = set()
        self._network_sample = None
        self._network_download_mbps = 0.0
        self._network_upload_mbps = 0.0
        self._system_static_info = None
        self._system_log_entries = []
        self._last_system_log = 0.0
        self._last_battery_log = None

        # ----------------------------------------------------
        # NAVIGATION
        # ----------------------------------------------------

        self.nav_buttons = {}

        # ----------------------------------------------------
        # BUILD UI
        # ----------------------------------------------------
        
        self.settings = NEXUSSettings()
        
        self.setup_ui()
        
        self.apply_runtime_settings(nexus_settings.load_user_settings(), announce=False)

        self.system_check_overlay = None
        self.system_fix_process = None

        self.refresh_conversation_list()

        self.restore_latest_conversation()

        # ----------------------------------------------------
        # SYSTEM MONITOR
        # ----------------------------------------------------

        self.monitor_timer = QTimer(self)

        self.monitor_timer.timeout.connect(self.update_system_stats)

        self.monitor_timer.start(2000)

        self.update_system_stats()

        QTimer.singleShot(0, self.start_system_check)

        self.init_assistant_services()

    # ========================================================
    # NEXUS GLOBAL ACTIVATION
    # ========================================================

    def activate_nexus(self):
        """Bring the NEXUS window forward with a subtle desktop-style reveal."""
        try:
            if self.isMinimized():
                self.showNormal()
            elif not self.isVisible():
                self.show()

            self.raise_()
            self.activateWindow()

            if hasattr(self, "dashboard_input"):
                self.dashboard_input.setFocus()
        except Exception:
            pass


    def set_background_voice(self, service):
        """Attach the process-wide background voice service."""
        self.background_voice = service

    def closeEvent(self, event):
        try:
            self.window_settings.setValue("windowGeometry", self.saveGeometry())
        except Exception:  # noqa: BLE001
            pass
        tray = getattr(self, "tray", None)
        if self.settings.close_to_tray and tray is not None and tray.isVisible() and not getattr(self, "_quitting", False):
            # Keep reminders and the voice listener alive in the tray.
            event.ignore()
            self.hide()
            if not self.window_settings.value("tray_hint_shown", False, type=bool):
                self.window_settings.setValue("tray_hint_shown", True)
                tray.showMessage("NEXUS is still running", "NEXUS keeps running in the system tray so reminders can notify you. "
                                 "Right-click the tray icon and choose Exit to quit.")
            return
        self._quitting = True
        event.accept()
        QApplication.quit()

    def set_tray(self, tray):
        self.tray = tray

    def request_quit(self):
        self._quitting = True
        QApplication.quit()

    def shutdown(self):
        """Stop timers, workers and audio before the process exits."""
        self._quitting = True
        for name in ("reminder_scheduler",):
            service = getattr(self, name, None)
            if service is not None:
                try:
                    service.stop()
                except Exception:  # noqa: BLE001
                    pass
        for name in ("monitor_timer", "speech_watch_timer", "thinking_timer", "global_clock_timer"):
            timer = getattr(self, name, None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception:  # noqa: BLE001
                    pass
        if self.kokoro_speech_queue is not None:
            try:
                self.kokoro_speech_queue.close()
            except Exception:  # noqa: BLE001
                pass
        for thread in list(self.ai_threads.values()):
            try:
                thread.quit()
                thread.wait(1500)
            except Exception:  # noqa: BLE001
                pass
        check_thread = getattr(self, "_system_check_thread", None)
        if check_thread is not None and check_thread.is_alive():
            check_thread.join(timeout=4.0)
        # Stop an active microphone capture and any running document summary, so closing the
        # window never leaves the microphone open or a thread running into interpreter exit.
        voice_worker = getattr(self, "voice_worker", None)
        if voice_worker is not None:
            try:
                if voice_worker.isRunning():
                    voice_worker.cancel()
                    voice_worker.wait(2000)
            except Exception:  # noqa: BLE001
                pass
        document_worker = getattr(self, "document_worker", None)
        if document_worker is not None:
            try:
                document_worker.abandon()   # a daemon thread: it is left to finish quietly, never killed
                document_worker.wait(1500)
            except Exception:  # noqa: BLE001
                pass

    # ========================================================
    # ASSISTANT SERVICES: reminders, greeting, data window
    # ========================================================

    def init_assistant_services(self):
        from core.reminders import ReminderScheduler

        self.tray = getattr(self, "tray", None)
        self.reminder_scheduler = ReminderScheduler(self.command_engine.assistant.reminders, parent=self)
        self.reminder_scheduler.reminder_due.connect(self.handle_reminder_due)
        # Start after the window exists so reminders missed while NEXUS was closed
        # are announced once the UI is ready.
        QTimer.singleShot(1500, self.reminder_scheduler.start)

        self.speech_watch_timer = QTimer(self)
        self.speech_watch_timer.setInterval(500)
        self.speech_watch_timer.timeout.connect(self._poll_speech)
        self.speech_watch_timer.start()

        if self.settings.startup_greeting:
            QTimer.singleShot(2500, self.show_startup_greeting)

    def show_startup_greeting(self):
        from core.assistant import build_greeting

        name = str(self.settings.get("user_name", "") or "")
        greeting = build_greeting(name)
        self.add_activity(greeting)
        try:
            conversation_id = self.ensure_conversation()
            self.conversation_manager.add_message(conversation_id, "assistant", greeting)
            self.render_current_conversation()
        except Exception:  # noqa: BLE001
            pass
        self.speak_response(greeting, self.current_voice_language)

    def handle_reminder_due(self, reminder, missed):
        """A reminder came due: notify, record it, and (optionally) speak it."""
        text = f"Reminder: {reminder.get('message', '')}"
        if missed:
            text += f" (this was due at {str(reminder.get('due_at', ''))[11:16]} - NEXUS wasn't running or the PC was asleep)"
        self.add_activity(text)
        try:
            conversation_id = self.ensure_conversation()
            self.conversation_manager.add_message(conversation_id, "assistant", f"\u23f0 {text}")
            self.render_current_conversation()
        except Exception:  # noqa: BLE001
            pass
        if self.settings.reminder_notifications:
            tray = getattr(self, "tray", None)
            if tray is not None and tray.isVisible():
                tray.showMessage("NEXUS reminder", text)
            if not self.isVisible():
                self.activate_nexus()
        if self.settings.speak_reminders and self.voice_enabled:
            self.speak_response(text, self.current_voice_language)

    def open_data_dialog(self):
        from ui.data_dialog import DataDialog

        dialog = DataDialog(self.command_engine.assistant, self.settings, self)
        dialog.exec()

    # ========================================================
    # MAIN UI
    # ========================================================

    def setup_ui(self):
        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        self.setCentralWidget(central_widget)

        # The dashboard is the only permanent surface. The header provides a
        # compact tools menu and direct settings access; secondary pages open
        # as focused, non-modal windows over the dashboard.
        central_layout.addWidget(self.create_global_header())

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        self.create_sidebar()
        # Keep the existing conversation model/list plumbing alive for search,
        # restore, and history behavior, but do not place a navigation rail in
        # the dashboard layout.
        self.sidebar.hide()
        self.search_input.hide()

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("pageStack")
        body_layout.addWidget(self.page_stack, 1)
        central_layout.addWidget(body, 1)

        self.dashboard_page = self.create_reference_dashboard_page()
        self.assistant_page = self.create_assistant_page()
        self.system_page = self.create_system_page()
        self.activity_page = self.create_activity_page()
        self.settings_page = SettingsPage(self.settings, self)
        self.settings_page.settingsSaved.connect(self.apply_runtime_settings)
        self.settings_page.resetRequested.connect(self.apply_reset_preferences)
        self.settings_page.manageDataRequested.connect(self.open_data_dialog)

        self.page_stack.addWidget(self.dashboard_page)
        self.tool_dialogs = {}
        self.register_tool_dialog("assistant", self.assistant_page, "NEXUS ASSISTANT", 1000, 700)
        self.register_tool_dialog("system", self.system_page, "SYSTEM MONITOR", 980, 700)
        self.register_tool_dialog("activity", self.activity_page, "ACTIVITY LOG", 940, 680)
        self.register_tool_dialog("settings", self.settings_page, "NEXUS SETTINGS", 820, 760)
        self.register_conversation_dialog()

        self.global_clock_timer = QTimer(self)
        self.global_clock_timer.timeout.connect(self.update_dashboard_clock)
        self.global_clock_timer.start(1000)
        self.update_dashboard_clock()
        self.switch_page("dashboard")

    def register_tool_dialog(self, name, page, title, width, height):
        """Host a retained NEXUS page in a compact, reusable popup window."""
        dialog = QDialog(self, Qt.Window)
        dialog.setObjectName("toolPopup")
        dialog.setWindowTitle(title)
        dialog.setModal(False)
        dialog.setWindowModality(Qt.NonModal)
        dialog.setAttribute(Qt.WA_DeleteOnClose, False)
        dialog.resize(width, height)
        dialog.setMinimumSize(min(width, 680), min(height, 500))
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(page)
        self.tool_dialogs[name] = dialog

    def register_conversation_dialog(self):
        """Expose saved conversations in a focused popup, not a permanent rail."""
        dialog = QDialog(self, Qt.Window)
        dialog.setObjectName("toolPopup")
        dialog.setWindowTitle("SAVED CONVERSATIONS")
        dialog.setModal(False)
        dialog.setWindowModality(Qt.NonModal)
        dialog.setAttribute(Qt.WA_DeleteOnClose, False)
        dialog.resize(430, 620)
        dialog.setMinimumSize(360, 420)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        title = QLabel("SAVED CONVERSATIONS")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        self.search_input.setPlaceholderText("Search conversations…")
        self.search_input.setMinimumWidth(0)
        self.search_input.setMaximumWidth(16777215)
        self.search_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.search_input.setFixedHeight(42)
        layout.addWidget(self.search_input)
        layout.addWidget(self.conversation_list, 1)
        self.search_input.show()
        self.conversation_list.show()
        self.tool_dialogs["conversations"] = dialog

    def show_controls_menu(self):
        menu = QMenu(self)
        menu.setObjectName("dashboardToolsMenu")
        for title, page_name in (
            ("Assistant", "assistant"),
            ("Conversation history", "conversations"),
            ("System monitor", "system"),
            ("Activity log", "activity"),
            ("Customize NEXUS", "customize"),
            ("AI & system settings", "settings"),
        ):
            action = menu.addAction(title)
            action.triggered.connect(
                lambda _checked=False, target=page_name: (
                    self.open_customize_dialog()
                    if target == "customize"
                    else self.switch_page(target)
                )
            )
        menu.addSeparator()
        view_dashboard = menu.addAction("Return to dashboard")
        view_dashboard.triggered.connect(lambda: self.switch_page("dashboard"))
        menu.popup(self.header_tools_button.mapToGlobal(self.header_tools_button.rect().bottomLeft()))

    def create_global_header(self):
        header = QFrame()
        header.setObjectName("globalHeader")
        self.global_header = header
        header.setFixedHeight(80)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(18, 8, 18, 8)
        layout.setSpacing(14)

        # Brand
        brand = QWidget()
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(10)
        emblem = HudIcon("nexus", 46)
        brand_layout.addWidget(emblem)
        brand_text = QVBoxLayout()
        brand_title = QLabel("NEXUS")
        brand_title.setObjectName("globalBrandTitle")
        brand_sub = QLabel("By NSHUTI Emmy")
        brand_sub.setObjectName("globalBrandSubtitle")
        brand_text.addWidget(brand_title)
        brand_text.addWidget(brand_sub)
        brand_layout.addLayout(brand_text)
        brand.setMinimumWidth(225)
        layout.addWidget(brand)

        # Center clock
        clock_box = QWidget()
        clock_layout = QVBoxLayout(clock_box)
        clock_layout.setContentsMargins(0, 0, 0, 0)
        clock_layout.setSpacing(1)
        self.dashboard_date = QLabel()
        self.dashboard_date.setObjectName("dateLabel")
        self.dashboard_date.setAlignment(Qt.AlignCenter)
        self.dashboard_clock = QLabel()
        self.dashboard_clock.setObjectName("clockLabel")
        self.dashboard_clock.setAlignment(Qt.AlignCenter)
        clock_layout.addWidget(self.dashboard_date)
        clock_layout.addWidget(self.dashboard_clock)
        layout.addWidget(clock_box, 1, alignment=Qt.AlignCenter)

        # Compact actions: the hidden search widget stays available to the
        # existing conversation helpers, but is not part of the main surface.
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.header_tools_button = self.create_header_icon_button(
            "menu", "Open NEXUS tools", self.show_controls_menu
        )
        actions.addWidget(self.header_tools_button)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("Search conversations...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumWidth(180)
        self.search_input.setMaximumWidth(290)
        self.search_input.setFixedHeight(40)
        self.search_input.textChanged.connect(self.filter_conversations)
        self.search_input.returnPressed.connect(self.open_first_search_result)
        self.search_input.hide()

        self.notification_button = self.create_header_icon_button(
            "bell", "Notifications", self.show_notifications
        )
        self.notification_button.hide()

        self.header_settings_button = self.create_header_icon_button(
            "settings", "Customize NEXUS", self.open_customize_dialog
        )
        actions.addWidget(self.header_settings_button)

        self.profile_button = self.create_header_icon_button(
            "profile", "Profile", self.show_profile_dialog
        )
        self.profile_button.hide()

        self.global_status_badge = QLabel("● ONLINE")
        self.global_status_badge.setObjectName("statusBadge")
        self.global_status_badge.setMinimumWidth(86)
        self.global_status_badge.setAlignment(Qt.AlignCenter)
        actions.addWidget(self.global_status_badge)
        layout.addLayout(actions)

        # The custom top header is draggable while search/action controls stay clickable.
        for target in (header, brand, brand_title, brand_sub, clock_box, self.dashboard_date, self.dashboard_clock):
            self._register_drag_target(target)

        return header

    @staticmethod
    def theme_for_accent(color):
        accent = QColor(color)
        if not accent.isValid():
            accent = QColor("#45d9ff")
        theme = DARK_THEME.replace("#45d9ff", "__NEXUS_ACCENT__")
        for old, new in (
            ("#2acfff", accent.lighter(125).name()),
            ("#70e5ff", accent.lighter(150).name()),
            ("#25b9e5", accent.darker(110).name()),
        ):
            theme = theme.replace(old, new)
        return theme.replace("__NEXUS_ACCENT__", accent.name())

    def apply_accent_color(self, color):
        accent = QColor(color)
        if not accent.isValid():
            return
        self._accent_color = accent
        self.setStyleSheet(self.theme_for_accent(accent))
        for icon in self.findChildren(HudIcon):
            if not icon.property("hudColor"):
                icon.setProperty("hudColor", accent.lighter(125).name())
                icon.update()
        if hasattr(self, "dashboard_core_widget"):
            self.dashboard_core_widget.set_state_color("sleeping", accent)
        if hasattr(self, "settings"):
            self.settings.set("ui_accent", accent.name())

    def open_customize_dialog(self):
        """Open the compact, modal NEXUS identity and appearance editor."""
        dialog = QDialog(self)
        dialog.setObjectName("customizeDialog")
        dialog.setWindowTitle("CUSTOMIZE NEXUS")
        dialog.setModal(True)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.resize(620, 660)
        dialog.setMinimumSize(560, 590)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(24, 22, 24, 20)
        outer.setSpacing(14)

        heading = QHBoxLayout()
        heading.addWidget(HudIcon("settings", 30))
        title = QLabel("CUSTOMIZE NEXUS")
        title.setObjectName("pageTitle")
        heading.addWidget(title)
        heading.addStretch(1)
        outer.addLayout(heading)

        subtitle = QLabel("Personalize the NEXUS HUD. The assistant identity remains NEXUS.")
        subtitle.setObjectName("mutedText")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        form = QFrame()
        form.setObjectName("customizePanel")
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(18, 16, 18, 16)
        form_layout.setSpacing(12)

        assistant_name = QLineEdit("NEXUS")
        assistant_name.setReadOnly(True)
        assistant_name.setObjectName("customizeIdentity")
        form_layout.addWidget(self._customize_field("ASSISTANT NAME", assistant_name))

        user_name = QLineEdit(str(self.settings.get("user_name", "") or ""))
        user_name.setObjectName("customizeInput")
        user_name.setMaxLength(50)
        user_name.setPlaceholderText("Optional — leave blank for a neutral greeting")
        form_layout.addWidget(self._customize_field("YOUR NAME", user_name))

        voice_language = QComboBox()
        for code, label in (
            ("auto", "Automatic"),
            ("en", "English"),
            ("fr", "French"),
            ("sw", "Swahili"),
            ("es", "Spanish"),
            ("de", "German"),
            ("it", "Italian"),
            ("pt", "Portuguese"),
            ("rw", "Kinyarwanda"),
        ):
            voice_language.addItem(label, code)
        selected_voice = voice_language.findData(self.settings.voice_language)
        if selected_voice >= 0:
            voice_language.setCurrentIndex(selected_voice)
        form_layout.addWidget(self._customize_field("VOICE LANGUAGE", voice_language))

        selected_color = [QColor(self._accent_color)]
        accent_button = QPushButton()
        accent_button.setObjectName("accentColorButton")
        accent_button.setCursor(Qt.PointingHandCursor)
        accent_button.setFixedHeight(44)

        def refresh_accent_button():
            accent_button.setText(f"  {selected_color[0].name().upper()}     CHANGE HUD COLOUR")
            accent_button.setStyleSheet(
                "QPushButton { background-color: #071622; color: %s; "
                "border: 1px solid %s; border-radius: 7px; padding: 7px; } "
                "QPushButton:hover { background-color: #0a2638; }"
                % (selected_color[0].name(), selected_color[0].name())
            )

        def choose_accent_color():
            chosen = QColorDialog.getColor(selected_color[0], dialog, "Choose NEXUS accent color")
            if chosen.isValid():
                selected_color[0] = chosen
                refresh_accent_button()

        refresh_accent_button()
        accent_button.clicked.connect(choose_accent_color)
        form_layout.addWidget(self._customize_field("HUD ACCENT", accent_button))
        outer.addWidget(form)

        signature = QLabel("NEXUS  •  BY NSHUTI EMMY")
        signature.setObjectName("mutedText")
        signature.setAlignment(Qt.AlignCenter)
        outer.addWidget(signature)
        outer.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        apply_button = QPushButton("APPLY CHANGES")
        apply_button.setObjectName("primaryButton")
        cancel_button = QPushButton("CANCEL")
        cancel_button.setObjectName("secondaryButton")
        buttons.addWidget(apply_button)
        buttons.addWidget(cancel_button)
        outer.addLayout(buttons)

        def apply_changes():
            display_name = user_name.text().strip()
            self.settings.set("user_name", display_name)
            self.settings.voice_language = voice_language.currentData() or "auto"
            self.current_voice_language = self.settings.voice_language
            self.pending_voice_language = "auto"
            self.apply_accent_color(selected_color[0])
            self.update_dashboard_greeting(display_name)
            self._sync_voice_language_controls(self.settings.voice_language)
            self.add_activity("NEXUS appearance and voice-language preferences updated.")
            dialog.accept()

        apply_button.clicked.connect(apply_changes)
        cancel_button.clicked.connect(dialog.reject)
        dialog.exec()

    @staticmethod
    def _customize_field(label_text, widget):
        field = QWidget()
        layout = QVBoxLayout(field)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        label = QLabel(label_text)
        label.setObjectName("customizeFieldLabel")
        layout.addWidget(label)
        layout.addWidget(widget)
        return field

    def update_dashboard_greeting(self, display_name=None):
        if not hasattr(self, "dashboard_greeting_label"):
            return
        if display_name is None:
            display_name = str(self.settings.get("user_name", "") or "").strip()
        self.dashboard_greeting_label.setText(
            f"Your private AI assistant. Ready when you are, {display_name}."
            if display_name
            else "Your private AI assistant. Ready when you are."
        )

    def _sync_voice_language_controls(self, language):
        for combo in (
            getattr(self, "voice_language_combo", None),
            getattr(getattr(self, "settings_page", None), "voice_language", None),
        ):
            if combo is None:
                continue
            index = combo.findData(language)
            if index >= 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(index)
                combo.blockSignals(False)

    def create_header_icon_button(self, kind, tooltip, callback):
        button = QPushButton()
        button.setObjectName("headerIconButton")
        button.setText("")
        button.setFixedSize(38, 38)
        button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        button.setToolTip(tooltip)
        button.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(button)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignCenter)

        icon = HudIcon(kind, 22, button)
        icon.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        layout.addWidget(icon)
        button.clicked.connect(callback)
        return button

    def _register_drag_target(self, widget):
        if widget is None:
            return
        widget.installEventFilter(self)
        self._drag_targets.add(widget)

    @staticmethod
    def _event_global_position(event):
        try:
            return event.globalPosition().toPoint()
        except AttributeError:
            return event.globalPos()

    def eventFilter(self, watched, event):
        if watched in getattr(self, "_drag_targets", set()):
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
                if self.isMaximized():
                    return False
                self._drag_active = True
                self._drag_start_global = self._event_global_position(event)
                self._drag_start_window = self.pos()
                return True
            if event.type() == QEvent.Type.MouseMove and self._drag_active:
                if event.buttons() & Qt.LeftButton and self._drag_start_global is not None:
                    delta = self._event_global_position(event) - self._drag_start_global
                    self.move(self._drag_start_window + delta)
                    return True
            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.LeftButton:
                self._drag_active = False
                self._drag_start_global = None
                self._drag_start_window = None
                return True
        return super().eventFilter(watched, event)

    def show_notifications(self):
        menu = QMenu(self)
        menu.setObjectName("notificationsMenu")
        if not self.activity_events:
            empty = menu.addAction("No activity recorded yet")
            empty.setEnabled(False)
        else:
            for stamp, event_text in reversed(self.activity_events[-8:]):
                action = menu.addAction(f"{stamp}   {str(event_text)[:70]}")
                action.setToolTip(str(event_text))
                action.triggered.connect(lambda _=False: self.switch_page("activity"))
        menu.addSeparator()
        view_log = menu.addAction("Open activity log")
        view_log.triggered.connect(lambda: self.switch_page("activity"))
        menu.popup(self.notification_button.mapToGlobal(self.notification_button.rect().bottomLeft()))

    def show_profile_dialog(self):
        model = getattr(self.settings, "ai_model", nexus_settings.NEXUS_MODEL)
        voice = "Enabled" if getattr(self, "voice_enabled", False) else "Disabled"
        data_dir = getattr(nexus_settings, "USER_DATA_DIR", None)
        text = (
            "<b>NEXUS</b><br>"
            "Local desktop AI assistant<br><br>"
            f"<b>Model:</b> {escape(str(model))}<br>"
            f"<b>Voice:</b> {voice}<br>"
            f"<b>Version:</b> {escape(nexus_settings.APP_VERSION)}<br>"
            f"<b>Data:</b> {escape(str(data_dir or 'Local application storage'))}"
        )
        box = QMessageBox(self)
        box.setWindowTitle("NEXUS PROFILE")
        box.setText(text)
        box.setIcon(QMessageBox.Information)
        settings_btn = box.addButton("Open Settings", QMessageBox.ActionRole)
        data_btn = box.addButton("Open Data Folder", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        clicked = box.clickedButton()
        if clicked is settings_btn:
            self.switch_page("settings")
        elif clicked is data_btn and data_dir:
            try:
                target = Path(data_dir)
                target.mkdir(parents=True, exist_ok=True)
                os.startfile(str(target))
            except Exception as error:
                QMessageBox.warning(self, "NEXUS", f"Could not open the data folder:\n{error}")

    def filter_conversations(self, query):
        query = str(query or "").strip().lower()
        if not hasattr(self, "conversation_list"):
            return
        for index in range(self.conversation_list.count()):
            item = self.conversation_list.item(index)
            cid = item.data(Qt.UserRole)
            match = True
            if query:
                title = str(item.data(Qt.UserRole + 1) or "").lower()
                message_text = ""
                try:
                    message_text = " ".join(
                        str(m.get("content", ""))
                        for m in self.conversation_manager.get_messages(cid)
                    ).lower()
                except Exception:
                    pass
                match = query in title or query in message_text
            item.setHidden(not match)

    def open_first_search_result(self):
        query = self.search_input.text().strip() if hasattr(self, "search_input") else ""
        if not query or not hasattr(self, "conversation_list"):
            return
        for index in range(self.conversation_list.count()):
            item = self.conversation_list.item(index)
            if not item.isHidden():
                self.load_conversation_from_item(item)
                return

    # ========================================================
    # IN-APP SYSTEM CHECK
    # ========================================================

    def start_system_check(self):
        self.system_check_overlay = SystemCheckDialog(parent=self.centralWidget())
        self.system_check_overlay.setGeometry(self.centralWidget().rect())
        self.system_check_overlay.raise_()
        self.system_check_overlay.continueRequested.connect(self.finish_system_check)
        self.system_check_overlay.retryRequested.connect(self._run_system_check)
        self.system_check_overlay.fixRequested.connect(self._attempt_system_fix)
        self.system_check_overlay.show()
        self.system_check_overlay.update_status("Running startup diagnostics…")
        QTimer.singleShot(80, self._run_system_check)

    def _run_system_check(self):
        """Run the checks on a worker thread (they make network calls); results return via a signal."""
        if self.system_check_overlay is None or getattr(self, "_system_check_running", False):
            return
        self._system_check_running = True
        self.system_check_overlay.update_status("Running startup diagnostics…")
        if not hasattr(self, "_system_check_bridge"):
            self._system_check_bridge = _SystemCheckBridge(self)
            self._system_check_bridge.finished.connect(self._system_check_done)

        def work():
            try:
                results, error = NEXUSSystemChecker().run_all_checks(), ""
            except Exception as failure:  # noqa: BLE001
                results, error = [], str(failure)
            if not getattr(self, "_quitting", False):  # never signal into a window that is closing
                self._system_check_bridge.finished.emit(results, error)

        # Kept so shutdown() can wait for it: a thread still importing modules or talking to
        # Qt while the interpreter finalises is what used to crash NEXUS right after launch.
        self._system_check_thread = threading.Thread(target=work, name="NEXUS-SystemCheck", daemon=True)
        self._system_check_thread.start()

    def _system_check_done(self, results, error):
        self._system_check_running = False
        if self.system_check_overlay is None:
            return
        self.system_check_overlay.set_results(results)
        if error:
            self.system_check_overlay.update_status(f"System check could not complete: {error}")

    def _attempt_system_fix(self, index):
        if self.system_check_overlay is None:
            return

        results = list(getattr(self.system_check_overlay, "results", []) or [])
        if index < 0 or index >= len(results):
            return

        result = results[index]
        text = f"{getattr(result, 'name', '')} {getattr(result, 'details', '')}".lower()

        try:
            if "nexus local model" in text or ("modelfile" in text and "customized" in text):
                self.system_check_overlay.set_busy(True)
                self.system_check_overlay.update_status("NEXUS is creating the customized local model…")
                modelfile = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "Modelfile")
                self._new_fix_process(self._system_fix_finished).start("ollama", ["create", "nexus", "-f", modelfile])
                return

            if "ollama" in text and "llama3.1:8b" in text and "model" in text:
                self.system_check_overlay.set_busy(True)
                self.system_check_overlay.update_status("NEXUS is preparing the local AI model…")
                self._new_fix_process(self._system_fix_finished).start("ollama", ["pull", "llama3.1:8b"])
                return

            if "ollama" in text:
                self.system_check_overlay.set_busy(True)
                self.system_check_overlay.update_status("NEXUS is starting the local AI service…")
                self._new_fix_process().start("ollama", ["serve"])
                QTimer.singleShot(2500, self._system_fix_service_check)
                return

            if "microphone" in text or "microphone" in getattr(result, "name", "").lower():
                try:
                    os.startfile("ms-settings:privacy-microphone")
                    self.system_check_overlay.update_status(
                        "Microphone settings opened. Enable microphone access, then run the check again."
                    )
                except Exception as error:
                    self.system_check_overlay.update_status(
                        f"Open Windows microphone settings and enable access, then run the check again. ({error})"
                    )
                return

            self.system_check_overlay.update_status(
                "Please complete this requirement on the PC, then run the check again."
            )
        except Exception as error:
            self.system_check_overlay.set_busy(False)
            self.system_check_overlay.update_status(f"Automatic fix could not be started: {error}")

    def _system_fix_finished(self, exit_code, exit_status):
        self.system_fix_process = None
        if self.system_check_overlay is not None:
            self.system_check_overlay.set_busy(False)
            self.system_check_overlay.update_status("Rechecking system requirements…")
        QTimer.singleShot(250, self._run_system_check)

    def _system_fix_failed(self, error):
        """The helper program could not even be started (for example Ollama is not installed)."""
        self.system_fix_process = None
        if self.system_check_overlay is not None:
            self.system_check_overlay.set_busy(False)
            self.system_check_overlay.update_status(
                "NEXUS could not start 'ollama'. Install Ollama from https://ollama.com/download, "
                "then choose Retry - or switch to Online AI in Settings."
            )

    def _new_fix_process(self, finished=None):
        process = QProcess(self)
        if finished is not None:
            process.finished.connect(finished)
        process.errorOccurred.connect(
            lambda error, p=process: self._system_fix_failed(error)
            if error == QProcess.ProcessError.FailedToStart else None
        )
        self.system_fix_process = process
        return process

    def _system_fix_service_check(self):
        if self.system_check_overlay is not None:
            self.system_check_overlay.set_busy(False)
            self.system_check_overlay.update_status("Rechecking system requirements…")
        QTimer.singleShot(250, self._run_system_check)

    def finish_system_check(self):
        if self.system_check_overlay is None:
            return

        # Missing components never lock the user out of the app; the dialog has
        # already told them what is missing and Settings can fix it later.
        self.system_check_overlay.hide()
        self.system_check_overlay.deleteLater()
        self.system_check_overlay = None
        self.switch_page("dashboard")
        if hasattr(self, "dashboard_input"):
            self.dashboard_input.setFocus()

    # ========================================================
    # SIDEBAR
    # ========================================================

    def create_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setMinimumWidth(220)
        self.sidebar.setMaximumWidth(246)
        self.sidebar.setFixedWidth(246)
        self.sidebar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(12, 14, 12, 12)
        sidebar_layout.setSpacing(7)

        navigation_title = QLabel("NAVIGATION")
        navigation_title.setObjectName("sectionTitle")
        navigation_title.setContentsMargins(8, 10, 0, 5)
        sidebar_layout.addWidget(navigation_title)

        self.create_nav_button("dashboard", "home", "Dashboard")
        self.create_nav_button("assistant", "assistant", "Assistant")
        self.create_nav_button("system", "system", "System")
        self.create_nav_button("activity", "activity", "Activity")
        self.create_nav_button("settings", "settings", "Settings")

        conversation_title = QLabel("CONVERSATIONS")
        conversation_title.setObjectName("sectionTitle")
        conversation_title.setContentsMargins(8, 18, 0, 5)
        sidebar_layout.addWidget(conversation_title)

        self.new_conversation_button = QPushButton()
        self.new_conversation_button.setObjectName("newConversationButton")
        self.new_conversation_button.setCursor(Qt.PointingHandCursor)
        row = QHBoxLayout(self.new_conversation_button)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(10)
        row.addWidget(HudIcon("plus", 22))
        label = QLabel("New Conversation")
        label.setObjectName("buttonText")
        label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row.addWidget(label)
        row.addStretch()
        self.new_conversation_button.clicked.connect(self.start_new_conversation)
        sidebar_layout.addWidget(self.new_conversation_button)

        self.conversation_list = QListWidget()
        self.conversation_list.setObjectName("conversationList")
        self.conversation_list.setUniformItemSizes(False)
        self.conversation_list.setWordWrap(False)
        self.conversation_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.conversation_list.customContextMenuRequested.connect(self.show_conversation_context_menu)
        self.conversation_list.itemClicked.connect(self.load_conversation_from_item)
        sidebar_layout.addWidget(self.conversation_list, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(5, 8, 5, 0)
        footer_dot = QLabel("●")
        footer_dot.setObjectName("online")
        footer.addWidget(footer_dot)
        self.version_label = QLabel(f"NEXUS v{nexus_settings.APP_VERSION}")
        self.version_label.setObjectName("mutedText")
        footer.addWidget(self.version_label)
        footer.addStretch()
        sidebar_layout.addLayout(footer)

    def create_conversation_row(self, title, stamp):
        """Create one custom row; QListWidget itself contains no display text."""
        widget = QWidget()
        widget.setObjectName("conversationRow")
        widget.setMinimumWidth(0)
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout = QHBoxLayout(widget)
        layout.setContentsMargins(7, 5, 7, 5)
        layout.setSpacing(9)

        icon = HudIcon("chat", 25)
        icon.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        layout.addWidget(icon, 0, Qt.AlignTop)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)

        raw_title = str(title or "New Conversation")
        title_label = QLabel(raw_title)
        title_label.setObjectName("conversationRowTitle")
        title_label.setWordWrap(True)
        title_label.setMinimumWidth(0)
        title_label.setMaximumHeight(34)
        title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        title_label.setToolTip(raw_title)

        stamp_label = QLabel(str(stamp or "Local"))
        stamp_label.setObjectName("conversationRowStamp")
        stamp_label.setMinimumWidth(0)
        stamp_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        text.addWidget(title_label)
        text.addWidget(stamp_label)
        layout.addLayout(text, 1)
        return widget

    # ========================================================
    # NAV BUTTON
    # ========================================================

    def create_nav_button(self, page_name, icon_kind, label_text):
        button = QPushButton()
        button.setObjectName("navButton")
        button.setCursor(Qt.PointingHandCursor)
        button.setProperty("expandedText", label_text)
        row = QHBoxLayout(button)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(11)
        row.addWidget(HudIcon(icon_kind, 22))
        label = QLabel(label_text)
        label.setObjectName("navButtonLabel")
        label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row.addWidget(label, 1)
        button.clicked.connect(lambda checked=False, name=page_name: self.switch_page(name))
        self.nav_buttons[page_name] = button
        self.sidebar.layout().addWidget(button)
    # ========================================================
    # PAGE SWITCHING
    # ========================================================


    def switch_page(self, page_name):
        if page_name == "dashboard":
            for dialog in getattr(self, "tool_dialogs", {}).values():
                dialog.hide()
            if hasattr(self, "page_stack"):
                self.page_stack.setCurrentWidget(self.dashboard_page)
            if hasattr(self, "dashboard_scroll"):
                self.dashboard_scroll.horizontalScrollBar().setValue(0)
                self.dashboard_scroll.verticalScrollBar().setValue(0)
            return

        dialog = getattr(self, "tool_dialogs", {}).get(page_name)
        if dialog is None:
            return

        # Keep one focused tool popup open at a time. Work and conversation
        # state remain in the same widgets and database as before.
        for name, other in self.tool_dialogs.items():
            if name != page_name:
                other.hide()
        if page_name == "system" and hasattr(self, "system_scroll"):
            self.system_scroll.horizontalScrollBar().setValue(0)
            self.system_scroll.verticalScrollBar().setValue(0)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    # ========================================================
    # DASHBOARD PAGE
    # ========================================================

    def create_reference_dashboard_page(self):
        """A compact three-zone dashboard inspired by the JARVIS reference."""
        page = QWidget()
        page.setObjectName("referenceDashboard")
        root = QVBoxLayout(page)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        zones = QHBoxLayout()
        zones.setContentsMargins(0, 0, 0, 0)
        zones.setSpacing(10)

        # Live system information is compact and stays separate from the AI core.
        monitor = QFrame()
        monitor.setObjectName("dashboardPanel")
        monitor.setMinimumWidth(145)
        monitor.setMaximumWidth(210)
        monitor_layout = QVBoxLayout(monitor)
        monitor_layout.setContentsMargins(12, 12, 12, 12)
        monitor_layout.setSpacing(12)
        monitor_title = QLabel("SYSTEM MONITOR")
        monitor_title.setObjectName("cardTitle")
        monitor_layout.addWidget(monitor_title)
        monitor_note = QLabel("Live local telemetry")
        monitor_note.setObjectName("mutedText")
        monitor_layout.addWidget(monitor_note)

        self.dashboard_system_values = {}
        self.dashboard_system_bars = {}
        for key, title, color in (
            ("cpu", "CPU", "#20c9ee"),
            ("memory", "MEMORY", "#38d6c3"),
            ("disk", "STORAGE", "#9471f5"),
            ("battery", "BATTERY", "#49d999"),
        ):
            row = QFrame()
            row.setObjectName("compactMetricRow")
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 5, 0, 5)
            row_layout.setSpacing(5)
            heading = QHBoxLayout()
            label = QLabel(title)
            label.setObjectName("mutedText")
            value = QLabel("N/A")
            value.setObjectName("compactMetricValue")
            value.setStyleSheet(f"color: {color};")
            heading.addWidget(label)
            heading.addStretch(1)
            heading.addWidget(value)
            row_layout.addLayout(heading)
            bar = QProgressBar()
            bar.setObjectName("compactMetricBar")
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(7)
            bar.setToolTip(f"Current {title.lower()} usage")
            row_layout.addWidget(bar)
            monitor_layout.addWidget(row)
            self.dashboard_system_values[key] = value
            self.dashboard_system_bars[key] = bar
        monitor_layout.addStretch(1)
        monitor_live = QLabel("●  MONITORING")
        monitor_live.setObjectName("online")
        monitor_layout.addWidget(monitor_live)
        zones.addWidget(monitor)

        # The central area is the primary focus, with the existing animated core.
        center = QFrame()
        center.setObjectName("heroPanel")
        center.setMinimumWidth(240)
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(16, 14, 16, 12)
        center_layout.setSpacing(8)
        center_heading = QHBoxLayout()
        welcome = QLabel("NEXUS AI CORE")
        welcome.setObjectName("heroTitle")
        center_heading.addWidget(welcome)
        center_heading.addStretch(1)
        self.dashboard_engine_label = QLabel()
        self.dashboard_engine_label.setObjectName("statusBadge")
        center_heading.addWidget(self.dashboard_engine_label)
        center_layout.addLayout(center_heading)
        description = QLabel("Your private AI assistant. Ready when you are.")
        self.dashboard_greeting_label = description
        description.setTextFormat(Qt.PlainText)
        description.setObjectName("heroDescription")
        description.setWordWrap(True)
        center_layout.addWidget(description)
        self.dashboard_core_widget = NexusCoreWidget()
        self.dashboard_core_widget.setMinimumSize(260, 250)
        self.dashboard_core_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        center_layout.addWidget(self.dashboard_core_widget, 1)

        zones.addWidget(center, 3)

        activity = QFrame()
        activity.setObjectName("activityPanel")
        activity.setMinimumWidth(230)
        activity.setMaximumWidth(365)
        activity_layout = QVBoxLayout(activity)
        activity_layout.setContentsMargins(12, 12, 12, 10)
        activity_layout.setSpacing(8)
        activity_header = QHBoxLayout()
        activity_title = QLabel("ACTIVITY LOG")
        activity_title.setObjectName("activityTitle")
        activity_header.addWidget(activity_title)
        activity_header.addStretch(1)
        activity_live = QLabel("● LIVE")
        activity_live.setObjectName("online")
        activity_header.addWidget(activity_live)
        activity_layout.addLayout(activity_header)
        self.dashboard_activity_container = QWidget()
        self.dashboard_activity_layout = QVBoxLayout(self.dashboard_activity_container)
        self.dashboard_activity_layout.setContentsMargins(0, 0, 0, 0)
        self.dashboard_activity_layout.setSpacing(0)
        activity_layout.addWidget(self.dashboard_activity_container, 1)
        view_activity = QPushButton("View all activity")
        view_activity.setObjectName("dashboardLinkButton")
        view_activity.clicked.connect(lambda: self.switch_page("activity"))
        activity_layout.addWidget(view_activity)

        divider = QFrame()
        divider.setObjectName("dashboardSeparator")
        divider.setFixedHeight(1)
        activity_layout.addWidget(divider)
        attach_title = QLabel("ATTACH TEXT OR CODE")
        attach_title.setObjectName("cardTitle")
        activity_layout.addWidget(attach_title)
        self.dashboard_attachment = None
        attach_row = QHBoxLayout()
        self.dashboard_attach_button = QPushButton("＋  Choose file")
        self.dashboard_attach_button.setObjectName("dashboardLinkButton")
        self.dashboard_attach_button.setToolTip("Attach a small text or source-code file to your next prompt")
        self.dashboard_attach_button.clicked.connect(self.attach_dashboard_file)
        attach_row.addWidget(self.dashboard_attach_button)
        self.dashboard_attachment_label = QLabel("No file attached")
        self.dashboard_attachment_label.setObjectName("mutedText")
        self.dashboard_attachment_label.setMinimumWidth(0)
        self.dashboard_attachment_label.setWordWrap(True)
        attach_row.addWidget(self.dashboard_attachment_label, 1)
        clear_attachment = QPushButton("×")
        clear_attachment.setObjectName("dashboardLinkButton")
        clear_attachment.setFixedWidth(28)
        clear_attachment.setToolTip("Remove attached file")
        clear_attachment.clicked.connect(self.clear_dashboard_attachment)
        attach_row.addWidget(clear_attachment)
        activity_layout.addLayout(attach_row)

        command_title = QLabel("ASK NEXUS")
        command_title.setObjectName("cardTitle")
        activity_layout.addWidget(command_title)
        composer = QHBoxLayout()
        composer.setSpacing(6)
        self.mic_button = self.create_header_icon_button("mic", "Speak to NEXUS", self.capture_voice_command)
        self.mic_button.setObjectName("dashboardMicButton")
        self.mic_button.setFixedSize(38, 38)
        composer.addWidget(self.mic_button)
        self.dashboard_input = TerminalInput()
        self.dashboard_input.setObjectName("dashboardInput")
        self.dashboard_input.setFixedHeight(48)
        self.dashboard_input.setPlaceholderText("Type a message…")
        self.dashboard_input.sendRequested.connect(self.handle_dashboard_command)
        composer.addWidget(self.dashboard_input, 1)
        send = self.create_header_icon_button(
            "send", "Send message", lambda: self.handle_dashboard_command(self.dashboard_input.toPlainText())
        )
        send.setObjectName("dashboardSendButton")
        send.setFixedSize(36, 36)
        composer.addWidget(send)
        activity_layout.addLayout(composer)

        self.voice_toggle = QPushButton("VOICE")
        self.voice_toggle.setObjectName("dashboardVoiceToggle")
        self.voice_toggle.setFixedHeight(30)
        self.voice_toggle.setCheckable(True)
        self.voice_toggle.setChecked(False)
        self.voice_toggle.setToolTip("Enable speech output; provider preferences are in Settings")
        self.voice_toggle.toggled.connect(self.set_voice_mode)
        voice_row = QHBoxLayout()
        voice_row.addWidget(self.voice_toggle, 1)
        self.dashboard_mic_status = QLabel("● MIC READY")
        self.dashboard_mic_status.setObjectName("mutedText")
        self.dashboard_mic_status.setAlignment(Qt.AlignCenter)
        voice_row.addWidget(self.dashboard_mic_status, 1)
        activity_layout.addLayout(voice_row)

        self.interrupt_button = QPushButton("INTERRUPT  [ESC]")
        self.interrupt_button.setObjectName("interruptButton")
        self.interrupt_button.setFixedHeight(36)
        self.interrupt_button.setToolTip(
            "Stop NEXUS voice playback. It does not terminate an AI request already in progress."
        )
        self.interrupt_button.clicked.connect(self.interrupt_voice_output)
        activity_layout.addWidget(self.interrupt_button)
        zones.addWidget(activity)
        root.addLayout(zones, 1)

        self.dashboard_sparklines = {}
        self.refresh_dashboard_activity_feed()
        self.refresh_dashboard_metrics()
        return page

    def refresh_dashboard_metrics(self):
        """Update the compact, non-blocking telemetry rail from real local data."""
        values = {
            "cpu": self.cpu_value,
            "memory": self.memory_value,
            "disk": self.storage_value,
        }
        battery = self.battery_value
        values["battery"] = None if battery is None else battery.get("percent")
        for key, value in values.items():
            label = getattr(self, "dashboard_system_values", {}).get(key)
            bar = getattr(self, "dashboard_system_bars", {}).get(key)
            available = value is not None
            if label is not None:
                label.setText("N/A" if not available else f"{float(value):.0f}%")
            if bar is not None:
                bar.setEnabled(available)
                bar.setValue(0 if not available else max(0, min(100, int(float(value)))))
                if key == "battery" and battery is not None:
                    state = "charging" if battery.get("charging") else "on battery"
                    bar.setToolTip(f"Battery {state}")

    def attach_dashboard_file(self):
        """Attach a small UTF-8 text/code file to the next explicit prompt."""
        allowed = "Text and source files (*.txt *.md *.py *.json *.csv *.log *.yaml *.yml *.toml *.xml *.html *.css *.js *.ts *.sql *.ini *.cfg *.ps1 *.bat *.sh)"
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Attach a text or code file",
            str(Path.home()),
            allowed,
        )
        if not file_path:
            return

        path = Path(file_path)
        try:
            if path.stat().st_size > 32 * 1024:
                raise ValueError("Choose a text or code file no larger than 32 KB.")
            content = path.read_bytes().decode("utf-8-sig")
            if "\x00" in content:
                raise ValueError("This looks like a binary file. Attach a UTF-8 text or code file instead.")
        except (OSError, UnicodeDecodeError, ValueError) as error:
            QMessageBox.warning(self, "Could not attach file", str(error))
            return

        self.dashboard_attachment = {"name": path.name, "content": content}
        self.dashboard_attachment_label.setText(path.name)
        self.dashboard_attachment_label.setToolTip(
            "Attached for the next message only; processed using the AI engine selected in Settings."
        )
        self.add_activity(f"Text file attached for the next assistant request: {path.name}")

    def clear_dashboard_attachment(self):
        self.dashboard_attachment = None
        if hasattr(self, "dashboard_attachment_label"):
            self.dashboard_attachment_label.setText("No file attached")
            self.dashboard_attachment_label.setToolTip("")

    def create_dashboard_page(self):
        """Build the NEXUS dashboard to closely match the supplied HUD reference."""
        page = QWidget()
        page.setMinimumWidth(0)
        page.setMinimumHeight(0)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(12, 10, 12, 10)
        page_layout.setSpacing(10)

        # The command bar stays visible while the dashboard content scrolls.
        scroll = QScrollArea()
        scroll.setObjectName("dashboardScroll")
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content = QWidget()
        # Reference layout width. On narrower windows the dashboard can scroll
        # instead of squeezing text/icons into invisible or overlapping areas.
        content.setMinimumWidth(1220)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(2, 2, 2, 2)
        content_layout.setSpacing(10)
        scroll.setWidget(content)
        self.dashboard_scroll = scroll
        page_layout.addWidget(scroll, 1)

        # ====================================================
        # HERO + ACTIVITY FEED
        # ====================================================
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(10)

        hero_panel = QFrame()
        hero_panel.setObjectName("heroPanel")
        hero_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        hero_layout = QVBoxLayout(hero_panel)
        hero_layout.setContentsMargins(20, 16, 20, 14)
        hero_layout.setSpacing(8)

        hero_title = QLabel("YOUR AI COMMAND CENTER")
        hero_title.setObjectName("heroTitle")
        hero_layout.addWidget(hero_title)

        hero_body = QHBoxLayout()
        hero_body.setSpacing(10)

        overview = QFrame()
        overview.setObjectName("coreOverview")
        overview.setMinimumWidth(195)
        overview.setMaximumWidth(245)
        overview_layout = QVBoxLayout(overview)
        overview_layout.setContentsMargins(10, 6, 10, 7)
        overview_layout.setSpacing(6)

        overview_title = QLabel("NEXUS AI CORE")
        overview_title.setObjectName("microTitle")
        overview_layout.addWidget(overview_title)

        overview_text = QLabel(
            "NEXUS is online and monitoring your system. Ready to help,\n"
            "answer, and get things done."
        )
        overview_text.setObjectName("heroDescription")
        overview_text.setWordWrap(True)
        overview_layout.addWidget(overview_text)
        overview_layout.addStretch()

        online_row = QHBoxLayout()
        online_row.setSpacing(7)
        online_dot = QLabel("●")
        online_dot.setObjectName("online")
        online_row.addWidget(online_dot)
        online_text = QLabel("SYSTEM ONLINE")
        online_text.setObjectName("online")
        online_row.addWidget(online_text)
        online_row.addStretch()
        overview_layout.addLayout(online_row)
        hero_body.addWidget(overview)

        self.dashboard_core_widget = NexusCoreWidget()
        self.dashboard_core_widget.setMinimumSize(300, 205)
        hero_body.addWidget(self.dashboard_core_widget, 1)
        hero_layout.addLayout(hero_body, 1)
        top_row.addWidget(hero_panel, 3)

        activity_panel = QFrame()
        activity_panel.setObjectName("activityPanel")
        activity_panel.setMinimumWidth(305)
        activity_panel.setMaximumWidth(390)
        activity_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        activity_layout = QVBoxLayout(activity_panel)
        activity_layout.setContentsMargins(14, 12, 14, 9)
        activity_layout.setSpacing(6)

        activity_header = QHBoxLayout()
        activity_title = QLabel("ACTIVITY FEED")
        activity_title.setObjectName("activityTitle")
        activity_header.addWidget(activity_title)
        activity_header.addStretch()
        activity_live = QLabel("● Live")
        activity_live.setObjectName("online")
        activity_header.addWidget(activity_live)
        activity_layout.addLayout(activity_header)

        self.dashboard_activity_container = QWidget()
        self.dashboard_activity_layout = QVBoxLayout(self.dashboard_activity_container)
        self.dashboard_activity_layout.setContentsMargins(0, 0, 0, 0)
        self.dashboard_activity_layout.setSpacing(0)
        activity_layout.addWidget(self.dashboard_activity_container, 1)
        top_row.addWidget(activity_panel, 1)
        content_layout.addLayout(top_row, 4)

        # ====================================================
        # METRIC CARDS + MISSION TIMELINE
        # ====================================================
        metrics_timeline_row = QHBoxLayout()
        metrics_timeline_row.setSpacing(10)

        stats_panel = QWidget()
        stats_panel.setMinimumWidth(0)
        stats_grid = QGridLayout(stats_panel)
        stats_grid.setContentsMargins(0, 0, 0, 0)
        stats_grid.setHorizontalSpacing(10)
        stats_grid.setVerticalSpacing(10)

        # Create the four live dashboard meters before building their cards.
        # These must be real CircularMeter widgets, not placeholders, because
        # refresh_system_metrics() updates them continuously.
        self.dashboard_cpu = CircularMeter(
            "CPU", 0, color="#2aaeff", show_title=False
        )
        self.dashboard_memory = CircularMeter(
            "MEMORY", 0, color="#35e5d2", show_title=False
        )
        self.dashboard_storage = CircularMeter(
            "STORAGE", 0, color="#9663ff", show_title=False
        )
        self.dashboard_battery = CircularMeter(
            "BATTERY", 0, color="#54e993", show_title=False
        )

        metric_specs = (
            ("CPU", "cpu", "#2aaeff", self.dashboard_cpu, "Usage"),
            ("MEMORY", "memory", "#35e5d2", self.dashboard_memory, "Usage"),
            ("STORAGE", "storage", "#9663ff", self.dashboard_storage, "Usage"),
            ("BATTERY", "battery", "#54e993", self.dashboard_battery, "Charging"),
        )
        self.dashboard_sparklines = {}
        for index, (title, icon_kind, color, meter, caption) in enumerate(metric_specs):
            meter.center_label = caption
            card = self.create_dashboard_metric_card(title, icon_kind, meter, color)
            stats_grid.addWidget(card, 0, index)
            stats_grid.setColumnStretch(index, 1)

        metrics_timeline_row.addWidget(stats_panel, 3)

        mission_panel = QFrame()
        mission_panel.setObjectName("dashboardPanel")
        mission_panel.setMinimumWidth(270)
        mission_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        mission_layout = QVBoxLayout(mission_panel)
        mission_layout.setContentsMargins(14, 12, 14, 10)
        mission_layout.setSpacing(7)

        mission_header = QHBoxLayout()
        mission_title = QLabel("MISSION TIMELINE")
        mission_title.setObjectName("cardTitle")
        mission_header.addWidget(mission_title)
        mission_header.addStretch()
        mission_today = QLabel("Today⌄")
        mission_today.setObjectName("mutedText")
        mission_header.addWidget(mission_today)
        mission_layout.addLayout(mission_header)

        self.dashboard_timeline_container = QWidget()
        self.dashboard_timeline_layout = QVBoxLayout(self.dashboard_timeline_container)
        self.dashboard_timeline_layout.setContentsMargins(0, 2, 0, 0)
        self.dashboard_timeline_layout.setSpacing(0)
        mission_layout.addWidget(self.dashboard_timeline_container, 1)
        metrics_timeline_row.addWidget(mission_panel, 1)
        content_layout.addLayout(metrics_timeline_row, 3)

        # ====================================================
        # SYSTEM MONITOR + QUICK COMMANDS + RECENT CONVERSATIONS
        # ====================================================
        lower_row = QHBoxLayout()
        lower_row.setSpacing(10)

        graph_panel = QFrame()
        graph_panel.setObjectName("dashboardPanel")
        graph_panel.setMinimumWidth(360)
        graph_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        graph_layout = QVBoxLayout(graph_panel)
        graph_layout.setContentsMargins(14, 11, 14, 8)
        graph_layout.setSpacing(6)

        graph_header = QHBoxLayout()
        graph_title = QLabel("SYSTEM MONITOR")
        graph_title.setObjectName("cardTitle")
        graph_header.addWidget(graph_title)
        graph_header.addStretch()
        graph_view_all = QPushButton("LIVE")
        graph_view_all.setObjectName("dashboardLinkButton")
        graph_header.addWidget(graph_view_all)
        graph_layout.addLayout(graph_header)
        self.system_graph = SystemGraphWidget()
        self.system_graph.setMinimumHeight(150)
        graph_layout.addWidget(self.system_graph, 1)
        lower_row.addWidget(graph_panel, 2)

        quick_panel = QFrame()
        quick_panel.setObjectName("dashboardPanel")
        quick_panel.setMinimumWidth(255)
        quick_layout = QVBoxLayout(quick_panel)
        quick_layout.setContentsMargins(14, 11, 14, 10)
        quick_layout.setSpacing(7)
        quick_header = QHBoxLayout()
        quick_title = QLabel("QUICK COMMANDS")
        quick_title.setObjectName("cardTitle")
        quick_header.addWidget(quick_title)
        quick_header.addStretch()
        quick_view = QPushButton("View All")
        quick_view.setObjectName("dashboardLinkButton")
        quick_view.clicked.connect(lambda: self.switch_page("assistant"))
        quick_header.addWidget(quick_view)
        quick_layout.addLayout(quick_header)

        command_grid = QGridLayout()
        command_grid.setHorizontalSpacing(7)
        command_grid.setVerticalSpacing(7)
        self.create_dashboard_command(command_grid, 0, 0, "play", "Start New Task", self.start_new_conversation)
        self.create_dashboard_command(command_grid, 0, 1, "calendar", "Open Calendar", self.open_calendar)
        self.create_dashboard_command(command_grid, 1, 0, "system", "System Info", lambda: self.run_quick_command("system"))
        self.create_dashboard_command(command_grid, 1, 1, "download", "Check Updates", self.check_windows_updates)
        self.create_dashboard_command(command_grid, 2, 0, "trash", "Clear Data", self.clear_dashboard_data)
        self.create_dashboard_command(command_grid, 2, 1, "bolt", "Run Workflow", self.run_dashboard_workflow)
        command_grid.setColumnStretch(0, 1)
        command_grid.setColumnStretch(1, 1)
        quick_layout.addLayout(command_grid, 1)
        lower_row.addWidget(quick_panel, 1)

        recent_panel = QFrame()
        recent_panel.setObjectName("dashboardPanel")
        recent_panel.setMinimumWidth(275)
        recent_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        recent_layout = QVBoxLayout(recent_panel)
        recent_layout.setContentsMargins(14, 11, 12, 10)
        recent_layout.setSpacing(6)
        recent_header = QHBoxLayout()
        recent_title = QLabel("RECENT CONVERSATIONS")
        recent_title.setObjectName("cardTitle")
        recent_header.addWidget(recent_title)
        recent_header.addStretch()
        recent_view = QPushButton("View All")
        recent_view.setObjectName("dashboardLinkButton")
        recent_view.clicked.connect(lambda: self.switch_page("assistant"))
        recent_header.addWidget(recent_view)
        recent_layout.addLayout(recent_header)

        self.dashboard_recent_container = QWidget()
        self.dashboard_recent_layout = QVBoxLayout(self.dashboard_recent_container)
        self.dashboard_recent_layout.setContentsMargins(0, 0, 0, 0)
        self.dashboard_recent_layout.setSpacing(3)
        recent_layout.addWidget(self.dashboard_recent_container, 1)
        lower_row.addWidget(recent_panel, 2)
        content_layout.addLayout(lower_row, 3)

        # ====================================================
        # FIXED COMMAND BAR
        # ====================================================
        bottom_panel = QFrame()
        bottom_panel.setObjectName("askPanel")
        bottom_panel.setFixedHeight(56)
        bottom_layout = QHBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(10, 6, 10, 6)
        bottom_layout.setSpacing(7)

        self.mic_button = self.create_header_icon_button(
            "mic", "Speak a command", self.capture_voice_command
        )
        self.mic_button.setObjectName("dashboardMicButton")
        self.mic_button.setText("")
        self.mic_button.setFixedSize(48, 48)
        bottom_layout.addWidget(self.mic_button)

        self.dashboard_input = TerminalInput()
        self.dashboard_input.setObjectName("dashboardInput")
        self.dashboard_input.setFixedHeight(42)
        self.dashboard_input.sendRequested.connect(self.handle_dashboard_command)
        bottom_layout.addWidget(self.dashboard_input, 1)

        send_button = self.create_header_icon_button(
            "send", "Send command", lambda: self.handle_dashboard_command(self.dashboard_input.toPlainText())
        )
        send_button.setObjectName("dashboardSendButton")
        send_button.setFixedSize(38, 38)
        bottom_layout.addWidget(send_button)

        self.voice_toggle = QPushButton("VOICE")
        self.voice_toggle.setObjectName("dashboardVoiceToggle")
        self.voice_toggle.setFixedHeight(42)
        self.voice_toggle.setMinimumWidth(98)
        self.voice_toggle.setMaximumWidth(112)
        self.voice_toggle.setCheckable(True)
        self.voice_toggle.setChecked(False)
        self.voice_toggle.setToolTip("Enable online AI-generated voice responses")
        self.voice_toggle.toggled.connect(self.set_voice_mode)
        bottom_layout.addWidget(self.voice_toggle)

        settings_button = self.create_header_icon_button(
            "settings", "Settings", lambda: self.switch_page("settings")
        )
        settings_button.setObjectName("dashboardSettingsButton")
        settings_button.setFixedSize(38, 38)
        bottom_layout.addWidget(settings_button)

        clear_button = self.create_header_icon_button(
            "chat", "Open Assistant", lambda: self.switch_page("assistant")
        )
        clear_button.setObjectName("dashboardAssistantButton")
        clear_button.setFixedSize(38, 38)
        bottom_layout.addWidget(clear_button)

        page_layout.addWidget(bottom_panel)

        # Populate data-driven dashboard sections after all widgets exist.
        self.refresh_dashboard_activity_feed()
        self.refresh_dashboard_timeline()
        self.refresh_dashboard_recent_conversations()
        self._update_dashboard_sparklines()

        return page

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                # Hide and detach immediately: deleteLater() alone leaves the old
                # widget painted at its previous position until the event loop runs.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)

    def _set_button_icon(self, button, kind):
        if button is None:
            return
        button.setText("")
        icons = button.findChildren(HudIcon)
        if icons:
            icons[0].setKind(kind)
            for extra in icons[1:]:
                extra.hide()

    def create_dashboard_metric_card(self, title, icon_kind, meter, color):
        card = QFrame()
        card.setObjectName("dashboardMetricCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        card.setMinimumHeight(185)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)

        header = QHBoxLayout()
        badge = QFrame()
        badge.setObjectName("dashboardMetricIconBadge")
        badge.setFixedSize(38, 38)
        badge_layout = QHBoxLayout(badge)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.setAlignment(Qt.AlignCenter)
        icon = HudIcon(icon_kind, 22)
        icon.setProperty("hudColor", color)
        badge_layout.addWidget(icon)
        header.addWidget(badge)
        title_label = QLabel(title)
        title_label.setObjectName("metricCardTitle")
        header.addWidget(title_label)
        header.addStretch()
        layout.addLayout(header)

        meter.setFixedSize(104, 104)
        layout.addWidget(meter, 1, alignment=Qt.AlignCenter)

        spark = MiniSparklineWidget(color)
        self.dashboard_sparklines[title.lower()] = spark
        layout.addWidget(spark)
        return card

    def create_dashboard_command(self, layout, row, column, icon_kind, text, callback):
        button = QPushButton()
        button.setObjectName("dashboardCommandButton")
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(str(text))
        button_layout = QHBoxLayout(button)
        button_layout.setContentsMargins(8, 5, 8, 5)
        button_layout.setSpacing(7)
        button_layout.addWidget(HudIcon(icon_kind, 21))
        label = QLabel(str(text))
        label.setObjectName("buttonText")
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        button_layout.addWidget(label, 1)
        button.clicked.connect(callback)
        layout.addWidget(button, row, column)
        return button

    def _dashboard_activity_icon(self, text):
        value = str(text or "").lower()
        if "system" in value or "check" in value:
            return "settings"
        if "conversation" in value or "chat" in value:
            return "chat"
        if "response" in value or "ai" in value:
            return "assistant"
        if "battery" in value:
            return "battery"
        return "bolt"

    def refresh_dashboard_activity_feed(self):
        if not hasattr(self, "dashboard_activity_layout"):
            return
        self._clear_layout(self.dashboard_activity_layout)
        events = list(reversed(getattr(self, "activity_events", [])[-5:]))
        if not events:
            events = [
                ("Local", "System check completed — dashboard is ready."),
                ("Local", "NEXUS started and background services are active."),
            ]

        for index, (stamp, text) in enumerate(events):
            row = QFrame()
            row.setObjectName("dashboardActivityRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 7, 0, 7)
            row_layout.setSpacing(8)

            badge = QFrame()
            badge.setObjectName("dashboardActivityIconBadge")
            badge.setFixedSize(38, 38)
            badge_layout = QHBoxLayout(badge)
            badge_layout.setContentsMargins(0, 0, 0, 0)
            badge_layout.setAlignment(Qt.AlignCenter)
            badge_layout.addWidget(HudIcon(self._dashboard_activity_icon(text), 20))
            row_layout.addWidget(badge)

            text_box = QVBoxLayout()
            text_box.setSpacing(1)
            title = QLabel(str(text))
            title.setObjectName("dashboardActivityTitle")
            title.setWordWrap(True)
            detail = QLabel("NEXUS local event")
            detail.setObjectName("dashboardActivityDetail")
            text_box.addWidget(title)
            text_box.addWidget(detail)
            row_layout.addLayout(text_box, 1)

            time_label = QLabel(str(stamp))
            time_label.setObjectName("dashboardActivityTime")
            time_label.setAlignment(Qt.AlignRight | Qt.AlignTop)
            row_layout.addWidget(time_label)
            self.dashboard_activity_layout.addWidget(row)
            if index < len(events) - 1:
                separator = QFrame()
                separator.setObjectName("dashboardSeparator")
                separator.setFixedHeight(1)
                self.dashboard_activity_layout.addWidget(separator)
        self.dashboard_activity_layout.addStretch(1)

    def refresh_dashboard_timeline(self):
        if not hasattr(self, "dashboard_timeline_layout"):
            return
        self._clear_layout(self.dashboard_timeline_layout)
        conversations = []
        try:
            conversations = list(self.conversation_manager.get_conversations())[:4]
        except Exception:
            conversations = []

        fallback = [
            ("11:12", "Project Planning"),
            ("10:42", "Code Review"),
            ("09:18", "General Help"),
            ("04:33", "System Check"),
        ]
        rows = []
        for conversation in conversations:
            stamp = self._format_record_time(conversation.get("updated_at") or conversation.get("created_at"))
            rows.append((stamp, str(conversation.get("title") or "New Conversation")))
        rows = rows or fallback

        for index, (stamp, title) in enumerate(rows[:4]):
            row = QFrame()
            row.setObjectName("dashboardTimelineRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 4, 0, 4)
            row_layout.setSpacing(7)
            time_label = QLabel(stamp)
            time_label.setObjectName("dashboardTimelineTime")
            time_label.setFixedWidth(48)
            row_layout.addWidget(time_label)
            node = QLabel("●")
            node.setObjectName("dashboardTimelineNode")
            node.setFixedWidth(15)
            node.setAlignment(Qt.AlignCenter)
            row_layout.addWidget(node)
            title_label = QLabel(title)
            title_label.setObjectName("dashboardTimelineTitle")
            title_label.setWordWrap(True)
            row_layout.addWidget(title_label, 1)
            status = QLabel("Completed")
            status.setObjectName("dashboardTimelineStatus")
            row_layout.addWidget(status)
            self.dashboard_timeline_layout.addWidget(row)
            if index < min(3, len(rows) - 1):
                line = QFrame()
                line.setObjectName("dashboardTimelineLine")
                line.setFixedHeight(1)
                self.dashboard_timeline_layout.addWidget(line)
        self.dashboard_timeline_layout.addStretch(1)

    def refresh_dashboard_recent_conversations(self):
        if not hasattr(self, "dashboard_recent_layout"):
            return
        self._clear_layout(self.dashboard_recent_layout)
        try:
            conversations = list(self.conversation_manager.get_conversations())[:5]
        except Exception:
            conversations = []

        if not conversations:
            empty = QLabel("No saved conversations yet.")
            empty.setObjectName("mutedText")
            empty.setAlignment(Qt.AlignCenter)
            self.dashboard_recent_layout.addWidget(empty)
        else:
            for conversation in conversations[:5]:
                conversation_id = conversation.get("id")
                title = str(conversation.get("title") or "New Conversation")
                stamp = self._format_record_time(conversation.get("updated_at") or conversation.get("created_at"))
                button = QPushButton()
                button.setObjectName("dashboardRecentRow")
                button.setCursor(Qt.PointingHandCursor)
                button_layout = QHBoxLayout(button)
                button_layout.setContentsMargins(8, 5, 7, 5)
                button_layout.setSpacing(7)
                button_layout.addWidget(HudIcon("chat", 20))
                text_box = QVBoxLayout()
                text_box.setSpacing(0)
                title_label = QLabel(title)
                title_label.setObjectName("dashboardRecentTitle")
                title_label.setWordWrap(True)
                title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                stamp_label = QLabel(stamp)
                stamp_label.setObjectName("dashboardRecentStamp")
                stamp_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                text_box.addWidget(title_label)
                text_box.addWidget(stamp_label)
                button_layout.addLayout(text_box, 1)
                button_layout.addWidget(HudIcon("chevron", 18))
                button.clicked.connect(
                    lambda checked=False, cid=conversation_id: self.load_conversation(cid)
                )
                self.dashboard_recent_layout.addWidget(button)
        self.dashboard_recent_layout.addStretch(1)

    def _update_dashboard_sparklines(self):
        mapping = {
            "cpu": self.cpu_history,
            "memory": self.memory_history,
            "storage": self.disk_history,
            "battery": [self.dashboard_battery.value] if self.dashboard_battery else [],
        }
        for key, spark in getattr(self, "dashboard_sparklines", {}).items():
            spark.setData(mapping.get(key, []))

    def open_calendar(self):
        """Open the user's calendar without assuming a specific Calendar app."""
        try:
            if os.name != "nt":
                self.add_activity("Calendar opening is currently implemented for Windows.")
                return

            # First use Windows' registered Outlook calendar protocol.
            # os.startfile delegates protocol handling to the Windows shell and
            # is more reliable than launching explorer.exe with a URI argument.
            try:
                os.startfile("outlookcal:")
                self.add_activity("Calendar opened.")
                return
            except OSError:
                pass

            # Fall back to classic Outlook when it is installed.
            outlook_candidates = [
                os.path.expandvars(r"%ProgramFiles%\Microsoft Office\root\Office16\OUTLOOK.EXE"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft Office\root\Office16\OUTLOOK.EXE"),
                os.path.expandvars(r"%ProgramFiles%\Microsoft Office\Office16\OUTLOOK.EXE"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft Office\Office16\OUTLOOK.EXE"),
            ]
            for candidate in outlook_candidates:
                if Path(candidate).is_file():
                    started = QProcess.startDetached(candidate, ["/select", "outlook:calendar"])
                    if started:
                        self.add_activity("Calendar opened in Outlook.")
                        return

            # Final fallback: open Outlook on the web in the default browser.
            import webbrowser
            if webbrowser.open_new_tab("https://outlook.live.com/calendar/"):
                self.add_activity("Outlook Calendar opened in the browser.")
                return

            QMessageBox.information(
                self,
                "Calendar",
                "NEXUS could not find a local calendar application.\n\n"
                "Install or configure a calendar app, then try again.",
            )
        except Exception as error:  # noqa: BLE001
            self.add_activity(f"Could not open Calendar: {error}")

    def check_windows_updates(self):
        try:
            if os.name == "nt":
                os.startfile("ms-settings:windowsupdate")
                self.add_activity("Windows Update settings opened.")
            else:
                self.add_activity("Windows Update is only available on Windows.")
        except Exception as error:  # noqa: BLE001
            self.add_activity(f"Could not open Windows Update: {error}")

    def clear_dashboard_data(self):
        self.cpu_history.clear()
        self.memory_history.clear()
        self.disk_history.clear()
        self.network_history.clear()
        self._update_dashboard_sparklines()
        if hasattr(self, "system_graph"):
            self.system_graph.set_data([], [], [], [])
        self.clear_activity()
        self.refresh_dashboard_activity_feed()
        self.add_activity("Dashboard live telemetry and activity view cleared; saved conversations are unchanged.")

    def run_dashboard_workflow(self):
        self.add_activity("Dashboard workflow started.")
        self.switch_page("assistant")
        self.assistant_input.setPlainText("status")
        self.process_command("status")

    # ========================================================
    # QUICK COMMAND
    # ========================================================

    def create_quick_command(
        self,
        layout,
        title,
        command,
    ):

        button = QPushButton(f"›  {title}")

        button.setObjectName("quickCommand")

        button.setCursor(Qt.PointingHandCursor)

        button.clicked.connect(
            lambda checked=False, value=command: self.run_quick_command(value)
        )

        layout.addWidget(button)

    def create_agent_card(self, layout, row, column, icon, title, prompt):
        """A dashboard shortcut that sends a useful prompt through the normal AI path."""
        button = QPushButton(f"{icon}  {title}\n     READY")
        button.setObjectName("agentCard")
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(f"Ask the {title.lower()}")
        button.clicked.connect(
            lambda checked=False, value=prompt: self.run_quick_command(value)
        )
        layout.addWidget(button, row, column)

    # ========================================================
    # APPLICATION SETTINGS
    # ========================================================

    def apply_runtime_settings(self, values=None, announce=True):
        values = dict(values or nexus_settings.load_user_settings())

        try:
            self.command_engine.reload_configuration()
        except Exception:
            pass

        language = str(values.get("voice_language", "auto") or "auto")
        self.current_voice_language = language
        self.pending_voice_language = "auto"

        if hasattr(self, "voice_language_combo"):
            index = self.voice_language_combo.findData(language)
            if index >= 0:
                self.voice_language_combo.blockSignals(True)
                self.voice_language_combo.setCurrentIndex(index)
                self.voice_language_combo.blockSignals(False)

        self.set_voice_mode(bool(values.get("voice_enabled", False)))

        background_voice = getattr(self, "background_voice", None)
        if background_voice is not None:
            if self.settings.legacy_openai_voice_enabled:
                background_voice.start()
            else:
                background_voice.stop()

        if hasattr(self, "assistant_model_badge"):
            self.refresh_assistant_metrics()
        self.update_dashboard_greeting()
        if announce:
            self.add_activity("NEXUS settings applied.")

    def apply_reset_preferences(self):
        self.apply_accent_color("#45d9ff")
        self.update_dashboard_greeting("")
        self.apply_runtime_settings(nexus_settings.load_user_settings(), announce=False)

    def open_settings_page(self):
        self.switch_page("settings")

    # ========================================================
    # DASHBOARD COMMAND
    # ========================================================

    def handle_dashboard_command(
        self,
        command,
    ):

        command = str(command or "").strip()
        attachment = getattr(self, "dashboard_attachment", None)
        if attachment:
            if not command:
                command = "Please review the attached file and explain its contents."
            command += (
                f"\n\n[Attached text file: {attachment['name']}]\n"
                f"{attachment['content']}\n[End attached file]"
            )
            self.clear_dashboard_attachment()

        self.dashboard_input.clear()

        if not command:
            return

        self.set_core_state("thinking")

        self.assistant_input.setPlainText(command)

        self.process_command(command)

    def get_selected_voice_language(self):
        if hasattr(self, "voice_language_combo"):
            data = self.voice_language_combo.currentData()
            return str(data or "auto")
        return "auto"

    def set_voice_language(self, index):
        if hasattr(self, "voice_language_combo"):
            language = self.voice_language_combo.itemData(index)
            self.current_voice_language = str(language or "auto")
        else:
            self.current_voice_language = "auto"

        if self.current_voice_language == "auto":
            self.add_activity("Voice language set to Automatic.")
        else:
            labels = {
                "en": "English",
                "fr": "French",
                "sw": "Swahili",
                "es": "Spanish",
                "de": "German",
                "it": "Italian",
                "pt": "Portuguese",
                "rw": "Kinyarwanda",
            }
            self.add_activity(
                f"Voice language set to {labels.get(self.current_voice_language, self.current_voice_language)}."
            )

    def set_voice_mode(self, enabled):
        self.voice_enabled = bool(enabled)

        text = "Voice on" if self.voice_enabled else "Voice"

        if hasattr(
            self,
            "voice_toggle",
        ):
            self.voice_toggle.blockSignals(True)
            self.voice_toggle.setChecked(self.voice_enabled)
            self.voice_toggle.setText(text)
            self.voice_toggle.blockSignals(False)

        if hasattr(
            self,
            "assistant_voice_toggle",
        ):
            self.assistant_voice_toggle.blockSignals(True)
            self.assistant_voice_toggle.setChecked(self.voice_enabled)
            self.assistant_voice_toggle.setText(text)
            self.assistant_voice_toggle.blockSignals(False)

        if self.voice_enabled:
            self.add_activity("Nexus voice output enabled.")
        else:
            self.add_activity("Nexus voice output disabled.")

    def capture_voice_command(self):
        worker = getattr(self, "voice_worker", None)
        if worker is not None and worker.isRunning():
            # A second click while listening means "I am done talking".
            worker.finish_listening()
            return

        # Speaking over NEXUS interrupts it, and also keeps its own voice out of the microphone.
        if self.voice_output_active:
            self.interrupt_voice_output()
        local_route = VoiceCaptureWorker.route(self.settings.ai_engine) == "local"

        # The background wake listener uses the same microphone. Pause it
        # before the foreground voice capture starts.
        background_voice = getattr(self, "background_voice", None)
        if background_voice is not None:
            background_voice.stop()

        language = self.get_selected_voice_language()
        self.pending_voice_language = language
        self.set_core_state("listening")
        if hasattr(self, "dashboard_mic_status"):
            self.dashboard_mic_status.setText("● MICROPHONE ACTIVE")
            self.dashboard_mic_status.setObjectName("online")
            self.dashboard_mic_status.style().unpolish(self.dashboard_mic_status)
            self.dashboard_mic_status.style().polish(self.dashboard_mic_status)

        # Give immediate visual feedback while the microphone captures speech.
        if hasattr(self, "assistant_status"):
            self.assistant_status.setText("● LISTENING")
        if hasattr(self, "mic_button"):
            self.mic_button.setEnabled(local_route)
            self._set_button_icon(self.mic_button, "mic")
            self.mic_button.setProperty("listening", True)
            self.mic_button.style().unpolish(self.mic_button)
            self.mic_button.style().polish(self.mic_button)
            self.mic_button.setToolTip("Listening - click to stop, Esc to cancel" if local_route else "NEXUS is listening...")
        if hasattr(self, "assistant_mic_button"):
            self.assistant_mic_button.setEnabled(local_route)
            self._set_button_icon(self.assistant_mic_button, "mic")
            self.assistant_mic_button.setProperty("listening", True)
            self.assistant_mic_button.style().unpolish(self.assistant_mic_button)
            self.assistant_mic_button.style().polish(self.assistant_mic_button)
            self.assistant_mic_button.setToolTip("Listening - click to stop, Esc to cancel" if local_route else "NEXUS is listening...")

        language_name = {
            "auto": "Automatic",
            "en": "English",
            "fr": "French",
            "sw": "Swahili",
            "es": "Spanish",
            "de": "German",
            "it": "Italian",
            "pt": "Portuguese",
            "rw": "Kinyarwanda",
        }.get(language, language)

        if local_route:
            voice_route = "on-device speech recognition"
        else:
            voice_route = "Gemini Live online"
        self.add_activity(f"Microphone active — {voice_route} ({language_name})…")

        current = self.conversation_manager.get_messages(self.current_conversation_id) if self.current_conversation_id is not None else []
        history = [{"role": item.get("role", "user"), "content": item.get("content", "")} for item in current[-12:]]
        self.voice_worker = VoiceCaptureWorker(language, self.settings.ai_engine, history, self, settings=self.settings)
        self.voice_worker.status.connect(self.add_activity)
        self.voice_worker.captured.connect(self.handle_voice_command)
        self.voice_worker.geminiCompleted.connect(self.handle_gemini_voice_result)
        self.voice_worker.failed.connect(self.handle_voice_error)
        self.voice_worker.finished.connect(self.finish_voice_capture)
        self.voice_worker.start()

    def finish_voice_capture(self):
        if hasattr(self, "mic_button"):
            self.mic_button.setEnabled(True)
            self.mic_button.setProperty("listening", False)
            self._set_button_icon(self.mic_button, "mic")
            self.mic_button.style().unpolish(self.mic_button)
            self.mic_button.style().polish(self.mic_button)
            self.mic_button.setToolTip("Speak a command")

        if hasattr(self, "assistant_mic_button"):
            self.assistant_mic_button.setEnabled(True)
            self.assistant_mic_button.setProperty("listening", False)
            self._set_button_icon(self.assistant_mic_button, "mic")
            self.assistant_mic_button.style().unpolish(self.assistant_mic_button)
            self.assistant_mic_button.style().polish(self.assistant_mic_button)
            self.assistant_mic_button.setToolTip("Speak a command")

        # Do not overwrite THINKING/ERROR after a recognized command.
        if hasattr(self, "assistant_status"):
            current = self.assistant_status.text()
            if current == "● LISTENING":
                self.assistant_status.setText("● READY")

        if getattr(self.dashboard_core_widget, "state", "sleeping") in {"listening", "speaking"}:
            self.set_core_idle_state()
        self.voice_output_active = False
        if hasattr(self, "dashboard_mic_status"):
            self.dashboard_mic_status.setText("● MIC READY")
            self.dashboard_mic_status.setObjectName("mutedText")
            self.dashboard_mic_status.style().unpolish(self.dashboard_mic_status)
            self.dashboard_mic_status.style().polish(self.dashboard_mic_status)

        background_voice = getattr(self, "background_voice", None)
        if background_voice is not None:
            background_voice.start()

    def handle_voice_command(self, command, detected_language):
        from core.gemini_engine import redact_secrets
        command = redact_secrets(command)
        command = command.strip()

        self.current_voice_language = str(
            detected_language
            or self.pending_voice_language
            or "auto"
        )

        self.pending_voice_language = "auto"

        if not command or command.startswith("No speech detected"):
            self.add_activity(
                command or "No speech detected."
            )
            if hasattr(self, "assistant_status"):
                self.assistant_status.setText("● READY")
            self.set_core_idle_state()
            return

        self.add_activity(
            f"Voice command recognized "
            f"({self.current_voice_language}): {command}"
        )

        # You spoke, so NEXUS answers aloud. This lasts for the session only; the Voice
        # toggle in the header turns it off again and Settings is not changed.
        if not self.voice_enabled:
            self.set_voice_mode(True)
            self.add_activity("Voice output turned on for this session because you used the microphone.")

        self.assistant_input.setPlainText(command)
        self.process_command(command)

    def handle_gemini_voice_result(self, transcript, response, audio):
        """Persist a Gemini Live turn in the existing conversation history."""
        self.set_core_state("speaking")
        self.voice_output_active = True
        from core.gemini_engine import redact_secrets
        conversation_id = self.ensure_conversation()
        user_text = redact_secrets(str(transcript or "Voice message")).strip()
        answer = redact_secrets(str(response or "")).strip()
        if not answer:
            self.handle_voice_error("Gemini Live returned no answer.")
            return
        self.conversation_manager.add_message(conversation_id, "user", user_text)
        conversation = self.conversation_manager.get_conversation(conversation_id)
        if conversation and conversation.get("title") == "New Conversation":
            self.conversation_manager.update_title(conversation_id, self.conversation_manager.create_title_from_message(user_text))
        self.conversation_manager.add_message(conversation_id, "assistant", answer)
        self.current_voice_language = self.pending_voice_language or "auto"
        self.pending_voice_language = "auto"
        self.ai_success_count += 1
        self.add_activity(f"NEXUS (Gemini Live): {answer}")
        self.refresh_conversation_list()
        self.render_current_conversation()
        self.assistant_status.setText("● READY")

    # ========================================================
    # DOCUMENT SUMMARY
    # ========================================================

    def start_document_summary(self, path_text=""):
        worker = getattr(self, "document_worker", None)
        if worker is not None and worker.isRunning():
            self.add_activity("A document summary is already in progress.")
            return
        if not path_text:
            path_text, _ = QFileDialog.getOpenFileName(
                self,
                "Choose a document to summarise",
                str(Path.home()),
                "Text documents (*.txt *.md *.csv *.log *.json *.xml *.yaml *.yml *.ini *.html *.py);;All files (*)",
            )
            if not path_text:
                self.add_activity("Document summary cancelled.")
                return

        name = Path(str(path_text).strip("\"'")).name or str(path_text)
        if self.settings.ai_engine == "online":
            where = "Gemini online (the text will leave this PC because Online mode is selected)"
        else:
            where = "the local model on this PC (the text is not uploaded)"
        self.add_activity(f"Summarising {name} with {where}...")

        conversation_id = self.ensure_conversation()
        user_text = f"Summarize the document: {name}"
        self.conversation_manager.add_message(conversation_id, "user", user_text)
        conversation = self.conversation_manager.get_conversation(conversation_id)
        if conversation and conversation.get("title") == "New Conversation":
            self.conversation_manager.update_title(
                conversation_id, self.conversation_manager.create_title_from_message(user_text)
            )
        self.refresh_conversation_list()
        self.render_current_conversation()
        self.set_core_state("thinking")
        self.assistant_status.setText("● THINKING")

        self._summary_conversation_id = conversation_id
        self.document_worker = DocumentSummaryWorker(self.command_engine.ai, path_text, self)
        self.document_worker.done.connect(self.handle_document_summary)
        self.document_worker.failed.connect(self.handle_document_summary_error)
        self.document_worker.start()

    def _finish_document_turn(self, text, ok):
        conversation_id = getattr(self, "_summary_conversation_id", None)
        if conversation_id is not None:
            self.conversation_manager.add_message(conversation_id, "assistant", text)
        self.refresh_conversation_list()
        self.render_current_conversation()
        self.set_core_idle_state()
        self.assistant_status.setText("● READY" if ok else "● ERROR")
        if self.voice_enabled:
            try:
                self.speak_response(text, self.current_voice_language)
            except Exception as error:  # noqa: BLE001
                self.add_activity(f"Voice output error: {error}")

    def handle_document_summary(self, name, summary, where):
        self.add_activity(f"Summary of {name} ready ({where}).")
        self._finish_document_turn(f"**Summary of {name}**\n\n{summary}\n\n_Produced by {where}._", True)

    def handle_document_summary_error(self, message, file_problem):
        self.add_activity(message)
        self._finish_document_turn(message, file_problem)

    def handle_voice_error(self, message):
        self.set_core_idle_state()
        self.voice_output_active = False
        if hasattr(self, "assistant_status"):
            self.assistant_status.setText("● ERROR")

        self.add_activity(
            f"Voice input unavailable: {message}"
        )

    def _ensure_speech_manager(self):
        """Shared local speech engine: Kokoro, with the Windows voice as fallback."""
        if self.kokoro_speech_queue is None:
            from core.voice import KokoroSpeechQueue, VoiceService

            self.kokoro_speech_queue = KokoroSpeechQueue(self.settings)
            VoiceService._active_kokoro_queue = self.kokoro_speech_queue
        return self.kokoro_speech_queue

    def speak_response(self, response, language=None):  # noqa: F811
        """Speak a response with the configured local engine (Kokoro / Windows voice)."""
        if not response or not self.voice_enabled:
            return

        if self.settings.legacy_openai_voice_enabled:
            self._speak_response_legacy_openai(response, language)
            return

        manager = self._ensure_speech_manager()
        if manager.enqueue(response, language or self.current_voice_language or "auto"):
            self.voice_output_active = True
            self.set_core_state("speaking")
            if hasattr(self, "assistant_status"):
                self.assistant_status.setText("● SPEAKING")
        else:
            self.add_activity(f"Voice output unavailable: {manager.last_error}")

    def _poll_speech(self):
        """Report engine changes/failures and detect when speech has finished."""
        manager = self.kokoro_speech_queue
        if manager is None:
            return
        notice = manager.pop_notice()
        while notice:
            self.add_activity(notice)
            notice = manager.pop_notice()
        if self.voice_output_active and not manager.busy:
            if not (self.voice_speech_thread is not None and self.voice_speech_thread.isRunning()):
                self.voice_output_active = False
                self.set_core_idle_state(voice_output_finished=True)
                if hasattr(self, "assistant_status") and self.pending_ai_requests == 0:
                    self.assistant_status.setText("● READY")
                if manager.last_error and not manager.last_engine:
                    self.add_activity(f"Voice output unavailable: {manager.last_error}")

    def _speak_response_legacy_openai(self, response, language=None):

        if (
            self.voice_speech_thread is not None
            and self.voice_speech_thread.isRunning()
        ):
            return

        self.voice_speech_thread = QThread(self)

        self.voice_speech_worker = VoiceSpeakWorker(
            response,
            language or self.current_voice_language or self.get_selected_voice_language(),
        )

        self.voice_speech_worker.moveToThread(self.voice_speech_thread)

        self.voice_speech_thread.started.connect(self.voice_speech_worker.run)

        self.voice_speech_worker.started.connect(self.handle_voice_speech_started)

        self.voice_speech_worker.finished.connect(self.handle_voice_speech_finished)

        self.voice_speech_worker.error.connect(self.handle_voice_speech_error)

        self.voice_speech_worker.finished.connect(self.voice_speech_thread.quit)

        self.voice_speech_worker.error.connect(self.voice_speech_thread.quit)

        self.voice_speech_thread.finished.connect(
            self.voice_speech_worker.deleteLater
        )

        self.voice_speech_thread.finished.connect(self.cleanup_voice_speech)

        self.voice_speech_thread.start()

    def handle_voice_speech_started(self):  # noqa: F811
        self.set_core_state("speaking")
        self.voice_output_active = True
        self.add_activity("Nexus voice output started.")

    def handle_voice_speech_finished(self):  # noqa: F811
        was_interrupted = self.voice_output_interrupted
        self.voice_output_active = False
        self.voice_output_interrupted = False
        self.set_core_idle_state(voice_output_finished=True)
        if not was_interrupted:
            self.add_activity("Nexus voice output completed.")

    def handle_voice_speech_error(self, message):  # noqa: F811
        was_interrupted = self.voice_output_interrupted
        self.voice_output_active = False
        self.voice_output_interrupted = False
        self.set_core_idle_state(voice_output_finished=True)
        if not was_interrupted:
            self.add_activity(f"Voice output unavailable: {message}")

    def interrupt_voice_output(self):
        """Cancel active listening, or stop audio playback (never pretends to cancel AI requests)."""
        worker = getattr(self, "voice_worker", None)
        if worker is not None and worker.isRunning() and hasattr(worker, "cancel") and worker.route(worker.engine) == "local":
            worker.cancel()
            self.add_activity("Listening cancelled.")
            return True
        if not self.voice_output_active:
            return False
        try:
            from core.voice import VoiceService
            VoiceService.stop_speaking()
        except Exception as error:  # noqa: BLE001
            self.add_activity(f"Could not interrupt voice playback: {error}")
            return False
        self.voice_output_interrupted = True
        self.voice_output_active = False
        self.set_core_idle_state(voice_output_finished=True)
        self.add_activity("NEXUS voice playback interrupted by the user.")
        return True

    def cleanup_voice_speech(self):  # noqa: F811
        self.voice_speech_worker = None
        self.voice_speech_thread = None

    # ========================================================
    # WINDOWS SHELL EXECUTION
    # ========================================================

    def start_shell_command(self, command, conversation_id, response_language="auto"):
        if self.shell_thread is not None and self.shell_thread.isRunning():
            response = "NEXUS is already executing a Windows command. Please wait for it to finish."
            self.conversation_manager.add_message(conversation_id, "assistant", response)
            self.display_user_and_response(command, response)
            self.add_activity(response)
            return

        self.shell_conversation_id = conversation_id
        self.shell_response_language = response_language or "auto"
        self.shell_command = command

        self.set_core_state("thinking")
        self.assistant_status.setText("● EXECUTING")
        self.add_activity(f"NEXUS executing Windows command: {command}")

        self.shell_thread = QThread(self)
        self.shell_worker = ShellCommandWorker(command)
        self.shell_worker.moveToThread(self.shell_thread)

        self.shell_thread.started.connect(self.shell_worker.run)
        self.shell_worker.started.connect(
            lambda: self.assistant_status.setText("● EXECUTING")
        )
        self.shell_worker.finished.connect(self.handle_shell_finished)
        self.shell_worker.error.connect(self.handle_shell_error)
        self.shell_worker.finished.connect(self.shell_thread.quit)
        self.shell_worker.error.connect(self.shell_thread.quit)
        self.shell_thread.finished.connect(self.shell_worker.deleteLater)
        self.shell_thread.finished.connect(self.cleanup_shell_command)
        self.shell_thread.start()

    def handle_shell_finished(self, response, success):
        conversation_id = self.shell_conversation_id
        if conversation_id is None:
            return

        response = str(response)
        self.conversation_manager.add_message(conversation_id, "assistant", response)
        self.display_user_and_response(
            self.shell_command or "Windows command",
            response,
        )
        self.add_activity("Windows command execution completed." if success else "Windows command completed with errors.")
        self.set_core_idle_state()
        self.assistant_status.setText("● READY" if success else "● ERROR")
        self._thinking_active = False
        self.render_current_conversation()

        if self.voice_enabled:
            try:
                self.speak_response(response, self.shell_response_language)
            except Exception as error:
                self.add_activity(f"Voice output error: {error}")

    def handle_shell_error(self, message):
        conversation_id = self.shell_conversation_id
        response = f"Windows command execution failed: {message}"
        if conversation_id is not None:
            self.conversation_manager.add_message(conversation_id, "assistant", response)
            self.display_user_and_response(
                self.shell_command or "Windows command",
                response,
            )
        self.add_activity(response)
        self._thinking_active = False
        self.set_core_idle_state()
        self.assistant_status.setText("● ERROR")
        self.render_current_conversation()

    def cleanup_shell_command(self):
        self.shell_worker = None
        self.shell_thread = None
        self.shell_conversation_id = None
        self.shell_response_language = "auto"
        self.shell_command = ""

    # ========================================================
    # QUICK COMMAND EXECUTION
    # ========================================================

    def run_quick_command(
        self,
        command,
    ):

        self.switch_page("assistant")

        self.assistant_input.setPlainText(command)

        self.process_command(command)

    # ========================================================
    # DASHBOARD CLOCK
    # ========================================================

    def update_dashboard_clock(self):
        from datetime import datetime
        now = datetime.now()
        current_time = now.strftime("%I:%M:%S %p")
        if hasattr(self, "dashboard_clock"):
            self.dashboard_clock.setText(current_time)
        if hasattr(self, "dashboard_date"):
            self.dashboard_date.setText(now.strftime("%A, %d %B %Y"))
        if hasattr(self, "core_uptime_value"):
            uptime = max(0, int((datetime.now() - self._started_at).total_seconds()))
            hh, rem = divmod(uptime, 3600)
            mm, ss = divmod(rem, 60)
            self.core_uptime_value.setText(f"{hh:02d}:{mm:02d}:{ss:02d}")

    def set_core_state(self, state):
        core = getattr(self, "dashboard_core_widget", None)
        if core is not None:
            core.set_state(state)

    def set_core_idle_state(self, voice_output_finished=False):
        """Choose the truthful non-thinking state without hiding concurrent work."""
        if getattr(self, "pending_ai_requests", 0) > 0:
            self.set_core_state("thinking")
            return

        core = getattr(self, "dashboard_core_widget", None)
        current = getattr(core, "state", "sleeping")
        voice_worker = getattr(self, "voice_worker", None)
        if voice_worker is not None and voice_worker.isRunning():
            self.set_core_state(current if current in {"listening", "speaking"} else "listening")
            return

        speech_thread = getattr(self, "voice_speech_thread", None)
        if speech_thread is not None and speech_thread.isRunning() and not voice_output_finished:
            self.set_core_state("speaking")
            return

        self.set_core_state("sleeping")

    def _wrap_page_for_vertical_fit(self, page, object_name):
        """Wrap a page in a vertical scroll area without introducing horizontal clipping."""
        scroll = QScrollArea()
        scroll.setObjectName(object_name)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(page)
        return scroll

    # ========================================================
    # ASSISTANT PAGE
    # ========================================================

    def create_assistant_page(self):
        page = QWidget()
        page.setMinimumWidth(0)
        page.setMinimumHeight(0)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(16, 14, 16, 14)
        page_layout.setSpacing(10)

        header = QFrame()
        header.setObjectName("assistantHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 9, 14, 9)
        header_layout.setSpacing(11)

        header_layout.addWidget(HudIcon("assistant", 30))
        title_layout = QVBoxLayout()
        title = QLabel("NEXUS AI ASSISTANT")
        title.setObjectName("pageTitle")
        subtitle = QLabel("LOCAL INTELLIGENCE INTERFACE")
        subtitle.setObjectName("mutedText")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        self.assistant_status = QLabel("● READY")
        self.assistant_status.setObjectName("online")
        header_layout.addWidget(self.assistant_status)

        self.assistant_model_badge = QLabel()
        self.assistant_model_badge.setObjectName("modelBadge")
        self.assistant_model_badge.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(self.assistant_model_badge)
        page_layout.addWidget(header)

        workspace = QHBoxLayout()
        workspace.setContentsMargins(0, 0, 0, 0)
        workspace.setSpacing(9)

        # -----------------------------------------------------------------
        # Conversation canvas
        # -----------------------------------------------------------------
        conversation_panel = QFrame()
        conversation_panel.setObjectName("assistantWorkspace")
        conversation_panel.setMinimumWidth(0)
        conversation_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        conversation_layout = QVBoxLayout(conversation_panel)
        conversation_layout.setContentsMargins(8, 8, 8, 8)
        conversation_layout.setSpacing(8)

        canvas_header = QHBoxLayout()
        canvas_title = QLabel("LIVE CONVERSATION")
        canvas_title.setObjectName("hudPanelTitle")
        canvas_header.addWidget(canvas_title)
        canvas_header.addStretch()
        self.current_conversation_title_label = QLabel("New Conversation")
        self.current_conversation_title_label.setObjectName("mutedText")
        self.current_conversation_title_label.setWordWrap(True)
        self.current_conversation_title_label.setMinimumWidth(0)
        self.current_conversation_title_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.current_conversation_title_label.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )
        canvas_header.addWidget(self.current_conversation_title_label, 1)
        conversation_layout.addLayout(canvas_header)

        self.assistant_output = QTextEdit()
        self.assistant_output.setReadOnly(True)
        self.assistant_output.setAcceptRichText(True)
        self.assistant_output.setUndoRedoEnabled(False)
        self.assistant_output.setObjectName("assistantOutput")
        self.assistant_output.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.assistant_output.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.assistant_output.setLineWrapMode(QTextEdit.WidgetWidth)
        self.assistant_output.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.assistant_output.setAcceptRichText(True)
        document = self.assistant_output.document()
        document.setDocumentMargin(7)
        document.setDefaultStyleSheet(
            """
            div, p, td, th, span {
                word-wrap: break-word;
                overflow-wrap: anywhere;
            }
            table {
                width: 100%;
                max-width: 100%;
                table-layout: fixed;
            }
            img {
                max-width: 100%;
            }
            pre, code {
                white-space: pre-wrap;
                word-wrap: break-word;
                overflow-wrap: anywhere;
            }
            """
        )
        self.assistant_output.setMinimumHeight(0)
        self.assistant_output.setMinimumWidth(0)
        conversation_layout.addWidget(self.assistant_output, 1)

        # -----------------------------------------------------------------
        # Input row
        # -----------------------------------------------------------------
        input_panel = QFrame()
        input_panel.setObjectName("askPanel")
        input_layout = QHBoxLayout(input_panel)
        input_layout.setContentsMargins(9, 7, 9, 7)
        input_layout.setSpacing(7)

        self.assistant_mic_button = self.create_header_icon_button(
            "mic", "Speak a command", self.capture_voice_command
        )
        self.assistant_mic_button.setObjectName("assistantMicButton")
        self.assistant_mic_button.setText("")
        self.assistant_mic_button.setFixedSize(42, 42)
        input_layout.addWidget(self.assistant_mic_button)

        self.assistant_input = TerminalInput()
        self.assistant_input.setObjectName("assistantInput")
        self.assistant_input.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        input_wrap = self.assistant_input.document().defaultTextOption()
        input_wrap.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.assistant_input.document().setDefaultTextOption(input_wrap)
        self.assistant_input.setMinimumHeight(42)
        self.assistant_input.setMaximumHeight(86)
        self.assistant_input.sendRequested.connect(self.process_command)
        self.assistant_input.clearRequested.connect(self.clear_assistant_chat)
        self.assistant_input.newConversationRequested.connect(self.start_new_conversation)
        input_layout.addWidget(self.assistant_input, 1)

        self.voice_language_combo = QComboBox()
        self.voice_language_combo.setObjectName("voiceLanguageCombo")
        self.voice_language_combo.setFixedWidth(104)
        for code, label in (
            ("auto", "Automatic"),
            ("en", "English"),
            ("fr", "French"),
            ("sw", "Swahili"),
            ("es", "Spanish"),
            ("de", "German"),
            ("it", "Italian"),
            ("pt", "Portuguese"),
            ("rw", "Kinyarwanda"),
        ):
            self.voice_language_combo.addItem(label, code)
        self.voice_language_combo.currentIndexChanged.connect(self.set_voice_language)
        input_layout.addWidget(self.voice_language_combo)

        self.assistant_voice_toggle = QPushButton("VOICE")
        self.assistant_voice_toggle.setObjectName("secondaryButton")
        self.assistant_voice_toggle.setFixedSize(68, 41)
        self.assistant_voice_toggle.setCheckable(True)
        self.assistant_voice_toggle.setChecked(False)
        self.assistant_voice_toggle.toggled.connect(self.set_voice_mode)
        input_layout.addWidget(self.assistant_voice_toggle)

        send_button = self.create_header_icon_button(
            "send", "Send message", lambda: self.process_command(self.assistant_input.toPlainText())
        )
        send_button.setObjectName("sendIconButton")
        send_button.setFixedSize(43, 41)
        input_layout.addWidget(send_button)
        conversation_layout.addWidget(input_panel)

        hint = QLabel("ENTER Send   •   SHIFT+ENTER New line   •   ESC Clear input")
        hint.setObjectName("shortcutHint")
        hint.setAlignment(Qt.AlignRight)
        conversation_layout.addWidget(hint)
        workspace.addWidget(conversation_panel, 1)

        # -----------------------------------------------------------------
        # Right telemetry rail — all values are tied to real NEXUS state.
        # -----------------------------------------------------------------
        rail = QWidget()
        self.assistant_rail = rail
        rail.setObjectName("assistantRail")
        rail.setMinimumWidth(225)
        rail.setMaximumWidth(300)
        rail.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(0, 0, 0, 0)
        rail_layout.setSpacing(10)

        core_panel, core_layout = self.create_hud_panel("AI CORE STATUS")
        core_identity = QHBoxLayout()
        core_identity.addWidget(HudIcon("assistant", 28))
        identity_text = QVBoxLayout()
        core_name = QLabel("NEXUS AI CORE")
        core_name.setObjectName("railCoreName")
        core_sub = QLabel("LOCAL LLM INTERFACE")
        core_sub.setObjectName("mutedText")
        identity_text.addWidget(core_name)
        identity_text.addWidget(core_sub)
        core_identity.addLayout(identity_text, 1)
        self.core_online_badge = QLabel("● ONLINE")
        self.core_online_badge.setObjectName("onlineBadge")
        core_identity.addWidget(self.core_online_badge)
        core_layout.addLayout(core_identity)

        self.core_model_value = self.create_dynamic_stat(core_layout, "MODEL", "—")
        self.core_context_value = self.create_dynamic_stat(core_layout, "CONTEXT", "0 messages")
        self.core_responses_value = self.create_dynamic_stat(core_layout, "RESPONSES", "0")
        self.core_uptime_value = self.create_dynamic_stat(core_layout, "UPTIME", "00:00:00")
        rail_layout.addWidget(core_panel)

        stats_panel, stats_layout = self.create_hud_panel("CONVERSATION STATS")
        self.stat_conversations_value = self.create_dynamic_stat(stats_layout, "TOTAL CONVERSATIONS", "0")
        self.stat_messages_value = self.create_dynamic_stat(stats_layout, "MESSAGES EXCHANGED", "0")
        self.stat_latency_value = self.create_dynamic_stat(stats_layout, "AVG RESPONSE TIME", "—")
        self.stat_success_value = self.create_dynamic_stat(stats_layout, "SUCCESS RATE", "—")
        rail_layout.addWidget(stats_panel)

        actions_panel, actions_layout = self.create_hud_panel("QUICK ACTIONS")
        action_grid = QGridLayout()
        action_grid.setSpacing(7)
        self.create_icon_action(action_grid, 0, 0, "trash", "Clear Chat", self.clear_assistant_chat)
        self.create_icon_action(action_grid, 0, 1, "chat", "Conversations", lambda: self.switch_page("conversations"))
        self.create_icon_action(action_grid, 1, 0, "info", "System Info", lambda: self.run_quick_command("system"))
        self.create_icon_action(action_grid, 1, 1, "help", "Help", lambda: self.run_quick_command("help"))
        self.create_icon_action(action_grid, 2, 0, "activity", "Activity", lambda: self.switch_page("activity"))
        self.create_icon_action(action_grid, 2, 1, "settings", "Settings", lambda: self.switch_page("settings"))
        actions_layout.addLayout(action_grid)
        rail_layout.addWidget(actions_panel)
        rail_layout.addStretch(1)

        workspace.addWidget(rail, 0)
        workspace.setStretch(0, 1)
        workspace.setStretch(1, 0)
        page_layout.addLayout(workspace, 1)
        self.refresh_assistant_metrics()
        return self._wrap_page_for_vertical_fit(page, "assistantScroll")

    def create_dynamic_stat(self, layout, label, value):
        row = QFrame()
        row.setObjectName("statLine")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(7, 6, 7, 6)
        label_widget = QLabel(label)
        label_widget.setObjectName("telemetryLabel")
        label_widget.setMinimumWidth(0)
        label_widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        value_widget = QLabel(value)
        value_widget.setObjectName("statLineValue")
        value_widget.setWordWrap(True)
        value_widget.setMinimumWidth(0)
        value_widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        value_widget.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_layout.addWidget(label_widget, 1)
        row_layout.addWidget(value_widget, 1)
        layout.addWidget(row)
        return value_widget

    def create_icon_action(self, layout, row, column, icon_kind, text, callback):
        button = QPushButton()
        button.setObjectName("actionButton")
        button.setCursor(Qt.PointingHandCursor)
        button_layout = QHBoxLayout(button)
        button_layout.setContentsMargins(9, 7, 8, 7)
        button_layout.setSpacing(7)
        button_layout.addWidget(HudIcon(icon_kind, 21))
        label = QLabel(str(text))
        label.setObjectName("buttonText")
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        button_layout.addWidget(label, 1)
        button.clicked.connect(callback)
        layout.addWidget(button, row, column)
        return button

    def refresh_assistant_metrics(self):
        if not hasattr(self, "assistant_output"):
            return
        model = getattr(self.settings, "ai_model", nexus_settings.NEXUS_MODEL)
        if hasattr(self, "assistant_model_badge"):
            mode = self.settings.ai_engine
            labels = {
                "automatic": f"AUTO · LOCAL FIRST · {model}",
                "online": f"GEMINI · {self.settings.gemini_text_model}",
                "local": f"LOCAL · {model}",
            }
            self.assistant_model_badge.setText(labels.get(mode, str(model).upper()))
            from core.gemini_engine import gemini_is_configured
            self.assistant_model_badge.setToolTip(
                "Gemini key configured — routed prompts may be processed online."
                if gemini_is_configured()
                else "Gemini key not configured — Online text and Gemini Live voice require GEMINI_API_KEY."
            )
        if hasattr(self, "dashboard_engine_label"):
            mode = self.settings.ai_engine
            badge_text = {
                "automatic": f"AUTO / LOCAL FIRST / {model}",
                "online": f"GEMINI / {self.settings.gemini_text_model}",
                "local": f"LOCAL / {model}",
            }
            self.dashboard_engine_label.setText(badge_text.get(mode, "NEXUS READY"))
            self.dashboard_engine_label.setToolTip(
                "Prompts are routed according to the selected engine setting."
            )
        current_messages = []
        if self.current_conversation_id is not None:
            try:
                current_messages = self.conversation_manager.get_messages(self.current_conversation_id)
            except Exception:
                current_messages = []
        if hasattr(self, "current_conversation_title_label"):
            conversation = self.conversation_manager.get_conversation(self.current_conversation_id) if self.current_conversation_id is not None else None
            self.current_conversation_title_label.setText(str(conversation.get("title", "New Conversation")) if conversation else "New Conversation")
        if hasattr(self, "core_model_value"):
            self.core_model_value.setText(str(model))
        if hasattr(self, "core_context_value"):
            self.core_context_value.setText(f"{len(current_messages)} messages")
        conversations = self.conversation_manager.get_conversations()
        total_messages = 0
        total_responses = 0
        for conversation in conversations:
            try:
                messages = self.conversation_manager.get_messages(conversation["id"])
                total_messages += len(messages)
                total_responses += sum(1 for m in messages if m.get("role") == "assistant")
            except Exception:
                continue
        if hasattr(self, "core_responses_value"):
            self.core_responses_value.setText(str(total_responses))
        uptime = max(0, int((__import__("datetime").datetime.now() - self._started_at).total_seconds()))
        hh, rem = divmod(uptime, 3600)
        mm, ss = divmod(rem, 60)
        if hasattr(self, "core_uptime_value"):
            self.core_uptime_value.setText(f"{hh:02d}:{mm:02d}:{ss:02d}")
        if hasattr(self, "stat_conversations_value"):
            self.stat_conversations_value.setText(str(len(conversations)))
        if hasattr(self, "stat_messages_value"):
            self.stat_messages_value.setText(str(total_messages))
        if hasattr(self, "stat_latency_value"):
            self.stat_latency_value.setText(f"{(sum(self.response_times)/len(self.response_times)):.1f}s" if self.response_times else "—")
        if hasattr(self, "stat_success_value"):
            rate = (self.ai_success_count / self.ai_request_count * 100.0) if self.ai_request_count else None
            self.stat_success_value.setText(f"{rate:.0f}%" if rate is not None else "—")
        if hasattr(self, "assistant_status") and self.shell_thread is not None and self.shell_thread.isRunning():
            self.assistant_status.setText("● EXECUTING")

    def send_assistant_message(self):

        if not hasattr(
            self,
            "assistant_input",
        ):
            return

        command = (
            self.assistant_input
            .toPlainText()
            .strip()
        )

        if not command:
            self.dashboard_input.setFocus()
            return

        self.assistant_input.clear()

        self.process_command(
            command
        )

    # ========================================================
    # HUD COMPONENTS
    # ========================================================

    def create_hud_panel(self, title, badge=None):
        panel = QFrame()
        panel.setObjectName("hudPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        header = QHBoxLayout()
        label = QLabel(title)
        label.setObjectName("hudPanelTitle")
        header.addWidget(label)
        header.addStretch()
        if badge:
            status = QLabel(badge)
            status.setObjectName("online")
            header.addWidget(status)
        layout.addLayout(header)
        return panel, layout

    def create_stat_line(self, label, value):
        row = QFrame()
        row.setObjectName("statLine")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 6, 8, 6)
        name = QLabel(label)
        name.setObjectName("telemetryLabel")
        content = QLabel(value)
        content.setObjectName("statLineValue")
        content.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(name)
        layout.addWidget(content, 1)
        return row

    def create_action_button(self, layout, row, column, text, callback):
        button = QPushButton(text)
        button.setObjectName("actionButton")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(callback)
        layout.addWidget(button, row, column)

    # ========================================================
    # SYSTEM PAGE
    # ========================================================

    def create_system_page(self):
        """Reference-style system monitor using real local telemetry."""
        page = QWidget()
        page.setMinimumWidth(0)
        page.setMinimumHeight(0)

        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(10, 10, 10, 10)
        page_layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setObjectName("systemScroll")
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content = QWidget()
        content.setMinimumWidth(1220)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(2, 2, 2, 2)
        content_layout.setSpacing(10)
        scroll.setWidget(content)
        self.system_scroll = scroll
        page_layout.addWidget(scroll, 1)

        # ====================================================
        # TOP ROW — SYSTEM MONITOR + LIVE STATISTICS
        # ====================================================
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        monitor_panel = QFrame()
        monitor_panel.setObjectName("systemReferencePanel")
        monitor_panel.setMinimumWidth(790)
        monitor_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        monitor_layout = QVBoxLayout(monitor_panel)
        monitor_layout.setContentsMargins(14, 10, 14, 10)
        monitor_layout.setSpacing(7)

        monitor_header = QHBoxLayout()
        monitor_header.setSpacing(9)
        monitor_icon_badge = QFrame()
        monitor_icon_badge.setObjectName("systemHeaderIconBadge")
        monitor_icon_badge.setFixedSize(46, 46)
        monitor_icon_layout = QHBoxLayout(monitor_icon_badge)
        monitor_icon_layout.setContentsMargins(0, 0, 0, 0)
        monitor_icon_layout.setAlignment(Qt.AlignCenter)
        monitor_icon_layout.addWidget(HudIcon("nexus", 28))
        monitor_header.addWidget(monitor_icon_badge)

        monitor_titles = QVBoxLayout()
        monitor_title = QLabel("SYSTEM MONITOR")
        monitor_title.setObjectName("systemReferenceTitle")
        monitor_subtitle = QLabel("REAL-TIME HARDWARE AND SYSTEM TELEMETRY")
        monitor_subtitle.setObjectName("systemReferenceSubtitle")
        monitor_titles.addWidget(monitor_title)
        monitor_titles.addWidget(monitor_subtitle)
        monitor_header.addLayout(monitor_titles, 1)

        self.system_status_label = QLabel("● LIVE")
        self.system_status_label.setObjectName("systemLiveBadge")
        self.system_status_label.setAlignment(Qt.AlignCenter)
        self.system_status_label.setMinimumWidth(82)
        self.system_status_label.setFixedHeight(34)
        monitor_header.addWidget(self.system_status_label)
        monitor_layout.addLayout(monitor_header)

        self.system_cards_container = QWidget()
        cards_grid = QGridLayout(self.system_cards_container)
        cards_grid.setContentsMargins(0, 3, 0, 0)
        cards_grid.setHorizontalSpacing(8)
        cards_grid.setVerticalSpacing(6)

        self.system_cpu_card = self.create_system_card("CPU", "cpu", "0%", "#2aaeff")
        self.system_memory_card = self.create_system_card("MEMORY", "memory", "0%", "#35e5d2")
        self.system_storage_card = self.create_system_card("STORAGE", "storage", "0%", "#9663ff")
        self.system_battery_card = self.create_system_card("BATTERY", "battery", "N/A", "#54e993")

        for index, card in enumerate((
            self.system_cpu_card,
            self.system_memory_card,
            self.system_storage_card,
            self.system_battery_card,
        )):
            cards_grid.addWidget(card, 0, index)
            cards_grid.setColumnStretch(index, 1)

        monitor_layout.addWidget(self.system_cards_container)
        top_row.addWidget(monitor_panel, 1)

        stats_panel = QFrame()
        stats_panel.setObjectName("systemReferencePanel")
        stats_panel.setMinimumWidth(365)
        stats_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        stats_layout = QVBoxLayout(stats_panel)
        stats_layout.setContentsMargins(14, 10, 14, 10)
        stats_layout.setSpacing(7)

        stats_header = QHBoxLayout()
        stats_icon = HudIcon("activity", 27)
        stats_header.addWidget(stats_icon)
        stats_title = QLabel("LIVE SYSTEM STATISTICS")
        stats_title.setObjectName("systemReferenceTitleSmall")
        stats_header.addWidget(stats_title)
        stats_header.addStretch()
        stats_layout.addLayout(stats_header)

        stats_body = QHBoxLayout()
        stats_body.setSpacing(12)
        stats_list = QVBoxLayout()
        stats_list.setSpacing(5)

        self.system_live_rows = {}
        live_specs = (
            ("cpu_temp", "thermometer", "CPU Temperature", "Unavailable", "#2aaeff"),
            ("gpu_load", "gpu", "GPU Load", "Unavailable", "#35e5d2"),
            ("download", "download", "Network (Download)", "0.0 MB/s", "#21d9ff"),
            ("upload", "upload", "Network (Upload)", "0.0 MB/s", "#9663ff"),
            ("uptime", "clock", "Uptime", "Unavailable", "#54e993"),
        )
        for key, icon_kind, label_text, value_text, color in live_specs:
            row = QFrame()
            row.setObjectName("systemLiveStatRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 1, 0, 1)
            row_layout.setSpacing(7)
            badge = QFrame()
            badge.setObjectName("systemStatIconBadge")
            badge.setFixedSize(38, 38)
            badge_layout = QHBoxLayout(badge)
            badge_layout.setContentsMargins(0, 0, 0, 0)
            badge_layout.setAlignment(Qt.AlignCenter)
            icon = HudIcon(icon_kind, 22)
            icon.setProperty("hudColor", color)
            badge_layout.addWidget(icon)
            row_layout.addWidget(badge)
            text_box = QVBoxLayout()
            text_box.setSpacing(0)
            label = QLabel(label_text)
            label.setObjectName("systemLiveStatLabel")
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            value = QLabel(value_text)
            value.setObjectName("systemLiveStatValue")
            value.setWordWrap(True)
            value.setMinimumWidth(0)
            text_box.addWidget(label)
            text_box.addWidget(value)
            row_layout.addLayout(text_box, 1)
            stats_list.addWidget(row)
            self.system_live_rows[key] = value
        stats_list.addStretch(1)
        stats_body.addLayout(stats_list, 1)

        stats_visuals = QVBoxLayout()
        stats_visuals.setSpacing(6)
        self.system_live_graph = SystemMiniGraphWidget()
        self.system_live_graph.setMinimumSize(175, 105)
        stats_visuals.addWidget(self.system_live_graph)
        self.system_live_bars = {}
        for key, label_text, color in (
            ("cpu", "CPU", "#2aaeff"),
            ("memory", "Memory", "#21d9e7"),
            ("disk", "Disk", "#9663ff"),
            ("battery", "Battery", "#54e993"),
        ):
            bar = CompactProgressBar(color=color)
            bar.setObjectName("systemCompactBar")
            stats_visuals.addWidget(self._create_compact_bar_row(label_text, bar))
            self.system_live_bars[key] = bar
        stats_body.addLayout(stats_visuals, 1)
        stats_layout.addLayout(stats_body, 1)
        top_row.addWidget(stats_panel, 0)
        content_layout.addLayout(top_row)

        # ====================================================
        # MIDDLE ROW — ACTIVITY + INFORMATION + HARDWARE
        # ====================================================
        middle_row = QHBoxLayout()
        middle_row.setSpacing(10)

        activity_panel = QFrame()
        activity_panel.setObjectName("systemReferencePanel")
        activity_panel.setMinimumWidth(570)
        activity_layout = QVBoxLayout(activity_panel)
        activity_layout.setContentsMargins(14, 10, 14, 10)
        activity_header = QHBoxLayout()
        activity_header.addWidget(HudIcon("waveform", 23))
        activity_title = QLabel("SYSTEM ACTIVITY")
        activity_title.setObjectName("systemReferenceTitleSmall")
        activity_header.addWidget(activity_title)
        activity_header.addStretch()
        activity_header.addWidget(QLabel("LIVE"))
        activity_layout.addLayout(activity_header)
        self.system_page_graph = SystemGraphWidget()
        self.system_page_graph.setMinimumHeight(205)
        activity_layout.addWidget(self.system_page_graph, 1)
        middle_row.addWidget(activity_panel, 13)

        info_panel = QFrame()
        info_panel.setObjectName("systemReferencePanel")
        info_panel.setMinimumWidth(300)
        info_layout = QVBoxLayout(info_panel)
        info_layout.setContentsMargins(14, 10, 14, 10)
        info_header = QHBoxLayout()
        info_header.addWidget(HudIcon("info", 23))
        info_title = QLabel("SYSTEM INFORMATION")
        info_title.setObjectName("systemReferenceTitleSmall")
        info_header.addWidget(info_title)
        info_header.addStretch()
        info_layout.addLayout(info_header)
        self.system_info_grid = QGridLayout()
        self.system_info_grid.setContentsMargins(2, 8, 2, 0)
        self.system_info_grid.setHorizontalSpacing(9)
        self.system_info_grid.setVerticalSpacing(7)
        self.system_info_labels = {}
        for row_index, key in enumerate(("os", "cpu", "ram", "gpu", "storage", "hostname", "ip")):
            label = QLabel(key.upper() if key != "ip" else "IP ADDRESS")
            label.setObjectName("systemInfoKey")
            value = QLabel("Reading…")
            value.setObjectName("systemInfoValue")
            value.setWordWrap(True)
            value.setMinimumWidth(0)
            self.system_info_grid.addWidget(label, row_index, 0)
            self.system_info_grid.addWidget(value, row_index, 1)
            self.system_info_grid.setColumnStretch(1, 1)
            self.system_info_labels[key] = value
        info_layout.addLayout(self.system_info_grid, 1)
        middle_row.addWidget(info_panel, 8)

        hardware_panel = QFrame()
        hardware_panel.setObjectName("systemReferencePanel")
        hardware_panel.setMinimumWidth(290)
        hardware_layout = QVBoxLayout(hardware_panel)
        hardware_layout.setContentsMargins(14, 10, 14, 10)
        hardware_header = QHBoxLayout()
        hardware_header.addWidget(HudIcon("cpu", 23))
        hardware_title = QLabel("HARDWARE OVERVIEW")
        hardware_title.setObjectName("systemReferenceTitleSmall")
        hardware_header.addWidget(hardware_title)
        hardware_header.addStretch()
        hardware_layout.addLayout(hardware_header)
        self.system_hardware_bars = {}
        for key, label_text, icon_kind, color in (
            ("cpu", "CPU", "cpu", "#2aaeff"),
            ("memory", "Memory", "memory", "#21d9e7"),
            ("disk", "Storage", "storage", "#9663ff"),
            ("battery", "Battery", "battery", "#54e993"),
        ):
            row, bar = self._create_hardware_overview_row(label_text, icon_kind, color)
            hardware_layout.addWidget(row)
            self.system_hardware_bars[key] = bar
        hardware_layout.addStretch(1)
        middle_row.addWidget(hardware_panel, 8)
        content_layout.addLayout(middle_row)

        # ====================================================
        # BOTTOM ROW — LOGS + QUICK COMMANDS
        # ====================================================
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)

        logs_panel = QFrame()
        logs_panel.setObjectName("systemReferencePanel")
        logs_panel.setMinimumWidth(690)
        logs_layout = QVBoxLayout(logs_panel)
        logs_layout.setContentsMargins(14, 10, 14, 8)
        logs_header = QHBoxLayout()
        logs_header.addWidget(HudIcon("process", 23))
        logs_title = QLabel("SYSTEM LOGS")
        logs_title.setObjectName("systemReferenceTitleSmall")
        logs_header.addWidget(logs_title)
        logs_header.addStretch()
        logs_view = QPushButton("View All")
        logs_view.setObjectName("dashboardLinkButton")
        logs_view.clicked.connect(lambda: self.switch_page("activity"))
        logs_header.addWidget(logs_view)
        logs_layout.addLayout(logs_header)
        self.system_logs_output = QPlainTextEdit()
        self.system_logs_output.setObjectName("systemLogsOutput")
        self.system_logs_output.setReadOnly(True)
        self.system_logs_output.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        logs_layout.addWidget(self.system_logs_output, 1)
        bottom_row.addWidget(logs_panel, 4)

        commands_panel = QFrame()
        commands_panel.setObjectName("systemReferencePanel")
        commands_panel.setMinimumWidth(500)
        commands_layout = QVBoxLayout(commands_panel)
        commands_layout.setContentsMargins(14, 10, 14, 8)
        commands_header = QHBoxLayout()
        commands_header.addWidget(HudIcon("bolt", 23))
        commands_title = QLabel("QUICK COMMANDS")
        commands_title.setObjectName("systemReferenceTitleSmall")
        commands_header.addWidget(commands_title)
        commands_header.addStretch()
        commands_view = QPushButton("View All")
        commands_view.setObjectName("dashboardLinkButton")
        commands_view.clicked.connect(lambda: self.switch_page("assistant"))
        commands_header.addWidget(commands_view)
        commands_layout.addLayout(commands_header)
        command_grid = QGridLayout()
        command_grid.setHorizontalSpacing(7)
        command_grid.setVerticalSpacing(7)
        self.create_dashboard_command(command_grid, 0, 0, "system", "System Info", self.show_system_info)
        self.create_dashboard_command(command_grid, 0, 1, "battery", "Battery", self.show_battery_info)
        self.create_dashboard_command(command_grid, 0, 2, "network", "Network", self.show_network_info)
        self.create_dashboard_command(command_grid, 1, 0, "process", "Process List", self.show_process_list)
        self.create_dashboard_command(command_grid, 1, 1, "database", "Disk Usage", self.show_disk_usage)
        self.create_dashboard_command(command_grid, 1, 2, "thermometer", "Temperature", self.show_temperature_info)
        for column in range(3):
            command_grid.setColumnStretch(column, 1)
        commands_layout.addLayout(command_grid, 1)
        bottom_row.addWidget(commands_panel, 3)
        content_layout.addLayout(bottom_row)

        self._load_static_system_info()
        self._refresh_system_logs()
        return page

    def _create_compact_bar_row(self, label_text, bar):
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        head = QHBoxLayout()
        label = QLabel(label_text)
        label.setObjectName("systemBarLabel")
        value = QLabel("0%")
        value.setObjectName("systemBarValue")
        head.addWidget(label)
        head.addStretch()
        head.addWidget(value)
        layout.addLayout(head)
        layout.addWidget(bar)
        bar.value_label = value
        return wrapper

    def _create_hardware_overview_row(self, label_text, icon_kind, color):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(7)
        badge = QFrame()
        badge.setObjectName("systemHardwareIconBadge")
        badge.setFixedSize(38, 38)
        badge_layout = QHBoxLayout(badge)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.setAlignment(Qt.AlignCenter)
        icon = HudIcon(icon_kind, 22)
        icon.setProperty("hudColor", color)
        badge_layout.addWidget(icon)
        layout.addWidget(badge)
        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        header = QHBoxLayout()
        title = QLabel(label_text)
        title.setObjectName("systemHardwareLabel")
        value = QLabel("0%")
        value.setObjectName("systemHardwareValue")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(value)
        text_box.addLayout(header)
        bar = CompactProgressBar(color=color)
        text_box.addWidget(bar)
        bar.value_label = value
        layout.addLayout(text_box, 1)
        return row, bar

    def _load_static_system_info(self):
        """Load identifiers that do not need to be queried every refresh."""
        if self._system_static_info is not None:
            return self._system_static_info

        # This method can be reached by more than one UI refresh path.  Build the
        # snapshot once and keep subprocess work from racing with itself.
        if getattr(self, "_loading_static_system_info", False):
            return self._system_static_info or {}
        self._loading_static_system_info = True

        os_name = f"{platform.system()} {platform.release()}"
        build = platform.version()
        cpu_name = platform.processor() or "Unavailable"

        if os.name == "nt":
            powershell = os.path.join(
                os.environ.get("SystemRoot", r"C:\Windows"),
                "System32",
                "WindowsPowerShell",
                "v1.0",
                "powershell.exe",
            )
            try:
                result = subprocess.run(
                    [powershell, "-NoProfile", "-Command", "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); $OutputEncoding = [Console]::OutputEncoding; (Get-ComputerInfo -Property WindowsProductName,WindowsVersion | ConvertTo-Json -Compress)"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=2,
                    check=False,
                )
                import json
                product = json.loads(result.stdout.strip()) if result.stdout.strip() else {}
                os_product = str(product.get("WindowsProductName") or "").strip()
                os_version = str(product.get("WindowsVersion") or "").strip()
                if os_product:
                    os_name = os_product
                if os_version:
                    build = os_version
            except Exception:  # noqa: BLE001
                pass

            try:
                result = subprocess.run(
                    [powershell, "-NoProfile", "-Command", "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); $OutputEncoding = [Console]::OutputEncoding; (Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=2,
                    check=False,
                )
                friendly_cpu = result.stdout.strip()
                if friendly_cpu:
                    cpu_name = friendly_cpu
            except Exception:  # noqa: BLE001
                pass

        if not cpu_name or cpu_name.lower() in {"generic", "unknown"}:
            cpu_name = "Unavailable"

        hostname = socket.gethostname() or "Unavailable"
        ip_address = "Unavailable"
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                ip_address = sock.getsockname()[0]
        except OSError:
            try:
                ip_address = socket.gethostbyname(hostname)
            except OSError:
                pass

        ram_total_gb = None
        if psutil is not None:
            try:
                ram_total_gb = psutil.virtual_memory().total / (1024 ** 3)
            except Exception:  # noqa: BLE001
                pass

        gpu_name = "Unavailable"
        gpu_load = None
        gpu_temp = None
        if os.name == "nt":
            nvidia = shutil.which("nvidia-smi")
            if nvidia:
                try:
                    result = subprocess.run(
                        [nvidia, "--query-gpu=name,utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=2,
                        check=False,
                    )
                    line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
                    parts = [item.strip() for item in line.split(",")]
                    if parts:
                        gpu_name = parts[0] or gpu_name
                    if len(parts) > 1 and parts[1].isdigit():
                        gpu_load = float(parts[1])
                    if len(parts) > 2 and parts[2].isdigit():
                        gpu_temp = float(parts[2])
                except Exception:  # noqa: BLE001
                    pass

            if gpu_name == "Unavailable":
                powershell = os.path.join(
                    os.environ.get("SystemRoot", r"C:\\Windows"),
                    "System32",
                    "WindowsPowerShell",
                    "v1.0",
                    "powershell.exe",
                )
                try:
                    result = subprocess.run(
                        [powershell, "-NoProfile", "-Command", "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); $OutputEncoding = [Console]::OutputEncoding; (Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join '; '"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=2,
                        check=False,
                    )
                    value = result.stdout.strip()
                    if value:
                        gpu_name = value
                except Exception:  # noqa: BLE001
                    pass

        self._system_static_info = {
            "os": f"{os_name} · {build}" if build else os_name,
            "cpu": cpu_name,
            "ram_total_gb": ram_total_gb,
            "gpu": gpu_name,
            "gpu_load": gpu_load,
            "gpu_temp": gpu_temp,
            "hostname": hostname,
            "ip": ip_address,
        }
        self._apply_static_system_info()
        self._loading_static_system_info = False
        return self._system_static_info

    def _apply_static_system_info(self):
        info = self._system_static_info or {}
        for key, value in {
            "os": info.get("os", "Unavailable"),
            "cpu": info.get("cpu", "Unavailable"),
            "ram": (
                f"{info['ram_total_gb']:.1f} GB"
                if info.get("ram_total_gb") is not None else "Unavailable"
            ),
            "gpu": info.get("gpu", "Unavailable"),
            "hostname": info.get("hostname", "Unavailable"),
            "ip": info.get("ip", "Unavailable"),
        }.items():
            label = self.system_info_labels.get(key) if hasattr(self, "system_info_labels") else None
            if label is not None:
                label.setText(str(value))

    def _update_gpu_telemetry(self):
        """Read optional NVIDIA GPU telemetry without inventing data for other GPUs."""
        info = self._system_static_info or {}
        if os.name != "nt":
            return None, None
        nvidia = shutil.which("nvidia-smi")
        if not nvidia:
            return info.get("gpu_load"), info.get("gpu_temp")
        try:
            result = subprocess.run(
                [nvidia, "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1.5,
                check=False,
            )
            line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
            parts = [item.strip() for item in line.split(",")]
            load = float(parts[0]) if len(parts) > 0 and parts[0].replace(".", "", 1).isdigit() else None
            temp = float(parts[1]) if len(parts) > 1 and parts[1].replace(".", "", 1).isdigit() else None
            return load, temp
        except Exception:  # noqa: BLE001
            return info.get("gpu_load"), info.get("gpu_temp")

    def _update_network_rates(self):
        if psutil is None:
            self._network_download_mbps = 0.0
            self._network_upload_mbps = 0.0
            return
        try:
            counters = psutil.net_io_counters()
            now = time.monotonic()
            if self._network_sample is not None:
                previous_time, previous_recv, previous_sent = self._network_sample
                elapsed = max(0.001, now - previous_time)
                self._network_download_mbps = max(0.0, counters.bytes_recv - previous_recv) / elapsed / (1024 ** 2)
                self._network_upload_mbps = max(0.0, counters.bytes_sent - previous_sent) / elapsed / (1024 ** 2)
            self._network_sample = (now, counters.bytes_recv, counters.bytes_sent)
        except Exception:  # noqa: BLE001
            self._network_download_mbps = 0.0
            self._network_upload_mbps = 0.0

    def _read_cpu_temperature(self):
        if psutil is None:
            return None
        try:
            sensors = psutil.sensors_temperatures()
        except Exception:  # noqa: BLE001
            return None
        candidates = []
        for name, entries in (sensors or {}).items():
            low = str(name).lower()
            for entry in entries:
                label = str(getattr(entry, "label", "") or "").lower()
                current = getattr(entry, "current", None)
                if current is None or not (0 < float(current) < 130):
                    continue
                score = 0
                if any(token in low or token in label for token in ("cpu", "package", "core", "tctl", "tdie")):
                    score += 2
                candidates.append((score, float(current)))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
        return None

    @staticmethod
    def _format_uptime():
        if psutil is None:
            return "Unavailable"
        try:
            seconds = max(0, int(time.time() - psutil.boot_time()))
            days, remainder = divmod(seconds, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes = remainder // 60
            if days:
                return f"{days}d {hours:02d}h {minutes:02d}m"
            return f"{hours}h {minutes:02d}m"
        except Exception:  # noqa: BLE001
            return "Unavailable"

    def _refresh_system_logs(self):
        if not hasattr(self, "system_logs_output"):
            return
        text = "\n".join(self._system_log_entries[-8:]) or "Waiting for telemetry…"
        self.system_logs_output.setPlainText(text)
        cursor = self.system_logs_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.system_logs_output.setTextCursor(cursor)

    def _append_system_log(self, message):
        from datetime import datetime
        stamp = datetime.now().strftime("%H:%M:%S")
        entry = f"● {stamp}   {message}"
        self._system_log_entries.append(entry)
        self._system_log_entries = self._system_log_entries[-30:]
        self._refresh_system_logs()

    def show_system_info(self):
        self.switch_page("system")
        self.add_activity("System information opened.")

    def show_battery_info(self):
        self.switch_page("system")
        battery = getattr(self, "battery_value", None)
        if battery is None:
            self.add_activity("Battery information is unavailable on this PC.")
        else:
            charging = "charging" if battery.get("charging") else "not charging"
            self.add_activity(f"Battery: {battery.get('percent', 0):.0f}% ({charging}).")

    def show_network_info(self):
        self.switch_page("system")
        self.add_activity(
            f"Network: {self._network_download_mbps:.2f} MB/s down, {self._network_upload_mbps:.2f} MB/s up."
        )

    def show_process_list(self):
        self.switch_page("assistant")
        self.assistant_input.setPlainText("show running processes")
        self.process_command("show running processes")

    def show_disk_usage(self):
        self.switch_page("system")
        self.add_activity(f"Storage usage: {self.storage_value or 0:.1f}%.")

    def show_temperature_info(self):
        self.switch_page("system")
        temp = self._read_cpu_temperature()
        if temp is None:
            self.add_activity("CPU temperature is unavailable through the supported local sensors.")
        else:
            self.add_activity(f"CPU temperature: {temp:.1f}°C.")

    def create_system_card(self, title, icon_kind, value, color):
        card = QFrame()
        card.setObjectName("systemMetricCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        card.setMinimumHeight(268)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(9, 7, 9, 7)
        layout.setSpacing(3)

        header = QHBoxLayout()
        header.setSpacing(7)
        badge = QFrame()
        badge.setObjectName("systemMetricIconBadge")
        badge.setFixedSize(38, 38)
        badge_layout = QHBoxLayout(badge)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.setAlignment(Qt.AlignCenter)
        icon = HudIcon(icon_kind, 22)
        icon.setProperty("hudColor", color)
        badge_layout.addWidget(icon)
        header.addWidget(badge)
        title_label = QLabel(title)
        title_label.setObjectName("systemMetricTitle")
        header.addWidget(title_label)
        header.addStretch()
        layout.addLayout(header)

        meter = CircularMeter(title, 0, color=color, show_title=False)
        meter.setFixedSize(148, 148)
        meter.center_label = "BATTERY" if title == "BATTERY" else f"{title} USAGE"
        layout.addWidget(meter, 1, alignment=Qt.AlignCenter)

        detail = QLabel(value)
        detail.setObjectName("systemMetricDetail")
        detail.setAlignment(Qt.AlignCenter)
        detail.setMinimumHeight(18)
        layout.addWidget(detail)

        spark = MiniSparklineWidget(color)
        spark.setMinimumHeight(28)
        card.meter = meter
        card.value_label = detail
        card.detail_label = detail
        card.spark = spark
        card.color = color
        card.title = title
        layout.addWidget(spark)
        return card

    # ========================================================
    # ACTIVITY PAGE
    # ========================================================

    def create_activity_page(self):

        page = QWidget()
        page.setMinimumWidth(0)
        page.setMinimumHeight(0)

        page_layout = QVBoxLayout(page)

        page_layout.setContentsMargins(
            18,
            16,
            18,
            16,
        )

        page_layout.setSpacing(12)

        # ----------------------------------------------------
        # HEADER
        # ----------------------------------------------------

        header = QFrame()

        header.setObjectName("dashboardPanel")

        header_layout = QHBoxLayout(header)

        header_layout.setContentsMargins(
            18,
            12,
            18,
            12,
        )

        title_layout = QVBoxLayout()

        title = QLabel("ACTIVITY")

        title.setObjectName("pageTitle")

        title_layout.addWidget(title)

        subtitle = QLabel("Nexus OPERATIONAL EVENT STREAM")

        subtitle.setObjectName("mutedText")

        title_layout.addWidget(subtitle)

        header_layout.addLayout(title_layout)

        header_layout.addStretch()

        clear_button = QPushButton("Clear Activity")

        clear_button.setObjectName("quickCommand")

        clear_button.clicked.connect(self.clear_activity)

        header_layout.addWidget(clear_button)

        page_layout.addWidget(header)

        # ----------------------------------------------------
        # ACTIVITY OUTPUT
        # ----------------------------------------------------

        self.activity_output = QTextEdit()

        self.activity_output.setReadOnly(True)

        self.activity_output.setAcceptRichText(True)

        self.activity_output.setObjectName("activityOutput")

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(10)
        timeline_panel, timeline_layout = self.create_hud_panel(
            "LIVE ACTIVITY TIMELINE", "● LIVE"
        )
        timeline_layout.addWidget(self.activity_output, 1)
        content.addWidget(timeline_panel, 1)

        rail = QVBoxLayout()
        live_panel, live_layout = self.create_hud_panel("LIVE ACTIVITY FEED", "● LIVE")
        live_layout.addWidget(self.create_stat_line("SYSTEM", "Monitoring active"))
        live_layout.addWidget(self.create_stat_line("AI", "Ready for requests"))
        live_layout.addWidget(self.create_stat_line("MEMORY", "Conversation sync"))
        rail.addWidget(live_panel)

        logs_panel, logs_layout = self.create_hud_panel("SYSTEM LOGS")
        self.log_summary = QLabel("Waiting for events…")
        self.log_summary.setObjectName("timelineText")
        self.log_summary.setWordWrap(True)
        logs_layout.addWidget(self.log_summary)
        rail.addWidget(logs_panel)

        actions_panel, actions_layout = self.create_hud_panel("QUICK ACTIONS")
        action_grid = QGridLayout()
        self.create_action_button(
            action_grid, 0, 0, "+  New", self.start_new_conversation
        )
        self.create_action_button(action_grid, 0, 1, "⌫  Clear", self.clear_activity)
        self.create_action_button(
            action_grid,
            1,
            0,
            "◉  Status",
            lambda: self.run_quick_command("status"),
        )
        self.create_action_button(
            action_grid, 1, 1, "?  Help", lambda: self.run_quick_command("help")
        )
        actions_layout.addLayout(action_grid)
        rail.addWidget(actions_panel)
        rail.addStretch()
        content.addLayout(rail)
        page_layout.addLayout(content, 1)

        return self._wrap_page_for_vertical_fit(page, "activityScroll")

    # ========================================================
    # SYSTEM STATS
    # ========================================================

    def update_system_stats(self):
        """Refresh all real local telemetry used by the dashboard and System page."""
        try:
            info = SystemMonitor.get_system_info()
            cpu = float(info.get("cpu", 0) or 0)
            memory = float(info.get("memory", 0) or 0)
            storage = float(info.get("disk", 0) or 0)
            battery = info.get("battery")
            network = float(info.get("network", 0) or 0)

            self.cpu_value = cpu
            self.memory_value = memory
            self.storage_value = storage
            self.battery_value = battery
            self.refresh_dashboard_metrics()

            if self.dashboard_cpu:
                self.dashboard_cpu.setValue(cpu)
            if self.dashboard_memory:
                self.dashboard_memory.setValue(memory)
            if self.dashboard_storage:
                self.dashboard_storage.setValue(storage)
            if self.dashboard_battery:
                self.dashboard_battery.setValue(0 if battery is None else battery.get("percent", 0))
                self.dashboard_battery.center_label = (
                    "Unavailable" if battery is None else ("Charging" if battery.get("charging") else "Battery")
                )

            # System page metric cards.
            if self.system_cpu_card:
                self.system_cpu_card.value_label.setText(f"{cpu:.0f}%")
                self.system_cpu_card.meter.setValue(cpu)
                self.system_cpu_card.spark.setData(self.cpu_history)
            if self.system_memory_card:
                self.system_memory_card.value_label.setText(f"{memory:.0f}%")
                self.system_memory_card.meter.setValue(memory)
                self.system_memory_card.spark.setData(self.memory_history)
            if self.system_storage_card:
                self.system_storage_card.value_label.setText(f"{storage:.0f}%")
                self.system_storage_card.meter.setValue(storage)
                self.system_storage_card.spark.setData(self.disk_history)
            if self.system_battery_card:
                battery_percent = 0 if battery is None else float(battery.get("percent", 0))
                self.system_battery_card.value_label.setText("Unavailable" if battery is None else ("Charging" if battery.get("charging") else "Not charging"))
                self.system_battery_card.meter.setValue(battery_percent)
                self.system_battery_card.spark.setData([battery_percent])

            # Real capacity/frequency details under the circular meters.
            if psutil is not None:
                try:
                    freq = psutil.cpu_freq().current / 1000.0 if psutil.cpu_freq() else 0.0
                    cores = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 0
                    self.system_cpu_card.detail_label.setText(f"{freq:.1f} GHz  |  {cores} Cores")
                except Exception:  # noqa: BLE001
                    self.system_cpu_card.detail_label.setText("Frequency unavailable")
                try:
                    vm = psutil.virtual_memory()
                    used_gb = vm.used / (1024 ** 3)
                    total_gb = vm.total / (1024 ** 3)
                    self.system_memory_card.detail_label.setText(f"{used_gb:.1f} GB / {total_gb:.1f} GB")
                except Exception:  # noqa: BLE001
                    self.system_memory_card.detail_label.setText("Memory capacity unavailable")
            self.system_storage_card.detail_label.setText(self._format_gb_used_total(storage))

            self.cpu_history.append(cpu)
            self.memory_history.append(memory)
            self.disk_history.append(storage)
            self.network_history.append(min(100, network * 10))
            for history in (self.cpu_history, self.memory_history, self.disk_history, self.network_history):
                if len(history) > self.max_graph_points:
                    del history[:-self.max_graph_points]

            self._update_network_rates()
            static_info = self._load_static_system_info()
            cpu_temp = self._read_cpu_temperature()
            gpu_load, gpu_temp = self._update_gpu_telemetry()
            if cpu_temp is not None:
                self.system_live_rows["cpu_temp"].setText(f"{cpu_temp:.1f}°C")
            else:
                self.system_live_rows["cpu_temp"].setText("Unavailable")
            if gpu_load is not None:
                self.system_live_rows["gpu_load"].setText(f"{gpu_load:.0f}%")
            else:
                self.system_live_rows["gpu_load"].setText("Unavailable")
            self.system_live_rows["download"].setText(f"{self._network_download_mbps:.2f} MB/s")
            self.system_live_rows["upload"].setText(f"{self._network_upload_mbps:.2f} MB/s")
            self.system_live_rows["uptime"].setText(self._format_uptime())

            # Hardware bars use only measured metrics.
            for key, value in (("cpu", cpu), ("memory", memory), ("disk", storage)):
                bar = self.system_hardware_bars.get(key) if hasattr(self, "system_hardware_bars") else None
                if bar is not None:
                    bar.setValue(value)
                    bar.value_label.setText(f"{value:.0f}%")
            if hasattr(self, "system_hardware_bars"):
                battery_bar = self.system_hardware_bars.get("battery")
                if battery_bar is not None:
                    battery_value = 0 if battery is None else float(battery.get("percent", 0))
                    battery_bar.setValue(battery_value)
                    battery_bar.value_label.setText("Unavailable" if battery is None else f"{battery_value:.0f}%")

            if hasattr(self, "system_live_bars"):
                for key, value in (("cpu", cpu), ("memory", memory), ("disk", storage)):
                    bar = self.system_live_bars.get(key)
                    if bar is not None:
                        bar.setValue(value)
                        bar.value_label.setText(f"{value:.0f}%")
                battery_bar = self.system_live_bars.get("battery")
                if battery_bar is not None:
                    battery_value = 0 if battery is None else float(battery.get("percent", 0))
                    battery_bar.setValue(battery_value)
                    battery_bar.value_label.setText("N/A" if battery is None else f"{battery_value:.0f}%")

            if hasattr(self, "system_live_graph"):
                self.system_live_graph.setData(self.cpu_history, self.memory_history)
            if hasattr(self, "system_page_graph"):
                self.system_page_graph.set_data(self.cpu_history, self.memory_history, [], [])
            if hasattr(self, "system_graph"):
                self.system_graph.set_data(self.cpu_history, self.memory_history, self.disk_history, self.network_history)
            self._update_dashboard_sparklines()

            if hasattr(self, "system_info_labels"):
                self.system_info_labels["storage"].setText(
                    f"{self._format_gb_used_total(storage)}"
                )

            # Only add a telemetry log periodically or when battery state changes.
            now = time.monotonic()
            battery_state = None if battery is None else (round(float(battery.get("percent", 0))), bool(battery.get("charging")))
            if battery_state != self._last_battery_log and battery_state is not None:
                charging_text = "Charging" if battery_state[1] else "Not charging"
                self._append_system_log(f"Battery status: {charging_text} ({battery_state[0]}%)")
                self._last_battery_log = battery_state
            if now - self._last_system_log >= 10:
                self._append_system_log(
                    f"Telemetry refresh · CPU {cpu:.0f}% · Memory {memory:.0f}% · Disk {storage:.0f}%"
                )
                self._last_system_log = now

        except Exception as error:  # noqa: BLE001
            print(f"System monitor error: {error}")

    @staticmethod
    def _format_gb_used_total(disk_percent):
        try:
            anchor = Path.home().anchor or os.environ.get("SystemDrive", "C:\\")
            usage = __import__("shutil").disk_usage(anchor)
            used_gb = usage.used / (1024 ** 3)
            total_gb = usage.total / (1024 ** 3)
            return f"{used_gb:.1f} GB / {total_gb:.1f} GB"
        except Exception:  # noqa: BLE001
            return f"{float(disk_percent):.0f}% used"

    # ========================================================
    # CONVERSATION HELPERS
    # ========================================================

    def ensure_conversation(self):

        if self.current_conversation_id is not None:
            conversation = self.conversation_manager.get_conversation(
                self.current_conversation_id
            )

            if conversation:
                return self.current_conversation_id

        conversation_id = self.conversation_manager.create_conversation()

        self.current_conversation_id = conversation_id

        return conversation_id

    # ========================================================
    # START NEW CONVERSATION
    # ========================================================

    def restore_latest_conversation(self):

        try:

            conversations = (
                self.conversation_manager
                .get_conversations()
            )

            if not conversations:

                self.current_conversation_id = None
                return

            latest = conversations[0]

            conversation_id = latest.get(
                "id"
            )

            if conversation_id is None:
                return

            self.load_conversation(
                conversation_id
            )

        except Exception as error:  # noqa: BLE001

            print(
                "Could not restore latest conversation:",
                error,
            )

    def start_new_conversation(self):

        self.current_conversation_id = None

        self.assistant_input.clear()

        if hasattr(
            self,
            "dashboard_input",
        ):
            self.dashboard_input.clear()

        self._thinking_active = False
        self.thinking_timer.stop()
        self.assistant_output.clear()
        self.assistant_output.setHtml(self._empty_conversation_html())
        self.assistant_status.setText("● READY")

        self.add_activity("New conversation ready.")

        self.switch_page("assistant")

        self.refresh_conversation_list()

        self.assistant_input.setFocus()

    # ========================================================
    # REFRESH CONVERSATION LIST
    # ========================================================

    @staticmethod
    def _format_record_time(value):
        if not value:
            return "Local"
        raw = str(value).strip()
        try:
            from datetime import datetime, timedelta
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            now = datetime.now()
            if parsed.date() == now.date():
                return f"Today, {parsed:%I:%M %p}"
            if parsed.date() == (now.date() - timedelta(days=1)):
                return f"Yesterday, {parsed:%I:%M %p}"
            return f"{parsed:%d %b %Y, %I:%M %p}"
        except Exception:  # noqa: BLE001
            return raw[-19:] if len(raw) > 19 else raw

    def refresh_conversation_list(self):
        if not hasattr(self, "conversation_list"):
            return
        current_id = self.current_conversation_id
        conversations = self.conversation_manager.get_conversations()
        self.conversation_list.blockSignals(True)
        self.conversation_list.clear()
        selected_item = None
        for conversation in conversations:
            conversation_id = conversation.get("id")
            title = conversation.get("title", "New Conversation")
            stamp = self._format_record_time(conversation.get("updated_at") or conversation.get("created_at"))
            item = QListWidgetItem()
            # The row widget is the only place where the title is rendered.
            # Keep BOTH DisplayRole and normal item text empty so QListWidget's
            # delegate cannot paint a second copy of the conversation title.
            item.setText("")
            item.setData(Qt.DisplayRole, "")
            item.setData(Qt.UserRole, conversation_id)
            item.setData(Qt.UserRole + 1, str(title))
            item.setSizeHint(QSize(0, 66))
            self.conversation_list.addItem(item)
            item.setText("")
            item.setData(Qt.DisplayRole, "")
            self.conversation_list.setItemWidget(
                item,
                self.create_conversation_row(title, stamp),
            )
            if current_id is not None and conversation_id == current_id:
                selected_item = item
        if selected_item is not None:
            self.conversation_list.setCurrentItem(selected_item)
        self.conversation_list.blockSignals(False)
        self.refresh_assistant_metrics()
        query = self.search_input.text() if hasattr(self, "search_input") else ""
        self.filter_conversations(query)
        self.refresh_dashboard_recent_conversations()
        self.refresh_dashboard_timeline()
    # ========================================================
    # LOAD CONVERSATION FROM LIST
    # ========================================================

    def load_conversation_from_item(
        self,
        item,
    ):

        conversation_id = item.data(Qt.UserRole)

        if conversation_id is None:
            return

        self.load_conversation(conversation_id)

    # ========================================================
    # LOAD CONVERSATION
    # ========================================================

    def load_conversation(self, conversation_id):
        conversation = self.conversation_manager.get_conversation(conversation_id)
        if not conversation:
            return
        self.current_conversation_id = conversation_id
        self._thinking_active = False
        self.thinking_timer.stop()
        self.assistant_status.setText("● READY")
        self.render_current_conversation()
        self.switch_page("assistant")
        self.refresh_conversation_list()

    # ========================================================
    # PROCESS COMMAND
    # ========================================================

    def process_command(
        self,
        command,
    ):

        from core.gemini_engine import redact_secrets
        command = redact_secrets(command).strip()

        if not command:
            return

        # "summarize C:\\notes\\report.txt" reads that file; ordinary questions fall through to the AI.
        from core.documents import parse_summarize_request
        document_request = parse_summarize_request(command)
        if document_request is not None:
            self.assistant_input.clear()
            self.start_document_summary(document_request)
            return

        self.set_core_state("thinking")

        conversation_id = self.ensure_conversation()

        response_language = self.pending_voice_language
        self.pending_voice_language = "auto"

        self.conversation_manager.add_message(
            conversation_id,
            "user",
            command,
        )

        conversation = self.conversation_manager.get_conversation(conversation_id)

        if conversation and conversation["title"] == "New Conversation":

            title = self.conversation_manager.create_title_from_message(command)

            self.conversation_manager.update_title(
                conversation_id,
                title,
            )

        self.refresh_conversation_list()

        # ----------------------------------------------------
        # CLEAR INPUT
        # ----------------------------------------------------

        self.assistant_input.clear()

        # ----------------------------------------------------
        # LOCAL COMMANDS
        # ----------------------------------------------------

        command_lower = command.lower()

        local_commands = {
            "help",
            "status",
            "system",
            "battery",
            "time",
            "about",
            "new",
            "clear",
        }
        
        # Windows shell commands execute in a worker so the UI never blocks
        # while PowerShell/CMD is running.
        is_shell_command = self.command_engine.is_shell_command(command)

        if is_shell_command:
            if self.command_engine.shell_requires_confirmation(command):
                answer = QMessageBox.question(
                    self,
                    "Confirm Windows command",
                    "NEXUS is about to execute this Windows shell command:\n\n"
                    f"{command}\n\nContinue?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    response = "Windows command cancelled."
                    self.conversation_manager.add_message(conversation_id, "assistant", response)
                    self.display_user_and_response(command, response)
                    self.add_activity(response)
                    self.set_core_idle_state()
                    return

            self.start_shell_command(command, conversation_id, response_language)
            return

        # Phase 5: send recognized local PC-control requests to the
        # CommandEngine instead of unnecessarily sending them to Ollama.
        is_pc_command = self.command_engine.is_pc_command(command)

        if command_lower in local_commands or is_pc_command:

            response = self.command_engine.execute(command)

            if response == "__OPEN_NEXUS__":
                self.activate_nexus()
                response = "NEXUS is open."

            if response == "__CLEAR__":

                self.clear_activity()
                self.set_core_idle_state()

                self.conversation_manager.add_message(
                    conversation_id,
                    "assistant",
                    "Activity console cleared.",
                )

                return

            self.conversation_manager.add_message(
                conversation_id,
                "assistant",
                response,
            )

            self.display_user_and_response(
                command,
                response,
            )

            self.add_activity(response)
            self.set_core_idle_state()

            if self.voice_enabled:
                try:
                    self.speak_response(response, response_language)
                except Exception as error:  # noqa: BLE001
                    self.add_activity(f"Voice output error: {error}")

            return

        # ----------------------------------------------------
        # AI REQUEST
        # ----------------------------------------------------

        self.ai_request_count += 1
        self.pending_ai_requests += 1
        self.response_started_at[conversation_id] = __import__("datetime").datetime.now()
        messages = self.conversation_manager.get_messages(conversation_id)

        conversation_history = []

        for message in messages[:-1]:

            conversation_history.append(
                {
                    "role": message["role"],
                    "content": message["content"],
                }
            )

        self.assistant_status.setText("● THINKING")

        self.add_activity(f"Nexus processing: {command}")

        safe_command = escape(command)
        self.thinking_command = command
        self.thinking_index = 0
        self.start_thinking_indicator(safe_command)

        self.ai_voice_languages[conversation_id] = response_language

        thread = QThread()

        worker = AIWorker(
            self.command_engine.ai,
            conversation_id,
            command,
            conversation_history,
            speech_enabled=self.voice_enabled,
            speech_language=response_language,
        )

        worker.moveToThread(thread)

        thread.started.connect(worker.run)

        worker.chunk.connect(self.handle_ai_stream_chunk)
        worker.speech_chunk.connect(self.handle_ai_speech_chunk)

        worker.finished.connect(self.handle_ai_response)

        worker.error.connect(self.handle_ai_error)

        worker.finished.connect(thread.quit)

        worker.error.connect(thread.quit)

        thread.finished.connect(worker.deleteLater)

        thread.finished.connect(self.cleanup_ai_worker)

        self.ai_threads[conversation_id] = thread

        self.ai_workers[conversation_id] = worker

        thread.start()

    # ========================================================
    # DISPLAY USER + RESPONSE
    # ========================================================

    def _empty_conversation_html(self):
        return (
            "<div style='padding:20px 8px; color:#61879d;'>"
            "<table width='100%' cellspacing='0' cellpadding='0'><tr><td align='center'>"
            "<div style='border:1px solid #135879; background:#071827; border-radius:10px; padding:18px; max-width:560px;'>"
            "<div style='color:#58ddff; font-size:16px; font-weight:bold; letter-spacing:1px;'>NEXUS READY</div>"
            "<div style='color:#a6cfe4; font-size:13px; margin-top:6px;'>Start a conversation and NEXUS will keep the conversation history here.</div>"
            "</div></td></tr></table></div>"
        )

    @staticmethod
    def _message_stamp(message):
        for key in ("created_at", "updated_at", "timestamp", "time"):
            value = message.get(key)
            if value:
                return str(value)[-8:]
        return "LOCAL"

    def _message_card_html(self, role, content, stamp):
        is_user = role == "user"
        align = "right" if is_user else "left"
        width = "78%"
        border = "#1c6f99" if is_user else "#166087"
        bg = "#0a2033" if is_user else "#071a2b"
        avatar_bg = "#123e58" if is_user else "#0b3046"
        accent = "#5fe1ff" if is_user else "#39e2c2"
        name = "YOU" if is_user else "NEXUS"
        if is_user:
            user_text = self._soft_wrap_long_tokens(str(content))
            body = f"<div style='width:100%; color:#d9ecf5; font-size:13px; line-height:1.55; word-wrap:break-word; overflow-wrap:anywhere; white-space:pre-wrap;'>{escape(user_text).replace(chr(10), '<br>')}</div>"
        else:
            body = self.render_markdown(str(content))
        return (
            f"<div style='padding:7px 3px; width:100%;'>"
            f"<table width='100%' cellspacing='0' cellpadding='0' style='table-layout:fixed;'><tr><td align='{align}'>"
            f"<table width='{width}' cellspacing='0' cellpadding='0' style='width:{width}; max-width:100%; table-layout:fixed; background:{bg}; border:1px solid {border}; border-radius:11px;'>"
            f"<tr><td style='padding:10px 12px; word-wrap:break-word; overflow-wrap:anywhere;'>"
            f"<table width='100%' cellspacing='0' cellpadding='0' style='width:100%; max-width:100%; table-layout:fixed;'><tr>"
            f"<td width='34' style='vertical-align:top;'><div style='background:{avatar_bg}; border:1px solid {accent}; border-radius:17px; width:30px; height:30px; text-align:center;'>"
            f"<span style='color:{accent}; font-size:16px; line-height:30px;'>{'◉' if is_user else '✦'}</span>"
            f"</div></td>"
            f"<td style='vertical-align:top; padding-left:8px; word-wrap:break-word; overflow-wrap:anywhere;'>"
            f"<div style='color:{accent}; font-weight:bold; font-size:12px; letter-spacing:1px; word-wrap:break-word;'>{name}<span style='color:#5f8298; font-weight:normal; margin-left:10px;'>{escape(stamp)}</span></div>"
            f"<div style='margin-top:7px; color:#d9ecf5; word-wrap:break-word; overflow-wrap:anywhere;'>{body}</div>"
            f"</td></tr></table>"
            f"</td></tr></table>"
            f"</td></tr></table></div>"
        )

    def render_current_conversation(self):
        if not hasattr(self, "assistant_output"):
            return
        messages = []
        if self.current_conversation_id is not None:
            try:
                messages = self.conversation_manager.get_messages(self.current_conversation_id)
            except Exception:
                messages = []
        html_parts = []
        for message in messages:
            role = str(message.get("role", "assistant"))
            if role not in {"user", "assistant"}:
                continue
            html_parts.append(self._message_card_html(role, message.get("content", ""), self._message_stamp(message)))
        if not html_parts:
            html_parts.append(self._empty_conversation_html())
        live_text = self.streaming_ai_responses.get(self.current_conversation_id, "")
        if live_text:
            html_parts.append(self._message_card_html("assistant", live_text + " ▌", "LIVE"))
        if self._thinking_active and not live_text:
            html_parts.append(
                "<div style='padding:7px 3px;'>"
                "<table width='100%' cellspacing='0' cellpadding='0'><tr><td align='left'>"
                "<table width='64%' cellspacing='0' cellpadding='0' style='background:#071a2b; border:1px solid #1b688f; border-radius:10px;'>"
                "<tr><td style='padding:12px; color:#58ddff; font-size:13px;'><b>NEXUS</b> &nbsp; ● PROCESSING REQUEST...</td></tr>"
                "</table></td></tr></table></div>"
            )
        self.assistant_output.setHtml("".join(html_parts))
        self.assistant_output.moveCursor(QTextCursor.End)
        self.assistant_output.ensureCursorVisible()
        self.refresh_assistant_metrics()

    def start_thinking_indicator(self, safe_command):
        self.thinking_command = safe_command
        self._thinking_active = True
        self.assistant_status.setText("● THINKING")
        self.render_current_conversation()

    def update_thinking_indicator(self):
        # The processing card is intentionally static; it does not delay or animate UI.
        if not self._thinking_active:
            self.thinking_timer.stop()

    @staticmethod
    def _soft_wrap_long_tokens(text, limit=28):
        """Insert invisible break opportunities into long unbroken strings."""
        import re

        source = str(text or "")
        return re.sub(
            rf"(\S{{{limit}}})(?=\S)",
            lambda match: match.group(1) + "\u200b",
            source,
        )

    def render_markdown(self, text):
        text = self._soft_wrap_long_tokens(text)
        html = markdown(text, extensions=["fenced_code", "tables"])
        html = html.replace(
            "<table>",
            "<table style='border-collapse: collapse; width: 100%; margin: 10px 0; border: 1px solid #194764; background: #091b29;'>",
        )
        html = html.replace("<thead>", "<thead style='background:#0e2a3e;'>")
        html = html.replace(
            "<th>",
            "<th style='padding:8px 10px; border:1px solid #194764; background:#0e2a3e; color:#aeefff; text-align:left; font-weight:bold;'>",
        )
        html = html.replace(
            "<td>",
            "<td style='padding:8px 10px; border:1px solid #194764; color:#dce9f5; vertical-align:top;'>",
        )
        html = html.replace(
            "<pre>",
            "<pre style='background:#071823; border:1px solid #194764; border-radius:7px; padding:10px; color:#dce9f5; white-space:pre-wrap; word-wrap:break-word; overflow-wrap:anywhere;'>",
        )
        html = html.replace(
            "<code>",
            "<code style='background:#0d2638; color:#dce9f5; padding:2px 5px; border-radius:4px; white-space:pre-wrap; word-wrap:break-word; overflow-wrap:anywhere;'>",
        )
        return "<div style='color:#dce9f5; line-height:1.6; font-size:13px; word-wrap:break-word; overflow-wrap:anywhere;'>" + html + "</div>"

    def display_user_and_response(self, command, response):
        self._thinking_active = False
        self.thinking_timer.stop()
        self.render_current_conversation()

    def display_assistant_response(self, response):
        self._thinking_active = False
        self.thinking_timer.stop()
        self.render_current_conversation()

    # ========================================================
    # AI STREAMING + RESPONSE HANDLER
    # ========================================================

    def handle_ai_stream_chunk(self, conversation_id, text):
        """Append streamed text and refresh the visible conversation incrementally."""
        if not text:
            return
        self.streaming_ai_responses[conversation_id] = (
            self.streaming_ai_responses.get(conversation_id, "") + str(text)
        )
        if conversation_id == self.current_conversation_id:
            self.render_current_conversation()

    def handle_ai_speech_chunk(self, conversation_id, text, language="auto"):
        """Queue a completed phrase for speech while the local model keeps generating."""
        if not text or not self.voice_enabled or self.settings.legacy_openai_voice_enabled:
            return
        try:
            manager = self._ensure_speech_manager()
            if manager.enqueue(text, language):
                self.kokoro_streamed_conversations.add(conversation_id)
                self.voice_output_active = True
                if hasattr(self, "assistant_status"):
                    self.assistant_status.setText("● SPEAKING")
            elif not self._kokoro_unavailable_notified:
                self._kokoro_unavailable_notified = True
                self.add_activity("Voice output unavailable: " + (manager.last_error or "no speech engine found."))
        except Exception as error:  # noqa: BLE001
            if not self._kokoro_unavailable_notified:
                self._kokoro_unavailable_notified = True
                self.add_activity(f"Speech could not start: {error}")

    def handle_ai_response(
        self,
        conversation_id,
        message,
        response,
    ):

        self.pending_ai_requests = max(0, self.pending_ai_requests - 1)
        self.set_core_idle_state()

        conversation = (
            self.conversation_manager
            .get_conversation(
                conversation_id
            )
        )

        if not conversation:

            self.add_activity(
                "AI response received for "
                "a conversation that no longer exists."
            )

            self.refresh_conversation_list()

            return

        kokoro_spoke_this_response = conversation_id in self.kokoro_streamed_conversations
        self.kokoro_streamed_conversations.discard(conversation_id)
        self.streaming_ai_responses.pop(conversation_id, None)

        try:

            self.conversation_manager.add_message(
                conversation_id,
                "assistant",
                response,
            )

        except Exception as error:  # noqa: BLE001

            self.add_activity(
                "Could not save AI response: "
                f"{error}"
            )

            if (
                conversation_id
                == self.current_conversation_id
            ):

                self.thinking_timer.stop()
                self._thinking_active = False
                self.assistant_status.setText("● ERROR")
                self.render_current_conversation()

            return

        started = self.response_started_at.pop(conversation_id, None)
        if started is not None:
            elapsed = max(0.0, (__import__("datetime").datetime.now() - started).total_seconds())
            self.response_times.append(elapsed)
            self.response_times = self.response_times[-50:]
        self.ai_success_count += 1

        if (
            conversation_id
            == self.current_conversation_id
        ):

            self.thinking_timer.stop()
            self._thinking_active = False

            self.assistant_status.setText(
                "● READY"
            )

            self.render_current_conversation()

            self.add_activity(
                response
            )

            if getattr(
                self,
                "voice_enabled",
                False,
            ) and not kokoro_spoke_this_response:

                try:
                    response_language = self.ai_voice_languages.pop(
                        conversation_id,
                        self.current_voice_language,
                    )
                    self.speak_response(
                        response,
                        response_language,
                    )
                except Exception as error:  # noqa: BLE001

                    self.add_activity(
                        "Voice output error: "
                        f"{error}"
                    )

        self.ai_voice_languages.pop(
            conversation_id,
            None,
        )

        self.refresh_conversation_list()

    # ========================================================
    # AI ERROR HANDLER
    # ========================================================

    def handle_ai_error(
        self,
        conversation_id,
        message,
        error,
    ):

        error_message = "Nexus could not complete " "the request.\n\n" f"Error: {error}"
        self.streaming_ai_responses.pop(conversation_id, None)
        self.pending_ai_requests = max(0, self.pending_ai_requests - 1)
        self.set_core_idle_state()

        self.conversation_manager.add_message(
            conversation_id,
            "assistant",
            error_message,
        )

        started = self.response_started_at.pop(conversation_id, None)
        if started is not None:
            elapsed = max(0.0, (__import__("datetime").datetime.now() - started).total_seconds())
            self.response_times.append(elapsed)
            self.response_times = self.response_times[-50:]

        if conversation_id == self.current_conversation_id:

            self.thinking_timer.stop()
            self._thinking_active = False
            self.assistant_status.setText("● ERROR")
            self.render_current_conversation()
            self.add_activity(error_message)

        self.refresh_conversation_list()

    # ========================================================
    # CLEANUP AI WORKER
    # ========================================================

    def cleanup_ai_worker(
        self,
    ):

        sender = self.sender()

        if sender is None:
            return

        conversation_id = None

        for (
            cid,
            thread,
        ) in list(self.ai_threads.items()):

            if thread is sender:
                conversation_id = cid
                break

        if conversation_id is None:
            return

        thread = self.ai_threads.pop(
            conversation_id,
            None,
        )

        self.ai_workers.pop(
            conversation_id,
            None,
        )

        if thread:
            thread.deleteLater()

        self.refresh_conversation_list()

    # ========================================================
    # ACTIVITY
    # ========================================================

    def add_activity(
        self,
        text,
    ):

        from datetime import datetime

        self.activity_events.append(
            (
                datetime.now().strftime("%H:%M:%S"),  # noqa: DTZ005
                str(text),
            )
        )
        self.activity_events = self.activity_events[-60:]
        self.refresh_activity_view()
        self.refresh_dashboard_activity_feed()
        self.refresh_dashboard_recent_conversations()
        self.refresh_dashboard_timeline()

    def refresh_activity_view(self):
        if not hasattr(self, "activity_output"):
            return
        cards = []
        for stamp, text in reversed(self.activity_events):
            cards.append(
                "<div style='margin:7px 4px; padding:11px 14px; border:1px solid #12618a; "
                "border-left:3px solid #29d8ff; border-radius:7px; background:#071b2a;'>"
                f"<span style='color:#31dfff; font-weight:bold;'>◉  Nexus</span>"
                f"<span style='float:right; color:#6f9eb6;'>{escape(stamp)}</span>"
                f"<p style='margin:7px 0 0 24px; color:#c5e5f4;'>{escape(text)}</p></div>"
            )
        self.activity_output.setHtml(
            "".join(cards)
            or "<p style='color:#6f9eb6;'>No activity recorded yet.</p>"
        )
        if hasattr(self, "log_summary"):
            recent = self.activity_events[-5:]
            self.log_summary.setText(
                "\n".join(f"● {stamp}  {text[:42]}" for stamp, text in recent)
                or "Waiting for events…"
            )

    # ========================================================
    # CLEAR ACTIVITY
    # ========================================================

    def clear_assistant_chat(self):
        self._thinking_active = False
        self.thinking_timer.stop()
        if hasattr(self, "assistant_output"):
            self.assistant_output.clear()
            self.assistant_output.setHtml(self._empty_conversation_html())
        if hasattr(self, "assistant_status"):
            self.assistant_status.setText("● READY")
        self.add_activity("Chat view cleared; saved conversation history is unchanged.")
        if hasattr(self, "assistant_input"):
            self.assistant_input.setFocus()

    def clear_activity(self):
        if hasattr(self, "activity_output"):
            self.activity_output.clear()
        self.activity_events.clear()
        self.refresh_activity_view()

    # ========================================================
    # CONVERSATION CONTEXT MENU
    # ========================================================

    def show_conversation_context_menu(
        self,
        position,
    ):

        item = self.conversation_list.itemAt(position)

        if item is None:
            return

        conversation_id = item.data(Qt.UserRole)

        menu = QMenu(self)

        rename_action = menu.addAction("Rename")

        delete_action = menu.addAction("Delete")

        action = menu.exec(self.conversation_list.mapToGlobal(position))

        if action == rename_action:

            self.rename_conversation(conversation_id)

        elif action == delete_action:

            self.delete_conversation(conversation_id)

    # ========================================================
    # RENAME CONVERSATION
    # ========================================================

    def rename_conversation(
        self,
        conversation_id,
    ):

        conversation = self.conversation_manager.get_conversation(conversation_id)

        if not conversation:
            return

        title, ok = QInputDialog.getText(
            self,
            "Rename Conversation",
            "Conversation name:",
            text=conversation["title"],
        )

        if not ok:
            return

        title = title.strip()

        if not title:
            return

        self.conversation_manager.update_title(
            conversation_id,
            title,
        )

        self.refresh_conversation_list()

    # ========================================================
    # DELETE CONVERSATION
    # ========================================================

    def delete_conversation(
        self,
        conversation_id,
    ):

        conversation = self.conversation_manager.get_conversation(conversation_id)

        if not conversation:
            return

        reply = QMessageBox.question(
            self,
            "Delete Conversation",
            ("Delete this conversation?\n\n" f"{conversation['title']}"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        self.conversation_manager.delete_conversation(conversation_id)

        if self.current_conversation_id == conversation_id:

            self.current_conversation_id = None

            self._thinking_active = False
            self.assistant_output.clear()
            self.assistant_output.setHtml(self._empty_conversation_html())

        self.refresh_conversation_list()


    def resizeEvent(self, event):
        super().resizeEvent(event)

        width = self.width()

        # Sidebar gives space to the page on compact windows while remaining
        # at the full reference width on normal desktop sizes.
        if hasattr(self, "sidebar"):
            sidebar_width = 220 if width < 1120 else 246
            self.sidebar.setMinimumWidth(sidebar_width)
            self.sidebar.setMaximumWidth(sidebar_width)
            if getattr(self, "_last_sidebar_width", None) != sidebar_width:
                self._last_sidebar_width = sidebar_width
                if hasattr(self, "conversation_list"):
                    self.refresh_conversation_list()

        # On genuinely compact windows the transcript gets priority. The
        # reference-style telemetry rail remains visible on normal desktops
        # but yields completely on small widths instead of covering content.
        if hasattr(self, "assistant_rail"):
            compact_rail = width < 1050
            self.assistant_rail.setVisible(not compact_rail)
            if not compact_rail:
                rail_width = 255 if width < 1250 else 300
                self.assistant_rail.setMinimumWidth(rail_width)
                self.assistant_rail.setMaximumWidth(rail_width)

        if hasattr(self, "global_header"):
            compact_header = width < 1050
            brand = self.global_header.findChild(QWidget)
            # The header itself stays functional; only nonessential spacing
            # tightens so the clock and action buttons never run outside it.
            if compact_header:
                self.global_header.setFixedHeight(70)
            else:
                self.global_header.setFixedHeight(80)

        # Smaller meter circles keep the four system cards on one visible row.
        if hasattr(self, "system_cpu_card"):
            compact = width < 1080
            size = 100 if compact else 122
            for card_name in (
                "system_cpu_card",
                "system_memory_card",
                "system_storage_card",
                "system_battery_card",
            ):
                card = getattr(self, card_name, None)
                if card is not None and hasattr(card, "meter"):
                    card.meter.setFixedSize(size, size)

        # Recalculate conversation item heights after the sidebar changes
        # width, so wrapped titles receive enough vertical room.
        if hasattr(self, "conversation_list"):
            for index in range(self.conversation_list.count()):
                item = self.conversation_list.item(index)
                row = self.conversation_list.itemWidget(item)
                if row is not None:
                    item.setSizeHint(QSize(0, max(58, row.sizeHint().height() + 2)))

        central_widget = self.centralWidget()
        if central_widget is not None and self.system_check_overlay is not None:
            self.system_check_overlay.setGeometry(central_widget.rect())


    # ============================================================


# SYSTEM GRAPH WIDGET
# ============================================================


class SystemGraphWidget(QWidget):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.cpu_data = []
        self.memory_data = []
        self.disk_data = []
        self.network_data = []

        self.setMinimumHeight(150)

        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

    # ========================================================
    # SET GRAPH DATA
    # ========================================================

    def set_data(
        self,
        cpu_data,
        memory_data,
        disk_data=None,
        network_data=None,
    ):

        self.cpu_data = list(cpu_data)

        self.memory_data = list(memory_data)
        self.disk_data = list(disk_data or [])
        self.network_data = list(network_data or [])

        self.update()

    # ========================================================
    # PAINT GRAPH
    # ========================================================

    def paintEvent(self, event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        painter.fillRect(rect, QColor("#071522"))

        compact = self.width() < 470
        legend_width = 0 if compact else min(165, max(120, int(self.width() * 0.30)))
        left = 31
        top = 10
        bottom = 25
        right = 8 + legend_width
        graph_width = max(80, rect.width() - left - right)
        graph_height = max(60, rect.height() - top - bottom)

        # Subtle chart grid.
        painter.setPen(QPen(QColor("#10293a"), 1))
        for index in range(5):
            y = top + graph_height * index / 4
            painter.drawLine(left, int(y), left + graph_width, int(y))
        for index in range(6):
            x = left + graph_width * index / 5
            painter.drawLine(int(x), top, int(x), top + graph_height)

        painter.setFont(QFont("Segoe UI", 7))
        painter.setPen(QPen(QColor("#527086"), 1))
        for label, fraction in (("100", 0), ("75", .25), ("50", .5), ("25", .75), ("0", 1)):
            y = top + graph_height * fraction
            painter.drawText(3, int(y + 3), label)

        if not self.cpu_data:
            painter.drawText(
                QRectF(left, top, graph_width, graph_height),
                Qt.AlignCenter,
                "WAITING FOR SYSTEM TELEMETRY",
            )
        else:
            self.draw_line(painter, self.cpu_data, left, top, graph_width, graph_height, "#45d9ff")
            self.draw_line(painter, self.memory_data, left, top, graph_width, graph_height, "#35e5d2")
            self.draw_line(painter, self.disk_data, left, top, graph_width, graph_height, "#8c7cff")
            self.draw_line(painter, self.network_data, left, top, graph_width, graph_height, "#9663ff")

        # Time labels mirror the supplied reference while staying legible.
        painter.setPen(QPen(QColor("#527086"), 1))
        painter.setFont(QFont("Segoe UI", 7))
        labels = ("12AM", "4AM", "8AM", "12PM", "4PM", "8PM")
        for i, label in enumerate(labels):
            x = left + graph_width * i / (len(labels) - 1)
            painter.drawText(QRectF(x - 22, rect.height() - 18, 44, 13), Qt.AlignCenter, label)

        # Reference-style right legend with live values.
        if not compact:
            base_x = int(rect.width() - legend_width + 12)
            latest = tuple(item for item in (
                ("CPU", self.cpu_data, "#45d9ff"),
                ("Memory", self.memory_data, "#35e5d2"),
                ("Disk", self.disk_data, "#8c7cff"),
                ("Network", self.network_data, "#9663ff"),
            ) if item[1])
            row_y = 18
            painter.setFont(QFont("Segoe UI", 8))
            for name, values, color in latest:
                value = values[-1] if values else 0
                painter.setPen(QPen(QColor(color), 2))
                painter.drawEllipse(QPointF(base_x + 5, row_y + 2), 5, 5)
                painter.setPen(QPen(QColor("#cfe8f6"), 1))
                painter.drawText(base_x + 17, row_y + 6, name)
                painter.setPen(QPen(QColor("#8db1c5"), 1))
                suffix = " MB/s" if name == "Network" else "%"
                display = f"{value:.0f}{suffix}" if name != "Network" else f"{value / 10:.1f} MB/s"
                painter.drawText(int(rect.right() - 4 - legend_width + 78), row_y + 6, display)
                row_y += 25

        painter.end()

    # ========================================================
    # DRAW DATA LINE
    # ========================================================

    def draw_line(
        self,
        painter,
        data,
        left,
        top,
        width,
        height,
        color,
    ):

        if not data:
            return

        pen = QPen(
            QBrush(color),
            2,
        )

        pen.setCapStyle(Qt.RoundCap)

        pen.setJoinStyle(Qt.RoundJoin)

        painter.setPen(pen)

        if len(data) == 1:

            value = max(
                0,
                min(
                    100,
                    float(data[0]),
                ),
            )

            x = left + width / 2

            y = top + height - (value / 100 * height)

            painter.drawEllipse(
                QPointF(x, y),
                3,
                3,
            )

            return

        points = []

        count = len(data)

        for index, value in enumerate(data):

            value = max(
                0,
                min(
                    100,
                    float(value),
                ),
            )

            x = left + (width * index / (count - 1))

            y = top + height - (value / 100 * height)

            points.append(
                QPointF(
                    x,
                    y,
                )
            )

        for index in range(len(points) - 1):

            painter.drawLine(
                points[index],
                points[index + 1],
            )
            