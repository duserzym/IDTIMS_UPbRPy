"""Step 6, Reduce: run the reduction off the UI thread and show per-fraction status.

The session snapshots the run on the GUI thread (`Session.prepare_reduction`);
`ReductionJob.run()` then goes to Qt's thread pool through Studio's
`FunctionWorker`, one `load_grains` call per fraction. While it runs, the page
keeps working and the status bar shows the busy indicator.

Covariance mode is a per-project choice, strict by default. Diagnostic mode
is an explicit, labelled check box; while it is on, a banner that cannot be
dismissed says the results contain substituted covariances and are not
certified uncertainties.
"""
from __future__ import annotations

import math
from html import escape

from PySide6 import QtCore, QtGui, QtWidgets

from idtims_app.reduction import DIAGNOSTIC, NOT_REDUCED, REDUCED
from idtims_app.ui.panels import RememberedSplitter, WorkPanel, WorkArea, scroll_content
from idtims_app.ui.theme import active_theme, theme_color
from idtims_app.widgets.fraction_table import marker_icon
from idtims_app.widgets.forms import note_label
from idtims_app.widgets.import_page import MessageBanner
from idtims_app.workers import FunctionWorker

RESULT_COLUMNS = ["Fraction", "Status", "206Pb/238U\n(Ma ± 2σ)", "207Pb/206Pb\n(Ma ± 2σ)",
                  "207Pb/235U\n(Ma ± 2σ)", "206Pb/238U Th\n(Ma ± 2σ)",
                  "207Pb/206Pb Th\n(Ma ± 2σ)", "Pb*/Pbc", "Reason"]
DATE_ATTRIBUTES = [("t68", "t68_std"), ("t76", "t76_std"), ("t75", "t75_std"),
                   ("t68_Th_corr", "t68_Th_corr_std"), ("t76_Th_corr", "t76_Th_corr_std")]


def date_text(grain, name, std):
    value, sigma = getattr(grain, name, None), getattr(grain, std, None)
    if value is None or sigma is None or not (math.isfinite(value) and math.isfinite(sigma)):
        return "–"
    return f"{value:.3f} ± {2 * sigma:.3f}"


