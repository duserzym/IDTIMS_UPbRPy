"""Published compositions are completed only at the engine/app boundary."""
from dataclasses import replace
from copy import deepcopy
from pathlib import Path
import json
import warnings

import numpy as np
import pandas as pd
import pytest

from IDTIMS_UPbRPy import UPbR, spike_registry, uncertainty
from IDTIMS_UPbRPy.fractions import read_fractions
from IDTIMS_UPbRPy.spikes import SPIKES
from IDTIMS_UPbRPy.tracer import (
    CROSS_RATIOS, TracerCompositionError, complete_tracer,
    load_cross_ratio_supplements, validate_cross_ratio_supplements,
)
from idtims_app.services import Session

ROOT = Path(__file__).resolve().parents[1]
KEY = 'ET535/master/v3'
SHEET_RATIOS = {
    '207Pb/206Pb': (0.761593363043767, 7.048716571),
    '204Pb/206Pb': (0.23153930860262267, 33.749377052),
}


@pytest.fixture
def public_registry(monkeypatch):
    path = spike_registry.find_public_registry()
    if path is None:
        pytest.skip('Real public spike checkout not found by spike_registry.find_public_registry()')
    registry = spike_registry.load_registry(public=path)
    monkeypatch.setattr(spike_registry, 'get_registry', lambda: registry)
    return registry


def numeric(frame):
    return frame.loc[['value', 'uncertainty']].apply(pd.to_numeric, errors='coerce')


def reduce_public(name='ET535', strict=True, grain_id='z1'):
    is2535 = name == 'ET2535'
    path = ROOT / ('tests/data/synthetic_template_2535.csv' if is2535 else 'examples/synthetic_zircon_CA-ID-TIMS.csv')
    settings = ROOT / ('tests/data/settings_BSU_template.json' if is2535 else 'examples/synthetic_settings.json')
    data, columns = read_fractions(path).load_grains_frame()
    data = data.loc[data[columns['id']] == grain_id]
    data['Spike'] = name
    s = json.loads(settings.read_text())
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        return UPbR.load_grains(data, s['fractionation'], s['lab_blanks'], s['common_pb'], None,
                                strict_covariance=strict, spike_key=f'{name}/master/v3', **columns)[0]


def test_real_public_quotients_preserve_registry_view(public_registry):
    raw = numeric(spike_registry.to_legacy_frame(public_registry.by_key(KEY)))
    before = raw.copy()
    completed, notes, sources = complete_tracer(raw, KEY, key=KEY, with_sources=True)
    pd.testing.assert_frame_equal(raw, before, check_exact=True)
    assert raw.loc['value', list(CROSS_RATIOS)].isna().all()
    for ratio, (value, error) in SHEET_RATIOS.items():
        assert completed.at['value', ratio] == value
        assert completed.at['uncertainty', ratio] == error
        assert sources[ratio][0] == 'BSU sheet'
    ratio = '238U/233U'
    a, b = CROSS_RATIOS[ratio]
    assert completed.at['value', ratio] == raw.at['value', a] / raw.at['value', b]
    assert completed.at['uncertainty', ratio] == np.hypot(
        raw.at['uncertainty', a], raw.at['uncertainty', b])
    assert sources[ratio][0] == 'derived'
    assert completed.at['uncertainty', '204Pb/205Pb'] == pytest.approx(0.000009 / 0.00009 * 100)
    assert len(notes) == 3
    assert sum('BSU sheet' in n for n in notes) == 2
    assert sum(' derived as ' in n for n in notes) == 1
    assert all(KEY in n and 'McLean et al. (2011)' in n
               and 'pairwise covariances the engine infers' in n
               and 'diagnostic approximation' not in n for n in notes)
    for quantity in ('202Pb/205Pb', '235U/205Pb'):
        pd.testing.assert_series_equal(completed[quantity], raw[quantity], check_exact=True)


def test_supplement_matches_independent_lab_transcription():
    lab = spike_registry.load_registry(public=False).by_key('ET535/unassigned/v2')
    supplements = load_cross_ratio_supplements()
    assert set(supplements) == {KEY}
    for ratio, (value, error) in SHEET_RATIOS.items():
        measurement = supplements[KEY]['ratios'][ratio]
        assert measurement['value'] == value
        assert measurement['uncertainty'] == error
        assert measurement['uncertainty_type'] == '1sd_rel_pct'
        assert measurement['value'] == pytest.approx(lab.ratios[ratio].value, rel=1e-12, abs=0)
        assert measurement['uncertainty'] == pytest.approx(lab.ratios[ratio].uncertainty, rel=1e-12, abs=0)


