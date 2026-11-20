"""Registry integrity, private layering and exact legacy reduction compatibility."""
from pathlib import Path
import json
from io import StringIO
import shutil
import subprocess
import sys

import pandas as pd
import pytest

from IDTIMS_UPbRPy import UPbR
from IDTIMS_UPbRPy import spike_registry as registry
from IDTIMS_UPbRPy import _spike_registry_check as check
from IDTIMS_UPbRPy.spikes import SPIKES

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT.parent / 'upb-standards/spikes'
LEGACY = [(name, version, filename) for name, versions in SPIKES.items()
          for version, filename in versions.items()]


def numeric(frame):
    return frame.apply(pd.to_numeric, errors='coerce')


@pytest.mark.parametrize('name,version,filename', LEGACY)
def test_all_legacy_frames_are_exact(name, version, filename):
    loaded = registry.load_registry(public=False)
    expected = pd.read_csv(ROOT / 'src/IDTIMS_UPbRPy/spike_compositions' / filename, index_col=0)
    actual = registry.to_legacy_frame(loaded.resolve(name, version))
    pd.testing.assert_frame_equal(numeric(actual), numeric(expected), rtol=0, atol=0, check_exact=True)
    pd.testing.assert_frame_equal(actual, expected, check_exact=True)
    pd.testing.assert_frame_equal(UPbR.load_spike_data(name, version), expected, check_exact=True)


@pytest.fixture
def public(tmp_path):
    """Self-contained public-shaped fixture; no checkout dependency for CI."""
    path = tmp_path / 'public'
    path.mkdir()
    (path / 'registry.toml').write_text('format_version = 1\nsources = "sources.toml"\nspike_files = ["TEST.toml"]\nlock = "versions.lock.json"\n')
    (path / 'sources.toml').write_text('format_version = 1\n[sources.fixture]\ndisplay = "Synthetic test fixture"\n')
    (path / 'TEST.toml').write_text('''format_version = 1
[spike]
id = "TEST"
name = "TEST"
aliases = ["TestAlias"]
spike_type = "535"
isotopes = ["205Pb", "235U"]
description = "Synthetic fixture; not a calibration."
visibility = "public"
[[spike.subfractions]]
id = "master"
name = "Master"
[[spike.versions]]
subfraction = "master"
version = "v1"
status = "current"
source = "fixture"
locator = "Fixture table"
notes = "Fixture"
[spike.versions.concentrations]
"205Pb" = { value = 1.0e-12, unit = "mol/g" }
[spike.versions.ratios]
"233U/235U" = { value = 1.0, uncertainty = 0.01, uncertainty_type = "1sd_abs" }
''')
    check.check_registries(path, update_lock=True)
    return path


def overlay_from_public(public, tmp_path):
    path = tmp_path / 'overlay'
    shutil.copytree(public, path)
    p = path / 'TEST.toml'
    p.write_text(p.read_text().replace('visibility = "public"', 'visibility = "private"'))
    (path / 'versions.lock.json').unlink()
    return path


def test_actual_public_files_parse_and_merge():
    if not PUBLIC.is_dir():
        pytest.skip('Optional public checkout is not installed')
    layers = check.check_registries(PUBLIC, [registry.BUNDLED_OVERLAY])
    assert sum(len(s['versions']) for _, spikes, _ in layers for s in spikes) == 10
    loaded = registry.load_registry(public=PUBLIC)
    for sid in ('ET535', 'ET2535'):
        version = loaded.resolve(sid, 'v3', 'master')
        assert version.visibility == 'public'
        assert version.locator.startswith('Table 3, p. 474')
        assert version.concentrations['235U'].value == 1.0336e-9
        assert version.concentrations['235U'].uncertainty_type == '1sd_abs'
        assert loaded.resolve(sid, 'v3').visibility == 'private'


