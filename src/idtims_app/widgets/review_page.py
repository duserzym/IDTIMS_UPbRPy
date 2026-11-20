"""Step 7, Review: results table, concordia and weighted mean with fractions on and off.

One include set lives in the session (`Session.excluded_fractions`). The
table's check boxes, the concordia (Ctrl/Cmd-click, or select and press E)
and the ranked-date plot all switch it, and every view redraws from it, so
they stay in sync. It survives re-reduction for fractions still present.

Layout for small screens (Studio's handling): the table sits above the plots
in a vertical splitter and can be hidden ("Hide table"); the concordia and
the weighted mean share a horizontal splitter. The diagnostic-mode banner of
the Reduce step shows here too when the results came from diagnostic mode.
"""
from __future__ import annotations

from html import escape

from PySide6 import QtCore, QtGui, QtWidgets

from idtims_app import review
from idtims_app.ui.tables import FrozenDateTable
from idtims_app.ui.labels import ElidedLabel
from idtims_app.ui.panels import RememberedSplitter, WorkPanel, WorkArea
from idtims_app.widgets.weighted_mean import YZ_NOTE
from idtims_app.ui.theme import active_theme, theme_color
from idtims_app.widgets.concordia import DIAGNOSTIC_COLOR, ConcordiaPanel
from idtims_app.widgets.forms import note_label
from idtims_app.widgets.reduce_page import DiagnosticBanner
from idtims_app.widgets.weighted_mean import WeightedMeanPanel

DATE_KEYS = ("t68", "t75", "t76", "t68_th", "t76_th")

def _date(pair):
    if pair is None:
        return "–"
    value, sigma = pair
    if not (review.finite(value) and review.finite(sigma)):
        return "–"
    return f"{value:.3f} ± {2 * sigma:.3f}"

def _number(value, spec):
    return format(value, spec) if review.finite(value) else "–"

def marker_pixmap(markers):
    """Small round badges side by side: [(colour, glyph), ...]."""
    size = 16
    width = size * max(1, len(markers))
    image = QtGui.QImage(width * 2, size * 2, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(2.0)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    font = QtGui.QFont()
    font.setPixelSize(10)
    font.setBold(True)
    painter.setFont(font)
    for index, (color, glyph) in enumerate(markers):
        rect = QtCore.QRectF(index * size + 1.5, 1.5, size - 3, size - 3)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(color))
        painter.drawEllipse(rect)
        painter.setPen(QtGui.QColor("#ffffff"))
        painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()
    return QtGui.QPixmap.fromImage(image)

