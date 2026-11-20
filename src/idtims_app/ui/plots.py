# Copied from UPbRPy Studio: GUI/widgets.py at Studio commit f8c561f, on
# 2026-11-14: _RoundedCanvas, RoundedPlotWidget, RoundedGraphicsLayoutWidget,
# RoundedLegendItem, _rounded_legend, AxisZoomViewBox, _ConcordiaEllipse,
# _ConcordiaEllipseBatch, _make_diag_axis and
# ConcordiaReviewWidget.ellipse_coordinates_batch. Changes: extracted into
# their own module; imports point at idtims_app.ui.theme;
# ellipse_coordinates_batch is a module function instead of a static method
# (its body is unchanged). The class and function bodies are unchanged.
"""Studio's rounded pyqtgraph canvases, axis-constrained zoom and batched ellipses."""
from __future__ import annotations

import os
import weakref

import numpy as np

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

from PySide6 import QtCore, QtGui  # noqa: E402

import pyqtgraph as pg  # noqa: E402

from idtims_app.ui.theme import ThemeSpec, active_theme, theme_color  # noqa: E402


class _RoundedCanvas:
    """Clip only the outer canvas corners; plot items retain normal rendering."""

    def resizeEvent(self, event):
        super().resizeEvent(event)
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(self.rect()), 11, 11)
        self.setMask(QtGui.QRegion(path.toFillPolygon().toPolygon()))


class RoundedPlotWidget(_RoundedCanvas, pg.PlotWidget):
    """An opaque scientific plot with rounded outer corners."""


class RoundedGraphicsLayoutWidget(_RoundedCanvas, pg.GraphicsLayoutWidget):
    """A rounded canvas for multi-panel scientific plots."""


class RoundedLegendItem(pg.LegendItem):
    """Paint a compact rounded legend without a graphics effect."""

    def paint(self, painter, *args):
        if not self.items:
            return
        theme = active_theme()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        fill = theme_color(theme.glass_strong)
        painter.setBrush(fill)
        painter.setPen(QtGui.QPen(theme_color(theme.input_border), 1))
        painter.drawRoundedRect(self.boundingRect().adjusted(0.5, 0.5, -0.5, -0.5), 9, 9)


def _rounded_legend(plot, **options):
    legend = RoundedLegendItem(**options)
    legend.setParentItem(plot.vb)
    plot.legend = legend
    return legend


