# Copied from UPbRPy Studio: GUI/widgets.py (class FrozenColumnsView) at
# Studio commit f8c561f, on 2026-11-14. Changes: extracted into its own module;
# imports point at idtims_app.ui.theme. The class body is unchanged; callers
# that need editing or no sorting adjust the view after construction.
"""A table overlay that keeps the first columns visible while the table scrolls."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from idtims_app.ui.theme import active_theme


class FrozenColumnsView(QtWidgets.QTableView):
    """Keeps a table's first columns (Include, sample, spot) visible while it scrolls.

    It shares the table's model and selection and sits over its left edge.
    """

    def __init__(self, table: QtWidgets.QTableView, frozen_names) -> None:
        super().__init__(table)
        self._table = table
        self._frozen_names = tuple(frozen_names)
        self.setObjectName("FrozenColumns")
        self.setModel(table.model())
        self.setSelectionModel(table.selectionModel())
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.verticalHeader().setVisible(False)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(table.verticalScrollMode())
        self.setSelectionBehavior(table.selectionBehavior())
        self.setSelectionMode(table.selectionMode())
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setSortingEnabled(True)
        self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Fixed)
        theme = active_theme()
        self.setStyleSheet(
            f"QTableView#FrozenColumns {{ border: none; border-right: 1px solid {theme.input_border}; "
            f"background: {theme.surface}; }}")
        self.viewport().setAutoFillBackground(True)
        # One-way: the table owns the scroll position; wheel events over the
        # frozen columns are passed to it.
        table.verticalScrollBar().valueChanged.connect(self._follow_table_scroll)
        table.verticalScrollBar().rangeChanged.connect(lambda *_args: self._follow_table_scroll())
        table.horizontalHeader().sectionResized.connect(self._refresh)
        table.horizontalHeader().sortIndicatorChanged.connect(
            lambda column, order: self.horizontalHeader().setSortIndicator(column, order))
        model = table.model()
        for signal in (model.modelReset, model.layoutChanged, model.columnsInserted, model.columnsRemoved):
            signal.connect(self._refresh)
        self.viewport().installEventFilter(self)
        self._refresh()

    def _follow_table_scroll(self, *_args) -> None:
        bar = self.verticalScrollBar()
        bar.setRange(self._table.verticalScrollBar().minimum(), self._table.verticalScrollBar().maximum())
        bar.setValue(self._table.verticalScrollBar().value())

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API
        QtWidgets.QApplication.sendEvent(self._table.viewport(), event)

    def frozen_columns(self) -> list[int]:
        model = self._table.model()
        names = [model.headerData(column, QtCore.Qt.Orientation.Horizontal) for column in range(model.columnCount())]
        count = 0
        for index, name in enumerate(names):
            if index == 0 and name in {"Include", "Shown"} or name in self._frozen_names:
                count = index + 1
            else:
                break
        return list(range(count))

    def frozen_width(self) -> int:
        return sum(self._table.columnWidth(column) for column in self.frozen_columns()
                   if not self._table.isColumnHidden(column))

    def _refresh(self, *_args) -> None:
        frozen = set(self.frozen_columns())
        for column in range(self.model().columnCount()):
            self.setColumnHidden(column, column not in frozen or self._table.isColumnHidden(column))
            if column in frozen:
                self.setColumnWidth(column, self._table.columnWidth(column))
        self.setVisible(bool(frozen))
        self.update_geometry()

    def update_geometry(self) -> None:
        table = self._table
        frame = table.frameWidth()
        left = table.verticalHeader().width() if table.verticalHeader().isVisible() else 0
        self.setGeometry(frame + left, frame, self.frozen_width() + 1,
                         table.viewport().height() + table.horizontalHeader().height())
        self._follow_table_scroll()


class FrozenDateTable(QtWidgets.QTableView):
    """Date table with shared selection, scroll, and frozen Fraction and On/off."""

    def setModel(self, model):
        super().setModel(model)
        self.frozen = FrozenColumnsView(self, ("Fraction", "On/off"))
        self.frozen.setSortingEnabled(False)
        self.frozen.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self.verticalHeader().sectionResized.connect(
            lambda row, _old, size: self.frozen.setRowHeight(row, size))

    def sync_frozen(self):
        self.frozen.setSelectionBehavior(self.selectionBehavior())
        self.frozen.setSelectionMode(self.selectionMode())
        self.frozen.setVerticalScrollMode(self.verticalScrollMode())
        self.frozen.verticalHeader().setDefaultSectionSize(self.verticalHeader().defaultSectionSize())
        self.frozen.horizontalHeader().setFixedHeight(self.horizontalHeader().height())
        self.frozen.horizontalHeader().setStretchLastSection(False)
        self.frozen.setIconSize(self.iconSize())
        self.frozen._refresh()
        self.frozen.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "frozen"):
            self.sync_frozen()

    def scrollTo(self, index, hint=QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible):
        if index.column() >= 2:
            super().scrollTo(index, hint)
        else:
            self.frozen.scrollTo(index, hint)
            self.verticalScrollBar().setValue(self.frozen.verticalScrollBar().value())
