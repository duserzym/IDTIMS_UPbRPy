import unittest
import warnings
import numpy as np
import pandas as pd
from IDTIMS_UPbRPy import (UPbR, DataQualityError, check_measurement_quality,
                          check_ratio_errors)
from test_reduction import ROOT, F, B, C, T


class MeasurementQualityTests(unittest.TestCase):
    def data(self):
        data = pd.read_csv(ROOT/'examples/synthetic_zircon_CA-ID-TIMS.csv').iloc[:1].copy()
        data.loc[:, 'Grain ID'] = 'z6'
        data.loc[:, '206Pb/205Pb % Standard Error'] = 0.008
        data.loc[:, '206Pb/207Pb % Standard Error'] = 0.02
        data.loc[:, '207Pb/205Pb % Standard Error'] = 0.032
        return data

    def test_synthetic_failure_and_allowed_interval(self):
        check = check_measurement_quality(self.data()).iloc[0]
        self.assertFalse(check.passed)
        self.assertAlmostEqual(check.implied_correlation, 1.75, places=12)
        self.assertAlmostEqual(check.x_error_lower_pct, 0.012, places=12)
        self.assertAlmostEqual(check.x_error_upper_pct, 0.028, places=12)

    def test_correlations_with_both_signs_and_boundaries(self):
        for rho in [-1, -0.5, 0, 0.5, 1]:
            su, sv = 0.02, 0.03
            for kind, sign in [('product', 1), ('quotient', -1)]:
                sx = np.sqrt(su**2+sv**2+sign*2*rho*su*sv)
                check = check_ratio_errors(sx, su, sv, relationship=kind)
                self.assertTrue(check['passed'])
                self.assertAlmostEqual(check['implied_correlation'], rho, places=14)

    def test_invalid_negative_correlation_is_not_clipped(self):
        check = check_ratio_errors(0.03, 0.01, 0.01, relationship='quotient')
        self.assertFalse(check['passed'])
        self.assertAlmostEqual(check['implied_correlation'], -3.5)

    def test_units_and_sigma_level_do_not_change_result(self):
        for scale in [1e-200, 0.01, 1, 2, 1e200]:
            check = check_ratio_errors(0.032*scale, 0.008*scale, 0.02*scale)
            self.assertAlmostEqual(check['implied_correlation'], 1.75, places=12)

    def test_zero_error_checks_without_inventing_correlation(self):
        for errors in [(0,0,0), (0.02,0,0.02), (0.02,0.02,0)]:
            check = check_ratio_errors(*errors)
            self.assertTrue(check['passed'])
            self.assertIsNone(check['implied_correlation'])
            self.assertEqual(check['status'], 'undefined')
        self.assertFalse(check_ratio_errors(0.03,0,0.02)['passed'])

    def test_malformed_errors_rejected(self):
        for error in [-1, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                check_ratio_errors(error, 0.01, 0.02)

    def test_default_reduction_rejects_before_tracer_calculation(self):
        with self.assertRaises(DataQualityError) as caught:
            UPbR.load_grains(self.data(), F, B, C, T)
        self.assertIn('z6', str(caught.exception))
        self.assertIn('1.75', str(caught.exception))
        self.assertIn('Tripoli', str(caught.exception))
        self.assertEqual(len(caught.exception.checks), 3)

    def test_diagnostic_mode_preserves_failure_and_warns(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            g = UPbR.load_grains(self.data(), F, B, C, T, strict_covariance=False)[0]
        self.assertFalse(g.data_quality_passed)
        self.assertAlmostEqual(g.data_quality_checks[0]['implied_correlation'], 1.75)
        self.assertTrue(any('Tripoli' in str(w.message) for w in caught))
        self.assertAlmostEqual(g.Pb_R75m_std/g.Pb_R75m*100, 0.032)

    def test_preflight_reports_every_grain_and_does_not_modify_data(self):
        data = pd.concat([self.data(), self.data()], ignore_index=True)
        data.loc[1, 'Grain ID'] = 'other'
        original = data.copy(deep=True)
        report = check_measurement_quality(data)
        self.assertEqual(len(report), 6)
        self.assertEqual(set(report.grain), {'z6', 'other'})
        pd.testing.assert_frame_equal(data, original)

    def test_custom_columns_and_direct_ratio_errors(self):
        data = self.data().rename(columns={'Grain ID':'fraction',
                                          '206Pb/205Pb % Standard Error':'custom65'})
        # Direct 207/206 relative error takes precedence over the reciprocal.
        data['custom76'] = 0.026
        report = check_measurement_quality(data, columns={
            'id':'fraction', 'Pb_R65m_std_rel':'custom65', 'Pb_R76m_std_rel':'custom76'})
        self.assertEqual(report.iloc[0].v_error_pct, 0.026)
        with self.assertRaises(ValueError):
            check_measurement_quality(data, columns={'misspelling':'x'})

    def test_empty_input_returns_report_columns(self):
        report = check_measurement_quality(self.data().iloc[:0])
        self.assertEqual(len(report), 0)
        self.assertIn('implied_correlation', report.columns)


if __name__ == '__main__':
    unittest.main()
