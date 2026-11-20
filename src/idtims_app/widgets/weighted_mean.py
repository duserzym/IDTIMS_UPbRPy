"""Weighted-mean panel of the Review step: date kind, result and a ranked-date plot.

Every number comes from `IDTIMS_UPbRPy.dates.sample_dates` (through
`review.sample_date`); this module formats and draws it. The result is the
analytical ("X") level. The tracer ("Y") and decay-constant ("Z") levels
need tracer calibration uncertainties and are not available yet.

The ranked plot shows each fraction's date ± 2σ as a vertical bar, youngest
on the left, with the weighted mean and its ±2σ band (and the ±2σ·√MSWD band
when MSWD > 1). Switched-off fractions are grey. Clicks follow the concordia:
a click selects, Ctrl/Cmd-click or E switches on/off.
"""
from __future__ import annotations

import weakref

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from idtims_app import review
from idtims_app.ui.plots import AxisZoomViewBox, RoundedPlotWidget, _make_diag_axis
from idtims_app.ui.theme import active_theme, theme_color

YZ_NOTE = ("Y (tracer) and Z (decay constant) levels need tracer calibration uncertainties "
           "and are not available yet.")


class _RankedViewBox(AxisZoomViewBox):
    owner = None

    def mouseClickEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self.owner is not None:
            self.owner.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
            if event.double():
                self.owner.autoRange()
            else:
                self.owner.click_at(event.scenePos(), event.modifiers())
            event.accept()
            return
        super().mouseClickEvent(event)


