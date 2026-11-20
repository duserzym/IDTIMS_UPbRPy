"""Read-only audit of a 2535 (ET2535 double spike) UPbR26XML workbook.

Companion to tools/audit_xls.py (which audits the 535 SA18-1 workbook and is
unchanged). Reads the fraction inputs from 'Raw Data Input' and the workbook's
own settings (blank and initial-Pb compositions and amounts, D(Th/U),
Th/U magma, decay constants including its lambda230, natural 238U/235U and
the tracer values it used) from cached 'Data Reduction Engine' cells, passes
them to the Python reduction for this comparison only, and compares results
with the cached values. Package defaults are not changed. The workbook is
opened read-only and never modified.

Requires xlrd. Run:
    PYTHONPATH=src python tools/audit_xls_2535.py /path/to/BSULab_UPbR26XML.xls --output out.json [--strict]
"""
import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xlrd

from IDTIMS_UPbRPy import UPbR

# Workbook rows (1-based) of the inputs on 'Raw Data Input'.
RAW_RATIOS = [('206Pb/204Pb', 11), ('206Pb/207Pb', 15), ('206Pb/205Pb', 19),
              ('207Pb/205Pb', 23), ('204Pb/205Pb', 27), ('208Pb/205Pb', 31),
              ('202Pb/205Pb', 35), ('238U/235U', 39), ('233U/235U', 43),
              ('238U/233U', 47)]

# Tracer values the workbook used ('Data Reduction Engine' rows) versus the
# package ET2535 table columns: (row of value, row of 1σ %, grain attribute, csv column).
TRACER_ROWS = [(152, 153, 'Pb_R25t', '202Pb/205Pb'), (154, 155, 'Pb_R65t', '206Pb/205Pb'),
               (156, 157, 'Pb_R75t', '207Pb/205Pb'), (158, 159, 'Pb_R45t', '204Pb/205Pb'),
               (160, 161, 'Pb_R85t', '208Pb/205Pb'), (162, 163, 'Pb_R76t', '207Pb/206Pb'),
               (164, 165, 'Pb_R46t', '204Pb/206Pb'), (166, 167, 'U_R85t', '238U/235U'),
               (168, 169, 'U_R35t', '233U/235U'), (170, 171, 'U_R83t', '238U/233U')]

