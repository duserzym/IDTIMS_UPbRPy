"""BSU export against frozen synthetic values, retaining numeric tolerances."""
import json
import copy
import importlib.util
import math
import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from IDTIMS_UPbRPy import UPbR
from IDTIMS_UPbRPy.dates import percent_discordance
from IDTIMS_UPbRPy.export import (BSU_COLUMNS, bsu_columns, bsu_table, footnotes, full_table,
                                  with_groups, write_csv, write_xlsx)
from IDTIMS_UPbRPy.settings import ReductionSettings
from snapshot_support import B, C, EXAMPLE, F, VARIANTS
from test_et2535 import BLANKS, PBC, TH, load, with_sheet_constants

# Frozen synthetic export values, z1..z6.
SHEET_TABLE = json.loads((Path(__file__).parent / "data/synthetic_template_expected.json").read_text())["table"]
# All template fractions have no initial common Pb: the sheet's 204Pb-based
# sample ratios (AC, AI, AK, AO, AQ, AU, AW, BA, BC) are all zero.
SHEET_ZERO = ['sample 204Pb/206Pb', 'sample 238U/204Pb', 'sample 206Pb/204Pb',
              'sample 235U/204Pb', 'sample 207Pb/204Pb', 'sample 206Pb/204Pb (6/4-7/4)',
              'sample 207Pb/204Pb (6/4-7/4)', 'sample 206Pb/204Pb (6/4-8/4)',
              'sample 208Pb/204Pb']

SHEET_LETTERS = ['B', 'C', 'D', 'E', 'F', 'G', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'R', 'S',
                 'T', 'U', 'V', 'W', 'Y', 'Z', 'AA', 'AB', 'AC', 'AD', 'AE', 'AF', 'AG', 'AI',
                 'AJ', 'AK', 'AL', 'AM', 'AO', 'AP', 'AQ', 'AR', 'AS', 'AU', 'AV', 'AW', 'AX',
                 'AY', 'BA', 'BB', 'BC', 'BD', 'BE', 'BG', 'BH', 'BI']


class BsuTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grains = [with_sheet_constants(g) for g in load()]
        cls.table = bsu_table(cls.grains)

    def test_column_order(self):
        self.assertEqual([c.sheet_column for c in BSU_COLUMNS], SHEET_LETTERS)
        self.assertEqual(list(self.table.columns), ['Fraction ID'] + [c.key for c in BSU_COLUMNS])
        self.assertEqual(len({c.key for c in BSU_COLUMNS}), len(BSU_COLUMNS))
        self.assertEqual(list(self.table['Fraction ID']), ['z1', 'z2', 'z3', 'z4', 'z5', 'z6'])

    def test_values_match_synthetic_reference(self):
        for key, expected in SHEET_TABLE.items():
            actual = self.table[key].to_numpy()
            with self.subTest(column=key):
                if key == '207Pb/206Pb date':
                    self.assertLessEqual(np.max(np.abs(actual - expected)), 0.0018)
                elif key == 'U (ppm)':
                    np.testing.assert_allclose(actual, expected, rtol=2e-6, atol=0)
                else:
                    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=0)
        for key in SHEET_ZERO:
            with self.subTest(column=key):
                self.assertTrue((self.table[key] == 0.0).all())

    def test_uncertainty_units(self):
        g = self.grains[0]
        row = self.table.iloc[0]
        self.assertEqual(row['207Pb/235U % err'], 200*g.R75r_std/g.R75r)
        self.assertEqual(row['206Pb/238U date ±'], 2*g.t68_Th_corr_std)
        self.assertEqual(row['corr. coef. 7/5-6/8'], g.rho_7568_r)
        self.assertTrue(math.isnan(row['sample 208Pb/204Pb % err']))

    def test_th_choices(self):
        plain = bsu_table(self.grains, th_corrected_dates=False, th_corrected_ratios=True,
                          include_discordance=True)
        g = self.grains[1]
        self.assertEqual(plain.loc[1, '206Pb/238U date'], g.t68)
        self.assertEqual(plain.loc[1, '207Pb/206Pb date ±'], 2*g.t76_std)
        self.assertEqual(plain.loc[1, '206Pb/238U'], g.R68r_Th)
        self.assertEqual(plain.loc[1, '% discordance'], percent_discordance(g))
        self.assertEqual(list(plain.columns).index('% discordance'),
                         list(plain.columns).index('206Pb/238U date ±') + 1)

    def test_identifiers(self):
        ids = {'z1': {'Sample': 'BSU-T', 'Beaker': 'K1', 'Source Spot': 's1'},
               'z2': {'Sample': 'BSU-T', 'Source Grain': 'g7'}}
        table = bsu_table(self.grains, identifiers=ids)
        self.assertEqual(list(table.columns[:5]),
                         ['Sample', 'Fraction ID', 'Beaker', 'Source Grain', 'Source Spot'])
        self.assertEqual(list(table['Beaker']), ['K1', '', '', '', '', ''])
        self.assertEqual(table.loc[1, 'Source Grain'], 'g7')
        self.grains[3].sample = 'from-attribute'
        try:
            self.assertEqual(bsu_table(self.grains).loc[3, 'Sample'], 'from-attribute')
        finally:
            del self.grains[3].sample

    def test_groups(self):
        grouped = with_groups(self.table)
        self.assertEqual(grouped.columns.names, ['group', 'label', 'note'])
        self.assertEqual(grouped.columns[0], ('Fraction', 'Fraction ID', 'a'))
        self.assertEqual(grouped.columns[1], ('Compositional Parameters', 'Th/U', 'b'))
        self.assertEqual({c[0] for c in grouped.columns},
                         {'Fraction', 'Compositional Parameters', 'Radiogenic Isotope Ratios',
                          'Dates (Ma)', 'Sample (Radiogenic + Initial Pb) Isotope Ratios', ''})
        pd.testing.assert_frame_equal(grouped.set_axis(self.table.columns, axis=1), self.table)
        self.assertIn('% discordance', [c.key for c in bsu_columns(True)])

    def test_rounding_residue_in_common_pb(self):
        # The engine now preserves the partitioned zero. Keep export coverage
        # for older in-memory grains that still contain a rounding residue.
        self.assertEqual(self.grains[2].Pb204c, 0)
        self.assertLess(self.table['sample 206Pb/204Pb'].abs().max(), 1)
        legacy = copy.deepcopy(self.grains[2])
        legacy.Pb204c = legacy.Pb204b*1e-16
        legacy.calc_PbPb_Rs()
        legacy.calc_UPb_Rs()
        self.assertGreater(legacy.R64s, 1e15)
        table = bsu_table([legacy])
        self.assertEqual(table.loc[0, 'sample 206Pb/204Pb'], 0)
        self.assertEqual(table.loc[0, 'sample 238U/204Pb'], 0)

    def test_real_initial_pb_uses_engine_ratios(self):
        data = pd.read_csv(EXAMPLE)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            grains = UPbR.load_grains(data, F, B, C, VARIANTS['th_D'], strict_covariance=False)
        table = bsu_table(grains)
        for i, g in enumerate(grains):
            if g.Pb204c > 1e-9*g.Pb204b:
                self.assertEqual(table.loc[i, 'sample 206Pb/204Pb'], g.R64s)
                self.assertEqual(table.loc[i, 'sample corr. coef. 8/4-6/4'], g.rho_8464_s)


