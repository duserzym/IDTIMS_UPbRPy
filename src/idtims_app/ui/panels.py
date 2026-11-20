"""Shared work panels: contained maximise, remembered splitters and short motion.

Layout preferences belong to the viewer's QSettings, never to a project. A
maximised panel is temporarily lifted out of its splitter; a placeholder and
saved states preserve the exact original layout, including hidden panels.
"""
from __future__ import annotations

import os

from PySide6 import QtCore, QtGui, QtWidgets

from idtims_app import branding


def layout_settings():
    path = os.environ.get("IDTIMS_APP_SETTINGS")
    if path:
        return QtCore.QSettings(path, QtCore.QSettings.Format.IniFormat)
    return QtCore.QSettings(branding.ORGANISATION, branding.SLUG)


def reduced_motion():
    if any(os.environ.get(key, "").lower() not in {"", "0", "false", "no", "off"}
           for key in ("UPBRPY_REDUCE_MOTION", "UPBLAB_REDUCE_MOTION")):
        return True
    app = QtWidgets.QApplication.instance()
    hints = app.styleHints()  # Keep the owner alive while reading accessibility hints.
    if hasattr(hints, "accessibility"):
        preference = hints.accessibility().motionPreference()
        if preference.name == "ReducedMotion":
            return True
    return not app.style().styleHint(QtWidgets.QStyle.StyleHint.SH_Widget_Animate)


class _ResetHandle(QtWidgets.QSplitterHandle):
    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.splitter().reset_sizes()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)


class RememberedSplitter(QtWidgets.QSplitter):
    """Studio's saveState/restoreState pattern, with per-splitter reset."""

    def __init__(self, orientation, key, proportions, parent=None):
        super().__init__(orientation, parent)
        self.key = f"layout/{key}_v1"
        self.proportions = proportions
        self.initialized = False
        self.suspended = False
        self.setChildrenCollapsible(False)
        self.setHandleWidth(8)
        self.splitterMoved.connect(self.save_layout)

    def createHandle(self):
        handle = _ResetHandle(self.orientation(), self)
        handle.setToolTip("Drag to resize · Double-click to reset this split")
        return handle

    def showEvent(self, event):
        super().showEvent(event)
        if not self.initialized:
            QtCore.QTimer.singleShot(0, self.restore_layout)

    def restore_layout(self):
        if self.initialized:
            return
        self.initialized = True
        state = layout_settings().value(self.key)
        if not isinstance(state, QtCore.QByteArray) or not self.restoreState(state):
            self.reset_sizes()

    def reset_sizes(self):
        total = self.height() if self.orientation() == QtCore.Qt.Orientation.Vertical else self.width()
        self.setSizes([round(total * part / sum(self.proportions)) for part in self.proportions])
        if self.initialized:
            self.save_layout()

    def save_layout(self, *_):
        if self.initialized and not self.suspended:
            layout_settings().setValue(self.key, self.saveState())


class WorkPanel(QtWidgets.QFrame):
    """A slim header with a focus target, double-click and maximise control."""

    toggleRequested = QtCore.Signal(object)

    def __init__(self, title, content, control=None, *, minimum=(180, 100), maximum=(8192, 8192)):
        super().__init__()
        self.title = title
        self.setObjectName("WorkPanel")
        self.setMinimumSize(*minimum)
        self.setMaximumSize(*maximum)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 7)
        layout.setSpacing(4)
        self.header = QtWidgets.QWidget()
        self.header.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        bar = QtWidgets.QHBoxLayout(self.header)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(6)
        self.label = QtWidgets.QLabel(title)
        self.label.setObjectName("WorkflowContextTitle")
        bar.addWidget(self.label)
        if control is not None:
            stretch = 1 if isinstance(control, QtWidgets.QComboBox) else 0
            bar.addWidget(control, stretch)
            if not stretch:
                bar.addStretch(1)
        else:
            bar.addStretch(1)
        self.maximise_button = QtWidgets.QToolButton()
        self.maximise_button.setText("⛶")
        self.maximise_button.setProperty("modeToggle", True)
        self.maximise_button.setFixedSize(24, 24)
        self.maximise_button.setStyleSheet("font-size: 17px; padding: 0;")
        self.maximise_button.clicked.connect(lambda: self.toggleRequested.emit(self))
        bar.addWidget(self.maximise_button)
        layout.addWidget(self.header)
        layout.addWidget(content, 1)
        self.header.installEventFilter(self)
        self.label.installEventFilter(self)
        self.set_maximised(False)

    def set_reference(self, reference):
        if self.property("reference") == reference:
            return
        self.setProperty("reference", reference)
        self.label.setProperty("referenceTitle", reference)
        for widget in (self, self.label):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def set_maximised(self, on):
        verb = "Restore" if on else "Maximise"
        self.maximise_button.setText("❐" if on else "⛶")
        self.maximise_button.setToolTip(f"{verb} {self.title} · Cmd/Ctrl+Shift+Return")
        self.maximise_button.setAccessibleName(f"{verb} {self.title}")

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.MouseButtonDblClick \
                and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.toggleRequested.emit(self)
            event.accept()
            return True
        return super().eventFilter(watched, event)


