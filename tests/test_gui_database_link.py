"""Offline database proposal confirmation and review at laptop dimensions."""
import os
from pathlib import Path

import pytest

from gui_support import require_gui

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
require_gui()
from PySide6 import QtCore, QtTest
from test_gui_import import _layout_problems
from test_gui_steps import app, settle
from test_tracer_completion import public_registry, incomplete_registry

DATA = Path(__file__).parent / 'data'


@pytest.mark.parametrize('valid', [True, False])
def test_public_composition_marks_derivations_or_reports_refusal(app, request, valid):
    request.getfixturevalue('public_registry' if valid else 'incomplete_registry')
    from idtims_app.window import MainWindow

    window = MainWindow(confirm_close=False)
    try:
        window.show()
        assert window.open_paths([str(DATA / 'synthetic_database_link.fractions.csv')]) is None
        assert window.session.set_value(0, 'Spike Solution', 'ET535/master/v3') is None
        window.on_session_changed()
        assert window.set_step(1)
        page = window.tracer_page
        page.select_fraction('z1')
        settle()
        assert 'ET535/master/v3' in page.tracer_source.text()
        table = page.tracer_table
        if valid:
            headers = [table.horizontalHeaderItem(c) for c in range(table.columnCount())]
            for quantity in ('207Pb/206Pb', '204Pb/206Pb'):
                header = next(h for h in headers if h.text().startswith(quantity))
                assert header.text().endswith('\n(BSU sheet)')
                assert quantity + ' = ' in header.toolTip()
                assert 'BSU sheet' in header.toolTip()
                assert 'McLean et al. (2011)' in header.toolTip()
                assert header.toolTip() in page.tracer_source.toolTip()
            header = next(h for h in headers if h.text().startswith('238U/233U'))
            assert header.text().endswith('\n(derived)')
            assert '238U/233U derived as ' in header.toolTip()
            assert 'zero covariance' in header.toolTip()
            assert 'McLean et al. (2011)' in header.toolTip()
            assert header.toolTip() in page.tracer_source.toolTip()
            assert 'BSU sheet' in page.tracer_source.toolTip()
            assert 'zero covariance' in page.tracer_source.toolTip()
            assert page.confirm_database_button.isEnabled()
        else:
            assert table.columnCount() == 0
            assert 'has no uncertainty for 204Pb/205Pb' in page.tracer_source.text()
            assert not page.confirm_database_button.isEnabled()
    finally:
        window.close()
        window.deleteLater()
        settle()


@pytest.mark.parametrize('size', [(1512, 982), (1024, 640)])
def test_database_confirm_and_review_marker(app, size, tmp_path):
    from idtims_app.window import MainWindow

    window = MainWindow(confirm_close=False)
    try:
        window.resize(*size)
        window.show()
        assert window.open_paths([str(DATA / 'synthetic_database_link.fractions.csv')]) is None
        assert window.load_settings(str(DATA.parent.parent / 'examples/synthetic_settings.json')) is None
        window._confirm_all('missing_oxide')
        window.session.set_strict_covariance(False)
        window.on_session_changed()
        assert window.set_step(1)
        page = window.tracer_page
        page.select_fraction('z1')
        settle()
        assert 'ET535/unassigned/v3' in page.tracer_source.text()
        assert 'legacy_csv' in page.tracer_source.text()
        assert page.tracer_table.columnCount() > 0
        assert 'z1' not in window.session.ready_ids()
        assert page.confirm_database_button.isVisible() and page.confirm_database_button.isEnabled()
        assert _layout_problems(window) == []
        QtTest.QTest.mouseClick(page.confirm_database_button, QtCore.Qt.MouseButton.LeftButton)
        settle()
        assert 'z1' in window.session.ready_ids()
        assert 'overrides project tracer version' in page.database_spike_label.text()
        page.select_fraction('z2')
        QtTest.QTest.mouseClick(page.confirm_database_button, QtCore.Qt.MouseButton.LeftButton)
        settle()
        window.session.reduce()
        window.on_session_changed()
        assert window.set_step(6)
        settle()
        review = window.review_page
        model = review.model
        columns = {key: i for i, (key, _) in enumerate(model.columns)}
        marker = model.index(0, columns['id:Database link'])
        assert model.data(marker) == 'Linked to database'
        tip = model.data(marker, QtCore.Qt.ItemDataRole.ToolTipRole)
        assert 'Database Read At: 2026-11-20T10:00:00-07:00' in tip
        assert 'upbdb.example.invalid' in tip
        assert model.data(model.index(2, columns['id:Database link'])) == ''
        assert model.data(model.index(0, columns['id:Beaker'])) == 'K9 · Krogh'
        assert model.data(model.index(1, columns['id:Source Mount'])) == 'M1; M2'
        anneal = model.index(0, columns['id:Annealing'])
        assert '900 °C, 60 h' in model.data(anneal, QtCore.Qt.ItemDataRole.ToolTipRole)
        assert _layout_problems(window) == []
        assert window.size() == QtCore.QSize(*size)
        assert window.grab().save(str(tmp_path / 'linked-review.png'))
    finally:
        window.close()
        window.deleteLater()
        settle()
