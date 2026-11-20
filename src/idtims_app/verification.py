"""`--verify-reduction`: reduce the bundled synthetic example and compare with a snapshot.

The settings are copies of the dictionaries in tests/snapshot_support.py (the
app must not import tests). The frozen app runs this to prove that the bundle
reduces exactly as the source tree does: every numeric attribute of every
grain, under three Th-correction variants, at a relative tolerance of 1e-12.
Qt-free.
"""
from __future__ import annotations

import json
import math
import numbers
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from IDTIMS_UPbRPy import UPbR

EXAMPLE_NAME = "synthetic_zircon_CA-ID-TIMS.csv"
RTOL = 1e-12
ATOL = 1e-300

# Copied from tests/snapshot_support.py; keep the two in step.
F = dict(FPb_Faraday=0.1, FPb_Faraday_std=0.02, FPb_Daly=0.18, FPb_Daly_std=0.03)
B = dict(Pb_blank_total=10, Pb_blank_total_std_rel=25,
         U_blank_total=0.013, U_blank_total_std_rel=25,
         R64b=18.0421945908634, R64b_std_rel=0.607139377926844,
         R74b=15.5371020776877, R74b_std_rel=0.517837380732101,
         R84b=37.6863067377047, R84b_std_rel=0.629661232098709,
         rho_6474_b=0.98, rho_6484_b=0.98)
C = dict(R64c=17.1761972269812, R64c_std_rel=0.0069,
         R74c=15.4453687937006, R74c_std_rel=0.0103,
         R84c=36.6115109186091, R84c_std_rel=0.0094,
         rho_6474_c=0.999, rho_6484_c=0.999)
VARIANTS = {
    "th_D": dict(Th230_correction_type="D", D_Th_U=0.2, D_Th_U_std=0.05,
                 Th_U_magma=3, Th_U_magma_std=0.05),
    "th_magma": dict(Th230_correction_type="magma", Th_U_magma=3, Th_U_magma_std=0.5),
    "th_none": None,
}


def example_path():
    """The bundled synthetic example: inside the frozen app, else the repository's examples/."""
    here = Path(__file__).resolve().parent
    for candidate in (here / "examples" / EXAMPLE_NAME,
                      here.parents[1] / "examples" / EXAMPLE_NAME):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"The bundled example {EXAMPLE_NAME} was not found.")


def grain_numbers(grain):
    """Every numeric attribute of a reduced grain, as plain JSON (as the snapshot stores)."""
    out = {}
    for name, value in sorted(vars(grain).items()):
        if isinstance(value, bool):
            continue
        if isinstance(value, numbers.Real):
            out[name] = float(value)
        elif isinstance(value, np.ndarray) and value.dtype.kind in "fi":
            out[name] = np.asarray(value, dtype=float).tolist()
    return out


def reduce_variants(path=None):
    """Reduce the example under each Th variant: {variant: {grain: numbers}}."""
    data = pd.read_csv(path or example_path())
    result = {}
    for key, th in VARIANTS.items():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            grains = UPbR.load_grains(data, F, B, C, th, strict_covariance=False)
        result[key] = {str(g.id): grain_numbers(g) for g in grains}
    return result


def _close(a, b):
    if isinstance(a, list):
        return isinstance(b, list) and len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    if isinstance(b, list):
        return False
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return math.isclose(a, b, rel_tol=RTOL, abs_tol=ATOL)


def _count(value):
    return sum(_count(v) for v in value) if isinstance(value, list) else 1


def compare(expected, actual):
    """(numbers compared, list of mismatch messages)."""
    problems, compared = [], 0
    if sorted(expected) != sorted(actual):
        problems.append(f"variants differ: {sorted(expected)} vs {sorted(actual)}")
    for variant, grains in expected.items():
        got_grains = actual.get(variant, {})
        if sorted(grains) != sorted(got_grains):
            problems.append(f"{variant}: grains differ")
        for grain, values in grains.items():
            got = got_grains.get(grain, {})
            for name, value in values.items():
                compared += _count(value)
                if name not in got:
                    problems.append(f"{variant}/{grain}/{name}: missing")
                elif not _close(value, got[name]):
                    problems.append(f"{variant}/{grain}/{name}: snapshot {value!r}, "
                                    f"now {got[name]!r}")
    return compared, problems


def verify(snapshot_path):
    """Run the check; returns (report dict, ok)."""
    expected = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    compared, problems = compare(expected, reduce_variants())
    report = {"frozen": bool(getattr(sys, "frozen", False)), "example": str(example_path()),
              "snapshot": str(snapshot_path), "numbers_compared": compared,
              "mismatches": len(problems), "first_mismatches": problems[:10]}
    return report, not problems and compared > 0
