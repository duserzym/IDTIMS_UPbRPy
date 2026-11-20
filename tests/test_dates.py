"""Weighted means, sample dates and the BSU sheet's % discordance (IDTIMS_UPbRPy.dates)."""
import json
from pathlib import Path
import math
import unittest
import warnings

import numpy as np
import pandas as pd
from scipy import stats

from IDTIMS_UPbRPy import UPbR
from IDTIMS_UPbRPy.dates import (DATE_KINDS, WeightedMean, percent_discordance,
                                 percent_discordance_from_values, sample_dates, weighted_mean)
from snapshot_support import B, C, EXAMPLE, F, VARIANTS
from test_et2535 import SHEET, load, with_sheet_constants

# Frozen synthetic percent-discordance outputs, generated with the package.
_EXPECTED = json.loads((Path(__file__).parent /
                        'data/synthetic_template_expected.json').read_text())
SHEET_DISCORDANCE = _EXPECTED['discordance']
SHEET_DISCORDANCE_TH = _EXPECTED['discordance_th']
SHEET_LAMBDA_238, SHEET_LAMBDA_235 = 1.55125e-10, 9.8485e-10


class WeightedMeanTests(unittest.TestCase):
    def test_equal_sigmas_give_arithmetic_mean(self):
        wm = weighted_mean([1.0, 2.0, 3.0, 6.0], [0.5]*4)
        self.assertIsInstance(wm, WeightedMean)
        self.assertAlmostEqual(wm.mean, 3.0, places=14)
        self.assertAlmostEqual(wm.sigma, 0.5/2, places=14)
        self.assertEqual((wm.n, wm.dof, wm.indices), (4, 3, (0, 1, 2, 3)))

    def test_identical_values_mswd_zero(self):
        wm = weighted_mean([5.0, 5.0, 5.0], [0.1, 0.2, 0.3])
        self.assertEqual(wm.mswd, 0.0)
        self.assertEqual(wm.probability_of_fit, 1.0)
        self.assertEqual(wm.sigma_expanded, wm.sigma)

    def test_inverse_variance_weights(self):
        wm = weighted_mean([10.0, 20.0], [1.0, 2.0])
        self.assertAlmostEqual(wm.mean, (10 + 20/4)/(1 + 1/4), places=13)
        self.assertAlmostEqual(wm.sigma, 1/math.sqrt(1.25), places=14)

    def test_known_chi_square_probability(self):
        # Values ±1 about 0 with unit sigma: chi2 = 2, dof = 1, P = 0.157299...
        wm = weighted_mean([-1.0, 1.0], [1.0, 1.0])
        self.assertEqual(wm.mean, 0.0)
        self.assertAlmostEqual(wm.mswd, 2.0, places=14)
        self.assertAlmostEqual(wm.probability_of_fit, 0.15729920705028513, places=12)
        self.assertAlmostEqual(wm.probability_of_fit, stats.chi2.sf(2.0, 1), places=14)
        self.assertAlmostEqual(wm.sigma_expanded, wm.sigma*math.sqrt(2.0), places=14)

    def test_single_value(self):
        wm = weighted_mean([7.0], [0.3])
        self.assertEqual((wm.mean, wm.sigma, wm.n, wm.dof), (7.0, 0.3, 1, 0))
        self.assertTrue(math.isnan(wm.mswd))
        self.assertTrue(math.isnan(wm.probability_of_fit))
        self.assertEqual(wm.sigma_expanded, 0.3)

    def test_include_mask_and_indices(self):
        values, sigmas = [1.0, 100.0, 3.0], [1.0, 1.0, 1.0]
        by_mask = weighted_mean(values, sigmas, include=[True, False, True])
        by_index = weighted_mean(values, sigmas, include=[2, 0])
        self.assertEqual(by_mask, by_index)
        self.assertEqual(by_mask.mean, 2.0)
        self.assertEqual(by_mask.indices, (0, 2))

    def test_excluded_values_are_not_checked(self):
        wm = weighted_mean([1.0, np.nan, 3.0], [1.0, 0.0, 1.0], include=[0, 2])
        self.assertEqual(wm.mean, 2.0)

    def test_errors(self):
        with self.assertRaisesRegex(ValueError, "n < 1"):
            weighted_mean([], [])
        with self.assertRaisesRegex(ValueError, "n < 1"):
            weighted_mean([1.0, 2.0], [1.0, 1.0], include=[False, False])
        with self.assertRaisesRegex(ValueError, "Non-finite"):
            weighted_mean([1.0, np.inf], [1.0, 1.0])
        with self.assertRaisesRegex(ValueError, "Non-finite"):
            weighted_mean([1.0, 2.0], [1.0, np.nan])
        with self.assertRaisesRegex(ValueError, "positive"):
            weighted_mean([1.0, 2.0], [1.0, 0.0])
        with self.assertRaisesRegex(ValueError, "positive"):
            weighted_mean([1.0, 2.0], [-1.0, 1.0])
        with self.assertRaisesRegex(ValueError, "differ in length"):
            weighted_mean([1.0, 2.0], [1.0])
        with self.assertRaisesRegex(ValueError, "mask"):
            weighted_mean([1.0, 2.0], [1.0, 1.0], include=[True])
        with self.assertRaisesRegex(ValueError, "out of range"):
            weighted_mean([1.0, 2.0], [1.0, 1.0], include=[5])

    def test_frozen(self):
        wm = weighted_mean([1.0], [1.0])
        with self.assertRaises(Exception):
            wm.mean = 2.0


class DiscordanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grains = [with_sheet_constants(g) for g in load()]

    def test_formula_reproduces_synthetic_discordance(self):
        # The decoded formula, fed frozen synthetic t76, R68 and R75.
        for i in range(6):
            a = percent_discordance_from_values(SHEET['t76'][i], SHEET['R68r'][i],
                                                SHEET['R75r'][i], SHEET_LAMBDA_238,
                                                SHEET_LAMBDA_235)
            b = percent_discordance_from_values(SHEET['t76_Th_corr'][i], SHEET['R68r'][i],
                                                SHEET['R75r'][i], SHEET_LAMBDA_238,
                                                SHEET_LAMBDA_235)
            np.testing.assert_allclose(a, SHEET_DISCORDANCE[i], rtol=1e-11)
            np.testing.assert_allclose(b, SHEET_DISCORDANCE_TH[i], rtol=1e-11)

    def test_engine_grains_match_synthetic_reference(self):
        # Engine t76 differs from the sheet's 23-step bisection by up to 1.8 ka,
        # which moves the discordance by up to ~5e-4 percentage points.
        for g, expected, expected_th in zip(self.grains, SHEET_DISCORDANCE, SHEET_DISCORDANCE_TH):
            with self.subTest(grain=g.id):
                self.assertLess(abs(percent_discordance(g) - expected), 1e-3)
                self.assertLess(abs(percent_discordance(g, th_corrected=True) - expected_th), 1e-3)

    def test_concordant_point_is_zero_and_unsigned(self):
        t = 500.0
        r68 = math.expm1(SHEET_LAMBDA_238*1e6*t)
        r75 = math.expm1(SHEET_LAMBDA_235*1e6*t)
        self.assertEqual(percent_discordance_from_values(t, r68, r75, SHEET_LAMBDA_238,
                                                         SHEET_LAMBDA_235), 0.0)
        self.assertGreater(percent_discordance_from_values(t, r68*0.99, r75, SHEET_LAMBDA_238,
                                                           SHEET_LAMBDA_235), 0)
        self.assertGreater(percent_discordance_from_values(t, r68*1.01, r75, SHEET_LAMBDA_238,
                                                           SHEET_LAMBDA_235), 0)

    def test_non_finite_gives_nan(self):
        self.assertTrue(math.isnan(percent_discordance_from_values(np.nan, 0.1, 1.0, 1e-10, 1e-9)))
        self.assertTrue(math.isnan(percent_discordance_from_values(None, 0.1, 1.0, 1e-10, 1e-9)))


class SampleDatesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = pd.read_csv(EXAMPLE)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            cls.grains = UPbR.load_grains(data, F, B, C, VARIANTS["th_D"], strict_covariance=False)
        cls.ids = [g.id for g in cls.grains]

    def test_all_kinds(self):
        result = sample_dates(self.grains)
        self.assertEqual(list(result), list(DATE_KINDS))
        for kind, date in result.items():
            self.assertEqual(date.kind, kind)
            self.assertEqual(date.fraction_ids, tuple(self.ids))
            self.assertEqual(date.skipped, {})
            self.assertEqual(date.result.n, len(self.ids))
            attr, sattr = DATE_KINDS[kind]
            expected = weighted_mean([getattr(g, attr) for g in self.grains],
                                     [getattr(g, sattr) for g in self.grains])
            self.assertEqual(date.result, expected)

    def test_include_set_and_mapping(self):
        chosen = {"z1", "z3", "z4"}
        by_set = sample_dates(self.grains, include=chosen, kinds=("206Pb/238U",))["206Pb/238U"]
        self.assertEqual(by_set.fraction_ids, ("z1", "z3", "z4"))
        self.assertEqual(set(by_set.skipped), set(self.ids) - chosen)
        self.assertTrue(all(r == "switched off" for r in by_set.skipped.values()))
        mapping = {fid: fid in chosen for fid in self.ids}
        by_map = sample_dates(self.grains, include=mapping, kinds=("206Pb/238U",))["206Pb/238U"]
        self.assertEqual(by_map.result, by_set.result)
        # Ids missing from a mapping stay on.
        partial = sample_dates(self.grains, include={"z2": False}, kinds=("207Pb/235U",))
        self.assertEqual(partial["207Pb/235U"].fraction_ids,
                         tuple(i for i in self.ids if i != "z2"))
        g = {g.id: g for g in self.grains}
        expected = weighted_mean([g[i].t68 for i in ("z1", "z3", "z4")],
                                 [g[i].t68_std for i in ("z1", "z3", "z4")])
        self.assertEqual(by_set.result, expected)

    def test_non_finite_dates_are_skipped_with_reason(self):
        grains = [with_sheet_constants(g) for g in load()]
        grains[2].t76 = float("nan")
        grains[4].t76_std = 0.0
        date = sample_dates(grains, kinds=("207Pb/206Pb",))["207Pb/206Pb"]
        self.assertEqual(date.fraction_ids, ("z1", "z2", "z4", "z6"))
        self.assertIn("finite", date.skipped["z3"])
        self.assertIn("uncertainty", date.skipped["z5"])

    def test_nothing_included(self):
        date = sample_dates(self.grains, include=set(), kinds=("206Pb/238U",))["206Pb/238U"]
        self.assertIsNone(date.result)
        self.assertEqual(date.fraction_ids, ())

    def test_unknown_kind(self):
        with self.assertRaisesRegex(ValueError, "Unknown date kind"):
            sample_dates(self.grains, kinds=("208Pb/232U",))


if __name__ == "__main__":
    unittest.main()
