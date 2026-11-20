"""Clarification 10: offline database metadata, exact tracers and replayable consent."""
import copy
from dataclasses import replace
from io import StringIO
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import pytest

from IDTIMS_UPbRPy import UPbR, export, spike_registry
from IDTIMS_UPbRPy.fractions import (CHEMISTRY_NUMERIC_COLUMNS, FractionFileError,
                                    read_fractions, split_source_list, write_fractions)
from idtims_app import project, reporting
from idtims_app.services import NEEDS_CONFIRMATION, Session
from snapshot_support import F, B, C, grain_numbers

DATA = Path(__file__).parent / 'data'
CSV = DATA / 'synthetic_database_link.fractions.csv'
KEY = 'ET535/unassigned/v3'


def csv_frame(frame, name='input.csv'):
    stream = StringIO(frame.to_csv(index=False))
    stream.name = name
    return stream


@pytest.fixture
def linked():
    session = Session()
    assert session.open_files([CSV]).error is None
    assert session.load_settings(DATA.parent.parent / 'examples/synthetic_settings.json')[0] is None
    session.confirm_all('missing_oxide')
    session.set_strict_covariance(False)
    return session


def test_columns_and_source_lists_round_trip():
    table = read_fractions(CSV)
    assert table.fraction_ids == ['z1', 'z2', 'z3']
    assert table._row('z1')['Annealing Temperature (°C)'] == 900.0
    assert all(table.frame[c].dtype == float for c in CHEMISTRY_NUMERIC_COLUMNS)
    assert split_source_list(table._row('z2')['Source Spot']) == ['s2', '']
    assert table._row('z2')['Source Spot'] == 's2; '
    assert split_source_list(table._row('z2')['Source Fragment Note']) == ['', 'tip fragment']
    assert not [i for i in table.issues() if i.kind == 'source_list_count']
    assert split_source_list(None) == []
    buffer = StringIO()
    write_fractions(table, buffer)
    pd.testing.assert_frame_equal(read_fractions(StringIO(buffer.getvalue())).frame, table.frame)
    # Pb/U hand-offs may carry complementary metadata; all list cells stay text.
    pb = table.frame.drop(columns=['Annealing', 'Spike Solution'])
    u = table.frame[['Contract', 'Fraction ID', 'Annealing', 'Spike Solution']]
    merged = read_fractions(csv_frame(pb, 'pb.csv'), csv_frame(u, 'u.csv'))
    assert merged._row('z2')['Source Mount'] == 'M1; M2'
    assert merged._row('z2')['Spike Solution'] == KEY


def test_latest_database_read_with_offset_and_other_conflicts():
    frame = read_fractions(CSV).frame.iloc[:1]
    newer = frame.copy()
    newer['Database Read At'] = '2026-11-20T17:30:00+00:00'
    # 10:00 -07:00 is 17:00 UTC. Keep the latest in either file order.
    for a, b in ((frame, newer), (newer, frame)):
        merged = read_fractions(csv_frame(a, 'pb.csv'), csv_frame(b, 'u.csv'))
        assert merged._row('z1')['Database Read At'] == newer.iloc[0]['Database Read At']
    newer['Annealing'] = '950 °C, 60 h'
    with pytest.raises(FractionFileError, match='z1.*Annealing.*pb.csv.*u.csv'):
        read_fractions(csv_frame(frame, 'pb.csv'), csv_frame(newer, 'u.csv'))


@pytest.mark.parametrize('stamp', ['yesterday', '2026-11-20T10:00:00', '2026-11-20'])
def test_invalid_database_read_names_fraction_and_file(stamp):
    frame = read_fractions(CSV).frame.iloc[:1].copy()
    frame['Database Read At'] = stamp
    with pytest.raises(FractionFileError, match='z1.*bad.csv.*Database Read At'):
        read_fractions(csv_frame(frame, 'bad.csv'))


def test_servers_refused_within_file_and_across_merge():
    frame = read_fractions(CSV).frame.iloc[:2].copy()
    frame.loc[1, 'Database Server'] = 'https://another.example.invalid'
    with pytest.raises(FractionFileError, match='more than one Database Server|More than one Database Server'):
        read_fractions(csv_frame(frame))
    with pytest.raises(FractionFileError, match='Database Server.*pb.csv.*u.csv'):
        read_fractions(csv_frame(frame.iloc[:1], 'pb.csv'), csv_frame(frame.iloc[1:], 'u.csv'))


def test_source_list_count_is_an_issue():
    frame = read_fractions(CSV).frame.copy()
    frame.loc[1, 'Source Spot'] = 's2'
    table = read_fractions(csv_frame(frame))
    issues = [i for i in table.issues() if i.kind == 'source_list_count']
    assert len(issues) == 1 and issues[0].fraction_id == 'z2'
    assert 'Source Spot = 1' in issues[0].message
    assert 'Source Grain = 2' in issues[0].message
    assert not issues[0].blocking


