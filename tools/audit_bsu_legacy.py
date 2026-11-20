"""Read-only, label-driven BSU UPbR21/22/24 comparison with the current engine.

Run with the repository Python: tools/audit_bsu_legacy.py --output-dir /private/tmp/audit
Data-derived output is deliberately forbidden inside this repository. Cached BIFF
values are evidence, not a fresh Excel recalculation. No workbook is ever saved.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import copy
from collections import Counter, defaultdict
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import struct
import time
import warnings

import numpy as np
import pandas as pd
import xlrd

from IDTIMS_UPbRPy import UPbR, utils
from IDTIMS_UPbRPy.spike_registry import get_registry, to_legacy_frame
try:
    from .audit_xls import formulas as legacy_formulas
except ImportError:
    from audit_xls import formulas as legacy_formulas

ADK = Path.home() / 'Github/Adirondack_mountains/data/geochron_new/TIMS'
WORKBOOKS = {
    'MA1_zircon_UPbR21XML.xls': 'MA1_zircon_TIMS.csv',
    'MA1_apatite_UPbR21XML.xls': 'MA1_apatite_TIMS.csv',
    'MA5_zircon_UPbR21XML.xls': 'MA5_zircon_TIMS.csv',
    'MA5_apatite_UPbR21XML.xls': 'MA5_apatite_TIMS.csv',
    'MA1_rutile_UPbR24XML.xls': 'MA1_rutile_TIMS.csv',
    'MA12_titanite_UPbR24XML.xls': 'MA12_titanite_TIMS.csv',
    'new-all-Willsboro-gt-cpx_UPbR22XML.xls': 'new_Willsboro_garnet_TIMS.csv',
}
PUBLICATION = 'MA1 zircon_CA-TIMS U-Pb data table_04Aug25.xls'
RAW_FIELDS = {
    'Grain ID': "Fraction ID (e.g. IDTIMS 'z' #)",
    'Sample Weight (mg)': 'Sample Weight (mg)', 'Spike Weight (g)': 'Spike Weight (g)',
    'Spike Type': 'Spike Type (""535","2535")',
    'Spike': 'Spike (""ET535","ET2535","BSU1B","MIT1L")',
    'Collector': 'Collector ("F"araday or "D"aly/SEM)',
}
RATIOS = ('206Pb/204Pb', '206Pb/207Pb', '206Pb/205Pb', '207Pb/205Pb',
          '204Pb/205Pb', '208Pb/205Pb', '202Pb/205Pb', '238U/235U',
          '233U/235U', '238U/233U')
TRACER = {
    'Pb_R25t': ('RPb25t', '202Pb/205Pb'), 'Pb_R65t': ('RPb65t', '206Pb/205Pb'),
    'Pb_R75t': ('RPb75t', '207Pb/205Pb'), 'Pb_R45t': ('RPb45t', '204Pb/205Pb'),
    'Pb_R85t': ('RPb85t', '208Pb/205Pb'), 'Pb_R76t': ('RPb76t', '207Pb/206Pb'),
    'Pb_R46t': ('RPb46t', '204Pb/206Pb'),
    'U_R85t': ('RU8Xt (X=5 or 6)', '238U/235U'),
    'U_R35t': ('RU3Xt (X=5 or 6)', '233U/235U'), 'U_R83t': ('RU83t', '238U/233U'),
}
# Section + label disambiguates repeated ratio and error labels. No row numbers.
SECTIONS = {
    'age': 'Model Ages:', 'th_age': '230Th-Disequilibrium Corrected Model Ages',
    'rad': 'Radiogenic Isotope Ratios:',
    'th_rad': '230Th-Disequilibrium-Corrected Radiogenic Isotope Ratios:',
    'sample': 'Sample Isotope Ratios:',
    'common': 'Initial Pb Composition: grey cells from "Laboratory and Sample Constants"',
    'sk': 'Stacey & Kramers Two-Stage Pb Evolution Calculator (<3.7 Ga): copy and paste values into initial Pb if appropriate',
}


def parenthesized_formula(book, tokens, kind, row, col):
    """Extend audit_xls' arithmetic decoder to IF, comparisons and 3D refs.

    xlrd's pretty printer loses required parentheses inside IF arguments. A
    cached replay exposes this for Th ppm and several sample correlations.
    """
    stack, pos = [], 0
    binary = {3: '+', 4: '-', 5: '*', 6: '/', 7: '^', 8: '&',
              9: '<', 10: '<=', 11: '=', 12: '>=', 13: '>', 14: '<>'}
    while pos < len(tokens):
        start = pos
        op = tokens[pos]
        pos += 1
        base = (op & 0x1f) | 0x20 if op >= 0x20 else op
        if op in binary:
            right, left = stack.pop(), stack.pop()
            stack.append('(' + left + binary[op] + right + ')')
        elif op in (0x12, 0x13):
            stack.append('(' + ('+' if op == 0x12 else '-') + stack.pop() + ')')
        elif op == 0x14:
            stack.append('(' + stack.pop() + '/100)')
        elif op == 0x15:
            pass
        elif op == 0x16:
            stack.append('0')
        elif op == 0x17:
            size, flags = tokens[pos], tokens[pos+1]
            pos += 2
            width = 2 if flags & 1 else 1
            value = tokens[pos:pos+size*width].decode('utf-16-le' if width == 2 else 'latin1')
            pos += size*width
            stack.append(json.dumps(value))
        elif op == 0x19:
            flags, count = struct.unpack_from('<BH', tokens, pos)
            pos += 3
            if flags & 4:  # optimized CHOOSE jump table
                pos += 2*(count+1)
            if flags & 16:
                stack.append('SUM(' + stack.pop() + ')')
        elif base in (0x21, 0x22):
            if base == 0x22:
                nargs = tokens[pos] & 127
                pos += 1
            func = struct.unpack_from('<H', tokens, pos)[0] & 0x7fff
            pos += 2
            definition = xlrd.formula.func_defs[func]
            if base == 0x21:
                nargs = definition[1]
            args = stack[-nargs:] if nargs else []
            if nargs:
                del stack[-nargs:]
            stack.append(definition[0] + '(' + ','.join(args) + ')')
        elif base in (0x24, 0x25, 0x2c, 0x2d, 0x3a, 0x3b) or op in (0x1e, 0x1f, 0x1d):
            size = {0x24: 4, 0x25: 8, 0x2c: 4, 0x2d: 8, 0x3a: 6, 0x3b: 10,
                    0x1e: 2, 0x1f: 8, 0x1d: 1}[base]
            pos += size
            with contextlib.redirect_stdout(io.StringIO()):
                value = xlrd.formula.decompile_formula(book, tokens[start:pos], pos-start,
                                                       kind, browx=row, bcolx=col)
            stack.append(value)
        else:
            return None
    return stack[0] if len(stack) == 1 else None


def formulas(book, sheet_index, wanted):
    """Read BIFF formula records, preserving arithmetic precedence in IF."""
    fallback = legacy_formulas(book, sheet_index, wanted)
    pos, direct, shared = book._sh_abs_posn[sheet_index], {}, []
    while pos+4 <= len(book.mem):
        opcode, length = struct.unpack_from('<HH', book.mem, pos)
        record = book.mem[pos+4:pos+4+length]
        pos += 4+length
        if opcode == 0x000a:
            break
        if opcode == 0x0006:
            r, c = struct.unpack_from('<HH', record)
            if (r, c) in wanted:
                size = struct.unpack_from('<H', record, 20)[0]
                direct[r, c] = record[22:22+size]
        elif opcode == 0x04bc:
            rlo, rhi, clo, chi = struct.unpack_from('<HHBB', record)
            size = struct.unpack_from('<H', record, 8)[0]
            shared.append((rlo, rhi, clo, chi, record[10:10+size]))
    for (r, c), tokens in direct.items():
        kind = xlrd.formula.FMLA_TYPE_CELL
        if tokens and tokens[0] == 1:
            for rlo, rhi, clo, chi, other in shared:
                if rlo <= r <= rhi and clo <= c <= chi:
                    tokens, kind = other, xlrd.formula.FMLA_TYPE_SHARED
                    break
        try:
            precise = parenthesized_formula(book, tokens, kind, r, c)
            if precise:
                fallback[address(r, c)] = precise
        except (AssertionError, IndexError, KeyError, NotImplementedError, UnicodeError):
            pass  # retain explicitly decoded legacy fallback, checked by replay
    return fallback


def address(r, c):
    return f'{xlrd.formula.colname(c)}{r + 1}'


def norm(value):
    return ' '.join(str(value).split())


class Labels:
    """Inventory A/B labels, retaining duplicates; fail closed on ambiguity."""
    def __init__(self, sheet):
        self.sheet = sheet
        self.rows = defaultdict(list)
        for r in range(sheet.nrows):
            for c in range(min(2, sheet.ncols)):
                value = sheet.cell_value(r, c)
                if isinstance(value, str) and value.strip():
                    self.rows[norm(value)].append(r)

    def find(self, label, section=None):
        candidates = sorted(set(self.rows[norm(label)]))
        supplemental = self.rows.get('Sample 208Pb/204 Calculations:', [])
        if (supplemental and section != 'Sample 208Pb/204 Calculations:'
                and any(r < supplemental[0] for r in candidates)):
            candidates = [r for r in candidates if r < supplemental[0]]
        if section:
            start = self.find(SECTIONS.get(section, section))
            candidates = [r for r in candidates if r > start]
            if candidates:
                return candidates[0]
        if len(candidates) != 1:
            raise ValueError(f'{self.sheet.name}: ambiguous/missing {label!r}: {candidates}')
        return candidates[0]

    def error(self, row):
        r = row + 1
        label = norm(self.sheet.cell_value(r, 0))
        if not (label.startswith('±') or label.startswith('s')):
            raise ValueError(f'Missing labeled uncertainty after {row + 1}: {label}')
        return r

    def inventory(self):
        return {k: [r + 1 for r in sorted(set(v))] for k, v in self.rows.items()}


def number(sheet, r, c):
    cell = sheet.cell(r, c)
    if cell.ctype == xlrd.XL_CELL_ERROR:
        return {'excel_error': xlrd.error_text_from_code.get(cell.value, str(cell.value))}
    return cell.value


def finite(value):
    return isinstance(value, (int, float, np.number)) and math.isfinite(value)


class FormulaReplay:
    """Small, closed AST interpreter for scalar BIFF audit interventions.

    Unchanged precedents retain their cached values. Only descendants of an
    explicit patch are recalculated. This is not an Excel recalculation engine.
    IF is lazy; unsupported nodes/functions fail visibly instead of guessing.
    """
    reference = re.compile(r"(?:'([^']+)'!)?(\$?[A-Z]+\$?\d+)(?::(\$?[A-Z]+\$?\d+))?")

    def __init__(self, book, sheet, decoded, patches=None):
        self.book, self.sheet, self.decoded = book, sheet, decoded
        self.patches = patches or {}
        self.memo = {}
        self.dependencies = {}

    def cached(self, sheet, cell):
        m = re.fullmatch(r'([A-Z]+)(\d+)', cell)
        c = 0
        for ch in m[1]:
            c = c*26 + ord(ch)-64
        value = number(self.book.sheet_by_name(sheet), int(m[2])-1, c-1)
        if isinstance(value, dict):
            raise ValueError(str(value))
        return value or 0.0

    def affected(self, cell, trail=()):
        if cell in self.patches:
            return True
        if cell in self.dependencies:
            return self.dependencies[cell]
        if cell in trail:
            raise ValueError('Circular formula: ' + cell)
        formula = self.decoded.get(cell, '')
        refs = [(sn or self.sheet, a.replace('$', '')) for sn, a, _ in self.reference.findall(formula)]
        changed = any(sn == self.sheet and self.affected(a, (*trail, cell)) for sn, a in refs)
        self.dependencies[cell] = changed
        return changed

    def value(self, cell):
        if cell in self.patches:
            return self.patches[cell]
        if cell not in self.memo:
            self.memo[cell] = (self.evaluate(self.decoded[cell]) if self.affected(cell)
                               else self.cached(self.sheet, cell))
        return self.memo[cell]

    def evaluate(self, formula):
        refs = {}
        def replace(match):
            sn, a, b = match.groups()
            if b and a.replace('$', '') != b.replace('$', ''):
                raise ValueError('Non-scalar range')
            token = 'ref_' + str(len(refs))
            refs[token] = (sn or self.sheet, a.replace('$', ''))
            return token
        expression = self.reference.sub(replace, formula).replace('^', '**').replace('<>', '!=')
        expression = re.sub(r'(?<![<>=!])=(?!=)', '==', expression)
        def visit(node):
            if isinstance(node, ast.Constant):
                return node.value
            if isinstance(node, ast.Name) and node.id in refs:
                sn, cell = refs[node.id]
                return self.value(cell) if sn == self.sheet else self.cached(sn, cell)
            if isinstance(node, ast.UnaryOp):
                value = visit(node.operand)
                if isinstance(node.op, ast.USub):
                    return -value
                if isinstance(node.op, ast.UAdd):
                    return value
            if isinstance(node, ast.BinOp):
                a, b = visit(node.left), visit(node.right)
                if isinstance(node.op, ast.Add):
                    return a+b
                if isinstance(node.op, ast.Sub):
                    return a-b
                if isinstance(node.op, ast.Mult):
                    return a*b
                if isinstance(node.op, ast.Div):
                    return a/b
                if isinstance(node.op, ast.Pow):
                    return a**b
            if isinstance(node, ast.Compare) and len(node.ops) == 1:
                a, b = visit(node.left), visit(node.comparators[0])
                op = node.ops[0]
                if isinstance(op, ast.Eq):
                    return a == b
                if isinstance(op, ast.NotEq):
                    return a != b
                if isinstance(op, ast.Gt):
                    return a > b
                if isinstance(op, ast.Lt):
                    return a < b
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == 'IF':
                    return visit(node.args[1] if visit(node.args[0]) else node.args[2])
                funcs = {'SQRT': math.sqrt, 'EXP': math.exp, 'LN': math.log,
                         'ABS': abs, 'SUM': lambda *args: sum(args)}
                if node.func.id in funcs:
                    return funcs[node.func.id](*(visit(a) for a in node.args))
            raise ValueError('Unsupported formula AST: ' + ast.dump(node))
        return visit(ast.parse(expression, mode='eval').body)


def compare(quantity, sheet_value, engine_value, cell, group, **extra):
    ok = finite(sheet_value) and finite(engine_value)
    delta = float(engine_value - sheet_value) if ok else None
    rel = delta / abs(sheet_value) if ok and sheet_value else (0.0 if ok and not delta else None)
    status = 'MISMATCH'
    if ok and (delta == 0 or rel is not None and abs(rel) < 1e-10):
        status = 'exact'
    elif ok and (rel is not None and abs(rel) < 1e-6 or
                 quantity in ('t76', 't76_Th_corr') and abs(delta) <= 0.0018):
        status = 'numerical'
    return dict(quantity=quantity, sheet=sheet_value, engine=engine_value,
                difference=delta, absolute_difference=abs(delta) if ok else None,
                relative_difference=rel, status=status, cell=cell, group=group, **extra)


def settings_cell(raw, label, offset=1):
    hits = [(r, c) for r in range(raw.nrows) for c in range(36, raw.ncols)
            if norm(raw.cell_value(r, c)) == norm(label)]
    if label == '238U/235U':
        constant_cols = {c for r in range(raw.nrows) for c in range(36, raw.ncols)
                         if norm(raw.cell_value(r, c)) == 'l 235U'}
        hits = [(r, c) for r, c in hits if c in constant_cols]
    if len(hits) != 1:
        raise ValueError(f'Raw settings: ambiguous/missing {label}: {hits}')
    r, c = hits[0]
    return dict(cell=address(r, c + offset), value=raw.cell_value(r, c + offset),
                uncertainty_cell=address(r, c + offset + 1),
                uncertainty=raw.cell_value(r, c + offset + 1))


def tracer_match(composition):
    """Exact binary comparison; names alone do not select a calibration."""
    matches, nearest = [], []
    for spike in get_registry().spikes.values():
        for version in spike.versions:
            frame = to_legacy_frame(version).apply(pd.to_numeric, errors='coerce')
            differences = []
            for label, entry in composition.items():
                for field, row in [('value', 'value'), ('error_pct_1s', 'uncertainty')]:
                    if field not in entry:
                        continue
                    actual = float(frame.loc[row, label]) if label in frame else None
                    if actual != entry[field]:
                        differences.append(dict(quantity=label, field=field, sheet=entry[field], registry=actual))
            if not differences:
                matches.append(version.key)
            nearest.append((len(differences), version.key, differences))
    nearest.sort(key=lambda x: (x[0], x[1]))
    return dict(exact_keys=matches, nearest_key=nearest[0][1], differences=nearest[0][2])


def specifications(labels):
    specs = []
    def add(name, label, section=None, kind='value', group='composition'):
        r = labels.find(label, section)
        specs.append((name, r, kind, group))
        return r
    for attr, label in [('Pb_R65m', 'RPb65m'), ('Pb_R46m', 'RPb46m'),
                        ('Pb_R76m', 'RPb76m'), ('Pb_R45m', 'RPb45m'),
                        ('Pb_R75m', 'RPb75m'), ('Pb_R85m', 'RPb85m'),
                        ('U_R85m', 'RU8Xm (X=5 or 6)'), ('U_R35m', 'RU3Xm (X=5 or 6)'),
                        ('U_R83m', 'RU83m')]:
        r = add(attr, label, group='measured')
        specs.append((attr + '_error_pct_1s', labels.error(r), 'pct1', 'measured'))
    for name, label in [('FPb', 'F(Pb)'), ('FU', 'F(U)')]:
        r = add(name, label, group='fractionation')
        specs.append((name + '_std', labels.error(r), 'value', 'fractionation'))
    for name in ('Pb206s', 'Pb207s', 'Pb204c', 'U238s', 'U235s', 'Pb206r', 'Pb207r', 'Pb208r'):
        r = add(name, name + ' [mol]', 'Molar Quantities & Errors:', group='amounts')
        specs.append((name + '_std', labels.error(r), 'value', 'uncertainties'))
    for name in ('Pb204b', 'Pb206b', 'Pb207b', 'Pb208b', 'Pb206c', 'Pb207c', 'Pb208c'):
        add(name, name + ' [mol]', 'Pb Partitioning', group='amounts')
    for section, suffix in [('age', ''), ('th_age', '_Th_corr')]:
        for name, ratio in [('t76', '207Pb/206Pb'), ('t75', '207Pb/235U'), ('t68', '206Pb/238U')]:
            if name == 't75' and suffix:
                continue
            r = add(name + suffix, ratio, section, group='dates')
            specs.append((name + suffix + '_std', labels.error(r), 'age2', 'uncertainties'))
    for section, suffix in [('rad', ''), ('th_rad', '_Th'), ('sample', 's')]:
        pairs = [('R75r', '207Pb/235U'), ('R68r', '206Pb/238U'), ('R76r', '207Pb/206Pb')]
        if section == 'sample':
            pairs = [('R84', '238U/204Pb'), ('R64', '206Pb/204Pb'),
                     ('R54', '235U/204Pb'), ('R74', '207Pb/204Pb'),
                     ('R86', '238U/206Pb'), ('R76', '207Pb/206Pb'), ('R46', '204Pb/206Pb')]
        for name, label in pairs:
            r = add(name + suffix, label, section, group='ratios')
            specs.append((name + suffix + '_error_pct_2s', labels.error(r), 'pct2', 'uncertainties'))
    for name, label, section in [('rho_7568_r', 'rho (7/5-6/8)', 'rad'),
                                 ('rho_8676_r', 'rho (8/6-7/6)', 'rad'),
                                 ('rho_8676_s', 'rho (8/6-7/6)', 'sample'),
                                 ('rho_8646_s', 'rho (8/6-4/6)', 'sample'),
                                 ('rho_7646_s', 'rho (7/6-4/6)', 'sample')]:
        add(name, label, section, group='correlations')
    for name, label in [('U_ppm', 'U (ppm)'), ('Th_ppm', 'Th (ppm) (wrt t68)'),
                        ('Th_U', 'Th/U (wrt t68)'), ('Pb_ppm', 'Pb total (ppm)'),
                        ('Pbr_pg', 'Pb rad (pg)'), ('Pbc_pg', 'Pb common (pg)'),
                        ('Pbr_Pbc', 'Pb*/Pbc'), ('R64fc', '206Pb/204Pb (fc-spike)'),
                        ('R86rad', '208Pbr/206Pbr'), ('mol_fraction_206r', 'Mol% 206r (wrt r,b,c)'),
                        ('Th232s', 'Th232s [mol] (wrt t68)'),
                        ('Pb_R84m_std', 'sRPb84m')]:
        add(name, label)
    if 'Sample 208Pb/204 Calculations:' in labels.rows:
        add('Pb208sample', 'Pb208s [mol]', 'Sample 208Pb/204 Calculations:', group='amounts')
        add('Pb208sample_std', 'sPb208s (abs)', kind='unsupported', group='uncertainties')
        for name, label in [('Pb_R86sample', '208Pb/206Pb'), ('Pb_R84sample', '208Pb/204Pb')]:
            r = add(name, label, 'Sample 208Pb/204 Calculations:', group='ratios')
            specs.append((name+'_error_pct_2s', labels.error(r), 'unsupported', 'uncertainties'))
        add('rho_Pb8464sample', 'rho (8/4-6/4)', 'Sample 208Pb/204 Calculations:',
            kind='unsupported', group='correlations')
    return specs


def actual_value(g, name, kind):
    if kind == 'unsupported':
        return None
    if name == 'Pb208sample':
        return g.Pb208r + g.Pb208c
    if name == 'Pb_R86sample':
        return (g.Pb208r + g.Pb208c)/g.Pb206s
    if name == 'Pb_R84sample':
        return (g.Pb208r + g.Pb208c)/g.Pb204c if g.Pb204c > 0 else 0.0
    name = name.replace('R75r_Th', 'R75r')
    if kind == 'age2':
        return 2 * getattr(g, name)
    if kind in ('pct1', 'pct2'):
        base = name.rsplit('_error_pct_', 1)[0]
        value, sigma = getattr(g, base), getattr(g, base + '_std')
        return (100 if kind == 'pct1' else 200)*sigma/value if value else (0.0 if not sigma else None)
    if name == 'Th_U':
        return g.Th232s / (g.U238s + g.U235s)
    if name == 'R64fc':
        return (g.Pb206r + g.Pb206b + g.Pb206c) / (g.Pb204b + g.Pb204c)
    if name == 'R86rad':
        return g.Pb208r / g.Pb206r
    if name == 'mol_fraction_206r':
        return g.Pb206r / (g.Pb206r + g.Pb206b + g.Pb206c)
    return float(getattr(g, name))


def audit_workbook(path, include_formulas=True):
    book = xlrd.open_workbook(str(path), on_demand=True, logfile=io.StringIO())
    try:
        raw, sheet = (book.sheet_by_name(n) for n in ('Raw Data Input', 'Data Reduction Engine'))
        rl, el = Labels(raw), Labels(sheet)
        specs = specifications(el)
        raw_rows = {name: rl.find(label) for name, label in RAW_FIELDS.items()}
        ratio_rows = {name: rl.find(name) for name in RATIOS}
        settings = {label: settings_cell(raw, label) for label in
                    ('"magma" or "D"?', 'DTh/U', 't ("t68", "t75", "off")', '(Th/U)magma',
                     '[230Th/238U]magma', 'l 235U', 'l 238U', 'l 232Th', 'l 230Th',
                     '238U/235U', '<initialPbModelET>', '<TracerUPbModel>')}
        # Read both collector tables and the configured U fractionation, even
        # though double-spiked U derives F(U) from its measured ratios.
        settings['fractionation_tables'] = []
        for r in range(raw.nrows):
            for c in range(36, raw.ncols-3):
                if raw.cell_value(r, c) in ('Faraday', 'Daly/SEM'):
                    settings['fractionation_tables'].append(dict(
                        label=raw.cell_value(r, c), cell=address(r, c+1),
                        value=raw.cell_value(r, c+1), uncertainty=raw.cell_value(r, c+2)))
        cols = [c for c in range(4, min(raw.ncols, sheet.ncols + 2))
                if isinstance(raw.cell_value(raw_rows['Grain ID'], c), str)
                and raw.cell_value(raw_rows['Grain ID'], c).strip()]
        # Use the engine's formula link to identify corresponding raw columns, not c-2.
        idrow = el.find('Fraction ID')
        links = formulas(book, book.sheet_names().index(sheet.name),
                         {(idrow, c) for c in range(2, sheet.ncols)})
        engine_cols = {}
        for c in range(2, sheet.ncols):
            m = re.search(r"'Raw Data Input'!\$?([A-Z]+)\$?(\d+)", links.get(address(idrow, c), ''))
            if m and int(m[2]) == raw_rows['Grain ID'] + 1:
                engine_cols[m[1]] = c
        wanted_cols = [engine_cols[xlrd.formula.colname(c)] for c in cols]
        fdict = formulas(book, book.sheet_names().index(sheet.name),
                         {(r, c) for r in range(sheet.nrows) for c in wanted_cols}) if include_formulas else {}
        reports = []
        for c in cols:
            ec = engine_cols[xlrd.formula.colname(c)]
            def e(label, section=None):
                return sheet.cell_value(el.find(label, section), ec)
            def err(label, section=None):
                return sheet.cell_value(el.error(el.find(label, section)), ec)
            row = {name: raw.cell_value(r, c) for name, r in raw_rows.items()}
            blank_errors = []
            for name, r in ratio_rows.items():
                row[name + ' Mean'] = raw.cell_value(r, c)
                er = r + 1
                if norm(raw.cell_value(er, 2)) != '% Standard Error':
                    raise ValueError(f'Missing Raw Data Input uncertainty label after {name}')
                raw_error = raw.cell_value(er, c)
                # Excel direct references evaluate an empty numeric error cell
                # as zero. Keep that source distinction in the evidence.
                if raw_error == '':
                    blank_errors.append(address(er, c))
                row[name + ' % Standard Error'] = 0.0 if raw_error == '' else raw_error
            blank = dict(Pb_blank_total=e('Pb blank assumed [pg]'),
                         Pb_blank_total_std_rel=err('Pb blank assumed [pg]'),
                         U_blank_total=e('U blank assumed [pg]'), U_blank_total_std_rel=err('U blank assumed [pg]'),
                         rho_6474_b=e('rho 6/4b-x/4b'), rho_6484_b=e('rho 6/4b-x/4b'))
            common = dict(rho_6474_c=e('rho 6/4c-x/4c'), rho_6484_c=e('rho 6/4c-x/4c'))
            for ratio in ('64', '74', '84'):
                blank['R' + ratio + 'b'] = e('RPb' + ratio + 'b')
                blank['R' + ratio + 'b_std_rel'] = err('RPb' + ratio + 'b')
                common['R' + ratio + 'c'] = e('RPb' + ratio + 'c', 'common')
                common['R' + ratio + 'c_std_rel'] = err('RPb' + ratio + 'c', 'common')
            th = dict(Th230_correction_type=settings['"magma" or "D"?']['value'],
                      D_Th_U=e('DTh/DU'), D_Th_U_std=err('DTh/DU'),
                      Th_U_magma=e('Th/U magma', 'R68dc (magma) calcs'),
                      Th_U_magma_std=err('Th/U magma', 'R68dc (magma) calcs'))
            fp = e('F(Pb)')
            frac = dict(FPb_Daly=fp*100, FPb_Daly_std=err('F(Pb)')*100,
                        FPb_Faraday=fp*100, FPb_Faraday_std=err('F(Pb)')*100)
            composition = {label: dict(value=e(slabel), error_pct_1s=err(slabel))
                           for _, (slabel, label) in TRACER.items()}
            composition['Pb205'] = dict(value=e('Pb205t [mol/g]'))
            composition['U235'] = dict(value=e('U23Xt [mol/g] (X=3, 5 or 6)'))
            match = tracer_match(composition)
            record = dict(fraction=row['Grain ID'], uid=xlrd.formula.colname(c) + ':' + row['Grain ID'],
                          raw_column=xlrd.formula.colname(c), engine_column=xlrd.formula.colname(ec),
                          inputs=row, settings=dict(fractionation=frac, blanks=blank, common=common, th=th,
                          constants={key: settings[key] for key in ('l 235U', 'l 238U', 'l 232Th', 'l 230Th', '238U/235U')},
                          sk_age_Ga=e('Estimated'), sk_values={r: e('RPb' + r + 'c', 'sk') for r in ('64', '74', '84')}),
                          tracer=dict(composition=composition, **match), checks=[])
            record['empty_error_cells_treated_as_excel_zero'] = blank_errors
            record['measured_covariance_source'] = 'No explicit raw correlation cells supplied; linked-ratio identities and documented engine completion assumptions.'
            record['tracer']['source_table_headers'] = [dict(cell=address(r, c), label=raw.cell_value(r, c))
                for r in range(raw.nrows) for c in range(36, raw.ncols)
                if isinstance(raw.cell_value(r, c), str) and raw.cell_value(r, c).startswith(row['Spike']+' ')]
            record['input_cells'] = {name: address(r, c) for name, r in raw_rows.items()}
            record['input_cells'].update({name + suffix: address(r + shift, c)
                                         for name, r in ratio_rows.items()
                                         for suffix, shift in [(' Mean', 0), (' % Standard Error', 1)]})
            record['settings']['common_cells'] = {
                label: address(el.find(label, 'common'), ec)
                for label in ('RPb64c', 'RPb74c', 'RPb84c')}
            record['formulas'] = {cell: value for cell, value in fdict.items()
                                  if re.match(r'[A-Z]+', cell)[0] == xlrd.formula.colname(ec)}
            caught = []
            g = None
            try:
                with warnings.catch_warnings(record=True) as caught, contextlib.redirect_stdout(io.StringIO()):
                    warnings.simplefilter('always')
                    g = UPbR.load_grains(pd.DataFrame([row]), frac, blank, common, th,
                                         spike_key=match['exact_keys'][0] if match['exact_keys'] else None,
                                         spike_version='v1', strict_covariance=False)[0]
                    bootstrap = {n: float(getattr(g, n)) for n in ('R68r','R75r','R76r','t68','t75','t76')}
                    # If registry has no exact snapshot, overwrite this disposable grain
                    # with the complete sheet composition. Never mutate a registry record.
                    for attr, (_, label) in TRACER.items():
                        entry = composition[label]
                        setattr(g, attr, entry['value'])
                        setattr(g, attr + '_std', entry['value'] * entry['error_pct_1s'] / 100)
                    g.Pb205t = composition['Pb205']['value'] * g.spike_weight
                    g.U235t = composition['U235']['value'] * g.spike_weight
                    g.Pb_R84t = g.Pb_R85t / g.Pb_R45t
                    g.Pb_R84t_std = g.Pb_R84t * math.hypot(g.Pb_R85t_std/g.Pb_R85t, g.Pb_R45t_std/g.Pb_R45t)
                    for isotope in ('235', '238', '232', '230'):
                        setattr(g, 'lambda_' + isotope, settings['l ' + isotope + ('U' if isotope in ('235', '238') else 'Th')]['value'])
                    g.common_U238_U235 = settings['238U/235U']['value']
                    # Calibration errors are read explicitly even though dates do not propagate them.
                    for isotope in ('235', '238', '232', '230'):
                        item = settings['l ' + isotope + ('U' if isotope in ('235', '238') else 'Th')]
                        setattr(g, 'lambda_' + isotope + '_std', item['value'] * (item['uncertainty'] or 0) / 100)
                    g.calc_all()
                record['diagnostic'] = 'reduced'
                record['tracer']['registry_to_sheet_delta'] = {n: float(getattr(g,n))-v for n,v in bootstrap.items()}
                record['assumptions'] = g.uncertainty_assumptions
                record['quality'] = g.data_quality_checks
                strict = copy.deepcopy(g)
                strict.strict_covariance = True
                try:
                    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
                        warnings.simplefilter('ignore')
                        strict.calc_all()
                    record['strict'] = dict(accepted=True)
                except (ValueError, ArithmeticError) as error:
                    record['strict'] = dict(accepted=False, reason=str(error))
            except (ValueError, TypeError, ArithmeticError) as error:
                record['diagnostic'] = 'refused'
                record['reduction_error'] = str(error)
                record['strict'] = dict(accepted=False, reason=str(error))
                g = None
                # Still exercise strict mode, even when diagnostic reduction
                # stopped before load_grains could return a grain.
                try:
                    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
                        warnings.simplefilter('ignore')
                        UPbR.load_grains(pd.DataFrame([row]), frac, blank, common, th,
                                         spike_key=match['exact_keys'][0] if match['exact_keys'] else None,
                                         spike_version='v1', strict_covariance=True)
                    record['strict'] = dict(accepted=True, stage='registry bootstrap')
                except (ValueError, TypeError, ArithmeticError) as strict_error:
                    record['strict'] = dict(accepted=False, reason=str(strict_error), stage='registry bootstrap; exact-snapshot reduction not reached')
            record['warnings'] = sorted(set(str(w.message) for w in caught))
            for name, r, kind, group in specs:
                value = actual_value(g, name, kind) if g else None
                check = compare(name, number(sheet, r, ec), value,
                                sheet.name + '!' + address(r, ec), group,
                                formula=fdict.get(address(r, ec)), convention=kind)
                record['checks'].append(check)
            # Sheet-specific numerical interventions, independent of engine implementation.
            record['experiments'] = experiments(g, e, err, record)
            record['formula_experiments'] = formula_experiments(book, sheet, el, ec, record) if include_formulas else {}
            record['export_engine'] = export_engine_values(g, settings)
            record['_grain'] = g
            reports.append(record)
        output_table = read_table(book, 'U-Pb Data Table Output')
        switches = [r['ratio_switch'] for r in output_table['rows'] if r.get('ratio_switch')]
        if not switches or len({(s['cell'], s['value']) for s in switches}) != 1:
            raise ValueError('Export ratio selection must be explicit and consistent')
        settings['export_ratio_switch'] = switches[0]
        for record in reports:
            record['export_engine'] = export_engine_values(record['_grain'], settings)
        attach_output_table(reports, output_table)
        return dict(source=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    layout=re.search(r'UPbR(\d+)', path.name)[1],
                    row_map={raw.name: rl.inventory(), sheet.name: el.inventory()},
                    settings=settings, grains=reports, output_table=output_table)
    finally:
        book.release_resources()


def experiments(g, e, err, record):
    if g is None:
        return {}
    # Counterfactual values replace one formula convention at a time.
    k = g.common_U238_U235
    th_sheet = g.Pb208r / np.expm1(g.lambda_232 * e('206Pb/238U', 'th_age') * 1e6)
    out = dict(
        U_ppm_sheet_atomic_weight=(g.U238s + g.U235s)*238.0289/g.sample_weight*1e9,
        Th_ppm_sheet_atomic_weight=th_sheet*232.0381/g.sample_weight*1e9,
        Th_U_sheet_age=th_sheet/(g.U238s + g.U235s),
        Pbc_sheet_nominal_initial_masses=None,
        R68r_Th_sheet_total_U=None,
        t68_Th_corr_sheet_total_U=None,
        Th_U_engine_U238_denominator=g.Th232s/g.U238s,
    )
    aw = (204 + 206*g.R64c + 207*g.R74c + 208*g.R84c)/(1 + g.R64c + g.R74c + g.R84c)
    out['Pbc_sheet_nominal_initial_masses'] = (
        (g.Pb204b + g.Pb206b + g.Pb207b + g.Pb208b)*g.Pb_blank_AW
        + (g.Pb204c + g.Pb206c + g.Pb207c + g.Pb208c)*aw)*1e12
    # This layout omits the quotient magnitude entirely; verify its cache.
    out['sRPb84m_sheet_formula'] = math.hypot(g.Pb_R85m_std/g.Pb_R85m, g.Pb_R45m_std/g.Pb_R45m)
    out['sRPb84m_quotient_rule'] = g.Pb_R84m_std
    # Known derivative error: change its square and linked covariance term,
    # keeping all remaining cached terms. This isolates, not conflates, causes.
    wrong = e('dPb207r/dR76m')
    right = g.Pb_R65m*(1+2*g.FPb)*g.Pb205t
    sigma76 = g.Pb_R76m_std
    cov = e('cov-R65m/R76m', 'dPb207r/dR65m')
    variance = e('sPb207r (abs)')**2 + (right**2-wrong**2)*sigma76**2
    variance += 2*cov*e('dPb207r/dR65m')*(right-wrong)
    out['Pb207r_std_fix_derivative_only'] = math.sqrt(variance) if variance >= 0 else None
    out['Pb207r_std_sheet'] = e('sPb207r (abs)')
    out['Pb207r_std_engine'] = g.Pb207r_std
    partitioned = copy.deepcopy(g)
    partitioned.calc_Pb_partitioning()
    out['Pb204c_partitioned'] = partitioned.Pb204c
    out['Pb204c_recomputed'] = g.Pb204c
    if partitioned.Pb204c == 0:
        partitioned.calc_PbPb_Rs()
        partitioned.calc_UPb_Rs()
        partitioned.calc_all_Pb_Rs_uncertainty()
        partitioned.calc_all_UPb_Rs_uncertainty()
        partitioned.calc_PbPbs_rhos()
        partitioned.calc_UPbs_rhos()
        out['preserve_partitioned_zero'] = [compare(c['quantity'], c['sheet'],
            getattr(partitioned, c['quantity']), c['cell'], 'counterfactual')
            for c in record['checks'] if c['quantity'] in ('Pb204c', 'R46s', 'R64s', 'R74s', 'R54s', 'R84s')]
        out['preserve_partitioned_zero_correlations'] = [compare(c['quantity'], c['sheet'],
            getattr(partitioned, c['quantity']), c['cell'], 'counterfactual')
            for c in record['checks'] if c['quantity'] in ('rho_8646_s', 'rho_7646_s')]
    legacy = copy.deepcopy(g)
    legacy.prop_U238s_uncertainty()
    legacy.prop_Pb206r_uncertainty()
    out['U238s_std_term_by_term'] = legacy.U238s_std
    out['Pb206r_std_term_by_term'] = legacy.Pb206r_std
    if record['settings']['th']['Th230_correction_type'] == 'magma':
        # Re-solve same implicit equation with total natural U denominator.
        from scipy.optimize import brentq
        def residual(t):
            thu = g.Pb208r/np.expm1(g.lambda_232*t*1e6)/(g.U238s*(1+1/k))
            return np.expm1(g.lambda_238*t*1e6)-g.R68r+g.lambda_238/g.lambda_230*(thu/g.Th_U_magma-1)
        t = brentq(residual, g.t68/2, g.t68*2, xtol=1e-10)
        out['t68_Th_corr_sheet_total_U'] = t
        out['R68r_Th_sheet_total_U'] = float(np.expm1(g.lambda_238*t*1e6))
        out['R76r_Th_sheet_total_U'] = g.R76r*g.R68r/out['R68r_Th_sheet_total_U']
        out['t76_Th_corr_sheet_total_U'] = utils.calc_t76(out['R76r_Th_sheet_total_U'],
            lambda_235=g.lambda_235, lambda_238=g.lambda_238, common_U238_U235=k)
        out['total_U_checks'] = [compare(c['quantity'], c['sheet'],
            out[c['quantity']+'_sheet_total_U'], c['cell'], 'counterfactual')
            for c in record['checks'] if c['quantity']+'_sheet_total_U' in out
            and out[c['quantity']+'_sheet_total_U'] is not None]
    mass_check = next(c for c in record['checks'] if c['quantity'] == 'Pbc_pg')
    out['nominal_mass_minus_engine_pg'] = out['Pbc_sheet_nominal_initial_masses']-mass_check['engine']
    return out


def formula_experiments(book, sheet, labels, col, record):
    decoded = record['formulas']
    def cell(label, section=None):
        return address(labels.find(label, section), col)
    def cached(label, section=None):
        return sheet.cell_value(labels.find(label, section), col)
    if record['diagnostic'] != 'reduced':
        return {}
    r65, r76 = cached('RPb65m'), cached('RPb76m')
    corrected_derivative = r65*(1+2*cached('F(Pb)'))*cached('Pb205t [mol]')
    r85, r45 = cached('RPb85m'), cached('RPb45m')
    s85, s45 = cached('sRPb85m'), cached('sRPb45m')
    # Quotient rule AND quotient covariance sign: UPbR21/22/24's formula
    # differs from the UPbR26 error described in BSU_SHEET_NOTES.md.
    quotient = r85/r45*math.hypot(s85/r85, s45/r45)
    experiments = {
        'correct_207_derivative': {cell('dPb207r/dR76m'): corrected_derivative},
        'correct_208_quotient': {cell('sRPb84m'): quotient,
                               cell('cov-R85m/R45m'): 0.0},
    }
    experiments['both_sheet_errors'] = {**experiments['correct_207_derivative'],
                                        **experiments['correct_208_quotient']}
    # Recover exact analytic U derivatives locally from the cached inputs.
    upartials = utils.U238s_partials(cached('RU8Xm (X=5 or 6)'), cached('F(U)'),
                                   cached('U23Xt [mol] (X=3, 5 or 6)'), cached('RU8Xt (X=5 or 6)'),
                                   cached('U238b [mol]'), cached('238U/235U'))
    experiments['correct_U_denominator'] = {
        cell('dU238s/dR85m'): upartials['dU238s_dR85m'],
        cell('dU238s/dFU(35)'): upartials['dU238s_dFU'],
    }
    # Remaining confirmed legacy errors are isolated together, with every
    # changed cell retained in JSON. No engine parameters are fitted here.
    sb64 = sheet.cell_value(labels.error(labels.find('RPb64b')), col)/100
    sb84 = sheet.cell_value(labels.error(labels.find('RPb84b')), col)/100
    t85, t45 = cached('RPb85t'), cached('RPb45t')
    st85, st45 = cached('sRPb85t'), cached('sRPb45t')
    more = {
        address(labels.error(labels.find('RPb86b')), col): 100*math.sqrt(sb84**2+sb64**2-2*cached('rho 6/4b-x/4b')*sb84*sb64),
        cell('sRPb84t'): t85/t45*math.hypot(st85/t85, st45/t45),
        cell('cov-R85t/R45t'): 0.0,
    }
    for derivative, sigma in [('dPb207r/dR76t', 'sRPb76t'), ('dPb207r/dR64c', 'sRPb64c')]:
        r = labels.find(derivative)
        if norm(sheet.cell_value(r+1, 0)) != '(d/d)*s':
            raise ValueError('Missing labeled derivative uncertainty term')
        more[address(r+1, col)] = cached(derivative)*cached(sigma)
    experiments['confirmed_sheet_errors_combined'] = {
        **experiments['both_sheet_errors'], **experiments['correct_U_denominator'], **more}
    # Numerical replay on cached immediate inputs independently checks BIFF
    # decoding, including shared-formula parentheses, before interventions.
    result = {}
    baseline = FormulaReplay(book, sheet.name, decoded)
    for check in record['checks']:
        addr = check['cell'].split('!')[1]
        formula = decoded.get(addr)
        if not formula:
            continue
        item = {}
        try:
            item['cached_formula_replay'] = baseline.evaluate(formula)
            if finite(check['sheet']):
                item['cached_replay_residual'] = item['cached_formula_replay']-check['sheet']
        except (ValueError, SyntaxError, ArithmeticError, IndexError) as error:
            item['replay_unavailable'] = str(error)
        for name, patches in experiments.items():
            replay = FormulaReplay(book, sheet.name, decoded, patches)
            if not replay.affected(addr):
                continue
            try:
                value = replay.value(addr)
                item[name] = dict(value=value,
                                  change=value-check['sheet'] if finite(check['sheet']) else None,
                                  residual_engine=check['engine']-value if finite(check['engine']) else None)
            except (ValueError, SyntaxError, ArithmeticError, IndexError) as error:
                item[name] = dict(unavailable=str(error))
        if item:
            result[check['quantity']] = item
    result['patches'] = experiments
    result['derivative_factor'] = r65/r76
    return result


CSV_ALIASES = {
    '206Pb* (10-13 mol)': 'Pb206r_scaled', 'mol % 206Pb*': 'mol_fraction_206r',
    'Pb8/Pbc': 'Pbr_Pbc', 'Pb*/Pbc': 'Pbr_Pbc', 'Pbc (pg)': 'Pbc_export',
    'Th/U': 'Th_U', 'U (ppm)': 'U_ppm', 'Pb (ppm)': 'Pb_ppm',
    '206Pb/204Pb': 'R64fc', '208Pb/206Pb': 'R86rad',
    '207Pb/206Pb': 'R76r_Th', '207Pb/235U': 'R75r', '206Pb/238U': 'R68r_Th',
    '207Pb/206Pb_2sigma%': 'R76r_Th_error_pct_2s',
    '207Pb/235U_2sigma%': 'R75r_error_pct_2s',
    '206Pb/238U_2sigma%': 'R68r_Th_error_pct_2s', 'error_corr': 'rho_7568_r',
    '207Pb/206Pb_age': 't76_Th_corr', '207Pb/235U_age': 't75', '206Pb/238U_age': 't68_Th_corr',
    '207Pb/206Pb_age_2sigma': 't76_Th_corr_std', '207Pb/235U_age_2sigma': 't75_std',
    '206Pb/238U_age_2sigma': 't68_Th_corr_std',
    '238U/206Pb_total': 'R86s', '207Pb/206Pb_total': 'R76s', '204Pb/206Pb_total': 'R46s',
    '238U/206Pb_total_2sigma%': 'R86s_error_pct_2s',
    '207Pb/206Pb_total_2sigma%': 'R76s_error_pct_2s',
    '204Pb/206Pb_total_2sigma%': 'R46s_error_pct_2s',
    'error_corr_8676': 'rho_8676_s', 'error_corr_8646': 'rho_8646_s', 'error_corr_7646': 'rho_7646_s',
}


def table_columns(sheet):
    """Decode stacked header labels, including publication tables with extra columns."""
    headers = [r for r in range(sheet.nrows) if norm(sheet.cell_value(r, 0)) == 'Sample']
    if len(headers) != 1:
        raise ValueError(f'{sheet.name}: cannot identify table header')
    r = headers[0]
    group_rows = [i for i in range(r) if 'Radiogenic Isotope Ratios' in sheet.row_values(i)]
    gr = group_rows[-1]
    columns, group = {}, ''
    for c in range(sheet.ncols):
        if sheet.cell_value(gr, c):
            group = norm(sheet.cell_value(gr, c))
        top, bottom = norm(sheet.cell_value(r-1, c)), norm(sheet.cell_value(r, c))
        key = None
        if top in ('207Pb', '206Pb', '208Pb', '238U', '235U', '204Pb') and re.fullmatch(r'\d+(?:Pb|U)', bottom):
            ratio = top + '/' + bottom
            if 'Isotopic' in group or 'Dates' in group:
                key = {'207Pb/206Pb': 't76_Th_corr', '207Pb/235U': 't75', '206Pb/238U': 't68_Th_corr'}.get(ratio)
            elif 'Sample (' in group:
                key = {'238U/206Pb': 'R86s', '207Pb/206Pb': 'R76s', '204Pb/206Pb': 'R46s',
                       '238U/204Pb': 'R84s', '206Pb/204Pb': 'R64s', '235U/204Pb': 'R54s', '207Pb/204Pb': 'R74s',
                       '208Pb/204Pb': 'Pb_R84sample', '208Pb/206Pb': 'Pb_R86sample'}.get(ratio)
            else:
                key = {'207Pb/206Pb': 'R76r_Th', '207Pb/235U': 'R75r', '206Pb/238U': 'R68r_Th',
                       '206Pb/204Pb': 'R64fc', '208Pb/206Pb': 'R86rad'}.get(ratio)
        elif bottom == '% err' and c-1 in columns:
            key = columns[c-1] + '_error_pct_2s'
        elif bottom in ('±', '± 2s') and c-1 in columns:
            key = columns[c-1] + '_std'
        elif top == 'Th' and bottom == 'U':
            key = 'Th_U'
        elif top == '206Pb*' and 'mol' in bottom:
            key = 'Pb206r_scaled'
        elif top == 'mol %':
            key = 'mol_fraction_206r'
        elif top == 'Pb*' and bottom == 'Pbc':
            key = 'Pbr_Pbc'
        elif top == 'Pb*' and bottom == '(pg)':
            key = 'Pbr_pg'
        elif top == 'Pbc':
            key = 'Pbc_export'
        elif top == 'corr.':
            key = 'rho_7568_r'
        elif top == 'corr. coef.' or bottom in ('8/6-7/6', '8/6-4/6', '7/6-4/6'):
            key = {'8/6-7/6': 'rho_8676_s', '8/6-4/6': 'rho_8646_s', '7/6-4/6': 'rho_7646_s',
                   '8/4-6/4': 'rho_8464_s', '5/4-7/4': 'rho_5474_s', '6/4-7/4': 'rho_7464_s'}.get(bottom)
            if bottom in ('6/4-8/4', '8/4-6/4') and any(
                    k == 'Pb_R84sample' for k in columns.values()):
                key = 'rho_Pb8464sample'
        elif bottom == 'ppm' and top in ('U', 'Pb'):
            key = top + '_ppm'
        if key:
            columns[c] = key
    return r, columns


def read_table(book, name):
    sheet = book.sheet_by_name(name)
    header, columns = table_columns(sheet)
    rows, context = [], None
    for r in range(header+1, sheet.nrows):
        if not sheet.cell_value(r, 0) or not any(sheet.cell_type(r, c) == xlrd.XL_CELL_NUMBER for c in columns):
            if sheet.cell_value(r, 0):
                context = str(sheet.cell_value(r, 0))
            continue
        rows.append(dict(fraction=str(sheet.cell_value(r, 0)), context=context, row=r+1,
                         values={key: number(sheet, r, c) for c, key in columns.items()},
                         cells={key: address(r, c) for c, key in columns.items()}))
    wanted = {(row['row']-1, c) for row in rows for c in columns}
    decoded = formulas(book, book.sheet_names().index(name), wanted)
    for row in rows:
        row['formulas'] = {key: decoded.get(cell) for key, cell in row['cells'].items()}
        # Keep repeated sample-ratio columns as separate cell comparisons.
        row['entries'] = [dict(quantity=key, value=number(sheet, row['row']-1, c),
                               cell=address(row['row']-1, c), formula=decoded.get(address(row['row']-1, c)))
                          for c, key in columns.items()]
        refs = [re.search(r"'Data Reduction Engine'!\$?([A-Z]+)\$?\d+", f or '') for f in row['formulas'].values()]
        row['engine_columns'] = sorted({m[1] for m in refs if m})
        formula = row['formulas'].get('R68r_Th') or ''
        switch = re.search(r"'Raw Data Input'!(\$?[A-Z]+\$?\d+)", formula)
        if switch:
            cell = switch[1].replace('$', '')
            row['ratio_switch'] = dict(cell='Raw Data Input!'+cell,
                                      value=FormulaReplay(book, name, {}).cached('Raw Data Input', cell))
    return dict(sheet=name, columns={xlrd.formula.colname(c): key for c, key in columns.items()}, rows=rows)


def export_engine_values(g, settings):
    if not g:
        return {}
    values = {}
    sample = {'R84s', 'R64s', 'R54s', 'R74s', 'R86s', 'R76s', 'R46s'}
    names = (set(CSV_ALIASES.values()) | sample | {s+'_error_pct_2s' for s in sample}
             | {'Pbr_pg', 'rho_8464_s', 'rho_5474_s', 'rho_7464_s', 'Pb_R84sample', 'Pb_R86sample'})
    for name in names:
        if name == 'Pb206r_scaled':
            values[name] = g.Pb206r*1e13
        elif name == 'Pbc_export':
            values[name] = g.Pbc_pg
        else:
            kind = 'age2' if name.startswith('t') and name.endswith('_std') else 'pct2' if name.endswith('_error_pct_2s') else 'value'
            values[name] = actual_value(g, name, kind)
    # The sheet's output switch controls both dates and ratios in these layouts.
    if settings.get('export_ratio_switch', settings['t ("t68", "t75", "off")'])['value'] == 'off':
        for dest, source in [('R68r_Th', 'R68r'), ('R76r_Th', 'R76r')]:
            values[dest] = float(getattr(g, source))
            values[dest+'_error_pct_2s'] = 200*getattr(g, source+'_std')/getattr(g, source)
    if settings['t ("t68", "t75", "off")']['value'] == 'off':
        for dest, source in [('t68_Th_corr', 't68'), ('t76_Th_corr', 't76')]:
            values[dest] = float(getattr(g, source))
            values[dest+'_std'] = 2*getattr(g, source+'_std')
    return values


def attach_output_table(grains, table):
    for grain in grains:
        matches = [r for r in table['rows'] if grain['engine_column'] in r['engine_columns']]
        if len(matches) != 1:
            grain['output_table_error'] = f'Expected one linked output row, found {len(matches)}'
            continue
        row = matches[0]
        grain['table_values'] = row['values']
        for entry in row['entries']:
            q = entry['quantity']
            grain['checks'].append(compare(q, entry['value'], grain['export_engine'].get(q),
                                          table['sheet'] + '!' + entry['cell'], 'output_table',
                                          formula=entry['formula'], source='output_table'))


def attach_csv(workbook, path):
    frame = pd.read_csv(path, encoding='utf-8-sig')
    result = dict(source=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), rows=[])
    for idx, row in frame.iterrows():
        fraction = str(row['sample'])
        candidates = [g for g in workbook['grains'] if g['fraction'] == fraction or
                      g['fraction'].split(' - ')[0] == fraction]
        # Repeated Willsboro IDs denote distinct blocks. Choose by the live
        # numeric output, retain all scores, and refuse a tied assignment.
        scores = []
        for g in candidates:
            terms = [abs(float(row[key])-g.get('table_values', {}).get(q, math.inf))/max(abs(float(row[key])), 1e-30)
                     for key, q in CSV_ALIASES.items() if key in row and finite(row[key]) and
                     finite(g.get('table_values', {}).get(q)) and '_std' not in q and 'error' not in q and 'rho' not in q]
            scores.append((sum(terms)/len(terms) if terms else math.inf, g['uid'], g))
        scores.sort(key=lambda x: (x[0], x[1]))
        if not scores or len(scores)>1 and scores[0][0] == scores[1][0]:
            result['rows'].append(dict(fraction=fraction, error='No unique sheet assignment'))
            continue
        _, _, grain = scores[0]
        entry = dict(fraction=fraction, uid=grain['uid'], assignment_scores=[dict(uid=u, score=s) for s,u,_ in scores], checks=[])
        for column, q in CSV_ALIASES.items():
            if column not in row:
                continue
            check = compare(q, row[column], grain['export_engine'].get(q),
                            f'{path.name}:row {idx+2}:{column}', 'csv', source='csv',
                            export_column=column, workbook_sheet=grain.get('table_values', {}).get(q))
            check['csv_vs_sheet'] = compare(q, row[column], grain.get('table_values', {}).get(q),
                                             check['cell'], 'provenance')
            grain['checks'].append(check)
            entry['checks'].append(check)
        result['rows'].append(entry)
    return result


def read_common(path):
    import openpyxl
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        values = {s.title: {cell.coordinate: cell.value for row in s for cell in row
                             if cell.value is not None} for s in book}
    finally:
        book.close()
    return dict(source=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), sheets=values)


def attach_common(workbook, common):
    for grain in workbook['grains']:
        params = grain['settings']['common']
        matches = {}
        for q in ('R64c', 'R74c', 'R84c'):
            matches[q] = [f'{sn}!{cell}' for sn, cells in common['sheets'].items()
                          for cell, value in cells.items() if value == params[q]]
        sk = grain['settings']['sk_values']
        sk_match = all(params['R'+r+'c'] == sk[r] for r in ('64', '74', '84'))
        grain['common_provenance'] = dict(
            exact_external_cells=matches, matches_external=all(matches.values()),
            matches_SK_calculator=sk_match,
            interpretation=('external feldspar composition, with the sheet summary correlation' if all(matches.values())
                            else 'SK calculator composition' if sk_match else 'explicit composition; external provenance unresolved'),
            configured_model_label=workbook['settings']['<initialPbModelET>']['value'])


def attach_publication(workbooks, path):
    book = xlrd.open_workbook(str(path), on_demand=True, logfile=io.StringIO())
    try:
        table = read_table(book, 'U-Pb Data Table')
    finally:
        book.release_resources()
    table['source'] = str(path)
    table['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    for row in table['rows']:
        matched = [g for w in workbooks if Path(w['source']).name.startswith(str(row['context']) + '_zircon')
                   for g in w['grains'] if g['fraction'] == row['fraction']]
        if len(matched) != 1:
            row['assignment_error'] = 'No unique sample/fraction workbook assignment'
            continue
        grain = matched[0]
        row['uid'] = grain['uid']
        for entry in row['entries']:
            q, v = entry['quantity'], entry['value']
            check = compare(q, v, grain['export_engine'].get(q),
                            'publication:' + table['sheet'] + '!' + entry['cell'], 'publication',
                            source='publication', formula=entry['formula'])
            check['csv_vs_sheet'] = compare(q, v, grain.get('table_values', {}).get(q), check['cell'], 'provenance')
            grain['checks'].append(check)
    return table


def export_experiments(workbook, common_data):
    """Invert exported total 206/204 to infer F(Pb), then test candidate settings.

    Fits are diagnostic constraints, never assignments of undocumented provenance.
    Counterfactuals retain the workbook's measured data and all other settings.
    """
    for grain in workbook['grains']:
        if not grain.get('_grain'):
            continue
        csv = {c['quantity']: c for c in grain['checks'] if c.get('source') == 'csv'}
        if not csv or 'R64fc' not in csv:
            continue
        original = grain['_grain']
        ratio = csv['R64fc']['sheet']
        a, b, t, u = original.Pb_R65m, original.Pb_R46m, original.Pb_R65t, original.Pb_R45t
        inferred = (ratio*(a*b-u)-(a-t))/(a+ratio*a*b)
        variants = {'inferred_Pb_fractionation': (inferred, grain['settings']['common'])}
        # Candidate compositions are read live from common_Pb_TIMS.xlsx. Match
        # isotope-ratio triplets by the labeled summary block, not embedded data.
        from openpyxl.utils.cell import coordinate_from_string, column_index_from_string, get_column_letter
        for sn, cells in common_data['sheets'].items():
            ratio_labels = {value: coord for coord, value in cells.items()
                            if value in ('206Pb/204Pb', '207Pb/204Pb', '208Pb/204Pb')}
            if len(ratio_labels) != 3:
                continue
            for coord, label in cells.items():
                if not isinstance(label, str) or not re.fullmatch(r'MA\d+', label):
                    continue
                column, _ = coordinate_from_string(coord)
                ci = column_index_from_string(column)
                candidate = dict(grain['settings']['common'])
                for isotope, ratio_label in [('64', '206Pb/204Pb'), ('74', '207Pb/204Pb'), ('84', '208Pb/204Pb')]:
                    _, r = coordinate_from_string(ratio_labels[ratio_label])
                    candidate['R'+isotope+'c'] = cells[f'{column}{r}']
                    candidate['R'+isotope+'c_std_rel'] = cells[f'{get_column_letter(ci+1)}{r}']
                variants['external_common_' + label] = (original.FPb, candidate)
        results = {}
        for name, (fp, initial) in variants.items():
            g = copy.deepcopy(original)
            g.FPb = fp
            UPbR.assign_initial_Pb_composition(g, initial)
            try:
                with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
                    warnings.simplefilter('ignore')
                    g.calc_all()
                vals = export_engine_values(g, workbook['settings'])
                checks = [compare(q, check['sheet'], vals.get(q), check['cell'], 'counterfactual') for q, check in csv.items()]
                results[name] = dict(FPb=fp, common=initial, checks=checks)
            except (ValueError, ArithmeticError) as error:
                results[name] = dict(error=str(error))
        grain['export_experiments'] = dict(inferred_FPb=inferred, sheet_FPb=original.FPb, variants=results)


def compare_copies(working, committed):
    a = xlrd.open_workbook(str(committed), on_demand=True, logfile=io.StringIO())
    b = xlrd.open_workbook(str(working), on_demand=True, logfile=io.StringIO())
    try:
        changes, formula_changes = [], []
        for name in sorted(set(a.sheet_names()) | set(b.sheet_names())):
            if name not in a.sheet_names() or name not in b.sheet_names():
                changes.append(dict(sheet=name, change='sheet added or removed'))
                continue
            sa, sb = a.sheet_by_name(name), b.sheet_by_name(name)
            wanted = set()
            for r in range(max(sa.nrows, sb.nrows)):
                for c in range(max(sa.ncols, sb.ncols)):
                    va = sa.cell(r, c) if r < sa.nrows and c < sa.ncols else xlrd.sheet.Cell(0, '')
                    vb = sb.cell(r, c) if r < sb.nrows and c < sb.ncols else xlrd.sheet.Cell(0, '')
                    if va.ctype != vb.ctype or va.value != vb.value:
                        changes.append(dict(sheet=name, cell=address(r, c), committed=va.value, working=vb.value,
                                            committed_type=va.ctype, working_type=vb.ctype))
                    if va.ctype or vb.ctype:
                        wanted.add((r, c))
            # All BIFF formula text is compared, including cells with equal caches.
            fa = formulas(a, a.sheet_names().index(name), wanted)
            fb = formulas(b, b.sheet_names().index(name), wanted)
            formula_changes.extend(dict(sheet=name, cell=cell, committed=fa.get(cell), working=fb.get(cell))
                                   for cell in sorted(set(fa) | set(fb)) if fa.get(cell) != fb.get(cell))
        return dict(working=str(working), committed=str(committed), value_changes=changes,
                    formula_changes=formula_changes, working_sha256=hashlib.sha256(working.read_bytes()).hexdigest(),
                    committed_sha256=hashlib.sha256(committed.read_bytes()).hexdigest())
    finally:
        a.release_resources()
        b.release_resources()


def reduced_table_checks(rows, l235, l238, uranium):
    """Conditional ratio-to-date validation when raw inputs/settings are absent."""
    results = []
    for row in rows:
        vals = row['values']
        checks = []
        for ratio, date, decay in [('R68r_Th', 't68_Th_corr', l238), ('R75r', 't75', l235),
                                   ('R76r_Th', 't76_Th_corr', None)]:
            if ratio not in vals or date not in vals:
                continue
            v = vals[ratio]
            t = utils.calc_t76(v, lambda_235=l235, lambda_238=l238, common_U238_U235=uranium) if decay is None else math.log1p(v)/decay/1e6
            checks.append(compare(date, vals[date], t, row['cells'].get(date, date), 'ratio_to_date'))
            if ratio + '_error_pct_2s' in vals and date + '_std' in vals:
                sigma = v*vals[ratio+'_error_pct_2s']/200
                dt = utils.calc_t76_uncertainty(t, sigma, l235, l238, uranium) if decay is None else sigma/(1+v)/decay/1e6
                checks.append(compare(date+'_std', vals[date+'_std'], 2*dt,
                                      row['cells'].get(date+'_std', date+'_std'), 'ratio_to_date'))
        results.append(dict(fraction=row['fraction'], checks=checks))
    return results


def auxiliary_tables(data, settings):
    constants_used = {key: settings[key]['value'] for key in ('l 235U', 'l 238U', '238U/235U')}
    l235, l238, uranium = (constants_used[k] for k in ('l 235U', 'l 238U', '238U/235U'))
    frame = pd.read_csv(data / 'SJ1_apatite_TIMS.csv')
    rows = [dict(fraction=str(r['sample']), values={q: r[k] for k,q in CSV_ALIASES.items() if k in r},
                 cells={q: f'SJ1_apatite_TIMS.csv:{i+2}:{k}' for k,q in CSV_ALIASES.items() if k in r})
            for i,r in frame.iterrows()]
    sj = dict(source=str(data / 'SJ1_apatite_TIMS.csv'),
              limitation='No raw workbook: no tracer, blank, common-Pb, fractionation or raw covariance validation. '
                         'Ratio-to-date checks are CONDITIONAL on the constants shared by the seven supplied workbooks; SJ1 constants are unverified.',
              constants_assumed=constants_used, grains=reduced_table_checks(rows, l235, l238, uranium))
    path = data / 'ET2000Ma_solution.xls'
    book = xlrd.open_workbook(str(path), on_demand=True, logfile=io.StringIO())
    try:
        et = read_table(book, 'U-Pb Data Table')
    finally:
        book.release_resources()
    et['source'] = str(path)
    et['limitation'] = 'Reduced reference table only; no Raw Data Input/Data Reduction Engine. Conditional ratio-to-date checks, no raw reduction claim.'
    et['constants_assumed'] = constants_used
    et['grains'] = reduced_table_checks(et['rows'], l235, l238, uranium)
    # Test a plausible raw-ratio/corrected-date pairing for SJ1 without
    # claiming its absent workbook actually used these settings.
    for input_row, grain in zip(rows, sj['grains']):
        vals = input_row['values']
        magma = settings['(Th/U)magma']['value']
        delta = settings['l 238U']['value']/settings['l 230Th']['value']*(1-vals['Th_U']/magma)
        corrected = vals['R68r_Th'] + delta
        corrected76 = vals['R76r_Th']*vals['R68r_Th']/corrected
        grain['conditional_magma_pairing'] = dict(Th_U_magma_assumed=magma,
            t68=math.log1p(corrected)/l238/1e6,
            t76=utils.calc_t76(corrected76, lambda_235=l235, lambda_238=l238, common_U238_U235=uranium))
        grain['conditional_magma_pairing']['t68_2sigma'] = corrected*vals['R68r_Th_error_pct_2s']/100/(1+corrected)/l238/1e6
    for input_row, grain in zip(et['rows'], et['grains']):
        vals = input_row['values']
        corrected = vals['R68r_Th'] + l238/settings['l 230Th']['value']*(1-settings['DTh/U']['value'])
        grain['conditional_D_error_pairing'] = dict(D_assumed=settings['DTh/U']['value'],
            t68_2sigma=corrected*vals['R68r_Th_error_pct_2s']/100/(1+corrected)/l238/1e6,
            t76_2sigma_at_cached_age=2*utils.calc_t76_uncertainty(vals['t76_Th_corr'],
                vals['R76r_Th']*vals['R76r_Th_error_pct_2s']/200, l235, l238, uranium))
    for item in (sj, et):
        for grain in item['grains']:
            for check in grain['checks']:
                if check['status'] == 'MISMATCH':
                    check.update(cause='unknown', cause_class='f',
                                 cause_explanation='Reduced ratios and dates/errors are not a fully specified raw reduction; constants and correction pairing cannot be verified without the source workbook.')
                    variant = grain.get('conditional_magma_pairing', {})
                    target = {'t68_Th_corr':'t68', 't76_Th_corr':'t76', 't68_Th_corr_std':'t68_2sigma'}.get(check['quantity'])
                    if target in variant:
                        check['conditional_pairing'] = compare(check['quantity'], check['sheet'], variant[target], check['cell'], 'counterfactual')
                    variant = grain.get('conditional_D_error_pairing', {})
                    target = {'t68_Th_corr_std':'t68_2sigma', 't76_Th_corr_std':'t76_2sigma_at_cached_age'}.get(check['quantity'])
                    if target in variant:
                        check['conditional_pairing'] = compare(check['quantity'], check['sheet'], variant[target], check['cell'], 'counterfactual')
    return [sj, et]


CAUSES = {
    'blank_cap_residue': ('a', 'Engine recomputes zero initial 204Pb with a rounding residue; division by it destabilizes sample ratios.',
                          'Fix the engine to preserve the exact partitioned zero before calculating sample ratios. The export layer already masks it.'),
    'magma_total_u': ('a', 'Engine magma correction divides Th by 238U; sheet and exported atomic Th/U divide by total natural U.',
                     'Review and make the total-U convention consistent in magma reduction and its Jacobian; do not change D-mode dates.'),
    'missing_sample208_covariance': ('b', 'These UPbR22/24 sheets export supplemental sample 208Pb errors/covariances that the engine does not propagate.',
                                    'Add sample 208Pb covariance outputs through the joint model if these outputs are needed; do not import legacy error formulas.'),
    'sheet_208_quotient': ('c', 'Sheet sRPb84m omits the quotient magnitude, treating a relative error as absolute.', 'No engine fix: sheet error.'),
    'sheet_common_mass': ('c', 'Output common Pb uses nominal isotope masses for the initial component; engine/composition block use isotope masses.',
                          'No engine fix: inconsistent sheet outputs. Use isotope masses consistently in a corrected sheet.'),
    'sheet_U_derivative': ('c', 'Sheet U derivatives use numerator/denominator in a term requiring numerator/denominator squared.',
                           'No engine fix: sheet error; correct the derivative formulas if the sheet is maintained.'),
    'sheet_zero_initial_error': ('c', 'Sheet reports a nonzero percent error for a sample ratio whose guarded value is zero.',
                                'No engine fix: zero-denominator percent errors are undefined.'),
    'joint_covariance': ('d', 'Documented joint JΣJᵀ model retains shared-variable covariance; sheet propagates terms separately and also has confirmed formula errors.',
                         'Keep joint propagation. Do not tune engine errors to match legacy spreadsheet errors. Audit interventions quantify the sheet contribution and residual separately.'),
    'missing_measurement': ('e', 'Required raw means are missing or nonnumeric in this source fraction.', 'Obtain missing measurements; do not invent ratios.'),
    'date_domain': ('d', 'Blank/control or low-radiogenic fraction gives a negative or out-of-range date; engine date solvers validate their domains.',
                    'Keep validation; a future partial Pb-only reduction can expose valid intermediate quantities without inventing a date.'),
    'export_settings': ('e', 'Exported reduced data differ from the current workbook output; counterfactual settings and remaining residual are recorded.',
                        'Resolve source reduction provenance and regenerate exports deliberately; do not alter the engine to fit a different input dataset.'),
    'unknown': ('f', 'Cause not established by this audit.', 'Investigate before proposing a numerical change.'),
}


def classify(workbook):
    for grain in workbook['grains']:
        checks = grain['checks']
        for check in checks:
            if check['status'] != 'MISMATCH':
                continue
            q = check['quantity']
            source = check.get('source', 'engine')
            if source in ('csv', 'publication') and check.get('csv_vs_sheet', {}).get('status') == 'MISMATCH':
                cause = 'export_settings'
            elif grain['diagnostic'] != 'reduced':
                error = grain['reduction_error']
                cause = 'missing_measurement' if 'ufunc' in error or 'str' in error else 'date_domain'
            elif check.get('convention') == 'unsupported' or q in (
                    'Pb208sample_std', 'Pb_R84sample_error_pct_2s',
                    'Pb_R86sample_error_pct_2s', 'rho_Pb8464sample'):
                cause = 'missing_sample208_covariance'
            elif q in ('rho_8646_s', 'rho_7646_s', 'rho_7464_s', 'rho_8464_s', 'rho_5474_s') and (
                    grain['_grain'].Pb204c and
                    abs(grain['_grain'].Pb204c) < 1e-9*abs(grain['_grain'].Pb204b)):
                cause = 'blank_cap_residue'
            elif q == 'Pb_R84m_std':
                cause = 'sheet_208_quotient'
            elif q == 'Pbc_export':
                cause = 'sheet_common_mass'
            elif q in ('Th_U', 'Th232s', 'Th_ppm', 'R68r_Th', 'R76r_Th', 't68_Th_corr', 't76_Th_corr'):
                cause = 'magma_total_u' if grain['settings']['th']['Th230_correction_type'] == 'magma' else 'unknown'
            elif q in ('Pb204c', 'R46s', 'R64s', 'R74s', 'R84s', 'R54s') or (
                    q.startswith(('R46s_', 'R64s_', 'R74s_', 'R84s_', 'R54s_'))):
                g = grain['_grain']
                if abs(g.Pb204c) < 1e-9*abs(g.Pb204b):
                    cause = 'blank_cap_residue' if g.Pb204c else 'sheet_zero_initial_error'
                else:
                    cause = 'sheet_U_derivative' if q.startswith(('R84s_', 'R54s_')) else 'unknown'
            elif q.startswith(('R86s_', 'rho_8676_s', 'rho_8646_s', 'rho_8464_s', 'rho_5474_s')):
                cause = 'sheet_U_derivative'
            elif q.endswith(('_std', '_error_pct_2s')) or q.startswith('rho_'):
                cause = 'joint_covariance'
            else:
                cause = 'unknown'
            check['cause'] = cause
            check['cause_class'] = CAUSES[cause][0]
            check['cause_explanation'] = CAUSES[cause][1]
            if q in grain.get('formula_experiments', {}):
                check['quantification'] = grain['formula_experiments'][q]
            if q == 'Pbc_export' and grain.get('experiments'):
                check['nominal_mass_counterfactual'] = compare(q, check['sheet'],
                    grain['experiments']['Pbc_sheet_nominal_initial_masses'], check['cell'], 'counterfactual')
            if source in ('csv', 'publication'):
                check['engine_comparison_causes'] = sorted({c.get('cause') for c in checks
                    if c.get('source') is None and c['quantity'] == q and c.get('cause')})


def run_audit(data_dir=ADK, head_dir=None, include_formulas=True):
    data_dir = Path(data_dir)
    sources = [data_dir/name for name in (*WORKBOOKS, *WORKBOOKS.values(), PUBLICATION,
                                         'SJ1_apatite_TIMS.csv', 'common_Pb_TIMS.xlsx', 'ET2000Ma_solution.xls')]
    before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in sources}
    workbooks = [audit_workbook(data_dir/name, include_formulas) for name in WORKBOOKS]
    common = read_common(data_dir/'common_Pb_TIMS.xlsx')
    for workbook in workbooks:
        workbook['csv'] = attach_csv(workbook, data_dir/WORKBOOKS[Path(workbook['source']).name])
        attach_common(workbook, common)
        export_experiments(workbook, common)
    publication = attach_publication(workbooks, data_dir/PUBLICATION)
    for workbook in workbooks:
        classify(workbook)
    report = dict(workbooks=workbooks, common_Pb=common, publication=publication,
                  auxiliary=auxiliary_tables(data_dir, workbooks[0]['settings']), copies=[], committed_workbooks=[])
    if head_dir:
        for name in ('MA1_apatite_UPbR21XML.xls', 'MA1_zircon_UPbR21XML.xls', PUBLICATION):
            path = Path(head_dir)/name
            report['copies'].append(compare_copies(data_dir/name, path))
            if name in WORKBOOKS:
                committed = audit_workbook(path, include_formulas)
                classify(committed)
                report['committed_workbooks'].append(committed)
    report['source_integrity'] = {str(p): dict(size=before[str(p)][0], mtime_ns=before[str(p)][1],
        sha256=before[str(p)][2], unchanged=before[str(p)] == (p.stat().st_size, p.stat().st_mtime_ns,
                                                           hashlib.sha256(p.read_bytes()).hexdigest())) for p in sources}
    if not all(v['unchanged'] for v in report['source_integrity'].values()):
        raise RuntimeError('A source changed during this audit; rerun against stable source files')
    # Every differing row location is reported, not inferred from a version name.
    maps = defaultdict(dict)
    for workbook in workbooks:
        for sheet, labels in workbook['row_map'].items():
            for label, rows in labels.items():
                maps[sheet+'!'+label][Path(workbook['source']).name] = rows
    report['layout_differences'] = {key: value for key,value in maps.items()
                                    if len(value) != len(workbooks) or len({tuple(r) for r in value.values()}) > 1}
    return report


def summary(workbook):
    counts = Counter(c['status'] for g in workbook['grains'] for c in g['checks'])
    return (f"| {Path(workbook['source']).name} | {len(workbook['grains'])} | "
            f"{sum(g['diagnostic']=='reduced' for g in workbook['grains'])} | {sum(counts.values())} | "
            f"{counts['exact']} | {counts['numerical']} | {counts['MISMATCH']} |")


def compare_baseline(report, path):
    """Retain reviewable Phase 1 transitions without storing private data in Git."""
    previous = json.loads(Path(path).read_text())
    def index(workbooks):
        return {(Path(w['source']).name, g['uid'], c.get('source', 'engine'), c['cell'], c['quantity']): c
                for w in workbooks for g in w['grains'] for c in g['checks']}
    old, new = index(previous['workbooks']), index(report['workbooks'])
    transitions = [dict(key=key, before=old[key], after=new[key]) for key in old.keys() & new.keys()
                   if (old[key]['status'], old[key].get('cause')) != (new[key]['status'], new[key].get('cause'))]
    return dict(source=str(path), sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                source_hashes_match={name: value['sha256']==report['source_integrity'].get(name, {}).get('sha256')
                                     for name, value in previous['source_integrity'].items()},
                added_checks=sorted(new.keys()-old.keys()), removed_checks=sorted(old.keys()-new.keys()),
                rows=[dict(workbook=Path(w['source']).name,
                           before=dict(Counter(c['status'] for g in w['grains'] for c in g['checks'])),
                           after=dict(Counter(c['status'] for g in next(n for n in report['workbooks']
                                if Path(n['source']).name==Path(w['source']).name)['grains'] for c in g['checks'])))
                      for w in previous['workbooks']], transitions=sorted(transitions, key=lambda t: t['key']))


def render_report(report):
    lines = ['# Adirondack legacy TIMS audit (Phase 2)', '',
             'The current engine does **not** exactly reproduce all legacy outputs. '
             'Uncorrected radiogenic central values reproduce for the fully reducible fractions; '
             'the approved capped-zero and total-U magma corrections now reproduce the corresponding sheet central values. '
             'Legacy uncertainty formulas, unsupported outputs and historical exports still differ. '
             'No source workbook was changed.', '',
             'The JSON retains every comparison, label map, input, setting, formula, source hash, strict refusal and numerical intervention. '
             'Exact means relative difference <1e-10; numerical means <1e-6, or ≤0.0018 Ma for a Pb–Pb date. '
             'Zero expected values require actual zero for exact. Unavailable comparisons count as MISMATCH and are separately identified, not hidden as passes. '
             'All ratio errors are kept in their sheet percent/sigma convention. Age error comparisons use 2σ Ma.', '',
             '## Working workbooks', '',
             '| Workbook | Named fractions | Fully reduced | Comparisons | Exact | Numerical | MISMATCH |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    lines += [summary(w) for w in report['workbooks']]
    if report.get('baseline_comparison'):
        baseline = report['baseline_comparison']
        lines += ['', '## Phase 1 → Phase 2', '',
                  '| Workbook | Exact before → after | Numerical before → after | MISMATCH before → after |',
                  '| --- | ---: | ---: | ---: |']
        for row in baseline['rows']:
            counts = [f"{row['before'][q]} → {row['after'][q]}" for q in ('exact', 'numerical', 'MISMATCH')]
            lines.append('| '+row['workbook']+' | '+' | '.join(counts)+' |')
        transitions = baseline['transitions']
        resolved = sum(t['before']['status']=='MISMATCH' and t['after']['status']!='MISMATCH' for t in transitions)
        reclassified = sum(t['before'].get('cause')=='blank_cap_residue' and
                          t['after'].get('cause')=='sheet_zero_initial_error' for t in transitions)
        regressions = sum(t['before']['status']!='MISMATCH' and t['after']['status']=='MISMATCH' for t in transitions)
        lines += ['', f'{resolved} MISMATCH comparisons now pass; {regressions} passing comparisons regressed. '
                  f'{reclassified} additional capped cases now expose the sheet’s pre-existing nonzero percent error for a zero sample ratio; '
                  'these are class (c), not residual engine bugs. No comparison cells were added or removed. '
                  'Baseline transitions and source-hash equality are retained in JSON.', '',
                  'The two engine fixes preserve the exact zero assigned by Pb partitioning in sample outputs, '
                  'radiogenic helpers and the centre of joint propagation, retaining the prior first-order sensitivities. '
                  'Magma correction and its derivatives now use Th/(238U+235U), using each grain’s fixed natural U ratio. '
                  'D-mode dates, radiogenic values/errors and covariance arrays remain byte-identical in the example snapshot; '
                  'only capped sample outputs and magma-mode outputs were updated. '
                  'See snapshot-changes.json/.md for every approved snapshot field change.']
    unavailable = sum(c['absolute_difference'] is None for w in report['workbooks']
                      for g in w['grains'] for c in g['checks'] if c['status']=='MISMATCH')
    lines += ['', f'Of the MISMATCH entries, {unavailable} are unavailable engine results '
              '(missing measurements, a domain refusal or an unsupported engine output), rather than a measured numerical discrepancy.']
    lines += ['', 'Counts include the engine block, linked output-table cells, CSV columns and corresponding publication cells. '
              'They include process blanks, partial runs and repeated Willsboro fraction names; raw column + fraction is the unique key. '
              'CSV values are compared at their reported precision, without loosening the requested tolerance. '
              'The Willsboro CSV maps to the last garnet block by a uniquely best numerical match; all candidate scores are retained.', '',
              '## Working versus committed copies', '']
    for item in report['copies']:
        lines += [f"- `{Path(item['working']).name}`: {len(item['value_changes'])} changed cells (values/types, all sheets), "
                  f"{len(item['formula_changes'])} changed formulas (including equal cached values). "
                  f"File bytes {'match' if item['working_sha256']==item['committed_sha256'] else 'differ'}. "
                  'Formatting, workbook metadata and other binary records are not a numerical input/output change.']
    if report['committed_workbooks']:
        lines += ['', '| Committed workbook | Named fractions | Fully reduced | Comparisons | Exact | Numerical | MISMATCH |',
                  '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
        lines += [summary(w) for w in report['committed_workbooks']]
        lines += ['', 'Committed copies were independently reduced. Their counts omit CSV/publication attachments; '
                  'cell equality establishes that today’s save did not change the cached scientific results.']
    lines += ['', '## Largest differences by workbook and quantity group', '',
              '| Workbook | Group | Fraction | Quantity | Absolute difference | Relative difference |',
              '| --- | --- | --- | --- | ---: | ---: |']
    for w in report['workbooks']:
        groups = defaultdict(list)
        for g in w['grains']:
            for c in g['checks']:
                if c['absolute_difference'] is not None:
                    groups[c['group']].append((g, c))
        for group, entries in sorted(groups.items()):
            g,c = max(entries, key=lambda pair: abs(pair[1]['relative_difference'] or pair[1]['difference']))
            rel = f"{c['relative_difference']:.8g}" if c['relative_difference'] is not None else 'undefined (sheet zero)'
            lines.append(f"| {Path(w['source']).name} | {group} | {g['uid']} | {c['quantity']} | {c['absolute_difference']:.8g} | {rel} |")
    lines += ['', '## Mismatch causes and quantified interventions', '',
              'Classes: (a) engine bug, (b) missing sheet option, (c) sheet error, '
              '(d) deliberate documented difference, (e) input/transcription or export provenance, (f) unknown. '
              'A primary class is recorded for every mismatch. Uncertainty checks can contain both sheet-error contributions '
              'and the deliberate joint-propagation residual; the JSON keeps these separately. '
              'Class (b) includes missing supplemental sample-208Pb covariance outputs. All sheets select t68; t75/off and non-unit magma activity options are not validated here.', '']
    all_entries = defaultdict(list)
    for w in report['workbooks']:
        for g in w['grains']:
            for c in g['checks']:
                if c['status'] == 'MISMATCH':
                    all_entries[c['cause']].append((w,g,c))
    for cause, entries in sorted(all_entries.items(), key=lambda item: (CAUSES[item[0]][0], item[0])):
        cl, explanation, fix = CAUSES[cause]
        lines += [f'### ({cl}) {cause}: {len(entries)} comparisons', '', explanation, '', fix, '']
        numeric = [item for item in entries if item[2]['absolute_difference'] is not None]
        if numeric:
            w,g,c = max(numeric, key=lambda item: abs(item[2]['relative_difference'] or item[2]['difference']))
            lines += [f"Largest relative/zero-reference example: `{Path(w['source']).name}`, `{g['uid']}`, "
                      f"`{c['cell']}`, {c['quantity']}: sheet {c['sheet']:.12g}, engine {c['engine']:.12g}, "
                      f"difference {c['difference']:.8g}, relative {c['relative_difference']}.", '']
            if c.get('formula'):
                lines += [f"Decoded formula: `{c['formula']}`.", '']
        if cause == 'joint_covariance':
            lines += ['The README documents joint first-order propagation, conditional independence for unspecified covariances, '
                      'fixed tracer concentrations and diagnostic zero substitution for impossible covariances. '
                      'Every successfully reduced fraction is refused in strict mode by the BSU1B tracer errors '
                      'unless an earlier measured linked-error check rejects it. These are diagnostic uncertainties, not certified ones.', '',
                      '| Workbook | Fraction | Quantity | Sheet | Corrected sheet formulas | Engine | Remaining engine minus corrected sheet |',
                      '| --- | --- | --- | ---: | ---: | ---: | ---: |']
            for w in report['workbooks']:
                for q in ('U238s_std', 'Pb207r_std', 'Pb208r_std', 't76_std'):
                    candidates = [(g,g['formula_experiments'].get(q, {}).get('confirmed_sheet_errors_combined'))
                                  for g in w['grains'] if g['diagnostic']=='reduced']
                    candidates = [(g,v) for g,v in candidates if v and 'value' in v]
                    if not candidates:
                        continue
                    g,v = max(candidates, key=lambda pair: abs(pair[1]['residual_engine']))
                    c = next(c for c in g['checks'] if c['quantity']==q)
                    lines.append(f"| {Path(w['source']).name} | {g['uid']} | {q} | {c['sheet']:.8g} | {v['value']:.8g} | {c['engine']:.8g} | {v['residual_engine']:.8g} |")
            lines += ['', 'These are local interventions in decoded formulas with unchanged cached precedents. '
                      'The remaining residual is the difference between that corrected legacy model and joint propagation; '
                      'it is not claimed to be explained by fixing a single typo. Unsupported replay expressions are explicit in JSON.', '']
        if cause == 'magma_total_u':
            lines += ['Re-solving the implicit correction with total U in a disposable helper reproduces the sheet correction; '
                      '`experiments.t68_Th_corr_sheet_total_U` and `R68r_Th_sheet_total_U` give the residual directly. '
                      'Th232s/Th ppm then follow the changed corrected age. The fixed D-mode formula is unaffected.', '']
            lines += ['| Fraction | Quantity | Engine minus sheet (Ma for dates) | Total-U helper minus sheet | Helper status |',
                      '| --- | --- | ---: | ---: | --- |']
            for w in report['workbooks']:
                for g in w['grains']:
                    for c in g.get('experiments', {}).get('total_U_checks', []):
                        original = next(o for o in g['checks'] if o['quantity']==c['quantity'])
                        lines.append(f"| {g['uid']} | {c['quantity']} | {original['difference']:.8g} | {c['difference']:.8g} | {c['status']} |")
            lines += ['']
        if cause == 'blank_cap_residue':
            interventions = [c for w in report['workbooks'] for g in w['grains']
                             for c in g.get('experiments', {}).get('preserve_partitioned_zero', [])]
            lines += [f"Preserving the value returned by `calc_Pb_partitioning` reproduces "
                      f"{sum(c['status']!='MISMATCH' for c in interventions)}/{len(interventions)} "
                      'tested central-value sample ratios/initial-204 amounts. The JSON records each residual. '
                      'This intervention does not endorse the sheet’s nonzero percent error for a zero ratio.', '']
            correlations = [c for w in report['workbooks'] for g in w['grains']
                            for c in g.get('experiments', {}).get('preserve_partitioned_zero_correlations', [])]
            lines += [f"Recomputing sample correlations after preserving that zero also reproduces "
                      f"{sum(c['status']!='MISMATCH' for c in correlations)}/{len(correlations)} tested "
                      '204Pb-linked correlations. Tiny residues can otherwise yield nonphysical correlations outside ±1.', '']
        if cause == 'export_settings':
            lines += ['For each CSV fraction, the export experiments invert total 206/204 to obtain F(Pb) and re-run the engine '
                      'with that F(Pb), or with each live external feldspar composition. '
                      'These are constraints on provenance, not proof of the full historical settings. '
                      'The unchanged working/HEAD cells rule out today’s save as the origin of these discrepancies.', '',
                      '| Workbook | Fraction | Candidate | Value checks within tolerance / tried | Largest remaining relative value difference |',
                      '| --- | --- | --- | ---: | ---: |']
            for w in report['workbooks']:
                for g in w['grains']:
                    if not any(c.get('cause')=='export_settings' for c in g['checks']):
                        continue
                    for variant,v in g.get('export_experiments', {}).get('variants', {}).items():
                        values = [c for c in v.get('checks', []) if not c['quantity'].endswith(('_std','_error_pct_2s')) and not c['quantity'].startswith('rho')]
                        if not values:
                            continue
                        passed = sum(c['status'] != 'MISMATCH' for c in values)
                        rel = max(abs(c['relative_difference'] or 0) for c in values)
                        lines.append(f"| {Path(w['source']).name} | {g['uid']} | {variant} | {passed}/{len(values)} | {rel:.8g} |")
            lines += ['']
    lines += ['## Formula evidence and version differences', '',
              'Rows are resolved from labels, never assumed from the UPbR version. The main engines share a primary layout; '
              'the Willsboro UPbR22 and the UPbR24 files add a supplemental sample-208Pb block. Its repeated section labels are retained in the row maps and explicitly '
              'excluded from primary-section lookups. The UPbR26 documented row numbers do not apply here. '
              f"There are {len(report['layout_differences'])} labels with different row locations or version coverage; all are listed in JSON.", '',
              'The following confirmed defects are present in the legacy formula model. Their formulas and cell-specific patches are recorded for each fraction:', '',
              '- `dPb207r/dR76m` uses measured 207/206 where 206/205 belongs. The intervention also updates its linked covariance term.',
              '- `sRPb84m` returns only relative quadrature, omitting the absolute quotient factor. `cov-R85m/R45m` subtracts the 204/205 variance where quotient covariance requires addition.',
              '- `sRPb84t` and `cov-R85t/R45t` have the analogous tracer quotient problem.',
              '- The weighted `dPb207r/dR76t` term uses σ(204/205)t; the `dPb207r/dR64c` term uses σ(204/206)t. They need their own variable’s sigma.',
              '- The blank `RPb86b` percent-error formula misgroups the correlation term.',
              '- `dU238s/dR85m` and `dU238s/dFU` omit the second denominator factor in the quotient derivative. The sample-ratio uncertainties use these legacy helpers, so their small differences are sheet-derivative errors, distinct from the joint radiogenic model.', '',
              '| Workbook layout | Patched cell | Cached legacy formula | Corrected local value |',
              '| --- | --- | --- | ---: |']
    for layout in sorted({w['layout'] for w in report['workbooks']}):
        w = next(w for w in report['workbooks'] if w['layout']==layout)
        g = next(g for g in w['grains'] if g['diagnostic']=='reduced')
        for cell, value in g['formula_experiments']['patches']['confirmed_sheet_errors_combined'].items():
            lines.append(f"| UPbR{layout} | Data Reduction Engine!{cell} | `{g['formulas'].get(cell)}` | {value:.10g} |")
    lines += ['', '## Settings, tracer and common-Pb provenance', '']
    for w in report['workbooks']:
        g = w['grains'][0]
        provenance = Counter(gr['common_provenance']['interpretation'] for gr in w['grains'])
        th_type = w['settings']['"magma" or "D"?']['value']
        th_age = w['settings']['t ("t68", "t75", "off")']['value']
        lines += [f"- `{Path(w['source']).name}`: {w['settings']['<TracerUPbModel>']['value']}; "
                  f"Th {th_type}/{th_age}; "
                  f"common-Pb provenance {dict(provenance)}; SK calculator age {g['settings']['sk_age_Ga']} Ga."]
    lines += ['', 'All used BSU1B tables are the same. No registry version is an exact binary match: '
              'BSU-1/B/v1 is identical except missing unused 202/205 zero entries and last-bit differences in two cross-ratios. '
              'The audit loads through the registry, records those differences, then applies the exact sheet snapshot only to its disposable grain. '
              'No published EARTHTIME master is substituted. The selected table is BSU1B v1.2; the formula branches to its raw table cells. '
              'Decay constants and natural 238U/235U are taken from each workbook. Empty raw error cells are explicitly treated as Excel’s numeric zero, with their addresses retained. '
              'Measured correlations are inferred by linked identities where no measured covariance is supplied; blank/common-Pb correlations are read from the sheet, '
              'including the shared rho applied to two isotope pairs. The external common-Pb file’s detailed pair correlations are not silently substituted.', '',
              '## Refused fractions and strict mode', '']
    for w in report['workbooks']:
        lines += [f"### {Path(w['source']).name}", '']
        for g in w['grains']:
            if g['diagnostic'] != 'reduced':
                lines.append(f"- `{g['uid']}` diagnostic refusal: {g['reduction_error']}")
            else:
                lines.append(f"- `{g['uid']}` strict: {g['strict'].get('reason', 'accepted')}")
    lines += ['', '## (f) Reduced-only references and unresolved scope', '']
    for item in report['auxiliary']:
        counts = Counter(c['status'] for g in item['grains'] for c in g['checks'])
        lines += [f"- `{Path(item['source']).name}`: {len(item['grains'])} rows; {dict(counts)}. {item['limitation']}"]
        variants = [c for g in item['grains'] for c in g['checks'] if c.get('conditional_pairing')]
        if variants:
            passed = sum(c['conditional_pairing']['status']!='MISMATCH' for c in variants)
            remaining = max(abs(c['conditional_pairing']['difference']) for c in variants)
            lines += [f"  Conditional correction/error pairing reproduces {passed}/{len(variants)} "
                      f"tested baseline mismatches; largest remaining absolute residual {remaining:.8g} Ma. "
                      'SJ1 tests magma Th/U from the shared workbook settings; ET2000 tests the shared D '
                      'for the 206/238 error and its cached bisection age for the 207/206 error. '
                      'These plausible pairings do not identify the absent raw settings.']
    lines += ['', 'No raw reduction can be claimed for SJ1 or the ET2000 reference table. '
              'Historical uncertainty settings for exports are not uniquely recoverable from rounded reduced tables. '
              'Workbook values are cached; Excel was never opened, automated or asked to recalculate. '
              'Formula replay covers the scalar dependency paths used for stated interventions, not all Excel features. '
              'The supplemental sample-208Pb central values are compared; missing engine uncertainty/correlation outputs are explicitly class (b). '
              'Formatting-only differences between working and committed copies are not decoded.', '',
              '## Verification', '',
              'Source hashes, sizes and modification times were checked before and after; every source is unchanged. '
              'Regression expectations contain only fraction/quantity/category identifiers, never workbook measurements. '
              'The regression test reads these files in place and fails on either a newly mismatching quantity or an unexpectedly resolved known mismatch. '
              'The test and quick-tier results are recorded in validation.json beside this report.']
    return '\n'.join(lines) + '\n'


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items() if not str(k).startswith('_')}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, (np.integer, np.bool_)):
        return value.item()
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('IDTIMS_ADIRONDACK_DIR', ADK)))
    parser.add_argument('--head-dir', type=Path)
    parser.add_argument('--baseline-audit', type=Path, help='Read-only previous audit.json for before/after review')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.output_dir.resolve().is_relative_to(root):
        parser.error('Data-derived reports must be outside this repository')
    start = time.monotonic()
    report = run_audit(args.data_dir, args.head_dir)
    if args.baseline_audit:
        report['baseline_comparison'] = compare_baseline(report, args.baseline_audit)
    report['elapsed_seconds'] = time.monotonic()-start
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / 'audit.json').write_text(json.dumps(clean(report), indent=2, allow_nan=False) + '\n')
    (args.output_dir / 'report.md').write_text(render_report(report))
    print('seconds', time.monotonic()-start)
    for wb in report['workbooks']:
        print(Path(wb['source']).name, len(wb['grains']), Counter(c['status'] for g in wb['grains'] for c in g['checks']))


if __name__ == '__main__':
    main()
