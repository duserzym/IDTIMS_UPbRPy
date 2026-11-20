"""The editable fraction table: a Qt model over `services.Session` and its view.

Identity and setup cells are always editable; ratio cells only when the
session allows it (new tables, or "Edit ratios"). Fractions failing the
linked-error check carry a red marker on their Fraction ID, the failing error
cells are tinted, and the tooltip gives the identity, the reported errors and
the allowed interval. Cells a fraction still needs are tinted in the accent
colour. Ctrl+V pastes a tab-separated block from the selected cell; Ctrl+C
copies the selection as tab-separated text.
"""
from __future__ import annotations

from html import escape

from PySide6 import QtCore, QtGui, QtWidgets

from IDTIMS_UPbRPy.fractions import (OXIDE_FORMULA, OXIDE_FORMULAS, MEAN_STATISTIC_COLUMNS,
                                     MEAN_STATISTICS)
from idtims_app.services import is_numeric_column, is_ratio_column
from idtims_app.ui.tables import FrozenColumnsView
from idtims_app.ui.theme import active_theme, theme_color

QUALITY_ROLE = int(QtCore.Qt.ItemDataRole.UserRole) + 1
"""Data role: True on cells of a fraction that fails the linked-error check."""
ISSUES_ROLE = int(QtCore.Qt.ItemDataRole.UserRole) + 2
"""Data role: list of issue messages for the row (Fraction ID column)."""

SHORT_HEADERS = {
    "Fraction UID": "Fraction\nUID", "Database Server": "Database\nserver",
    "Database Read At": "Database\nread at", "Capsule Set": "Capsule\nset",
    "Source Grain UID": "Source grain\nUID", "Source Spot UID": "Source spot\nUID",
    "Source Fragment Note": "Source fragment\nnote", "Chemistry Batch UID": "Chemistry batch\nUID",
    "Chemical Abrasion": "Chemical\nabrasion", "Chemistry Steps": "Chemistry\nsteps",
    "Spike Solution": "Database spike\nsolution", "Spike Version UID": "Spike version\nUID",
    "Annealing Temperature (°C)": "Annealing\n°C", "Annealing Duration (h)": "Annealing\nh",
    "Chemical Abrasion Temperature (°C)": "Chemical abrasion\n°C",
    "Chemical Abrasion Duration (h)": "Chemical abrasion\nh",
    "Source Mount": "Source\nmount", "Source Grain": "Source\ngrain",
    "Source Spot": "Source\nspot", "Sample Weight (mg)": "Sample wt\n(mg)",
    "Spike Weight (g)": "Spike wt\n(g)", "Spike Type": "Spike\ntype",
    "U Oxide 18O/16O": "U oxide\n18O/16O", "Pb Collector Detail": "Pb collector\ndetail",
    "U Oxide Formula": "U oxide\nformula",
    "Pb Mean Statistic": "Pb mean\nstatistic", "U Mean Statistic": "U mean\nstatistic",
    "Pb Method": "Pb\nmethod", "U Method": "U\nmethod",
}


def header_label(column):
    """Two-line header text for a contract column."""
    if column in SHORT_HEADERS:
        return SHORT_HEADERS[column]
    if column.endswith(" Mean"):
        return column[:-5] + "\nmean"
    if column.endswith(" % Standard Error"):
        return column[:-17] + "\n±1σ %"
    if column.startswith("rho "):
        return "ρ\n" + column[4:]
    return column