class RankedDatePlot(RoundedPlotWidget):
    """Vertical bars ± 2σ per fraction, mean line and ±2σ band."""

    selected = QtCore.Signal(str)
    toggled = QtCore.Signal(str)

    def __init__(self, parent=None):
        view_box = _RankedViewBox()
        super().__init__(parent, viewBox=view_box)
        view_box.owner = weakref.proxy(self)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(220, 150)
        self.entries = []        # (fid, date, sigma), youngest first
        self.excluded = set()
        self.selected_id = None
        self.result = None
        self.kind = review.DEFAULT_KIND
        item = self.getPlotItem()
        item.hideButtons()
        for menu in (item.ctrlMenu, item.vb.menu):
            menu.setParent(self, menu.windowFlags())
        self.band_expanded = pg.FillBetweenItem(pg.PlotCurveItem(), pg.PlotCurveItem())
        self.band = pg.FillBetweenItem(pg.PlotCurveItem(), pg.PlotCurveItem())
        self.mean_line = pg.PlotCurveItem()
        self.bars_on = pg.ErrorBarItem(beam=0.18)
        self.bars_off = pg.ErrorBarItem(beam=0.18)
        self.bars_selected = pg.ErrorBarItem(beam=0.24)
        self.centres = pg.ScatterPlotItem(size=6)
        self.centres.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
        for z, graphic in enumerate((self.band_expanded, self.band, self.mean_line, self.bars_off,
                                     self.bars_on, self.bars_selected, self.centres)):
            graphic.setZValue(z)
            item.addItem(graphic)
        self.apply_theme()

    def apply_theme(self):
        theme = active_theme()
        self.setBackground(theme.plot_background)
        item = self.getPlotItem()
        _make_diag_axis(item, theme)
        item.getAxis("left").enableAutoSIPrefix(False)
        item.setLabel("left", "Ma", color=theme.axis_text, size="11px")
        self.redraw(reset=False)

    def set_data(self, entries, excluded, result, kind, selected_id=None):
        entries = list(entries)
        reset = entries != self.entries or kind != self.kind
        self.entries = entries
        self.excluded = set(excluded)
        self.result = result
        self.kind = kind
        self.selected_id = selected_id
        self.redraw(reset=reset)

    def set_selected(self, fid):
        self.selected_id = fid
        self.redraw(reset=False)

    def redraw(self, reset=False):
        theme = active_theme()
        item = self.getPlotItem()
        n = len(self.entries)
        x = np.arange(1, n + 1, dtype=float)
        dates = np.array([e[1] for e in self.entries], dtype=float)
        sigmas = np.array([2 * e[2] for e in self.entries], dtype=float)
        off = np.array([e[0] in self.excluded for e in self.entries], dtype=bool)
        chosen = np.array([e[0] == self.selected_id for e in self.entries], dtype=bool)
        accent, muted = QtGui.QColor(theme.accent), QtGui.QColor(theme.muted)
        for bars, mask, color, width in ((self.bars_on, ~off, accent, 2.0),
                                         (self.bars_off, off, muted, 1.6),
                                         (self.bars_selected, chosen,
                                          QtGui.QColor(theme.accent if getattr(self, "emphasize_selection", False)
                                                       else theme.text),
                                          4.0 if getattr(self, "emphasize_selection", False) else 2.6)):
            if mask.any():
                bars.setData(x=x[mask], y=dates[mask], top=sigmas[mask], bottom=sigmas[mask],
                             pen=pg.mkPen(color, width=width))
                bars.show()
            else:
                bars.hide()
        if n:
            self.centres.setData(x=x, y=dates, size=6,
                                 brush=[pg.mkBrush(None) if o else pg.mkBrush(accent) for o in off],
                                 pen=[pg.mkPen(muted, width=1.2) if o else
                                      pg.mkPen(theme.axis_text, width=0.6) for o in off])
        else:
            self.centres.setData([], [])
        result = self.result
        span = np.array([0.4, n + 0.6])
        if result is not None and n:
            mean, two = result.mean, 2 * result.sigma
            self.mean_line.setData(span, [mean, mean], pen=pg.mkPen(theme.accent, width=1.4))
            fill = theme_color(theme.accent_soft)
            self._band(self.band, span, mean, two, fill)
            if result.n > 1 and result.mswd > 1:
                wide = QtGui.QColor(fill)
                wide.setAlpha(max(12, fill.alpha() // 2))
                self._band(self.band_expanded, span, mean, 2 * result.sigma_expanded, wide)
                self.band_expanded.show()
            else:
                self.band_expanded.hide()
            self.band.show()
            self.mean_line.show()
        else:
            self.band.hide()
            self.band_expanded.hide()
            self.mean_line.hide()
        axis = item.getAxis("bottom")
        axis.setTicks([[(i + 1, e[0]) for i, e in enumerate(self.entries)
                        if i % self._label_every() == 0]])
        item.setLabel("bottom", f"{self.kind} date, ranked", color=theme.axis_text, size="11px")
        if reset:
            self.autoRange()

    def _label_every(self):
        """Label every k-th bar so fraction ids do not overlap."""
        if not self.entries:
            return 1
        metrics = QtGui.QFontMetrics(self.font())
        widest = max(metrics.horizontalAdvance(e[0]) for e in self.entries) + 8
        width = max(self.getPlotItem().vb.width(), self.width() - 60, 1)
        per_bar = width / len(self.entries)
        return max(1, int(np.ceil(widest / per_bar)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "entries", None):
            self.redraw(reset=False)

    def autoRange(self):
        item = self.getPlotItem()
        if not self.entries:
            item.setRange(xRange=(0, 1), yRange=(0, 1), padding=0)
            return
        dates = np.array([e[1] for e in self.entries])
        sigmas = np.array([2 * e[2] for e in self.entries])
        low, high = float(np.min(dates - sigmas)), float(np.max(dates + sigmas))
        if self.result is not None:
            wide = 2 * self.result.sigma_expanded
            low, high = min(low, self.result.mean - wide), max(high, self.result.mean + wide)
        pad = max((high - low) * 0.08, 1e-6)
        item.setRange(xRange=(0.4, len(self.entries) + 0.6), yRange=(low - pad, high + pad),
                      padding=0)

    @staticmethod
    def _band(band, span, mean, half, color):
        band.curves[0].setData(span, [mean - half] * 2)
        band.curves[1].setData(span, [mean + half] * 2)
        band.setBrush(pg.mkBrush(color))
        band.setPen(pg.mkPen(None))

    def fraction_at(self, scene_pos):
        vb = self.getPlotItem().vb
        if not self.entries or not vb.sceneBoundingRect().contains(scene_pos):
            return None
        pos = vb.mapSceneToView(scene_pos)
        index = int(round(pos.x())) - 1
        if not 0 <= index < len(self.entries):
            return None
        fid, date, sigma = self.entries[index]
        pixel = np.abs(vb.viewPixelSize())
        tolerance = 8 * pixel[1]
        if abs(pos.x() - (index + 1)) > 0.35 or abs(pos.y() - date) > 2 * sigma + tolerance:
            return None
        return fid

    def scene_position(self, fid):
        index = next(i for i, e in enumerate(self.entries) if e[0] == fid)
        return self.getPlotItem().vb.mapViewToScene(QtCore.QPointF(index + 1,
                                                                   self.entries[index][1]))

    def click_at(self, scene_pos, modifiers):
        fid = self.fraction_at(scene_pos)
        if fid is None:
            return
        if modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.toggled.emit(fid)
        else:
            self.selected.emit(fid)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key.Key_E and \
                any(e[0] == self.selected_id for e in self.entries):
            self.toggled.emit(self.selected_id)
            event.accept()
            return
        super().keyPressEvent(event)


class WeightedMeanPanel(QtWidgets.QWidget):
    """Date kind selector, the weighted mean of the included fractions, the ranked plot."""

    kindChanged = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sample = None
        self._total = 0
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(6)
        label = QtWidgets.QLabel("Weighted mean")
        label.setObjectName("SectionTitle")
        bar.addWidget(label)
        self.kind_combo = QtWidgets.QComboBox()
        self.kind_combo.setToolTip("Date used for the weighted mean (206Pb/238U by default)")
        self.kind_combo.currentIndexChanged.connect(self._kind_selected)
        bar.addWidget(self.kind_combo, 1)
        layout.addLayout(bar)
        self.result_label = QtWidgets.QLabel()
        self.result_label.setObjectName("PanelBody")
        self.result_label.setWordWrap(True)
        self.result_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.result_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.result_label)
        self.note_label = QtWidgets.QLabel(YZ_NOTE)
        self.note_label.setObjectName("SecondaryText")
        self.note_label.setWordWrap(True)
        layout.addWidget(self.note_label)
        self.plot = RankedDatePlot()
        layout.addWidget(self.plot, 1)

    def set_kinds(self, kinds, current):
        self.kind_combo.blockSignals(True)
        self.kind_combo.clear()
        self.kind_combo.addItems(kinds)
        self.kind_combo.setCurrentIndex(kinds.index(current) if current in kinds else 0)
        self.kind_combo.blockSignals(False)

    def _kind_selected(self, index):
        if index >= 0:
            self.kindChanged.emit(self.kind_combo.itemText(index))

    def show_result(self, sample, total, entries, excluded, selected_id=None):
        """Show a `dates.SampleDate` (from sample_dates) and its ranked plot."""
        self.sample = sample
        self._total = total
        lines = review.mean_lines(sample, total)
        theme = active_theme()
        html = [f"<span style='font-size:15px; font-weight:600; color:{theme.text}'>"
                f"{lines[0]}</span>"] + lines[1:]
        skipped = {fid: why for fid, why in sample.skipped.items() if why != "switched off"}
        if skipped:
            html.append("Left out: " + ", ".join(f"{fid} ({why})" for fid, why in skipped.items()))
        self.result_label.setText("<br>".join(html))
        self.plot.set_data(entries, excluded, sample.result, sample.kind, selected_id)

    def refresh_theme(self):
        self.plot.apply_theme()
        if self.sample is not None:
            self.show_result(self.sample, self._total, self.plot.entries,
                             self.plot.excluded, self.plot.selected_id)
