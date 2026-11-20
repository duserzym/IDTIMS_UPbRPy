"""Qt-free replay, provenance, atomic-write and export contract checks."""
import csv
import io
import shutil
import struct
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from IDTIMS_UPbRPy import export
from IDTIMS_UPbRPy.fractions import read_fractions
from idtims_app import autosave, project, reporting
from idtims_app.services import Session
from test_app_reduction import SYNTHETIC, SYNTHETIC_SETTINGS, TEMPLATE, TEMPLATE_SETTINGS, session_for


def assert_identical(a, b):
    """Every attribute, including non-numeric provenance and covariance arrays."""
    assert type(a) is type(b), (type(a), type(b))
    if isinstance(a, np.ndarray):
        assert a.dtype == b.dtype and a.shape == b.shape
        assert a.tobytes() == b.tobytes()
    elif isinstance(a, dict):
        assert a.keys() == b.keys()
        for key in a:
            assert_identical(a[key], b[key])
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b)
        for x, y in zip(a, b):
            assert_identical(x, y)
    elif isinstance(a, float):
        assert struct.pack('d', a) == struct.pack('d', b)
    else:
        assert a == b


@pytest.mark.parametrize('path,settings,strict', [(SYNTHETIC, SYNTHETIC_SETTINGS, False),
                                                   (TEMPLATE, TEMPLATE_SETTINGS, True)])
