"""Shared helpers for the reduction snapshot (tests and tools/make_snapshot.py)."""
import numbers
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from IDTIMS_UPbRPy import UPbR

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tests" / "data" / "synthetic_snapshot.json"
EXAMPLE = ROOT / "examples" / "synthetic_zircon_CA-ID-TIMS.csv"

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


def grain_numbers(grain):
    """Every finite-or-not numeric attribute of a reduced grain, as plain JSON."""
    out = {}
    for name, value in sorted(vars(grain).items()):
        if isinstance(value, bool):
            continue
        if isinstance(value, numbers.Real):
            out[name] = float(value)
        elif isinstance(value, np.ndarray) and value.dtype.kind in "fi":
            out[name] = np.asarray(value, dtype=float).tolist()
    return out


def reduce_variants():
    data = pd.read_csv(EXAMPLE)
    result = {}
    for key, th in VARIANTS.items():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            grains = UPbR.load_grains(data, F, B, C, th, strict_covariance=False)
        result[key] = {str(g.id): grain_numbers(g) for g in grains}
    return result
