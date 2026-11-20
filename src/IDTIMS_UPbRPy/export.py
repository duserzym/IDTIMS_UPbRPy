"""Tables for export: the BSU-style data table, its footnotes and a full table.

Qt-free; needs pandas only (openpyxl for the optional XLSX writer).

- `bsu_table` lays reduced grains out as the BSU UPbR spreadsheet's
  'U-Pb Data Table Output' sheet does. `BSU_COLUMNS` describes each column:
  its group, header label, footnote letter, unit and sigma level, the sheet
  column it reproduces and the engine quantity it comes from.
- `footnotes` writes footnotes (a) to (j) for the settings in use.
- `full_table` puts every numeric scalar attribute of every grain in one
  wide frame; `write_csv` writes any frame with 17 significant digits.
- `write_xlsx` writes a BSU table with its grouped header and footnotes,
  when openpyxl is installed.

Uncertainties come from the engine's joint first-order propagation and are
not expected to equal the spreadsheet's (see docs/BSU_SHEET_NOTES.md).
"""
from __future__ import annotations

import math
import numbers
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import constants
from .dates import percent_discordance

__all__ = ["ColumnSpec", "BSU_COLUMNS", "IDENTIFIER_COLUMNS", "bsu_columns", "bsu_table",
           "with_groups", "footnotes", "full_table", "write_csv", "write_xlsx"]

# Identifier columns: (column name, grain attribute).
IDENTIFIER_COLUMNS = (("Sample", "sample"), ("Fraction ID", "id"), ("Beaker", "beaker"),
                      ("Source Mount", "source_mount"), ("Source Grain", "source_grain"),
                      ("Source Spot", "source_spot"), ("Capsule Set", "capsule_set"),
                      ("Annealing", "annealing"), ("Chemical Abrasion", "chemical_abrasion"),
                      ("Annealing Temperature (°C)", "annealing_temperature"),
                      ("Annealing Duration (h)", "annealing_duration"),
                      ("Chemical Abrasion Temperature (°C)", "chemical_abrasion_temperature"),
                      ("Chemical Abrasion Duration (h)", "chemical_abrasion_duration"),
                      ("Spike Solution", "spike_solution"))
IDENTIFIER_GROUP = "Fraction"


@dataclass(frozen=True)
class ColumnSpec:
    """One column of the BSU table.

    `key` is the unique DataFrame column name; `label` is the header text,
    which may repeat (e.g. '± 2σ %'); `group` is the header group; `note`
    is the footnote letter. `sheet_column` and `source` say which column of
    'U-Pb Data Table Output' it reproduces and where the engine value comes
    from. `kind` is 'value', 'uncertainty' or 'correlation'.
    """
    key: str
    group: str
    label: str
    note: str
    unit: str
    sheet_column: str
    source: str
    kind: str = "value"


_COMP = "Compositional Parameters"
_RAD = "Radiogenic Isotope Ratios"
_DATES = "Dates (Ma)"
_SAMPLE = "Sample (Radiogenic + Initial Pb) Isotope Ratios"
_PCT = "%, 2σ"

