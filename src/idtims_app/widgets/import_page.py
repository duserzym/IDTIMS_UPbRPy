"""Step 1, Import fractions: open, merge, type, paste, check and save.

Read errors and rejected edits are shown in a banner on this page, never in a
modal dialog. The page talks to `services.Session` and emits `changed` after
every change so the window can update the inspector and the step locks.
"""
from __future__ import annotations

import os

from PySide6 import QtCore, QtWidgets

from idtims_app.ui.labels import ElidedLabel
from idtims_app.ui.panels import RememberedSplitter, WorkPanel, WorkArea
from idtims_app.ui.theme import NeumorphicFrame, active_theme
from idtims_app.widgets.fraction_table import FractionTableModel, FractionTableView

FILE_FILTER = "Fraction CSV files (*.csv *.txt);;All files (*)"


class MessageBanner(QtWidgets.QFrame):
    """An inline message strip with a close button (error or note)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MessageBanner")
        self.kind = "error"
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 6, 6)
        layout.setSpacing(8)
        self.label = QtWidgets.QLabel()
        self.label.setObjectName("MessageText")
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.label, 1)
        close = QtWidgets.QToolButton()
        close.setText("×")
        close.setToolTip("Dismiss")
        close.setProperty("modeToggle", True)
        close.clicked.connect(self.hide)
        layout.addWidget(close, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        self.hide()

    def show_message(self, text, kind="error"):
        self.kind = kind
        self.label.setText(text)
        self.refresh_theme()
        self.show()

    def text(self):
        return self.label.text() if self.isVisible() else ""

    def refresh_theme(self):
        theme = active_theme()
        color = theme.danger if self.kind == "error" else theme.accent
        tint = "rgba(194,65,59,0.10)" if self.kind == "error" else theme.accent_soft
        self.setStyleSheet(
            f"QFrame#MessageBanner {{ background: {tint}; border: 1px solid {color}; "
            f"border-radius: 12px; }} QLabel#MessageText {{ color: {theme.text}; }}")


class ImportPage(QtWidgets.QWidget):
    """Import step: action bar, message banner, summary, empty state or table."""

    changed = QtCore.Signal()
    fractionSelected = QtCore.Signal(str)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(6)
        self.open_button = QtWidgets.QPushButton("Open files…")
        self.open_button.setProperty("accent", True)
        self.open_button.setToolTip("Open contract or legacy fraction CSVs; more files are "
                                    "merged by Fraction ID (Ctrl+O)")
        self.open_button.clicked.connect(self.choose_files)
        self.new_button = QtWidgets.QPushButton("New table")
        self.new_button.setToolTip("Start an empty table for typing and pasting (Ctrl+N)")
        self.new_button.clicked.connect(self.request_new_table)
        self.add_button = QtWidgets.QPushButton("Add row")
        self.add_button.setToolTip("Append an empty fraction row")
        self.add_button.clicked.connect(self.add_row)
        self.delete_button = QtWidgets.QPushButton("Delete rows")
        self.delete_button.setToolTip("Remove the rows of the selected cells")
        self.delete_button.clicked.connect(self.delete_selected_rows)
        self.save_button = QtWidgets.QPushButton("Save CSV…")
        self.save_button.setToolTip("Save the table as a contract CSV, idtims-fractions/1 (Ctrl+S)")
        self.save_button.clicked.connect(self.choose_save_path)
        self.ratio_check = QtWidgets.QCheckBox("Edit ratios")
        self.ratio_check.setToolTip("Allow editing the measured ratio cells (always on for a new "
                                    "table; off for opened files so measured values stay as read)")
        self.ratio_check.toggled.connect(self.set_ratios_editable)
        for widget in (self.open_button, self.new_button, self.add_button, self.delete_button,
                       self.save_button):
            bar.addWidget(widget)
        bar.addStretch(1)
        layout.addLayout(bar)

        self.banner = MessageBanner()
        layout.addWidget(self.banner)

        summary_row = QtWidgets.QHBoxLayout()
        summary_row.setSpacing(6)
        self.count_pill = QtWidgets.QLabel()
        self.count_pill.setObjectName("Pill")
        self.ready_pill = QtWidgets.QLabel()
        self.ready_pill.setObjectName("StatusPill")
        self.quality_pill = QtWidgets.QLabel()
        self.quality_pill.setObjectName("QualityPill")
        self.sources_label = ElidedLabel()
        self.sources_label.setObjectName("SecondaryText")
        for widget in (self.count_pill, self.ready_pill, self.quality_pill):
            summary_row.addWidget(widget)
        summary_row.addWidget(self.sources_label, 1)
        summary_row.addWidget(self.ratio_check)
        layout.addLayout(summary_row)

        self.stack = QtWidgets.QStackedWidget()
        self.stack.addWidget(self._build_empty_state())
        self.model = FractionTableModel(session, self)
        self.model.edited.connect(self._after_edit)
        self.model.editRejected.connect(lambda text: self.banner.show_message(text))
        self.table = FractionTableView(self.model)
        self.table.pasteRequested.connect(self.paste_text)
        self.table.selectionModel().currentChanged.connect(self._current_changed)
        self.stack.addWidget(self.table)
        self.table_card = WorkPanel("Fractions", self.stack, minimum=(360, 180))
        self.issues_content = QtWidgets.QWidget()
        issues_layout = QtWidgets.QVBoxLayout(self.issues_content)
        issues_layout.setContentsMargins(0, 0, 0, 0)
        self.issues_card = WorkPanel("Issues", self.issues_content, minimum=(250, 180))
        self.splitter = RememberedSplitter(QtCore.Qt.Orientation.Horizontal, "import", (74, 26))
        self.splitter.addWidget(self.table_card)
        self.splitter.addWidget(self.issues_card)
        self.work_area = WorkArea(self.splitter, (self.table_card, self.issues_card))
        layout.addWidget(self.work_area, 1)
        self.refresh()

    def _build_empty_state(self):
        holder = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(holder)
        outer.addStretch(1)
        card = NeumorphicFrame()
        card.setMaximumWidth(560)
        inner = QtWidgets.QVBoxLayout(card)
        inner.setContentsMargins(28, 24, 28, 24)
        inner.setSpacing(10)
        title = QtWidgets.QLabel("Open fraction files")
        title.setObjectName("HeroTitle")
        body = QtWidgets.QLabel(
            "Drop contract CSVs (idtims-fractions/1, from the raw-data app) or legacy Tripoli "
            "CSVs anywhere on this window, or open them here. Several files are merged by "
            "Fraction ID, so Pb-only and U-only files make complete fractions. To type or paste "
            "values from Tripoli, start a new table.")
        body.setObjectName("PanelBody")
        body.setWordWrap(True)
        buttons = QtWidgets.QHBoxLayout()
        open_button = QtWidgets.QPushButton("Open files…")
        open_button.setProperty("accent", True)
        open_button.clicked.connect(self.choose_files)
        new_button = QtWidgets.QPushButton("New table")
        new_button.clicked.connect(self.request_new_table)
        buttons.addWidget(open_button)
        buttons.addWidget(new_button)
        buttons.addStretch(1)
        inner.addWidget(title)
        inner.addWidget(body)
        inner.addLayout(buttons)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card, 4)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(2)
        return holder

    # -- actions ---------------------------------------------------------------
    def choose_files(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Open fraction files", "",
                                                          FILE_FILTER)
        if paths:
            self.open_paths(paths)

    def open_paths(self, paths):
        """Open and merge files; returns the error message shown, or None."""
        result = self.session.open_files(paths)
        if result.error:
            self.banner.show_message(result.error)
            return result.error
        self.banner.hide()
        self.model.refresh()
        self.refresh()
        self.changed.emit()
        return None

    def request_new_table(self):
        window = self.window()
        if hasattr(window, "new_project"):
            if not window.new_project():
                return
        self.new_table()

    def new_table(self):
        self.session.new_table()
        self.banner.hide()
        self.model.refresh()
        self.refresh()
        self.table.setCurrentIndex(self.model.index(0, 0))
        self.changed.emit()

    def add_row(self):
        if not self.session.has_table:
            self.new_table()
            return
        self.session.add_rows(1)
        self.model.refresh()
        self.refresh()
        self.changed.emit()

    def delete_selected_rows(self):
        rows = sorted({i.row() for i in self.table.selectionModel().selectedIndexes()})
        if not rows:
            self.banner.show_message("Select a cell in each row to delete.", "note")
            return
        self.session.delete_rows(rows)
        self.model.refresh()
        self.refresh()
        self.changed.emit()

    def set_ratios_editable(self, on):
        if self.session.ratios_editable != bool(on):
            self.session.ratios_editable = bool(on)
            self.model.refresh()

    def paste_text(self, row, column, text):
        """Paste a tab-separated block at (row, column) and report problems inline."""
        if not self.session.has_table:
            self.session.new_table(rows=0)
            row = column = 0
        result = self.session.paste(row, column, text)
        self.model.refresh()
        self.refresh()
        if result.errors:
            shown = result.errors[:6]
            more = len(result.errors) - len(shown)
            self.banner.show_message("Paste: " + " ".join(shown)
                                     + (f" ({more} more)" if more > 0 else ""))
        else:
            self.banner.hide()
        self.changed.emit()
        return result

    def choose_save_path(self):
        if not self.session.has_table:
            return
        start = self.session.saved_path or "fractions.fractions.csv"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save contract CSV", start,
                                                        "Contract CSV (*.csv)")
        if path:
            self.save_to(path)

    def save_to(self, path):
        """Write the contract CSV; errors go to the banner."""
        try:
            self.session.save(path)
        except OSError as exc:
            self.banner.show_message(f"Could not save {path}: {exc.strerror or exc}")
            return False
        self.banner.show_message(f"Saved {os.path.basename(path)} (contract idtims-fractions/1).",
                                 "note")
        self.changed.emit()
        return True

    # -- refresh -----------------------------------------------------------------
    def _after_edit(self):
        self.refresh()
        self.changed.emit()

    def _current_changed(self, current, _previous):
        if current.isValid() and self.session.has_table:
            self.fractionSelected.emit(self.session.fraction_id(current.row()))

    def select_fraction(self, fid):
        row = self.session.row_of(fid)
        if row >= 0:
            self.table.setCurrentIndex(self.model.index(row, 0))
            self.table.scrollTo(self.model.index(row, 0))

    def refresh(self):
        """Update the summary, buttons and which of empty state / table is shown."""
        session = self.session
        has = session.has_table
        self.stack.setCurrentIndex(1 if has else 0)
        for widget in (self.add_button, self.delete_button, self.save_button):
            widget.setEnabled(has)
        self.ratio_check.setVisible(has)
        self.ratio_check.blockSignals(True)
        self.ratio_check.setChecked(session.ratios_editable)
        self.ratio_check.blockSignals(False)
        counts = session.summary()
        visible = has and counts["fractions"] > 0
        self.count_pill.setText(f"{counts['fractions']} fractions")
        self.ready_pill.setText(f"{counts['ready']} ready")
        self.quality_pill.setText(f"{counts['quality']} failing linked-error check")
        theme = active_theme()
        self.quality_pill.setStyleSheet(
            f"padding: 4px 10px; border-radius: 10px; color: {theme.danger}; "
            "background: rgba(194,65,59,0.10);")
        for widget in (self.count_pill, self.ready_pill):
            widget.setVisible(visible)
        self.quality_pill.setVisible(visible and counts["quality"] > 0)
        if session.sources:
            self.sources_label.setText("From " + ", ".join(session.sources))
        elif session.manual and has:
            self.sources_label.setText("New table: type values or paste a tab-separated block "
                                       "(a header row maps columns by name)")
        else:
            self.sources_label.setText("")

    def refresh_theme(self):
        self.banner.refresh_theme()
        self.table.refresh_theme()
        self.model.refresh_data()
        self.refresh()
