"""App settings panel for the shared, palette-based updater controls."""
from PySide6 import QtCore, QtGui, QtWidgets

from idtims_app.labupdate.qt import NotesLabel, release_notes_url
from idtims_app.labupdate.state import button_view


class UpdatesDialog(QtWidgets.QDialog):
    """Latest stable release, lab notes and automatic download preference."""

    def __init__(self, updater, parent=None):
        super().__init__(parent)
        self.updater = updater
        self.setWindowTitle("Update settings")
        self.resize(520, 360)
        self.setStyleSheet("""
            QDialog { background: palette(window); color: palette(window-text); }
            QLabel, QCheckBox { color: palette(window-text); }
            QPushButton { background: palette(button); color: palette(button-text); }
        """)
        layout = QtWidgets.QVBoxLayout(self)
        heading = QtWidgets.QLabel(f"{updater.config.app_name} v{updater.version}")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        self.status = QtWidgets.QLabel()
        self.details = QtWidgets.QLabel()
        for label in (self.status, self.details):
            label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            layout.addWidget(label)
        self.notes = NotesLabel()
        layout.addWidget(self.notes)
        self.notes_link = QtWidgets.QLabel('<a href="release">Release notes</a>')
        self.notes_link.linkActivated.connect(lambda _: QtGui.QDesktopServices.openUrl(
            QtCore.QUrl(release_notes_url(updater))))
        layout.addWidget(self.notes_link)
        row = QtWidgets.QHBoxLayout()
        self.check_button = QtWidgets.QPushButton("Check now")
        self.check_button.clicked.connect(lambda: updater.check(manual=True))
        self.action = QtWidgets.QPushButton()
        self.action.clicked.connect(self._act)
        row.addWidget(self.check_button)
        row.addWidget(self.action)
        row.addStretch()
        layout.addLayout(row)
        self.auto = QtWidgets.QCheckBox("Download updates automatically")
        self.auto.setChecked(updater.auto_download)
        self.auto.toggled.connect(updater.set_auto_download)
        layout.addWidget(self.auto)
        layout.addStretch()
        close = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.hide)
        layout.addWidget(close)
        updater.stateChanged.connect(self._changed)
        self._changed(updater.state)

    def _changed(self, state):
        view = button_view(state, self.updater.version, self.updater.auto_download)
        self.status.setText(view.text)
        raw = " ".join(state.message.split())
        self.details.setText("Details: " + (raw[:119] + "…" if len(raw) > 120 else raw))
        self.details.setVisible(state.status == "error" and bool(raw))
        self.notes.setText(getattr(state.info, "notes", "")
                           if state.status in {"available", "ready"} else "")
        self.notes.setVisible(bool(self.notes.text()))
        self.notes_link.setVisible(state.status in {"available", "ready"})
        self.check_button.setEnabled(not view.busy)
        self.action.setVisible(view.action is not None)
        self.action.setText({"download": "Download", "restart": "Restart to update",
                             "page": "Download page"}.get(view.action, ""))
        blocker = QtCore.QSignalBlocker(self.auto)
        self.auto.setChecked(self.updater.auto_download)
        del blocker

    def _act(self):
        action = button_view(self.updater.state, self.updater.version,
                             self.updater.auto_download).action
        if action == "download":
            self.updater.download()
        elif action == "restart":
            self.updater.install()
        elif action == "page":
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(self.updater.config.download_page))