BSU_COLUMNS = (
    ColumnSpec("Th/U", _COMP, "Th/U", "b", "atomic", "B",
               "Th232s/(U238s+U235s)"),
    ColumnSpec("206Pb* (x10-13 mol)", _COMP, "206Pb* (x10-13 mol)", "c", "1e-13 mol", "C",
               "Pb206r*1e13"),
    ColumnSpec("mol % 206Pb*", _COMP, "mol % 206Pb*", "c", "%", "D",
               "100*Pb206r/(Pb206r+Pb206b+Pb206c)"),
    ColumnSpec("Pb*/Pbc", _COMP, "Pb*/Pbc", "c", "mass ratio", "E", "Pbr_Pbc"),
    ColumnSpec("Pbc (pg)", _COMP, "Pbc (pg)", "c", "pg", "F", "Pbc_pg"),
    ColumnSpec("206Pb/204Pb", _COMP, "206Pb/204Pb", "d", "", "G",
               "(Pb206r+Pb206b+Pb206c)/(Pb204b+Pb204c)"),
    ColumnSpec("208Pb/206Pb", _RAD, "208Pb/206Pb", "e", "", "I", "Pb208r/Pb206r"),
    ColumnSpec("207Pb/206Pb", _RAD, "207Pb/206Pb", "e", "", "J", "R76r (R76r_Th if Th-corrected ratios)"),
    ColumnSpec("207Pb/206Pb % err", _RAD, "% err", "f", _PCT, "K",
               "200*R76r_std/R76r", "uncertainty"),
    ColumnSpec("207Pb/235U", _RAD, "207Pb/235U", "e", "", "L", "R75r"),
    ColumnSpec("207Pb/235U % err", _RAD, "% err", "f", _PCT, "M",
               "200*R75r_std/R75r", "uncertainty"),
    ColumnSpec("206Pb/238U", _RAD, "206Pb/238U", "e", "", "N", "R68r (R68r_Th if Th-corrected ratios)"),
    ColumnSpec("206Pb/238U % err", _RAD, "% err", "f", _PCT, "O",
               "200*R68r_std/R68r (R68r_Th_std/R68r_Th if Th-corrected ratios)", "uncertainty"),
    ColumnSpec("corr. coef. 7/5-6/8", _RAD, "corr. coef.", "", "", "P", "rho_7568_r",
               "correlation"),
    ColumnSpec("207Pb/206Pb date", _DATES, "207Pb/206Pb", "g", "Ma", "R",
               "t76_Th_corr (t76 if not Th-corrected)"),
    ColumnSpec("207Pb/206Pb date ±", _DATES, "±", "f", "Ma, 2σ", "S",
               "2*t76_Th_corr_std (2*t76_std)", "uncertainty"),
    ColumnSpec("207Pb/235U date", _DATES, "207Pb/235U", "g", "Ma", "T", "t75"),
    ColumnSpec("207Pb/235U date ±", _DATES, "±", "f", "Ma, 2σ", "U", "2*t75_std",
               "uncertainty"),
    ColumnSpec("206Pb/238U date", _DATES, "206Pb/238U", "g", "Ma", "V",
               "t68_Th_corr (t68 if not Th-corrected)"),
    ColumnSpec("206Pb/238U date ±", _DATES, "±", "f", "Ma, 2σ", "W",
               "2*t68_Th_corr_std (2*t68_std)", "uncertainty"),
    # Sample (radiogenic + initial Pb) ratios, block 1: 238/206-207/206-204/206.
    ColumnSpec("sample 238U/206Pb", _SAMPLE, "238U/206Pb", "h", "", "Y", "R86s"),
    ColumnSpec("sample 238U/206Pb % err", _SAMPLE, "% err", "f", _PCT, "Z",
               "200*R86s_std/R86s", "uncertainty"),
    ColumnSpec("sample 207Pb/206Pb", _SAMPLE, "207Pb/206Pb", "h", "", "AA", "R76s"),
    ColumnSpec("sample 207Pb/206Pb % err", _SAMPLE, "% err", "f", _PCT, "AB",
               "200*R76s_std/R76s", "uncertainty"),
    ColumnSpec("sample 204Pb/206Pb", _SAMPLE, "204Pb/206Pb", "h", "", "AC", "R46s"),
    ColumnSpec("sample 204Pb/206Pb % err", _SAMPLE, "% err", "f", _PCT, "AD",
               "200*R46s_std/R46s", "uncertainty"),
    ColumnSpec("sample corr. coef. 8/6-7/6", _SAMPLE, "corr. coef. 8/6-7/6", "", "", "AE",
               "rho_8676_s", "correlation"),
    ColumnSpec("sample corr. coef. 8/6-4/6", _SAMPLE, "corr. coef. 8/6-4/6", "", "", "AF",
               "rho_8646_s", "correlation"),
    ColumnSpec("sample corr. coef. 7/6-4/6", _SAMPLE, "corr. coef. 7/6-4/6", "", "", "AG",
               "rho_7646_s", "correlation"),
    # Block 2: 238/204-206/204.
    ColumnSpec("sample 238U/204Pb", _SAMPLE, "238U/204Pb", "h", "", "AI", "R84s"),
    ColumnSpec("sample 238U/204Pb % err", _SAMPLE, "% err", "f", _PCT, "AJ",
               "200*R84s_std/R84s", "uncertainty"),
    ColumnSpec("sample 206Pb/204Pb", _SAMPLE, "206Pb/204Pb", "h", "", "AK", "R64s"),
    ColumnSpec("sample 206Pb/204Pb % err", _SAMPLE, "% err", "f", _PCT, "AL",
               "200*R64s_std/R64s", "uncertainty"),
    ColumnSpec("sample corr. coef. 8/4-6/4", _SAMPLE, "corr. coef. 8/4-6/4", "", "", "AM",
               "rho_8464_s", "correlation"),
    # Block 3: 235/204-207/204.
    ColumnSpec("sample 235U/204Pb", _SAMPLE, "235U/204Pb", "h", "", "AO", "R54s"),
    ColumnSpec("sample 235U/204Pb % err", _SAMPLE, "% err", "f", _PCT, "AP",
               "200*R54s_std/R54s", "uncertainty"),
    ColumnSpec("sample 207Pb/204Pb", _SAMPLE, "207Pb/204Pb", "h", "", "AQ", "R74s"),
    ColumnSpec("sample 207Pb/204Pb % err", _SAMPLE, "% err", "f", _PCT, "AR",
               "200*R74s_std/R74s", "uncertainty"),
    ColumnSpec("sample corr. coef. 5/4-7/4", _SAMPLE, "corr. coef. 5/4-7/4", "", "", "AS",
               "rho_5474_s", "correlation"),
    # Block 4: 206/204-207/204 (the sheet repeats AK, AL, AQ, AR here).
    ColumnSpec("sample 206Pb/204Pb (6/4-7/4)", _SAMPLE, "206Pb/204Pb", "h", "", "AU", "R64s"),
    ColumnSpec("sample 206Pb/204Pb % err (6/4-7/4)", _SAMPLE, "% err", "f", _PCT, "AV",
               "200*R64s_std/R64s", "uncertainty"),
    ColumnSpec("sample 207Pb/204Pb (6/4-7/4)", _SAMPLE, "207Pb/204Pb", "h", "", "AW", "R74s"),
    ColumnSpec("sample 207Pb/204Pb % err (6/4-7/4)", _SAMPLE, "% err", "f", _PCT, "AX",
               "200*R74s_std/R74s", "uncertainty"),
    ColumnSpec("sample corr. coef. 6/4-7/4", _SAMPLE, "corr. coef. 6/4-7/4", "", "", "AY",
               "rho_7464_s", "correlation"),
    # Block 5: 206/204-208/204.
    ColumnSpec("sample 206Pb/204Pb (6/4-8/4)", _SAMPLE, "206Pb/204Pb", "h", "", "BA", "R64s"),
    ColumnSpec("sample 206Pb/204Pb % err (6/4-8/4)", _SAMPLE, "% err", "f", _PCT, "BB",
               "200*R64s_std/R64s", "uncertainty"),
    ColumnSpec("sample 208Pb/204Pb", _SAMPLE, "208Pb/204Pb", "h", "", "BC",
               "(Pb208r+Pb208c)/Pb204c (0 when Pb204c <= 0, as the sheet)"),
    ColumnSpec("sample 208Pb/204Pb % err", _SAMPLE, "% err", "f", _PCT, "BD",
               "not propagated by the engine (nan)", "uncertainty"),
    ColumnSpec("sample corr. coef. 6/4-8/4", _SAMPLE, "corr. coef. 6/4-8/4", "", "", "BE",
               "not propagated by the engine (nan)", "correlation"),
    ColumnSpec("Wt. (mg)", "", "Wt. (mg)", "i", "mg", "BG", "sample_weight"),
    ColumnSpec("U (ppm)", "", "U (ppm)", "j", "ppm", "BH", "U_ppm"),
    ColumnSpec("Pb (ppm)", "", "Pb (ppm)", "j", "ppm", "BI", "Pb_ppm"),
)

