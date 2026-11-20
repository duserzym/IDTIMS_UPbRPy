"""ET2535 reduction against frozen synthetic reference values.

The generator uses invented ratios with z1/z6 linked-error failures and
strictly reducible z2-z5. Historical comparison tolerances are retained;
no measured workbook values are distributed.
"""
import json
import unittest
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from IDTIMS_UPbRPy import UPbR, DataQualityError

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'tests' / 'data' / 'synthetic_template_2535.csv'
SYNTHETIC = ROOT / 'examples' / 'synthetic_zircon_CA-ID-TIMS.csv'

# Template settings ('Data Reduction Engine' rows 185-219 and 679-684).
BLANKS = dict(Pb_blank_total=0.5, Pb_blank_total_std_rel=25.0,
              U_blank_total=0.013, U_blank_total_std_rel=25.0,
              R64b=18.042194590863367, R64b_std_rel=0.6071393779268438,
              R74b=15.53710207768766, R74b_std_rel=0.5178373807321012,
              R84b=37.68630673770467, R84b_std_rel=0.6296612320987086,
              rho_6474_b=0.98, rho_6484_b=0.98)
PBC = dict(R64c=17.91430033772488, R64c_std_rel=0.6071393779268438,
           R74c=15.583897037991658, R74c_std_rel=0.5178373807321012,
           R84c=37.70735296752293, R84c_std_rel=0.6296612320987086,
           rho_6474_c=0.98, rho_6484_c=0.98)
# Template selection: "D", t68-based, D(Th/U) = 0.2 ± 0.05 with
# [230Th/238U]magma = [234U/238U]magma = 1, which is the engine's D mode.
TH = dict(Th230_correction_type='D', D_Th_U=0.2, D_Th_U_std=0.05,
          Th_U_magma=3.0, Th_U_magma_std=0.5)
# The template's own decay constants (rows 241-246), for comparison only.
SHEET_CONSTANTS = dict(lambda_235=9.8485e-10, lambda_238=1.55125e-10,
                       lambda_232=4.94752e-11, lambda_230=9.158e-06,
                       common_U238_U235=137.818)

SHEET = json.loads((ROOT / "tests/data/synthetic_template_expected.json").read_text())["quantities"]


def load(data=None, strict=False, fractionation=None, **kwargs):
    data = pd.read_csv(TEMPLATE) if data is None else data
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        return UPbR.load_grains(data, fractionation or {}, BLANKS, PBC, TH,
                                strict_covariance=strict, **kwargs)


def with_sheet_constants(grain):
    for name, value in SHEET_CONSTANTS.items():
        setattr(grain, name, value)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        grain.calc_all()
    return grain


class TemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grains = [with_sheet_constants(g) for g in load()]

    def test_fraction_ids(self):
        self.assertEqual([g.id for g in self.grains], ['z1', 'z2', 'z3', 'z4', 'z5', 'z6'])

    def test_fpb_z1(self):
        self.assertAlmostEqual(self.grains[0].FPb / SHEET["FPb"][0], 1, places=12)

    def test_fpb_from_202_205(self):
        for g in self.grains:
            self.assertEqual(g.FPb, (1 - g.Pb_R25t/g.Pb_R25m)/3)
            self.assertAlmostEqual(g.Pb_R25t, 0.999239128056085, places=15)
            self.assertAlmostEqual(g.Pb_R25t_std/g.Pb_R25t*100, 0.02657, places=12)

    def test_values_match_synthetic_reference(self):
        for name, expected in SHEET.items():
            for g, value in zip(self.grains, expected):
                actual = g.Th232s/(g.U238s+g.U235s) if name == 'Th_U' else getattr(g, name)
                with self.subTest(grain=g.id, quantity=name):
                    if name in ('t76', 't76_Th_corr'):
                        self.assertLessEqual(abs(actual-value), 0.0018)
                    elif name == 'U_ppm':
                        np.testing.assert_allclose(actual, value, rtol=2e-6, atol=0)
                    elif name == 'FPb_std':
                        # Same independent two-term sum as the sheet.
                        np.testing.assert_allclose(actual, value, rtol=1e-12, atol=0)
                    else:
                        np.testing.assert_allclose(actual, value, rtol=1e-9, atol=0)

    def test_blank_capped_common_pb(self):
        # The synthetic template's total common Pb is below the assumed 0.5 pg blank:
        # the sheet's Pb204c is exactly zero; the engine keeps a rounding residue.
        for g in self.grains:
            self.assertLessEqual(abs(g.Pb204c), 1e-9*g.Pb204b)

    def test_package_constants_unchanged(self):
        from IDTIMS_UPbRPy import constants
        g = load()[0]
        self.assertEqual(g.lambda_230, constants.lambda_230)
        self.assertEqual(constants.lambda_230, 9.195e-6)

    def test_recalculation_follows_202_205(self):
        g = load()[1]
        g.Pb_R25m *= 1.001
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            g.calc_all()
        self.assertEqual(g.FPb, (1 - g.Pb_R25t/g.Pb_R25m)/3)


