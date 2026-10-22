"""The NEXUS mark.

A luminous "N" drawn as three light beams joined at four glowing nodes (a *nexus* is a
point where connections meet), set in a glass panel inside a gunmetal tile. The sidebar
logo, chat avatars, the window/taskbar and tray icons, and ``assets/nexus.ico`` (used by
the .exe and the installer) are all drawn by :func:`paint_mark`, so the identity is the
same everywhere.
"""
from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)

BEAM_START = "#3fe0ff"   # cyan
BEAM_END = "#9a7bff"     # violet
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def _rgba(color: str, alpha: float) -> QColor:
    c = QColor(color)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def _rounded(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def paint_mark(painter: QPainter, rect: QRectF, accent=None, *, tile: bool = True) -> None:
    """Draw the NEXUS mark in ``rect``. ``accent`` and ``tile`` are accepted for
    compatibility; the mark keeps its own colours so it is recognisable in every theme."""
    del accent, tile
    size = min(rect.width(), rect.height())
    x0 = rect.center().x() - size / 2
    y0 = rect.center().y() - size / 2
    small = size <= 24

    def pt(u, v):
        return QPointF(x0 + u * size, y0 + v * size)

    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)

    # --- gunmetal tile with a bevelled edge
    outer = QRectF(x0, y0, size, size)
    radius = size * 0.23
    body = QLinearGradient(pt(0.5, 0), pt(0.5, 1))
    body.setColorAt(0.0, QColor("#25303f"))
    body.setColorAt(0.45, QColor("#111824"))
    body.setColorAt(1.0, QColor("#05080d"))
    painter.setBrush(body)
    painter.drawPath(_rounded(outer, radius))
    if not small:
        bevel = QLinearGradient(pt(0.5, 0), pt(0.5, 1))
        bevel.setColorAt(0.0, _rgba("#ffffff", 0.35))
        bevel.setColorAt(0.5, _rgba("#ffffff", 0.05))
        bevel.setColorAt(1.0, _rgba("#000000", 0.4))
        painter.setPen(QPen(bevel, max(1.0, size * 0.012)))
        painter.setBrush(Qt.NoBrush)
        inset = size * 0.006
        painter.drawPath(_rounded(outer.adjusted(inset, inset, -inset, -inset), radius))
        painter.setPen(Qt.NoPen)

    # --- recessed glass panel
    pad = size * (0.07 if small else 0.095)
    panel = outer.adjusted(pad, pad, -pad, -pad)
    panel_radius = radius * 0.72
    glass = QRadialGradient(pt(0.5, 0.42), size * 0.55)
    glass.setColorAt(0.0, QColor("#0f1d30"))
    glass.setColorAt(1.0, QColor("#03060b"))
    painter.setBrush(glass)
    painter.drawPath(_rounded(panel, panel_radius))
    if not small:
        # A faint circuit grid in the glass.
        painter.save()
        painter.setClipPath(_rounded(panel, panel_radius))
        grid = QPen(_rgba(BEAM_START, 0.07), max(0.6, size * 0.003))
        painter.setPen(grid)
        steps = 8
        for i in range(1, steps):
            t = i / steps
            painter.drawLine(pt(0.0, t), pt(1.0, t))
            painter.drawLine(pt(t, 0.0), pt(t, 1.0))
        painter.restore()
        rim = QPen(_rgba(BEAM_START, 0.28), max(0.8, size * 0.006))
        painter.setPen(rim)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(_rounded(panel, panel_radius))
        painter.setPen(Qt.NoPen)

    # --- the N: three beams through four nodes
    left, right = (0.30, 0.70) if small else (0.325, 0.675)
    top, bottom = (0.27, 0.73) if small else (0.30, 0.70)
    nodes = [pt(left, bottom), pt(left, top), pt(right, bottom), pt(right, top)]
    beam = QPainterPath(nodes[0])
    beam.lineTo(nodes[1])
    beam.lineTo(nodes[2])
    beam.lineTo(nodes[3])
    gradient = QLinearGradient(pt(left, top), pt(right, bottom))
    gradient.setColorAt(0.0, QColor(BEAM_START))
    gradient.setColorAt(1.0, QColor(BEAM_END))

    width = size * (0.115 if small else 0.072)
    if not small:
        # Bloom: wide, faint passes under the beam.
        for factor, alpha in ((4.2, 0.07), (2.8, 0.11), (1.8, 0.18)):
            glow = QPen(_rgba(BEAM_START, alpha), width * factor)
            glow.setCapStyle(Qt.RoundCap)
            glow.setJoinStyle(Qt.RoundJoin)
            painter.setPen(glow)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(beam)
    core = QPen(gradient, width)
    core.setCapStyle(Qt.RoundCap)
    core.setJoinStyle(Qt.RoundJoin)
    painter.setPen(core)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(beam)
    if size >= 32:
        hot = QPen(_rgba("#ffffff", 0.75), max(0.8, width * 0.28))
        hot.setCapStyle(Qt.RoundCap)
        hot.setJoinStyle(Qt.RoundJoin)
        painter.setPen(hot)
        painter.drawPath(beam)

    # --- glowing nodes where the beams meet
    if size >= 24:
        painter.setPen(Qt.NoPen)
        for index, node in enumerate(nodes):
            colour = BEAM_START if index < 2 else BEAM_END
            r = width * 0.95
            halo = QRadialGradient(node, r * 1.7)
            halo.setColorAt(0.0, _rgba(colour, 0.45))
            halo.setColorAt(1.0, _rgba(colour, 0.0))
            painter.setBrush(halo)
            painter.drawEllipse(node, r * 1.7, r * 1.7)
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(node, r * 0.42, r * 0.42)

    # --- glass reflection across the top
    if not small:
        painter.save()
        painter.setClipPath(_rounded(panel, panel_radius))
        sheen = QLinearGradient(pt(0.5, 0.1), pt(0.5, 0.5))
        sheen.setColorAt(0.0, _rgba("#ffffff", 0.09))
        sheen.setColorAt(1.0, _rgba("#ffffff", 0.0))
        painter.setBrush(sheen)
        painter.setPen(Qt.NoPen)
        arc = QPainterPath()
        arc.moveTo(panel.topLeft())
        arc.lineTo(panel.topRight())
        arc.lineTo(pt(0.905, 0.36))
        arc.quadTo(pt(0.5, 0.5), pt(0.095, 0.44))
        arc.closeSubpath()
        painter.drawPath(arc)
        painter.restore()

    painter.restore()