_DISCORDANCE = ColumnSpec("% discordance", _DATES, "% discordance", "g", "%", "",
                          "dates.percent_discordance (sheet 'Data Reduction Engine' row 40/50)")


def bsu_columns(include_discordance=False):
    """The `ColumnSpec`s of the numeric BSU columns, in table order."""
    cols = list(BSU_COLUMNS)
    if include_discordance:
        cols.insert(next(i for i, c in enumerate(cols) if c.key == "206Pb/238U date ±") + 1,
                    _DISCORDANCE)
    return cols


def _f(value):
    """float(value), or nan for None and non-numbers."""
    if value is None or isinstance(value, bool):
        return math.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _pct2(value, std):
    """2σ relative error in percent; nan when the value is zero or missing."""
    v, s = _f(value), _f(std)
    if not math.isfinite(v) or v == 0:
        return math.nan
    return 200.0*s/abs(v)


def _th_corrected(grain, flag):
    if flag is None:
        return getattr(grain, "Th230_correction_type", None) is not None
    return bool(flag)


def _row(g, th_dates, th_ratios):
    a = lambda name: _f(getattr(g, name, None))  # noqa: E731
    pb206_total = a("Pb206r") + a("Pb206b") + a("Pb206c")
    pb204_total = a("Pb204b") + a("Pb204c")
    th = a("Th232s")
    r76, r76s = ("R76r_Th", "R76r_Th_std") if th_ratios else ("R76r", "R76r_std")
    r68, r68s = ("R68r_Th", "R68r_Th_std") if th_ratios else ("R68r", "R68r_std")
    t76, t76s = ("t76_Th_corr", "t76_Th_corr_std") if th_dates else ("t76", "t76_std")
    t68, t68s = ("t68_Th_corr", "t68_Th_corr_std") if th_dates else ("t68", "t68_std")
    pb204c = a("Pb204c")
    # The engine can leave a rounding residue (~1e-16 of the blank) in
    # Pb204c when all common Pb is blank; the 204-based sample ratios then
    # blow up. Report them as the sheet does for zero initial Pb: ratio 0,
    # with error and correlations undefined (nan).
    no_initial = not pb204c > _RESIDUE*abs(a("Pb204b"))
    out = {
        "Th/U": th/(a("U238s") + a("U235s")),
        "206Pb* (x10-13 mol)": a("Pb206r")*1e13,
        "mol % 206Pb*": 100.0*a("Pb206r")/pb206_total,
        "Pb*/Pbc": a("Pbr_Pbc"),
        "Pbc (pg)": a("Pbc_pg"),
        "206Pb/204Pb": pb206_total/pb204_total if pb204_total else math.nan,
        "208Pb/206Pb": a("Pb208r")/a("Pb206r"),
        "207Pb/206Pb": a(r76),
        "207Pb/206Pb % err": _pct2(a(r76), a(r76s)),
        "207Pb/235U": a("R75r"),
        "207Pb/235U % err": _pct2(a("R75r"), a("R75r_std")),
        "206Pb/238U": a(r68),
        "206Pb/238U % err": _pct2(a(r68), a(r68s)),
        "corr. coef. 7/5-6/8": a("rho_7568_r"),
        "207Pb/206Pb date": a(t76),
        "207Pb/206Pb date ±": 2*a(t76s),
        "207Pb/235U date": a("t75"),
        "207Pb/235U date ±": 2*a("t75_std"),
        "206Pb/238U date": a(t68),
        "206Pb/238U date ±": 2*a(t68s),
        "% discordance": percent_discordance(g, th_corrected=th_dates),
        "sample 238U/206Pb": a("R86s"),
        "sample 238U/206Pb % err": _pct2(a("R86s"), a("R86s_std")),
        "sample 207Pb/206Pb": a("R76s"),
        "sample 207Pb/206Pb % err": _pct2(a("R76s"), a("R76s_std")),
        "sample 204Pb/206Pb": a("R46s"),
        "sample 204Pb/206Pb % err": _pct2(a("R46s"), a("R46s_std")),
        "sample corr. coef. 8/6-7/6": a("rho_8676_s"),
        "sample corr. coef. 8/6-4/6": a("rho_8646_s"),
        "sample corr. coef. 7/6-4/6": a("rho_7646_s"),
        "sample 238U/204Pb": a("R84s"),
        "sample 238U/204Pb % err": _pct2(a("R84s"), a("R84s_std")),
        "sample 206Pb/204Pb": a("R64s"),
        "sample 206Pb/204Pb % err": _pct2(a("R64s"), a("R64s_std")),
        "sample corr. coef. 8/4-6/4": a("rho_8464_s"),
        "sample 235U/204Pb": a("R54s"),
        "sample 235U/204Pb % err": _pct2(a("R54s"), a("R54s_std")),
        "sample 207Pb/204Pb": a("R74s"),
        "sample 207Pb/204Pb % err": _pct2(a("R74s"), a("R74s_std")),
        "sample corr. coef. 5/4-7/4": a("rho_5474_s"),
        "sample 206Pb/204Pb (6/4-7/4)": a("R64s"),
        "sample 206Pb/204Pb % err (6/4-7/4)": _pct2(a("R64s"), a("R64s_std")),
        "sample 207Pb/204Pb (6/4-7/4)": a("R74s"),
        "sample 207Pb/204Pb % err (6/4-7/4)": _pct2(a("R74s"), a("R74s_std")),
        "sample corr. coef. 6/4-7/4": a("rho_7464_s"),
        "sample 206Pb/204Pb (6/4-8/4)": a("R64s"),
        "sample 206Pb/204Pb % err (6/4-8/4)": _pct2(a("R64s"), a("R64s_std")),
        "sample 208Pb/204Pb": (a("Pb208r") + a("Pb208c"))/pb204c if pb204c > 0 else 0.0,
        "sample 208Pb/204Pb % err": math.nan,
        "sample corr. coef. 6/4-8/4": math.nan,
        "Wt. (mg)": a("sample_weight"),
        "U (ppm)": a("U_ppm"),
        "Pb (ppm)": a("Pb_ppm"),
    }
    if no_initial:
        for key in _ZERO_WITHOUT_INITIAL:
            out[key] = 0.0
        for key in _NAN_WITHOUT_INITIAL:
            out[key] = math.nan
    return out