class InputTests(unittest.TestCase):
    def setUp(self):
        self.data = pd.read_csv(TEMPLATE)

    def test_missing_202_205_column_raises_value_error(self):
        for column in ['202Pb/205Pb Mean', '202Pb/205Pb % Standard Error']:
            with self.assertRaisesRegex(ValueError, '202Pb/205Pb'):
                load(self.data.drop(columns=column))

    def test_invalid_202_205_value_raises(self):
        for value in [np.nan, 0.0, -1.0]:
            data = self.data.copy()
            data.loc[2, '202Pb/205Pb Mean'] = value
            with self.assertRaisesRegex(ValueError, 'Grain z3.*202Pb/205Pb'):
                load(data)

    def test_tracer_without_202_205_raises(self):
        data = self.data.copy()
        data['Spike'] = 'ET535'
        with self.assertRaisesRegex(ValueError, 'tracer ET535 has no 202Pb/205Pb'):
            load(data, spike_version='v3')

    def test_error_is_value_and_not_implemented_error(self):
        with self.assertRaises(UPbR.Missing202Pb205PbError) as raised:
            load(self.data.drop(columns='202Pb/205Pb Mean'))
        self.assertIsInstance(raised.exception, ValueError)
        self.assertIsInstance(raised.exception, NotImplementedError)

    def test_custom_202_205_columns(self):
        data = self.data.rename(columns={'202Pb/205Pb Mean': 'r25', '202Pb/205Pb % Standard Error': 'r25se'})
        a = load(data, Pb_R25m='r25', Pb_R25m_std_rel='r25se')
        b = load()
        self.assertEqual([g.FPb for g in a], [g.FPb for g in b])

    def test_fractionation_factors_not_needed(self):
        a = load(fractionation=None)
        b = load(fractionation=dict(FPb_Daly=99.0, FPb_Daly_std=1.0))
        self.assertEqual([g.t68 for g in a], [g.t68 for g in b])


class MixedTests(unittest.TestCase):
    F535 = dict(FPb_Faraday=0.1, FPb_Faraday_std=0.02, FPb_Daly=0.18, FPb_Daly_std=0.03)

    def load(self, data):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            return UPbR.load_grains(data, self.F535, BLANKS, PBC, TH, strict_covariance=False)

    def test_535_ignores_absent_and_empty_202_205(self):
        synthetic = pd.read_csv(SYNTHETIC).iloc[:3].assign(**{'Grain ID': lambda d: 'SYNTHETIC-' + d['Grain ID']})
        base = self.load(synthetic)
        with_nan = synthetic.assign(**{'202Pb/205Pb Mean': np.nan, '202Pb/205Pb % Standard Error': np.nan})
        for a, b in zip(base, self.load(with_nan)):
            self.assertEqual(a.FPb, {'D': 0.0018, 'F': 0.001}[a.collector])
            self.assertEqual((a.FPb, a.t68, a.t76, a.Pb206r_std), (b.FPb, b.t68, b.t76, b.Pb206r_std))
            self.assertIsNone(b.Pb_R25m)

    def test_mixed_535_and_2535_frames(self):
        synthetic = pd.read_csv(SYNTHETIC).iloc[:3].assign(**{'Grain ID': lambda d: 'SYNTHETIC-' + d['Grain ID']})
        template = pd.read_csv(TEMPLATE)
        mixed = pd.concat([synthetic, template], ignore_index=True)
        grains = self.load(mixed)
        separate = self.load(synthetic) + self.load(template)
        self.assertEqual([g.id for g in grains], [g.id for g in separate])
        for a, b in zip(grains, separate):
            self.assertEqual((a.spike_type, a.FPb, a.t68, a.t76, a.t68_Th_corr, a.R76r_std),
                             (b.spike_type, b.FPb, b.t68, b.t76, b.t68_Th_corr, b.R76r_std))
        self.assertEqual({int(g.spike_type) for g in grains}, {535, 2535})