def test_supplement_keys_and_absent_ratios_exist_in_real_public_registry(public_registry):
    for key, entry in load_cross_ratio_supplements().items():
        version = public_registry.by_key(key)
        assert version.visibility == 'public'
        assert not (entry['ratios'].keys() & version.ratios.keys())


@pytest.mark.parametrize('field,value,message', [
    ('value', float('nan'), 'value must be finite and positive'),
    ('value', 0, 'value must be finite and positive'),
    ('uncertainty', float('inf'), 'uncertainty must be finite and positive'),
    ('uncertainty', -1, 'uncertainty must be finite and positive'),
    ('uncertainty_type', 'unknown', 'unsupported uncertainty_type'),
])
def test_invalid_supplement_measurements_are_refused(field, value, message):
    data = deepcopy(load_cross_ratio_supplements())
    data[KEY]['ratios']['207Pb/206Pb'][field] = value
    with pytest.raises(ValueError, match=message):
        validate_cross_ratio_supplements(data)


def test_unknown_supplement_ratio_is_refused():
    data = deepcopy(load_cross_ratio_supplements())
    data[KEY]['ratios']['202Pb/205Pb'] = data[KEY]['ratios'].pop('207Pb/206Pb')
    with pytest.raises(ValueError, match='202Pb/205Pb: unknown cross-ratio label'):
        validate_cross_ratio_supplements(data)


def test_present_ratios_take_precedence_over_supplement():
    raw = numeric(spike_registry.to_legacy_frame(spike_registry.load_registry(public=False).resolve('ET535')))
    completed, notes, sources = complete_tracer(raw, KEY, key=KEY, with_sources=True)
    pd.testing.assert_frame_equal(completed, raw, check_exact=True)
    assert notes == [] and sources == {}


@pytest.mark.parametrize('key', [None, 'ET535/unassigned/v3', 'ET535/master/v2',
                               'ET2535/master/v3'])
def test_supplement_lookup_requires_exact_explicit_key(key):
    raw = numeric(spike_registry.to_legacy_frame(spike_registry.load_registry(public=False).resolve('ET535')))
    raw.loc[:, list(CROSS_RATIOS)] = np.nan
    # Even a matching display label must not select a supplement without its key.
    completed, notes = complete_tracer(raw, KEY, key=key)
    for ratio, (a, b) in CROSS_RATIOS.items():
        assert completed.at['value', ratio] == raw.at['value', a] / raw.at['value', b]
        assert completed.at['uncertainty', ratio] == np.hypot(
            raw.at['uncertainty', a], raw.at['uncertainty', b])
    assert len(notes) == 3 and all(' derived as ' in n for n in notes)


def test_real_public_et2535_still_derives_all_cross_ratios(public_registry):
    key = 'ET2535/master/v3'
    raw = numeric(spike_registry.to_legacy_frame(public_registry.by_key(key)))
    completed, notes = complete_tracer(raw, key, key=key)
    for ratio, (a, b) in CROSS_RATIOS.items():
        assert completed.at['value', ratio] == raw.at['value', a] / raw.at['value', b]
        assert completed.at['uncertainty', ratio] == np.hypot(
            raw.at['uncertainty', a], raw.at['uncertainty', b])
    assert len(notes) == 3
    assert all(' derived as ' in n and 'zero covariance' in n
               and 'McLean et al. (2011)' in n for n in notes)


@pytest.mark.parametrize('name,strict', [('ET535', True), ('ET535', False), ('ET2535', False)])
def test_real_public_reduces(public_registry, name, strict):
    g = reduce_public(name, strict)
    assert g.id == 'z1'
    assert all(np.isfinite(getattr(g, q)) for q in ('t68', 't75', 't76', 't68_std', 't75_std', 't76_std'))
    assert len(g.tracer_derivations) == 3
    assert all(isinstance(n, str) for n in g.tracer_derivations)
    assert all(n in g.uncertainty_assumptions for n in g.tracer_derivations)


def test_real_public_z9b_uncertainty_uses_sheet_cross_ratios(public_registry):
    grain = reduce_public(strict=False, grain_id='z9b')
    assert np.isfinite(grain.t76_std) and grain.t76_std < 2.5