_RESIDUE = 1e-9
_ZERO_WITHOUT_INITIAL = (
    "sample 204Pb/206Pb", "sample 238U/204Pb", "sample 206Pb/204Pb", "sample 235U/204Pb",
    "sample 207Pb/204Pb", "sample 206Pb/204Pb (6/4-7/4)", "sample 207Pb/204Pb (6/4-7/4)",
    "sample 206Pb/204Pb (6/4-8/4)", "sample 208Pb/204Pb")
_NAN_WITHOUT_INITIAL = tuple(
    k.replace(" (", " % err (") if "(" in k else k + " % err" for k in _ZERO_WITHOUT_INITIAL
) + ("sample corr. coef. 8/6-4/6", "sample corr. coef. 7/6-4/6", "sample corr. coef. 8/4-6/4",
     "sample corr. coef. 5/4-7/4", "sample corr. coef. 6/4-7/4", "sample corr. coef. 6/4-8/4")


def _identifiers(grains, identifiers):
    """Identifier columns present on the grains or in `identifiers`."""
    identifiers = identifiers or {}
    rows = []
    for g in grains:
        extra = identifiers.get(g.id, {}) or {}
        row = {}
        for column, attr in IDENTIFIER_COLUMNS:
            value = extra.get(column, extra.get(attr, getattr(g, attr, None)))
            row[column] = None if isinstance(value, float) and math.isnan(value) else value
        row["Fraction ID"] = g.id if row["Fraction ID"] is None else row["Fraction ID"]
        rows.append(row)
    present = [c for c, _ in IDENTIFIER_COLUMNS
               if c == "Fraction ID" or any(r[c] not in (None, "") for r in rows)]
    return present, [{c: ("" if r[c] is None else r[c]) for c in present} for r in rows]