@pytest.mark.parametrize('update', [False, True])
def test_locked_value_cannot_change(public, update):
    path = public / 'TEST.toml'
    path.write_text(path.read_text().replace('1.0e-12', '2.0e-12'))
    lock_before = (public / 'versions.lock.json').read_bytes()
    with pytest.raises(ValueError, match='locked version changed: TEST/master/v1'):
        check.check_registries(public, update_lock=update)
    assert (public / 'versions.lock.json').read_bytes() == lock_before


def test_status_and_notes_are_only_unlocked_version_fields(public):
    path = public / 'TEST.toml'
    original = path.read_text()
    path.write_text(original.replace('status = "current"', 'status = "withdrawn"').replace('notes = "Fixture"', 'notes = "Later review"'))
    check.check_registries(public)
    path.write_text(original.replace('Fixture table', 'Changed locator'))
    with pytest.raises(ValueError, match='locked version changed'):
        check.check_registries(public)


def test_removing_a_locked_version_is_refused(public):
    (public / 'registry.toml').write_text('format_version = 1\nspike_files = []\nlock = "versions.lock.json"\n')
    with pytest.raises(ValueError, match='locked version removed'):
        check.check_registries(public, update_lock=True)


def test_overlay_cannot_redefine_public_version(public, tmp_path):
    overlay = overlay_from_public(public, tmp_path)
    with pytest.raises(ValueError, match='never redefine.*TEST/master/v1'):
        check.check_registries(public, [overlay], update_lock=True)
    assert not (overlay / 'versions.lock.json').exists()


def test_overlay_extends_public_and_supersedes_across_layers(public, tmp_path):
    overlay = overlay_from_public(public, tmp_path)
    path = overlay / 'TEST.toml'
    path.write_text(path.read_text().replace('version = "v1"', 'version = "v2"\nsupersedes = "v1"').replace('TestAlias', 'PrivateAlias'))
    check.check_registries(public, [overlay], update_lock=True)
    old_hash = json.loads((public / 'versions.lock.json').read_text())
    loaded = registry.load_registry(public=public, overlays=[overlay])
    assert loaded.resolve('TEST', 'v1').visibility == 'public'
    v = loaded.resolve('PrivateAlias', 'v2')
    assert v.visibility == 'private' and v.supersedes == 'v1'
    assert v.citation['display'] == 'Synthetic test fixture'
    assert loaded.spikes['TEST'].subfractions['master'].visibility == 'public'
    assert json.loads((public / 'versions.lock.json').read_text()) == old_hash


def test_update_only_appends(public):
    path = public / 'TEST.toml'
    original = path.read_text()
    before = json.loads((public / 'versions.lock.json').read_text())
    version = original[original.index('[[spike.versions]]'):].replace('version = "v1"', 'version = "v2"\nsupersedes = "v1"')
    path.write_text(original + '\n' + version)
    with pytest.raises(ValueError, match='unlocked versions'):
        check.check_registries(public)
    check.check_registries(public, update_lock=True)
    after = json.loads((public / 'versions.lock.json').read_text())
    assert all(after[key] == value for key, value in before.items())
    assert set(after) == {'TEST/master/v1', 'TEST/master/v2'}


@pytest.mark.parametrize('old,new,message', [
    ('source = "fixture"', 'source = "unknown"', 'unknown source'),
    ('1sd_abs', '3sd_abs', 'invalid uncertainty_type'),
    ('1.0e-12', '-1.0e-12', 'nonnegative number'),
    ('unit = "mol/g"', 'unit = "g/mol"', 'expected mol/g'),
    ('subfraction = "master"', 'subfraction = "absent"', 'unknown subfraction'),
    ('status = "current"', 'status = "active"', 'invalid status'),
    ('version = "v1"', 'version = "v1"\nsupersedes = "v1"', 'supersedes cycle'),
    ('uncertainty_type = "1sd_abs"', 'unrecognized = "1sd_abs"', 'unknown fields'),
])
def test_schema_rejects_bad_inputs(public, old, new, message):
    path = public / 'TEST.toml'
    path.write_text(path.read_text().replace(old, new))
    (public / 'versions.lock.json').unlink()
    with pytest.raises(ValueError, match=message):
        check.check_registries(public, update_lock=True)