def mark_image(size: int, accent=None, *, tile: bool = True) -> QImage:
    """Render at 4x and scale down for clean edges at every size."""
    scale = 4 if size <= 64 else 2
    big = QImage(size * scale, size * scale, QImage.Format_ARGB32_Premultiplied)
    big.fill(Qt.transparent)
    painter = QPainter(big)
    # Small icons use the simplified drawing, so pass the *target* size's style.
    if size <= 24:
        painter.scale(scale, scale)
        paint_mark(painter, QRectF(0, 0, size, size), tile=tile)
    else:
        paint_mark(painter, QRectF(0, 0, size * scale, size * scale), tile=tile)
    painter.end()
    return big.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def app_icon(accent=None) -> QIcon:
    """The window, taskbar and tray icon."""
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(QPixmap.fromImage(mark_image(size)))
    return icon


def write_ico(path: Path, accent=None) -> None:
    """Write a multi-size Windows .ico (PNG-compressed entries, Windows Vista and later)."""
    blobs = []
    for size in ICON_SIZES:
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        mark_image(size).save(buffer, "PNG")
        buffer.close()
        blobs.append((size, bytes(data)))
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = len(header) + 16 * len(blobs)
    entries, payload = b"", b""
    for size, blob in blobs:
        dimension = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(blob), offset + len(payload))
        payload += blob
    Path(path).write_bytes(header + entries + payload)