def bsu_table(grains, identifiers=None, th_corrected_dates=None, th_corrected_ratios=False,
              include_discordance=False):
    """The BSU 'U-Pb Data Table Output' layout as a DataFrame, one row per grain.

    Columns: optional identifiers and chemistry in `IDENTIFIER_COLUMNS` first
    ('Fraction ID' always, the others when any grain has a value as an
    attribute, or `identifiers` supplies them as
    ``{fraction_id: {'Sample': ..., ...}}``), then the numeric columns of
    `bsu_columns()` under their `key`. Use `with_groups` for the grouped
    header.

    Units as in the sheet: 206Pb* in 1e-13 mol, mol % 206Pb* in percent
    (the sheet stores a fraction formatted as %), Pbc in pg, ratio errors
    as 2σ percent, dates and their ± in Ma at 2σ absolute, weight in mg,
    U and Pb in ppm.

    `th_corrected_dates` (sheet 'Raw Data Input'!AT55): True uses the
    230Th-corrected 207/206 and 206/238 dates, False the uncorrected ones,
    None (default) the corrected ones when the grain had a Th correction.
    `th_corrected_ratios` (sheet AU53, 'off' in the template): True uses the
    Th-corrected 207/206 and 206/238 ratios and their errors.
    `include_discordance` adds '% discordance' (the sheet's definition,
    with the dates' Th choice) after the dates.

    When a fraction has no initial common Pb (Pb204c zero, or a rounding
    residue below 1e-9 of the blank 204Pb), its 204Pb-based sample ratios
    are 0, as in the sheet, and their errors and correlations are nan.

    Two sheet columns are not reproduced: the 208Pb/204Pb error (BD) and
    the 6/4-8/4 correlation (BE) of the sample ratios, which the engine does
    not propagate; they are nan.
    """
    grains = list(grains)
    id_cols, id_rows = _identifiers(grains, identifiers)
    keys = [c.key for c in bsu_columns(include_discordance)]
    records = []
    for g, ids in zip(grains, id_rows):
        values = _row(g, _th_corrected(g, th_corrected_dates), bool(th_corrected_ratios))
        rec = dict(ids)
        rec.update({k: values[k] for k in keys})
        records.append(rec)
    return pd.DataFrame(records, columns=id_cols + keys)


def with_groups(table, include_discordance=None):
    """Copy of a `bsu_table` frame with MultiIndex columns (group, label, note)."""
    if include_discordance is None:
        include_discordance = "% discordance" in table.columns
    specs = {c.key: c for c in bsu_columns(include_discordance)}
    tuples = []
    for key in table.columns:
        spec = specs.get(key)
        if spec is None:
            tuples.append((IDENTIFIER_GROUP, key, "a" if key == "Fraction ID" else ""))
        else:
            tuples.append((spec.group, spec.label, spec.note))
    out = table.copy()
    out.columns = pd.MultiIndex.from_tuples(tuples, names=["group", "label", "note"])
    return out