# (name, engine row, kind) kind: value | std_abs1 (1σ abs) | std_pct2 (2σ % of row-1)
# | std_age2 (2σ abs Ma) | derived (see python_value)
CHECKS = [
    ('FPb', 222, 'value'), ('FPb_std', 223, 'std_abs1'),
    ('FU', 224, 'value'), ('FU_std', 225, 'std_abs1'),
    ('Pb206s', 118, 'value'), ('Pb206s_std', 119, 'std_abs1'),
    ('Pb207s', 121, 'value'), ('Pb207s_std', 122, 'std_abs1'),
    ('Pb204c', 124, 'value'), ('Pb204c_std', 125, 'std_abs1'),
    ('Pb204b', 229, 'value'),
    ('U238s', 127, 'value'), ('U238s_std', 128, 'std_abs1'),
    ('U235s', 130, 'value'), ('U235s_std', 131, 'std_abs1'),
    ('Pb206r', 133, 'value'), ('Pb206r_std', 134, 'std_abs1'),
    ('Pb207r', 136, 'value'), ('Pb207r_std', 137, 'std_abs1'),
    ('Pb208r', 139, 'value'), ('Pb208r_std', 140, 'std_abs1'),
    ('R75r', 69, 'value'), ('R75r_std', 70, 'std_pct2'),
    ('R68r', 71, 'value'), ('R68r_std', 72, 'std_pct2'),
    ('rho_7568_r', 73, 'value'),
    ('R76r', 77, 'value'), ('R76r_std', 78, 'std_pct2'),
    ('rho_8676_r', 79, 'value'),
    ('R68r_Th', 84, 'value'), ('R68r_Th_std', 85, 'std_pct2'),
    ('R76r_Th', 90, 'value'), ('R76r_Th_std', 91, 'std_pct2'),
    ('t76', 34, 'value'), ('t76_std', 35, 'std_age2'),
    ('t75', 36, 'value'), ('t75_std', 37, 'std_age2'),
    ('t68', 38, 'value'), ('t68_std', 39, 'std_age2'),
    ('t76_Th_corr', 44, 'value'), ('t76_Th_corr_std', 45, 'std_age2'),
    ('t68_Th_corr', 48, 'value'), ('t68_Th_corr_std', 49, 'std_age2'),
    ('U_ppm', 52, 'value'), ('U_ppm_sheet_AW', 52, 'derived'),
    ('Th_ppm', 54, 'value'), ('Th_ppm_sheet_AW', 54, 'derived'), ('Th_U', 55, 'derived'),
    ('Pb_ppm', 58, 'value'), ('Pbr_pg', 59, 'value'), ('Pbc_pg', 60, 'value'),
    ('Pbr_Pbc', 66, 'value'), ('Th232s', 142, 'value'),
]
BISECTION = ('t76', 't76_Th_corr')   # sheet solves by 23-step bisection: 1.79 ka steps
BISECTION_MA = 0.0018
VALUE_RTOL = 1e-9
# Correlations are built from uncertainties, so they are reported like them.
UNCERTAINTY_DERIVED = ('rho_7568_r', 'rho_8676_r')
# Known, explained value differences that are not 2535-specific.
EXPLAINED = {
    'U_ppm': ('sheet row 52 multiplies (U238s+U235s) by 238.0289 (natural U atomic weight); '
              'the engine weights each isotope by its own mass (constants.AWU238, AWU235)'),
    'Th_ppm': 'sheet row 54 uses 232.0381 for 232Th; the engine uses constants.AWTh232 = 232.03805',
    'Pb204c': ('sheet row 233 is exactly 0 (blank cap); the engine keeps the rounding residue of '
               'total 204Pb minus blank 204Pb, compared with atol = 1e-9 * Pb204b'),
}


def python_value(grain, name):
    if name == 'Th_U':
        # Sheet row 729: Th232s/(U238s+U235s); the engine stores no Th/U attribute.
        return grain.Th232s / (grain.U238s + grain.U235s)
    if name == 'U_ppm_sheet_AW':
        # Engine U amounts with the sheet's natural U atomic weight (row 52).
        return (grain.U238s + grain.U235s) * 238.0289 / (grain.sample_weight / 1000) * 1e6
    if name == 'Th_ppm_sheet_AW':
        # xlrd shows row 54 without the parentheses around (C6/1000); the cached value needs them.
        return grain.Th232s * 232.0381 / (grain.sample_weight / 1000) * 1e6
    return float(getattr(grain, name))


