"""Complete published tracer quotients at the reduction boundary, not in the registry."""
from functools import lru_cache
import math

import numpy as np
import pandas as pd

from ._spike_registry_check import fields, read_toml, require
from .spike_registry import BUNDLED_OVERLAY


CROSS_RATIOS = {
    "207Pb/206Pb": ("207Pb/205Pb", "206Pb/205Pb"),
    "204Pb/206Pb": ("204Pb/205Pb", "206Pb/205Pb"),
    "238U/233U": ("238U/235U", "233U/235U"),
}

COVARIANCE_NOTE = (
    "Tracer errors enter as 1σ per ratio with the pairwise covariances the engine infers; "
    "the full correlated tracer covariance of McLean et al. (2011) is not propagated."
)


def validate_cross_ratio_supplements(supplements):
    """Validate private cross-ratio data, returning the per-exact-key mapping.

    Only 1σ relative percent uncertainties are supported at this boundary.
    """
    require(isinstance(supplements, dict), "Cross-ratio supplement: expected a table")
    for key, entry in supplements.items():
        context = f"Cross-ratio supplement {key}"
        require(isinstance(key, str) and len(key.split('/')) == 3
                and all(key.split('/')), f"{context}: expected spike/subfraction/version key")
        fields(entry, ['source', 'table', 'locator', 'notes', 'ratios'], [], context)
        for field in ('source', 'table', 'locator', 'notes'):
            require(isinstance(entry[field], str) and bool(entry[field].strip()),
                    f"{context}: expected nonempty {field}")
        require(isinstance(entry['ratios'], dict) and bool(entry['ratios']),
                f"{context}: expected nonempty ratios table")
        for ratio, measurement in entry['ratios'].items():
            where = f"{context}, {ratio}"
            require(ratio in CROSS_RATIOS, f"{where}: unknown cross-ratio label")
            fields(measurement, ['value', 'uncertainty', 'uncertainty_type'], [], where)
            require(measurement['uncertainty_type'] == '1sd_rel_pct',
                    f"{where}: unsupported uncertainty_type {measurement['uncertainty_type']!r}; "
                    "expected 1sd_rel_pct")
            for field in ('value', 'uncertainty'):
                number = measurement[field]
                require(type(number) in (int, float) and math.isfinite(number) and number > 0,
                        f"{where}: {field} must be finite and positive")
    return supplements


@lru_cache(maxsize=1)
def load_cross_ratio_supplements():
    """Read static bundled supplements independently of registry manifests/locks."""
    return validate_cross_ratio_supplements(read_toml(BUNDLED_OVERLAY / 'cross_ratios.toml'))


class TracerCompositionError(ValueError):
    """A tracer lacks a value or published uncertainty needed by the reduction."""


def complete_tracer(frame, label, key=None, *, with_sources=False):
    """Return a completed numeric value/1σ-% frame and derivation notes.

    Absent cross-ratio values use private supplements only for an exact key;
    otherwise they are derived with zero covariance between published inputs.
    Present values (including ones with unknown errors) are never replaced.
    With with_sources, also return quantity -> (kind, note) for UI annotations;
    the ordinary notes remain a list of strings for uncertainty_assumptions.
    Concentrations are fixed in the reduction; their uncertainties are unused.
    Tracer 202Pb/205Pb is validated for 2535 fractions by UPbR.assign_Pb_R25m.
    """
    frame = frame.copy()
    notes, unavailable = [], {}
    sources = {}
    supplement = load_cross_ratio_supplements().get(key) if key is not None else None

    def cell(row, quantity):
        return frame.at[row, quantity] if quantity in frame.columns else np.nan

    for ratio, (a, b) in CROSS_RATIOS.items():
        if not pd.isna(cell("value", ratio)):
            continue
        if supplement and ratio in supplement['ratios']:
            measurement = supplement['ratios'][ratio]
            value, error = measurement['value'], measurement['uncertainty']
            frame.loc['value', ratio] = value
            frame.loc['uncertainty', ratio] = error
            note = (f"Tracer {label}: {ratio} = {value:.6g} ± {error:.3g} % (1σ) "
                    f"from the BSU sheet table '{supplement['table']}'; "
                    "Condon et al. (2015) Table 3 does not print it. " + COVARIANCE_NOTE)
            notes.append(note)
            sources[ratio] = ('BSU sheet', note)
            continue
        missing = [f"no value for {q}" for q in (a, b)
                   if not np.isfinite(cell("value", q))]
        if cell("value", b) == 0:
            missing.append(f"zero denominator {b}")
        if missing:
            unavailable[ratio] = ", ".join(missing)
            continue
        frame.loc["value", ratio] = cell("value", a) / cell("value", b)
        frame.loc["uncertainty", ratio] = np.hypot(cell("uncertainty", a), cell("uncertainty", b))
        missing = [f"no uncertainty for {q}" for q in (a, b)
                   if not np.isfinite(cell("uncertainty", q))]
        if missing:
            unavailable[ratio] = ", ".join(missing)
        note = (f"Tracer {label}: {ratio} derived as ({a})/({b}); "
                "1σ assumes zero covariance between the published ratios. " + COVARIANCE_NOTE)
        notes.append(note)
        sources[ratio] = ('derived', note)

    required = ["206Pb/205Pb", "207Pb/205Pb", "204Pb/205Pb", "208Pb/205Pb",
                "207Pb/206Pb", "204Pb/206Pb", "238U/235U", "233U/235U"]
    problems = []
    for quantity in ["Pb205", "U235", *required]:
        for row in (["value"] if quantity in ("Pb205", "U235") else ["value", "uncertainty"]):
            if not np.isfinite(cell(row, quantity)):
                detail = f"has no {row} for {quantity}"
                if quantity in unavailable:
                    detail += f" (cannot derive: {unavailable[quantity]})"
                problems.append(detail)
    if problems:
        raise TracerCompositionError(
            f"Tracer {label} " + "; ".join(problems) +
            "; the reduction does not assume one. Choose another tracer version or add "
            "the published value/uncertainty to the registry.")
    return (frame, notes, sources) if with_sources else (frame, notes)
