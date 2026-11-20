"""Qt-free tests of the app's session state and the --verify-reduction check.

These run without the gui extra: idtims_app.services and .verification import
no Qt.
"""
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from IDTIMS_UPbRPy.fractions import CONTRACT, read_fractions
from idtims_app.services import Session

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data"
SYNTHETIC = ROOT / "examples" / "synthetic_zircon_CA-ID-TIMS.csv"
TEMPLATE = DATA / "synthetic_template_2535.csv"
ENV = dict(os.environ, PYTHONPATH=os.pathsep.join(
    [str(ROOT / "src"), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep))


def test_open_synthetic_completes_import():
    session = Session()
    result = session.open_files([SYNTHETIC])
    assert result.error is None
    assert session.row_count == 12
    assert session.step_complete(0) and session.unlocked(1)
    # Tracer and Fractionation are complete with SYNTHETIC and the default settings;
    # Blanks is not (the default initial Pb has no ratios), so Th stays locked.
    assert session.unlocked(3) and not session.unlocked(4)


def test_template_quality_failures_name_the_interval():
    session = Session()
    session.open_files([TEMPLATE])
    failing = {f.fraction_id for f in session.quality_failures()}
    assert failing == {"z1", "z6"}
    reason = session.quality_failures("z1")[0].reason
    assert "204/205 = (206/205)*(204/206)" in reason
    assert "must lie between" in reason and "0.190186" in reason


@pytest.mark.parametrize('case,expected', [
    ('no reduction', '6 fractions: 6 ready, 2 failing the linked-error check'),
    ('strict', '6 fractions: 4 reduced, 2 not reduced (2 failing the linked-error check)'),
    ('diagnostic', '6 fractions: 6 reduced (2 with diagnostic substitution)'),
    ('oxide', '6 fractions: 5 reduced, 1 not reduced '
              '(1 awaiting oxide information, 2 with diagnostic substitution)'),
    ('blocks', '6 fractions: 5 reduced, 1 not reduced '
               '(2 with diagnostic substitution, 1 with missing or incomplete blocks)'),
])
def test_shared_fraction_summary(case, expected):
    from test_app_reduction import TEMPLATE_SETTINGS, session_for

    session = session_for(TEMPLATE, TEMPLATE_SETTINGS, strict=case == 'strict')
    if case == 'oxide':
        session.table.no_oxide_confirmed.remove('z2')
        session.settings_edited()
    if case == 'blocks':
        session.set_value(session.row_of('z2'), '238U/235U Mean', '')
    if case != 'no reduction':
        session.reduce()
    assert session.summary_text() == expected
    if case == 'strict':
        session.settings_edited()
        assert session.summary_text() == '6 fractions: 6 ready, 2 failing the linked-error check'


def test_summary_groups_the_actual_reduction_failure():
    from test_app_reduction import SYNTHETIC_SETTINGS, session_for

    session = session_for(SYNTHETIC, SYNTHETIC_SETTINGS, strict=True)
    session.reduce()
    # Eleven fail at tracer covariance; z10b fails the measured linked-error check first.
    assert session.summary_text() == ('12 fractions: 12 not reduced '
                                      '(11 failing the covariance check, '
                                      '1 failing the linked-error check)')


def test_pb_and_u_files_merge_and_conflicts_leave_table_unchanged(tmp_path):
    session = Session()
    session.open_files([DATA / "synthetic_pb_only.fractions.csv"])
    assert not session.step_complete(0)
    result = session.open_files([DATA / "synthetic_u_only.fractions.csv"])
    assert result.error is None and sorted(result.merged) == ["z1", "z2"]
    assert session.step_complete(0)
    other = tmp_path / "other.fractions.csv"
    other.write_text(f"Contract,Fraction ID,Sample\n{CONTRACT},z1,SYN-2\n", encoding="utf-8")
    before = session.table.frame.copy()
    result = session.open_files([other])
    assert "z1" in result.error and "Sample" in result.error
    assert session.table.frame.equals(before)


def test_missing_file_is_reported_not_raised(tmp_path):
    result = Session().open_files([tmp_path / "missing.csv"])
    assert result.error and "missing.csv" in result.error


def test_set_value_validates_and_renames():
    session = Session()
    session.open_files([SYNTHETIC])
    assert "not a number" in session.set_value(0, "Sample Weight (mg)", "abc")
    assert "already used" in session.set_value(0, "Fraction ID", "z2")
    assert session.set_value(0, "Fraction ID", "z1x") is None
    assert session.fraction_id(0) == "z1x"
    assert session.set_value(0, "Spike Type", "535.0") is None
    assert session.value(0, "Spike Type") == "535"


def test_paste_fills_from_cell_and_maps_header_rows():
    session = Session()
    session.new_table(rows=2)
    columns = session.display_columns()
    start = columns.index("206Pb/204Pb Mean")
    result = session.paste(1, start, "2400.0\t0.14\n1800\t0.2\n")
    assert result.errors == [] and result.added_rows == 1
    assert session.value(1, "206Pb/204Pb Mean") == 2400.0
    assert session.value(2, "206Pb/204Pb % Standard Error") == 0.2
    result = session.paste(0, 0, "Grain ID\tSample\nz9\tSYN-1\n")
    assert result.errors == []
    assert session.fraction_id(0) == "z9" and session.value(0, "Sample") == "SYN-1"


def test_paste_refuses_ratios_when_not_editable():
    session = Session()
    session.open_files([SYNTHETIC])
    column = session.display_columns().index("206Pb/204Pb Mean")
    result = session.paste(0, column, "1\n")
    assert result.changed == 0 and "Edit ratios" in result.errors[0]


def test_inferred_spike_type_and_oxide_confirmations(tmp_path):
    path = tmp_path / "pb.fractions.csv"
    path.write_text(f"Contract,Fraction ID,202Pb/205Pb Mean,202Pb/205Pb % Standard Error\n"
                    f"{CONTRACT},z1,0.5,0.01\n", encoding="utf-8")
    session = Session()
    session.open_files([path])
    assert "unconfirmed_spike_type" in {i.kind for i in session.issues("z1")}
    session.confirm_spike_type("z1")
    assert session.value(0, "Spike Type") == "2535"
    other = Session()
    other.open_files([SYNTHETIC])
    assert sum(i.kind == "missing_oxide" for i in other.issues()) == 12
    other.confirm_all("missing_oxide")
    assert not any(i.kind == "missing_oxide" for i in other.issues())


def test_save_round_trip(tmp_path):
    session = Session()
    session.open_files([SYNTHETIC])
    session.set_value(0, "Sample", "SYN-1-edited")
    target = tmp_path / "out.fractions.csv"
    session.save(target)
    assert not session.dirty
    again = read_fractions(target)
    original = read_fractions(SYNTHETIC)
    assert again.frame.loc[0, "Sample"] == "SYN-1-edited"
    for column in original.frame.columns:
        a, b = original.frame[column].tolist(), again.frame[column].tolist()
        assert all((x == y) or (isinstance(x, float) and math.isnan(x) and math.isnan(y))
                   for x, y in zip(a, b)), column


def test_verify_reduction_command(tmp_path):
    snapshot = DATA / "synthetic_snapshot.json"
    ok = subprocess.run([sys.executable, "-m", "idtims_app", "--verify-reduction", str(snapshot)],
                        capture_output=True, text=True, cwd=ROOT, env=ENV)
    assert ok.returncode == 0, ok.stderr
    assert json.loads(ok.stdout)["mismatches"] == 0
    data = json.loads(snapshot.read_text())
    data["th_none"]["z1"]["t68"] *= 1 + 1e-9
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(data))
    bad = subprocess.run([sys.executable, "-m", "idtims_app", "--verify-reduction", str(broken)],
                         capture_output=True, text=True, cwd=ROOT, env=ENV)
    assert bad.returncode == 1
    assert json.loads(bad.stdout)["mismatches"] == 1


def test_verify_reduction_does_not_import_qt():
    code = ("import sys\nfrom idtims_app import verification, services\n"
            "print(','.join(m for m in sys.modules if m.split('.')[0] in "
            "('PySide6', 'shiboken6', 'pyqtgraph')))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         check=True, cwd=ROOT, env=ENV)
    assert out.stdout.strip() == ""


@pytest.mark.parametrize("name", ["synthetic_pb_only.fractions.csv", "synthetic_u_only.fractions.csv"])
def test_partial_files_report_missing_block(name):
    session = Session()
    session.open_files([DATA / name])
    assert {i.kind for i in session.issues()} & {"missing_block"}