class CovarianceTests(unittest.TestCase):
    def setUp(self):
        self.data = pd.read_csv(TEMPLATE)

    def test_strict_rejects_inconsistent_tripoli_errors(self):
        # z1 and z6 errors violate 204/205 = (206/205)*(204/206).
        for index in (0, 5):
            with self.assertRaises(DataQualityError):
                UPbR.load_grains(self.data.iloc[[index]], {}, BLANKS, PBC, TH)

    def test_strict_reduces_consistent_fractions_without_warnings(self):
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            grains = UPbR.load_grains(self.data.iloc[1:5], {}, BLANKS, PBC, TH)
        self.assertEqual(len(grains), 4)
        for g in grains:
            self.assertTrue(g.data_quality_passed)
            self.assertFalse(any('diagnostic approximation' in n for n in g.uncertainty_assumptions))
            self.assertTrue(any('202Pb/205Pb' in n for n in g.uncertainty_assumptions))

    def test_diagnostic_warns_and_flags(self):
        with self.assertWarns(RuntimeWarning):
            g = UPbR.load_grains(self.data.iloc[[0]], {}, BLANKS, PBC, TH, strict_covariance=False)[0]
        self.assertFalse(g.data_quality_passed)
        self.assertTrue(any('diagnostic approximation' in n for n in g.uncertainty_assumptions))

    def test_fpb_primitive_slot_and_variance(self):
        g = load(self.data.iloc[[1]], strict=True)[0]
        synthetic = pd.read_csv(SYNTHETIC).iloc[[1]]
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            h = UPbR.load_grains(synthetic, MixedTests.F535, BLANKS, PBC, TH, strict_covariance=False)[0]
        self.assertEqual(g.input_covariance_names, h.input_covariance_names)
        i = g.input_covariance_names.index('FPb')
        self.assertEqual(g.input_covariance[i, i], g.FPb_std**2)
        self.assertTrue(np.all(g.input_covariance[i, np.arange(len(g.input_values)) != i] == 0))

    def test_fpb_covariance_override(self):
        base = load(self.data.iloc[[1]], strict=True)[0]
        cov = 0.5*base.FPb_std*base.Pb_R65m_std
        g = load(self.data.iloc[[1]], strict=True,
                 covariance_overrides={('FPb', 'Pb_R65m'): cov})[0]
        i, j = (g.input_covariance_names.index(n) for n in ('FPb', 'Pb_R65m'))
        self.assertEqual(g.input_covariance[i, j], cov)
        self.assertNotEqual(g.Pb206r_std, base.Pb206r_std)

    def test_impossible_fpb_override_strict_vs_diagnostic(self):
        base = load(self.data.iloc[[1]], strict=True)[0]
        bad = {('FPb', 'Pb_R65m'): 2*base.FPb_std*base.Pb_R65m_std}
        with self.assertRaisesRegex(ValueError, 'impossible covariance for Pb_R65m, FPb|impossible covariance for FPb, Pb_R65m'):
            UPbR.load_grains(self.data.iloc[[1]], {}, BLANKS, PBC, TH, covariance_overrides=bad)
        with self.assertWarns(RuntimeWarning):
            g = UPbR.load_grains(self.data.iloc[[1]], {}, BLANKS, PBC, TH,
                                 covariance_overrides=bad, strict_covariance=False)[0]
        i, j = (g.input_covariance_names.index(n) for n in ('FPb', 'Pb_R65m'))
        self.assertEqual(g.input_covariance[i, j], 0.0)
        self.assertEqual(g.Pb206r_std, base.Pb206r_std)


if __name__ == '__main__':
    unittest.main()


class FractionReaderTests(unittest.TestCase):
    def test_template_reduces_through_fraction_reader(self):
        from IDTIMS_UPbRPy.fractions import read_fractions
        table = read_fractions(ROOT / "tests/data/synthetic_template_2535.csv")
        data, columns = table.load_grains_frame()
        self.assertEqual(columns["Pb_R25m"], "202Pb/205Pb Mean")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            grains = UPbR.load_grains(data, None, BLANKS, PBC, None, spike_version="v3",
                                      strict_covariance=False, **columns)
        self.assertAlmostEqual(grains[0].FPb, SHEET["FPb"][0], places=15)

