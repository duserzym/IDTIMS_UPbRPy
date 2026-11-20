"""Workflow window with per-user panels and a contained issues inspector.

Import gives blocking issues a resizable work panel. Other pages give the
whole work area to their content and open issues in a contained right drawer.
The workflow rail starts expanded, auto-collapsing only below 1100 px unless
the viewer has chosen a mode. Expanded widths and explicit modes are saved
per user. Back and Next remain Ctrl+[ and Ctrl+].
"""
from __future__ import annotations

import os
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from PySide6 import QtCore, QtGui, QtWidgets

from idtims_app import branding, project, autosave
from idtims_app.services import Session
from idtims_app.steps import STEPS
from idtims_app.ui.busy_indicator import BusyIndicator
from idtims_app.ui.icon import build_app_icon, build_workflow_stage_icon
from idtims_app.ui.labels import ElidedLabel
from idtims_app.ui.panels import PanelShortcuts, WorkArea, reduced_motion
from idtims_app.ui.rail import WorkflowRailSplitter, _WorkflowRailDelegate
from idtims_app.ui.theme import (NeumorphicFrame, WallpaperWidget, active_theme, apply_theme,
                                 paint_wallpaper)
from idtims_app.widgets.import_page import ImportPage, MessageBanner
from idtims_app.widgets.issues_panel import IssuesPanel
from idtims_app.widgets.export_page import ExportPage
from idtims_app.widgets.reduce_page import ReducePage
from idtims_app.widgets.review_page import ReviewPage
from idtims_app.widgets.settings_pages import BlanksPage, FractionationPage, ThPage
from idtims_app.widgets.tracer_page import TracerPage

SETTINGS_FILTER = "Reduction settings (*.json);;All files (*)"

COMPACT_RAIL_BELOW = 1100
RAIL_MIN_WIDTH = 200
RAIL_MAX_WIDTH = 360
RAIL_COMPACT_WIDTH = 84
RAIL_MODE_KEY = "layout/rail_compact_v2"
RAIL_WIDTH_KEY = "layout/rail_width_v1"
MINIMUM_SIZE = QtCore.QSize(1000, 640)


def app_settings():
    """QSettings for this app; `IDTIMS_APP_SETTINGS` points tests at an ini file."""
    path = os.environ.get("IDTIMS_APP_SETTINGS")
    if path:
        return QtCore.QSettings(path, QtCore.QSettings.Format.IniFormat)
    return QtCore.QSettings(branding.ORGANISATION, branding.SLUG)


class PlaceholderPage(QtWidgets.QWidget):
    """A short page for a step that is not built yet."""

    def __init__(self, step, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addStretch(1)
        card = NeumorphicFrame()
        card.setMaximumWidth(520)
        inner = QtWidgets.QVBoxLayout(card)
        inner.setContentsMargins(26, 22, 26, 22)
        title = QtWidgets.QLabel(f"{step.title}: not built yet")
        title.setObjectName("WorkflowContextTitle")
        body = QtWidgets.QLabel(f"{step.summary} {step.hint} This step comes in a later "
                                "phase of the app (docs/APP_SPEC.md, section 5).")
        body.setObjectName("PanelBody")
        body.setWordWrap(True)
        inner.addWidget(title)
        inner.addWidget(body)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card, 4)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(2)