def audit(path, strict_covariance=False):
    """Diagnostic covariance by default, as tools/audit_xls.py: the template's z1 and z6
    Tripoli errors fail the 204/205 = (206/205)*(204/206) consistency check."""
    book = xlrd.open_workbook(str(path), on_demand=True)
    raw = book.sheet_by_name('Raw Data Input')
    engine = book.sheet_by_name('Data Reduction Engine')
    th_type, th_age = raw.cell_value(52, 45), raw.cell_value(54, 45)   # AT53, AT55
    if th_type != 'D' or th_age != 't68':
        raise NotImplementedError("This audit supports the workbook's D/t68 Th correction selection only")
    package_tracer = UPbR.load_spike_data('ET2535', 'v3')
    reports, tracer_report = [], None
    for col in range(4, raw.ncols):
        if raw.cell_type(4, col) != xlrd.XL_CELL_NUMBER or not raw.cell_value(4, col):
            continue
        if int(raw.cell_value(6, col)) != 2535:
            continue
        ec = col - 2

        def e(row):
            return engine.cell_value(row-1, ec)
        blanks = dict(Pb_blank_total=e(211), Pb_blank_total_std_rel=e(212),
                      U_blank_total=e(217), U_blank_total_std_rel=e(218),
                      R64b=e(198), R64b_std_rel=e(199), R74b=e(200), R74b_std_rel=e(201),
                      R84b=e(202), R84b_std_rel=e(203), rho_6474_b=e(209), rho_6484_b=e(209))
        common = dict(R64c=e(185), R64c_std_rel=e(186), R74c=e(187), R74c_std_rel=e(188),
                      R84c=e(189), R84c_std_rel=e(190), rho_6474_c=e(196), rho_6484_c=e(196))
        # D mode: sheet row 725 is R68 - l238/l230*(D*[230/238]magma - 1) - l238/l234*([234/238]magma - 1);
        # the engine's D mode equals it when both magma activity ratios are 1.
        if e(681) != 1.0 or e(685) != 1.0:
            raise NotImplementedError('Engine D mode assumes [230Th/238U]magma = [234U/238U]magma = 1')
        th = dict(Th230_correction_type='D', D_Th_U=e(683), D_Th_U_std=e(684),
                  Th_U_magma=e(679), Th_U_magma_std=e(680))
        row = {'Grain ID': raw.cell_value(3, col), 'Sample Weight (mg)': raw.cell_value(4, col),
               'Spike Weight (g)': raw.cell_value(5, col), 'Spike Type': int(raw.cell_value(6, col)),
               'Spike': raw.cell_value(7, col), 'Collector': raw.cell_value(8, col)}
        for ratio, r in RAW_RATIOS:
            row[ratio+' Mean'] = raw.cell_value(r-1, col)
            row[ratio+' % Standard Error'] = raw.cell_value(r, col)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            grain = UPbR.load_grains(pd.DataFrame([row]), {}, blanks, common, th,
                                     spike_version='v3', strict_covariance=strict_covariance)[0]
            # Tracer values the workbook used; overwrite only if they differ from the table.
            tracer = []
            for vrow, srow, attr, csv in TRACER_ROWS:
                sheet_v, sheet_s = e(vrow), e(srow)
                pkg_v = float(package_tracer.loc['value', csv])
                pkg_s = float(package_tracer.loc['uncertainty', csv])
                tracer.append(dict(quantity=attr, sheet=sheet_v, sheet_1s_pct=sheet_s,
                                   ET2535_v3=pkg_v, ET2535_v3_1s_pct=pkg_s,
                                   identical=bool(sheet_v == pkg_v and sheet_s == pkg_s),
                                   relative_difference=abs(sheet_v-pkg_v)/pkg_v,
                                   relative_difference_1s=abs(sheet_s-pkg_s)/pkg_s))
                if sheet_v != pkg_v or sheet_s != pkg_s:
                    setattr(grain, attr, sheet_v)
                    setattr(grain, attr+'_std', sheet_v*sheet_s/100)
            for sheet_v, attr, csv, scale in [(e(150), 'Pb205t', 'Pb205', grain.spike_weight),
                                              (e(151), 'U235t', 'U235', grain.spike_weight)]:
                pkg_v = float(package_tracer.loc['value', csv])
                tracer.append(dict(quantity=attr+' [mol/g]', sheet=sheet_v, ET2535_v3=pkg_v,
                                   identical=bool(sheet_v == pkg_v)))
                if sheet_v != pkg_v:
                    setattr(grain, attr, sheet_v*scale)
            tracer_report = tracer_report or tracer
            # The workbook's decay constants and natural U ratio, for this comparison only.
            grain.lambda_235, grain.lambda_238 = e(241), e(242)
            grain.lambda_232, grain.lambda_230 = e(243), e(244)
            grain.lambda_235_std = e(241)*raw.cell_value(62, 46)/100   # AU63, 1σ %
            grain.lambda_238_std = e(242)*raw.cell_value(63, 46)/100   # AU64, 1σ %
            grain.common_U238_U235 = e(246)
            grain.calc_all()
        checks = []
        for name, erow, kind in CHECKS:
            if engine.cell_type(erow-1, ec) == xlrd.XL_CELL_ERROR:
                code = engine.cell_value(erow-1, ec)
                checks.append(dict(quantity=name, spreadsheet_cell=xlrd.formula.colname(ec)+str(erow),
                                   spreadsheet=None,
                                   spreadsheet_error=xlrd.error_text_from_code.get(code, str(code)),
                                   python=python_value(grain, name), difference=None,
                                   relative_difference=None, matches=None))
                continue
            expected = e(erow)
            if kind == 'std_pct2':
                expected = e(erow-1)*expected/200
            elif kind == 'std_age2':
                expected /= 2
            actual = python_value(grain, name)
            diff = actual - expected
            rel = abs(diff)/abs(expected) if expected else (0.0 if actual == 0 else float('inf'))
            is_std = name.endswith('_std')
            if name in BISECTION:
                matches = abs(diff) <= BISECTION_MA
            elif is_std or name in UNCERTAINTY_DERIVED:
                matches = None    # joint propagation vs sheet's propagation; reported, not forced
            elif name == 'Pb204c' and expected == 0:
                matches = abs(actual) <= 1e-9*abs(e(229))
            else:
                matches = bool(np.isclose(actual, expected, rtol=VALUE_RTOL, atol=0.0))
            checks.append(dict(quantity=name, spreadsheet_cell=xlrd.formula.colname(ec)+str(erow),
                               spreadsheet=expected, python=actual, difference=diff,
                               relative_difference=rel, matches=matches))
        for c in checks:
            c['grain_id'] = grain.id
        reports.append(dict(grain=grain.id, checks=checks,
                            data_quality_passed=grain.data_quality_passed,
                            uncertainty_assumptions=grain.uncertainty_assumptions,
                            warnings=[str(w.message) for w in caught],
                            input_columns={'raw': xlrd.formula.colname(col),
                                           'engine': xlrd.formula.colname(ec)}))
    summary = {}
    for name, _, _ in CHECKS:
        rows = [c for r in reports for c in r['checks'] if c['quantity'] == name]
        numeric = [c for c in rows if c['difference'] is not None]
        is_compared = not (name.endswith('_std') or name in UNCERTAINTY_DERIVED)
        summary[name] = dict(max_relative_difference=max(c['relative_difference'] for c in numeric),
                             max_abs_difference=max(abs(c['difference']) for c in numeric),
                             matches=all(c['matches'] for c in rows) if is_compared else None,
                             sheet_errors={c['grain_id']: c['spreadsheet_error'] for c in rows
                                           if c.get('spreadsheet_error')},
                             note=EXPLAINED.get(name))
    settings = dict(Th230_correction=f'{th_type} ({th_age})', strict_covariance=strict_covariance)
    return dict(source=str(path), settings=settings, tracer=tracer_report,
                summary=summary, grains=reports, source_modified=False,
                limitations=['Cached Excel values audited; no native Excel recalculation performed.',
                             'Uncertainties (_std) are compared but not required to match: the engine '
                             'propagates jointly, the sheet term by term.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('xls', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--strict', action='store_true',
                        help='strict_covariance=True (default is diagnostic, as audit_xls.py)')
    args = parser.parse_args()
    report = audit(args.xls, strict_covariance=args.strict)
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered+'\n')
    for name, s in report['summary'].items():
        print(f"{name:16s} max rel {s['max_relative_difference']:.3e}  max abs {s['max_abs_difference']:.3e}  "
              f"matches={s['matches']}" + (f"  sheet errors {s['sheet_errors']}" if s['sheet_errors'] else ''))
