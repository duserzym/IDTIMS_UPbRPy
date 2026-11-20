"""Small building blocks for the settings pages: cards, number fields, inline problems.

A `NumberField` is bound to one attribute of one section of the session's
`ReductionSettings` (looked up on every read, so loading or resetting the
settings needs no rebinding). Problems from `ReductionSettings.problems()`
are matched to fields by their label and shown in red right under the field's
row; text that is not a number is refused in place and the stored value stays.
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtWidgets

from idtims_app.ui.theme import active_theme
from idtims_app.ui.panels import RememberedSplitter, WorkPanel, WorkArea, scroll_content


def format_number(value):
    """Shortest round-trip text of a number; empty for None/NaN."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    return repr(float(value))


def card(title, subtitle=None):
    """(frame, layout): a NeumorphicFrame with a title and optional muted line."""
    body = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(body)
    layout.setContentsMargins(8, 5, 8, 5)
    layout.setSpacing(6)
    layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
    frame = WorkPanel(title, scroll_content(body), minimum=(280, 120))
    if subtitle:
        note = QtWidgets.QLabel(subtitle)
        note.setObjectName("SecondaryText")
        note.setWordWrap(True)
        layout.addWidget(note)
    return frame, layout


def note_label(text=""):
    label = QtWidgets.QLabel(text)
    label.setObjectName("SecondaryText")
    label.setWordWrap(True)
    label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


class ProblemLabel(QtWidgets.QLabel):
    """A red, word-wrapped message shown under a field row; hidden when empty."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setObjectName("FieldProblem")
        self.hide()

    def set_messages(self, messages):
        theme = active_theme()
        self.setStyleSheet(f"color: {theme.danger}; font-size: 11px;")
        self.setText(" ".join(messages))
        self.setVisible(bool(messages))


class NumberField(QtWidgets.QLineEdit):
    """A line edit bound to `session.settings.<section>.<name>`."""

    edited = QtCore.Signal()

    def __init__(self, session, section, name, problem_label, *, width=132, optional=False,
                 parent=None):
        super().__init__(parent)
        self.session = session
        self.section = section
        self.name = name
        self.problem_label = problem_label
        self.optional = optional
        self.problems = None  # ProblemLabel, set by the page
        self.text_error = None
        # Wide enough for a full-precision float64 (17 significant digits).
        self.setFixedWidth(max(width, self.fontMetrics().horizontalAdvance("0." + "8" * 17) + 30))
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.setToolTip(problem_label)
        self.setAccessibleName(problem_label)
        self.editingFinished.connect(self.commit)

    def target(self):
        return getattr(self.session.settings, self.section)

    def stored(self):
        return getattr(self.target(), self.name)

    def load(self):
        """Show the stored value (unless the user is typing here)."""
        if self.hasFocus() and self.isModified():
            return
        self.setText(format_number(self.stored()))
        self.setModified(False)
        self.text_error = None

    def commit(self):
        """Store the typed number; refuse text that is not a finite number."""
        text = self.text().strip()
        if text == "":
            value = None
        else:
            try:
                value = float(text)
            except ValueError:
                value = math.nan
            if not math.isfinite(value):
                self.text_error = f"{self.problem_label}: {text!r} is not a number."
                self.edited.emit()
                return
        self.text_error = None
        if value != self.stored() or (value is None) != (self.stored() is None):
            setattr(self.target(), self.name, value)
            self.session.settings_edited()
        self.setModified(False)
        self.edited.emit()

    def set_invalid(self, invalid):
        if bool(self.property("invalid")) == bool(invalid):
            return
        self.setProperty("invalid", bool(invalid))
        theme = active_theme()
        self.setStyleSheet(f"border: 1px solid {theme.danger};" if invalid else "")


class SettingsGrid:
    """A QGridLayout of `label | value | ± | error | unit` rows with problem lines."""

    def __init__(self, page, headers=None):
        self.page = page
        self.layout = QtWidgets.QGridLayout()
        self.layout.setHorizontalSpacing(8)
        self.layout.setVerticalSpacing(4)
        self.layout.setColumnStretch(5, 1)
        self.row = 0
        if headers:
            for column, text in enumerate(headers):
                if text:
                    label = QtWidgets.QLabel(text)
                    label.setObjectName("SectionTitle")
                    alignment = QtCore.Qt.AlignmentFlag.AlignRight if column in (1, 3) else \
                        QtCore.Qt.AlignmentFlag.AlignLeft
                    self.layout.addWidget(label, self.row, column, alignment)
            self.row += 1

    def add(self, label, value_field=None, error_field=None, unit="", error_unit="",
            value_widget=None):
        """Add one row; returns the row's ProblemLabel."""
        text = QtWidgets.QLabel(label)
        self.layout.addWidget(text, self.row, 0)
        widget = value_widget if value_widget is not None else value_field
        if widget is not None:
            self.layout.addWidget(widget, self.row, 1)
        if error_field is not None:
            plus = QtWidgets.QLabel("±")
            plus.setObjectName("SecondaryText")
            self.layout.addWidget(plus, self.row, 2)
            self.layout.addWidget(error_field, self.row, 3)
        unit_text = " ".join(t for t in (unit, error_unit) if t)
        if unit_text:
            unit_label = QtWidgets.QLabel(unit_text)
            unit_label.setObjectName("SecondaryText")
            self.layout.addWidget(unit_label, self.row, 4)
        problems = ProblemLabel()
        self.layout.addWidget(problems, self.row + 1, 0, 1, 6)
        for field in (value_field, error_field):
            if field is not None:
                field.problems = problems
                self.page.register(field)
        self.row += 2
        return problems


