"""Qt-free checks of the Review step's numbers (idtims_app.review, Session include set).

(a) The Tera-Wasserburg covariance (x = 1/R68r) used for the ellipses equals a
    Monte Carlo and a finite-difference transform of the engine's (R68r, R76r)
    covariance for one SYNTHETIC grain.
(b) The Th-corrected toggle changes 206Pb/238U and 207Pb/206Pb (and so
    238U/206Pb) to the engine's Th-corrected values and leaves 207Pb/235U as
    it is; the Wetherill correlation it implies is consistent with R75r_std.
(c) The weighted mean of an include set is `dates.sample_dates` of it.
(d) The include set survives re-reduction for fractions still present, and
    step 7 completes only while a fraction is switched on.
"""
import math
from pathlib import Path

import numpy as np
import pytest

from IDTIMS_UPbRPy import dates
from idtims_app import review
from idtims_app.services import Session

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC = ROOT / "examples" / "synthetic_zircon_CA-ID-TIMS.csv"
SYNTHETIC_SETTINGS = ROOT / "examples" / "synthetic_settings.json"
TEMPLATE = ROOT / "tests" / "data" / "synthetic_template_2535.csv"
TEMPLATE_SETTINGS = ROOT / "tests" / "data" / "settings_BSU_template.json"


def reduced_session(path, settings, strict):
    session = Session()
    assert session.open_files([path]).error is None
    session.confirm_all("missing_oxide")
    assert session.load_settings(settings)[0] is None
    session.set_strict_covariance(strict)
    session.reduce()
    return session


@pytest.fixture(scope="module")
def synthetic():
    return reduced_session(SYNTHETIC, SYNTHETIC_SETTINGS, strict=False)


def _cov_68_76(grain):
    names = list(grain.reduction_covariance_names)
    index = [names.index("R68r"), names.index("R76r")]
    return np.asarray(grain.reduction_covariance)[np.ix_(index, index)]


def test_tw_covariance_matches_monte_carlo_and_finite_difference(synthetic):
    grain = synthetic.reduction.grains[0]
    x, y, sx, sy, rho = review.ratio_covariance(grain, review.TERA_WASSERBURG)
    assert x == pytest.approx(1 / grain.R68r, rel=1e-15)
    assert y == grain.R76r
    # The engine's own 238U/206Pb error, propagated from the inputs, agrees.
    assert sx == pytest.approx(grain.R86r_std, rel=1e-12)
    cov = _cov_68_76(grain)
    # Monte Carlo: sample (R68r, R76r), transform, compare the sample covariance.
    rng = np.random.default_rng(20261114)
    samples = rng.multivariate_normal([grain.R68r, grain.R76r], cov, size=400_000)
    transformed = np.column_stack([1 / samples[:, 0], samples[:, 1]])
    mc = np.cov(transformed, rowvar=False)
    assert math.sqrt(mc[0, 0]) == pytest.approx(sx, rel=5e-3)
    assert math.sqrt(mc[1, 1]) == pytest.approx(sy, rel=5e-3)
    assert mc[0, 1] / math.sqrt(mc[0, 0] * mc[1, 1]) == pytest.approx(rho, abs=5e-3)
    # Finite-difference Jacobian of (R68, R76) -> (1/R68, R76).
    step = grain.R68r * 1e-6
    jacobian = np.array([[(1 / (grain.R68r + step) - 1 / (grain.R68r - step)) / (2 * step), 0],
                         [0, 1]])
    fd = jacobian @ cov @ jacobian.T
    assert math.sqrt(fd[0, 0]) == pytest.approx(sx, rel=1e-8)
    assert fd[0, 1] / math.sqrt(fd[0, 0] * fd[1, 1]) == pytest.approx(rho, abs=1e-8)
    # rho_8676_r is corr(238/206, 207/206) = -corr(206/238, 207/206).
    assert rho == pytest.approx(-cov[0, 1] / math.sqrt(cov[0, 0] * cov[1, 1]), abs=1e-12)


def test_wetherill_uses_engine_values_and_identity_holds(synthetic):
    for grain in synthetic.reduction.grains:
        x, y, sx, sy, rho = review.ratio_covariance(grain, review.WETHERILL)
        assert (x, y, sx, sy, rho) == (grain.R75r, grain.R68r, grain.R75r_std,
                                       grain.R68r_std, grain.rho_7568_r)
        # R75r = k*R68r*R76r: the Wetherill covariance follows from (R68r, R76r).
        x2, _y2, sigma = review.wetherill_covariance_from_r68_r76(
            grain.R68r, grain.R76r, _cov_68_76(grain), grain.common_U238_U235)
        assert x2 == pytest.approx(grain.R75r, rel=1e-12)
        assert math.sqrt(sigma[0, 0]) == pytest.approx(grain.R75r_std, rel=1e-9)
        assert sigma[0, 1] / math.sqrt(sigma[0, 0] * sigma[1, 1]) == \
            pytest.approx(grain.rho_7568_r, abs=1e-9)


