"""Read-only audit of UPbR26XML legacy workbooks against the Python reduction.

Requires xlrd (optional test extra). Source workbook is never modified.
Run: python tools/audit_xls.py /path/to/workbook.xls --output outputs/audit.json
"""
import argparse
import contextlib
import io
import json
from pathlib import Path
import struct
import xlrd
import numpy as np
import pandas as pd
from IDTIMS_UPbRPy import UPbR, utils


def arithmetic_formula(tokens, row, col):
    """Fully parenthesize BIFF arithmetic; xlrd omits some required parentheses."""
    stack, pos = [], 0
    while pos < len(tokens):
        op = tokens[pos]
        pos += 1
        if op in (3,4,5,6,7):
            right, left = stack.pop(), stack.pop()
            stack.append('('+left+{3:'+',4:'-',5:'*',6:'/',7:'^'}[op]+right+')')
        elif op == 0x15:
            pass
        elif op in (0x12,0x13):
            stack.append('('+('+' if op==0x12 else '-')+stack.pop()+')')
        elif op == 0x1e:
            stack.append(str(struct.unpack_from('<H',tokens,pos)[0])); pos += 2
        elif op == 0x1f:
            stack.append(repr(struct.unpack_from('<d',tokens,pos)[0])); pos += 8
        elif op in (0x24,0x44,0x64,0x2c,0x4c,0x6c):
            r,c = struct.unpack_from('<HH',tokens,pos); pos += 4
            if op in (0x2c,0x4c,0x6c):
                if c & 0x8000:
                    r = row + (r if r < 32768 else r-65536)
                if c & 0x4000:
                    offset = c & 255
                    c = col + (offset if offset < 128 else offset-256)
            c &= 255
            stack.append(xlrd.formula.colname(c)+str(r+1))
        elif op in (0x21,0x41,0x61):
            func = struct.unpack_from('<H',tokens,pos)[0]; pos += 2
            if func not in (20,21,22):
                return None
            stack.append({20:'SQRT',21:'EXP',22:'LN'}[func]+'('+stack.pop()+')')
        else:
            return None
    return stack[0] if len(stack)==1 else None


def formulas(book, sheet_index, wanted):
    """Decode BIFF8 formula records at requested cells, including shared formulas."""
    pos = book._sh_abs_posn[sheet_index]
    direct, shared = {}, []
    while pos + 4 <= len(book.mem):
        opcode, length = struct.unpack_from('<HH', book.mem, pos)
        record = book.mem[pos+4:pos+4+length]
        pos += 4 + length
        if opcode == 0x000A:
            break
        if opcode == 0x0006:
            row, col = struct.unpack_from('<HH', record)
            if (row, col) in wanted:
                size = struct.unpack_from('<H', record, 20)[0]
                direct[row, col] = record[22:22+size]
        elif opcode == 0x04BC:
            rlo, rhi, clo, chi = struct.unpack_from('<HHBB', record)
            size = struct.unpack_from('<H', record, 8)[0]
            shared.append((rlo, rhi, clo, chi, record[10:10+size]))
    result = {}
    for (row, col), tokens in direct.items():
        kind = xlrd.formula.FMLA_TYPE_CELL
        if tokens and tokens[0] == 1:
            for rlo, rhi, clo, chi, stokens in shared:
                if rlo <= row <= rhi and clo <= col <= chi:
                    tokens, kind = stokens, xlrd.formula.FMLA_TYPE_SHARED
                    break
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                result[xlrd.formula.colname(col)+str(row+1)] = arithmetic_formula(tokens,row,col) or xlrd.formula.decompile_formula(
                    book, tokens, len(tokens), kind, browx=row, bcolx=col)
        except (AssertionError, NotImplementedError, IndexError) as error:
            result[xlrd.formula.colname(col)+str(row+1)] = 'Unavailable: '+str(error)
    return result


