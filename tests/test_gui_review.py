"""Offscreen GUI tests of step 7, Review.

Built like tests/test_gui_steps.py (copied `build_application`, no
pytest-qt); skipped when PySide6 or pyqtgraph is not installed.
"""
import math
import os
import sys
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6 import QtCore, QtGui, QtTest  # noqa: E402
import pyqtgraph as pg  # noqa: E402

from IDTIMS_UPbRPy import dates  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_gui_import import _layout_problems  # noqa: E402
from test_gui_steps import (SYNTHETIC, SYNTHETIC_SETTINGS, TEMPLATE, TEMPLATE_SETTINGS,  # noqa: E402,F401
                            _run_app, app, settle)

CHECK = QtCore.Qt.ItemDataRole.CheckStateRole
CONTROL = QtCore.Qt.KeyboardModifier.ControlModifier


@pytest.fixture
def review_window(app):  # noqa: F811
    from idtims_app.window import MainWindow

    windows = []

    def factory(path=SYNTHETIC, settings=SYNTHETIC_SETTINGS, diagnostic=True, size=(1280, 800)):
        window = MainWindow(confirm_close=False)
        window.resize(*size)
        window.show()
        settle()
        assert window.open_paths([str(path)]) is None
        window._confirm_all("missing_oxide")
        assert window.load_settings(str(settings)) is None
        if diagnostic:
            window.session.set_strict_covariance(False)
            window.on_session_changed()
        assert window.set_step(5)
        assert window.reduce_page.run_sync() is not None
        assert window.set_step(6)
        settle()
        windows.append(window)
        return window

    yield factory
    for window in windows:
        window.close()
        window.deleteLater()
    settle()


def expected(window, excluded, kind):
    grains = window.session.reduction.grains
    include = {g.id for g in grains} - set(excluded)
    return dates.sample_dates(grains, include=include, kinds=(kind,))[kind]


def check_state(page, fid):
    model = page.model
    return QtCore.Qt.CheckState(model.data(model.index(model.row_of(fid), 1), CHECK))


@pytest.mark.parametrize('diagnostic', [False, True])
def test_three_headers_share_fraction_summary(review_window, diagnostic):
    window = review_window(path=TEMPLATE, settings=TEMPLATE_SETTINGS, diagnostic=diagnostic)
    for state in ('current', 'switched off', 'stale'):
        if state == 'switched off':
            window.review_page.set_included('z3', False)
        elif state == 'stale':
            window.session.settings_edited()
        window.on_session_changed()
        settle()
        summary = window.session.summary_text()
        assert window.status_label.text() == summary
        assert window.issues_panel.summary.text() == summary
        assert window.review_page.summary.toolTip() == summary


def test_panel_mean_equals_sample_dates(review_window):
    window = review_window()
    page = window.review_page
    assert page.isVisible() and page.diagnostic_banner.isVisible()
    assert page.weighted.kind_combo.currentText() == "206Pb/238U (Th-corrected)"
    for excluded in (set(), {"z3"}, {"z1", "z7", "z10b"}, {"z2", "z4", "z6", "z8", "z9a"}):
        window.session.excluded_fractions.clear()
        for fid in excluded:
            page.set_included(fid, False)
        for kind in dates.DATE_KINDS:
            page.weighted.kind_combo.setCurrentText(kind)
            settle(1)
            assert page.current_sample() == expected(window, excluded, kind), (excluded, kind)
            result = page.current_sample().result
            text = page.weighted.result_label.text()
            assert f"{result.mean:.3f} ± {2 * result.sigma:.3f} Ma" in text
            assert f"n = {result.n} of 12" in text
            assert (f"{2 * result.sigma_expanded:.3f}" in text) == (result.mswd > 1)


def test_toggle_in_table_updates_plots_and_mean(review_window):
    window = review_window()
    page = window.review_page
    kind = window.session.review_date_kind()
    model = page.model
    index = model.index(model.row_of("z3"), 1)
    assert model.setData(index, QtCore.Qt.CheckState.Unchecked.value, CHECK)
    settle(1)
    assert window.session.excluded_fractions == {"z3"}
    assert check_state(page, "z3") == QtCore.Qt.CheckState.Unchecked
    assert page.concordia.canvas.excluded == {"z3"}
    assert page.weighted.plot.excluded == {"z3"}
    assert page.current_sample() == expected(window, {"z3"}, kind)
    assert "z3" not in page.current_sample().fraction_ids
    assert model.setData(index, QtCore.Qt.CheckState.Checked.value, CHECK)
    assert page.current_sample() == expected(window, set(), kind)


