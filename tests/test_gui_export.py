"""Export fits, project file actions and debounced autosave recovery offscreen."""
import json
import os
import csv
import re

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')
pytest.importorskip('pyqtgraph')
from PySide6 import QtCore, QtTest, QtWidgets

from idtims_app import autosave, project
from test_gui_import import _layout_problems
from test_gui_review import review_window
from test_gui_steps import app, settle, _run_app, TEMPLATE, TEMPLATE_SETTINGS


@pytest.mark.parametrize('diagnostic', [False, True])
def test_footnote_order_in_preview_csv_and_xlsx(review_window, tmp_path, diagnostic):
    from openpyxl import load_workbook

    window = review_window(path=TEMPLATE, settings=TEMPLATE_SETTINGS, diagnostic=diagnostic)
    assert window.set_step(7)
    page = window.export_page
    expected = list('abcdefghijkl' if diagnostic else 'abcdefghijk')
    preview = page.notes_view.toPlainText()
    assert re.findall(r'^\(([a-z])\)', preview, re.MULTILINE) == expected
    assert [letter for letter, _ in page.notes] == expected
    assert 'U oxide' in dict(page.notes)['l' if diagnostic else 'k']
    if diagnostic:
        assert 'Diagnostic covariance mode' in dict(page.notes)['k']
    csv_path, xlsx_path = tmp_path / 'table.csv', tmp_path / 'table.xlsx'
    assert page.save_to(csv_path, 'bsu_csv')
    assert page.save_to(xlsx_path, 'bsu_xlsx')
    csv_notes = [row for row in csv.reader(csv_path.open())
                 if row and re.fullmatch(r'\([a-z]\)', row[0])]
    sheet = load_workbook(xlsx_path).active
    xlsx_notes = [row[0] for row in sheet.iter_rows(values_only=True)
                  if isinstance(row[0], str) and re.match(r'^\([a-z]\) ', row[0])]
    assert [row[0][1] for row in csv_notes] == expected
    assert [text[1] for text in xlsx_notes] == expected
    assert csv_notes == [[f'({letter})', text] for letter, text in page.notes]
    assert xlsx_notes == [f'({letter}) {text}' for letter, text in page.notes]
    for output in (preview, csv_path.read_text(), '\n'.join(xlsx_notes)):
        for phrase in ('BSU spreadsheet', 'formula errors', 'BSU_SHEET_NOTES'):
            assert phrase.lower() not in output.lower()


@pytest.mark.parametrize('size', [(1280, 800), (1024, 640)])
def test_export_fits_and_save_completes(review_window, size, tmp_path):
    window = review_window(size=size)
    assert window.set_step(7)
    settle()
    page = window.export_page
    assert page.isVisible() and page.preview.rowCount() > 2
    assert window.minimumSizeHint().width() <= size[0]
    assert window.minimumSizeHint().height() <= size[1]
    assert _layout_problems(window) == []
    assert 'Diagnostic covariance mode' in page.notes_view.toPlainText()
    assert not window.session.step_complete(7)
    assert page.save_to(tmp_path / 'output.csv', 'bsu_csv')
    assert window.session.step_complete(7)
    page.off_check.setChecked(True)
    page.discordance_check.setChecked(True)
    page.th_check.setChecked(False)
    assert '% discordance' in page.table
    assert page.save_to(tmp_path / 'output.xlsx', 'bsu_xlsx')
    assert not page.save_to(tmp_path / 'nonexistent/output.csv', 'bsu_csv')


def test_project_cli_content_routing(tmp_path):
    saved, png = tmp_path / 'saved.idtr', tmp_path / 'export.png'
    result = _run_app(str(TEMPLATE), '--settings', str(TEMPLATE_SETTINGS), '--confirm-no-oxide',
                      '--reduce', '--step', '8', '--exclude', 'z3', '--save-project', str(saved),
                      '--export', str(png), settings_dir=tmp_path)
    assert result.returncode == 0, result.stderr
    assert saved.exists() and png.stat().st_size > 10_000
    # JSON in a CSV-named file must still open as a project, with automatic recomputation.
    renamed = tmp_path / 'actually-project.csv'
    renamed.write_bytes(saved.read_bytes())
    result = _run_app(str(renamed), '--step', '8', '--export', str(png), settings_dir=tmp_path)
    assert result.returncode == 0, result.stderr
    assert png.stat().st_size > 10_000
    result = _run_app('--print-engine-fingerprint', settings_dir=tmp_path)
    report = json.loads(result.stdout)
    assert report['engine'] == project.engine_fingerprint()
    assert report['frozen_code_first'] is None and report['frozen_code_second'] is None
    assert report['match'] and not report['frozen']
    result = _run_app('--print-project-status', str(saved), settings_dir=tmp_path)
    assert result.returncode == 0, result.stderr
    status = json.loads(result.stdout)
    assert status == {'engine_note': '', 'reduced': ['z2', 'z3', 'z4', 'z5'],
                      'included': ['z2', 'z4', 'z5']}