def marker_icon(color, glyph):
    """A small round badge with a one-character glyph, for the Fraction ID cell."""
    size = 16
    image = QtGui.QImage(size * 2, size * 2, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(2.0)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(QtGui.QColor(color))
    painter.drawEllipse(QtCore.QRectF(1.5, 1.5, size - 3, size - 3))
    painter.setPen(QtGui.QColor("#ffffff"))
    font = QtGui.QFont()
    font.setPixelSize(11)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(QtCore.QRectF(0, 0, size, size), QtCore.Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()
    return QtGui.QIcon(QtGui.QPixmap.fromImage(image))


class FractionTableModel(QtCore.QAbstractTableModel):
    """Table model over the session's fraction frame (contract column names)."""

    edited = QtCore.Signal()
    editRejected = QtCore.Signal(str)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._columns = []
        self._issues = {}
        self._quality = {}
        self._icons = {}

    # -- caches --------------------------------------------------------------
    def refresh(self):
        """Re-read columns, issues and linked-error failures after any change."""
        self.beginResetModel()
        self._reload()
        self.endResetModel()

    def refresh_data(self):
        """Re-read issues and values without resetting the view (same shape)."""
        if self.session.display_columns() != self._columns or \
                self.session.row_count != self.rowCount():
            self.refresh()
            return
        self._reload()
        if self.rowCount() and self.columnCount():
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(self.rowCount() - 1, self.columnCount() - 1))

    def _reload(self):
        session = self.session
        self._columns = session.display_columns()
        self._issues, self._quality = {}, {}
        if session.has_table:
            for issue in session.issues():
                self._issues.setdefault(issue.fraction_id, []).append(issue)
            for failure in session.quality_failures():
                self._quality.setdefault(failure.fraction_id, []).append(failure)
        theme = active_theme()
        self._icons = {"quality": marker_icon(theme_color(theme.danger), "!"),
                       "input": marker_icon(theme_color(theme.accent), "i")}

    @property
    def columns(self):
        return list(self._columns)

    # -- Qt model API ----------------------------------------------------------
    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else self.session.row_count

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self._columns)

    def headerData(self, section, orientation, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if orientation == QtCore.Qt.Orientation.Vertical:
            return str(section + 1) if role == QtCore.Qt.ItemDataRole.DisplayRole else None
        if section >= len(self._columns):
            return None
        column = self._columns[section]
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return header_label(column)
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            note = "" if self.session.is_editable(column) else (
                " (read-only: turn on Edit ratios to change measured ratios)")
            return column + note
        return None

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and self.session.is_editable(self._columns[index.column()]):
            flags |= QtCore.Qt.ItemFlag.ItemIsEditable
        return flags

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, column = index.row(), self._columns[index.column()]
        fid = self.session.fraction_id(row)
        if role in (QtCore.Qt.ItemDataRole.DisplayRole, QtCore.Qt.ItemDataRole.EditRole):
            text = self.session.display_text(row, column)
            if (role == QtCore.Qt.ItemDataRole.DisplayRole and not text
                    and column in MEAN_STATISTIC_COLUMNS):
                return "arithmetic"
            return text
        if role == QtCore.Qt.ItemDataRole.TextAlignmentRole:
            if is_numeric_column(column):
                return int(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            return int(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        failures = self._quality.get(fid, [])
        issues = self._issues.get(fid, [])
        if role == QUALITY_ROLE:
            return bool(failures)
        if role == ISSUES_ROLE:
            return [i.message for i in issues] + [f.reason for f in failures]
        bad_cells = {c for f in failures for c in f.columns}
        wanted = {c for i in issues if i.blocking or i.kind == "missing_oxide" for c in i.columns}
        if role == QtCore.Qt.ItemDataRole.DecorationRole and column == "Fraction ID":
            if failures:
                return self._icons["quality"]
            if wanted or any(i.kind == "unconfirmed_spike_type" for i in issues):
                return self._icons["input"]
            return None
        if role == QtCore.Qt.ItemDataRole.BackgroundRole:
            theme = active_theme()
            if column in bad_cells:
                color = theme_color(theme.danger)
                color.setAlpha(46)
                return QtGui.QBrush(color)
            if column in wanted:
                return QtGui.QBrush(theme_color(theme.accent_soft))
            return None
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            lines = []
            if column == "Fraction ID":
                if failures:
                    lines.append("<b>Linked-error check failed</b>")
                    lines += [escape(f.reason) for f in failures]
                lines += [escape(i.message) for i in issues]
                if not lines:
                    lines.append(f"{escape(fid)}: no issues.")
            else:
                lines += [escape(f.reason) for f in failures if column in f.columns]
                lines += [escape(i.message) for i in issues if column in i.columns]
                if column in MEAN_STATISTIC_COLUMNS and not self.session.display_text(row, column):
                    lines.append("Missing statistic: arithmetic (legacy Tripoli / BSU default).")
            return "<p style='white-space:normal'>" + "<br>".join(lines) + "</p>" if lines else None
        return None

    def setData(self, index, value, role=QtCore.Qt.ItemDataRole.EditRole):
        if not index.isValid() or role != QtCore.Qt.ItemDataRole.EditRole:
            return False
        column = self._columns[index.column()]
        error = self.session.set_value(index.row(), column, value)
        if error:
            self.editRejected.emit(error)
            return False
        self._reload()
        self.dataChanged.emit(self.index(index.row(), 0),
                              self.index(index.row(), self.columnCount() - 1))
        self.edited.emit()
        return True


class ProvenanceDelegate(QtWidgets.QStyledItemDelegate):
    """Contract choices for formula and statistics; other cells keep text editors."""

    def createEditor(self, parent, option, index):
        column = index.model().columns[index.column()]
        choices = OXIDE_FORMULAS if column == OXIDE_FORMULA else (
            MEAN_STATISTICS if column in MEAN_STATISTIC_COLUMNS else None)
        if choices is None:
            return super().createEditor(parent, option, index)
        editor = QtWidgets.QComboBox(parent)
        editor.addItems(["", *choices])
        return editor

    def setEditorData(self, editor, index):
        if isinstance(editor, QtWidgets.QComboBox):
            editor.setCurrentIndex(max(0, editor.findText(index.data(QtCore.Qt.ItemDataRole.EditRole))))
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if isinstance(editor, QtWidgets.QComboBox):
            model.setData(index, editor.currentText())
        else:
            super().setModelData(editor, model, index)


class FractionTableView(QtWidgets.QTableView):
    """The fraction table with a frozen Fraction ID column, paste and copy."""

    pasteRequested = QtCore.Signal(int, int, str)

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.setModel(model)
        self.setItemDelegate(ProvenanceDelegate(self))
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked
                             | QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed
                             | QtWidgets.QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.horizontalHeader().setMinimumSectionSize(48)
        self.verticalHeader().setDefaultSectionSize(26)
        self.verticalHeader().setMinimumWidth(28)
        self.setIconSize(QtCore.QSize(14, 14))
        self.frozen = FrozenColumnsView(self, ("Fraction ID",))
        # Studio's overlay is read-only and sortable; here the id is editable
        # in place and the order is the table's own.
        self.frozen.setEditTriggers(self.editTriggers())
        self.frozen.setSortingEnabled(False)
        self.frozen.setIconSize(self.iconSize())
        self.frozen.verticalHeader().setDefaultSectionSize(26)
        self.refresh_theme()
        model.modelReset.connect(self.fit_columns)
        model.edited.connect(self.fit_columns)

    def refresh_theme(self):
        """Restyle the overlay for the current theme; no padding so rows line up."""
        theme = active_theme()
        self.setStyleSheet("QTableView { padding: 0px; }")
        self.frozen.setStyleSheet(
            f"QTableView#FrozenColumns {{ border: none; padding: 0px; border-right: 1px solid "
            f"{theme.input_border}; background: {theme.surface}; }}")

    def fit_columns(self):
        """Size columns to their content within sensible bounds."""
        model = self.model()
        metrics = self.fontMetrics()
        for section in range(model.columnCount()):
            column = model.columns[section]
            header = max(metrics.horizontalAdvance(part) for part in
                         str(model.headerData(section, QtCore.Qt.Orientation.Horizontal)).split("\n"))
            widest = header + 22
            for row in range(min(model.rowCount(), 200)):
                text = model.session.display_text(row, column)
                widest = max(widest, metrics.horizontalAdvance(text) + 18)
            if column == "Fraction ID":
                widest += 22
            # Keep complete formula labels visible; the four provenance columns
            # are placed immediately after ID because setup would push them offscreen.
            limit = 210 if column == OXIDE_FORMULA else (150 if is_ratio_column(column) else 180)
            self.setColumnWidth(section, max(56, min(widest, limit)))
        self.frozen._refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.frozen.update_geometry()

    def updateGeometries(self):
        super().updateGeometries()
        if hasattr(self, "frozen"):
            # Two-line headers: keep the overlay's header as tall as the table's
            # so its rows line up.
            self.frozen.horizontalHeader().setFixedHeight(self.horizontalHeader().height())
            self.frozen.update_geometry()

    def keyPressEvent(self, event):
        if event.matches(QtGui.QKeySequence.StandardKey.Paste):
            self.paste_clipboard()
            return
        if event.matches(QtGui.QKeySequence.StandardKey.Copy):
            self.copy_selection()
            return
        super().keyPressEvent(event)

    def paste_clipboard(self):
        """Ask the page to paste the clipboard text at the current cell."""
        text = QtWidgets.QApplication.clipboard().text()
        if text:
            index = self.currentIndex()
            row = index.row() if index.isValid() else 0
            column = index.column() if index.isValid() else 0
            self.pasteRequested.emit(row, column, text)

    def copy_selection(self):
        """Copy the selected cells as tab-separated text."""
        indexes = self.selectionModel().selectedIndexes()
        if not indexes:
            return
        rows = sorted({i.row() for i in indexes})
        columns = sorted({i.column() for i in indexes})
        model = self.model()
        lines = ["\t".join(model.data(model.index(r, c)) or "" for c in columns) for r in rows]
        QtWidgets.QApplication.clipboard().setText("\n".join(lines))
