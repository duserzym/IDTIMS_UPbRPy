"""Native rail divider gestures, laptop defaults and per-user persistence."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")
from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from idtims_app.ui.theme import apply_theme
from idtims_app.window import (MainWindow, RAIL_COMPACT_WIDTH, RAIL_MAX_WIDTH,
                               RAIL_MIN_WIDTH, RAIL_MODE_KEY, RAIL_WIDTH_KEY, app_settings)
from test_gui_import import _layout_problems
from test_gui_steps import app, settle


@pytest.fixture
def rail_window(app, monkeypatch, tmp_path):
    monkeypatch.setenv("IDTIMS_APP_SETTINGS", str(tmp_path / "rail.ini"))
    monkeypatch.setenv("IDTIMS_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    windows = []

    def factory(size=(1280, 800)):
        window = MainWindow(confirm_close=False)
        windows.append(window)
        window.resize(*size)
        window.show()
        settle()
        assert window.size().toTuple() == size
        return window

    yield factory
    for window in windows:
        window.close()
        window.deleteLater()
    settle()
    apply_theme(app, "light")


def drag_rail(window, delta):
    handle = window.splitter.handle(1)
    start = handle.rect().center()
    QtTest.QTest.mousePress(handle, QtCore.Qt.MouseButton.LeftButton, pos=start)
    QtTest.QTest.mouseMove(handle, start + QtCore.QPoint(delta, 0), delay=10)
    QtTest.QTest.mouseRelease(handle, QtCore.Qt.MouseButton.LeftButton,
                             pos=handle.rect().center())
    settle()


def assert_labels_not_elided(window):
    """Compare normal row painting with elision disabled, without a PNG baseline."""
    view = window.workflow_list
    for row in range(view.count()):
        index = view.model().index(row, 0)
        option = QtWidgets.QStyleOptionViewItem()
        view.initViewItemOption(option)
        option.rect = QtCore.QRect(QtCore.QPoint(), view.visualRect(index).size())
        images = []
        for mode in (QtCore.Qt.TextElideMode.ElideRight, QtCore.Qt.TextElideMode.ElideNone):
            option.textElideMode = mode
            image = QtGui.QImage(option.rect.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(QtCore.Qt.GlobalColor.transparent)
            painter = QtGui.QPainter(image)
            view.itemDelegate().paint(painter, option, index)
            painter.end()
            images.append(image)
        assert images[0] == images[1], f"Elided label: {view.item(row).text()}"


@pytest.mark.parametrize("size", [(1280, 800), (1512, 982)])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_laptop_defaults_show_labels_and_ignore_legacy_mode(rail_window, app, size, theme):
    # A v1 compact setting from the forced-compact era must not hide labels.
    app_settings().setValue("layout/rail_compact_v1", True)
    apply_theme(app, theme)
    window = rail_window(size)
    assert not window._rail_compact
    assert window.rail.width() == window._default_rail_width()
    assert window.workflow_list.font().pixelSize() == (11 if size[0] < 1400 else 12)
    assert_labels_not_elided(window)
    assert window.main_panel.width() >= 900
    assert window.rail_brand.isVisible() and window.rail_section.isVisible()
    assert window.workflow_list.item(0).text() == "1  Import fractions"
    assert window.workflow_list.textElideMode() == QtCore.Qt.TextElideMode.ElideRight
    assert window.workflow_list.horizontalScrollBar().maximum() == 0
    assert not app_settings().contains(RAIL_MODE_KEY)  # Automatic layout is not a choice.
    assert _layout_problems(window) == []


def test_handle_drag_bounds_resize_persistence_and_reset(rail_window):
    first = rail_window()
    default_width = first.rail.width()
    drag_rail(first, 60)
    dragged = first.rail.width()
    assert dragged == default_width + 60
    assert int(app_settings().value(RAIL_WIDTH_KEY)) == dragged
    for size in [(1512, 982), (1280, 800)]:
        first.resize(*size)
        settle()
        assert first.rail.width() == dragged  # Window resize must not reset a drag.
    first.rail_toggle.click()
    assert first._rail_compact and first.rail.width() == RAIL_COMPACT_WIDTH
    assert not first.splitter.handle(1).isEnabled()
    first.close()

    second = rail_window((1512, 982))
    assert second._rail_compact
    second.rail_toggle.click()
    settle()
    assert second.rail.width() == dragged
    second.close()
    third = rail_window()
    assert not third._rail_compact and third.rail.width() == dragged
    drag_rail(third, 1000)
    assert third.rail.width() == RAIL_MAX_WIDTH
    drag_rail(third, -1000)
    assert third.rail.width() == RAIL_MIN_WIDTH
    for row in range(third.workflow_list.count()):
        item = third.workflow_list.item(row)
        assert item.text() in item.toolTip()  # Full label remains reachable when elided.
    assert _layout_problems(third) == []
    QtTest.QTest.mouseDClick(third.splitter.handle(1), QtCore.Qt.MouseButton.LeftButton)
    settle()
    assert third.rail.width() == third._default_rail_width()
    assert_labels_not_elided(third)
    assert not app_settings().contains(RAIL_WIDTH_KEY)


def test_narrow_auto_mode_and_explicit_choices_survive_width_changes(rail_window):
    automatic = rail_window((1000, 800))
    assert automatic._rail_compact
    automatic.resize(1280, 800)
    settle()
    assert not automatic._rail_compact
    automatic.resize(1000, 800)
    settle()
    assert automatic._rail_compact
    assert not app_settings().contains(RAIL_MODE_KEY)
    automatic.rail_action.trigger()  # View menu expands, overriding the narrow rule.
    settle()
    assert not automatic._rail_compact and not automatic.rail_action.isChecked()
    automatic.close()
    chosen = rail_window((1000, 800))
    assert not chosen._rail_compact
    chosen.rail_toggle.click()
    assert chosen._rail_compact and chosen.rail_action.isChecked()
    chosen.resize(1512, 982)
    settle()
    assert chosen._rail_compact
    chosen.rail_action.trigger()
    settle()
    assert not chosen._rail_compact and chosen.rail_toggle.text() == "« Collapse"
    chosen.reset_layout_action.trigger()
    chosen.resize(1000, 800)
    settle()
    assert chosen._rail_compact
    assert not app_settings().contains(RAIL_MODE_KEY)


@pytest.mark.parametrize("saved, expected", [(20, RAIL_MIN_WIDTH), (999, RAIL_MAX_WIDTH),
                                             ("invalid", None)])
def test_saved_width_is_validated(rail_window, saved, expected):
    app_settings().setValue(RAIL_WIDTH_KEY, saved)
    window = rail_window()
    assert window.rail.width() == (window._default_rail_width() if expected is None else expected)


def test_default_width_tracks_font_band_and_reset_uses_current_font(rail_window):
    window = rail_window()
    laptop_width = window.rail.width()
    window.resize(1512, 982)
    settle()
    assert window.rail.width() > laptop_width
    assert_labels_not_elided(window)
    drag_rail(window, -1000)
    assert window.rail.width() == RAIL_MIN_WIDTH
    QtTest.QTest.mouseDClick(window.splitter.handle(1), QtCore.Qt.MouseButton.LeftButton)
    settle()
    assert window.rail.width() == window._default_rail_width()
    assert_labels_not_elided(window)
    window.resize(1280, 800)
    settle()
    assert window.rail.width() == laptop_width
    assert_labels_not_elided(window)
    drag_rail(window, 30)
    window.reset_layout_action.trigger()
    settle()
    assert window.rail.width() == laptop_width
    assert_labels_not_elided(window)
