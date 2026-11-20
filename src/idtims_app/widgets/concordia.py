"""Concordia panel of the Review step: Wetherill or Tera-Wasserburg with 2σ ellipses.

The canvas follows Studio's concordia review (rounded pyqtgraph canvas,
axis-constrained zoom, ellipses batched into one graphics item, muted curve
with age labels, a hover card). The numbers come from `idtims_app.review`
(`ratio_covariance`, `concordia_curve`); this module only draws them.

Interaction follows Studio: a click selects the fraction under the pointer
(smallest ellipse first) and E switches the selected fraction on or off
(Studio's exclude toggle). Ctrl-click (Cmd-click on macOS) switches the
fraction under the pointer on or off directly. Double-click resets the view.
Switched-off fractions are drawn hollow with a grey dashed outline;
fractions reduced in diagnostic mode carry an amber outline.
"""
from __future__ import annotations

import math
import weakref
from html import escape

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from idtims_app import review
from idtims_app.ui.plots import (AxisZoomViewBox, RoundedGraphicsLayoutWidget, _ConcordiaEllipse,
                                 _ConcordiaEllipseBatch, _make_diag_axis,
                                 ellipse_coordinates_batch)
from idtims_app.ui.theme import active_theme, theme_color

DIAGNOSTIC_COLOR = "#c98a00"
AXIS_LABELS = {review.WETHERILL: ("207Pb/235U", "206Pb/238U"),
               review.TERA_WASSERBURG: ("238U/206Pb", "207Pb/206Pb")}
_STEPS = (1, 2, 2.5, 5)


def nice_step(span, target=6):
    """A 1-2-2.5-5 step giving about `target` labels over `span` (Ma)."""
    if not span > 0:
        return 1.0
    raw = span / target
    power = 10 ** math.floor(math.log10(raw))
    for factor in _STEPS + (10,):
        if factor * power >= raw:
            return factor * power
    return 10 * power


def age_label(age, step):
    decimals = max(0, -int(math.floor(math.log10(step))))
    if not float(step * 10 ** decimals).is_integer():
        decimals += 1
    return f"{age:.{decimals}f} Ma"


def _path_overlap(path, rect):
    """Area of an ellipse polygon inside a scene-space label rectangle (px²)."""
    if not path.intersects(rect):
        return 0.0
    box = QtGui.QPainterPath()
    box.addRect(rect)
    polygon = list(path.intersected(box).toFillPolygon())
    return abs(sum(a.x() * b.y() - b.x() * a.y()
                   for a, b in zip(polygon, polygon[1:] + polygon[:1]))) / 2


class _FilledEllipseBatch(_ConcordiaEllipseBatch):
    """Studio's ellipse batch, with a light fill under solid (switched-on) outlines."""

    def paint(self, painter, *args):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        for pen, path in self.paths:
            if pen.style() == QtCore.Qt.PenStyle.SolidLine:
                fill = QtGui.QColor(pen.color())
                fill.setAlpha(38)
                painter.setBrush(fill)
                painter.drawPath(path)
        super().paint(painter, *args)


class _ReviewViewBox(AxisZoomViewBox):
    """Route clicks to the concordia canvas (select, toggle, reset)."""

    def __init__(self, canvas):
        super().__init__()
        self.canvas = weakref.proxy(canvas)

    def mouseClickEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.canvas.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
            if event.double():
                self.canvas.restore_default_view()
            else:
                self.canvas.click_at(event.scenePos(), event.modifiers())
            event.accept()
            return
        super().mouseClickEvent(event)