def audit(path):
    book = xlrd.open_workbook(path, on_demand=True)
    raw = book.sheet_by_name('Raw Data Input')
    engine = book.sheet_by_name('Data Reduction Engine')
    if raw.cell_value(52,45) != 'D' or raw.cell_value(54,45) != 't68':
        raise NotImplementedError("This audit currently supports the workbook's D/t68 correction selection")
    reports = []
    for col in range(4, raw.ncols):
        if raw.cell_type(10, col) != xlrd.XL_CELL_NUMBER or not raw.cell_value(10, col):
            continue
        ec = col - 2
        def e(row):
            return engine.cell_value(row-1, ec)
        fractionation = dict(FPb_Daly=e(222)*100, FPb_Daly_std=e(223)*100,
                             FPb_Faraday=e(222)*100, FPb_Faraday_std=e(223)*100)
        blanks = dict(Pb_blank_total=e(211), Pb_blank_total_std_rel=e(212),
                      U_blank_total=e(217), U_blank_total_std_rel=e(218),
                      R64b=e(198), R64b_std_rel=e(199), R74b=e(200), R74b_std_rel=e(201),
                      R84b=e(202), R84b_std_rel=e(203), rho_6474_b=e(209), rho_6484_b=e(209))
        common = dict(R64c=e(185), R64c_std_rel=e(186), R74c=e(187), R74c_std_rel=e(188),
                      R84c=e(189), R84c_std_rel=e(190), rho_6474_c=e(196), rho_6484_c=e(196))
        th = dict(Th230_correction_type='D', D_Th_U=e(683), D_Th_U_std=e(684),
                  Th_U_magma=e(679), Th_U_magma_std=e(680))
        row = {'Grain ID':raw.cell_value(3,col), 'Sample Weight (mg)':raw.cell_value(4,col),
               'Spike Weight (g)':raw.cell_value(5,col), 'Spike Type':raw.cell_value(6,col),
               'Spike':raw.cell_value(7,col), 'Collector':raw.cell_value(8,col)}
        for ratio, r in [('206Pb/204Pb',11),('206Pb/207Pb',15),('206Pb/205Pb',19),
                         ('207Pb/205Pb',23),('204Pb/205Pb',27),('208Pb/205Pb',31),
                         ('238U/235U',39),('233U/235U',43),('238U/233U',47)]:
            row[ratio+' Mean'] = raw.cell_value(r-1,col)
            row[ratio+' % Standard Error'] = raw.cell_value(r,col)
        grain = UPbR.load_grains(pd.DataFrame([row]),fractionation,blanks,common,th,
                               spike_version='v3', strict_covariance=False)[0]
        # Use the workbook's constants, rather than silently changing calibration.
        grain.lambda_230, grain.lambda_232 = e(244), e(243)
        grain.lambda_235, grain.lambda_238 = e(241), e(242)
        grain.common_U238_U235 = e(246)
        grain.calc_all()
        checks = []
        for name, erow in [('Pb204b',229),('Pb204c',233),('Pb206r',133),('Pb207r',136),
                           ('Pb208r',139),('U238s',127),('U235s',130),('R68r',71),
                           ('R75r',69),('R76r',77),('t68',38),('t75',36),('t76',34),
                           ('t68_Th_corr',48),('t76_Th_corr',44),('R68r_std',72),
                           ('R75r_std',70),('R76r_std',78),('rho_7568_r',73),('rho_8676_r',79),
                           ('t68_std',39),('t75_std',37),('t76_std',35),('t68_Th_corr_std',49),
                           ('t76_Th_corr_std',45)]:
            expected = e(erow)
            if name.startswith('R') and name.endswith('_std'):
                expected = e(erow-1)*expected/200
            elif name.startswith('t') and name.endswith('_std'):
                expected /= 2
            actual = float(getattr(grain,name))
            atol = 2e-6 if name.startswith('t') else 0.0
            checks.append(dict(quantity=name, spreadsheet_cell=xlrd.formula.colname(ec)+str(erow),
                               spreadsheet=expected, python=actual, difference=actual-expected,
                               matches=bool(np.isclose(actual,expected,rtol=1e-8,atol=atol)),
                               matches_sheet_solver_precision=bool(abs(actual-expected) <= 0.0018) if name in ('t76','t76_Th_corr') else None))
        selected = {(r-1,ec) for r in [34,35,38,39,44,45,48,49,71,73,84,90,127,128,133,134,136,137,213,229,233,350,371,470,495,498,499,519,621,622,671,673,725,726]}
        reports.append(dict(grain=grain.id, checks=checks,
                            data_quality_checks=grain.data_quality_checks,
                            data_quality_passed=grain.data_quality_passed,
                            formulas=formulas(book,1,selected),
                            uncertainty_assumptions=grain.uncertainty_assumptions,
                            implied_measured_correlations={
                                'Pb65_Pb76': float(grain.cov_76_65_m/(grain.Pb_R65m_std*grain.Pb_R76m_std)),
                                'Pb65_Pb46': float(grain.cov_65_46_m/(grain.Pb_R65m_std*grain.Pb_R46m_std))},
                            input_columns={'raw':xlrd.formula.colname(col),'engine':xlrd.formula.colname(ec)}))
    return dict(source=str(path), grains=reports, source_modified=False,
                limitations=['Cached Excel values and decoded formulas audited; no native Excel recalculation performed.',
                             'Tracer concentration uncertainties, natural U ratio uncertainty and unspecified covariances excluded.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('xls',type=Path)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    report = audit(args.xls)
    rendered = json.dumps(report,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(rendered+'\n')
    for grain in report['grains']:
        print(grain['grain'],[(c['quantity'],c['difference']) for c in grain['checks'] if not c['matches']])
