"""Numbers check of the app's per-fraction reduction (Qt-free).

The Reduce step calls `load_grains` once per fraction. These tests prove that
this gives bit-identical grains to a direct `load_grains` call:

(a) SYNTHETIC with the snapshot settings in diagnostic mode equals
    tests/data/synthetic_snapshot.json exactly, for every fraction and all three Th
    variants, and every numeric attribute equals one batch `load_grains` call;
(b) the BSU template with tests/data/settings_BSU_template.json reproduces the synthetic
    t68 values asserted in tests/test_et2535.py (same tolerance) and equals a
    direct call bit for bit;
(c) strict mode on the template reduces z2-z5 and reports z1/z6 as not
    reduced with the reason and the diagnostic-mode hint;
(d) require_oxide leaves unconfirmed fractions out, with the reason.

settings_BSU_template.json carries the template's blanks, initial Pb and Th
settings. The template's own decay constants (its lambda_230 is 9.158e-6) are
not part of the settings and are NOT applied: the engine constants stay.
"""
import copy
import json
import math
import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

from IDTIMS_UPbRPy import UPbR
from IDTIMS_UPbRPy.settings import ReductionSettings
from idtims_app.reduction import DIAGNOSTIC, NOT_REDUCED, REDUCED
from idtims_app.services import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from snapshot_support import grain_numbers  # noqa: E402
from test_et2535 import SHEET  # noqa: E402

SYNTHETIC = ROOT / "examples" / "synthetic_zircon_CA-ID-TIMS.csv"
SYNTHETIC_SETTINGS = ROOT / "examples" / "synthetic_settings.json"
TEMPLATE = ROOT / "tests" / "data" / "synthetic_template_2535.csv"
TEMPLATE_SETTINGS = ROOT / "tests" / "data" / "settings_BSU_template.json"
SNAPSHOT = ROOT / "tests" / "data" / "synthetic_snapshot.json"
CHECKED = ["t68", "t76", "t75", "t68_std", "t76_std", "t75_std", "R68r", "R75r", "R76r",
           "rho_7568_r", "rho_8676_r"]
TH_VARIANTS = {
    "th_D": dict(kind="D", D_Th_U=0.2, D_Th_U_std=0.05, Th_U_magma=3, Th_U_magma_std=0.05),
    "th_magma": dict(kind="magma", Th_U_magma=3, Th_U_magma_std=0.5),
    "th_none": dict(kind=None),
}


def session_for(path, settings_path, *, strict, confirm=True):
    session = Session()
    assert session.open_files([path]).error is None
    if confirm:
        session.confirm_all("missing_oxide")
    error, _note = session.load_settings(settings_path)
    assert error is None
    session.set_strict_covariance(strict)
    return session


def same(a, b):
    """Bitwise equality of floats and float lists (nan equals nan)."""
    if isinstance(a, list):
        return isinstance(b, list) and len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return (math.isnan(a) and math.isnan(b)) or a == b


def batch(data, settings, **kwargs):
    args, keywords = settings.load_grains_arguments()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return UPbR.load_grains(data, *args, **keywords, **kwargs)


@pytest.mark.parametrize("variant", sorted(TH_VARIANTS))
def test_synthetic_per_fraction_equals_snapshot_and_batch(variant):
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))[variant]
    session = session_for(SYNTHETIC, SYNTHETIC_SETTINGS, strict=False)
    th = dict(TH_VARIANTS[variant])
    for name, value in th.items():
        setattr(session.settings.th_correction, name, value)
    session.settings_edited()
    run = session.reduce()
    assert [r.fraction_id for r in run.results] == session.table.fraction_ids
    assert all(r.reduced for r in run.results)
    got = {r.fraction_id: grain_numbers(r.grain) for r in run.results}
    assert sorted(got) == sorted(expected)
    for fid, numbers in expected.items():
        for name in CHECKED:
            assert got[fid][name] == numbers[name], (variant, fid, name)
    # Every numeric attribute equals the snapshot and one batch call over the raw CSV.
    settings = copy.deepcopy(session.settings)
    settings.strict_covariance = False
    direct = {str(g.id): grain_numbers(g) for g in batch(pd.read_csv(SYNTHETIC), settings)}
    for fid, numbers in got.items():
        assert sorted(numbers) == sorted(direct[fid])
        for name, value in numbers.items():
            assert same(value, direct[fid][name]), (variant, fid, name)
            assert same(value, expected[fid][name]), (variant, fid, name)


