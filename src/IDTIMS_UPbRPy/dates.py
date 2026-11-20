"""Sample dates from reduced fractions: weighted means and % discordance.

Qt-free. Nothing here changes a reduced number; these are derived outputs.

- `weighted_mean` is the inverse-variance weighted mean of 1σ inputs, with
  MSWD and probability of fit.
- `sample_dates` applies it to the 206Pb/238U, 207Pb/206Pb (each with and
  without the 230Th correction) and 207Pb/235U dates of a list of grains,
  with fractions switched on and off.
- `percent_discordance` reproduces the BSU UPbR spreadsheet's
  '% discordance' (sheet 'Data Reduction Engine', rows 40 and 50).

Uncertainty level: everything here is the analytical ("X") level of
McLean et al. (2011), with analytical errors treated as independent between
fractions. Tracer calibration ("Y") and decay-constant ("Z") terms, which
are shared by all fractions and do not average down, are not included yet;
they will follow McLean et al. (2011) and ET_Redux's `SampleDateModel`.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
from scipy import stats

__all__ = ["WeightedMean", "SampleDate", "DATE_KINDS", "weighted_mean", "sample_dates",
           "percent_discordance", "percent_discordance_from_values"]

# kind -> (date attribute, 1σ attribute). Dates and 1σ are in Ma.
DATE_KINDS = {
    "206Pb/238U": ("t68", "t68_std"),
    "206Pb/238U (Th-corrected)": ("t68_Th_corr", "t68_Th_corr_std"),
    "207Pb/206Pb": ("t76", "t76_std"),
    "207Pb/206Pb (Th-corrected)": ("t76_Th_corr", "t76_Th_corr_std"),
    "207Pb/235U": ("t75", "t75_std"),
}


@dataclass(frozen=True)
class WeightedMean:
    """Inverse-variance weighted mean of 1σ inputs.

    `sigma` is the internal 1σ of the mean (analytical "X" level).
    `sigma_expanded` is `sigma*sqrt(mswd)` when `mswd > 1`, otherwise `sigma`.
    `probability_of_fit` is the chi-square survival probability of
    `mswd*dof` with `dof = n - 1`. With n = 1, `mswd` and
    `probability_of_fit` are nan. `indices` are the positions of the values
    used, in the order given.
    """
    mean: float
    sigma: float
    n: int
    mswd: float
    dof: int
    probability_of_fit: float
    sigma_expanded: float
    indices: tuple


@dataclass(frozen=True)
class SampleDate:
    """Weighted mean of one date kind over a set of fractions.

    `result` is None when no fraction could be used. `fraction_ids` are the
    fractions in the mean; `skipped` maps every other fraction id to the
    reason it was left out.
    """
    kind: str
    result: WeightedMean | None
    fraction_ids: tuple
    skipped: dict = field(default_factory=dict)


def _selected_indices(include, size):
    """Indices chosen by `include`: None (all), a boolean mask or integer indices."""
    if include is None:
        return list(range(size))
    chosen = list(include)
    if chosen and all(isinstance(x, (bool, np.bool_)) for x in chosen):
        if len(chosen) != size:
            raise ValueError(f"include mask has {len(chosen)} entries for {size} values.")
        return [i for i, keep in enumerate(chosen) if keep]
    out = []
    for x in chosen:
        if isinstance(x, (bool, np.bool_)) or not isinstance(x, (int, np.integer)):
            raise ValueError("include must be a boolean mask or a collection of integer indices.")
        if not -size <= x < size:
            raise ValueError(f"include index {x} is out of range for {size} values.")
        out.append(int(x) % size)
    return sorted(set(out))


def weighted_mean(values, sigmas, include=None):
    """Inverse-variance weighted mean of `values` with 1σ `sigmas`.

    `include` selects the values used: None (all), a boolean mask of the same
    length, or a collection of integer indices. Only the selected values are
    checked: each must be finite with a finite, positive sigma, otherwise
    ValueError. At least one value must be selected.

    mean = Σ wᵢxᵢ / Σ wᵢ with wᵢ = 1/σᵢ²; σ(mean) = (Σ wᵢ)^-1/2;
    MSWD = Σ wᵢ(xᵢ - mean)² / (n - 1).
    """
    x = np.asarray(values, dtype=float).ravel()
    s = np.asarray(sigmas, dtype=float).ravel()
    if x.shape != s.shape:
        raise ValueError(f"values and sigmas differ in length ({x.size} and {s.size}).")
    used = _selected_indices(include, x.size)
    if len(used) < 1:
        raise ValueError("A weighted mean needs at least one value (n < 1).")
    xu, su = x[used], s[used]
    bad = [i for i, a, b in zip(used, xu, su) if not (math.isfinite(a) and math.isfinite(b))]
    if bad:
        raise ValueError(f"Non-finite value or sigma at index {bad}.")
    bad = [i for i, b in zip(used, su) if b <= 0]
    if bad:
        raise ValueError(f"Sigma must be positive; not at index {bad}.")
    w = 1.0/su**2
    mean = float(np.sum(w*xu)/np.sum(w))
    sigma = float(1.0/math.sqrt(np.sum(w)))
    n = len(used)
    dof = n - 1
    if dof > 0:
        chi2 = float(np.sum(w*(xu - mean)**2))
        mswd = chi2/dof
        probability = float(stats.chi2.sf(chi2, dof))
    else:
        mswd = probability = math.nan
    expanded = sigma*math.sqrt(mswd) if mswd > 1 else sigma
    return WeightedMean(mean=mean, sigma=sigma, n=n, mswd=mswd, dof=dof,
                        probability_of_fit=probability, sigma_expanded=expanded,
                        indices=tuple(used))


def _is_on(include, fraction_id):
    if include is None:
        return True
    if isinstance(include, Mapping):
        return bool(include.get(fraction_id, True))
    return fraction_id in include


def sample_dates(grains, include=None, kinds=tuple(DATE_KINDS)):
    """Weighted mean dates of reduced grains, one `SampleDate` per kind.

    `kinds` are keys of `DATE_KINDS`: '206Pb/238U', '206Pb/238U
    (Th-corrected)', '207Pb/206Pb', '207Pb/206Pb (Th-corrected)' and
    '207Pb/235U'. Each uses the grains' dates and their 1σ (Ma).

    `include` switches fractions on and off by fraction id (`grain.id`):
    None uses all; a mapping {id: bool} switches off the ids mapped to a
    false value (ids not in the mapping stay on); a set or other collection
    uses only the ids in it. A fraction without a finite date or a finite,
    positive 1σ of that kind is skipped, with the reason in `skipped`.

    Uncertainty level: the result is the analytical ("X") level only. The
    fractions' analytical errors are treated as independent. Tracer
    calibration ("Y") and decay-constant ("Z") uncertainties, which are
    shared between fractions, are not included yet; they will follow
    McLean et al. (2011, G-cubed 12, Q0AA18) and ET_Redux's
    `SampleDateModel` weighted mean.
    """
    out = {}
    for kind in kinds:
        if kind not in DATE_KINDS:
            raise ValueError(f"Unknown date kind {kind!r}; choose from {list(DATE_KINDS)}.")
        date_name, sigma_name = DATE_KINDS[kind]
        values, sigmas, ids, skipped = [], [], [], {}
        for grain in grains:
            fid = grain.id
            if not _is_on(include, fid):
                skipped[fid] = "switched off"
                continue
            value = getattr(grain, date_name, None)
            sigma = getattr(grain, sigma_name, None)
            try:
                value, sigma = float(value), float(sigma)
            except (TypeError, ValueError):
                skipped[fid] = f"no {kind} date"
                continue
            if not math.isfinite(value):
                skipped[fid] = f"no finite {kind} date"
            elif not math.isfinite(sigma) or sigma <= 0:
                skipped[fid] = f"no finite, positive {kind} uncertainty"
            else:
                values.append(value)
                sigmas.append(sigma)
                ids.append(fid)
        result = weighted_mean(values, sigmas) if values else None
        out[kind] = SampleDate(kind=kind, result=result, fraction_ids=tuple(ids),
                               skipped=skipped)
    return out


def percent_discordance_from_values(t76_Ma, R68, R75, lambda_238, lambda_235):
    """The BSU sheet's % discordance from a 207Pb/206Pb date and two ratios.

    `lambda_238` and `lambda_235` are in 1/year; `t76_Ma` in Ma. Returns
    nan when any input is not finite. See `percent_discordance`.
    """
    try:
        t, r68, r75 = float(t76_Ma), float(R68), float(R75)
    except (TypeError, ValueError):
        return math.nan
    if not all(math.isfinite(v) for v in (t, r68, r75)):
        return math.nan
    c68 = math.expm1(lambda_238*1e6*t)
    c75 = math.expm1(lambda_235*1e6*t)
    return 100.0*math.hypot(c68 - r68, c75 - r75)/math.hypot(c68, c75)


def percent_discordance(grain, th_corrected=False, lambda_238=None, lambda_235=None):
    """% discordance of a reduced grain, as the BSU UPbR sheet defines it.

    Decoded from 'Data Reduction Engine'!C40 (uncorrected) and C50
    (Th-corrected) of BSULab_UPbR26XML.xls::

        C40 = 100*SQRT((EXP(λ238*C34)-1-C71)^2 + (EXP(λ235*C34)-1-C69)^2)
                 / SQRT((EXP(λ238*C34)-1)^2 + (EXP(λ235*C34)-1)^2)

    with λ238 = 0.000155125 /Ma and λ235 = 0.00098485 /Ma hard-coded, C34 the
    207Pb/206Pb date (Ma), C71 the radiogenic 206Pb/238U and C69 the
    radiogenic 207Pb/235U. C50 is the same with C44, the Th-corrected
    207Pb/206Pb date, in place of C34; it keeps the uncorrected ratios C71
    and C69. (Both are wrapped in IF(... <> 0, ..., 0) to blank empty
    columns.)

    In words: the Wetherill-concordia distance between the measured point
    (207Pb/235U, 206Pb/238U) and the concordia point at the 207Pb/206Pb
    date, as a percentage of the distance of that concordia point from the
    origin. It is unsigned (never negative).

    Here λ238 and λ235 default to the grain's own decay constants (1/year),
    which equal the sheet's hard-coded values unless changed. Returns nan
    when the date or ratios are not finite.
    """
    t76 = getattr(grain, "t76_Th_corr" if th_corrected else "t76", None)
    l238 = grain.lambda_238 if lambda_238 is None else lambda_238
    l235 = grain.lambda_235 if lambda_235 is None else lambda_235
    return percent_discordance_from_values(t76, getattr(grain, "R68r", None),
                                           getattr(grain, "R75r", None), l238, l235)