class WorkArea(QtWidgets.QWidget):
    """Owns a splitter tree and lifts one work panel to its full area."""

    def __init__(self, root, panels, parent=None):
        super().__init__(parent)
        self.root = root
        self.panels = list(panels)
        self.maximised = None
        self._saved = None
        self._hidden_states = {}
        self._animation = None
        self._ghost = None
        self._stage = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(root)
        self.splitters = [root, *root.findChildren(RememberedSplitter)]
        for panel in self.panels:
            panel.toggleRequested.connect(self.toggle_panel)

    def states(self):
        return [(splitter, splitter.saveState(), splitter.sizes()) for splitter in self.splitters]

    def restore_states(self, states):
        self.layout().activate()
        for splitter, state, sizes in states:
            if sizes is None:
                splitter.restoreState(state)
            elif sum(sizes):
                splitter.restoreState(state)
                splitter.setSizes(sizes)
            else:
                splitter.reset_sizes()

    def toggle_panel(self, panel, *, keyboard=False):
        keyboard = keyboard or bool(QtWidgets.QApplication.instance().property("panelKeyboardInput"))
        self._finish_animation()
        if self.maximised is not None:
            self.restore_panel(keyboard=keyboard)
            return
        if panel not in self.panels or not panel.isVisible():
            return
        self._saved = self.states()
        parent = panel.parentWidget()
        index = parent.indexOf(panel)
        before = QtCore.QRect(panel.mapTo(self, QtCore.QPoint()), panel.size())
        pixmap = panel.grab() if not keyboard and not reduced_motion() else None
        self._placeholder = QtWidgets.QWidget()
        self._parent, self._index = parent, index
        for splitter in self.splitters:
            splitter.suspended = True
        parent.replaceWidget(index, self._placeholder)
        self.root.hide()
        self.layout().addWidget(panel)
        panel.show()
        self.maximised = panel
        panel.set_maximised(True)
        self.layout().activate()
        panel.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
        self._animate(pixmap, before, self.rect())

    def restore_panel(self, *, keyboard=False):
        if self.maximised is None:
            return False
        keyboard = keyboard or bool(QtWidgets.QApplication.instance().property("panelKeyboardInput"))
        self._finish_animation()
        panel = self.maximised
        pixmap = panel.grab() if not keyboard and not reduced_motion() else None
        self.layout().removeWidget(panel)
        panel.setParent(None)
        self._parent.replaceWidget(self._index, panel)
        self._placeholder.deleteLater()
        self.root.show()
        panel.show()
        panel.set_maximised(False)
        self.maximised = None
        self.restore_states(self._saved)
        for splitter in self.splitters:
            splitter.suspended = False
        self._saved = None
        after = QtCore.QRect(panel.mapTo(self, QtCore.QPoint()), panel.size())
        self._animate(pixmap, self.rect(), after)
        panel.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
        return True

    def _animate(self, pixmap, start, end):
        if pixmap is None or start == end:
            return
        from idtims_app.ui.theme import active_theme
        stage = QtWidgets.QWidget(self)
        stage.setGeometry(self.rect())
        stage.setStyleSheet(f"background: {active_theme().surface};")
        stage.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        stage.show()
        stage.raise_()
        self._stage = stage
        ghost = QtWidgets.QLabel(stage)
        ghost.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        ghost.setPixmap(pixmap)
        ghost.setScaledContents(True)
        ghost.setGeometry(start)
        ghost.show()
        ghost.raise_()
        animation = QtCore.QPropertyAnimation(ghost, b"geometry", self)
        animation.setDuration(180)
        animation.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        animation.setStartValue(start)
        animation.setEndValue(end)
        self._ghost, self._animation = ghost, animation
        animation.finished.connect(self._finish_animation)
        animation.start()

    def _finish_animation(self):
        if self._animation is not None:
            animation, self._animation = self._animation, None
            animation.stop()
            animation.deleteLater()
        if self._ghost is not None:
            self._ghost.hide()
            self._ghost.deleteLater()
            self._ghost = None
        if self._stage is not None:
            self._stage.hide()
            self._stage.deleteLater()
            self._stage = None

    def set_panel_visible(self, panel, visible, *, keyboard=False):
        if panel.isHidden() == (not visible):
            return
        self._finish_animation()
        keyboard = keyboard or bool(QtWidgets.QApplication.instance().property("panelKeyboardInput"))
        pixmap = self.grab() if self.isVisible() and not keyboard and not reduced_motion() else None
        if self.maximised is not None:
            self.restore_panel(keyboard=True)
        if visible:
            panel.show()
            if panel in self._hidden_states:
                self.restore_states(self._hidden_states.pop(panel))
        elif not panel.isHidden():
            states = self.states()
            for index, (splitter, state, sizes) in enumerate(states):
                if not splitter.initialized:
                    saved = layout_settings().value(splitter.key)
                    if isinstance(saved, QtCore.QByteArray):
                        states[index] = (splitter, saved, None)
            self._hidden_states[panel] = states
            panel.hide()
        if pixmap is not None:
            ghost = QtWidgets.QLabel(self)
            ghost.setPixmap(pixmap)
            ghost.setGeometry(self.rect())
            ghost.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            effect = QtWidgets.QGraphicsOpacityEffect(ghost)
            ghost.setGraphicsEffect(effect)
            ghost.show()
            ghost.raise_()
            animation = QtCore.QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(180)
            animation.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
            animation.setStartValue(1.)
            animation.setEndValue(0.)
            self._ghost, self._animation = ghost, animation
            animation.finished.connect(self._finish_animation)
            animation.start()

    def panel_for(self, widget):
        return next((panel for panel in self.panels
                     if panel.isVisible() and (widget is panel or panel.isAncestorOf(widget))), None) \
            if widget is not None else None

    def save_layout(self):
        states = self._saved or next(iter(self._hidden_states.values()), None)
        for splitter in self.splitters:
            if states:
                state, sizes = next((state, sizes) for candidate, state, sizes in states if candidate is splitter)
                if sizes is None or sum(sizes):
                    layout_settings().setValue(splitter.key, state)
            else:
                splitter.save_layout()

    def reset_layout(self):
        self.restore_panel(keyboard=True)
        for panel in self._hidden_states:
            panel.show()
        self._hidden_states.clear()
        for splitter in self.splitters:
            layout_settings().remove(splitter.key)
            splitter.reset_sizes()

    def hideEvent(self, event):
        self._finish_animation()  # Tab switches never animate.
        super().hideEvent(event)


