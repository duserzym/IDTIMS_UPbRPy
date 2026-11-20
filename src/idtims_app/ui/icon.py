# Copied from UPbRPy Studio: GUI/icon.py (build_workflow_stage_icon) at Studio
# commit f8c561f, on 2026-11-14. Changes: only the stage-icon painter is kept
# (its body is unchanged); the application icon loads the chosen PNG sizes
# named in idtims_app.branding instead of Studio's zircon mark.
"""Workflow stage icons (from Studio) and the app icon (from branding)."""
from __future__ import annotations

from PySide6 import QtCore, QtGui

from idtims_app import branding


def render_app_icon(size: int = 256) -> QtGui.QPixmap:
    """Return the chosen PNG representation at ``size`` physical pixels."""
    return build_app_icon().pixmap(size, size)


def build_app_icon() -> QtGui.QIcon:
    """Load all PNG sizes so Qt selects the native render at 16/32 px."""
    icon = QtGui.QIcon()
    for size, path in branding.ICON_PNGS.items():
        icon.addFile(str(path), QtCore.QSize(size, size))
    return icon


def build_workflow_stage_icon(
    stage: str,
    *,
    state: str = "ready",
    size: int = 28,
    accent: str = "#2468d4",
    muted: str = "#788da6",
    success: str = "#159a76",
) -> QtGui.QIcon:
    """Build a semantic vector-style icon for one reduction stage.

    The small glyphs are painted from primitives rather than loaded from
    raster artwork, so they remain sharp on Retina and high-DPI displays.
    ``state`` may be ``locked``, ``ready``, ``current``, or ``complete``.
    """
    canvas_size = max(16, int(size))
    image = QtGui.QImage(
        canvas_size * 2,
        canvas_size * 2,
        QtGui.QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.setDevicePixelRatio(2.0)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

    color = QtGui.QColor(
        success if state == "complete" else muted if state == "locked" else accent
    )
    background = QtGui.QColor(color)
    background.setAlpha(38 if state != "current" else 64)
    rect = QtCore.QRectF(1.5, 1.5, canvas_size - 3.0, canvas_size - 3.0)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(background)
    painter.drawRoundedRect(rect, canvas_size * 0.28, canvas_size * 0.28)

    pen = QtGui.QPen(color, max(1.25, canvas_size * 0.065))
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)

    left = canvas_size * 0.25
    right = canvas_size * 0.75
    top = canvas_size * 0.25
    bottom = canvas_size * 0.75
    center = QtCore.QPointF(canvas_size * 0.50, canvas_size * 0.50)
    stage_name = str(stage)

    if stage_name == "import":
        painter.drawRoundedRect(
            QtCore.QRectF(left, top + 2, right - left, bottom - top - 1),
            2,
            2,
        )
        painter.drawLine(center.x(), top, center.x(), bottom - 4)
        painter.drawLine(center.x(), bottom - 4, center.x() - 3, bottom - 7)
        painter.drawLine(center.x(), bottom - 4, center.x() + 3, bottom - 7)
    elif stage_name == "selection":
        painter.drawLine(left, top, left, top + 5)
        painter.drawLine(left, top, left + 5, top)
        painter.drawLine(right, top, right - 5, top)
        painter.drawLine(right, top, right, top + 5)
        painter.drawLine(left, bottom, left, bottom - 5)
        painter.drawLine(left, bottom, left + 5, bottom)
        painter.drawLine(right, bottom, right - 5, bottom)
        painter.drawLine(right, bottom, right, bottom - 5)
        painter.drawLine(left + 3, center.y(), right - 3, center.y())
    elif stage_name == "baseline":
        painter.drawLine(left, bottom, right, bottom)
        painter.drawLine(left, bottom, left, top)
        painter.drawLine(left + 2, bottom - 5, right - 2, bottom - 5)
    elif stage_name == "normalization":
        for y, knob in ((top + 2, 0.62), (center.y(), 0.40), (bottom - 2, 0.58)):
            painter.drawLine(left, y, right, y)
            x = canvas_size * knob
            painter.setBrush(color)
            painter.drawEllipse(QtCore.QPointF(x, y), 1.8, 1.8)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    elif stage_name == "concentration":
        path = QtGui.QPainterPath()
        path.moveTo(center.x() - 3, top)
        path.lineTo(center.x() - 3, center.y() - 2)
        path.lineTo(left + 2, bottom)
        path.lineTo(right - 2, bottom)
        path.lineTo(center.x() + 3, center.y() - 2)
        path.lineTo(center.x() + 3, top)
        painter.drawPath(path)
        painter.drawLine(left + 5, bottom - 5, right - 5, bottom - 5)
    elif stage_name == "ratios":
        painter.setBrush(color)
        painter.drawEllipse(QtCore.QPointF(left + 3, top + 3), 2, 2)
        painter.drawEllipse(QtCore.QPointF(right - 3, bottom - 3), 2, 2)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawLine(left + 3, bottom - 1, right - 3, top + 1)
    elif stage_name == "downhole":
        points = [
            QtCore.QPointF(left, top + 2),
            QtCore.QPointF(center.x() - 2, center.y() - 1),
            QtCore.QPointF(right, bottom - 2),
        ]
        painter.drawPolyline(QtGui.QPolygonF(points))
        painter.drawLine(right, bottom - 2, right - 1, bottom - 7)
    elif stage_name == "session":
        painter.drawEllipse(center, (right - left) / 2, (bottom - top) / 2)
        painter.drawLine(center, QtCore.QPointF(center.x(), top + 4))
        painter.drawLine(center, QtCore.QPointF(right - 4, center.y() + 2))
    elif stage_name == "spot_means":
        painter.drawEllipse(center, 7, 7)
        painter.drawEllipse(center, 3, 3)
        painter.setBrush(color)
        painter.drawEllipse(center, 1.4, 1.4)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    elif stage_name == "depth_profile":
        for offset in (0, 4, 8):
            painter.drawLine(
                left + 2,
                top + 2 + offset,
                right - 2,
                top + 2 + offset,
            )
        painter.drawLine(center.x(), top, center.x(), bottom)
        painter.drawLine(center.x(), bottom, center.x() - 3, bottom - 4)
        painter.drawLine(center.x(), bottom, center.x() + 3, bottom - 4)
    elif stage_name in {"finalize", "export"}:
        painter.drawEllipse(center, 8, 8)
        painter.drawLine(left + 5, center.y(), center.x() - 1, bottom - 5)
        painter.drawLine(center.x() - 1, bottom - 5, right - 4, top + 5)
    else:
        painter.drawEllipse(center, 7, 7)

    if state == "complete":
        painter.setPen(
            QtGui.QPen(QtGui.QColor(success), max(1.2, canvas_size * 0.06))
        )
        painter.drawEllipse(
            QtCore.QPointF(canvas_size * 0.78, canvas_size * 0.22),
            2.3,
            2.3,
        )
    painter.end()
    return QtGui.QIcon(QtGui.QPixmap.fromImage(image))
