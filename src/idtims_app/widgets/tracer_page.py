"""Step 2, Tracer and weights.

A per-fraction table of sample weight (mg), spike weight (g), tracer, spike
type and collector, written straight back to the session's FractionTable.
Fill down (Ctrl+D) copies the top selected cell of each selected column to the
cells below it; "Apply to selected" sets one column of the selected rows to a
value. Confirmed database keys override the project version per fraction.
The right-hand card shows the
selected tracer's table read-only (values and 1σ %) and names its source file.
"""
from __future__ import annotations

from html import escape

from PySide6 import QtCore, QtGui, QtWidgets

from IDTIMS_UPbRPy.spikes import SPIKES
from idtims_app.services import TRACER_SETUP_COLUMNS, TRACER_VERSIONS
from idtims_app.ui.labels import ElidedLabel
from idtims_app.ui.panels import RememberedSplitter, WorkPanel, WorkArea, scroll_content
from idtims_app.ui.theme import NeumorphicFrame, active_theme, theme_color
from idtims_app.widgets.forms import format_number, note_label, read_only_table, table_item
from idtims_app.widgets.import_page import MessageBanner

COLUMNS = ["Fraction ID"] + TRACER_SETUP_COLUMNS + ["Spike Solution"]
HEADERS = {"Fraction ID": "Fraction", "Sample Weight (mg)": "Sample wt\n(mg)",
           "Spike Weight (g)": "Spike wt\n(g)", "Spike": "Tracer", "Spike Type": "Spike\ntype",
           "Collector": "Pb\ncollector", "Spike Solution": "Database spike\n(confirm below)"}
CHOICES = {"Spike": sorted(SPIKES), "Spike Type": ["535", "2535"], "Collector": ["F", "D"]}
CHOICE_TIPS = {"F": "Faraday", "D": "Daly", "535": "205Pb-233U-235U tracer",
               "2535": "202Pb-205Pb-233U-235U double spike"}