def test_missing_uncertainty_is_unknown(public):
    v = registry.load_registry(public=public).resolve('TEST', 'v1')
    assert v.concentrations['205Pb'].uncertainty is None
    f = registry.to_legacy_frame(v)
    assert pd.isna(f.loc['uncertainty', 'Pb205'])
    assert float(f.loc['uncertainty', '233U/235U']) == 1.0


def test_resolution_alias_legacy_and_defaults():
    loaded = registry.load_registry(public=False)
    assert loaded.resolve('BSU1B', 'v1').key == 'BSU-1/B/v1'
    assert loaded.resolve('BSU-1').key == 'BSU-1/B/v1'
    assert loaded.resolve('MIT1L').key == 'MIT-1L/unassigned/v1'
    assert loaded.resolve('MIT-1L').key == 'MIT-1L/unassigned/v1'
    assert loaded.resolve('ET535').key == 'ET535/unassigned/v1'
    assert loaded.resolve('ET2535').key == 'ET2535/unassigned/v3'
    assert loaded.resolve('ET535', 'sheet-sa18-1', 'unassigned').ratios['202Pb/205Pb'].value == 0
    with pytest.raises(ValueError, match='Unknown or ambiguous'):
        loaded.resolve('ET535', 'v99')
    with pytest.raises(ValueError, match='Unknown or ambiguous'):
        loaded.resolve('no-such-spike')


def test_find_precedence_and_home_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    roots = [tmp_path / 'explicit', tmp_path / 'standards/spikes',
             tmp_path / 'UPbRPy/upb-standards/spikes', tmp_path / 'Github/upb-standards/spikes']
    for path in roots:
        path.mkdir(parents=True)
        (path / 'registry.toml').touch()
    monkeypatch.setenv('UPB_SPIKES_DIR', str(roots[0]))
    monkeypatch.setenv('UPB_STANDARDS_DIR', str(roots[1].parent))
    for expected in roots:
        assert registry.find_public_registry() == expected
        (expected / 'registry.toml').unlink()
    assert registry.find_public_registry() is None


def test_no_public_checkout_uses_private_overlay(monkeypatch, tmp_path):
    monkeypatch.setenv('UPB_SPIKES_DIR', str(tmp_path / 'absent'))
    monkeypatch.delenv('UPB_STANDARDS_DIR', raising=False)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    assert registry.find_public_registry() is None
    assert registry.resolve('ET2535').visibility == 'private'
    assert UPbR.load_spike_data('ET535').loc['value', 'Pb205'] == '0.00000000000988'


def test_unreadable_registry_warns_and_falls_back(monkeypatch, tmp_path):
    (tmp_path / 'registry.toml').write_text('invalid TOML !')
    monkeypatch.setattr(registry, 'find_public_registry', lambda: tmp_path)
    with pytest.warns(RuntimeWarning, match='falling back to bundled CSVs'):
        actual = UPbR.load_spike_data('ET2535')
    expected = pd.read_csv(ROOT / 'src/IDTIMS_UPbRPy/spike_compositions/ET2535_v3.csv', index_col=0)
    pd.testing.assert_frame_equal(actual, expected)


def test_unresolved_name_uses_csv_fallback(monkeypatch):
    monkeypatch.setitem(SPIKES, 'CSV_ONLY', {'v1': 'ET535_v1.csv'})
    pd.testing.assert_frame_equal(UPbR.load_spike_data('CSV_ONLY'), UPbR.load_spike_data('ET535'))
    with pytest.raises(ValueError, match='Unknown spike/version'):
        UPbR.load_spike_data('unknown')


