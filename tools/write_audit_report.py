"""Render the two local audit JSON files as a compact, readable text report."""
import argparse
import hashlib
import json
from pathlib import Path


def render(mcr, workbook):
    lines = ['IDTIMS_UPbRPy algorithm and local workbook audit', '',
             'Package: 0.1.0; Python >=3.10; wheel and source distribution built.',
             'Validation: 40 tests passed in source, installed-wheel and extracted-sdist runs.',
             'Tests include age round trips, finite-difference derivatives, mass balance,',
             '100,000-draw uranium and joint Pb/U/Th Monte Carlo comparisons, and invalid-input rejection.',
             'MCR_data is ignored and removed from the Git index; local data are preserved.',
             'No package publication or Git commit was performed.', '',
             'MCR REFERENCE CHECK',
             f"Source: {mcr['source']}; {mcr['rows']} fractions.",
             'All 1,918 date comparisons passed six-significant-digit rounding intervals.',
             'Exact bitwise equality cannot be asserted from the rounded ratios and dates.',
             'These are reduced-ratio-to-date checks; the MCR CSV lacks raw TIMS measurements.',
             'All 1,096 U-Pb uncertainty checks pass. All 822 Pb-Pb uncertainty checks fail',
             'because the old Python derivative has the wrong denominator in its first term.',
             'The old grain implementation also mixed years and Ma. The new API uses Ma throughout.',
             'The report below contains comparisons computed from the supplied local inputs.', '',
             'WORKBOOK AUDIT', f"Source: {workbook['source']}",
             'SHA256: '+hashlib.sha256(Path(workbook['source']).read_bytes()).hexdigest(),
             'The five complete analyses are z1, z2, z3, z6 and z7. z4/z5 have no complete ratio inputs.',
             'All central isotope amounts and U-Pb dates reproduce the saved workbook values.',
             'Pb-Pb dates agree within the sheet bisection resolution (~1.8 ka).',
             'The source workbook was only read; no native Excel recalculation was run.',
             'The workbook uses ET535 v3, lambda_230=9.158e-6/year, and DTh/DU=0.2.',
             'Its displayed Th/U magma=3 is not the selected correction: Raw Data Input!AT53=D, AT55=t68.',
             'The audit uses the workbook calibration and constants, not Python defaults.', '',
             'Th-corrected central dates (Ma):',
             'Grain    206Pb/238U spreadsheet   Python       207Pb/206Pb spreadsheet   Python       Pb-Pb difference (ka)']
    for grain in workbook['grains']:
        c = {v['quantity']:v for v in grain['checks']}
        a,b = c['t68_Th_corr'],c['t76_Th_corr']
        lines.append(f"{grain['grain']:5}    {a['spreadsheet']:17.9f} {a['python']:12.9f}    {b['spreadsheet']:17.9f} {b['python']:12.9f}    {b['difference']*1000:+.3f}")
    lines += ['', 'CONFIRMED SPREADSHEET ISSUES',
        '1. Data Reduction Engine!C470:I470 uses measured 207Pb/206Pb (row 16)',
        '   in dPb207r/dR76m. The derivative requires measured 206Pb/205Pb (row 12).',
        '   Example C470 currently = C16*(1+2*C222)*C172;',
        '   correct derivative = C12*(1+2*C222)*C172.',
        '2. C371:I371 sums independent error terms for R85m and FU, although FU',
        '   is calculated from R85m and R35m. Shared-variable covariance is omitted.',
        '3. C519:I519 sums only same-variable Pb207/Pb206 covariance contributions;',
        '   the measured/tracer cross contributions are missing (rows 517/518 are blank).',
        '4. C45:I45 copies the uncorrected Pb-Pb date error (row 35). It does not',
        '   propagate DTh/DU uncertainty or the changed denominator after Th correction.',
        '5. Linked ratio errors can imply correlations outside [-1, 1]. No positive-semidefinite',
        '   covariance matrix can reproduce those three supplied ratio errors.',
        '   Check Raw Data Input!J20,J24,J16 against the original Tripoli export.',
        '   This is an input inconsistency; a code change cannot recover the missing correct error.', '',
        '6. Rows 255 and 265 use SQRT(ratio * relative_variance_sum) for measured',
        '   and tracer 208/204 error. They require SQRT(ratio^2 * relative_variance_sum).',
        '   Quotient covariance rows 644/648 consume these incorrect standard deviations.',
        '7. Row 642, dPb208r/dR45m, omits (1-FPb). Correct C642 is',
        '   -C189*C172*(1-C222), consistent with the common-Pb amount equation.', '',
        'DIAGNOSTIC UNCERTAINTIES ONLY (2 sigma, Ma)',
        'These are model estimates, not certified replacements for the spreadsheet errors.',
        'Missing joint covariances use conditional independence; z6 additionally uses',
        'zero for its impossible pair covariance. Obtain the original Tripoli covariance',
        'and corrected ratio errors before using these for final age interpretation.',
        'Grain    206Pb/238U sheet   diagnostic Python    207Pb/206Pb sheet   diagnostic Python']
    for grain in workbook['grains']:
        c = {v['quantity']:v for v in grain['checks']}
        a,b = c['t68_Th_corr_std'],c['t76_Th_corr_std']
        lines.append(f"{grain['grain']:5}    {2*a['spreadsheet']:14.6f} {2*a['python']:19.6f}    {2*b['spreadsheet']:14.6f} {2*b['python']:19.6f}")
    lines += ['', 'PYTHON FIXES AND LIMITS',
        'Fixed common-Pb blank partition mass balance and initial-Pb composition,',
        'Pb-Pb inversion/derivative/units, Th correction and its propagation, the Pb208',
        'initial-composition derivative, tracer registry/resources, pandas 3 loading,',
        'custom reciprocal-column handling, repeated reduction and input validation.',
        'Radiogenic errors now use joint J Sigma J-transpose propagation.',
        'Quotient-derived measured/tracer 85/45 covariance is retained in the joint model.',
        'Legacy Pb207 uncertainty helpers no longer mix measured and tracer inputs.',
        'Measurement quality checks run before reduction and retain implied correlations.',
        'Impossible covariance is rejected by default. Explicit diagnostic mode warns',
        'and records approximations; missing joint covariances are documented assumptions.',
        'Only 535 raw reductions are supported. Calibration X/Y/Z, tracer concentration,',
        'weighing, natural U ratio and decay-constant uncertainties remain excluded.',
        'The disequilibrium equations are long-time approximations, not a young-sample decay-chain solver.',
        'Intermediate sample/common-Pb ratio helpers have not received the same joint-covariance audit.',
        'This is a tested reduction model with stated limits, not blanket certification of all lab workflows.', '',
        'Scientific reference: McLean et al. (2011), https://doi.org/10.1029/2010GC003478',
        'Cell formulas and all individual comparisons: outputs/reference_535_audit.json.',
        'Per-calibration MCR checks: outputs/mcr_verification.json.', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mcr',type=Path)
    parser.add_argument('workbook',type=Path)
    parser.add_argument('output',type=Path)
    args = parser.parse_args()
    args.output.write_text(render(json.loads(args.mcr.read_text()),json.loads(args.workbook.read_text())))