def test_project_round_trip_every_attribute(tmp_path, path, settings, strict):
    session = session_for(path, settings, strict=strict)
    session.set_value(0, 'Sample', 'Edited sample – embedded')
    session.excluded_fractions = {'z3', 'z7'} if not strict else {'z3'}
    session.review_kind = '207Pb/206Pb'
    session.review_diagram = 'tw'
    session.review_th_ratios = False
    session.reduce()
    target = session.save_project(tmp_path / 'project.idtr')
    doc = project.read(target)
    assert doc['format'] == project.FORMAT_NAME and doc['version'] == 1
    assert doc['origin'] is None and 'results' not in doc and 'grains' not in doc
    assert doc['sources'][0]['name'] == path.name
    import hashlib
    assert doc['sources'][0]['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    # Reopen without any dependence on the original source path.
    restored = project.restore(doc)
    assert restored.settings.to_dict() == session.settings.to_dict()
    assert restored.strict_covariance is strict
    assert restored.excluded_fractions == session.excluded_fractions
    assert restored.included_ids() == session.included_ids()
    assert restored.table.no_oxide_confirmed == session.table.no_oxide_confirmed
    assert restored.review_kind == session.review_kind
    assert restored.review_diagram == 'tw' and restored.review_th_ratios is False
    assert restored.scientific_project_fingerprint() == session.scientific_project_fingerprint()
    for a, b in zip(session.reduction.results, restored.reduction.results):
        assert (a.fraction_id, a.status, a.reason) == (b.fraction_id, b.status, b.reason)
        if a.reduced:
            assert_identical(vars(a.grain), vars(b.grain))
    assert not restored.has_unsaved_changes()


@pytest.fixture
def session():
    return session_for(TEMPLATE, TEMPLATE_SETTINGS, strict=True)


@pytest.mark.parametrize('key,value,match', [
    ('format', 'Other project', 'not an ID-TIMS'),
    ('version', 2, 'version 2'), ('version', None, 'version'),
    ('fractions_csv', None, 'fraction CSV'), ('settings', [], 'settings'),
    ('covariance_mode', 'guess', 'covariance mode'), ('include', 'z2', 'list'),
    ('review', {}, 'concordia mode'), ('origin', [], 'origin')])
def test_validate_readable_errors(session, key, value, match):
    doc = project.document(session)
    doc[key] = value
    with pytest.raises(ValueError, match=match):
        project.validate(doc)


def test_unknown_fraction_decision_rejected(session):
    doc = project.document(session)
    doc['no_oxide_confirmed'].append('missing')
    with pytest.raises(ValueError, match='unknown fractions'):
        project.restore(doc)


@pytest.mark.parametrize('stage', ['serialize', 'replace'])
def test_atomic_failure_keeps_old_file(session, tmp_path, monkeypatch, stage):
    target = tmp_path / 'atomic.idtr'
    session.save_project(target)
    old = target.read_bytes()
    session.set_value(0, 'Sample', 'New content')
    def fail(*args, **kwargs):
        if stage == 'serialize':
            args[1].write('partial JSON')
        raise OSError('simulated write failure')
    if stage == 'serialize':
        monkeypatch.setattr(project.json, 'dump', fail)
    else:
        monkeypatch.setattr(project.os, 'replace', fail)
    with pytest.raises(OSError, match='simulated'):
        session.save_project(target)
    assert target.read_bytes() == old
    assert list(tmp_path.iterdir()) == [target]
    assert session.has_unsaved_changes()


def test_scientific_changes_and_undo(session, tmp_path):
    assert session.has_unsaved_changes()
    session.save_project(tmp_path / 'saved.idtr')
    assert not session.has_unsaved_changes()
    # Arbitrary UI state is deliberately outside the document.
    session.concordia_zoom = (1, 2, 3, 4)
    assert not session.has_unsaved_changes()
    session.set_included('z3', False)
    assert session.has_unsaved_changes()
    session.set_included('z3', True)
    assert not session.has_unsaved_changes()
    session.settings.th_correction.Th_U_magma += 1
    assert session.has_unsaved_changes()


def test_engine_source_fingerprint_changes_only_in_copy(tmp_path):
    import hashlib
    import IDTIMS_UPbRPy
    root = Path(IDTIMS_UPbRPy.__file__).parent
    # Previous source implementation: sorted relative paths, NUL, exact .py bytes.
    previous = hashlib.sha256()
    for path in sorted(root.rglob('*.py'), key=lambda p: p.relative_to(root).as_posix()):
        previous.update(path.relative_to(root).as_posix().encode('utf-8') + b'\0'
                        + path.read_bytes())
    assert project.engine_fingerprint() == previous.hexdigest()
    clone = tmp_path / 'engine'
    shutil.copytree(root, clone)
    assert project.engine_fingerprint() == project.engine_fingerprint()
    assert project.engine_fingerprint(clone) == project.engine_fingerprint()
    with (clone / 'export.py').open('ab') as stream:
        stream.write(b'\n# fingerprint test\n')
    assert project.engine_fingerprint(clone) != project.engine_fingerprint()


def test_frozen_fingerprint_uses_raw_pyz_not_loaded_objects(monkeypatch):
    import IDTIMS_UPbRPy
    calls = []
    class Archive:
        toc = {'other': (), 'IDTIMS_UPbRPy.export': (), 'IDTIMS_UPbRPy': ()}
        def extract(self, name, *, raw):
            assert raw is True
            calls.append(name)
            return name.encode()
    monkeypatch.setattr(IDTIMS_UPbRPy, '__spec__', SimpleNamespace(
        loader=SimpleNamespace(_pyz_archive=Archive())))
    assert project.frozen_code_fingerprint() == project.frozen_code_fingerprint()
    assert calls == ['IDTIMS_UPbRPy', 'IDTIMS_UPbRPy.export'] * 2


def test_frozen_engine_uses_bundled_source_fingerprint(tmp_path, monkeypatch):
    monkeypatch.setattr(project.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(project, '__file__', str(tmp_path / 'project.py'))
    bundled = tmp_path / 'engine_source_fingerprint.txt'
    bundled.write_text('a' * 64 + '\n')
    assert project.engine_fingerprint() == 'a' * 64


def test_frozen_engine_missing_source_fingerprint_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(project.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(project, '__file__', str(tmp_path / 'project.py'))
    with pytest.raises(RuntimeError, match='missing the bundled engine source fingerprint'):
        project.engine_fingerprint()


def test_engine_change_note_and_disk_results_ignored(session):
    doc = project.document(session)
    doc['engine_fingerprint'] = 'different'
    doc['results'] = {'z2': 'untrusted garbage'}
    restored = project.restore(doc)
    assert restored.reduction.grains and 'different engine version' in restored.engine_note


def test_unconfirmed_spike_and_confirmed_types_survive(session):
    row = session.row_of('z2')
    session.set_value(row, 'Spike Type', '')
    doc = project.document(session)
    restored = project.restore(doc)
    assert restored.table.inferred_spike_types['z2'] == '2535'
    restored.confirm_spike_type('z2')
    again = project.restore(project.document(restored))
    assert 'z2' not in again.table.inferred_spike_types
    assert again.value(row, 'Spike Type') == '2535'


@pytest.mark.parametrize('strict', [True, False])
def test_bsu_csv_xlsx_match_engine_and_notes(tmp_path, strict):
    openpyxl = pytest.importorskip('openpyxl')
    session = session_for(TEMPLATE, TEMPLATE_SETTINGS, strict=strict)
    session.reduce()
    session.set_included('z3', False)
    options = dict(th_corrected=True, discordance=True)
    table, notes = reporting.bsu(session, **options)
    expected = export.bsu_table([g for g in session.reduction.grains if g.id != 'z3'],
                                identifiers=session.fraction_identifiers(),
                                th_corrected_dates=True, th_corrected_ratios=True,
                                include_discordance=True)
    pd.testing.assert_frame_equal(table, expected, check_exact=True)
    csv_path, xlsx_path = tmp_path / 'bsu.csv', tmp_path / 'bsu.xlsx'
    reporting.save(session, csv_path, 'bsu_csv', **options)
    reporting.save(session, xlsx_path, 'bsu_xlsx', **options)
    text = csv_path.read_text()
    numeric = text.split('\n\n', 1)[0]
    loaded = pd.read_csv(io.StringIO(numeric), float_precision='round_trip')
    pd.testing.assert_frame_equal(loaded, expected, check_dtype=False, check_exact=True)
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[len(table) + 1] == []
    assert rows[len(table) + 2:] == [[f'({letter})', note] for letter, note in notes]
    sheet = openpyxl.load_workbook(xlsx_path).active
    assert sheet.merged_cells.ranges
    for row, values in enumerate(table.itertuples(index=False, name=None), 4):
        for col, value in enumerate(values, 1):
            actual = sheet.cell(row, col).value
            if isinstance(value, float):
                assert actual is None if np.isnan(value) else actual == pytest.approx(value, rel=2e-15)
            else:
                assert actual == value
    for i, (letter, note) in enumerate(notes, 5 + len(table)):
        assert sheet.cell(i, 1).value == f'({letter}) {note}'
    assert sum('Diagnostic covariance' in note for _, note in notes) == (not strict)
    assert 'z3' in reporting.bsu(session, include_off=True)[0]['Fraction ID'].tolist()
    assert session.step_complete(7)


def test_full_table_17_digits_and_edited_contract(session, tmp_path):
    session.set_value(0, 'Sample', 'current edit')
    session.reduce()
    session.set_included('z3', False)
    target = tmp_path / 'full.csv'
    reporting.save(session, target, 'full')
    expected = export.full_table(session.reduction.grains)
    actual = pd.read_csv(target, float_precision='round_trip')
    pd.testing.assert_frame_equal(actual, expected, check_exact=True, check_dtype=False)
    assert 'z3' in actual['id'].tolist()
    target = tmp_path / 'fractions.csv'
    reporting.save(session, target, 'fractions')
    assert read_fractions(target).frame['Sample'].iat[0] == 'current edit'


def test_exported_provenance_formula_values_statistics_and_selection(session, tmp_path):
    for row in range(session.row_count):
        session.set_value(row, 'U Oxide 18O/16O', '0.00206')
        session.set_value(row, 'U Oxide Formula', 'isobar_233_18O')
    session.set_value(session.row_of('z3'), 'U Oxide Formula', 'tripoli_java_00dc941')
    session.set_value(session.row_of('z2'), 'Pb Mean Statistic', 'geometric')
    session.reduce()
    session.set_included('z3', False)
    table, notes = reporting.bsu(session)
    note = dict(notes)['k']
    assert notes[-1][0] == 'k'
    assert set(table['Fraction ID']) == {'z2', 'z4', 'z5'}
    assert 'isobar_233_18O' in note and '18O/16O = 0.00206' in note
    assert 'geometric Pb ratio means' in note and 'arithmetic U ratio means' in note
    assert 'z3' not in note and 'tripoli_java_00dc941' not in note
    assert 'tripoli_java_00dc941' in dict(reporting.bsu(session, include_off=True)[1])['k']
    for kind, extension in [('bsu_csv', 'csv'), ('bsu_xlsx', 'xlsx')]:
        target = tmp_path / f'provenance.{extension}'
        reporting.save(session, target, kind)
        if extension == 'csv':
            assert ['(k)', note] in list(csv.reader(io.StringIO(target.read_text())))
        else:
            openpyxl = pytest.importorskip('openpyxl')
            sheet = openpyxl.load_workbook(target).active
            assert f'(k) {note}' in [row[0] for row in sheet.iter_rows(values_only=True)]


def test_autosave_names_and_newer_scientific_candidate(session, tmp_path, monkeypatch):
    monkeypatch.setenv('IDTIMS_AUTOSAVE_DIR', str(tmp_path / 'autosave'))
    assert autosave.path_for(session).name.startswith('untitled-')
    other = Session()
    assert autosave.path_for(other) != autosave.path_for(session)
    session.save_project(tmp_path / 'saved.idtr')
    session.set_value(0, 'Sample', 'recover me')
    path = autosave.save(session)
    import hashlib
    suffix = hashlib.sha1(str(Path(session.project_path).resolve()).encode()).hexdigest()[:10]
    assert path.name == f'saved-{suffix}.idtr'
    disk = project.restore(project.read(session.project_path))
    disk.project_path = session.project_path
    assert autosave.candidate(disk)['fractions_csv'] == project.document(session)['fractions_csv']
    session.save_project(session.project_path)
    assert not path.exists()