class ConcordiaCanvas(RoundedGraphicsLayoutWidget):
    """The plot: curve, labels, ellipses, centres, hover card and selection ring."""

    selected = QtCore.Signal(str)
    toggled = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(260, 200)
        self.diagram = review.WETHERILL
        self.th = False
        self.rows = []
        self.excluded = set()
        self.selected_id = None
        self.points = []          # (fid, x, y, row)
        self.geometry = {}        # fid -> (x, y, sx, sy, rho)
        self.polygons = {}        # fid -> (ex, ey)
        self.constants = None
        self._default_range = [[0, 1], [0, 1]]
        self._label_items = []
        self._hover_id = None
        self.plot = self.addPlot(0, 0, viewBox=_ReviewViewBox(self))
        for menu in (self.plot.ctrlMenu, self.plot.vb.menu):
            menu.setParent(self, menu.windowFlags())
        self.plot.hideButtons()
        # Keep plot geometry stable when tick precision changes during zoom.
        self.plot.getAxis("left").setWidth(76)
        self.curve = self.plot.plot([], [])
        self.batch = _FilledEllipseBatch()
        self.plot.addItem(self.batch, ignoreBounds=True)
        self.scatter = pg.ScatterPlotItem(symbol="o", size=7)
        self.scatter.setZValue(10)
        # The view box handles every click (select, toggle) so ellipses and centres agree.
        self.scatter.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
        self.plot.addItem(self.scatter)
        self.highlight = QtWidgets.QGraphicsPathItem()
        self.highlight.setZValue(25)
        self.highlight.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
        self.plot.addItem(self.highlight, ignoreBounds=True)
        self.hover_text = pg.TextItem(anchor=(0, 0))
        self.hover_text.setZValue(30)
        self.hover_text.setParentItem(self.plot.vb)
        self.hover_text.hide()
        self.empty_text = pg.TextItem(anchor=(0.5, 0.5))
        self.empty_text.setParentItem(self.plot.vb)
        self.empty_text.hide()
        self._label_timer = QtCore.QTimer(self)
        self._label_timer.setSingleShot(True)
        self._label_timer.timeout.connect(self._update_curve_and_labels)
        self.plot.vb.sigRangeChanged.connect(self._schedule_labels)
        self.plot.vb.sigResized.connect(self._schedule_labels)
        self.scene().sigMouseMoved.connect(self._on_mouse_moved)
        self.apply_theme()

    # -- data ------------------------------------------------------------------
    def set_data(self, rows, diagram, th, excluded, selected_id=None, reset_view=True):
        """Draw reduced ReviewRows on `diagram` (Th-corrected ratios when `th`)."""
        self.rows = [r for r in rows if r.reduced]
        self.diagram = diagram
        self.th = bool(th)
        self.excluded = set(excluded)
        self.selected_id = selected_id
        self.geometry, self.points = {}, []
        for row in self.rows:
            values = review.ratio_covariance(row.grain, diagram, self.th)
            if values is not None:
                self.geometry[row.fraction_id] = values
                self.points.append((row.fraction_id, values[0], values[1], row))
        self.constants = review.decay_constants([r.grain for r in self.rows]) if self.rows else None
        ids = list(self.geometry)
        if ids:
            x, y, sx, sy, rho = (np.array([self.geometry[f][i] for f in ids]) for i in range(5))
            ex, ey, valid = ellipse_coordinates_batch(x, y, 2 * sx, 2 * sy, rho)
            self.polygons = {f: (ex[i], ey[i]) for i, f in enumerate(ids) if valid[i]}
        else:
            self.polygons = {}
        x_label, y_label = AXIS_LABELS[diagram]
        theme = active_theme()
        self.plot.setLabel("bottom", x_label, color=theme.axis_text, size="12px")
        self.plot.setLabel("left", y_label, color=theme.axis_text, size="12px")
        self._default_range = self._initial_range()
        self._restyle()
        if reset_view:
            self.restore_default_view()
        self.empty_text.setVisible(not self.points)
        if not self.points:
            self.empty_text.setText("No reduced fraction to plot.", color=theme.muted)
            self.empty_text.setPos(self.plot.vb.boundingRect().center())
        self._schedule_labels()

    def set_excluded(self, excluded):
        self.excluded = set(excluded)
        self._restyle()

    def set_selected(self, fid):
        self.selected_id = fid
        self._update_highlight()

    def _initial_range(self):
        """Data ±2σ boxes plus the nearest concordia point, with a 12 % margin."""
        if not self.points:
            return [[0, 1], [0, 1]]
        boxes = []
        for fid, x, y, _row in self.points:
            if fid in self.polygons:
                ex, ey = self.polygons[fid]
                boxes.append((np.nanmin(ex), np.nanmax(ex), np.nanmin(ey), np.nanmax(ey)))
            else:
                boxes.append((x, x, y, y))
        boxes = np.array(boxes, dtype=float)
        x_low, x_high = boxes[:, 0].min(), boxes[:, 1].max()
        y_low, y_high = boxes[:, 2].min(), boxes[:, 3].max()
        cx, cy = np.mean(boxes[:, :2]), np.mean(boxes[:, 2:])
        x_scale = max(x_high - x_low, abs(cx) * 0.01, 1e-12)
        y_scale = max(y_high - y_low, abs(cy) * 0.01, 1e-12)
        ages = self._ages_near_data()
        if ages is not None:
            curve_x, curve_y = review.concordia_curve(self.diagram, *self.constants, ages)
            distance = ((curve_x - cx) / x_scale) ** 2 + ((curve_y - cy) / y_scale) ** 2
            nearest = int(np.nanargmin(distance))
            x_low, x_high = min(x_low, curve_x[nearest]), max(x_high, curve_x[nearest])
            y_low, y_high = min(y_low, curve_y[nearest]), max(y_high, curve_y[nearest])
        x_pad = max((x_high - x_low) * 0.12, abs(cx) * 1e-4, 1e-12)
        y_pad = max((y_high - y_low) * 0.12, abs(cy) * 1e-4, 1e-12)
        return [[x_low - x_pad, x_high + x_pad], [y_low - y_pad, y_high + y_pad]]

    def _ages_near_data(self):
        if self.constants is None:
            return None
        dates = [r.grain.t68 for r in self.rows if review.finite(r.grain.t68)]
        dates += [r.grain.t76 for r in self.rows if review.finite(r.grain.t76)]
        if not dates:
            return None
        low, high = min(dates), max(dates)
        span = max(high - low, 0.02 * max(high, 1.0))
        return np.linspace(max(0.001, low - 3 * span), high + 3 * span, 4000)

    def restore_default_view(self):
        self.plot.setRange(xRange=self._default_range[0], yRange=self._default_range[1],
                           padding=0)

    # -- drawing ---------------------------------------------------------------
    def apply_theme(self):
        theme = active_theme()
        self.setBackground(theme.plot_background)
        _make_diag_axis(self.plot, theme)
        for name in ("left", "bottom"):
            self.plot.getAxis(name).enableAutoSIPrefix(False)
        background = theme_color(theme.surface)
        background.setAlpha(245)
        self.hover_text.fill = pg.mkBrush(background)
        self.hover_text.border = pg.mkPen(theme_color(theme.input_border))
        self.curve.setPen(pg.mkPen(theme.muted, width=1.4))
        if self.rows:
            self.set_data(self.rows, self.diagram, self.th, self.excluded, self.selected_id,
                          reset_view=False)

    def _restyle(self):
        theme = active_theme()
        handles, brushes, pens = [], [], []
        hollow = pg.mkBrush(None)
        accent = QtGui.QColor(theme.accent)
        for fid, _x, _y, row in self.points:
            off = fid in self.excluded
            color = QtGui.QColor(theme.muted if off else
                                 DIAGNOSTIC_COLOR if row.diagnostic else theme.accent)
            line = QtGui.QColor(color)
            line.setAlpha(200 if not off else 170)
            style = QtCore.Qt.PenStyle.DashLine if off else QtCore.Qt.PenStyle.SolidLine
            width = 1.6 if row.diagnostic else 1.1
            pen = pg.mkPen(line, width=width, style=style)
            if fid in self.polygons:
                ex, ey = self.polygons[fid]
                handles.append(_ConcordiaEllipse(self.batch, ex, ey, pen))
            brushes.append(hollow if off else pg.mkBrush(accent))
            pens.append(pg.mkPen(theme.muted, width=1.0) if off else
                        pg.mkPen(DIAGNOSTIC_COLOR if row.diagnostic else theme.axis_text,
                                 width=1.4 if row.diagnostic else 0.7))
        self.batch.handles = handles
        self.batch.dirty = True
        self.batch.rebuild()
        if self.points:
            self.scatter.setData(x=[p[1] for p in self.points], y=[p[2] for p in self.points],
                                 brush=brushes, pen=pens, size=7)
        else:
            self.scatter.setData([], [])
        self._update_highlight()
        if self._hover_id is not None:
            self._show_hover(self._hover_id)

    def _update_highlight(self):
        path = QtGui.QPainterPath()
        if self.selected_id in self.polygons:
            ex, ey = self.polygons[self.selected_id]
            path.addPolygon(QtGui.QPolygonF([QtCore.QPointF(a, b) for a, b in zip(ex, ey)]))
            path.closeSubpath()
        elif self.selected_id in self.geometry:
            x, y = self.geometry[self.selected_id][:2]
            path.addEllipse(QtCore.QPointF(x, y), 0, 0)
        pen = pg.mkPen(active_theme().accent, width=2.6)
        pen.setCosmetic(True)
        self.highlight.setPen(pen)
        self.highlight.setBrush(QtGui.QBrush(QtCore.Qt.BrushStyle.NoBrush))
        self.highlight.setPath(path)

    def _schedule_labels(self, *_args):
        if not self._label_timer.isActive():
            self._label_timer.start(0)

    def _visible_ages(self):
        """Age interval of the concordia inside the view, or None."""
        if self.constants is None:
            return None
        # Both coordinates are monotone with age in either diagram. Invert the
        # four view edges rather than sampling: a narrow zoom can fall entirely
        # between samples (the old sampling was ~0.5 Ma apart near 507 Ma).
        lo, hi = 0.001, 4600.0
        ends = review.concordia_curve(self.diagram, *self.constants, [lo, hi])
        for axis, (low, high) in enumerate(self.plot.vb.viewRange()):
            increasing = ends[axis][1] > ends[axis][0]
            axis_low, axis_high = sorted(ends[axis])
            if high <= axis_low or low >= axis_high:
                return None
            limits = []
            for edge in (low, high):
                left, right = 0.001, 4600.0
                for _ in range(42):
                    mid = (left + right) / 2
                    value = review.concordia_curve(self.diagram, *self.constants, [mid])[axis][0]
                    if (value < edge) == increasing:
                        left = mid
                    else:
                        right = mid
                limits.append((left + right) / 2)
            lo, hi = max(lo, min(limits)), min(hi, max(limits))
        return (lo, hi) if hi > lo else None

    def _update_curve_and_labels(self):
        theme = active_theme()
        for item in self._label_items:
            self.plot.removeItem(item)
        self._label_items = []
        interval = self._visible_ages()
        if interval is None:
            self.curve.setData([], [])
            return
        lo, hi = interval
        margin = max((hi - lo) * 0.2, 0.001)
        ages = np.linspace(max(0.001, lo - margin), hi + margin, 1200)
        self.curve.setData(*review.concordia_curve(self.diagram, *self.constants, ages))
        step = nice_step(hi - lo, target=5)
        first = math.ceil(lo / step) * step
        ticks = np.arange(first, hi, step)
        if not len(ticks):
            return
        # Reserve the ticks bracketing the plotted 206/238 dates before placing
        # optional labels. If a bracket is off screen, use the nearest visible
        # tick. Keep two distinct labels even for a single point at a tick age.
        date_name = "t68_Th_corr" if self.th else "t68"
        dates = [getattr(p[3].grain, date_name) for p in self.points
                 if review.finite(getattr(p[3].grain, date_name))]
        required = {0, len(ticks) - 1}
        if dates:
            young = int(np.clip(np.searchsorted(ticks, min(dates), side="right") - 1,
                                0, len(ticks) - 1))
            old = int(np.clip(np.searchsorted(ticks, max(dates)), 0, len(ticks) - 1))
            required = {young, old}
            if young == old and len(ticks) > 1:
                required.add(young - 1 if young else 1)
        font = QtGui.QFont()
        font.setPointSizeF(9.5)
        placed = []
        vb = self.plot.vb
        bounds = vb.sceneBoundingRect().adjusted(4, 4, -4, -4)
        ellipses = []
        for ex, ey in self.polygons.values():
            path = QtGui.QPainterPath()
            path.addPolygon(QtGui.QPolygonF([
                vb.mapViewToScene(QtCore.QPointF(float(x), float(y))) for x, y in zip(ex, ey)]))
            path.closeSubpath()
            ellipses.append(path)
        order = sorted(required) + [i for i in range(len(ticks)) if i not in required]
        for index in order[:24]:
            age = ticks[index]
            px, py = review.concordia_curve(self.diagram, *self.constants, [age])
            px, py = float(px[0]), float(py[0])
            scene = vb.mapViewToScene(QtCore.QPointF(px, py))
            # Compute the normal in pixels, so anisotropic axes do not distort
            # the perpendicular offset or its distance from the curve.
            tx, ty = review.concordia_curve(self.diagram, *self.constants,
                                            [age - step * 0.01, age + step * 0.01])
            tangent = (vb.mapViewToScene(QtCore.QPointF(tx[1], ty[1])) -
                       vb.mapViewToScene(QtCore.QPointF(tx[0], ty[0])))
            length = math.hypot(tangent.x(), tangent.y())
            normal = QtCore.QPointF(-tangent.y() / length, tangent.x() / length)
            label = pg.TextItem(age_label(age, step), color=theme.muted, anchor=(0.5, 0.5))
            label.setFont(font)
            label.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
            self.plot.addItem(label, ignoreBounds=True)
            label.setPos(vb.mapSceneToView(scene))
            size = label.sceneBoundingRect().size()
            if size.width() > bounds.width() or size.height() > bounds.height():
                self.plot.removeItem(label)
                continue
            support = (abs(normal.x()) * size.width() + abs(normal.y()) * size.height()) / 2
            candidates = {1: [], -1: []}
            for gap in (6, 16, 30, 50, 80):
                for side in (1, -1):
                    center = scene + normal * (side * (support + gap))
                    center.setX(max(bounds.left() + size.width() / 2,
                                    min(center.x(), bounds.right() - size.width() / 2)))
                    center.setY(max(bounds.top() + size.height() / 2,
                                    min(center.y(), bounds.bottom() - size.height() / 2)))
                    rect = QtCore.QRectF(center.x() - size.width() / 2,
                                         center.y() - size.height() / 2,
                                         size.width(), size.height())
                    padded = rect.adjusted(-2, -2, 2, 2)
                    overlap = sum(_path_overlap(path, padded) for path in ellipses)
                    label_overlap = sum(rect.intersected(other).width() *
                                        rect.intersected(other).height()
                                        for other in placed if rect.intersects(other))
                    candidates[side].append((label_overlap, overlap, center, rect))
            # Prefer the side with less ellipse overlap, trying both sides at
            # each increasing distance. Mandatory labels use the least crowded
            # candidate when every position intersects an ellipse.
            sides = sorted(candidates, key=lambda s: sum(c[1] for c in candidates[s]))
            ranked = [candidates[s][i] for i in range(5) for s in sides]
            choice = next((c for c in ranked if c[0] == 0 and c[1] == 0), None)
            if choice is None and index in required:
                choice = min(ranked, key=lambda c: (c[0], c[1]))
            if choice is None:
                self.plot.removeItem(label)
                continue
            _label_overlap, _ellipse_overlap, center, rect = choice
            label.setPos(vb.mapSceneToView(center))
            label.setZValue(5)
            placed.append(rect.adjusted(-4, -2, 4, 2))
            self._label_items.append(label)
            # Stop the leader at the label edge instead of drawing through text.
            delta = scene - center
            fraction = min(size.width() / (2 * abs(delta.x())) if delta.x() else math.inf,
                           size.height() / (2 * abs(delta.y())) if delta.y() else math.inf)
            end = vb.mapSceneToView(center + delta * min(fraction, 1.0))
            leader = pg.PlotCurveItem([px, end.x()], [py, end.y()],
                                      pen=pg.mkPen(theme.muted, width=1))
            leader.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
            self.plot.addItem(leader, ignoreBounds=True)
            self._label_items.append(leader)

    # -- hit testing, hover, clicks --------------------------------------------
    def fractions_at(self, scene_pos):
        """Fractions under a scene position: a centre within 10 px first, then ellipses
        that contain the point, smallest first."""
        vb = self.plot.vb
        if not vb.sceneBoundingRect().contains(scene_pos) or not self.points:
            return []
        pos = vb.mapSceneToView(scene_pos)
        point = QtCore.QPointF(pos.x(), pos.y())
        hits = []
        for fid, (ex, ey) in self.polygons.items():
            polygon = QtGui.QPolygonF([QtCore.QPointF(a, b) for a, b in zip(ex, ey)])
            if polygon.containsPoint(point, QtCore.Qt.FillRule.OddEvenFill):
                area = 0.5 * abs(np.dot(ex, np.roll(ey, 1)) - np.dot(ey, np.roll(ex, 1)))
                hits.append((area, fid))
        ordered = [fid for _area, fid in sorted(hits)]
        nearest = self.nearest_point(scene_pos)
        if nearest is not None:
            if nearest in ordered:
                ordered.remove(nearest)
            ordered.insert(0, nearest)
        return ordered

    def nearest_point(self, scene_pos, radius=10):
        vb = self.plot.vb
        if not self.points:
            return None
        scale = np.abs(vb.viewPixelSize())
        if not np.all(np.isfinite(scale)) or np.any(scale <= 0):
            return None
        pos = vb.mapSceneToView(scene_pos)
        xy = np.array([(p[1], p[2]) for p in self.points])
        delta = (xy - [pos.x(), pos.y()]) / scale
        distance = np.einsum("ij,ij->i", delta, delta)
        index = int(np.argmin(distance))
        return self.points[index][0] if distance[index] <= radius * radius else None

    def scene_position(self, fid):
        """Scene coordinates of a fraction's centre (tests)."""
        x, y = self.geometry[fid][:2]
        return self.plot.vb.mapViewToScene(QtCore.QPointF(x, y))

    def click_at(self, scene_pos, modifiers):
        hits = self.fractions_at(scene_pos)
        if not hits:
            return
        fid = hits[0]
        if modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.toggled.emit(fid)
        else:
            self.selected.emit(fid)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key.Key_E and self.selected_id in self.geometry:
            self.toggled.emit(self.selected_id)
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_mouse_moved(self, scene_pos):
        hits = self.fractions_at(scene_pos)
        self._show_hover(hits[0] if hits else None)

    def hover_html(self, fid):
        row = next((p[3] for p in self.points if p[0] == fid), None)
        if row is None:
            return ""
        g = row.grain
        th = self.th
        lines = [f"<b>{escape(fid)}</b>" + (" (switched off)" if fid in self.excluded else "")]

        def date(label, value, sigma):
            if review.finite(value) and review.finite(sigma):
                lines.append(f"{label}: {value:.3f} ± {2 * sigma:.3f} Ma")

        if th:
            date("206Pb/238U (Th)", g.t68_Th_corr, g.t68_Th_corr_std)
        date("206Pb/238U", g.t68, g.t68_std)
        date("207Pb/235U", g.t75, g.t75_std)
        if th:
            date("207Pb/206Pb (Th)", g.t76_Th_corr, g.t76_Th_corr_std)
        date("207Pb/206Pb", g.t76, g.t76_std)
        if row.diagnostic:
            lines.append("Diagnostic substitution: uncertainties not certified")
        theme = active_theme()
        return (f'<div style="color:{theme.axis_text}; padding:3px; font-size:11px">'
                + "<br>".join(lines) + "</div>")

    def _show_hover(self, fid):
        self._hover_id = fid
        if fid is None or fid not in self.geometry:
            self.hover_text.hide()
            return
        self.hover_text.setHtml(self.hover_html(fid))
        self.hover_text.show()
        x, y = self.geometry[fid][:2]
        vb = self.plot.vb
        scene = vb.mapViewToScene(QtCore.QPointF(x, y)) + QtCore.QPointF(12, 12)
        self.hover_text.updateTransform()
        bounds = vb.sceneBoundingRect().adjusted(3, 3, -3, -3)
        rect = self.hover_text.sceneBoundingRect()
        px = max(bounds.left(), min(scene.x(), bounds.right() - rect.width()))
        py = max(bounds.top(), min(scene.y(), bounds.bottom() - rect.height()))
        self.hover_text.setPos(vb.mapFromScene(QtCore.QPointF(px, py)))

    def leaveEvent(self, event):
        self._show_hover(None)
        super().leaveEvent(event)


