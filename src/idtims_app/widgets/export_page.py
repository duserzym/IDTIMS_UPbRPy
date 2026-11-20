"""Step 8: engine BSU table preview, settings-specific notes and save actions."""
import html

from PySide6 import QtCore, QtWidgets
from IDTIMS_UPbRPy import export
from idtims_app import reporting
from idtims_app.ui.panels import RememberedSplitter, WorkPanel, WorkArea
from idtims_app.widgets.import_page import MessageBanner


class ExportPage(QtWidgets.QWidget):
    changed = QtCore.Signal()

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._th_default = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.banner = MessageBanner()
        layout.addWidget(self.banner)
        options = QtWidgets.QHBoxLayout()
        self.th_check = QtWidgets.QCheckBox("Th-corrected dates and ratios")
        self.discordance_check = QtWidgets.QCheckBox("% discordance")
        self.off_check = QtWidgets.QCheckBox("Include switched off")
        for check in (self.th_check, self.discordance_check, self.off_check):
            options.addWidget(check)
            check.toggled.connect(self.refresh)
        options.addStretch(1)
        layout.addLayout(options)
        self.caption = QtWidgets.QLabel()
        self.caption.setObjectName("SecondaryText")
        layout.addWidget(self.caption)
        self.preview = QtWidgets.QTableWidget()
        self.preview.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.preview.verticalHeader().hide()
        self.preview.horizontalHeader().hide()
        self.preview.setMinimumHeight(130)
        self.preview.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,
                                   QtWidgets.QSizePolicy.Policy.Expanding)
        self.notes_view = QtWidgets.QTextBrowser()
        self.notes_view.setOpenExternalLinks(False)
        self.notes_view.setMinimumHeight(90)
        self.notes_view.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,
                                     QtWidgets.QSizePolicy.Policy.Expanding)
        self.preview_card = WorkPanel("BSU table preview", self.preview, minimum=(300, 160))
        self.notes_card = WorkPanel("Footnotes · settings in use", self.notes_view, minimum=(250, 120))
        self.splitter = RememberedSplitter(QtCore.Qt.Orientation.Vertical, "export", (60, 40))
        self.splitter.addWidget(self.preview_card)
        self.splitter.addWidget(self.notes_card)
        self.work_area = WorkArea(self.splitter, (self.preview_card, self.notes_card))
        layout.addWidget(self.work_area, 1)
        buttons = QtWidgets.QGridLayout()
        for index, (title, kind) in enumerate((("Save BSU table… CSV", "bsu_csv"),
                                               ("Save BSU table… XLSX", "bsu_xlsx"),
                                               ("Save full table…", "full"),
                                               ("Save fractions CSV…", "fractions"))):
            button = QtWidgets.QPushButton(title)
            button.clicked.connect(lambda _=False, k=kind: self.choose_save(k))
            buttons.addWidget(button, index // 2, index % 2)
        layout.addLayout(buttons)

    def options(self):
        return dict(th_corrected=self.th_check.isChecked(),
                    discordance=self.discordance_check.isChecked(),
                    include_off=self.off_check.isChecked())

    def refresh(self, *_):
        default = self.session.th_correction_applied
        if default != self._th_default:
            self._th_default = default
            self.th_check.blockSignals(True)
            self.th_check.setChecked(default)
            self.th_check.blockSignals(False)
        self.th_check.setEnabled(default)
        if not self.session.reduction_current:
            self.preview.clear()
            self.preview.setRowCount(0)
            self.notes_view.clear()
            self.caption.setText("Reduce the current inputs to preview the BSU table.")
            return
        self.table, self.notes = reporting.bsu(self.session, **self.options())
        grouped = export.with_groups(self.table)
        self.caption.setText(f"BSU data table · {len(self.table)} fractions · 2σ uncertainties · "
                             "scroll horizontally for all columns")
        preview = self.preview
        preview.clearSpans()
        preview.setRowCount(len(self.table) + 2)
        preview.setColumnCount(len(self.table.columns))
        preview.clearContents()
        start = 0
        columns = list(grouped.columns)
        for col, (group, label, note) in enumerate(columns):
            if col == 0 or group != columns[col - 1][0]:
                start = col
                item = QtWidgets.QTableWidgetItem(group)
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                preview.setItem(0, col, item)
            if col == len(columns) - 1 or group != columns[col + 1][0]:
                if col > start:
                    preview.setSpan(0, start, 1, col - start + 1)
            header = QtWidgets.QTableWidgetItem(label + (f" ({note})" if note else ""))
            header.setToolTip(str(self.table.columns[col]))
            preview.setItem(1, col, header)
            preview.setColumnWidth(col, max(90, min(115, len(label) * 7)))
        for row, values in enumerate(self.table.itertuples(index=False, name=None), 2):
            for col, value in enumerate(values):
                text = f"{value:.5g}" if isinstance(value, float) else str(value)
                item = QtWidgets.QTableWidgetItem(text)
                item.setToolTip(repr(value))
                preview.setItem(row, col, item)
        preview.setRowHeight(0, 28)
        preview.setRowHeight(1, 44)
        for row in range(2, preview.rowCount()):
            preview.setRowHeight(row, 25)
        self.notes_view.setHtml("<div style='font-size:11px'>" + "".join(
            f"<p style='margin:3px 0'><b>({html.escape(letter)})</b> {html.escape(text)}</p>"
            for letter, text in self.notes) + "</div>")

    def save_to(self, path, kind):
        try:
            reporting.save(self.session, path, kind, **self.options())
        except (OSError, ValueError, ImportError) as exc:
            self.banner.show_message(f"Could not save: {exc}")
            return False
        self.banner.show_message(f"Saved {path}", "note")
        self.changed.emit()
        return True

    def choose_save(self, kind):
        extension = "xlsx" if kind == "bsu_xlsx" else "csv"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save table", f"{kind}.{extension}", f"{extension.upper()} (*.{extension})")
        if path:
            self.save_to(path, kind)

    def refresh_theme(self):
        self.banner.refresh_theme()