def test_toggle_in_plots_updates_table_and_mean(review_window):
    window = review_window()
    page = window.review_page
    kind = window.session.review_date_kind()
    canvas = page.concordia.canvas
    canvas.click_at(canvas.scene_position("z5"), CONTROL)
    settle(1)
    assert check_state(page, "z5") == QtCore.Qt.CheckState.Unchecked
    assert page.current_sample() == expected(window, {"z5"}, kind)
    # A plain click selects (the table row follows); E switches the selection.
    canvas.click_at(canvas.scene_position("z7"), QtCore.Qt.KeyboardModifier.NoModifier)
    assert page.selected_id == "z7"
    assert page.model.rows[page.table.currentIndex().row()].fraction_id == "z7"
    QtTest.QTest.keyClick(canvas, QtCore.Qt.Key.Key_E)
    settle(1)
    assert window.session.excluded_fractions == {"z5", "z7"}
    assert page.current_sample() == expected(window, {"z5", "z7"}, kind)
    # The ranked plot switches too.
    ranked = page.weighted.plot
    ranked.click_at(ranked.scene_position("z5"), CONTROL)
    settle(1)
    assert check_state(page, "z5") == QtCore.Qt.CheckState.Checked
    assert canvas.excluded == {"z7"}
    assert page.current_sample() == expected(window, {"z7"}, kind)


def test_include_set_survives_re_reduction_and_unlocks_export(review_window):
    window = review_window()
    page = window.review_page
    page.set_included("z2", False)
    assert window.session.step_complete(6) and window.session.unlocked(7)
    assert window.set_step(5)
    window.reduce_page.run_sync()
    assert window.set_step(6)
    settle()
    assert check_state(page, "z2") == QtCore.Qt.CheckState.Unchecked
    for fid in window.session.included_ids():
        page.set_included(fid, False)
    settle(1)
    assert not window.session.unlocked(7)
    assert page.current_sample().result is None
    page.include_all()
    assert window.set_step(7)


def test_diagram_and_th_toggle(review_window):
    window = review_window()
    page = window.review_page
    canvas = page.concordia.canvas
    grain = window.session.reduction.grains[0]
    assert page.concordia.th_check.isEnabled() and page.concordia.th_check.isChecked()
    assert canvas.geometry["z1"][1] == grain.R68r_Th
    page.concordia.th_check.setChecked(False)
    assert canvas.geometry["z1"][:2] == (grain.R75r, grain.R68r)
    page.concordia.buttons["tw"].click()
    assert window.session.review_diagram == "tw"
    assert canvas.geometry["z1"][0] == pytest.approx(1 / grain.R68r, rel=1e-15)
    assert canvas.plot.getAxis("bottom").labelText == "238U/206Pb"
    assert "z1" in canvas.hover_html("z1")


@pytest.mark.parametrize("size", [(1280, 800), (1024, 640)])
def test_review_fits(review_window, size):
    window = review_window(size=size)
    settle()
    assert window.pages.currentWidget() is window.review_page
    assert window.minimumSizeHint().width() <= size[0]
    assert window.minimumSizeHint().height() <= size[1]
    assert _layout_problems(window) == []
    window.review_page.table_toggle.setChecked(True)
    settle()
    assert not window.review_page.table.isVisible()
    assert _layout_problems(window) == []


def test_template_strict_greys_z1_z6_and_means_z2_to_z5(review_window):
    window = review_window(path=TEMPLATE, settings=TEMPLATE_SETTINGS, diagnostic=False)
    page = window.review_page
    model = page.model
    assert not page.diagnostic_banner.isVisible()
    note = [key for key, _ in model.columns].index("note")
    for fid in ("z1", "z6"):
        row = model.row_of(fid)
        assert model.data(model.index(row, 0), CHECK) is None
        assert not model.flags(model.index(row, 0)) & QtCore.Qt.ItemFlag.ItemIsUserCheckable
        assert model.data(model.index(row, note)).startswith("Impossible covariance")
        assert model.data(model.index(row, 0), QtCore.Qt.ItemDataRole.ForegroundRole) is not None
        assert model.data(model.index(row, 0), QtCore.Qt.ItemDataRole.DecorationRole) is not None
    sample = page.current_sample()
    assert sample.fraction_ids == ("z2", "z3", "z4", "z5")
    assert sample == expected(window, set(), "206Pb/238U (Th-corrected)")
    assert set(page.concordia.canvas.geometry) == {"z2", "z3", "z4", "z5"}


def age_labels(canvas):
    return [item for item in canvas._label_items if isinstance(item, pg.TextItem)]


def assert_visible_age_labels(canvas):
    from idtims_app.widgets.concordia import nice_step

    labels = age_labels(canvas)
    assert len(labels) >= 2
    bounds = canvas.plot.vb.sceneBoundingRect()
    for i, label in enumerate(labels):
        assert label.isVisible()
        assert bounds.contains(label.sceneBoundingRect())
        assert all(not label.sceneBoundingRect().intersects(other.sceneBoundingRect())
                   for other in labels[i + 1:])
    # Every label has a leader, and rejected candidates leave no orphan ticks.
    assert len(canvas._label_items) == 2 * len(labels)
    ages = sorted(float(label.toPlainText().removesuffix(" Ma")) for label in labels)
    lo, hi = canvas._visible_ages()
    step = nice_step(hi - lo, target=5)
    dates = [getattr(row.grain, "t68_Th_corr" if canvas.th else "t68") for row in canvas.rows]
    # Check the specific bracketing ticks, clamped to the ticks in this view.
    first, last = math.ceil(lo / step) * step, math.floor(hi / step) * step
    for tick in (math.floor(min(dates) / step) * step, math.ceil(max(dates) / step) * step):
        assert min(abs(age - max(first, min(tick, last))) for age in ages) < step * 1e-6
    return ages