class MainWindow(QtWidgets.QMainWindow):
    """The app window for one document (`services.Session`)."""

    autosaveFailed = QtCore.Signal(str)

    def __init__(self, session=None, *, theme_mode="light", app_icon=None, confirm_close=True):
        super().__init__()
        self.session = session or Session()
        self.theme_mode = theme_mode
        self.confirm_close = confirm_close
        self._autosave_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="idtims-autosave")
        self._autosave_timer = QtCore.QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(2000)
        self._autosave_timer.timeout.connect(self.write_autosave)
        self._last_scientific = self.session.scientific_project_fingerprint()
        self._recovery_document = None
        self.drawer = None
        self._attention = set()
        self._rail_compact = None
        # v1 could reflect the old forced-compact laptop layout, not a choice.
        settings = app_settings()
        saved_rail = settings.value(RAIL_MODE_KEY)
        self._user_rail_compact = (str(saved_rail).lower() in {"true", "1"}
                                   if saved_rail is not None else None)
        try:
            width = int(settings.value(RAIL_WIDTH_KEY))
        except (TypeError, ValueError):
            width = None
        # None keeps the default responsive to the current rail font.
        self._expanded_rail_width = (max(RAIL_MIN_WIDTH, min(RAIL_MAX_WIDTH, width))
                                     if width is not None else None)
        self.setWindowTitle(f"{branding.DISPLAY_NAME}[*]")
        self.setWindowIcon(app_icon if app_icon is not None else build_app_icon())
        self.setMinimumSize(MINIMUM_SIZE)
        self.setAcceptDrops(True)
        # The window paints one wallpaper under the menu bar, panels and status bar.
        self.setProperty("wallpaperRoot", True)
        self._build_ui()
        self._build_menus()
        self.panel_shortcuts = PanelShortcuts(self)
        self.autosaveFailed.connect(self._autosave_failed)
        self.sync_steps()
        self.workflow_list.setCurrentRow(0)
        self.on_session_changed()
        self.drawer = QtWidgets.QFrame(self.main_panel)
        self.drawer.setObjectName("ReviewIssuesDrawer")
        layout = QtWidgets.QVBoxLayout(self.drawer)
        layout.setContentsMargins(6, 6, 6, 6)
        close = QtWidgets.QToolButton()
        close.setText("Close issues ×")
        close.clicked.connect(lambda: self.set_inspector_visible(False))
        layout.addWidget(close, 0, QtCore.Qt.AlignmentFlag.AlignRight)
        self.drawer.hide()
        self._sync_issues_shell()


    # -- construction --------------------------------------------------------
    def _build_ui(self):
        central = WallpaperWidget()
        outer = QtWidgets.QHBoxLayout(central)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)
        self.splitter = WorkflowRailSplitter()
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(10)
        self.splitter.setOpaqueResize(True)
        self.rail = self._build_rail()
        self.main_panel = self._build_main_column()
        self.inspector = QtWidgets.QWidget()
        self.inspector.setObjectName("Inspector")
        self.inspector.setMinimumWidth(250)
        inspector_layout = QtWidgets.QVBoxLayout(self.inspector)
        inspector_layout.setContentsMargins(0, 0, 0, 0)
        self.issues_panel = IssuesPanel(self.session)
        inspector_layout.addWidget(self.issues_panel)
        for panel in (self.rail, self.main_panel):
            self.splitter.addWidget(panel)
        for index in range(2):
            self.splitter.setCollapsible(index, False)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.splitterMoved.connect(self._rail_splitter_moved)
        self.splitter.resetRequested.connect(self._reset_rail_width)
        outer.addWidget(self.splitter, 1)
        self.setCentralWidget(central)

        self.busy = BusyIndicator()
        self.statusBar().addPermanentWidget(self.busy)
        self.status_label = ElidedLabel("No fractions loaded")
        self.status_label.setObjectName("SecondaryText")
        self.status_label.setMaximumWidth(900)
        self.status_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                                        QtWidgets.QSizePolicy.Policy.Fixed)
        self.statusBar().addPermanentWidget(self.status_label)

        self.issues_panel.confirmSpikeType.connect(self._confirm_spike_type)
        self.issues_panel.confirmNoOxide.connect(self._confirm_no_oxide)
        self.issues_panel.confirmAll.connect(self._confirm_all)
        self.issues_panel.fractionClicked.connect(self._select_fraction)
        self.import_page.changed.connect(self.on_session_changed)
        self.import_page.fractionSelected.connect(self.issues_panel.select)
        for page in self.step_pages[1:]:
            page.changed.connect(self.on_session_changed)
        self.tracer_page.fractionSelected.connect(self.issues_panel.select)
        self.reduce_page.busyStarted.connect(self.busy.start)
        self.reduce_page.busyProgress.connect(self.busy.set_progress)
        self.reduce_page.busyStopped.connect(self.busy.stop)

    def _build_rail(self):
        frame = NeumorphicFrame()
        frame.setObjectName("WorkflowRail")
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(6)
        brand = QtWidgets.QHBoxLayout()
        brand.setSpacing(8)
        icon = QtWidgets.QLabel()
        icon.setPixmap(self.windowIcon().pixmap(32, 32))
        icon.setFixedSize(32, 32)
        icon.setToolTip(branding.DISPLAY_NAME)
        self.rail_brand = ElidedLabel(branding.RAIL_NAME)
        self.rail_brand.setObjectName("RailBrand")
        self.rail_brand.setToolTip(branding.DISPLAY_NAME)
        brand.addWidget(icon)
        brand.addWidget(self.rail_brand, 1)
        layout.addLayout(brand)
        self.rail_section = ElidedLabel("Reduction workflow")
        self.rail_section.setObjectName("SectionTitle")
        layout.addWidget(self.rail_section)
        self.workflow_list = QtWidgets.QListWidget()
        self.workflow_list.setItemDelegate(_WorkflowRailDelegate(self.workflow_list))
        self.workflow_list.setObjectName("WorkflowStepRail")
        self.workflow_list.setIconSize(QtCore.QSize(24, 24))
        self.workflow_list.setWordWrap(False)
        self.workflow_list.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self.workflow_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.workflow_list.setSpacing(1)
        for step in STEPS:
            item = QtWidgets.QListWidgetItem(step.title)
            item.setToolTip(f"{step.title}: {step.summary}")
            item.setSizeHint(QtCore.QSize(0, 34))
            self.workflow_list.addItem(item)
        self.workflow_list.currentRowChanged.connect(self.on_step_changed)
        layout.addWidget(self.workflow_list, 1)
        self.rail_toggle = QtWidgets.QToolButton()
        self.rail_toggle.setProperty("modeToggle", True)
        self.rail_toggle.setToolTip("Collapse or expand the workflow rail")
        self.rail_toggle.clicked.connect(lambda: self.set_rail_compact(not self._rail_compact,
                                                                        user=True))
        layout.addWidget(self.rail_toggle, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        return frame

    def _build_main_column(self):
        frame = NeumorphicFrame()
        frame.setObjectName("MainColumn")
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(6)
        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(0)
        self.step_title = ElidedLabel()
        self.step_title.setObjectName("HeroTitle")
        self.step_summary = ElidedLabel()
        self.step_summary.setObjectName("SecondaryText")
        titles.addWidget(self.step_title)
        titles.addWidget(self.step_summary)
        header.addLayout(titles, 1)
        self.back_button = QtWidgets.QPushButton("Back")
        self.back_button.setToolTip("Previous step (Ctrl+[)")
        self.back_button.clicked.connect(lambda: self.go_to_step(-1))
        self.next_button = QtWidgets.QPushButton("Next")
        self.next_button.setProperty("accent", True)
        self.next_button.setToolTip("Next step (Ctrl+])")
        self.next_button.clicked.connect(lambda: self.go_to_step(1))
        self.inspector_toggle = QtWidgets.QToolButton()
        self.inspector_toggle.setText("Issues")
        self.inspector_toggle.setCheckable(True)
        self.inspector_toggle.setChecked(True)
        self.inspector_toggle.setToolTip("Show or hide the issues inspector (Ctrl+Alt+I)")
        self.inspector_toggle.toggled.connect(self.set_inspector_visible)
        for widget in (self.back_button, self.next_button, self.inspector_toggle):
            header.addWidget(widget, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.issue_notes = QtWidgets.QLabel()
        self.issue_notes.setObjectName("SecondaryText")
        self.issue_notes.hide()
        header.addWidget(self.issue_notes)
        layout.addLayout(header)
        self.window_banner = MessageBanner()
        layout.addWidget(self.window_banner)
        self.recovery_bar = QtWidgets.QWidget()
        recovery_layout = QtWidgets.QHBoxLayout(self.recovery_bar)
        recovery_layout.setContentsMargins(0, 0, 0, 0)
        recovery_label = QtWidgets.QLabel("Newer autosaved changes are available.")
        recovery_label.setWordWrap(True)
        recovery_layout.addWidget(recovery_label, 1)
        self.restore_button = QtWidgets.QPushButton("Restore")
        self.discard_button = QtWidgets.QPushButton("Discard")
        self.restore_button.clicked.connect(self.restore_autosave)
        self.discard_button.clicked.connect(self.discard_autosave)
        recovery_layout.addWidget(self.restore_button)
        recovery_layout.addWidget(self.discard_button)
        layout.addWidget(self.recovery_bar)
        self.recovery_bar.hide()
        self.pages = QtWidgets.QStackedWidget()
        self.import_page = ImportPage(self.session)
        self.tracer_page = TracerPage(self.session)
        self.fractionation_page = FractionationPage(self.session)
        self.blanks_page = BlanksPage(self.session)
        self.th_page = ThPage(self.session)
        self.reduce_page = ReducePage(self.session)
        self.review_page = ReviewPage(self.session)
        self.export_page = ExportPage(self.session)
        self.step_pages = [self.import_page, self.tracer_page, self.fractionation_page,
                           self.blanks_page, self.th_page, self.reduce_page, self.review_page, self.export_page]
        for page in self.step_pages:
            self.pages.addWidget(page)
        for step in STEPS[len(self.step_pages):]:
            self.pages.addWidget(PlaceholderPage(step))
        layout.addWidget(self.pages, 1)
        return frame

    def _build_menus(self):
        bar = self.menuBar()
        file_menu = bar.addMenu("File")
        for title, shortcut, handler in (
                ("New", QtGui.QKeySequence.StandardKey.New, self.new_project),
                ("Open…", QtGui.QKeySequence.StandardKey.Open, self.choose_open),
                ("Save", QtGui.QKeySequence.StandardKey.Save, self.save_project),
                ("Save As…", QtGui.QKeySequence.StandardKey.SaveAs, self.save_project_as)):
            action = file_menu.addAction(title)
            action.setShortcut(shortcut)
            action.triggered.connect(handler)
        file_menu.addSeparator()
        action = file_menu.addAction("Load Settings…")
        action.setToolTip("Read reduction settings (JSON) for steps 2 to 5")
        action.triggered.connect(self.choose_settings_to_load)
        action = file_menu.addAction("Save Settings…")
        action.triggered.connect(self.choose_settings_to_save)
        action = file_menu.addAction("Reset Settings")
        action.setToolTip("Restore every reduction setting to the defaults")
        action.triggered.connect(self.reset_settings)
        file_menu.addSeparator()
        action = file_menu.addAction("Quit")
        action.setShortcut(QtGui.QKeySequence.StandardKey.Quit)
        action.setMenuRole(QtGui.QAction.MenuRole.QuitRole)
        action.triggered.connect(self.close)

        view_menu = bar.addMenu("View")
        self.inspector_action = view_menu.addAction("Issues Inspector")
        self.inspector_action.setCheckable(True)
        self.inspector_action.setChecked(True)
        self.inspector_action.setShortcut(QtGui.QKeySequence("Ctrl+Alt+I"))
        self.inspector_action.toggled.connect(self.set_inspector_visible)
        self.rail_action = view_menu.addAction("Compact Workflow Rail")
        self.rail_action.setCheckable(True)
        self.rail_action.toggled.connect(lambda on: self.set_rail_compact(on, user=True))
        self.reset_layout_action = view_menu.addAction("Reset Layout")
        self.reset_layout_action.triggered.connect(self.reset_layout)
        appearance = view_menu.addMenu("Appearance")
        group = QtGui.QActionGroup(self)
        self.theme_actions = {}
        for mode, label in (("system", "System"), ("light", "Light"), ("dark", "Dark")):
            action = appearance.addAction(label)
            action.setCheckable(True)
            action.setChecked(mode == self.theme_mode)
            action.triggered.connect(lambda _c=False, m=mode: self.set_theme_mode(m))
            group.addAction(action)
            self.theme_actions[mode] = action

        workflow_menu = bar.addMenu("Workflow")
        self.back_action = workflow_menu.addAction("Previous Step")
        self.back_action.setShortcuts([QtGui.QKeySequence("Ctrl+["), QtGui.QKeySequence("Ctrl+Left")])
        self.back_action.triggered.connect(lambda: self.go_to_step(-1))
        self.next_action = workflow_menu.addAction("Next Step")
        self.next_action.setShortcuts([QtGui.QKeySequence("Ctrl+]"), QtGui.QKeySequence("Ctrl+Right")])
        self.next_action.triggered.connect(lambda: self.go_to_step(1))

    # -- documents -------------------------------------------------------------
    def choose_open(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Open project or fraction files", "",
            f"Projects and fractions (*{branding.PROJECT_EXTENSION} *.csv);;All files (*)")
        if paths:
            self.open_paths(paths)

    def open_paths(self, paths):
        """Route by content, leaving the current session intact on read errors."""
        if not paths:
            return None
        try:
            objects = []
            for path in paths:
                text = Path(path).read_text(encoding="utf-8-sig")
                if text.lstrip().startswith("{"):
                    objects.append((path, json.loads(text)))
            if objects:
                if len(paths) != 1:
                    raise ValueError("Open one project at a time, separately from fraction CSVs.")
                path, data = objects[0]
                restored = project.restore(data)
                if not self.request_save_changes():
                    return "Opening cancelled."
                # Save in the guard may have just updated this very same file.
                current_data = project.read(path)
                if current_data != data:
                    restored = project.restore(current_data)
                restored.project_path = str(Path(path).expanduser().resolve())
                self._install_session(restored)
                try:
                    self._recovery_document = autosave.candidate(self.session)
                except (OSError, ValueError):
                    self.window_banner.show_message("The autosave could not be read; the saved project was opened.", "note")
                self.recovery_bar.setVisible(self._recovery_document is not None)
                return None
            self.busy.start("Reading fractions")
            try:
                error = self.import_page.open_paths(paths)
            finally:
                self.busy.stop()
            if error is None:
                self.workflow_list.setCurrentRow(0)
            return error
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.window_banner.show_message(str(exc))
            return str(exc)

    def _install_session(self, restored):
        self._autosave_timer.stop()
        self.session.__dict__.clear()
        self.session.__dict__.update(restored.__dict__)
        self._last_scientific = self.session.scientific_project_fingerprint()
        self.review_page.run = None
        self.import_page.model.refresh()
        self.import_page.refresh()
        self.workflow_list.setCurrentRow(0)
        self.recovery_bar.hide()
        self._recovery_document = None
        if self.session.engine_note:
            self.window_banner.show_message(self.session.engine_note, "note")
        else:
            self.window_banner.hide()
        self.on_session_changed()

    def new_project(self):
        if not self.request_save_changes():
            return False
        self._install_session(Session())
        return True

    def save_project_as(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save reduction project", self.session.project_path or "Untitled" + branding.PROJECT_EXTENSION,
            f"Reduction project (*{branding.PROJECT_EXTENSION})")
        return self.save_project(path) if path else False

    def save_project(self, path=None):
        if not isinstance(path, (str, Path)):
            path = self.session.project_path
        if not path:
            return self.save_project_as()
        try:
            sidecar = autosave.path_for(self.session)
            self.session.save_project(path)
            self._autosave_timer.stop()
            # Remove after any already queued autosave as well, so a slow write
            # cannot resurrect a sidecar after a successful explicit Save.
            new_sidecar = autosave.path_for(self.session)
            self._autosave_executor.submit(lambda: (sidecar.unlink(missing_ok=True),
                                                    new_sidecar.unlink(missing_ok=True)))
            self.recovery_bar.hide()
            self._recovery_document = None
            self.on_session_changed()
            return True
        except (OSError, ValueError) as exc:
            self.window_banner.show_message(f"Could not save project: {exc}")
            return False

    def request_save_changes(self):
        if self.reduce_page.running:
            self.window_banner.show_message("Wait for the current reduction to finish.", "note")
            return False
        if not self.confirm_close or not self.session.has_unsaved_changes():
            return True
        answer = QtWidgets.QMessageBox.question(
            self, "Unsaved changes", "Save changes to this reduction project?",
            QtWidgets.QMessageBox.StandardButton.Save | QtWidgets.QMessageBox.StandardButton.Discard
            | QtWidgets.QMessageBox.StandardButton.Cancel)
        if answer == QtWidgets.QMessageBox.StandardButton.Cancel:
            return False
        if answer == QtWidgets.QMessageBox.StandardButton.Save:
            return self.save_project()
        self._remove_autosave()
        return True

    def _remove_autosave(self):
        target = autosave.path_for(self.session)
        target.unlink(missing_ok=True)
        self._autosave_executor.submit(lambda: target.unlink(missing_ok=True))

    def _autosave_failed(self, message):
        self.window_banner.show_message(f"Autosave failed: {message}")

    def write_autosave(self):
        if not self.session.has_unsaved_changes() or self._recovery_document is not None:
            return
        try:
            data = project.document(self.session)
        except (OSError, ValueError) as exc:
            self._autosave_failed(str(exc))
            return
        target = autosave.path_for(self.session)
        def write():
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                return project.write(data, target)
            except (OSError, ValueError) as exc:
                try:
                    self.autosaveFailed.emit(str(exc))
                except RuntimeError:  # window already destroyed during shutdown
                    pass
                return None
        self._autosave_future = self._autosave_executor.submit(write)

    def restore_autosave(self):
        if self._recovery_document is None:
            return
        try:
            restored = project.restore(self._recovery_document)
            restored.project_path = self.session.project_path
            restored._saved_project_fingerprint = self.session._saved_project_fingerprint
            self._install_session(restored)
        except (OSError, ValueError) as exc:
            self.window_banner.show_message(f"Could not restore autosave: {exc}")

    def discard_autosave(self):
        self._remove_autosave()
        self._recovery_document = None
        self.recovery_bar.hide()
        if self.session.has_unsaved_changes():
            self._autosave_timer.start()

    # -- settings files ----------------------------------------------------------
    def choose_settings_to_load(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load reduction settings", "",
                                                        SETTINGS_FILTER)
        if path:
            self.load_settings(path)

    def load_settings(self, path):
        """Load a settings JSON; errors and notes appear in the banner. Returns the error."""
        error, note = self.session.load_settings(path)
        if error:
            self.window_banner.show_message(error)
            return error
        if note:
            self.window_banner.show_message(note, "note")
        else:
            self.window_banner.hide()
        self.statusBar().showMessage(f"Loaded settings from {os.path.basename(path)}", 5000)
        self.on_session_changed()
        return None

    def choose_settings_to_save(self):
        start = self.session.settings_path or "reduction_settings.json"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save reduction settings", start,
                                                        "Reduction settings (*.json)")
        if path:
            self.save_settings(path)

    def save_settings(self, path):
        try:
            self.session.save_settings(path)
        except OSError as exc:
            self.window_banner.show_message(f"Could not save {path}: {exc.strerror or exc}")
            return False
        self.statusBar().showMessage(f"Saved settings to {os.path.basename(path)}", 5000)
        return True

    def reset_settings(self):
        self.session.reset_settings()
        self.window_banner.hide()
        self.statusBar().showMessage("Reduction settings reset to the defaults", 5000)
        self.on_session_changed()

    def current_page(self):
        return self.pages.currentWidget()

    def set_step(self, index):
        """Go to step `index` (0-based) if it is unlocked; returns whether it is shown."""
        if 0 <= index < len(STEPS) and self.session.unlocked(index):
            self.workflow_list.setCurrentRow(index)
            return self.workflow_list.currentRow() == index
        return False

    def on_session_changed(self):
        """Refresh everything that depends on the session."""
        self.issues_panel.rebuild()
        page = self.pages.currentWidget()
        for other in self.step_pages[1:]:
            if other is page and hasattr(other, "refresh"):
                other.refresh()
        self.sync_steps()
        self.status_label.setText(self.session.summary_text())
        fingerprint = self.session.scientific_project_fingerprint()
        if fingerprint != self._last_scientific:
            self._last_scientific = fingerprint
            if self.session.has_unsaved_changes() and self._recovery_document is None:
                self._autosave_timer.start()
            elif not self.session.has_unsaved_changes() and self._recovery_document is None:
                self._autosave_timer.stop()
                self._remove_autosave()
        name = Path(self.session.project_path).stem if self.session.project_path else "Untitled"
        self.setWindowTitle(f"{name}[*] — {branding.DISPLAY_NAME}")
        self.setWindowModified(self.session.has_unsaved_changes())
        if self.drawer is not None:
            self._update_issue_badge()

    def _confirm_spike_type(self, fid):
        self.session.confirm_spike_type(fid)
        self._after_confirm()

    def _confirm_no_oxide(self, fid):
        self.session.confirm_no_oxide(fid)
        self._after_confirm()

    def _confirm_all(self, kind):
        self.session.confirm_all(kind)
        self._after_confirm()

    def _after_confirm(self):
        self.import_page.model.refresh_data()
        self.import_page.refresh()
        self.on_session_changed()

    def _select_fraction(self, fid):
        if self._review_active():
            self.review_page.select_fraction(fid)
            self.issues_panel.select(fid)
        else:
            if self.pages.currentWidget() is self.tracer_page:
                self.tracer_page.select_fraction(fid)
            else:
                self.import_page.select_fraction(fid)
            self.issues_panel.select(fid)

    # -- workflow rail -----------------------------------------------------------
    def sync_steps(self):
        """Set each rail row's lock, icon and colour from the session."""
        theme = active_theme()
        current = self.workflow_list.currentRow()
        for index, step in enumerate(STEPS):
            item = self.workflow_list.item(index)
            unlocked = self.session.unlocked(index)
            done = self.session.step_complete(index)
            if not unlocked:
                state, color = "locked", theme.muted
            elif done:
                state, color = "complete", theme.success
            elif index == current:
                state, color = "current", theme.accent
            else:
                state, color = "ready", theme.text
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled
                          if unlocked else QtCore.Qt.ItemFlag.NoItemFlags)
            item.setForeground(QtGui.QColor(color))
            item.setText(f"{index + 1}  {step.title}")
            item.setIcon(build_workflow_stage_icon(step.icon, state=state, accent=theme.accent,
                                                   muted=theme.muted, success=theme.success))
            note = "" if unlocked else " (locked until the previous step is complete)"
            item.setToolTip(f"{index + 1}  {step.title}: {step.summary}{note}")
        if current >= 0 and not self.session.unlocked(current):
            last = max(i for i in range(len(STEPS)) if self.session.unlocked(i))
            self.workflow_list.setCurrentRow(last)
        self._sync_navigation()

    def _sync_navigation(self):
        row = self.workflow_list.currentRow()
        can_back = row > 0
        can_next = row + 1 < len(STEPS) and self.session.unlocked(row + 1)
        self.back_button.setEnabled(can_back)
        self.back_action.setEnabled(can_back)
        self.next_button.setEnabled(can_next)
        self.next_action.setEnabled(can_next)

    def on_step_changed(self, row):
        if row < 0:
            return
        if not self.session.unlocked(row):
            return
        step = STEPS[row]
        page = self.pages.widget(row)
        if page is self.import_page:
            self.import_page.model.refresh_data()
            self.import_page.refresh()
        elif hasattr(page, "refresh"):
            page.refresh()
        self.pages.setCurrentIndex(row)
        self.step_title.setText(f"{row + 1}. {step.title}")
        self.step_summary.setText(step.summary)
        self.step_summary.setToolTip(step.hint)
        self.sync_steps()
        self._sync_issues_shell()

    def go_to_step(self, offset):
        """Move by one step when the destination is unlocked."""
        target = self.workflow_list.currentRow() + offset
        if 0 <= target < len(STEPS) and self.session.unlocked(target):
            self.workflow_list.setCurrentRow(target)

    # -- layout --------------------------------------------------------------------
    def reset_layout(self):
        settings = app_settings()
        for key in (RAIL_MODE_KEY, RAIL_WIDTH_KEY, "layout/rail_compact_v1"):
            settings.remove(key)
        self._user_rail_compact = None
        self._expanded_rail_width = None
        self._apply_width_layout()
        self._size_rail()
        for area in self.findChildren(WorkArea):
            area.reset_layout()
        self.review_page.table_toggle.setChecked(False)
        self._sync_issues_shell()
        self.statusBar().showMessage("Layout reset.", 3000)

    def set_rail_compact(self, compact, *, user=False):
        compact = bool(compact)
        if user:
            self._user_rail_compact = compact
            app_settings().setValue(RAIL_MODE_KEY, compact)
        if compact == self._rail_compact:
            return
        self._rail_compact = compact
        self.workflow_list.setProperty("compactRail", compact)
        self.workflow_list.viewport().update()
        self.rail_brand.setVisible(not compact)
        self.rail_section.setVisible(not compact)
        self.rail.setMaximumWidth(RAIL_COMPACT_WIDTH if compact else RAIL_MAX_WIDTH)
        self.rail.setMinimumWidth(RAIL_COMPACT_WIDTH if compact else RAIL_MIN_WIDTH)
        self.rail.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed if compact else
                                QtWidgets.QSizePolicy.Policy.Preferred,
                                QtWidgets.QSizePolicy.Policy.Expanding)
        self.rail.layout().setContentsMargins(*((8, 12, 8, 10) if compact else (12, 14, 12, 12)))
        self.rail_toggle.setText("»" if compact else "« Collapse")
        self.rail_toggle.setToolTip("Expand the workflow rail" if compact else "Collapse the workflow rail")
        handle = self.splitter.handle(1)
        handle.setEnabled(not compact)
        handle.setToolTip("Expand the rail to resize" if compact else
                          "Drag to resize · Double-click to reset the rail width")
        self.rail_action.blockSignals(True)
        self.rail_action.setChecked(compact)
        self.rail_action.blockSignals(False)
        self._size_rail()
        self._position_drawer()

    def _default_rail_width(self):
        """Fit numbered labels, icons and styled padding at the current font."""
        view = self.workflow_list
        view.ensurePolished()
        option = QtWidgets.QStyleOptionViewItem()
        view.initViewItemOption(option)
        row_width = 0
        for row, step in enumerate(STEPS):
            view.itemDelegate().initStyleOption(option, view.model().index(row, 0))
            option.text = f"{row + 1}  {step.title}"
            text_size = QtCore.QSize(option.fontMetrics.horizontalAdvance(option.text),
                                    option.fontMetrics.height())
            # Unlike delegate.sizeHint(), this ignores the rows' fixed QSize(0, 34).
            item_size = view.style().sizeFromContents(
                QtWidgets.QStyle.ContentsType.CT_ItemViewItem, option, text_size, view)
            row_width = max(row_width, item_size.width())
        margins = (self.rail.contentsMargins(), self.rail.layout().contentsMargins(),
                   view.contentsMargins())
        width = row_width + sum(m.left() + m.right() for m in margins)
        width += 2 * view.spacing() + 2  # List spacing and font rounding allowance.
        return max(RAIL_MIN_WIDTH, min(RAIL_MAX_WIDTH, width))

    def _size_rail(self):
        if self._rail_compact:
            width = RAIL_COMPACT_WIDTH
        else:
            width = self._expanded_rail_width
            if width is None:
                width = self._default_rail_width()
        self.splitter.setSizes([width, max(1, self.splitter.width() - width - self.splitter.handleWidth())])

    def _rail_splitter_moved(self, *_):
        if self._rail_compact is False:
            self._expanded_rail_width = self.splitter.sizes()[0]
            app_settings().setValue(RAIL_WIDTH_KEY, self._expanded_rail_width)
        self._position_drawer()

    def _reset_rail_width(self):
        if not self._rail_compact:
            self._expanded_rail_width = None
            app_settings().remove(RAIL_WIDTH_KEY)
            self._size_rail()

    def set_inspector_visible(self, visible, *, keyboard=False):
        visible = bool(visible)
        if self.drawer is None:
            return
        if self.pages.currentWidget() is self.import_page:
            self.import_page.work_area.set_panel_visible(self.import_page.issues_card, visible, keyboard=keyboard)
        else:
            self._position_drawer()
            self._show_drawer(visible, keyboard=keyboard)
        for control in (self.inspector_toggle, self.inspector_action):
            control.blockSignals(True)
            control.setChecked(visible)
            control.blockSignals(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_width_layout()

    def _apply_width_layout(self):
        width = self.width()
        self._position_drawer()
        compact = (width < COMPACT_RAIL_BELOW if self._user_rail_compact is None
                   else self._user_rail_compact)
        # Studio's laptop rule: a slightly smaller rail font keeps step titles whole.
        font_style = "font-size: 11px;" if width < 1400 else ""
        font_changed = self.workflow_list.styleSheet() != font_style
        if font_changed:
            self.workflow_list.setStyleSheet(font_style)
        self.set_rail_compact(compact)
        if font_changed and not compact and self._expanded_rail_width is None:
            self._size_rail()
        self._position_drawer()

    # -- theme ---------------------------------------------------------------------
    def set_theme_mode(self, mode):
        """Switch between System, Light and Dark without restarting."""
        app = QtWidgets.QApplication.instance()
        self.theme_mode = mode
        apply_theme(app, mode)
        app_settings().setValue("theme_mode", mode)
        if mode in self.theme_actions:
            self.theme_actions[mode].setChecked(True)
        self.refresh_theme()

    def refresh_theme(self):
        self.import_page.refresh_theme()
        self.window_banner.refresh_theme()
        for page in self.step_pages[1:]:
            page.refresh_theme()
        self.issues_panel.rebuild()
        self._update_issue_badge()
        self._position_drawer()
        self.sync_steps()
        if self._rail_compact is False and self._expanded_rail_width is None:
            self._size_rail()
        self.update()

    def paintEvent(self, event):
        paint_wallpaper(self)

    # -- drag and drop -------------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.open_paths(paths)

    # -- closing -------------------------------------------------------------------
    def _review_active(self):
        return self.drawer is not None and self.pages.currentWidget() is self.review_page


    def _sync_issues_shell(self):
        if self.drawer is None:
            return
        animation = getattr(self, "_drawer_animation", None)
        if animation is not None:
            animation.stop()
            animation.deleteLater()
            self._drawer_animation = None
        self.drawer.setGraphicsEffect(None)
        self.drawer.hide()
        if self.pages.currentWidget() is self.import_page:
            self.issues_panel.title.hide()
            self.issues_panel.layout().setContentsMargins(0, 0, 0, 0)
            self.import_page.issues_content.layout().addWidget(self.inspector)
            self.inspector.show()
            self.set_inspector_visible(bool(self._attention), keyboard=True)
        else:
            self.issues_panel.title.show()
            self.issues_panel.layout().setContentsMargins(8, 8, 6, 8)
            self.drawer.layout().addWidget(self.inspector, 1)
            self.inspector.show()
            self.set_inspector_visible(False, keyboard=True)
        self._update_issue_badge()
        self._position_drawer()

    def _update_issue_badge(self):
        issues = self.session.issues()
        failures = self.session.quality_failures() if self.session.has_table else []
        blocking = {i.fraction_id for i in issues if i.blocking}
        failing = {f.fraction_id for f in failures}
        run = self.session.reduction
        known = {r.fraction_id for r in run.results if not r.reduced} \
            if run is not None and self.session.reduction_current else set()
        attention = {(i.fraction_id, i.kind, i.message) for i in issues if i.blocking}
        attention |= {(f.fraction_id, "quality", f.reason) for f in failures if f.fraction_id not in known}
        affected = {i.fraction_id for i in issues} | failing
        problems = blocking | failing
        notes = IssuesPanel.note_count(issues)
        note_count = f"{notes} note{'s' if notes != 1 else ''}"
        self.issue_notes.setText(note_count)
        self.issue_notes.setVisible(bool(problems and notes))
        self.inspector_toggle.setText(f"Issues · {len(problems)}" if problems else f"Notes · {notes}")
        color = active_theme().danger if blocking or failing else active_theme().muted
        self.inspector_toggle.setStyleSheet(f"color: {color}; padding: 7px 11px;")
        self.inspector_toggle.setToolTip(
            f"{len(affected)} fractions with issues · {len(failing)} linked-error failures · {note_count}. "
            "Failures already marked not reduced stay closed. Click to inspect.")
        if attention - self._attention:
            self.set_inspector_visible(True)
        elif not attention and self._attention:
            self.set_inspector_visible(False)
        self._attention = attention


    def _show_drawer(self, visible, *, keyboard=False):
        animation = getattr(self, "_drawer_animation", None)
        if animation is not None:
            animation.stop()
            animation.deleteLater()
            self._drawer_animation = None
            self.drawer.setGraphicsEffect(None)
        keyboard = keyboard or bool(QtWidgets.QApplication.instance().property("panelKeyboardInput"))
        if keyboard or reduced_motion() or not self.isVisible():
            self.drawer.setGraphicsEffect(None)
            self.drawer.setVisible(visible)
        elif self.drawer.isVisible() != visible:
            effect = QtWidgets.QGraphicsOpacityEffect(self.drawer)
            self.drawer.setGraphicsEffect(effect)
            self.drawer.show()
            animation = QtCore.QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(180)
            animation.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
            animation.setStartValue(0. if visible else 1.)
            animation.setEndValue(1. if visible else 0.)
            animation.finished.connect(lambda: self.drawer.setVisible(visible))
            self._drawer_animation = animation
            animation.start()
        self.drawer.raise_()

    def _position_drawer(self):
        if self.drawer is None:
            return
        theme = active_theme()
        self.drawer.setStyleSheet(f"QFrame#ReviewIssuesDrawer {{ background: {theme.surface}; "
                                 f"border: 1px solid {theme.input_border}; border-radius: 12px; }}")
        top = self.pages.y()
        width = min(360, self.main_panel.width() - 24)
        self.drawer.setGeometry(self.main_panel.width() - width - 12, top, width,
                                max(100, self.main_panel.height() - top - 14))


    def closeEvent(self, event):
        if not self.request_save_changes():
            event.ignore()
            return
        for area in self.findChildren(WorkArea):
            area.save_layout()
        self._autosave_timer.stop()
        self._autosave_executor.shutdown(wait=False)
        super().closeEvent(event)
