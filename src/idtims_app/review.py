"""Qt-free numbers behind the Review step: rows, concordia ellipses, weighted means.

Nothing here changes a reduced number. The table reads the reduced grains'
attributes; weighted means come from `IDTIMS_UPbRPy.dates.sample_dates`; %
discordance from `dates.percent_discordance`; Th/U, Pb*/Pbc and Pbc (pg) from
`export.bsu_table`, so they read the same as the export.

Concordia ellipses
------------------
Each fraction's 2x2 ratio covariance comes from the engine:

- Wetherill (x = 207Pb/235U, y = 206Pb/238U), uncorrected:
  R75r ± R75r_std, R68r ± R68r_std, correlation rho_7568_r.
- Tera-Wasserburg (x = 238U/206Pb, y = 207Pb/206Pb), uncorrected:
  x = 1/R68r. To first order (the engine's propagation is linear, a
  complex-step Jacobian), σx = R68r_std/R68r², which is the engine's
  R86r_std (238U/206Pb propagated from the same inputs), and the
  correlation is the engine's rho_8676_r = corr(R86r, R76r) =
  -corr(R68r, R76r). So cov(x, y) = rho_8676_r·σx·R76r_std.
  `tw_covariance_from_r68_r76` gives the same from cov(R68r, R76r) by the
  Jacobian J = diag(-1/R68r², 1); tests check both against a Monte Carlo
  transform.
- Th-corrected (only when a Th correction is set): R68r → R68r_Th and
  R76r → R76r_Th, with their joint 2x2 covariance
  `grain.th_correction_covariance` (the engine propagates the correction
  through Pb206r, Pb207r, Pb208r, U238s and the Th parameter jointly).
  R75r has no Th correction and keeps its value and σ. T-W uses
  x = 1/R68r_Th with J = diag(-1/R68r_Th², 1). Wetherill needs
  cov(R75r, R68r_Th), which the engine does not store; it follows exactly
  from the identity R75r = k·R68r_Th·R76r_Th (k = 238U/235U of the sample,
  `grain.common_U238_U235`; R76r_Th = Pb207r/Pb206r_Th, R75r =
  Pb207r·k/U238s, R68r_Th = Pb206r_Th/U238s), with J = [[k·b, k·a], [1, 0]]
  for a = R68r_Th, b = R76r_Th. The same identity holds uncorrected, and the
  σ(R75r) it implies equals the engine's R75r_std (checked in the tests).

The ellipse itself follows Studio (`ellipse_coordinates_batch`): the
covariance ellipse scaled by 2 along its principal axes, so its projection
on each axis is ±2σ ("2σ marginal"; it encloses about 86.5 % of a bivariate
normal, not 95 %).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from IDTIMS_UPbRPy import dates
from IDTIMS_UPbRPy.export import bsu_table

from idtims_app.reduction import DIAGNOSTIC, NOT_REDUCED

WETHERILL, TERA_WASSERBURG = "wetherill", "tw"
DIAGRAMS = {WETHERILL: "Wetherill", TERA_WASSERBURG: "Tera-Wasserburg"}
DEFAULT_KIND = "206Pb/238U"
DEFAULT_KIND_TH = "206Pb/238U (Th-corrected)"
ALL_BLANK, BLANK_AND_INITIAL = "all blank", "blank + initial"
ELLIPSE_CAPTION = "Ellipses 2σ (each axis ±2σ; ≈86 % joint)"
_RESIDUE = 1e-9
IDENTIFIERS = ("Sample", "Beaker", "Annealing", "Chemical Abrasion", "Source Mount",
               "Source Grain", "Source Spot", "Database link")


def finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def common_pb_rule(grain):
    """'all blank' when Pb204c is zero within 1e-9 of Pb204b, else 'blank + initial'."""
    pb204c, pb204b = _float(getattr(grain, "Pb204c", 0.0)), _float(getattr(grain, "Pb204b", 0.0))
    if not math.isfinite(pb204c):
        return ""
    return ALL_BLANK if abs(pb204c) <= _RESIDUE * abs(pb204b) else BLANK_AND_INITIAL


@dataclass
class ReviewRow:
    """One fraction as Review shows it."""
    fraction_id: str
    status: str
    reason: str = ""
    grain: object = None
    identifiers: dict = field(default_factory=dict)
    quality: list = field(default_factory=list)
    substitutions: list = field(default_factory=list)
    values: dict = field(default_factory=dict)

    @property
    def reduced(self):
        return self.status != NOT_REDUCED

    @property
    def diagnostic(self):
        return self.status == DIAGNOSTIC


def build_rows(run, identifiers=None):
    """ReviewRow per fraction of a ReductionRun, in table order (not-reduced ones too)."""
    identifiers = identifiers or {}
    grains = run.grains
    th = run.th_kind is not None
    table = bsu_table(grains) if grains else None
    by_id = {}
    if table is not None:
        for index, grain in enumerate(grains):
            by_id[str(grain.id)] = table.iloc[index]
    rows = []
    for result in run.results:
        fid = result.fraction_id
        row = ReviewRow(fid, result.status, result.reason, result.grain,
                        dict(identifiers.get(fid, {})), list(result.quality),
                        list(result.substitutions))
        grain = result.grain
        if grain is not None:
            bsu = by_id.get(str(grain.id))
            values = {
                "t68": (grain.t68, grain.t68_std), "t75": (grain.t75, grain.t75_std),
                "t76": (grain.t76, grain.t76_std),
                "t68_th": (grain.t68_Th_corr, grain.t68_Th_corr_std) if th else None,
                "t76_th": (grain.t76_Th_corr, grain.t76_Th_corr_std) if th else None,
                "disc": dates.percent_discordance(grain),
                "disc_th": dates.percent_discordance(grain, th_corrected=True) if th else None,
                "pbr_pbc": _float(bsu["Pb*/Pbc"]) if bsu is not None else math.nan,
                "pbc_pg": _float(bsu["Pbc (pg)"]) if bsu is not None else math.nan,
                "th_u": _float(bsu["Th/U"]) if bsu is not None else math.nan,
                "common_pb": common_pb_rule(grain),
            }
            row.values = values
        rows.append(row)
    return rows


# -- concordia geometry --------------------------------------------------------
def th_available(grain):
    cov = getattr(grain, "th_correction_covariance", None)
    return cov is not None and np.shape(cov) == (2, 2) and \
        getattr(grain, "Th230_correction_type", None) is not None


def tw_covariance_from_r68_r76(r68, r76, cov_68_76):
    """(x, y, Σ) for x = 1/R68, y = R76 from the 2x2 covariance of (R68, R76)."""
    jacobian = np.array([[-1.0 / r68**2, 0.0], [0.0, 1.0]])
    return 1.0 / r68, r76, jacobian @ np.asarray(cov_68_76, dtype=float) @ jacobian.T


def wetherill_covariance_from_r68_r76(r68, r76, cov_68_76, k):
    """(x, y, Σ) for x = R75 = k·R68·R76, y = R68 from the covariance of (R68, R76)."""
    jacobian = np.array([[k * r76, k * r68], [1.0, 0.0]])
    return k * r68 * r76, r68, jacobian @ np.asarray(cov_68_76, dtype=float) @ jacobian.T


def ratio_covariance(grain, diagram, th_corrected=False):
    """(x, y, σx, σy, ρ) of one grain on a diagram, or None when not finite.

    See the module docstring for which attributes each case reads.
    """
    if th_corrected and th_available(grain):
        a, b = grain.R68r_Th, grain.R76r_Th
        cov = np.asarray(grain.th_correction_covariance, dtype=float)
        if diagram == TERA_WASSERBURG:
            x, y, sigma = tw_covariance_from_r68_r76(a, b, cov)
        else:
            k = grain.common_U238_U235
            _x75, y, sigma = wetherill_covariance_from_r68_r76(a, b, cov, k)
            # R75r is not Th-corrected; its value and σ stay the engine's.
            x = grain.R75r
            sx = grain.R75r_std
            sy = math.sqrt(max(sigma[1, 1], 0.0))
            rho = sigma[0, 1] / (math.sqrt(max(sigma[0, 0], 0.0)) * sy) \
                if sigma[0, 0] > 0 and sy > 0 else 0.0
            return _checked(x, y, sx, sy, rho)
        sx, sy = math.sqrt(max(sigma[0, 0], 0.0)), math.sqrt(max(sigma[1, 1], 0.0))
        rho = sigma[0, 1] / (sx * sy) if sx > 0 and sy > 0 else 0.0
        return _checked(x, y, sx, sy, rho)
    if diagram == TERA_WASSERBURG:
        r68, s68 = grain.R68r, grain.R68r_std
        x = 1.0 / r68
        sx = s68 / r68**2
        return _checked(x, grain.R76r, sx, grain.R76r_std, grain.rho_8676_r)
    return _checked(grain.R75r, grain.R68r, grain.R75r_std, grain.R68r_std, grain.rho_7568_r)


def _checked(x, y, sx, sy, rho):
    values = [_float(v) for v in (x, y, sx, sy, rho)]
    if not all(math.isfinite(v) for v in values[:4]):
        return None
    if not math.isfinite(values[4]):
        values[4] = 0.0
    values[4] = float(np.clip(values[4], -1.0, 1.0))
    return tuple(values)


def concordia_curve(diagram, lambda_238, lambda_235, k, ages_ma):
    """Concordia (x, y) at `ages_ma` (Ma) from decay constants in 1/year."""
    t = np.asarray(ages_ma, dtype=float) * 1e6
    r68 = np.expm1(lambda_238 * t)
    r75 = np.expm1(lambda_235 * t)
    if diagram == TERA_WASSERBURG:
        with np.errstate(divide="ignore", invalid="ignore"):
            return 1.0 / r68, r75 / (k * r68)
    return r75, r68


def decay_constants(grains):
    """(λ238, λ235, k) of the run (all grains share them)."""
    grain = grains[0]
    return grain.lambda_238, grain.lambda_235, grain.common_U238_U235


# -- weighted mean ---------------------------------------------------------------
def date_kinds(th):
    """Kinds offered on the weighted-mean panel (Th-corrected ones only with a Th correction)."""
    return [k for k in dates.DATE_KINDS if th or "Th-corrected" not in k]


def default_kind(th):
    return DEFAULT_KIND_TH if th else DEFAULT_KIND


def included_ids(grains, excluded):
    return [str(g.id) for g in grains if str(g.id) not in excluded]


def sample_date(grains, excluded, kind):
    """`dates.sample_dates` for one kind over the included fractions."""
    include = set(included_ids(grains, excluded))
    return dates.sample_dates(grains, include=include, kinds=(kind,))[kind]


def ranked_dates(grains, kind):
    """[(fraction id, date, 1σ)] with a finite date and positive σ, youngest first."""
    date_name, sigma_name = dates.DATE_KINDS[kind]
    out = []
    for grain in grains:
        value, sigma = _float(getattr(grain, date_name, None)), \
            _float(getattr(grain, sigma_name, None))
        if math.isfinite(value) and math.isfinite(sigma) and sigma > 0:
            out.append((str(grain.id), value, sigma))
    return sorted(out, key=lambda item: item[1])


def mean_lines(sample, total):
    """Readable lines for a SampleDate: mean ± 2σ, MSWD, n of N, p, expanded."""
    result = sample.result
    if result is None:
        return ["No fraction is included, or none has this date."]
    lines = [f"{result.mean:.3f} ± {2 * result.sigma:.3f} Ma (2σ, X: analytical)"]
    if result.n > 1:
        lines.append(f"MSWD {result.mswd:.3g}, n = {result.n} of {total}, "
                     f"probability of fit {result.probability_of_fit:.3g}")
    else:
        lines.append(f"n = 1 of {total}: no MSWD or probability of fit")
    if result.n > 1 and result.mswd > 1:
        lines.append(f"Expanded ± {2 * result.sigma_expanded:.3f} Ma (2σ·√MSWD)")
    return lines