def test_all_private_and_legacy_compositions_are_unchanged():
    registry = spike_registry.load_registry(public=False)
    frames = [(v.key, spike_registry.to_legacy_frame(v))
              for spike in registry.spikes.values() for v in spike.versions]
    frames.extend((f'{name} {version}', pd.read_csv(ROOT / 'src/IDTIMS_UPbRPy/spike_compositions' / filename,
                                                  index_col=0))
                  for name, versions in SPIKES.items() for version, filename in versions.items())
    for label, frame in frames:
        raw = numeric(frame)
        for key in (None, label):
            completed, notes = complete_tracer(raw, label, key=key)
            pd.testing.assert_frame_equal(completed, raw, check_exact=True)
            assert notes == [], label


@pytest.fixture
def incomplete_registry(monkeypatch):
    # Keep refusal coverage independent of an installed public checkout.
    registry = spike_registry.load_registry(public=False)
    private = registry.resolve('ET535', 'v3')
    ratios = {q: m for q, m in private.ratios.items() if q not in CROSS_RATIOS}
    ratios['204Pb/205Pb'] = replace(ratios['204Pb/205Pb'], uncertainty=None, uncertainty_text=None)
    version = replace(private, subfraction='master', visibility='public', ratios=ratios)
    registry.spikes['ET535'].versions.append(version)
    monkeypatch.setattr(spike_registry, 'get_registry', lambda: registry)
    return registry


def test_missing_uncertainty_blocks_engine_database_and_preview(incomplete_registry):
    assert_missing_uncertainty_refused()


def test_real_public_missing_uncertainty_is_refused(public_registry):
    version = public_registry.by_key(KEY)
    ratios = {**version.ratios, '204Pb/205Pb': replace(version.ratios['204Pb/205Pb'],
                                                    uncertainty=None, uncertainty_text=None)}
    versions = public_registry.spikes['ET535'].versions
    versions[versions.index(version)] = replace(version, ratios=ratios)
    assert_missing_uncertainty_refused()


def assert_missing_uncertainty_refused():
    with pytest.raises(TracerCompositionError) as exc:
        reduce_public()
    message = str(exc.value)
    assert f'Tracer {KEY} has no uncertainty for 204Pb/205Pb' in message
    # The supplemented 204/206 does not excuse a missing required 204/205 error.
    assert 'has no uncertainty for 204Pb/206Pb' not in message
    assert 'the reduction does not assume one' in message
    session = Session()
    assert session.open_files([ROOT / 'tests/data/synthetic_database_link.fractions.csv']).error is None
    assert session.set_value(0, 'Spike Solution', KEY) is None
    issues = session.table.database_spike_issues('z1')
    assert len(issues) == 1 and issues[0].kind == 'database_spike' and issues[0].blocking
    assert issues[0].message == message
    with pytest.raises(ValueError, match='not awaiting confirmation'):
        session.confirm_database_spike('z1')
    with pytest.raises(TracerCompositionError, match='no uncertainty for 204Pb/205Pb'):
        session.tracer_table('ET535', spike_key=KEY)


def test_present_cross_ratio_with_missing_error_is_not_replaced():
    raw = numeric(spike_registry.to_legacy_frame(spike_registry.load_registry(public=False).resolve('ET535')))
    raw.at['uncertainty', '207Pb/206Pb'] = np.nan
    with pytest.raises(TracerCompositionError, match='no uncertainty for 207Pb/206Pb'):
        complete_tracer(raw, KEY, key=KEY)


def test_missing_input_names_cross_ratios_and_all_missing_quantities():
    raw = numeric(spike_registry.to_legacy_frame(spike_registry.load_registry(public=False).resolve('ET535')))
    raw = raw.drop(columns=['206Pb/205Pb', '207Pb/206Pb', '204Pb/206Pb', 'Pb205'])
    raw.at['uncertainty', '208Pb/205Pb'] = np.inf
    with pytest.raises(TracerCompositionError) as exc:
        complete_tracer(raw, 'ET535 v1')
    message = str(exc.value)
    for quantity in ('Pb205', '206Pb/205Pb', '207Pb/206Pb', '204Pb/206Pb', '208Pb/205Pb'):
        assert quantity in message
    assert 'has no value for 207Pb/206Pb (cannot derive: no value for 206Pb/205Pb)' in message