def test_th_toggle_changes_206_238_and_207_206_only(synthetic):
    assert synthetic.th_correction_applied
    for grain in synthetic.reduction.grains:
        plain = review.ratio_covariance(grain, review.WETHERILL)
        th = review.ratio_covariance(grain, review.WETHERILL, th_corrected=True)
        # 207Pb/235U: same value and σ; 206Pb/238U: the Th-corrected value and σ.
        assert th[0] == plain[0] == grain.R75r and th[2] == plain[2] == grain.R75r_std
        assert th[1] == grain.R68r_Th and th[3] == pytest.approx(grain.R68r_Th_std, rel=1e-12)
        assert th[1] != plain[1]
        # σ(R75r) implied by the Th covariance and R75r = k*R68r_Th*R76r_Th.
        _x, _y, sigma = review.wetherill_covariance_from_r68_r76(
            grain.R68r_Th, grain.R76r_Th, grain.th_correction_covariance,
            grain.common_U238_U235)
        assert math.sqrt(sigma[0, 0]) == pytest.approx(grain.R75r_std, rel=1e-9)
        tw = review.ratio_covariance(grain, review.TERA_WASSERBURG, th_corrected=True)
        tw_plain = review.ratio_covariance(grain, review.TERA_WASSERBURG)
        assert tw[0] == pytest.approx(1 / grain.R68r_Th, rel=1e-15) and tw[0] != tw_plain[0]
        assert tw[1] == grain.R76r_Th and tw[1] != tw_plain[1]
        assert tw[3] == pytest.approx(grain.R76r_Th_std, rel=1e-12)
        assert tw[2] == pytest.approx(grain.R68r_Th_std / grain.R68r_Th**2, rel=1e-12)


def test_th_toggle_ignored_without_th_correction():
    session = Session()
    session.open_files([SYNTHETIC])
    session.confirm_all("missing_oxide")
    session.load_settings(SYNTHETIC_SETTINGS)
    session.settings.th_correction.kind = None
    session.settings_edited()
    session.set_strict_covariance(False)
    session.reduce()
    assert not session.th_correction_applied and not session.review_th_shown()
    assert session.review_date_kind() == "206Pb/238U"
    assert review.date_kinds(False) == ["206Pb/238U", "207Pb/206Pb", "207Pb/235U"]


@pytest.mark.parametrize("excluded", [set(), {"z3"}, {"z1", "z7", "z10b"},
                                      {"z2", "z4", "z6", "z8", "z9a"}])
def test_weighted_mean_is_sample_dates(synthetic, excluded):
    grains = synthetic.reduction.grains
    for kind in dates.DATE_KINDS:
        ours = review.sample_date(grains, excluded, kind)
        include = {g.id for g in grains} - excluded
        assert ours == dates.sample_dates(grains, include=include, kinds=(kind,))[kind]


def test_include_set_survives_reduction_and_completes_step(synthetic):
    session = reduced_session(SYNTHETIC, SYNTHETIC_SETTINGS, strict=False)
    assert session.review_date_kind() == "206Pb/238U (Th-corrected)"
    assert session.step_complete(6) and session.unlocked(7)
    session.set_included("z3", False)
    session.set_included("z7", False)
    session.reduce()
    assert session.excluded_fractions == {"z3", "z7"}
    assert "z3" not in session.included_ids()
    for fid in session.included_ids():
        session.set_included(fid, False)
    assert not session.step_complete(6) and not session.unlocked(7)
    session.set_included("z1", True)
    assert session.step_complete(6)
    # Fractions no longer in the run are forgotten.
    session.excluded_fractions.add("gone")
    session.reduce()
    assert "gone" not in session.excluded_fractions


def test_template_rows_and_common_pb_rule():
    session = reduced_session(TEMPLATE, TEMPLATE_SETTINGS, strict=True)
    rows = review.build_rows(session.reduction, session.fraction_identifiers())
    assert [r.fraction_id for r in rows] == ["z1", "z2", "z3", "z4", "z5", "z6"]
    assert [r.reduced for r in rows] == [False, True, True, True, True, False]
    assert rows[0].reason.startswith("Impossible covariance") and rows[0].quality
    for row in rows[1:5]:
        assert row.values["common_pb"] == review.ALL_BLANK  # template has no initial Pb
        assert row.values["disc"] == dates.percent_discordance(row.grain)
        assert row.values["disc_th"] == dates.percent_discordance(row.grain, th_corrected=True)
    sample = review.sample_date(session.reduction.grains, set(), session.review_date_kind())
    assert sample.fraction_ids == ("z2", "z3", "z4", "z5")


def test_common_pb_rule_threshold():
    class Grain:
        Pb204b = 1e-16
    grain = Grain()
    grain.Pb204c = 1e-26
    assert review.common_pb_rule(grain) == review.ALL_BLANK
    grain.Pb204c = 1e-24
    assert review.common_pb_rule(grain) == review.BLANK_AND_INITIAL