# ---------------------------------------------------------------- footnotes

def _get(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _fmt(x, digits=4):
    return "n/a" if x is None else f"{x:.{digits}g}"


def footnotes(settings=None, grains=None, th_corrected_dates=None, th_corrected_ratios=False,
              *, oxide=None, mean_statistics=None, oxide_values=None, mean_statistic_blocks=None):
    """Footnotes (a) to (j) for a BSU table, as a list of (letter, text).

    `settings` is a `ReductionSettings` (or None). `grains`, when given,
    supply the tracer, the 230Th correction and the decay constants actually
    used (grains can carry constants other than the package defaults);
    otherwise those come from `settings` and `IDTIMS_UPbRPy.constants`.
    The other arguments match `bsu_table`.

    Optional provenance adds (k). `oxide` groups fraction IDs by formula (or
    "none confirmed" / "missing"); `mean_statistics` groups IDs by arithmetic
    or geometric statistics. `oxide_values` maps IDs to the actual 18O/16O
    values. `mean_statistic_blocks` maps IDs to {"Pb": statistic, "U": statistic}
    when the blocks differ. These describe the imported ratios, without
    recomputing any correction or statistics.
    """
    grains = list(grains or [])
    g0 = grains[0] if grains else None
    lam = {name: _f(_get(g0, name, getattr(constants, name)))
           for name in ("lambda_238", "lambda_235", "lambda_230")}
    u_ratio = _f(_get(g0, "common_U238_U235", constants.common_U238_U235))

    tracers = sorted({f"{_get(g, 'spike_name', '?')} ({int(_get(g, 'spike_type', 0) or 0)})"
                      for g in grains}) if grains else []
    version = _get(settings, "spike_version")
    tracer_text = ", ".join(tracers) if tracers else "the tracer named for each fraction"
    if version:
        tracer_text += f", table version {version}"
    types = {int(_get(g, "spike_type", 0) or 0) for g in grains}

    fr = _get(settings, "fractionation")
    parts = []
    if not grains or types - {2535}:
        if fr is not None:
            parts.append("for 205Pb-235U tracers a fixed linear Pb fractionation of "
                         f"{_fmt(_get(fr, 'FPb_Daly'))} ± {_fmt(_get(fr, 'FPb_Daly_std'))} %/amu "
                         f"(Daly) and {_fmt(_get(fr, 'FPb_Faraday'))} ± "
                         f"{_fmt(_get(fr, 'FPb_Faraday_std'))} %/amu (Faraday), 1σ")
        else:
            parts.append("for 205Pb-235U tracers a fixed linear Pb fractionation per collector")
    if 2535 in types or not grains:
        parts.append("for 202Pb-205Pb tracers a linear Pb fractionation computed for each "
                     "fraction from its measured 202Pb/205Pb against the tracer value")
    fractionation_text = "; ".join(parts)

    blanks = _get(settings, "lab_blanks")
    if blanks is not None:
        blank_text = (f"Lab Pb blank {_fmt(_get(blanks, 'Pb_blank_total'))} pg ± "
                      f"{_fmt(_get(blanks, 'Pb_blank_total_std_rel'))} % (1σ) with "
                      f"206Pb/204Pb = {_fmt(_get(blanks, 'R64b'), 5)}, "
                      f"207Pb/204Pb = {_fmt(_get(blanks, 'R74b'), 5)}, "
                      f"208Pb/204Pb = {_fmt(_get(blanks, 'R84b'), 5)}; lab U blank "
                      f"{_fmt(_get(blanks, 'U_blank_total'))} pg ± "
                      f"{_fmt(_get(blanks, 'U_blank_total_std_rel'))} %.")
    else:
        blank_text = "Lab Pb and U blanks as set for the reduction."
    common = _get(settings, "common_pb")
    if common is not None and _get(common, "model") == "stacey_kramers":
        initial_text = (f"Stacey and Kramers (1975) Pb at {_fmt(_get(common, 'age_Ga'))} Ga")
    elif common is not None:
        initial_text = (f"initial Pb with 206Pb/204Pb = {_fmt(_get(common, 'R64c'), 5)}, "
                        f"207Pb/204Pb = {_fmt(_get(common, 'R74c'), 5)}, "
                        f"208Pb/204Pb = {_fmt(_get(common, 'R84c'), 5)}")
    else:
        initial_text = "the initial Pb composition set for the reduction"

    th_set = _get(settings, "th_correction")
    kind = _get(th_set, "kind") if th_set is not None else _get(g0, "Th230_correction_type")
    if kind == "D":
        d = _get(th_set, "D_Th_U", _get(g0, "D_Th_U"))
        ds = _get(th_set, "D_Th_U_std", _get(g0, "D_Th_U_std"))
        th_text = (f"230Th disequilibrium correction with D(Th/U) mineral/melt = {_fmt(d)} ± "
                   f"{_fmt(ds)} (1σ)")
    elif kind == "magma":
        m = _get(th_set, "Th_U_magma", _get(g0, "Th_U_magma"))
        ms = _get(th_set, "Th_U_magma_std", _get(g0, "Th_U_magma_std"))
        th_text = (f"230Th disequilibrium correction with Th/U of the magma = {_fmt(m)} ± "
                   f"{_fmt(ms)} (1σ) and the fraction's Th/U from its radiogenic 208Pb")
    else:
        th_text = "no disequilibrium correction"
    th_text += f"; λ230 = {lam['lambda_230']:.4e} /yr is the value in use"
    if kind is None:
        date_choice = "Dates are not corrected for 230Th disequilibrium."
    else:
        uses = (th_corrected_dates is None) or bool(th_corrected_dates)
        date_choice = ("The 206Pb/238U and 207Pb/206Pb dates are corrected for 230Th "
                       "disequilibrium." if uses else
                       "The 206Pb/238U and 207Pb/206Pb dates are shown without the 230Th "
                       "correction.")
        date_choice += (" The 206Pb/238U and 207Pb/206Pb ratios are corrected as well."
                        if th_corrected_ratios else " The ratios are shown without it.")

    notes = [
        ("a", "Fraction labels as entered; sample, beaker and source grain or spot are shown "
              "where recorded."),
        ("b", "Th/U of the fraction modelled from its radiogenic 208Pb/206Pb and its "
              "206Pb/238U date."),
        ("c", "Pb* is radiogenic Pb and Pbc is common Pb (lab blank plus initial Pb); "
              "mol % 206Pb* is relative to radiogenic, blank and initial 206Pb."),
        ("d", "Measured ratio after tracer subtraction and mass fractionation correction "
              f"only. Tracer: {tracer_text}. Fractionation: {fractionation_text}; U "
              "fractionation from the measured 233U/235U of the double spike."),
        ("e", "Corrected for mass fractionation, tracer, lab blank and initial Pb. Common Pb "
              "up to the lab blank is assigned to blank and any excess to "
              f"{initial_text}. {blank_text} 230Th: {th_text}."),
        ("f", "Uncertainties are 2σ, from joint first-order propagation of the measured, "
              "fractionation, blank, initial Pb and Th inputs (McLean et al. 2011 framework); "
              "tracer calibration and decay-constant uncertainties are not included. They "
              "can differ from reductions that propagate these terms separately."),
        ("g", f"Dates use λ238 = {lam['lambda_238']:.5e} /yr and λ235 = "
              f"{lam['lambda_235']:.5e} /yr (Jaffey et al. 1971) and 238U/235U = "
              f"{u_ratio:g}. {date_choice}"),
        ("h", "Total sample ratios (radiogenic plus initial Pb), corrected for mass "
              "fractionation, tracer and lab blank only."),
        ("i", "Fraction weight as entered."),
        ("j", "U and total Pb concentrations scale with the entered fraction weight."),
    ]
    if oxide is not None or mean_statistics is not None:
        notes.append(("k", _provenance_note(oxide, mean_statistics, oxide_values,
                                          mean_statistic_blocks)))
    return notes


_OXIDE_EQUATIONS = {
    "isobar_233_18O": (
        "r238/235 = r270/267 / (1 − 2·r18·r265/267); "
        "r233/235 = r265/267 / (1 − 2·r18·r265/267); r238/233 = r238/235 / r233/235"),
    "tripoli_java_00dc941": (
        "r238/235 = r270/267 / (1 − 2·r18·r270/267); "
        "r233/235 = r265/267 / (1 − 2·r18·r265/267); r238/233 = r238/235 / r233/235"),
    "instrument": "ratios arrived already oxide-corrected in the raw file; formula not recorded",
}


def _provenance_note(oxide, mean_statistics, oxide_values, mean_statistic_blocks):
    """One sentence for shared provenance, grouped clauses otherwise."""
    oxide = {key: list(ids) for key, ids in (oxide or {}).items() if ids}
    statistics = {key: list(ids) for key, ids in (mean_statistics or {}).items() if ids}

    def correction(formula, ids):
        if formula == "none confirmed":
            return "no U oxide correction (confirmed)"
        description = _OXIDE_EQUATIONS.get(formula, "formula not recorded")
        label = "U oxide correction not recorded" if formula == "missing" else f"U oxide correction {formula}"
        values = {}
        for fid in ids:
            value = (oxide_values or {}).get(fid)
            text = str(value) if value is not None else "not recorded"
            values.setdefault(text, []).append(fid)
        r18 = ", ".join(value + (f" ({', '.join(group)})" if len(values) > 1 else "")
                        for value, group in values.items())
        return f"{label} ({description}; 18O/16O = {r18})"

    # The IDs must also agree: a single statistic group can describe only a
    # subset when callers supply partial provenance.
    if (len(oxide) == len(statistics) == 1
            and set(next(iter(oxide.values()))) == set(next(iter(statistics.values())))
            and not any(len(set(blocks.values())) > 1
                        for blocks in (mean_statistic_blocks or {}).values())):
        formula, ids = next(iter(oxide.items()))
        statistic = next(iter(statistics))
        return (f"Fractions {', '.join(ids)}: {correction(formula, ids)}, with {statistic} "
                "Pb and U ratio means and % standard errors.")

    parts = [f"Fractions {', '.join(ids)}: {correction(formula, ids)}"
             for formula, ids in oxide.items()]
    if mean_statistic_blocks:
        exported = {fid for ids in statistics.values() for fid in ids}
        for block in ("Pb", "U"):
            for statistic in ("arithmetic", "geometric"):
                ids = [fid for fid, blocks in mean_statistic_blocks.items()
                       if fid in exported and blocks.get(block) == statistic]
                if ids:
                    parts.append(f"Fractions {', '.join(ids)}: {statistic} {block} ratio means "
                                 "and % standard errors")
    else:
        parts.extend(f"Fractions {', '.join(ids)}: {statistic} ratio means and % standard errors"
                     for statistic, ids in statistics.items())
    return "; ".join(parts) + "." if parts else "Ratio provenance was not supplied."


# ---------------------------------------------------------------- full table

def full_table(grains):
    """Every numeric scalar attribute of every grain, one row per grain.

    The first column is 'id'; the others are sorted by name. Booleans,
    strings, arrays and containers are left out; an attribute that is
    numeric on some grains and None on others is nan where missing.
    Values keep full float64 precision.
    """
    grains = list(grains)
    rows, names = [], set()
    for g in grains:
        row = {}
        for name, value in vars(g).items():
            if isinstance(value, (bool, np.bool_)) or name == "id":
                continue
            if isinstance(value, numbers.Real):
                row[name] = float(value)
            elif isinstance(value, np.ndarray) and value.ndim == 0 and value.dtype.kind in "fiu":
                row[name] = float(value)
        names.update(row)
        rows.append(row)
    columns = sorted(names)
    frame = pd.DataFrame([{n: r.get(n, math.nan) for n in columns} for r in rows],
                         columns=columns, dtype=float)
    frame.insert(0, "id", [g.id for g in grains])
    return frame


def write_csv(frame, path):
    """Write a frame to CSV with 17 significant digits (exact float64 round trip).

    Values read back exactly with pandas >= 3 ``pd.read_csv(path)`` (older
    pandas: pass ``float_precision='round_trip'``). Whole numbers are written
    without a decimal point, so pandas reads such columns as integers.
    MultiIndex columns are flattened by pandas into several header rows.
    """
    frame.to_csv(path, index=False, float_format="%.17g")


def write_xlsx(table, notes, path):
    """Write a `bsu_table` frame with its grouped header and footnotes to XLSX.

    Needs openpyxl (not a dependency of the engine). Rows 1-3 hold group,
    label and footnote letter; data follow; footnotes go below the data.
    """
    try:
        from openpyxl import Workbook
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise ImportError("write_xlsx needs openpyxl, which is not installed.") from error
    grouped = with_groups(table)
    wb = Workbook()
    ws = wb.active
    ws.title = "U-Pb data"
    for level in range(3):
        values = [t[level] for t in grouped.columns]
        if level == 0:
            values = [v if i == 0 or v != values[i - 1] else "" for i, v in enumerate(values)]
        if level == 2:
            values = [f"({v})" if v else "" for v in values]
        ws.append(values)
    for row in table.itertuples(index=False):
        ws.append([None if isinstance(v, float) and not math.isfinite(v) else v for v in row])
    ws.append([])
    for letter, text in notes:
        ws.append([f"({letter}) {text}"])
    wb.save(path)
