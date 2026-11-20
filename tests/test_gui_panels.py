"""Panel interaction, persistence, fit and long-data regressions (Qt offscreen)."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")
from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from IDTIMS_UPbRPy import dates
from IDTIMS_UPbRPy.fractions import FractionIssue
from idtims_app.ui import panels
from idtims_app.window import MainWindow
from test_gui_import import _layout_problems
from test_gui_review import review_window
from test_gui_steps import app, settle, TEMPLATE, TEMPLATE_SETTINGS

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ui_round_support import long_fraction_fixture

SIZES = [(1280, 800), (1512, 982), (1440, 900), (1024, 640)]


@pytest.fixture(autouse=True)
def isolated_layout(app, monkeypatch, tmp_path):
    monkeypatch.setenv("IDTIMS_APP_SETTINGS", str(tmp_path / "layout.ini"))
    monkeypatch.setenv("IDTIMS_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    monkeypatch.setenv("UPBRPY_REDUCE_MOTION", "1")
    app.setProperty("panelKeyboardInput", False)


def template_window(factory, size=(1280, 800), path=TEMPLATE):
    return factory(path=path, settings=TEMPLATE_SETTINGS, diagnostic=False, size=size)


def sizes(area):
    return [splitter.sizes() for splitter in area.splitters]


@pytest.mark.parametrize("size", SIZES)
def test_every_step_fits_three_sizes(review_window, size):
    window = template_window(review_window, size)
    for step in range(8):
        assert window.set_step(step)
        settle()
        assert window.size().toTuple() == size
        assert window.splitter.sizes()[0] == window.rail.width()
        assert window.main_panel.x() == window.rail.width() + window.splitter.handleWidth()
        assert window.minimumSizeHint().width() <= size[0]
        assert window.minimumSizeHint().height() <= size[1]
        assert _layout_problems(window) == [], step
        area = window.current_page().work_area
        for panel in area.panels:
            if panel.isVisible():
                assert area.rect().contains(QtCore.QRect(panel.mapTo(area, QtCore.QPoint()), panel.size()))


@pytest.mark.parametrize("step", range(8))
def test_all_work_panels_maximise_and_restore_exact_sizes(review_window, step):
    window = template_window(review_window)
    assert window.set_step(step)
    if step == 0:
        window.set_inspector_visible(True, keyboard=True)
    settle()
    area = window.current_page().work_area
    original = sizes(area)
    for panel in area.panels:
        panel.maximise_button.click()
        settle()
        assert area.maximised is panel
        assert panel.geometry() == area.rect()
        assert _layout_problems(window) == []
        # Refreshing scientific presentation must leave the solo panel in place.
        window.on_session_changed()
        settle()
        assert area.maximised is panel and panel.geometry() == area.rect()
        QtTest.QTest.keyClick(panel, QtCore.Qt.Key.Key_Escape)
        settle()
        assert area.maximised is None
        assert sizes(area) == original


def test_header_double_click_shortcut_focus_and_pointer(review_window):
    window = template_window(review_window)
    page, area = window.review_page, window.review_page.work_area
    QtTest.QTest.mouseDClick(page.concordia_card.label, QtCore.Qt.MouseButton.LeftButton)
    assert area.maximised is page.concordia_card
    QtTest.QTest.mouseDClick(page.concordia_card.header, QtCore.Qt.MouseButton.LeftButton)
    assert area.maximised is None
    window.activateWindow()
    page.table.setFocus()
    settle()
    QtTest.QTest.keyClick(page.table, QtCore.Qt.Key.Key_Return,
                        QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.ShiftModifier)
    assert area.maximised is page.table_card
    assert area._animation is None
    QtTest.QTest.keyClick(page.table, QtCore.Qt.Key.Key_Return,
                        QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.ShiftModifier)
    assert area.maximised is None
    # With focus outside a work panel, the panel under the pointer wins.
    window.next_button.setFocus()
    QtGui.QCursor.setPos(page.weighted_card.mapToGlobal(page.weighted_card.rect().center()))
    settle()
    window.panel_shortcuts.toggle_focused()
    assert area.maximised is page.weighted_card


def test_escape_is_delivered_when_nothing_is_maximised(review_window):
    window = template_window(review_window)
    area = window.review_page.work_area
    original = sizes(area)

    class EscapeProbe(QtCore.QObject):
        seen = False

        def eventFilter(self, watched, event):
            if event.type() == QtCore.QEvent.Type.KeyPress and event.key() == QtCore.Qt.Key.Key_Escape:
                self.seen = True
            return False

    probe = EscapeProbe(window)
    window.review_page.table.installEventFilter(probe)
    QtTest.QTest.keyClick(window.review_page.table, QtCore.Qt.Key.Key_Escape)
    assert probe.seen
    assert area.maximised is None and sizes(area) == original


def test_splitter_handle_and_view_reset(review_window):
    window = template_window(review_window)
    page = window.review_page
    for splitter in (page.plots, page.splitter):
        splitter.reset_sizes()
        default = splitter.sizes()
        splitter.setSizes([500, 300])
        QtTest.QTest.mouseDClick(splitter.handle(1), QtCore.Qt.MouseButton.LeftButton)
        assert splitter.sizes() == default
    page.table_toggle.setChecked(True)
    window.set_rail_compact(False, user=True)
    window.reset_layout_action.trigger()
    settle()
    assert not page.table_toggle.isChecked() and page.table_card.isVisible()
    assert not window._rail_compact  # Reset restores labels on laptops.
    assert not window.import_page.issues_card.isVisible()


def test_hide_table_keeps_plot_proportions_and_restores(review_window):
    window = template_window(review_window)
    page = window.review_page
    before = sizes(page.work_area)
    page.table_toggle.setChecked(True)
    settle()
    assert page.plots.sizes() == before[1]
    assert not page.table_card.isVisible()
    page.table_toggle.setChecked(False)
    settle()
    assert sizes(page.work_area) == before
    assert page.table.viewport().height() >= 4 * page.table.rowHeight(0)


def test_sizes_survive_new_window_and_saving_while_maximised(review_window):
    first = template_window(review_window)
    area = first.review_page.work_area
    first.review_page.plots.setSizes([610, 490])
    first.review_page.splitter.setSizes([350, 240])
    expected = sizes(area)
    area.toggle_panel(first.review_page.concordia_card, keyboard=True)
    first.close()
    second = template_window(review_window)
    assert sizes(second.review_page.work_area) == expected
    second.review_page.table_toggle.setChecked(True)
    second.close()
    third = template_window(review_window)
    assert sizes(third.review_page.work_area) == expected


@pytest.mark.parametrize("step", [0, 1, 2, 3, 4, 5, 7])
def test_other_splitters_survive_new_window(review_window, step):
    first = template_window(review_window)
    first.set_step(step)
    if step == 0:
        first.set_inspector_visible(True, keyboard=True)
    settle()
    area = first.current_page().work_area
    area.root.setSizes([320, 210])
    expected = sizes(area)
    first.close()
    second = template_window(review_window)
    second.set_step(step)
    if step == 0:
        second.set_inspector_visible(True, keyboard=True)
    settle()
    assert sizes(second.current_page().work_area) == expected


@pytest.mark.parametrize("size", SIZES)
def test_forty_long_fractions_remain_usable_and_numerically_equal(review_window, tmp_path, size):
    window = template_window(review_window, size, long_fraction_fixture(tmp_path / "forty.csv"))
    page = window.review_page
    assert len(page.rows) == 40 and len(window.session.reduction.grains) == 27
    assert page.concordia_card.width() >= 360
    assert page.table.viewport().height() >= 4 * page.table.rowHeight(0)
    assert _layout_problems(window) == []
    assert not window.drawer.isVisible()  # 13 known failures are already not reduced.
    window.set_inspector_visible(True, keyboard=True)
    settle()
    assert window.drawer.geometry().right() <= window.main_panel.width()
    for card in window.issues_panel._cards.values():
        button = next(button for button in card.findChildren(QtWidgets.QToolButton)
                      if hasattr(button, "fraction_id"))
        assert button.width() <= card.width()
        assert button.fraction_id in button.toolTip()
    window.set_inspector_visible(False, keyboard=True)
    page.table.horizontalScrollBar().setValue(page.table.horizontalScrollBar().maximum())
    assert page.table.frozen.frozen_columns() == [0, 1]
    assert page.table.frozen.width() >= page.table.columnWidth(0) + page.table.columnWidth(1)
    last = next(row.fraction_id for row in reversed(page.rows) if row.reduced)
    page.select_fraction(last)
    settle()
    assert page.concordia.canvas.selected_id == page.weighted.plot.selected_id == last
    assert page.table.currentIndex().row() == page.model.row_of(last)
    assert page.table.verticalScrollBar().value() == page.table.frozen.verticalScrollBar().value()
    assert page.table.frozen.visualRect(page.model.index(page.model.row_of(last), 0)).intersects(
        page.table.frozen.viewport().rect())
    assert last in page.model.data(page.model.index(page.model.row_of(last), 0), QtCore.Qt.ItemDataRole.ToolTipRole)
    checkbox = page.model.index(page.model.row_of(last), 1)
    position = page.table.frozen.visualRect(checkbox).topLeft() + QtCore.QPoint(10, 10)
    QtTest.QTest.mouseClick(page.table.frozen.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=position)
    assert not window.session.is_included(last)
    page.set_included(last, True)
    page.refresh_theme()
    assert page.table.currentIndex().row() == page.model.row_of(last)
    assert page.concordia.canvas.selected_id == page.weighted.plot.selected_id == last
    for excluded in (set(), {last}):
        page.set_included(last, last not in excluded)
        for kind in dates.DATE_KINDS:
            page.set_kind(kind)
            expected = dates.sample_dates(window.session.reduction.grains,
                                          include=set(window.session.included_ids()), kinds=(kind,))[kind]
            assert page.current_sample() == expected


def test_issues_auto_open_only_for_new_blocking_problem(review_window, monkeypatch):
    window = template_window(review_window)
    before = sizes(window.review_page.work_area)
    assert not window.drawer.isVisible()
    issue = FractionIssue("z2", "missing_setup", "z2: new missing setup")
    monkeypatch.setattr(window.session, "issues", lambda *args: [issue])
    window._update_issue_badge()
    assert window.drawer.isVisible()
    assert window.drawer.geometry().right() <= window.main_panel.width()
    assert sizes(window.review_page.work_area) == before
    window.set_inspector_visible(False, keyboard=True)
    window._update_issue_badge()
    assert not window.drawer.isVisible()
    issue = FractionIssue("z2", "missing_setup", "z2: a different new problem")
    window._update_issue_badge()
    assert window.drawer.isVisible()
    issue = FractionIssue("z2", "mean_statistic_note", "An informational note")
    monkeypatch.setattr(window.session, "quality_failures", lambda *args: [])
    window._update_issue_badge()
    assert not window.drawer.isVisible()
    assert window.inspector_toggle.text() == "Notes · 1"


def test_rail_preference_and_narrow_startup(review_window):
    first = template_window(review_window, (1440, 900))
    assert not first._rail_compact
    first.set_rail_compact(True, user=True)
    first.close()
    second = template_window(review_window, (1440, 900))
    assert second._rail_compact
    second.set_rail_compact(False, user=True)
    second.close()
    narrow = template_window(review_window, (1000, 800))
    assert not narrow._rail_compact  # Explicit expanded choice wins at every width.
    narrow.resize(1440, 900)
    settle()
    assert not narrow._rail_compact


def test_motion_is_short_and_keyboard_and_reduced_motion_are_instant(review_window, monkeypatch, app):
    window = template_window(review_window)
    area, panel = window.review_page.work_area, window.review_page.concordia_card
    with monkeypatch.context() as patch:
        patch.delenv("UPBRPY_REDUCE_MOTION")
        patch.delenv("UPBLAB_REDUCE_MOTION", raising=False)
        patch.setattr(panels, "reduced_motion", lambda: False)
        app.setProperty("panelKeyboardInput", False)
        area.toggle_panel(panel)
        assert 0 < area._animation.duration() < 300
        assert area._animation.easingCurve().type() == QtCore.QEasingCurve.Type.OutCubic
        finished = QtTest.QSignalSpy(area._animation.finished)
        assert finished.wait(600)  # Wait for the signal; a busy offscreen loop may start late.
        assert area._animation is None
        area.restore_panel(keyboard=True)
        assert area._animation is None
        area.toggle_panel(panel, keyboard=True)
        assert area._animation is None
        area.restore_panel(keyboard=True)
        area.toggle_panel(panel)
        window.set_step(5)
        assert area._animation is None
        window.set_step(6)
        assert area._animation is None
        area.restore_panel(keyboard=True)
    for key in ("UPBRPY_REDUCE_MOTION", "UPBLAB_REDUCE_MOTION"):
        with monkeypatch.context() as patch:
            patch.delenv("UPBRPY_REDUCE_MOTION", raising=False)
            patch.delenv("UPBLAB_REDUCE_MOTION", raising=False)
            patch.setenv(key, "1")
            assert panels.reduced_motion()
            area.toggle_panel(panel)
            assert area._animation is None
            area.restore_panel()
    monkeypatch.delenv("UPBRPY_REDUCE_MOTION", raising=False)
    monkeypatch.delenv("UPBLAB_REDUCE_MOTION", raising=False)
    hints = SimpleNamespace(accessibility=lambda: SimpleNamespace(
        motionPreference=lambda: SimpleNamespace(name="ReducedMotion")))
    monkeypatch.setattr(app, "styleHints", lambda: hints)
    assert panels.reduced_motion()