def test_synthetic_diagnostic_marks_substitutions():
    run = session_for(SYNTHETIC, SYNTHETIC_SETTINGS, strict=False).reduce()
    # SYNTHETIC's BSU1B tracer covariance is substituted for every fraction.
    assert {r.status for r in run.results} == {DIAGNOSTIC}
    assert all(r.substitutions for r in run.results)


def test_synthetic_strict_reduces_nothing_and_says_why():
    session = session_for(SYNTHETIC, SYNTHETIC_SETTINGS, strict=True)
    run = session.reduce()
    assert {r.status for r in run.results} == {NOT_REDUCED}
    z1 = run.result("z1")
    assert "tracer 206Pb/205Pb" in z1.reason and "tracer 204Pb/205Pb" in z1.reason
    assert "Diagnostic mode" in z1.hint
    assert not session.step_complete(5)


def test_template_diagnostic_reproduces_synthetic_t68_and_direct_call():
    session = session_for(TEMPLATE, TEMPLATE_SETTINGS, strict=False)
    run = session.reduce()
    grains = {r.fraction_id: r.grain for r in run.results}
    assert list(grains) == ["z1", "z2", "z3", "z4", "z5", "z6"]
    for fid, value in zip(grains, SHEET["t68"]):
        assert grains[fid].t68 == pytest.approx(value, rel=1e-9, abs=0)
    settings = copy.deepcopy(session.settings)
    settings.strict_covariance = False
    direct = {str(g.id): g for g in batch(pd.read_csv(TEMPLATE), settings)}
    for fid, grain in grains.items():
        a, b = grain_numbers(grain), grain_numbers(direct[fid])
        assert sorted(a) == sorted(b)
        assert all(same(a[n], b[n]) for n in a), fid
    assert run.result("z1").status == DIAGNOSTIC and run.result("z6").status == DIAGNOSTIC
    assert {run.result(f).status for f in ("z2", "z3", "z4", "z5")} == {REDUCED}


def test_template_settings_keep_engine_decay_constants():
    from IDTIMS_UPbRPy import constants

    session = session_for(TEMPLATE, TEMPLATE_SETTINGS, strict=True)
    run = session.reduce()
    assert run.result("z2").grain.lambda_230 == constants.lambda_230 == 9.195e-6


def test_template_strict_reduces_z2_to_z5_and_reports_z1_z6():
    session = session_for(TEMPLATE, TEMPLATE_SETTINGS, strict=True)
    run = session.reduce()
    status = {r.fraction_id: r.status for r in run.results}
    assert status == dict(z1=NOT_REDUCED, z2=REDUCED, z3=REDUCED, z4=REDUCED, z5=REDUCED,
                          z6=NOT_REDUCED)
    for fid in ("z1", "z6"):
        result = run.result(fid)
        assert "Impossible covariance" in result.reason
        assert "204/205 = (206/205)*(204/206)" in result.reason
        assert "per-project choice" in result.hint
        assert result.quality, "the linked-error marker carries the import-check reason"
        assert result.grain is None
    assert session.strict_covariance is True  # nothing switched
    assert session.step_complete(5)
    # Strict grains equal a direct strict call on the same rows.
    settings = copy.deepcopy(session.settings)
    settings.strict_covariance = True
    direct = batch(pd.read_csv(TEMPLATE).iloc[1:5], settings)
    for g in direct:
        a, b = grain_numbers(run.result(g.id).grain), grain_numbers(g)
        assert all(same(a[n], b[n]) for n in a)


def test_require_oxide_excludes_unconfirmed_fractions():
    session = session_for(TEMPLATE, TEMPLATE_SETTINGS, strict=False, confirm=False)
    session.confirm_no_oxide("z2")
    session.set_value(session.row_of("z3"), "U Oxide 18O/16O", "0.00205")
    # Contract clarification 6: a filled oxide value also needs its formula.
    assert "z3" not in [r.fraction_id for r in session.reduce().results if r.reduced]
    session.set_value(session.row_of("z3"), "U Oxide Formula", "instrument")
    run = session.reduce()
    reduced = [r.fraction_id for r in run.results if r.reduced]
    assert reduced == ["z2", "z3"]
    for fid in ("z1", "z4", "z5", "z6"):
        result = run.result(fid)
        assert result.status == NOT_REDUCED
        assert "U oxide" in result.reason and "U Oxide 18O/16O is empty" in result.reason


def test_results_go_stale_after_edits_and_mode_changes():
    session = session_for(TEMPLATE, TEMPLATE_SETTINGS, strict=True)
    session.reduce()
    assert session.reduction_current and session.step_complete(5)
    session.set_strict_covariance(False)
    assert not session.reduction_current and not session.step_complete(5)
    session.reduce()
    session.settings.lab_blanks.Pb_blank_total = 0.6
    session.settings_edited()
    assert not session.reduction_current