class AxisZoomViewBox(pg.ViewBox):
    """Constrain zoom axes while allowing panning in both directions."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_zoom_axes("xy")

    def set_zoom_axes(self, mode: str) -> None:
        """Choose xy, x, or y for zooming without restricting panning."""
        self._zoom_axes = mode if mode in {"xy", "x", "y"} else "xy"
        self.setMouseEnabled(x=True, y=True)

    def zoom_axes(self) -> str:
        """Return the selected zoom axes."""
        return self._zoom_axes

    def _zoom_mask(self):
        return [self.state["mouseEnabled"][0] and self._zoom_axes != "y",
                self.state["mouseEnabled"][1] and self._zoom_axes != "x"]

    def wheelEvent(self, event, axis=None):
        """Zoom the chosen axes, or the axis item receiving the wheel."""
        mask = ([enabled and index == axis
                 for index, enabled in enumerate(self.state["mouseEnabled"])]
                if axis in (0, 1) else self._zoom_mask())
        if not any(mask):
            event.ignore()
            return
        scale = 1.02 ** (event.delta() * self.state["wheelScaleFactor"])
        factors = [scale if enabled else None for enabled in mask]
        transform = pg.functions.invertQTransform(self.childGroup.transform())
        center = pg.Point(transform.map(event.pos()))
        self._resetTarget()
        self.scaleBy(factors, center)
        event.accept()
        self.sigRangeChangedManually.emit(mask)

    def mouseDragEvent(self, event, axis=None):
        """Pan with left/middle drag and constrain right-drag zoom axes."""
        button = event.button()
        if (button == QtCore.Qt.MouseButton.LeftButton
                and self.state["mouseMode"] == self.RectMode and axis is None):
            # Keep pyqtgraph's rubber band and view history; showAxRect below
            # applies the zoom-axis choice when the rectangle is finished.
            super().mouseDragEvent(event, axis=axis)
            return

        event.accept()
        transform = pg.functions.invertQTransform(self.childGroup.transform())
        if button in (QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.MiddleButton):
            mask = [enabled and (axis is None or index == axis)
                    for index, enabled in enumerate(self.state["mouseEnabled"])]
            delta = (event.lastPos() - event.pos()) * np.array(mask, dtype=float)
            delta = transform.map(delta) - transform.map(pg.Point(0, 0))
            self._resetTarget()
            if any(mask):
                self.translateBy(x=delta.x() if mask[0] else None,
                                 y=delta.y() if mask[1] else None)
            self.sigRangeChangedManually.emit(mask)
        elif button == QtCore.Qt.MouseButton.RightButton:
            mask = [enabled and (axis is None or index == axis)
                    for index, enabled in enumerate(self._zoom_mask())]
            if self.state["aspectLocked"] is not False:
                mask[0] = False
            delta = event.screenPos() - event.lastScreenPos()
            factors = (1 + np.array(mask, dtype=float) * 0.02) ** np.array([-delta.x(), delta.y()])
            center = pg.Point(transform.map(event.buttonDownPos(button)))
            self._resetTarget()
            self.scaleBy(x=factors[0] if mask[0] else None,
                         y=factors[1] if mask[1] else None, center=center)
            self.sigRangeChangedManually.emit(mask)

    def showAxRect(self, rect, **kwargs):
        """Apply rectangle zoom only to the selected zoom axes."""
        rect = rect.normalized()
        mask = self._zoom_mask()
        limits = {}
        if mask[0]:
            limits["xRange"] = (rect.left(), rect.right())
        if mask[1]:
            limits["yRange"] = (rect.top(), rect.bottom())
        if self._zoom_axes != "xy":
            kwargs.setdefault("padding", 0)
        self.setRange(**limits, **kwargs)
        self.sigRangeChangedManually.emit(mask)


class _ConcordiaEllipse:
    """A per-row ellipse handle; the canvas owns the single graphics item."""

    def __init__(self, owner, x, y, pen, outline_color=None):
        self.owner = weakref.ref(owner)
        self.x, self.y = x, y
        self.opts = {"pen": pen}
        self.outline_color = outline_color
        self._style_key = None
        self.visible = True

    def getData(self):
        return self.x, self.y

    def setPen(self, pen):
        if pen != self.opts["pen"]:
            self.opts["pen"] = pen
            self._mark_dirty()

    def setVisible(self, visible):
        if self.visible != visible:
            self.visible = visible
            self._mark_dirty()

    def style_key(self):
        """Cache the effective outline style across visibility-only redraws."""
        if self._style_key is None:
            pen = self.opts["pen"]
            color = pen.color()
            if self.outline_color is not None:
                alpha = color.alpha()
                color = QtGui.QColor(self.outline_color)
                color.setAlpha(alpha)
            self._style_key = color.rgba(), pen.widthF(), pen.style()
        return self._style_key

    def _mark_dirty(self):
        self._style_key = None
        owner = self.owner()
        if owner is not None:
            owner.dirty = True

    def isVisible(self):
        return self.visible


class _ConcordiaEllipseBatch(pg.GraphicsObject):
    """Cache ellipse paths by pen, with no per-ellipse scene objects."""

    def __init__(self):
        super().__init__()
        self.handles = []
        self.paths = []
        self.dirty = True
        self._bounds = QtCore.QRectF()
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)

    def rebuild(self):
        if not self.dirty:
            return
        groups = {}
        for handle in self.handles:
            if not handle.visible:
                continue
            groups.setdefault(handle.style_key(), []).append(handle)
        paths = []
        bounds = QtCore.QRectF()
        for (rgba, width, style), handles in groups.items():
            # Finite connections close each ellipse and skip its NaN separator.
            x = np.full((len(handles), len(handles[0].x) + 1), np.nan)
            y = np.full_like(x, np.nan)
            x[:, :-1] = [handle.x for handle in handles]
            y[:, :-1] = [handle.y for handle in handles]
            path = pg.arrayToQPath(x.ravel(), y.ravel(), connect="finite")
            pen = pg.mkPen(QtGui.QColor.fromRgba(rgba), width=width, style=style)
            paths.append((pen, path))
            bounds = bounds.united(path.boundingRect())
        self.prepareGeometryChange()
        self._bounds = bounds
        self.paths = paths
        self.dirty = False
        self.update()

    def boundingRect(self):
        return self._bounds

    def paint(self, painter, *_args):
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        for pen, path in self.paths:
            painter.setPen(pen)
            painter.drawPath(path)



def _make_diag_axis(plot_item: pg.PlotItem, theme: ThemeSpec) -> None:
    """Apply consistent axis styling to a diagnostic sub-plot."""
    tick_font = QtGui.QFont()
    tick_font.setPointSizeF(9.0)
    for axis_name in ("left", "bottom"):
        ax = plot_item.getAxis(axis_name)
        ax.setPen(theme.axis_line)
        ax.setTextPen(theme.axis_text)
        ax.setStyle(tickFont=tick_font, tickTextOffset=4)
    plot_item.showGrid(x=True, y=True, alpha=theme.grid_alpha)
    plot_item.setContentsMargins(4, 4, 4, 4)


def ellipse_coordinates_batch(x, y, x_2e, y_2e, rho, *, points=48) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return stacked two-SE ellipses and a mask of valid input rows.

    Invalid rows have NaN vertices. The angle grid and covariance
    eigendecomposition match :meth:`ellipse_coordinates`.
    """
    x, y, x_2e, y_2e, rho = np.broadcast_arrays(
        *[np.asarray(value, dtype=float) for value in (x, y, x_2e, y_2e, rho)])
    x, y, x_2e, y_2e, rho = [a.reshape(-1) for a in (x, y, x_2e, y_2e, rho)]
    valid = (np.isfinite(x) & np.isfinite(y) & np.isfinite(x_2e) & np.isfinite(y_2e)
             & (x_2e > 0) & (y_2e > 0))
    count = max(4, int(np.ceil((points - 1) / 4)) * 4)
    ex = np.full((len(x), count + 1), np.nan)
    ey = np.full_like(ex, np.nan)
    sx, sy = x_2e[valid] / 2, y_2e[valid] / 2
    correlation = np.clip(np.where(np.isnan(rho[valid]), 0., rho[valid]), -.999, .999)
    covariance = np.empty((len(sx), 2, 2))
    covariance[:, 0, 0], covariance[:, 1, 1] = sx * sx, sy * sy
    covariance[:, 0, 1] = covariance[:, 1, 0] = correlation * sx * sy
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    axes = np.zeros_like(covariance)
    axes[:, 0, 0], axes[:, 1, 1] = (2 * np.sqrt(np.maximum(eigenvalues, 0.))).T
    angle = np.linspace(0., 2. * np.pi, count + 1)
    circle = np.vstack((np.cos(angle), np.sin(angle)))
    offsets = eigenvectors @ axes @ circle
    ex[valid], ey[valid] = x[valid, None] + offsets[:, 0], y[valid, None] + offsets[:, 1]
    return ex, ey, valid



__all__ = ["AxisZoomViewBox", "RoundedGraphicsLayoutWidget", "RoundedLegendItem",
           "RoundedPlotWidget", "ellipse_coordinates_batch"]