def test_optional_underivable_uranium_quotient_is_not_required():
    raw = numeric(spike_registry.to_legacy_frame(spike_registry.load_registry(public=False).resolve('ET535')))
    raw.at['value', '238U/233U'] = np.nan
    raw.at['value', '233U/235U'] = 0.0
    completed, notes = complete_tracer(raw, 'ET535 v1')
    assert np.isnan(completed.at['value', '238U/233U']) and notes == []


@pytest.mark.parametrize('quantity,row', [('Pb205', 'value'), ('U235', 'value')])
def test_required_concentrations(quantity, row):
    raw = numeric(spike_registry.to_legacy_frame(spike_registry.load_registry(public=False).resolve('ET2535')))
    raw.at[row, quantity] = np.nan
    with pytest.raises(TracerCompositionError, match=f'has no {row} for {quantity}'):
        complete_tracer(raw, 'ET2535 v3')


def test_absolute_uncertainty_at_zero_blocks_database_spike(monkeypatch):
    registry = spike_registry.load_registry(public=False)
    version = registry.resolve('ET535', 'v3')
    ratios = {**version.ratios, '204Pb/205Pb': replace(
        version.ratios['204Pb/205Pb'], value=0.0, value_text='0',
        uncertainty=0.000009, uncertainty_type='1sd_abs', uncertainty_text=None)}
    versions = registry.spikes['ET535'].versions
    versions[versions.index(version)] = replace(version, ratios=ratios)
    monkeypatch.setattr(spike_registry, 'get_registry', lambda: registry)
    session = Session()
    assert session.open_files([ROOT / 'tests/data/synthetic_database_link.fractions.csv']).error is None
    assert session.set_value(0, 'Spike Solution', version.key) is None
    issues = session.table.database_spike_issues('z1')
    assert len(issues) == 1 and issues[0].kind == 'database_spike' and issues[0].blocking
    assert issues[0].message == (
        f'{version.key}: cannot express absolute uncertainty relative to zero for 204Pb/205Pb')
    assert 'z1' not in session.ready_ids()
    with pytest.raises(ValueError, match='not awaiting confirmation'):
        session.confirm_database_spike('z1')


def test_535_tracer_on_2535_row_keeps_missing_double_spike_preview():
    session = Session()
    assert session.open_files([ROOT / 'tests/data/synthetic_template_2535.csv']).error is None
    assert session.set_value(0, 'Spike', 'ET535') is None
    row = session.fpb_2535()[0]
    assert row[0] == 'z1'
    assert row[3:7] == (None, None, None, None)
    assert 'Tracer ET535 has no 202Pb/205Pb' in row[-1]


def test_public_strict_app_result_and_double_spike_preview(public_registry):
    session = Session()
    assert session.open_files([ROOT / 'examples/synthetic_zircon_CA-ID-TIMS.csv']).error is None
    assert session.load_settings(ROOT / 'examples/synthetic_settings.json')[0] is None
    session.confirm_all('missing_oxide')
    assert session.set_value(0, 'Spike', 'ET535') is None
    assert session.set_value(0, 'Spike Solution', KEY) is None
    session.confirm_database_spike('z1')
    result = session.reduce().result('z1')
    assert result.status_text == 'Reduced'
    assert result.substitutions == []
    session = Session()
    session.open_files([ROOT / 'tests/data/synthetic_template_2535.csv'])
    session.set_value(0, 'Spike Solution', 'ET2535/master/v3')
    row = session.fpb_2535()[0]
    assert row[-1] == '' and np.isfinite(row[5]) and np.isfinite(row[6])


@pytest.mark.parametrize('attribute,expected', [('Pb_R76t', 'tracer 207Pb/206Pb value'),
                                              ('U_R35m_std', 'measured 233U/235U 1σ')])
def test_nonfinite_propagation_input_is_readable(public_registry, attribute, expected):
    g = reduce_public()
    setattr(g, attribute, np.nan)
    with pytest.raises(ValueError, match=f'Grain z1: non-finite reduction inputs: {expected}'):
        uncertainty.propagate(g)


def test_nonfinite_projection_is_not_called_constant(public_registry):
    g = reduce_public()
    g.cov_45_65_t = np.nan
    with pytest.raises(ValueError, match='non-finite variance for 204/205 projection'):
        uncertainty.propagate(g)
