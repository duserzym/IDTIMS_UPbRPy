# Copied from UPbRPy Studio: GUI/widgets.py (class _WorkflowRailDelegate) at
# Studio commit f8c561f, on 2026-11-14. Changes: extracted into its own module;
# imports point at idtims_app.ui.theme. The delegate painting code is unchanged.
"""Studio-style workflow rows and a visible, resizable rail divider."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from idtims_app.ui.theme import active_theme, theme_color


class _RailHandle(QtWidgets.QSplitterHandle):
    """Use Studio's quiet central grip and the app's existing theme tokens."""

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.splitter().resetRequested.emit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        theme = active_theme()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        color = theme.accent if self.isEnabled() and self.underMouse() else theme.input_border
        painter.setPen(QtGui.QPen(theme_color(color), 1,
                                 QtCore.Qt.PenStyle.SolidLine, QtCore.Qt.PenCapStyle.RoundCap))
        centre = QtCore.QPointF(self.rect().center())
        extent = min(28., max(0., (self.height() - 8) / 2))
        painter.drawLine(centre + QtCore.QPointF(0, -extent), centre + QtCore.QPointF(0, extent))


class WorkflowRailSplitter(QtWidgets.QSplitter):
    """A native splitter with a 10 px hit area and a rail-width reset gesture."""

    resetRequested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(QtCore.Qt.Orientation.Horizontal, parent)

    def createHandle(self):
        return _RailHandle(self.orientation(), self)


class _WorkflowRailDelegate(QtWidgets.QStyledItemDelegate):
    """Keep stage icons and number badges readable in the compact rail."""

    def paint(self, painter, option, index):
        if not self.parent().property("compactRail"):
            return super().paint(painter, option, index)
        theme = active_theme()
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(1, 1, -1, -1)
        selected = bool(option.state & QtWidgets.QStyle.StateFlag.State_Selected)
        if selected or option.state & QtWidgets.QStyle.StateFlag.State_MouseOver:
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(theme_color(theme.accent_soft if selected else theme.row_hover))
            painter.drawRoundedRect(QtCore.QRectF(rect), 9, 9)
        icon = index.data(QtCore.Qt.ItemDataRole.DecorationRole)
        icon.paint(painter, QtCore.QRect(rect.left()+5, rect.center().y()-10, 20, 20))
        font = option.font
        font.setPixelSize(9)
        painter.setFont(font)
        painter.setPen(QtGui.QColor(theme.accent if selected else theme.muted))
        painter.drawText(rect.adjusted(27, 0, -2, 0), QtCore.Qt.AlignmentFlag.AlignCenter, str(index.row()+1))
        painter.restore()