class ConcordiaPanel(QtWidgets.QWidget):
    """Diagram switch, Th-corrected toggle, reset, the canvas and its caption."""

    diagramChanged = QtCore.Signal(str)
    thChanged = QtCore.Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(4)
        self.buttons = {}
        group = QtWidgets.QButtonGroup(self)
        group.setExclusive(True)
        for key, text, tip in ((review.WETHERILL, "Wetherill", "207Pb/235U vs 206Pb/238U"),
                               (review.TERA_WASSERBURG, "T-W",
                                "Tera-Wasserburg: 238U/206Pb vs 207Pb/206Pb")):
            button = QtWidgets.QToolButton()
            button.setText(text)
            button.setToolTip(tip)
            button.setCheckable(True)
            button.setProperty("modeToggle", True)
            group.addButton(button)
            button.clicked.connect(lambda _c=False, k=key: self.diagramChanged.emit(k))
            bar.addWidget(button)
            self.buttons[key] = button
        self.buttons[review.WETHERILL].setChecked(True)
        self.th_check = QtWidgets.QCheckBox("Th-corrected")
        self.th_check.setToolTip(
            "Plot the 230Th-corrected 206Pb/238U and 207Pb/206Pb (and so 238U/206Pb) with "
            "their joint covariance; 207Pb/235U has no Th correction.")
        self.th_check.toggled.connect(self.thChanged.emit)
        bar.addWidget(self.th_check)
        bar.addStretch(1)
        self.reset_button = QtWidgets.QToolButton()
        self.reset_button.setText("Reset view")
        self.reset_button.setProperty("modeToggle", True)
        self.reset_button.setToolTip("Fit the view to the fractions (or double-click the plot)")
        bar.addWidget(self.reset_button)
        layout.addLayout(bar)
        self.canvas = ConcordiaCanvas()
        self.reset_button.clicked.connect(self.canvas.restore_default_view)
        layout.addWidget(self.canvas, 1)
        self.caption = QtWidgets.QLabel()
        self.caption.setObjectName("SecondaryText")
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)
        self.update_caption()

    def set_state(self, diagram, th_shown, th_available):
        for key, button in self.buttons.items():
            button.blockSignals(True)
            button.setChecked(key == diagram)
            button.blockSignals(False)
        self.th_check.blockSignals(True)
        self.th_check.setEnabled(th_available)
        self.th_check.setChecked(th_shown)
        self.th_check.blockSignals(False)
        self.th_check.setToolTip(self.th_check.toolTip() if th_available else
                                 "No Th correction is set (step 5).")
        self.update_caption()

    def update_caption(self):
        self.caption.setText(
            f"{review.ELLIPSE_CAPTION}. Hollow dashed grey: switched off; amber outline: "
            "diagnostic substitution. Click selects, Ctrl/Cmd-click or E switches on/off.")

    def refresh_theme(self):
        self.canvas.apply_theme()