class FootnoteTests(unittest.TestCase):
    def test_no_exported_footnote_mentions_spreadsheet_errors(self):
        for notes in (footnotes(), footnotes(oxide={'instrument': ['z1']})):
            for _, text in notes:
                for phrase in ('BSU spreadsheet', 'formula errors', 'BSU_SHEET_NOTES'):
                    self.assertNotIn(phrase.lower(), text.lower())

    def test_provenance_is_additive_and_shared_groups_use_one_sentence(self):
        original = footnotes()
        notes = footnotes(oxide={'isobar_233_18O': ['z1', 'z2']},
                          oxide_values={'z1': 0.00206, 'z2': 0.00206},
                          mean_statistics={'arithmetic': ['z1', 'z2']})
        self.assertEqual(notes[:-1], original)
        self.assertEqual(notes[-1][0], 'k')
        text = notes[-1][1]
        self.assertIn('isobar_233_18O', text)
        self.assertIn('r238/235 = r270/267 / (1 − 2·r18·r265/267)', text)
        self.assertIn('r233/235 = r265/267 / (1 − 2·r18·r265/267)', text)
        self.assertIn('r238/233 = r238/235 / r233/235', text)
        self.assertIn('18O/16O = 0.00206', text)
        self.assertIn('arithmetic Pb and U ratio means and % standard errors', text)
        self.assertEqual(text.count('. '), 0)

    def test_grouped_provenance_and_block_statistics(self):
        text = dict(footnotes(
            oxide={'tripoli_java_00dc941': ['z1', 'z2'], 'instrument': ['z3'],
                   'none confirmed': ['z4'], 'missing': ['z5']},
            oxide_values={'z1': 0.002, 'z2': 0.00206, 'z3': 0.00206},
            mean_statistics={'geometric': ['z1'], 'arithmetic': ['z1', 'z2', 'z3', 'z4', 'z5']},
            mean_statistic_blocks={
                fid: {'Pb': 'geometric' if fid == 'z1' else 'arithmetic', 'U': 'arithmetic'}
                for fid in ['z1', 'z2', 'z3', 'z4', 'z5']}))['k']
        for phrase in ('tripoli_java_00dc941', 'r238/235 = r270/267 / (1 − 2·r18·r270/267)',
                       '0.002 (z1)', '0.00206 (z2)', 'formula not recorded',
                       'no U oxide correction (confirmed)', 'U oxide correction not recorded',
                       'geometric Pb ratio means', 'arithmetic U ratio means'):
            self.assertIn(phrase, text)

    def test_each_provenance_keyword_can_be_used_alone(self):
        self.assertIn('instrument', dict(footnotes(oxide={'instrument': ['z1']}))['k'])
        self.assertIn('geometric', dict(footnotes(mean_statistics={'geometric': ['z1']}))['k'])

    def test_th_correction_and_lambda230(self):
        grains = [with_sheet_constants(g) for g in load()]
        settings = ReductionSettings.from_dicts({}, BLANKS, PBC, TH, strict_covariance=False)
        notes = footnotes(settings, grains)
        self.assertEqual([n[0] for n in notes], list('abcdefghij'))
        text = ' '.join(t for _, t in notes)
        self.assertIn('D(Th/U) mineral/melt = 0.2 ± 0.05', text)
        self.assertIn('λ230 = 9.1580e-06 /yr', text)
        self.assertIn('ET2535 (2535)', text)
        self.assertIn('202Pb/205Pb', text)
        self.assertIn('McLean et al. 2011', dict(notes)['f'])
        self.assertEqual(dict(notes)['f'],
                         "Uncertainties are 2σ, from joint first-order propagation of the measured, "
                         "fractionation, blank, initial Pb and Th inputs (McLean et al. 2011 framework); "
                         "tracer calibration and decay-constant uncertainties are not included. They "
                         "can differ from reductions that propagate these terms separately.")
        self.assertIn('2σ', dict(notes)['f'])

    def test_defaults_and_other_modes(self):
        text = ' '.join(t for _, t in footnotes())
        self.assertIn('no disequilibrium correction', text)
        self.assertIn('λ230 = 9.1950e-06 /yr', text)
        magma = ReductionSettings.from_dicts(F, B, C, VARIANTS['th_magma'])
        text = ' '.join(t for _, t in footnotes(magma))
        self.assertIn('Th/U of the magma = 3 ± 0.5', text)
        self.assertIn('0.18 ± 0.03 %/amu (Daly)', text)


class FullTableTests(unittest.TestCase):
    def test_csv_round_trip(self):
        grains = [with_sheet_constants(g) for g in load()]
        table = full_table(grains)
        self.assertEqual(table.columns[0], 'id')
        self.assertEqual(list(table['id']), ['z1', 'z2', 'z3', 'z4', 'z5', 'z6'])
        for name in ('t68', 't76_Th_corr', 'Pb206r_std', 'rho_7568_r', 'lambda_230', 'FPb'):
            self.assertIn(name, table.columns)
        self.assertNotIn('strict_covariance', table.columns)
        self.assertNotIn('collector', table.columns)
        self.assertEqual(table.loc[0, 't68'], grains[0].t68)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'full.csv'
            write_csv(table, path)
            back = pd.read_csv(path, float_precision='round_trip')
        self.assertEqual(list(back.columns), list(table.columns))
        # Whole numbers (e.g. 0) are written without a decimal point and read as int.
        back = back.astype({c: float for c in table.columns[1:]})
        pd.testing.assert_frame_equal(back, table, check_exact=True)

    def test_none_attributes_become_nan(self):
        data = pd.read_csv(EXAMPLE).iloc[:2]
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            plain = UPbR.load_grains(data, F, B, C, None, strict_covariance=False)
            corrected = UPbR.load_grains(data, F, B, C, VARIANTS['th_D'], strict_covariance=False)
        self.assertIsNone(plain[0].Th232s)
        table = full_table(plain + corrected)
        self.assertEqual(len(table), 4)
        self.assertTrue(table['Th232s'][:2].isna().all())
        self.assertEqual(list(table['Th232s'][2:]), [g.Th232s for g in corrected])

    @unittest.skipUnless(importlib.util.find_spec('openpyxl'), 'openpyxl not installed')
    def test_write_xlsx(self):
        grains = [with_sheet_constants(g) for g in load()]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'table.xlsx'
            write_xlsx(bsu_table(grains), footnotes(None, grains), path)
            self.assertGreater(path.stat().st_size, 0)


if __name__ == '__main__':
    unittest.main()