def test_gui_autosave_recovery_removed_on_save(review_window, tmp_path, monkeypatch):
    monkeypatch.setenv('IDTIMS_AUTOSAVE_DIR', str(tmp_path / 'autosave'))
    window = review_window()
    target = tmp_path / 'session.idtr'
    assert window.save_project(target)
    window.session.set_value(0, 'Sample', 'Recovered edit')
    window.review_page.set_included('z3', False)
    window.on_session_changed()
    assert window.isWindowModified()
    sidecar = autosave.path_for(window.session)
    assert window._autosave_timer.isActive()
    QtTest.QTest.qWait(2100)
    window._autosave_future.result(timeout=5)
    assert sidecar.exists()
    # Opening saved data offers the newer edit inline, without applying it.
    assert window.open_paths([target]) is None
    settle()
    assert window.recovery_bar.isVisible()
    assert window.session.value(0, 'Sample') != 'Recovered edit'
    assert not window._autosave_timer.isActive()
    window.restore_button.click()
    settle()
    assert not window.recovery_bar.isVisible()
    assert window.session.value(0, 'Sample') == 'Recovered edit'
    assert not window.session.is_included('z3')
    assert window.session.reduction_current and window.isWindowModified()
    assert window.save_project()
    window._autosave_executor.submit(lambda: None).result(timeout=5)
    assert not sidecar.exists() and not window.isWindowModified()
    assert 'session' in window.windowTitle()


def test_recovery_discard_and_engine_note(review_window, tmp_path, monkeypatch):
    monkeypatch.setenv('IDTIMS_AUTOSAVE_DIR', str(tmp_path / 'autosave'))
    window = review_window()
    target = tmp_path / 'session.idtr'
    assert window.save_project(target)
    window.session.set_value(0, 'Sample', 'Discarded edit')
    sidecar = autosave.save(window.session)
    assert window.open_paths([target]) is None
    window.discard_button.click()
    assert not sidecar.exists() and not window.recovery_bar.isVisible()
    data = project.read(target)
    data['engine_fingerprint'] = 'older engine'
    project.write(data, target)
    assert window.open_paths([target]) is None
    assert 'different engine version' in window.window_banner.text()


def test_one_save_discard_cancel_guard_for_new_and_close(review_window, monkeypatch, tmp_path):
    window = review_window()
    window.confirm_close = True
    calls = []
    answer = QtWidgets.QMessageBox.StandardButton.Cancel
    def question(*args):
        calls.append(args)
        return answer
    monkeypatch.setattr(QtWidgets.QMessageBox, 'question', question)
    assert window.new_project() is False
    assert len(calls) == 1 and window.session.has_table
    assert not window.close()
    assert len(calls) == 2
    answer = QtWidgets.QMessageBox.StandardButton.Save
    target = tmp_path / 'guard.idtr'
    monkeypatch.setattr(window, 'save_project_as', lambda: window.save_project(target))
    assert window.new_project() is True
    assert len(calls) == 3 and target.exists() and not window.session.has_table
    window.confirm_close = False


def test_weighted_zoom_survives_toggle(review_window):
    window = review_window()
    ranked = window.review_page.weighted.plot
    vb = ranked.getPlotItem().vb
    vb.setRange(xRange=(2, 5), yRange=(100, 110), padding=0)
    before = vb.viewRange()
    window.review_page.set_included('z3', False)
    assert vb.viewRange() == before
    window.session.mark_project_saved()
    window.review_page.concordia.canvas.plot.vb.setRange(xRange=(1, 2), yRange=(3, 4), padding=0)
    assert not window.session.has_unsaved_changes()


@pytest.mark.parametrize('save', [True, False], ids=['save', 'discard'])
def test_reopen_same_project_uses_guard_decision(review_window, tmp_path, monkeypatch, save):
    window = review_window()
    target = tmp_path / 'same.idtr'
    assert window.save_project(target)
    previous = window.session.value(0, 'Sample')
    window.session.set_value(0, 'Sample', 'Latest edit')
    window.on_session_changed()
    window.confirm_close = True
    calls = []
    def question(*args):
        calls.append(args)
        return (QtWidgets.QMessageBox.StandardButton.Save if save
                else QtWidgets.QMessageBox.StandardButton.Discard)
    monkeypatch.setattr(QtWidgets.QMessageBox, 'question', question)
    assert window.open_paths([target]) is None
    assert len(calls) == 1
    assert window.session.value(0, 'Sample') == ('Latest edit' if save else previous)
    assert not window.isWindowModified()
    window.confirm_close = False