class TracerModel(QtCore.QAbstractTableModel):
    """The setup columns of the session's fractions."""

    edited = QtCore.Signal()
    editRejected = QtCore.Signal(str)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._wanted = {}
        self._rows = 0

    def refresh(self):
        self.beginResetModel()
        self._reload()
        self.endResetModel()

    def _reload(self):
        self._rows = self.session.row_count
        self._wanted = {}
        if self.session.has_table:
            for issue in self.session.issues():
                if issue.blocking:
                    self._wanted.setdefault(issue.fraction_id, []).append(issue)

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else self._rows

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if orientation == QtCore.Qt.Orientation.Vertical:
            return str(section + 1) if role == QtCore.Qt.ItemDataRole.DisplayRole else None
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return HEADERS[COLUMNS[section]]
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            return COLUMNS[section]
        return None

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and COLUMNS[index.column()] in TRACER_SETUP_COLUMNS:
            flags |= QtCore.Qt.ItemFlag.ItemIsEditable
        return flags

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, column = index.row(), COLUMNS[index.column()]
        fid = self.session.fraction_id(row)
        if role in (QtCore.Qt.ItemDataRole.DisplayRole, QtCore.Qt.ItemDataRole.EditRole):
            if column == "Spike Type" and role == QtCore.Qt.ItemDataRole.DisplayRole \
                    and fid in self.session.table.inferred_spike_types:
                return self.session.table.inferred_spike_types[fid] + " ?"
            return self.session.display_text(row, column)
        if role == QtCore.Qt.ItemDataRole.TextAlignmentRole:
            if column.endswith(")"):
                return int(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            return int(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        issues = [i for i in self._wanted.get(fid, []) if column in i.columns]
        if role == QtCore.Qt.ItemDataRole.BackgroundRole and issues:
            theme = active_theme()
            invalid = any(i.kind == "invalid_value" for i in issues)
            color = theme_color(theme.danger if invalid else theme.accent)
            color.setAlpha(46 if invalid else 30)
            return QtGui.QBrush(color)
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            lines = [escape(i.message) for i in issues]
            value = self.session.display_text(row, column)
            if value in CHOICE_TIPS and column in ("Spike Type", "Collector"):
                lines.insert(0, f"{escape(value)}: {CHOICE_TIPS[value]}")
            return "<p style='white-space:normal'>" + "<br>".join(lines) + "</p>" if lines \
                else None
        return None

    def setData(self, index, value, role=QtCore.Qt.ItemDataRole.EditRole):
        if not index.isValid() or role != QtCore.Qt.ItemDataRole.EditRole \
                or COLUMNS[index.column()] not in TRACER_SETUP_COLUMNS:
            return False
        error = self.session.set_value(index.row(), COLUMNS[index.column()], value)
        if error:
            self.editRejected.emit(error)
            return False
        self._reload()
        self.dataChanged.emit(self.index(index.row(), 0),
                              self.index(index.row(), self.columnCount() - 1))
        self.edited.emit()
        return True


class ChoiceDelegate(QtWidgets.QStyledItemDelegate):
    """A combo box editor for the tracer, spike type and collector columns."""

    def createEditor(self, parent, option, index):
        column = COLUMNS[index.column()]
        if column not in CHOICES:
            return super().createEditor(parent, option, index)
        combo = QtWidgets.QComboBox(parent)
        combo.addItem("")
        for value in CHOICES[column]:
            combo.addItem(value)
            if value in CHOICE_TIPS:
                combo.setItemData(combo.count() - 1, CHOICE_TIPS[value],
                                  QtCore.Qt.ItemDataRole.ToolTipRole)
        return combo

    def setEditorData(self, editor, index):
        if isinstance(editor, QtWidgets.QComboBox):
            text = index.model().data(index, QtCore.Qt.ItemDataRole.EditRole) or ""
            position = editor.findText(text)
            editor.setCurrentIndex(max(position, 0))
            editor.showPopup()
            return
        super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if isinstance(editor, QtWidgets.QComboBox):
            model.setData(index, editor.currentText(), QtCore.Qt.ItemDataRole.EditRole)
            return
        super().setModelData(editor, model, index)


class TracerPage(QtWidgets.QWidget):
    """Weights and tracer per fraction, the project tracer version, the tracer table."""

    changed = QtCore.Signal()
    fractionSelected = QtCore.Signal(str)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._tracer_choice = None  # tracer the user picked to view, if any
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(6)
        label = QtWidgets.QLabel("Tracer table version")
        bar.addWidget(label)
        self.version_combo = QtWidgets.QComboBox()
        self.version_combo.addItem("Default per tracer", None)
        for version in TRACER_VERSIONS:
            self.version_combo.addItem(version, version)
        self.version_combo.setToolTip("Default: v3 for ET2535, v1 for the others. A confirmed "
                                     "database spike key overrides this setting for its fraction.")
        self.version_combo.currentIndexChanged.connect(self._version_chosen)
        bar.addWidget(self.version_combo)
        bar.addSpacing(10)
        self.fill_button = QtWidgets.QPushButton("Fill down")
        self.fill_button.setToolTip("Copy the top selected cell of each selected column to the "
                                    "selected cells below it (Ctrl+D)")
        self.fill_button.clicked.connect(self.fill_down)
        bar.addWidget(self.fill_button)
        bar.addStretch(1)
        outer.addLayout(bar)

        apply_bar = QtWidgets.QHBoxLayout()
        apply_bar.setSpacing(6)
        apply_bar.addWidget(QtWidgets.QLabel("Set"))
        self.apply_column = QtWidgets.QComboBox()
        for column in TRACER_SETUP_COLUMNS:
            self.apply_column.addItem(HEADERS[column].replace("\n", " "), column)
        self.apply_column.currentIndexChanged.connect(self._apply_column_changed)
        apply_bar.addWidget(self.apply_column)
        apply_bar.addWidget(QtWidgets.QLabel("to"))
        self.apply_value = QtWidgets.QComboBox()
        self.apply_value.setEditable(True)
        self.apply_value.setMinimumWidth(90)
        self.apply_value.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        apply_bar.addWidget(self.apply_value)
        self.apply_button = QtWidgets.QPushButton("Apply to selected")
        self.apply_button.setToolTip("Set this column of every selected row (all rows when "
                                     "nothing is selected)")
        self.apply_button.clicked.connect(self.apply_to_selected)
        apply_bar.addWidget(self.apply_button)
        apply_bar.addStretch(1)
        outer.addLayout(apply_bar)
        self._apply_column_changed()

        self.banner = MessageBanner()
        outer.addWidget(self.banner)
        self.status = note_label()
        outer.addWidget(self.status)

        self.model = TracerModel(session, self)
        self.model.edited.connect(self._after_edit)
        self.model.editRejected.connect(self.banner.show_message)
        self.table = QtWidgets.QTableView()
        self.table.setModel(self.model)
        self.table.setItemDelegate(ChoiceDelegate(self.table))
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked
                                   | QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed
                                   | QtWidgets.QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.selectionModel().currentChanged.connect(self._current_changed)
        shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+D"), self.table)
        shortcut.activated.connect(self.fill_down)


        frame = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(8)
        self.tracer_combo = QtWidgets.QComboBox()
        self.tracer_combo.setToolTip("Tracer to show; the selected fraction's tracer is shown "
                                     "when you click a row")
        self.tracer_combo.currentIndexChanged.connect(self._show_tracer)
        self.tracer_combo.activated.connect(
            lambda _i: setattr(self, "_tracer_choice", self.tracer_combo.currentData()))
        head.addWidget(self.tracer_combo)
        self.tracer_source = ElidedLabel()
        self.tracer_source.setObjectName("SecondaryText")
        head.addWidget(self.tracer_source, 1)
        layout.addLayout(head)
        database_bar = QtWidgets.QHBoxLayout()
        self.database_spike_label = ElidedLabel()
        database_bar.addWidget(self.database_spike_label, 1)
        self.confirm_database_button = QtWidgets.QPushButton("Confirm database spike")
        self.confirm_database_button.clicked.connect(self._confirm_database_spike)
        database_bar.addWidget(self.confirm_database_button)
        layout.addLayout(database_bar)
        self.tracer_table = read_only_table([])
        self.tracer_table.setVerticalHeaderLabels(["Value", "± 1σ %"])
        self.tracer_table.verticalHeader().setVisible(True)
        layout.addWidget(self.tracer_table)
        self.table_card = WorkPanel("Fractions and weights", self.table, minimum=(320, 140))
        self.reference_card = WorkPanel("Tracer reference", scroll_content(frame), minimum=(250, 150))
        self.splitter = RememberedSplitter(QtCore.Qt.Orientation.Vertical, "tracer", (60, 40))
        self.splitter.addWidget(self.table_card)
        self.splitter.addWidget(self.reference_card)
        self.work_area = WorkArea(self.splitter, (self.table_card, self.reference_card))
        outer.addWidget(self.work_area, 1)
        self.refresh()

    # -- actions ---------------------------------------------------------------
    def _version_chosen(self):
        version = self.version_combo.currentData()
        if self.session.settings.spike_version != version:
            self.session.settings.spike_version = version
            self.session.settings_edited()
            self.refresh()
            self.changed.emit()

    def _apply_column_changed(self):
        column = self.apply_column.currentData()
        current = self.apply_value.currentText()
        self.apply_value.clear()
        self.apply_value.addItems(CHOICES.get(column, []))
        if column not in CHOICES:
            self.apply_value.setEditText(current if current.replace(".", "", 1).isdigit() else "")

    def selected_rows(self):
        return sorted({i.row() for i in self.table.selectionModel().selectedIndexes()})

    def apply_to_selected(self):
        if not self.session.has_table:
            return
        rows = self.selected_rows() or list(range(self.session.row_count))
        column = self.apply_column.currentData()
        errors = self.session.set_many(rows, column, self.apply_value.currentText())
        self._finish(errors, f"Set {column} for {len(rows)} fraction"
                             f"{'s' if len(rows) != 1 else ''}.")

    def fill_down(self):
        if not self.session.has_table:
            return
        by_column = {}
        for index in self.table.selectionModel().selectedIndexes():
            if COLUMNS[index.column()] in TRACER_SETUP_COLUMNS:
                by_column.setdefault(COLUMNS[index.column()], set()).add(index.row())
        targets = {c: r for c, r in by_column.items() if len(r) > 1}
        if not targets:
            self.banner.show_message("Select a value and the cells below it in the same column, "
                                     "then Fill down.", "note")
            return
        errors = []
        for column, rows in targets.items():
            errors += self.session.fill_down(rows, column)
        self._finish(errors, None)

    def _finish(self, errors, note):
        self.model.refresh()
        if errors:
            self.banner.show_message(" ".join(errors[:6]))
        elif note:
            self.banner.show_message(note, "note")
        else:
            self.banner.hide()
        self.refresh()
        self.changed.emit()

    def _after_edit(self):
        self.banner.hide()
        self.refresh()
        self.changed.emit()

    def _current_changed(self, current, _previous):
        if not current.isValid() or not self.session.has_table:
            return
        fid = self.session.fraction_id(current.row())
        self.fractionSelected.emit(fid)
        name = self.session.value(current.row(), "Spike")
        position = self.tracer_combo.findData(name)
        if position >= 0:
            self._tracer_choice = name
            self.tracer_combo.setCurrentIndex(position)
        self._show_tracer()

    def select_fraction(self, fid):
        row = self.session.row_of(fid) if self.session.has_table else -1
        if row >= 0:
            self.table.setCurrentIndex(self.model.index(row, 1))

    # -- refresh -------------------------------------------------------------------
    def refresh(self):
        session = self.session
        if self.model.rowCount() != session.row_count or \
                [self.model.data(self.model.index(r, 0)) for r in range(self.model.rowCount())] \
                != (session.table.fraction_ids if session.has_table else []):
            self.model.refresh()
        else:
            self.model._reload()
            if self.model.rowCount():
                self.model.dataChanged.emit(self.model.index(0, 0), self.model.index(
                    self.model.rowCount() - 1, self.model.columnCount() - 1))
        self.version_combo.blockSignals(True)
        self.version_combo.setCurrentIndex(max(0, self.version_combo.findData(
            session.settings.spike_version)))
        self.version_combo.blockSignals(False)
        self._fit_columns()
        # Tracers in use first, then the other known tracers.
        in_use = session.tracers_in_use()
        names = in_use + [n for n in sorted(SPIKES) if n not in in_use]
        current = self._tracer_choice if self._tracer_choice in names else (
            in_use[0] if in_use else None)
        self.tracer_combo.blockSignals(True)
        self.tracer_combo.clear()
        for name in names:
            self.tracer_combo.addItem(name + ("  (in use)" if name in in_use else ""), name)
        position = self.tracer_combo.findData(current)
        self.tracer_combo.setCurrentIndex(position if position >= 0 else 0)
        self.tracer_combo.blockSignals(False)
        self._show_tracer()
        self._update_status()

    def _update_status(self):
        session = self.session
        theme = active_theme()
        problems = session.tracer_problems()
        counts = session.summary()
        missing = sum(1 for i in session.issues() if i.kind in ("missing_setup", "invalid_value"))
        parts = [f"{counts['ready']} of {counts['fractions']} fractions ready."]
        tracers = [f"{n} {session.tracer_version(n)}" for n in session.tracers_in_use()
                   if session.tracer_file(n)]
        if tracers:
            parts.append("Project tracer defaults: " + ", ".join(tracers) + ".")
        if missing:
            parts.append(f"{missing} setup value{'s' if missing != 1 else ''} to enter or fix "
                         "(tinted cells; see Issues).")
        if problems:
            self.status.setText(" ".join(problems))
            self.status.setStyleSheet(f"color: {theme.danger};")
        else:
            self.status.setText(" ".join(parts))
            self.status.setStyleSheet("")

    def _fit_columns(self):
        metrics = self.table.fontMetrics()
        for section, column in enumerate(COLUMNS):
            header = max(metrics.horizontalAdvance(p) for p in HEADERS[column].split("\n"))
            widest = header + 24
            for row in range(min(self.session.row_count, 200)):
                widest = max(widest, metrics.horizontalAdvance(
                    self.session.display_text(row, column)) + 20)
            self.table.setColumnWidth(section, min(max(widest, 54), 140))

    def _show_tracer(self):
        name = self.tracer_combo.currentData()
        table = self.tracer_table
        key = None
        index = self.table.currentIndex()
        row = index.row() if index.isValid() else 0
        fid = self.session.fraction_id(row) if self.session.row_count else None
        proposed = self.session.value(row, "Spike Solution") if fid else None
        self.database_spike_label.setVisible(bool(proposed))
        self.confirm_database_button.setVisible(bool(proposed))
        self.confirm_database_button.setEnabled(False)
        if proposed:
            issues = self.session.table.database_spike_issues(fid)
            confirmed = self.session.table.database_spike_confirmed(fid)
            message = (f"{fid}: {proposed} confirmed; overrides project tracer version."
                       if confirmed and not issues else f"{fid}: " + " ".join(i.message for i in issues))
            self.database_spike_label.setText(message)
            self.database_spike_label.setToolTip(message + " To replace this proposal, clear Spike Solution in Import and choose a tracer.")
            self.confirm_database_button.setEnabled(any(i.kind == "unconfirmed_database_spike" for i in issues))
            from IDTIMS_UPbRPy.spike_registry import get_registry
            try:
                selected = get_registry().by_key(proposed)
            except (ValueError, OSError, KeyError, TypeError):
                table.setColumnCount(0)
                self.tracer_source.setText(message)
                self.tracer_source.setToolTip(message)
                return
            key = selected.key
            name = selected.spike_id
            self.tracer_source.setText(f"{key} · {selected.source} · {selected.status} · {selected.visibility}")
            self.tracer_source.setToolTip(f"{selected.citation.get('display', selected.source)}; {selected.locator}; {selected.notes}")
        if not name:
            table.setColumnCount(0)
            self.tracer_source.setText("")
            return
        version = self.session.tracer_version(name)
        source = self.session.tracer_file(name)
        if source is None and key is None:
            table.setColumnCount(0)
            self.tracer_source.setText(f"{name} has no version {version}; it has "
                                       + ", ".join(sorted(SPIKES[name])) + ".")
            return
        if key is None:
            self.tracer_source.setText(f"Version {version}, read-only, from {source}")
            self.tracer_source.setToolTip(f"IDTIMS_UPbRPy/spike_compositions/{source}; values with "
                                          "1σ in percent, as load_spike_data reads them")
        try:
            rows, notes, sources = self.session.tracer_table(name, spike_key=key, with_sources=True)
        except ValueError as error:
            table.setColumnCount(0)
            self.tracer_source.setText(str(error))
            self.tracer_source.setToolTip(str(error))
            return
        if notes:
            self.tracer_source.setToolTip(self.tracer_source.toolTip() + "\n\n" + "\n".join(notes))
        table.setColumnCount(len(rows))
        table.setRowCount(2)
        table.setVerticalHeaderLabels(["Value", "± 1σ %"])
        labels = []
        for c, (quantity, unit, value, error) in enumerate(rows):
            kind, _note = sources.get(quantity, (None, ""))
            labels.append(quantity + ("\n(mol/g)" if unit == "[mol/g]" else "")
                          + (f"\n({kind})" if kind else ""))
            table.setItem(0, c, table_item("–" if value != value else f"{value:.6g}",
                                           number=True, tooltip=format_number(value)))
            table.setItem(1, c, table_item("–" if error != error else f"{error:.4g}",
                                           number=True, tooltip=format_number(error)))
        table.setHorizontalHeaderLabels(labels)
        for c, (quantity, _unit, _value, _error) in enumerate(rows):
            _kind, note = sources.get(quantity, (None, ""))
            table.horizontalHeaderItem(c).setToolTip(note)
        table.resizeColumnsToContents()
        header = table.horizontalHeader().sizeHint().height()
        table.setFixedHeight(max(header, 44) + 2 * table.verticalHeader().defaultSectionSize()
                             + table.horizontalScrollBar().sizeHint().height()
                             + 2 * table.frameWidth() + 2)

    def _confirm_database_spike(self):
        index = self.table.currentIndex()
        row = index.row() if index.isValid() else 0
        try:
            self.session.confirm_database_spike(self.session.fraction_id(row))
        except ValueError as exc:
            self.banner.show_message(str(exc))
            return
        self.refresh()
        self.changed.emit()

    def refresh_theme(self):
        self.banner.refresh_theme()
        self.refresh()