def test_job_snapshot_is_independent_of_later_edits():
    session = session_for(TEMPLATE, TEMPLATE_SETTINGS, strict=True)
    job = session.prepare_reduction()
    session.settings.lab_blanks.Pb_blank_total = 50.0
    session.set_value(session.row_of("z2"), "Sample Weight (mg)", "0.5")
    run = job.run()
    reference = session_for(TEMPLATE, TEMPLATE_SETTINGS, strict=True).reduce()
    assert run.result("z2").grain.t68 == reference.result("z2").grain.t68


def test_export_full_table(tmp_path):
    session = session_for(TEMPLATE, TEMPLATE_SETTINGS, strict=True)
    session.reduce()
    path = tmp_path / "full.csv"
    session.export_full_table(path)
    frame = pd.read_csv(path)
    assert list(frame["id"]) == ["z2", "z3", "z4", "z5"]
    assert frame["t68"].tolist() == [session.reduction.result(f).grain.t68
                                     for f in ("z2", "z3", "z4", "z5")]


def test_settings_round_trip_and_mode_not_taken_from_file(tmp_path):
    session = Session()
    error, note = session.load_settings(SYNTHETIC_SETTINGS)
    assert error is None and note is None  # the example is saved in strict mode
    diagnostic_file = tmp_path / "diagnostic.json"
    data = json.loads(SYNTHETIC_SETTINGS.read_text())
    data["strict_covariance"] = False
    diagnostic_file.write_text(json.dumps(data))
    error, note = session.load_settings(diagnostic_file)
    assert error is None
    assert "diagnostic" in note and session.strict_covariance is True
    assert session.settings.th_correction.kind == "D"
    path = tmp_path / "s.json"
    session.save_settings(path)
    data = json.loads(path.read_text())
    assert data["strict_covariance"] is True
    reloaded = ReductionSettings.from_dict(data)
    assert reloaded.lab_blanks == session.settings.lab_blanks
    bad = tmp_path / "bad.json"
    bad.write_text('{"format": "other"}')
    before = session.settings
    error, _ = session.load_settings(bad)
    assert "not an ID-TIMS reduction settings file" in error and session.settings is before


def test_default_settings_and_steps():
    session = Session()
    assert session.settings == ReductionSettings()
    assert session.open_files([SYNTHETIC]).error is None
    assert session.step_complete(0) and session.step_complete(1)
    assert session.step_complete(2)  # fractionation defaults are valid
    assert not session.step_complete(3)  # initial Pb must be entered
    assert "Initial Pb 206Pb/204Pb is missing." in session.section_problems("blanks")
    assert session.step_complete(4)  # no Th correction


def test_tracer_version_and_fpb_2535():
    session = Session()
    session.open_files([TEMPLATE])
    assert session.tracers_in_use() == ["ET2535"]
    assert session.tracer_version("ET2535") == "v3"
    assert session.tracer_file("ET2535") == "ET2535_v3.csv"
    session.settings.spike_version = "v1"
    session.settings_edited()
    assert session.tracer_problems() and not session.step_complete(1)
    session.settings.spike_version = None
    rows = session.fpb_2535()
    assert [r[0] for r in rows] == ["z1", "z2", "z3", "z4", "z5", "z6"]
    for row, value, std in zip(rows, SHEET["FPb"], SHEET["FPb_std"]):
        assert row[5] == pytest.approx(value, rel=1e-12)
        assert row[6] == pytest.approx(std, rel=1e-12)
    table = dict((q, (v, e)) for q, _u, v, e in session.tracer_table("ET2535"))
    assert table["202Pb/205Pb"] == (0.999239128056085, 0.02657)


def test_fill_down_and_set_many():
    session = Session()
    session.open_files([TEMPLATE])
    errors = session.set_many([0, 1, 2], "Spike Weight (g)", "0.02")
    assert errors == [] and [session.value(r, "Spike Weight (g)") for r in range(3)] == [0.02] * 3
    session.set_value(3, "Sample Weight (mg)", "0.004")
    assert session.fill_down([3, 4, 5], "Sample Weight (mg)") == []
    assert [session.value(r, "Sample Weight (mg)") for r in (3, 4, 5)] == [0.004] * 3
    assert session.set_many([0], "Collector", "X") == []  # accepted; reported as an issue
    assert any(i.kind == "invalid_value" for i in session.issues("z1"))