class SettingsPage(QtWidgets.QWidget):
    """Base for the Fractionation, Blanks and Th pages: scrolled cards, bound fields."""

    changed = QtCore.Signal()
    key = ""
    sections = ()

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.fields = []
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(6)
        self.status = note_label()
        bar.addWidget(self.status, 1)
        self.reset_button = QtWidgets.QPushButton("Reset")
        self.reset_button.setToolTip("Restore this step's settings to the defaults")
        self.reset_button.clicked.connect(self.reset)
        bar.addWidget(self.reset_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        outer.addLayout(bar)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.viewport().setAutoFillBackground(False)
        self.body = QtWidgets.QWidget()
        self.body.setAutoFillBackground(False)
        self.content = QtWidgets.QVBoxLayout(self.body)
        self.content.setContentsMargins(2, 2, 8, 2)
        self.content.setSpacing(10)
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll, 1)

    def enable_panels(self):
        panels = self.body.findChildren(WorkPanel, options=QtCore.Qt.FindChildOption.FindDirectChildrenOnly)
        # U fractionation is explanatory text, rather than another work panel.
        notes = [label.text() for panel in panels if panel.title == "U fractionation"
                 for label in panel.findChildren(QtWidgets.QLabel) if label is not panel.label]
        notes += [label.text() for label in self.body.findChildren(
            QtWidgets.QLabel, options=QtCore.Qt.FindChildOption.FindDirectChildrenOnly)]
        panels = [panel for panel in panels if panel.title != "U fractionation"]
        if notes and panels:
            body = panels[-1].layout().itemAt(1).widget().widget()
            for text in notes:
                body.layout().addWidget(note_label(text))
        if len(panels) < 2:
            return
        self.layout().removeWidget(self.scroll)
        self.scroll.hide()
        self.splitter = RememberedSplitter(QtCore.Qt.Orientation.Vertical, self.key, (60, 40))
        for panel in panels:
            self.splitter.addWidget(panel)
        self.work_area = WorkArea(self.splitter, panels)
        self.layout().addWidget(self.work_area, 1)

    def register(self, field):
        self.fields.append(field)
        field.edited.connect(self._after_edit)

    def number(self, section, name, problem_label, **kwargs):
        return NumberField(self.session, section, name, problem_label, **kwargs)

    def _after_edit(self):
        self.refresh()
        self.changed.emit()

    def reset(self):
        for section in self.sections:
            self.session.reset_settings(section)
        self.refresh()
        self.changed.emit()

    def refresh(self):
        """Reload values and show the current problems next to their fields."""
        for field in self.fields:
            if field.text_error is None:  # keep refused text visible until corrected
                field.load()
        problems = self.session.section_problems(self.key)
        by_label = {}
        unmatched = []
        for message in problems:
            matches = [f for f in self.fields if message.startswith(f.problem_label + " ")]
            if not matches:
                unmatched.append(message)
                continue
            best = max(matches, key=lambda f: len(f.problem_label))
            by_label.setdefault(id(best), []).append(message)
        rows = {}
        for field in self.fields:
            messages = list(by_label.get(id(field), []))
            if field.text_error:
                messages.insert(0, field.text_error)
            field.set_invalid(bool(messages))
            if field.problems is not None:
                rows.setdefault(id(field.problems), (field.problems, []))[1].extend(messages)
        for problems_label, messages in rows.values():
            problems_label.set_messages(messages)
        self.unmatched_problems = unmatched
        self.refresh_extra()
        count = len(problems) + sum(1 for f in self.fields if f.text_error)
        theme = active_theme()
        if count:
            self.status.setText(f"{count} setting{'s' if count != 1 else ''} to fix before this "
                                "step is complete; each is marked in red below.")
            self.status.setStyleSheet(f"color: {theme.danger};")
        else:
            self.status.setText(self.complete_text())
            self.status.setStyleSheet("")

    def complete_text(self):
        return "These settings are valid."

    def refresh_extra(self):
        """Subclasses update read-only views here."""

    def refresh_theme(self):
        for field in self.fields:
            field.setProperty("invalid", None)
        self.refresh()


def read_only_table(columns):
    """A compact read-only QTableWidget with the given header labels."""
    table = QtWidgets.QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(24)
    table.setWordWrap(False)
    table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    return table


def table_item(text, *, number=False, tooltip=None):
    item = QtWidgets.QTableWidgetItem(text)
    if number:
        item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight
                              | QtCore.Qt.AlignmentFlag.AlignVCenter)
    if tooltip:
        item.setToolTip(tooltip)
    return item


def fit_table_height(table, max_rows=14):
    """Make a table as tall as its rows (up to max_rows), so cards do not scroll inside."""
    rows = min(table.rowCount(), max_rows)
    if rows == table.rowCount():
        table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    header = max(table.horizontalHeader().sizeHint().height(), 30)
    if any("\n" in (table.horizontalHeaderItem(c).text() if table.horizontalHeaderItem(c)
                     else "") for c in range(table.columnCount())):
        header = max(header, 44)
    height = header + rows * table.verticalHeader().defaultSectionSize() + \
        2 * table.frameWidth() + 4
    width = sum(table.columnWidth(c) for c in range(table.columnCount()))
    if width > table.viewport().width() and table.isVisible():
        height += table.horizontalScrollBar().sizeHint().height()
    table.setFixedHeight(max(height, 40))


__all__ = ["format_number", "card", "note_label", "ProblemLabel", "NumberField", "SettingsGrid",
           "SettingsPage", "read_only_table", "table_item", "fit_table_height"]