@pytest.mark.parametrize("diagram", ["wetherill", "tw"])
@pytest.mark.parametrize("th", [True, False])
def test_template_age_labels_bracket_data_and_follow_view(review_window, diagram, th):
    window = review_window(path=TEMPLATE, settings=TEMPLATE_SETTINGS, diagnostic=False)
    page = window.review_page
    assert_visible_age_labels(page.concordia.canvas)  # First draw, before any range change.
    page.concordia.buttons[diagram].click()
    page.concordia.th_check.setChecked(th)
    settle()
    canvas = page.concordia.canvas
    ages = assert_visible_age_labels(canvas)
    dates = [getattr(row.grain, "t68_Th_corr" if th else "t68") for row in canvas.rows]
    assert ages[0] <= min(dates)
    assert ages[-1] >= max(dates)
    initial_step = min(np.diff(ages))
    vb = canvas.plot.vb
    center = QtCore.QPointF(float(np.mean([p[1] for p in canvas.points])),
                           float(np.mean([p[2] for p in canvas.points])))
    vb.scaleBy((0.25, 0.25), center=center)
    settle()
    zoomed_ages = assert_visible_age_labels(canvas)
    assert min(np.diff(zoomed_ages)) < initial_step
    assert zoomed_ages != ages
    # A pan must also re-place the labels, without calling the layout directly.
    (x0, x1), (y0, y1) = vb.viewRange()
    vb.translateBy(x=(x1 - x0) * 0.15, y=(y1 - y0) * 0.15)
    settle()
    assert_visible_age_labels(canvas)
    canvas.restore_default_view()
    settle()
    assert assert_visible_age_labels(canvas) == ages
    vb.autoRange()
    settle()
    assert_visible_age_labels(canvas)


@pytest.mark.parametrize("diagram", ["wetherill", "tw"])
def test_synthetic_diagnostic_age_labels(review_window, diagram):
    window = review_window()
    window.review_page.concordia.buttons[diagram].click()
    settle()
    assert_visible_age_labels(window.review_page.concordia.canvas)


@pytest.mark.parametrize("diagram", ["wetherill", "tw"])
def test_bracketing_labels_survive_unavoidable_ellipse_overlap(review_window, diagram):
    window = review_window(path=TEMPLATE, settings=TEMPLATE_SETTINGS, diagnostic=False)
    window.review_page.concordia.buttons[diagram].click()
    settle()
    canvas = window.review_page.concordia.canvas
    ages = assert_visible_age_labels(canvas)
    dates = [row.grain.t68_Th_corr for row in canvas.rows]
    below = max(age for age in ages if age <= min(dates))
    above = min(age for age in ages if age >= max(dates))
    # Cover the entire view with a polygon: no candidate can avoid it.
    (x0, x1), (y0, y1) = canvas.plot.vb.viewRange()
    canvas.polygons = {"covered": (np.array([x0, x1, x1, x0]),
                                    np.array([y0, y0, y1, y1]))}
    canvas._schedule_labels()
    settle()
    assert assert_visible_age_labels(canvas) == [below, above]


def test_label_collision_uses_polygon_not_bounding_box():
    from idtims_app.widgets.concordia import _path_overlap, age_label

    path = QtGui.QPainterPath()
    path.addPolygon(QtGui.QPolygonF([QtCore.QPointF(0, 0), QtCore.QPointF(100, 98),
                                    QtCore.QPointF(100, 100), QtCore.QPointF(0, 2)]))
    path.closeSubpath()
    clear = QtCore.QRectF(0, 80, 20, 20)
    assert path.boundingRect().intersects(clear)
    assert _path_overlap(path, clear) == 0
    assert _path_overlap(path, QtCore.QRectF(40, 40, 20, 20)) > 0
    assert age_label(507.5, 0.5) == "507.5 Ma"
    assert age_label(507.25, 0.25) == "507.25 Ma"
    assert age_label(507.5, 2.5) == "507.5 Ma"


def test_export_command_reaches_review(tmp_path):
    png = tmp_path / "review.png"
    result = _run_app(str(TEMPLATE), "--settings", str(TEMPLATE_SETTINGS), "--confirm-no-oxide",
                      "--reduce", "--step", "7", "--review-mode", "tw", "--review-th", "off",
                      "--date-kind", "207Pb/206Pb", "--exclude", "z3,z5",
                      "--export", str(png), settings_dir=tmp_path)
    assert result.returncode == 0, result.stderr
    assert png.stat().st_size > 10_000
    bad = _run_app(str(TEMPLATE), "--settings", str(TEMPLATE_SETTINGS), "--confirm-no-oxide",
                   "--reduce", "--step", "7", "--exclude", "z9", "--date-kind", "nope",
                   "--export", str(tmp_path / "bad.png"), settings_dir=tmp_path)
    assert bad.returncode == 1
    assert "no reduced fraction 'z9'" in bad.stderr and "--date-kind" in bad.stderr