@pytest.fixture
def registry_with_master(monkeypatch):
    """Self-contained distinct public/master calibration, no public checkout required."""
    registry = spike_registry.load_registry(public=False)
    private = registry.by_key(KEY)
    public = replace(private, subfraction='master', source='test_public', visibility='public',
                     concentrations={**private.concentrations,
                                     '235U': spike_registry.Measurement(1.0336e-9, 'mol/g', value_text='1.0336e-9')})
    registry.spikes['ET535'].versions.append(public)
    monkeypatch.setattr(spike_registry, 'get_registry', lambda: registry)
    return registry


def test_exact_key_bypasses_legacy_and_never_falls_back(registry_with_master):
    registry = registry_with_master
    assert registry.resolve('ET535', 'v3').key == KEY
    assert registry.by_key('ET535/master/v3').visibility == 'public'
    private = UPbR.load_spike_data('ET535', 'v3')
    public = UPbR.load_spike_data('ET535', 'v1', spike_key='ET535/master/v3')
    assert float(public.at['value', 'U235']) != float(private.at['value', 'U235'])
    assert float(public.at['value', 'U235']) == 1.0336e-9
    with pytest.raises(ValueError, match='registry key'):
        UPbR.load_spike_data('ET535', spike_key='ET535/missing/v3')
    with pytest.raises(ValueError, match='disagrees'):
        UPbR.load_spike_data('BSU1B', spike_key='ET535/master/v3')


def reduce_frame(table, **kwargs):
    data, columns = table.load_grains_frame()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        return UPbR.load_grains(data, F, B, C, None, strict_covariance=False, **columns, **kwargs)


def test_notebooks_ignore_proposals_until_opt_in(registry_with_master):
    table = read_fractions(CSV)
    table._set('z1', 'Spike Solution', 'ET535/master/v3')
    plain = read_fractions(csv_frame(table.frame.drop(columns=['Spike Solution', 'Spike Version UID'])))
    defaults, before = reduce_frame(table), reduce_frame(plain)
    for a, b in zip(defaults, before):
        # Every stored numeric scalar/array compares as bytes, including NaNs.
        av, bv = grain_numbers(a), grain_numbers(b)
        assert av.keys() == bv.keys()
        for key in av:
            assert np.asarray(av[key]).tobytes() == np.asarray(bv[key]).tobytes(), key
    opted = reduce_frame(table, spike_from='Spike Solution')
    assert opted[0].spike_key == 'ET535/master/v3'
    assert opted[0].spike_version == 'v3'
    assert opted[0].U235t != defaults[0].U235t
    assert opted[2].spike_key is None and opted[2].t68 == defaults[2].t68
    single = read_fractions(csv_frame(table.frame.iloc[:1]))
    assert reduce_frame(single, spike_key='ET535/master/v3')[0].t68 == opted[0].t68


def test_confirmation_gate_and_exact_reduction(linked):
    assert 'unconfirmed_database_spike' in NEEDS_CONFIRMATION
    assert linked.ready_ids() == ['z3']
    assert linked.step_complete(0)  # Tracer must be reachable even with proposals.
    job = linked.prepare_reduction()
    assert set(job.excluded) == {'z1', 'z2'}
    assert KEY in job.excluded['z1']
    before = linked.scientific_project_fingerprint()
    linked.confirm_database_spike('z1')
    assert linked.scientific_project_fingerprint() != before
    assert linked.ready_ids() == ['z1', 'z3']
    # A confirmed exact key wins even when the global version changes afterwards.
    linked.settings.spike_version = 'v1'
    linked.settings_edited()
    run = linked.reduce()
    g = next(g for g in run.grains if g.id == 'z1')
    assert g.spike_key == KEY and g.spike_version == 'v3'
    assert g.U235t == float(UPbR.load_spike_data('ET535', spike_key=KEY).at['value', 'U235']) * g.spike_weight
    assert not next(r for r in run.results if r.fraction_id == 'z2').reduced
    reopened = project.restore(project.document(linked))
    assert reopened.settings.spike_version == 'v1'
    assert reopened.table.database_spike_confirmed('z1')
    restored = next(g for g in reopened.reduction.grains if g.id == 'z1')
    assert restored.spike_key == KEY and restored.U235t == g.U235t


@pytest.mark.parametrize('column,value,fragment', [
    ('Spike Solution', 'ET535/absent/v3', 'not in this app'),
    ('Spike', 'BSU1B', 'disagrees'),
    ('Spike Type', '2535', 'needs Spike Type'),
])
def test_database_conflicts_block_without_fallback(linked, column, value, fragment):
    assert linked.set_value(0, column, value) is None
    issues = [i for i in linked.issues('z1') if i.kind == 'database_spike']
    assert len(issues) == 1 and issues[0].blocking and fragment in issues[0].message
    assert 'z1' not in linked.ready_ids()
    with pytest.raises(ValueError, match='not awaiting'):
        linked.confirm_database_spike('z1')