class DiagnosticBanner(QtWidgets.QFrame):
    """Persistent warning while diagnostic covariance mode is on (no close button)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DiagnosticBanner")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 7, 12, 7)
        self.label = QtWidgets.QLabel(
            "<b>Diagnostic covariance mode is on.</b> Results contain substituted covariances "
            "and are not certified uncertainties. Use them to find the problem, not to "
            "report dates.")
        self.label.setObjectName("MessageText")
        self.label.setWordWrap(True)
        layout.addWidget(self.label, 1)
        self.refresh_theme()

    def refresh_theme(self):
        theme = active_theme()
        self.setStyleSheet(
            f"QFrame#DiagnosticBanner {{ background: rgba(214,138,0,0.14); border: 1px solid "
            f"#c98a00; border-radius: 12px; }} QLabel#MessageText {{ color: {theme.text}; }}")


class ResultsModel(QtCore.QAbstractTableModel):
    """One row per fraction of the session's last reduction."""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._results = []
        self._icons = {}
        self.run = None

    def refresh(self):
        self.beginResetModel()
        run = self.session.reduction
        self.run = run
        self._results = list(run.results) if run is not None else []
        theme = active_theme()
        self._icons = {"quality": marker_icon(theme_color(theme.danger), "!")}
        self.endResetModel()

    def result(self, row):
        return self._results[row]

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self._results)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(RESULT_COLUMNS)

    def headerData(self, section, orientation, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if orientation == QtCore.Qt.Orientation.Horizontal and \
                role == QtCore.Qt.ItemDataRole.DisplayRole:
            return RESULT_COLUMNS[section]
        if orientation == QtCore.Qt.Orientation.Vertical and \
                role == QtCore.Qt.ItemDataRole.DisplayRole:
            return str(section + 1)
        return None

    def _th_applied(self):
        run = self.session.reduction
        return run is not None and run.th_kind is not None

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        result = self._results[index.row()]
        column = index.column()
        grain = result.grain
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            if column == 0:
                return result.fraction_id
            if column == 1:
                return result.status_text
            if 2 <= column <= 6:
                if grain is None:
                    return ""
                if column >= 5 and not self._th_applied():
                    return "no Th corr."
                return date_text(grain, *DATE_ATTRIBUTES[column - 2])
            if column == 7:
                value = getattr(grain, "Pbr_Pbc", None) if grain is not None else None
                return "" if value is None or not math.isfinite(value) else f"{value:.4g}"
            if column == 8:
                if result.status == DIAGNOSTIC:
                    return result.substitutions[0] if result.substitutions else ""
                return result.reason
        if role == QtCore.Qt.ItemDataRole.TextAlignmentRole:
            if 2 <= column <= 7:
                return int(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            return int(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        if role == QtCore.Qt.ItemDataRole.DecorationRole and column == 0 and result.quality:
            return self._icons["quality"]
        if role == QtCore.Qt.ItemDataRole.ForegroundRole and column == 1:
            theme = active_theme()
            return QtGui.QBrush(theme_color({REDUCED: theme.success, DIAGNOSTIC: "#b07800",
                                             NOT_REDUCED: theme.danger}[result.status]))
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            lines = []
            if column == 0 and result.quality:
                lines.append("<b>Linked-error check failed</b>")
                lines += [escape(q) for q in result.quality]
            elif column in (1, 8):
                lines.append(f"<b>{escape(result.status_text)}</b>")
                if result.reason:
                    lines.append(escape(result.reason))
                if result.hint:
                    lines.append(escape(result.hint))
                lines += [escape(s) for s in result.substitutions]
            return "<p style='white-space:normal'>" + "<br>".join(lines) + "</p>" if lines \
                else None
        return None


class ReducePage(QtWidgets.QWidget):
    """Reduce button, covariance mode, banner, results table and full-table export."""

    changed = QtCore.Signal()
    busyStarted = QtCore.Signal(str)
    busyProgress = QtCore.Signal(str)
    busyStopped = QtCore.Signal()

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._worker = None
        self._running = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(6)
        self.reduce_button = QtWidgets.QPushButton("Reduce")
        self.reduce_button.setProperty("accent", True)
        self.reduce_button.setToolTip("Reduce every ready fraction, one load_grains call each "
                                      "(Ctrl+R)")
        self.reduce_button.setShortcut(QtGui.QKeySequence("Ctrl+R"))
        self.reduce_button.clicked.connect(self.start)
        bar.addWidget(self.reduce_button)
        self.export_button = QtWidgets.QPushButton("Export full table…")
        self.export_button.setToolTip("Every numeric attribute of every reduced fraction, "
                                      "17 significant digits (CSV)")
        self.export_button.clicked.connect(self.choose_export_path)
        bar.addWidget(self.export_button)
        bar.addSpacing(8)
        self.diagnostic_check = QtWidgets.QCheckBox("Diagnostic covariance mode")
        self.diagnostic_check.setToolTip(
            "Per-project choice. Strict (off, the default) refuses fractions whose input "
            "covariances are impossible. Diagnostic (on) substitutes zero for them and reduces "
            "anyway; such results are not certified uncertainties.")
        self.diagnostic_check.toggled.connect(self.set_diagnostic)
        bar.addWidget(self.diagnostic_check)
        bar.addStretch(1)
        layout.addLayout(bar)

        self.diagnostic_banner = DiagnosticBanner()
        layout.addWidget(self.diagnostic_banner)
        self.banner = MessageBanner()
        layout.addWidget(self.banner)

        pills = QtWidgets.QHBoxLayout()
        pills.setSpacing(6)
        self.reduced_pill = QtWidgets.QLabel()
        self.reduced_pill.setObjectName("StatusPill")
        self.diagnostic_pill = QtWidgets.QLabel()
        self.not_reduced_pill = QtWidgets.QLabel()
        self.mode_label = note_label()
        for widget in (self.reduced_pill, self.diagnostic_pill, self.not_reduced_pill):
            pills.addWidget(widget)
        pills.addWidget(self.mode_label, 1)
        layout.addLayout(pills)

        self.model = ResultsModel(session, self)
        self.table = QtWidgets.QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setIconSize(QtCore.QSize(14, 14))
        self.table.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.selectionModel().currentRowChanged.connect(self._show_details)


        self.details = QtWidgets.QLabel()
        self.details.setObjectName("PanelBody")
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.details.setMinimumHeight(48)
        self.details.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.table_card = WorkPanel("Reduction results", self.table, minimum=(300, 150))
        self.details_card = WorkPanel("Selected fraction", scroll_content(self.details), minimum=(250, 100))
        self.splitter = RememberedSplitter(QtCore.Qt.Orientation.Vertical, "reduce", (74, 26))
        self.splitter.addWidget(self.table_card)
        self.splitter.addWidget(self.details_card)
        self.work_area = WorkArea(self.splitter, (self.table_card, self.details_card))
        layout.addWidget(self.work_area, 1)
        self.empty = note_label()
        layout.addWidget(self.empty)
        self.refresh()

    # -- mode ----------------------------------------------------------------
    def set_diagnostic(self, on):
        self.session.set_strict_covariance(not on)
        self.refresh()
        self.changed.emit()

    # -- running -------------------------------------------------------------
    def _prepare(self):
        ok, message = self.session.can_reduce()
        if not ok:
            self.banner.show_message(message)
            return None
        try:
            return self.session.prepare_reduction()
        except ValueError as exc:  # SettingsError
            self.banner.show_message(str(exc))
            return None

    def start(self):
        """Run the reduction on Qt's thread pool."""
        if self._running:
            return
        job = self._prepare()
        if job is None:
            return
        self._running = True
        self.reduce_button.setEnabled(False)
        self.banner.hide()
        self.busyStarted.emit("Reducing")
        worker = FunctionWorker(lambda: job.run(progress=self._report_progress))
        worker.signals.succeeded.connect(self._finished)
        worker.signals.failed.connect(self._failed)
        worker.signals.finished.connect(self._done)
        self._worker = worker
        QtCore.QThreadPool.globalInstance().start(worker)

    def _report_progress(self, text):
        # Called on the worker thread; a queued signal reaches the busy indicator.
        self.busyProgress.emit(text)

    def run_sync(self):
        """Reduce on this thread (for --export and tests); returns the run or None."""
        job = self._prepare()
        if job is None:
            return None
        run = job.run()
        self._finished(run)
        return run

    def wait(self, timeout_ms=60000):
        """Block until a started reduction is done (tests)."""
        timer = QtCore.QElapsedTimer()
        timer.start()
        while self._running and timer.elapsed() < timeout_ms:
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 50)
        return not self._running

    @property
    def running(self):
        return self._running

    def _finished(self, run):
        self.session.apply_reduction(run)
        self.model.refresh()
        self._select_default()
        stale = not self.session.reduction_current
        if stale:
            self.banner.show_message("The fractions or settings changed while reducing; these "
                                     "results are out of date. Reduce again.", "note")
        self.refresh()
        self.changed.emit()

    def _failed(self, message, _trace):
        self.banner.show_message(f"Reduction failed: {message}")

    def _done(self):
        self._running = False
        self._worker = None
        self.reduce_button.setEnabled(True)
        self.busyStopped.emit()
        self.refresh()

    # -- export --------------------------------------------------------------------
    def choose_export_path(self):
        if not self._can_export():
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export full table",
                                                        "reduced_full_table.csv", "CSV (*.csv)")
        if path:
            self.export_to(path)

    def _can_export(self):
        run = self.session.reduction
        return run is not None and bool(run.grains)

    def export_to(self, path):
        try:
            self.session.export_full_table(path)
        except OSError as exc:
            self.banner.show_message(f"Could not write {path}: {exc.strerror or exc}")
            return False
        count = len(self.session.reduction.grains)
        self.banner.show_message(f"Wrote the full table of {count} reduced fraction"
                                 f"{'s' if count != 1 else ''} to {path}.", "note")
        return True

    # -- refresh -------------------------------------------------------------------
    def _select_default(self):
        """Select the first fraction that was not reduced (its reason shows below), else the first."""
        if not self.model.rowCount():
            return
        row = next((r for r in range(self.model.rowCount())
                    if self.model.result(r).status == NOT_REDUCED), 0)
        self.table.selectRow(row)
        self._show_details(self.model.index(row, 0))

    def _show_details(self, current, _previous=None):
        if not current.isValid() or current.row() >= self.model.rowCount():
            self.details.setText("")
            return
        result = self.model.result(current.row())
        theme = active_theme()
        color = {REDUCED: theme.success, DIAGNOSTIC: "#b07800",
                 NOT_REDUCED: theme.danger}[result.status]
        parts = [f"<b>{escape(result.fraction_id)}</b>: "
                 f"<span style='color:{color}'>{escape(result.status_text)}</span>"]
        if result.reason:
            parts.append(escape(result.reason))
        if result.hint:
            parts.append(f"<span style='color:{theme.muted}'>{escape(result.hint)}</span>")
        for text in result.substitutions[:2]:
            parts.append(escape(text))
        if result.quality:
            parts.append(f"<span style='color:{theme.danger}'>Linked-error check: "
                         f"{escape(result.quality[0])}</span>")
        self.details.setText("<br>".join(parts[:1]) + " " + " ".join(parts[1:]))

    def refresh(self):
        session = self.session
        diagnostic = not session.strict_covariance
        self.diagnostic_check.blockSignals(True)
        self.diagnostic_check.setChecked(diagnostic)
        self.diagnostic_check.blockSignals(False)
        self.diagnostic_banner.setVisible(diagnostic)
        ok, message = session.can_reduce()
        self.reduce_button.setEnabled(ok and not self._running)
        self.export_button.setEnabled(self._can_export() and session.reduction_current)
        run = session.reduction
        if self.model.run is not run:
            self.model.refresh()
            self._select_default()
        theme = active_theme()
        self.work_area.setVisible(run is not None)
        if run is None:
            for pill in (self.reduced_pill, self.diagnostic_pill, self.not_reduced_pill):
                pill.hide()
            self.mode_label.setText("Strict covariance (the default)." if not diagnostic else
                                    "Diagnostic covariance mode.")
            self.empty.setText("Press Reduce to reduce every ready fraction. " + (
                "" if ok else message))
            self.empty.show()
            self.table.hide()
            self.details.hide()
        else:
            counts = run.counts()
            self.empty.hide()
            self.table.show()
            self.details.show()
            self.reduced_pill.setText(f"{counts[REDUCED]} reduced")
            self.reduced_pill.setVisible(True)
            self.diagnostic_pill.setText(f"{counts[DIAGNOSTIC]} with diagnostic substitution")
            self.diagnostic_pill.setStyleSheet("padding: 4px 10px; border-radius: 10px; "
                                               "color: #8a5d00; background: rgba(214,138,0,0.14);")
            self.diagnostic_pill.setVisible(bool(counts[DIAGNOSTIC]))
            self.not_reduced_pill.setText(f"{counts[NOT_REDUCED]} not reduced")
            self.not_reduced_pill.setStyleSheet(
                f"padding: 4px 10px; border-radius: 10px; color: {theme.danger}; "
                "background: rgba(194,65,59,0.10);")
            self.not_reduced_pill.setVisible(bool(counts[NOT_REDUCED]))
            mode = "strict covariance" if run.strict else "diagnostic covariance mode"
            stale = "" if session.reduction_current else \
                " Out of date: the fractions, settings or mode changed since; reduce again."
            self.mode_label.setText(f"Last run: {mode}.{stale}")
            self.mode_label.setStyleSheet(f"color: {theme.danger};" if stale else "")
            self._fit_columns()

    def _fit_columns(self):
        metrics = self.table.fontMetrics()
        for column in range(self.model.columnCount() - 1):
            header = max(metrics.horizontalAdvance(p) for p in RESULT_COLUMNS[column].split("\n"))
            widest = header + 22
            for row in range(self.model.rowCount()):
                text = self.model.data(self.model.index(row, column)) or ""
                widest = max(widest, metrics.horizontalAdvance(text) + 18)
            if column == 0:
                widest += 22
            self.table.setColumnWidth(column, min(widest, 240 if column == 1 else 160))

    def refresh_theme(self):
        self.banner.refresh_theme()
        self.diagnostic_banner.refresh_theme()
        self.model.refresh()
        self.refresh()