class ReviewModel(QtCore.QAbstractTableModel):
    includeToggled = QtCore.Signal(str, bool)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.rows = []
        self.columns = []
        self._icons = {}
        self.th = False

    def set_rows(self, rows, th, identifiers):
        self.beginResetModel()
        self.rows = rows
        self.th = th
        columns = [("fraction", "Fraction"), ("included", "On/off")]
        columns += [(f"id:{name}", "Capsule" if name == "Beaker" else name) for name in identifiers]
        columns += [("t68", "206Pb/238U\nMa ± 2σ"), ("t75", "207Pb/235U\nMa ± 2σ"),
                    ("t76", "207Pb/206Pb\nMa ± 2σ")]
        if th:
            columns += [("t68_th", "206Pb/238U Th\nMa ± 2σ"), ("t76_th", "207Pb/206Pb Th\nMa ± 2σ")]
        columns += [("disc", "% disc.")]
        if th:
            columns += [("disc_th", "% disc.\nTh")]
        columns += [("pbr_pbc", "Pb*/Pbc"), ("pbc_pg", "Pbc\n(pg)"), ("th_u", "Th/U"),
                    ("common_pb", "Common Pb"), ("note", "Note")]
        first = ["fraction", "included", "t68_th" if th else "t68", "t76"]
        titles = dict(columns)
        self.columns = [(k, titles[k]) for k in first] + [(k, t) for k, t in columns if k not in first]
        theme = active_theme()
        quality = (theme_color(theme.danger).name(), "!")
        diagnostic = (DIAGNOSTIC_COLOR, "D")
        self._icons = {key: QtGui.QIcon(marker_pixmap(markers)) for key, markers in
                       {"q": [quality], "d": [diagnostic], "qd": [quality, diagnostic]}.items()}
        self.endResetModel()

    def refresh_checks(self):
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1,
                                                               len(self.columns) - 1))

    def row_of(self, fid):
        return next((i for i, r in enumerate(self.rows) if r.fraction_id == fid), -1)

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == QtCore.Qt.Orientation.Horizontal:
            return self.columns[section][1]
        return str(section + 1)

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.ItemFlag.NoItemFlags
        row = self.rows[index.row()]
        flags = QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable
        if index.column() == 1 and row.reduced:
            flags |= QtCore.Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def setData(self, index, value, role=QtCore.Qt.ItemDataRole.EditRole):
        if role != QtCore.Qt.ItemDataRole.CheckStateRole or index.column() != 1:
            return False
        row = self.rows[index.row()]
        if not row.reduced:
            return False
        state = value.value if hasattr(value, "value") else value
        included = state == QtCore.Qt.CheckState.Checked.value
        self.includeToggled.emit(row.fraction_id, included)
        return True

    def text(self, row, key):
        if key == "included":
            return "" if row.reduced else "–"
        if key == "fraction":
            return row.fraction_id
        if key.startswith("id:"):
            if key == "id:Beaker":
                return " · ".join(row.identifiers[c] for c in ("Beaker", "Capsule Set")
                                  if row.identifiers.get(c))
            return row.identifiers.get(key[3:], "")
        if key == "note":
            if not row.reduced:
                return row.reason
            if row.diagnostic:
                return row.substitutions[0] if row.substitutions else "Diagnostic substitution"
            if not self.session.is_included(row.fraction_id):
                return "Switched off"
            return ""
        if not row.reduced:
            return ""
        value = row.values.get(key)
        if key in DATE_KEYS:
            return _date(value)
        if key in ("disc", "disc_th"):
            return _number(value, ".2f")
        if key == "pbr_pbc":
            return _number(value, ".4g")
        if key == "pbc_pg":
            return _number(value, ".3g")
        if key == "th_u":
            return _number(value, ".3f")
        if key == "common_pb":
            return value or ""
        return ""

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        key = self.columns[index.column()][0]
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self.text(row, key)
        if role == QtCore.Qt.ItemDataRole.CheckStateRole and key == "included" and row.reduced:
            return (QtCore.Qt.CheckState.Checked if self.session.is_included(row.fraction_id)
                    else QtCore.Qt.CheckState.Unchecked)
        if role == QtCore.Qt.ItemDataRole.DecorationRole and key == "fraction":
            code = ("q" if row.quality else "") + ("d" if row.diagnostic else "")
            return self._icons.get(code)
        if role == QtCore.Qt.ItemDataRole.TextAlignmentRole:
            if key in DATE_KEYS or key in ("disc", "disc_th", "pbr_pbc", "pbc_pg", "th_u"):
                return int(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            return int(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        if role == QtCore.Qt.ItemDataRole.ForegroundRole:
            theme = active_theme()
            if not row.reduced or not self.session.is_included(row.fraction_id):
                return QtGui.QBrush(theme_color(theme.faint))
            if key == "note" and row.diagnostic:
                return QtGui.QBrush(QtGui.QColor("#8a5d00"))
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            if key == "included":
                return (("On: included in weighted mean" if self.session.is_included(row.fraction_id)
                         else "Off: excluded from weighted mean") if row.reduced else row.reason)
            lines = [escape(row.fraction_id)] if key == "fraction" else []
            if key in ("fraction", "id:Database link") and row.identifiers.get("Fraction UID"):
                lines.append("Linked to database")
                lines.append("Database Read At: " + escape(row.identifiers.get("Database Read At", "not recorded")))
                lines.append(escape(row.identifiers.get("Database Server", "")))
            if key.startswith("id:") and key != "id:Database link":
                lines.append(escape(str(self.text(row, key))))
            if key == "fraction" or key == "note":
                if not row.reduced:
                    lines.append("<b>Not reduced</b>")
                    lines.append(escape(row.reason))
                if row.quality:
                    lines.append("<b>Linked-error check failed</b>")
                    lines += [escape(q) for q in row.quality]
                if row.diagnostic:
                    lines.append("<b>Diagnostic substitution</b> (uncertainties not certified)")
                    lines += [escape(s) for s in row.substitutions]
                if key == "fraction" and row.reduced:
                    lines.append("Use On/off to include in the weighted mean; Ctrl/Cmd-click its "
                                 "ellipse to switch it on or off.")
            elif key == "common_pb" and row.reduced:
                lines.append("All common Pb is blank (initial 204Pb is zero)"
                             if row.values.get("common_pb") == review.ALL_BLANK else
                             "Common Pb is blank plus initial Pb")
            return "<p style='white-space:normal'>" + "<br>".join(lines) + "</p>" if lines \
                else None
        return None


class ReviewPage(QtWidgets.QWidget):
    changed = QtCore.Signal()

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.run = None
        self.rows = []
        self.selected_id = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.diagnostic_banner = DiagnosticBanner()
        self.diagnostic_banner.label.setToolTip(
            "Results contain substituted covariances and are not certified uncertainties. "
            "Use them to find the problem, not to report dates.")
        self.diagnostic_banner.label.setText(
            "<b>Diagnostic covariance.</b> Substituted covariances; uncertainties are not certified.")
        layout.addWidget(self.diagnostic_banner)

        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(6)
        self.summary = ElidedLabel()
        self.summary.setObjectName("SecondaryText")
        bar.addWidget(self.summary, 1)
        self.all_on_button = QtWidgets.QToolButton()
        self.all_on_button.setText("All on")
        self.all_on_button.setProperty("modeToggle", True)
        self.all_on_button.setToolTip("Switch every reduced fraction on")
        self.all_on_button.clicked.connect(self.include_all)
        bar.addWidget(self.all_on_button)
        self.table_toggle = QtWidgets.QToolButton()
        self.table_toggle.setText("Hide table")
        self.table_toggle.setCheckable(True)
        self.table_toggle.setProperty("modeToggle", True)
        self.table_toggle.setToolTip("Hide the results table to give the plots more room")
        self.table_toggle.toggled.connect(self.set_table_hidden)
        bar.addWidget(self.table_toggle)
        layout.addLayout(bar)

        self.table = FrozenDateTable()
        self.model = ReviewModel(session, self)
        self.model.includeToggled.connect(self.set_included)
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(self.table.SelectionMode.SingleSelection)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        self.table.setHorizontalScrollMode(self.table.ScrollMode.ScrollPerPixel)
        self.table.setStyleSheet("QTableView { font-size: 12px; padding: 0; } "
                                "QHeaderView::section { font-size: 11px; padding: 4px; }")
        self.table.horizontalHeader().setFixedHeight(36)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setMinimumSectionSize(36)
        self.table.setIconSize(QtCore.QSize(16, 14))
        self.table.setVerticalScrollMode(self.table.ScrollMode.ScrollPerPixel)
        self.table.setMinimumSize(270, 100)
        self.table.selectionModel().currentRowChanged.connect(self._table_row_changed)
        self.concordia = ConcordiaPanel()
        self.concordia.diagramChanged.connect(self.set_diagram)
        self.concordia.thChanged.connect(self.set_th_shown)
        self.concordia.canvas.selected.connect(self.select_fraction)
        self.concordia.canvas.toggled.connect(self.toggle_fraction)
        self.weighted = WeightedMeanPanel()
        self.weighted.kindChanged.connect(self.set_kind)
        self.weighted.plot.selected.connect(self.select_fraction)
        self.weighted.plot.toggled.connect(self.toggle_fraction)

        # The choice and maximise button share the slim panel header.
        old_bar = self.weighted.layout().takeAt(0).layout()
        while old_bar.count():
            widget = old_bar.takeAt(0).widget()
            if widget is not None and widget is not self.weighted.kind_combo:
                widget.hide()
                widget.deleteLater()
        self.weighted.note_label.hide()
        self.weighted.result_label.setToolTip(YZ_NOTE)
        self.weighted.plot.emphasize_selection = True
        self.weighted.plot.setMinimumSize(180, 100)
        self.concordia.canvas.setMinimumSize(240, 120)
        self.concordia.caption.setText("Ellipses 2σ · Hollow = off · Click selects · E switches on/off")
        self.concordia.caption.setToolTip(review.ELLIPSE_CAPTION)
        self.concordia.reset_button.setText("Reset")
        self.table_card = self._card("Date table", self.table, self.all_on_button)
        self.concordia_card = self._card("Concordia", self.concordia)
        self.weighted_card = self._card("Weighted mean", self.weighted, self.weighted.kind_combo)
        self.weighted.kind_combo.setMinimumWidth(100)
        self.weighted.kind_combo.setStyleSheet("font-size: 12px; padding: 3px 6px; min-height: 18px;")
        self.weighted.kind_combo.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,
                                              QtWidgets.QSizePolicy.Policy.Fixed)
        self.plots = RememberedSplitter(QtCore.Qt.Orientation.Horizontal, "review_plots", (58, 42))
        self.splitter = RememberedSplitter(QtCore.Qt.Orientation.Vertical, "review_rows", (62, 38))
        for splitter in (self.plots, self.splitter):
            splitter.setChildrenCollapsible(False)
            splitter.setHandleWidth(8)
        self.plots.addWidget(self.concordia_card)
        self.plots.addWidget(self.weighted_card)
        self.splitter.addWidget(self.plots)
        self.splitter.addWidget(self.table_card)
        self.concordia_card.setMinimumSize(360, 216)
        self.weighted_card.setMinimumSize(260, 216)
        self.table_card.setMinimumSize(270, 182)
        self.work_area = WorkArea(self.splitter, (self.concordia_card, self.weighted_card, self.table_card))
        layout.addWidget(self.work_area, 1)
        self.empty = note_label()
        layout.addWidget(self.empty)
        self.refresh()
        self._style_selection()

    def set_included(self, fid, included):
        if self.session.set_included(fid, included):
            self._include_changed()

    def toggle_fraction(self, fid):
        self.select_fraction(fid)
        self.set_included(fid, not self.session.is_included(fid))

    def include_all(self):
        if self.session.excluded_fractions:
            self.session.excluded_fractions.clear()
            self._include_changed()

    def _include_changed(self):
        self.model.refresh_checks()
        self.concordia.canvas.set_excluded(self.session.excluded_fractions)
        self._update_mean()
        self._update_summary()
        self.changed.emit()

    def select_fraction(self, fid):
        self.selected_id = fid
        row = self.model.row_of(fid)
        if row >= 0 and self.table.currentIndex().row() != row:
            self.table.selectionModel().blockSignals(True)
            self.table.selectRow(row)
            self.table.selectionModel().blockSignals(False)
            self.table.scrollTo(self.model.index(row, 0))
        self.concordia.canvas.set_selected(fid)
        self.weighted.plot.set_selected(fid)

        self._update_summary()

    def _table_row_changed(self, current, _previous=None):
        if current.isValid() and current.row() < len(self.model.rows):
            fid = self.model.rows[current.row()].fraction_id
            self.selected_id = fid
            self.concordia.canvas.set_selected(fid)
            self.weighted.plot.set_selected(fid)

        self._update_summary()

    def set_diagram(self, diagram):
        self.session.review_diagram = diagram
        self._update_concordia(reset_view=True)

    def set_th_shown(self, on):
        self.session.review_th_ratios = bool(on)
        self._update_concordia(reset_view=True)

    def set_kind(self, kind):
        self.session.review_kind = kind
        self._update_mean()

    def set_table_hidden(self, hidden):
        self.work_area.set_panel_visible(self.table_card, not hidden)
        self.table_toggle.setText("Show table" if hidden else "Hide table")

    def refresh(self):
        session = self.session
        run = session.reduction
        has = run is not None and session.reduction_current and bool(run.grains)
        self.work_area.setVisible(has)
        self.splitter.setVisible(has and self.work_area.maximised is None)
        self.all_on_button.setVisible(has)
        self.table_toggle.setVisible(has)
        self.diagnostic_banner.setVisible(has and not run.strict)
        if not has:
            self.run = None
            self.empty.setText("Reduce on step 6 first; Review shows the reduced fractions.")
            self.empty.show()
            self.summary.setText(session.summary_text())
            self.summary.setToolTip(session.summary_text())
            return
        self.empty.hide()
        if run is not self.run:
            self.run = run
            self.rows = review.build_rows(run, session.fraction_identifiers())
            identifiers = [c for c in review.IDENTIFIERS
                           if any(r.identifiers.get(c) or c == "Beaker" and r.identifiers.get("Capsule Set")
                                  for r in self.rows)]
            self.model.set_rows(self.rows, session.th_correction_applied, identifiers)
            self._fit_columns()
            th = session.th_correction_applied
            self.weighted.set_kinds(review.date_kinds(th), session.review_date_kind())
            if self.selected_id not in {r.fraction_id for r in self.rows if r.reduced}:
                self.selected_id = None
            self._update_concordia(reset_view=True)
            self._update_mean()
        else:
            self.model.refresh_checks()
            self.concordia.canvas.set_excluded(session.excluded_fractions)
            self._update_mean()
        self._update_summary()

        if self.selected_id is None:
            self.selected_id = next((r.fraction_id for r in self.rows if r.reduced), None)
        if self.selected_id is not None:
            self.select_fraction(self.selected_id)
        self.table.sync_frozen()

    def _update_summary(self):
        if self.run is None:
            return
        reduced = len(self.run.grains)
        selected = self.selected_id
        state = "On" if selected and self.session.is_included(selected) else "Off"
        if selected and not any(r.fraction_id == selected and r.reduced for r in self.rows):
            state = "Not reduced"
        theme = active_theme()
        self.summary.setText(
            f"Selected: {selected or '—'} · {state} | {len(self.session.included_ids())}/{reduced} on"
            f" · {len(self.rows) - reduced} not reduced · "
            + ("Strict covariance" if self.run.strict else "Diagnostic covariance"))
        self.summary.setToolTip(self.session.summary_text())

    def _update_concordia(self, reset_view=True):
        session = self.session
        th_available = session.th_correction_applied
        diagram = session.review_diagram
        th = session.review_th_shown()
        self.concordia.set_state(diagram, th, th_available)
        self.concordia.canvas.set_data(self.rows, diagram, th, session.excluded_fractions,
                                       self.selected_id, reset_view=reset_view)
        self.concordia.caption.setText("Ellipses 2σ · Hollow = off · Click selects · E switches on/off")

    def _update_mean(self):
        session = self.session
        if self.run is None:
            return
        grains = self.run.grains
        kind = session.review_date_kind()
        sample = review.sample_date(grains, session.excluded_fractions, kind)
        self.weighted.show_result(sample, len(grains), review.ranked_dates(grains, kind),
                                  session.excluded_fractions, self.selected_id)

        sample = self.weighted.sample
        lines = review.mean_lines(sample, len(self.run.grains))
        # These are the same formatted engine results, with a visual hierarchy only.
        result, _, level = lines[0].partition(" (2σ")
        theme = active_theme()
        html = [f"<span style='font-size:24px; font-weight:700; color:{theme.text}'>"
                f"{escape(result)}</span>"]
        if level:
            html.append("<span style='font-size:10px'>2σ · X: analytical</span>")
        html += [f"<span style='font-size:11px'>{escape(line)}</span>" for line in lines[1:]]
        self.weighted.result_label.setText("<br>".join(html))

    def current_sample(self):
        """The SampleDate shown on the weighted-mean panel (tests)."""
        return self.weighted.sample

    def _fit_columns(self):
        metrics = self.table.fontMetrics()
        for column, (key, header) in enumerate(self.model.columns[:-1]):
            widest = max(metrics.horizontalAdvance(p) for p in header.split("\n")) + 20
            for row in self.model.rows:
                widest = max(widest, metrics.horizontalAdvance(self.model.text(row, key)) + 16)
            if column == 0:
                widest += 52
            self.table.setColumnWidth(column, min(widest, 150))

        long_ids = any(len(row.fraction_id) > 18 for row in self.rows)
        self.table.setColumnWidth(0, 150 if long_ids else 86)
        self.table.setColumnWidth(1, 58)
        for column in (2, 3):
            self.table.setColumnWidth(column, 140)
        self.table.sync_frozen()

    def refresh_theme(self):
        self.diagnostic_banner.refresh_theme()
        if self.run is not None:
            identifiers = [c for c in review.IDENTIFIERS
                           if any(r.identifiers.get(c) or c == "Beaker" and r.identifiers.get("Capsule Set")
                                  for r in self.rows)]
            self.model.set_rows(self.rows, self.session.th_correction_applied, identifiers)
        self.concordia.refresh_theme()
        self.weighted.refresh_theme()
        self.refresh()

        self._style_selection()

    def _card(self, title, content, control=None):
        return WorkPanel(title, content, control)

    def _style_selection(self):
        theme = active_theme()
        self.setStyleSheet(
            f"QFrame#WorkPanel {{ background: {theme.glass}; border: 1px solid "
            f"{theme.input_border}; border-radius: 10px; }}"
            f"QTableView::item:selected {{ background: {theme.accent_soft}; color: {theme.accent}; }}")
        self.table.frozen.setStyleSheet(f"QTableView {{ background: {theme.surface}; font-size: 11px; "
                                       f"border: none; border-right: 1px solid {theme.input_border}; "
                                       "border-radius: 0; padding: 0; } "
                                       "QHeaderView::section { font-size: 11px; padding: 4px; }")

__all__ = ["ReviewModel", "ReviewPage", "marker_pixmap"]
