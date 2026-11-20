"""Verify local MCR ratio-to-date references; private data are not distributed.

Run: python tools/verify_mcr.py MCR_data/MCR_all_ages.csv
The CSV was exported with %.6g; comparisons account for rounding in BOTH
input ratios and output dates. Uncertainties are audited separately.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from IDTIMS_UPbRPy import utils


def half_unit(value):
    return 0.5*10**(np.floor(np.log10(abs(value)))-5) if value else 0.0


def verify(path):
    data = pd.read_csv(path)
    records = []
    configs = [
        ("t68_jaff", "206Pb/238U", 1.55125e-10, 9.8485e-10, 137.818),
        ("t68_sch", "206Pb/238U", 1.54993e-10, 9.8569e-10, 137.818),
        ("t75_jaff", "207Pb/235U", 1.55125e-10, 9.8485e-10, 137.818),
        ("t75_sch", "207Pb/235U", 1.54993e-10, 9.8569e-10, 137.818),
        ("t76_jaff_newU", "207Pb/206Pb", 1.55125e-10, 9.8485e-10, 137.818),
        ("t76_jaff_oldU", "207Pb/206Pb", 1.55125e-10, 9.8485e-10, 137.88),
        ("t76_sch_newU", "207Pb/206Pb", 1.54993e-10, 9.8569e-10, 137.818),
    ]
    for prefix, ratio_col, l238, l235, uratio in configs:
        if prefix.startswith("t68"):
            age = lambda r: utils.calc_t68(r, l238)
            sigma = lambda r, s: utils.calc_t68_uncertainty(r, s, l238)
        elif prefix.startswith("t75"):
            age = lambda r: utils.calc_t75(r, l235)
            sigma = lambda r, s: utils.calc_t75_uncertainty(r, s, l235)
        else:
            age = lambda r: utils.calc_t76(r, lambda_235=l235, lambda_238=l238, common_U238_U235=uratio)
            sigma = lambda r, s: utils.calc_t76_uncertainty(age(r), s, l235, l238, uratio)
        subset = data.dropna(subset=[ratio_col, prefix+"_Ma"])
        passed, upassed, umax, dmax = 0, 0, 0.0, 0.0
        for _, row in subset.iterrows():
            r, reference = row[ratio_col], row[prefix+"_Ma"]
            delta = abs(age(r)-reference)
            tolerance = max(abs(age(r+half_unit(r))-age(r)), abs(age(r-half_unit(r))-age(r))) + half_unit(reference) + 1e-8
            passed += delta <= tolerance
            dmax = max(dmax, delta)
            s, expected = row[ratio_col+" 2s abs"], row[prefix+"_2s"]
            actual = sigma(r, s)
            stol = max(abs(sigma(rr, ss)-actual) for rr in [r-half_unit(r), r+half_unit(r)] for ss in [s-half_unit(s), s+half_unit(s)]) + half_unit(expected) + 1e-8
            upassed += abs(actual-expected) <= stol
            umax = max(umax, abs(actual-expected))
        records.append(dict(column=prefix, count=len(subset), dates_pass=int(passed),
                            uncertainties_pass=int(upassed), max_age_difference_Ma=dmax,
                            max_uncertainty_difference_Ma=umax))
    return dict(source=str(path), rows=len(data), comparison="6 significant digit rounding intervals; not bitwise equality", results=records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify(args.csv)
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered+"\n")
    if any(r["dates_pass"] != r["count"] for r in report["results"]):
        raise SystemExit(1)