def test_fraction_validation_accepts_registry_id():
    from IDTIMS_UPbRPy.fractions import read_fractions
    data = pd.read_csv(ROOT / 'tests/data/synthetic_template_2535.csv')
    data['Spike'] = 'BSU-1'
    table = read_fractions(StringIO(data.to_csv(index=False)))
    assert not any(i.kind == 'invalid_value' and 'Spike' in i.columns for i in table.issues())


def test_sheet_snapshots_are_exact():
    loaded = registry.load_registry(public=False)
    report = json.loads((ROOT / 'docs/spike-sheet-compositions.json').read_text())
    labels = ['202Pb/205Pb', '206Pb/205Pb', '207Pb/205Pb', '204Pb/205Pb',
              '208Pb/205Pb', '207Pb/206Pb', '204Pb/206Pb', '238U/235U',
              '233U/235U', '238U/233U']
    for group in report:
        sid, subfraction, version = group['key'].split('/')
        v = loaded.resolve(sid, version, subfraction)
        assert v.concentrations['205Pb'].value == group['rows']['150']
        assert v.concentrations['235U'].value == group['rows']['151']
        for row, label in zip(range(152, 172, 2), labels):
            assert v.ratios[label].value == group['rows'][str(row)]
            assert v.ratios[label].uncertainty == group['rows'][str(row + 1)]


def test_public_and_vendored_checker_logic_agree():
    if not PUBLIC.is_dir():
        pytest.skip('Optional public checkout is not installed')
    public_code = (PUBLIC / 'check.py').read_text()
    vendored = Path(check.__file__).read_text().replace('try:\n    import tomllib\nexcept ModuleNotFoundError:\n    import tomli as tomllib\n', 'import tomllib\n')
    assert public_code == vendored


def test_checker_cli_failure(public):
    path = public / 'TEST.toml'
    path.write_text(path.read_text().replace('1.0e-12', '2.0e-12'))
    result = subprocess.run([sys.executable, check.__file__, '--registry', str(public), '--update-lock'], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'locked version changed' in result.stderr


def test_public_logical_paths_work_after_relocation(public, tmp_path):
    path = public / 'registry.toml'
    path.write_text(path.read_text().replace('["TEST.toml"]', '["spikes/TEST.toml"]').replace('lock = "versions.lock.json"', 'lock = "spikes/versions.lock.json"'))
    check.check_registries(public)
    moved = tmp_path / 'arbitrary-directory-name'
    shutil.copytree(public, moved)
    check.check_registries(moved)
    assert registry.load_registry(public=moved).resolve('TestAlias').spike_id == 'TEST'


@pytest.mark.parametrize('spike_name', ['BSU-1', 'MIT-1L', 'TestAlias'])
def test_fraction_validation_accepts_registry_names_and_aliases(public, monkeypatch, spike_name):
    from IDTIMS_UPbRPy.fractions import read_fractions
    monkeypatch.setenv('UPB_SPIKES_DIR', str(public))
    data = pd.read_csv(ROOT / 'tests/data/synthetic_template_2535.csv')
    data['Spike'] = spike_name
    table = read_fractions(StringIO(data.to_csv(index=False)))
    assert not any(i.kind == 'invalid_value' and 'Spike' in i.columns for i in table.issues())


def test_default_cache_revalidates_changed_lock(public, monkeypatch):
    monkeypatch.setenv('UPB_SPIKES_DIR', str(public))
    assert registry.get_registry().resolve('TEST').version == 'v1'
    path = public / 'TEST.toml'
    path.write_text(path.read_text().replace('1.0e-12', '2.0e-12'))
    with pytest.raises(ValueError, match='locked version changed'):
        registry.get_registry()


def test_alias_conflicts_between_spikes_are_refused(public, tmp_path):
    overlay = overlay_from_public(public, tmp_path)
    path = overlay / 'TEST.toml'
    path.write_text(path.read_text().replace('id = "TEST"', 'id = "OTHER"'))
    with pytest.raises(ValueError, match='ambiguous alias TEST'):
        check.check_registries(public, [overlay], update_lock=True)