class PanelShortcuts(QtCore.QObject):
    """Window-local key handling. Esc is untouched outside a maximised panel."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+Return"), window)
        self.shortcut.activated.connect(self.toggle_focused)
        QtWidgets.QApplication.instance().installEventFilter(self)

    def areas(self):
        return [area for area in self.window.findChildren(WorkArea) if area.isVisible()]

    def toggle_focused(self):
        app = QtWidgets.QApplication.instance()
        cursor = QtGui.QCursor.pos()
        under_mouse = app.widgetAt(cursor) or self.window.childAt(self.window.mapFromGlobal(cursor))
        for widget in (app.focusWidget(), under_mouse):
            for area in self.areas():
                panel = area.panel_for(widget)
                if panel is not None:
                    area.toggle_panel(panel, keyboard=True)
                    return

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.KeyPress:
            QtWidgets.QApplication.instance().setProperty("panelKeyboardInput", True)
        elif event.type() == QtCore.QEvent.Type.MouseButtonPress:
            QtWidgets.QApplication.instance().setProperty("panelKeyboardInput", False)
        if event.type() == QtCore.QEvent.Type.KeyPress and event.key() == QtCore.Qt.Key.Key_Escape \
                and isinstance(watched, QtWidgets.QWidget) and watched.window() is self.window:
            for area in reversed(self.areas()):
                if area.restore_panel(keyboard=True):
                    event.accept()
                    return True
        return False


def scroll_content(widget):
    """Keep form fields and long explanations reachable within a work panel."""
    scroll = QtWidgets.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    scroll.setMinimumSize(100, 50)
    scroll.setWidget(widget)
    return scroll