def test_preselection_and_project_version_conflict(linked):
    linked.set_value(0, 'Spike', '')
    assert linked.value(0, 'Spike') == 'ET535'
    linked.settings.spike_version = 'v1'
    linked.settings_edited()
    assert any('contradicts project' in i.message for i in linked.issues('z1'))
    with pytest.raises(ValueError):
        linked.confirm_database_spike('z1')
    linked.settings.spike_version = None
    linked.settings_edited()
    linked.confirm_database_spike('z1')
    # Even a table made solely of linked rows unlocks the Tracer step.
    linked.table.frame = linked.table.frame.iloc[:2].copy()
    linked.table.database_spike_confirmations.clear()
    assert linked.ready_ids() == [] and linked.step_complete(0)


def test_publication_optional_columns_and_no_uids(linked):
    linked.confirm_all('unconfirmed_database_spike')
    linked.reduce()
    table, _ = reporting.bsu(linked)
    expected = ['Source Mount', 'Capsule Set', 'Annealing', 'Chemical Abrasion',
                *CHEMISTRY_NUMERIC_COLUMNS, 'Spike Solution']
    assert all(c in table.columns for c in expected)
    assert table.loc[0, 'Source Mount'] == 'M1'
    assert table.loc[0, 'Annealing Temperature (°C)'] == 900.0
    assert not any('UID' in c or c.startswith('Database') for c in table.columns)
    assert not any('UID' in c or c.startswith('Database') for c in export.full_table(linked.reduction.grains))
    linked.set_included('z1', False)
    linked.set_included('z2', False)
    unlinked, _ = reporting.bsu(linked)
    assert not set(expected) & set(unlinked.columns)


def test_origin_round_trip_and_stale_confirmations(linked, tmp_path):
    linked.confirm_database_spike('z1')
    doc = project.document(linked)
    origin = doc['origin']
    assert doc['version'] == 1
    assert origin['format'] == 'idtims database link' and origin['format_version'] == 1
    assert origin['server'] == 'https://upbdb.example.invalid/lab'
    assert set(origin['fractions']) == {'z1', 'z2'}
    assert origin['fractions']['z1']['spike_confirmed_at']
    assert origin['fractions']['z2']['spike_confirmed_at'] is None
    project.write(doc, tmp_path / 'linked.idtr')
    restored = project.restore(project.read(tmp_path / 'linked.idtr'))
    assert restored.table.database_spike_confirmed('z1')
    assert not restored.table.database_spike_confirmed('z2')
    assert restored.scientific_project_fingerprint() == linked.scientific_project_fingerprint()
    assert project.document(restored)['origin'] == origin
    for column, value in [('Spike Solution', 'ET535/unassigned/v1'),
                          ('Spike Version UID', '40000000-0000-4000-8000-999999999999')]:
        changed = copy.deepcopy(doc)
        table = read_fractions(StringIO(changed['fractions_csv']))
        table._set('z1', column, value)
        stream = StringIO()
        write_fractions(table, stream)
        changed['fractions_csv'] = stream.getvalue()
        reopened = project.restore(changed)
        assert not reopened.table.database_spike_confirmed('z1')
        assert any(i.kind == 'unconfirmed_database_spike' for i in reopened.issues('z1'))
    linked.set_value(0, 'Spike Version UID', 'changed')
    assert not linked.table.database_spike_confirmed('z1')


@pytest.mark.parametrize('change,match', [
    ({'format': 'other'}, 'origin format'),
    ({'format_version': 2}, 'origin format_version'),
    ({'format_version': '1'}, 'origin format_version'),
    ({'fractions': []}, 'fractions object'),
])
def test_origin_refusals(linked, change, match):
    doc = project.document(linked)
    doc['origin'].update(change)
    with pytest.raises(ValueError, match=match):
        project.restore(doc)


def test_confirmation_follows_renaming_and_is_removed_on_delete(linked):
    linked.confirm_database_spike('z1')
    linked.set_value(0, 'Fraction ID', 'renamed')
    assert linked.table.database_spike_confirmed('renamed')
    assert project.document(linked)['origin']['fractions']['renamed']['spike_confirmed_at']
    linked.delete_rows([0])
    assert 'renamed' not in linked.table.database_spike_confirmations


@pytest.mark.parametrize('column', ['Fraction UID', 'Database Server'])
def test_confirmation_cleared_when_database_identity_changes(linked, column):
    linked.confirm_database_spike('z1')
    assert linked.set_value(0, column, 'changed') is None
    assert not linked.table.database_spike_confirmed('z1')
