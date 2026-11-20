"""Rebuild the invented public fixtures; no private source files are read.

Run: .venv/bin/python tools/generate_synthetic_fixtures.py
Seed 20261120; ratios come from invented amounts and linked-ratio identities.
The 535 set retains Daly/Faraday collectors, capped/uncapped blanks,
diagnostic tracer covariance and a final-row linked-error failure.
The 2535 set caps common Pb and deliberately fails linked errors at z1/z6;
z2-z5 pass strict reduction. Snapshots use the package's own reduction code.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import random
import sys
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))
from IDTIMS_UPbRPy import UPbR, constants, utils
from IDTIMS_UPbRPy.settings import ReductionSettings
from IDTIMS_UPbRPy.export import bsu_table
from IDTIMS_UPbRPy.dates import percent_discordance

SEED = 20261120
SCHEMAS = {'synthetic_zircon_CA-ID-TIMS.csv': ['Grain ID', 'Sample Weight (mg)', 'Spike Weight (g)', 'Spike Type',
                                     'Spike', 'Collector', '206Pb/204Pb Mean',
                                     '206Pb/204Pb % Standard Error', '206Pb/207Pb Mean',
                                     '206Pb/207Pb % Standard Error', '206Pb/205Pb Mean',
                                     '206Pb/205Pb % Standard Error', '207Pb/205Pb Mean',
                                     '207Pb/205Pb % Standard Error', '204Pb/205Pb Mean',
                                     '204Pb/205Pb % Standard Error', '208Pb/205Pb Mean',
                                     '208Pb/205Pb % Standard Error', '238U/235U Mean',
                                     '238U/235U % Standard Error', '233U/235U Mean',
                                     '233U/235U % Standard Error', '238U/233U Mean',
                                     '238U/233U % Standard Error'],
 'synthetic_template_2535.csv': ['Grain ID', 'Sample Weight (mg)', 'Spike Weight (g)', 'Spike Type',
                                 'Spike', 'Collector', '206Pb/204Pb Mean', '206Pb/204Pb % Standard Error',
                                 '206Pb/207Pb Mean', '206Pb/207Pb % Standard Error', '206Pb/205Pb Mean',
                                 '206Pb/205Pb % Standard Error', '207Pb/205Pb Mean',
                                 '207Pb/205Pb % Standard Error', '204Pb/205Pb Mean',
                                 '204Pb/205Pb % Standard Error', '208Pb/205Pb Mean',
                                 '208Pb/205Pb % Standard Error', '202Pb/205Pb Mean',
                                 '202Pb/205Pb % Standard Error', '238U/235U Mean',
                                 '238U/235U % Standard Error', '233U/235U Mean',
                                 '233U/235U % Standard Error', '238U/233U Mean',
                                 '238U/233U % Standard Error'],
 'synthetic_pb_only.fractions.csv': ['Contract', 'Fraction ID', 'Sample', 'Beaker', 'Sample Weight (mg)',
                                     'Spike Weight (g)', 'Spike Type', 'Spike', 'Collector',
                                     '206Pb/204Pb Mean', '206Pb/204Pb % Standard Error', '206Pb/207Pb Mean',
                                     '206Pb/207Pb % Standard Error', '206Pb/205Pb Mean',
                                     '206Pb/205Pb % Standard Error', '207Pb/205Pb Mean',
                                     '207Pb/205Pb % Standard Error', '204Pb/205Pb Mean',
                                     '204Pb/205Pb % Standard Error', '208Pb/205Pb Mean',
                                     '208Pb/205Pb % Standard Error', 'rho 206Pb/205Pb|206Pb/204Pb',
                                     'rho 206Pb/205Pb|207Pb/205Pb', 'Pb Raw File', 'Pb Cycles Used',
                                     'Lab Note'],
 'synthetic_u_only.fractions.csv': ['Contract', 'Fraction ID', 'Sample', '238U/235U Mean',
                                    '238U/235U % Standard Error', '233U/235U Mean',
                                    '233U/235U % Standard Error', '238U/233U Mean',
                                    '238U/233U % Standard Error', 'rho 238U/235U|233U/235U',
                                    'U Oxide 18O/16O', 'U Oxide Formula', 'U Raw File', 'U Cycles Used'],
 'synthetic_database_link.fractions.csv': ['Contract', 'Fraction ID', 'Beaker', 'Source Mount',
                                           'Source Grain', 'Source Spot', 'Fraction UID', 'Database Server',
                                           'Database Read At', 'Source Grain UID', 'Source Spot UID',
                                           'Source Fragment Note', 'Capsule Set', 'Chemistry Batch UID',
                                           'Sample Weight (mg)', 'Spike Weight (g)', 'Spike Type', 'Spike',
                                           'Collector', 'Annealing', 'Chemical Abrasion',
                                           'Annealing Temperature (°C)', 'Annealing Duration (h)',
                                           'Chemical Abrasion Temperature (°C)',
                                           'Chemical Abrasion Duration (h)', 'Chemistry Steps',
                                           'Spike Solution', 'Spike Version UID', '206Pb/204Pb Mean',
                                           '206Pb/204Pb % Standard Error', '206Pb/207Pb Mean',
                                           '206Pb/207Pb % Standard Error', '206Pb/205Pb Mean',
                                           '206Pb/205Pb % Standard Error', '207Pb/205Pb Mean',
                                           '207Pb/205Pb % Standard Error', '204Pb/205Pb Mean',
                                           '204Pb/205Pb % Standard Error', '208Pb/205Pb Mean',
                                           '208Pb/205Pb % Standard Error', '238U/235U Mean',
                                           '238U/235U % Standard Error', '233U/235U Mean',
                                           '233U/235U % Standard Error', '238U/233U Mean',
                                           '238U/233U % Standard Error', 'Pb Cycle Selection',
                                           'U Cycle Selection']}
DATABASE_METADATA = [{'Contract': 'idtims-fractions/1',
  'Fraction ID': 'z1',
  'Beaker': 'K9',
  'Source Mount': 'M1',
  'Source Grain': 'g1',
  'Source Spot': 's1',
  'Fraction UID': '00000000-0000-4000-8000-000000000001',
  'Database Server': 'https://upbdb.example.invalid/lab',
  'Database Read At': '2026-11-20T10:00:00-07:00',
  'Source Grain UID': '10000000-0000-4000-8000-000000000001',
  'Source Spot UID': '20000000-0000-4000-8000-000000000001',
  'Source Fragment Note': '',
  'Capsule Set': 'Krogh',
  'Chemistry Batch UID': '30000000-0000-4000-8000-000000000001',
  'Spike Type': '535',
  'Spike': 'ET535',
  'Collector': 'D',
  'Annealing': '900 °C, 60 h',
  'Chemical Abrasion': '190 °C, 12 h, 29 M HF',
  'Annealing Temperature (°C)': '900.0',
  'Annealing Duration (h)': '60.0',
  'Chemical Abrasion Temperature (°C)': '190.0',
  'Chemical Abrasion Duration (h)': '12.0',
  'Chemistry Steps': 'SP-TIMS-ANNEAL 900 °C 60 h; SP-TIMS-CA 190 °C 12 h 29 M HF',
  'Spike Solution': 'ET535/unassigned/v3',
  'Spike Version UID': '40000000-0000-4000-8000-000000000001',
  'Pb Cycle Selection': 'shared',
  'U Cycle Selection': 'shared'},
 {'Contract': 'idtims-fractions/1',
  'Fraction ID': 'z2',
  'Beaker': 'K10',
  'Source Mount': 'M1; M2',
  'Source Grain': 'g2; g3',
  'Source Spot': 's2; ',
  'Fraction UID': '00000000-0000-4000-8000-000000000002',
  'Database Server': 'https://upbdb.example.invalid/lab',
  'Database Read At': '2026-11-20T10:00:00-07:00',
  'Source Grain UID': '10000000-0000-4000-8000-000000000002; 10000000-0000-4000-8000-000000000003',
  'Source Spot UID': '20000000-0000-4000-8000-000000000002; ',
  'Source Fragment Note': '; tip fragment',
  'Capsule Set': 'Krogh',
  'Chemistry Batch UID': '30000000-0000-4000-8000-000000000001',
  'Spike Type': '535',
  'Spike': 'ET535',
  'Collector': 'D',
  'Annealing': '900 °C, 60 h',
  'Chemical Abrasion': '190 °C, 12 h, 29 M HF',
  'Annealing Temperature (°C)': '900.0',
  'Annealing Duration (h)': '60.0',
  'Chemical Abrasion Temperature (°C)': '190.0',
  'Chemical Abrasion Duration (h)': '12.0',
  'Chemistry Steps': 'SP-TIMS-ANNEAL 900 °C 60 h; SP-TIMS-CA 190 °C 12 h 29 M HF',
  'Spike Solution': 'ET535/unassigned/v3',
  'Spike Version UID': '40000000-0000-4000-8000-000000000001',
  'Pb Cycle Selection': 'shared',
  'U Cycle Selection': 'shared'},
 {'Contract': 'idtims-fractions/1',
  'Fraction ID': 'z3',
  'Beaker': '',
  'Source Mount': '',
  'Source Grain': '',
  'Source Spot': '',
  'Fraction UID': '',
  'Database Server': '',
  'Database Read At': '',
  'Source Grain UID': '',
  'Source Spot UID': '',
  'Source Fragment Note': '',
  'Capsule Set': '',
  'Chemistry Batch UID': '',
  'Spike Type': '535',
  'Spike': 'BSU1B',
  'Collector': 'F',
  'Annealing': '',
  'Chemical Abrasion': '',
  'Annealing Temperature (°C)': '',
  'Annealing Duration (h)': '',
  'Chemical Abrasion Temperature (°C)': '',
  'Chemical Abrasion Duration (h)': '',
  'Chemistry Steps': '',
  'Spike Solution': '',
  'Spike Version UID': '',
  'Pb Cycle Selection': 'shared',
  'U Cycle Selection': 'shared'}]


def write_csv(path, columns, rows):
    with (ROOT / path).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n', extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, value):
    (ROOT / path).write_text(json.dumps(value, sort_keys=True, separators=(',', ':'))+'\n')


def invent_rows(rng, double=False):
    tracer = UPbR.load_spike_data('ET2535' if double else 'BSU1B').loc['value']
    lab = json.loads((ROOT/'tests/data/settings_BSU_template.json').read_text())['lab_blanks']
    ids = ['z1','z2','z3','z4','z5','z6'] if double else [
        'z1','z2','z3','z4','z5','z6','z7','z8','z9a','z9b','z10a','z10b']
    rows = []
    for i, fid in enumerate(ids):
        r65 = rng.uniform(.7, 3.2) if double else rng.uniform(2.5, 45)
        # The first 535 row must be above the blank cap for Monte Carlo tests.
        r46 = (rng.uniform(.00012, .0002)/r65 if double else
               (.0012 if i == 0 else rng.uniform(.000025, .00035)))
        if not double and i == 9: r46 = .0005/r65
        r76 = rng.uniform(.059, .061) if double else rng.uniform(.074, .079)
        r85pb = r65*rng.uniform(.19, .32)
        r85u = r65*(.12 if double else .067)*rng.uniform(.97, 1.03)
        fu = rng.uniform(.0006, .0011)
        sample_u = (r85u*(1+3*fu)-float(tracer['238U/235U'])) / (1-r85u*(1+3*fu)/constants.common_U238_U235)
        r35 = float(tracer['233U/235U'])/(1+sample_u/constants.common_U238_U235)/(1-2*fu)
        e65, e46, e76 = rng.uniform(.006, .009), rng.uniform(.17, .24), rng.uniform(.011, .016)
        e45 = math.hypot(e65, e46)
        if double and i == 0: e45 = e46+2*e65
        if double and i == 5: e45 = e46-2*e65
        if not double and i == 11: e45 = e46+2*e65
        eu85, eu35 = rng.uniform(.004, .009), rng.uniform(.0015, .003)
        pairs = {
            '206Pb/204Pb': (1/r46, e46), '206Pb/207Pb': (1/r76, e76),
            '206Pb/205Pb': (r65, e65), '207Pb/205Pb': (r65*r76, math.hypot(e65,e76)),
            '204Pb/205Pb': (r65*r46, e45), '208Pb/205Pb': (r85pb, rng.uniform(.01,.025)),
            '238U/235U': (r85u, eu85), '233U/235U': (r35, eu35),
            '238U/233U': (r85u/r35, math.hypot(eu85,eu35)),
        }
        if double:
            fpb = rng.uniform(.0016,.0028)
            pairs['202Pb/205Pb'] = (float(tracer['202Pb/205Pb'])/(1-3*fpb), rng.uniform(.006,.009))
        row = {'Grain ID': fid, 'Sample Weight (mg)': .01,
               'Spike Weight (g)': round(rng.uniform(.011,.021),4),
               'Spike Type': 2535 if double else 535, 'Spike': 'ET2535' if double else 'BSU1B',
               'Collector': 'D' if double or i not in (2,4,5) else 'F'}
        if double:
            # A narrow concordant age cluster exercises the same zoom/bracketing
            # geometry as the original fixture, without reusing measured ages.
            age = 612.3 + (.04, -.09, .07, -.03, .10, -.06)[i]
            r68 = math.expm1(constants.lambda_238*age*1e6)
            target76 = math.expm1(constants.lambda_235*age*1e6)/r68/constants.common_U238_U235
            common204 = r65*r46*(1-fpb)-float(tracer['204Pb/205Pb'])
            pb206 = r65*(1+fpb)-float(tracer['206Pb/205Pb'])-lab['R64b']*common204
            r76 = (pb206*target76 + float(tracer['206Pb/205Pb'])*float(tracer['207Pb/206Pb'])
                   + lab['R74b']*common204)/(r65*(1+2*fpb))
            u235t = float(tracer['U235'])*row['Spike Weight (g)']
            u238s = pb206*float(tracer['Pb205'])*row['Spike Weight (g)']/r68
            ub = utils.calc_U238b(lab['U_blank_total'], 0, utils.calc_U_blank_AW())['U238b']
            eta, alpha, beta = (constants.common_U238_U235, float(tracer['238U/235U']),
                                float(tracer['233U/235U']))
            r85u = (u238s+alpha*u235t+ub)/((u235t+u238s/eta)*(1+3*fu))
            r35 = beta*(eta-r85u*(1+3*fu))/((eta-alpha)*(1-2*fu))
            for ratio, value in {'206Pb/207Pb': 1/r76, '207Pb/205Pb': r65*r76,
                                 '238U/235U': r85u, '233U/235U': r35,
                                 '238U/233U': r85u/r35}.items():
                pairs[ratio] = (value, pairs[ratio][1])
        for ratio, (mean,error) in pairs.items():
            # Decimal serialization shared by legacy, contract and split fixtures.
            row[ratio+' Mean'] = float(f'{mean:.12g}')
            row[ratio+' % Standard Error'] = float(f'{error:.12g}')
        rows.append(row)
    return rows


def generate():
    rng = random.Random(SEED)
    legacy, template = invent_rows(rng), invent_rows(rng, double=True)
    write_csv('examples/synthetic_zircon_CA-ID-TIMS.csv', SCHEMAS['synthetic_zircon_CA-ID-TIMS.csv'], legacy)
    columns = SCHEMAS['synthetic_template_2535.csv']
    write_csv('tests/data/synthetic_template_2535.csv', columns, template)
    write_csv('tests/data/synthetic_template_2535_oxide.csv', columns+['U Oxide 18O/16O','U Oxide Formula'],
              [dict(r, **{'U Oxide 18O/16O': .00206,'U Oxide Formula':'isobar_233_18O'}) for r in template])
    for part in ('pb','u'):
        rows = []
        for i, source in enumerate(legacy[:2]):
            row = dict(source, **{'Contract':'idtims-fractions/1','Fraction ID':source['Grain ID'],
                                 'Sample':'SYN-1','Beaker':f'K{i+1}',
                                 'rho 206Pb/205Pb|206Pb/204Pb': .25 if i == 0 else '',
                                 'rho 206Pb/205Pb|207Pb/205Pb': .5,
                                 'rho 238U/235U|233U/235U': -.125,
                                 'U Oxide 18O/16O': .00206, 'U Oxide Formula':'instrument',
                                 'Pb Raw File':f'pb_{source["Grain ID"]}.raw','Pb Cycles Used':120,
                                 'U Raw File':f'u_{source["Grain ID"]}.raw','U Cycles Used':80,
                                 'Lab Note':'first' if i == 0 else ''})
            rows.append(row)
        name=f'synthetic_{part}_only.fractions.csv'
        write_csv('tests/data/'+name, SCHEMAS[name], rows)
    rows = []
    for source, metadata in zip(legacy, DATABASE_METADATA):
        row = dict(source)
        row.update(metadata)
        rows.append(row)
    write_csv('tests/data/synthetic_database_link.fractions.csv', SCHEMAS['synthetic_database_link.fractions.csv'], rows)
    # The archived numbers are regenerated only on an intentional fixture update.
    from snapshot_support import OUTPUT, reduce_variants, F, B, C, VARIANTS
    write_json(OUTPUT.relative_to(ROOT), reduce_variants())
    write_json('examples/synthetic_settings.json',
               ReductionSettings.from_dicts(F, B, C, VARIANTS['th_D']).to_dict())
    import pandas as pd
    settings = ReductionSettings.from_dict(json.loads((ROOT/'tests/data/settings_BSU_template.json').read_text()))
    args, kwargs = settings.load_grains_arguments()
    kwargs['strict_covariance'] = False
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        grains = UPbR.load_grains(pd.read_csv(ROOT/'tests/data/synthetic_template_2535.csv'), *args, **kwargs)
        for grain in grains:
            grain.lambda_230 = 9.158e-6
            grain.calc_all()
    quantities = ['FPb','FPb_std','FU','Pb206s','Pb207s','U238s','U235s','Pb206r','Pb207r','Pb208r',
                  'R75r','R68r','R76r','t75','t68','t76','t68_Th_corr','t76_Th_corr','Pbc_pg','Pbr_Pbc','U_ppm','Pb_ppm']
    expected = {name:[float(getattr(g,name)) for g in grains] for name in quantities}
    expected['Th_U'] = [g.Th232s/(g.U238s+g.U235s) for g in grains]
    table = bsu_table(grains)
    write_json('tests/data/synthetic_template_expected.json', {
        'quantities':expected,
        'table':{c:table[c].tolist() for c in ['Th/U', '206Pb* (x10-13 mol)', 'mol % 206Pb*', 'Pb*/Pbc', 'Pbc (pg)', '206Pb/204Pb', '208Pb/206Pb', '207Pb/206Pb', '207Pb/235U', '206Pb/238U', '207Pb/206Pb date', '207Pb/235U date', '206Pb/238U date', 'sample 238U/206Pb', 'sample 207Pb/206Pb', 'Wt. (mg)', 'U (ppm)', 'Pb (ppm)']},
        'discordance':[percent_discordance(g) for g in grains],
        'discordance_th':[percent_discordance(g,th_corrected=True) for g in grains]})


if __name__ == '__main__':
    generate()
    print('Regenerated synthetic fixtures with seed', SEED)
