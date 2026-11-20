"""The notebook-facing API must keep working unchanged.

Covers the calls made in README.md, examples/zircon_CA-ID-TIMS_UPbR_demo.ipynb
(cell by cell) and the local MCR_data notebooks, plus the guarantee that the
engine imports without any GUI toolkit.
"""
import contextlib
import io
import subprocess
import sys
import unittest
import warnings

import numpy as np
import pandas as pd

import IDTIMS_UPbRPy
from IDTIMS_UPbRPy import UPbR, utils, constants, load_grains, check_measurement_quality
from IDTIMS_UPbRPy.UPb_grain import UPb_grain
from snapshot_support import B, C, EXAMPLE, F, ROOT, VARIANTS

UTILS_NAMES = """SK75 calc_U_blank_AW calc_U238b calc_Pb_blank_AW calc_rad_Pb calc_total_Pb_ppm
calc_Pb_partitioning calc_rho_quotient calc_covariance_squared Pb206s_partials Pb206r_partials
Pb207s_partials Pb207r_partials Pb204c_partials FU_partials U238s_partials U235s_partials
Pb_covariance_squared U_covariance_squared calc_Pb206s prop_Pb206s_uncertainty
calc_Pb206s_uncertainty calc_Pb207s prop_Pb207s_uncertainty calc_Pb207s_uncertainty calc_Pb204c
prop_Pb204c_uncertainty calc_Pb204c_uncertainty calc_FU prop_FU_uncertainty calc_FU_uncertainty
calc_U238s prop_U238s_uncertainty calc_U238s_uncertainty calc_U235s prop_U235s_uncertainty
calc_U235s_uncertainty calc_rad_U calc_total_U_ppm calc_PbPb_Rs calc_UPb_Rs calc_R76r calc_UPb_Rr
prop_cov_Pb_R76s_squared calc_cov_Pb_R76s_squared prop_cov_Pb_R46s_squared calc_cov_Pb_R46s_squared
prop_cov_Pb_R47s_squared calc_cov_Pb_R47s_squared calc_PbPb_uncertainty calc_UPb_uncertainty
calc_PbPbs_rhos calc_UPbs_rhos calc_Pb206r prop_Pb206r_uncertainty calc_Pb206r_uncertainty
calc_Pb207r prop_Pb207r_uncertainty calc_Pb207r_uncertainty prop_cov_Pb76r_squared
calc_cov_Pb76r_squared calc_UPbr_rhos calc_t75 calc_t68 calc_t76 calc_t68_uncertainty
calc_t75_uncertainty calc_t76_uncertainty Pb208r_partials calc_Pb208r prop_Pb208r_uncertainty
calc_Th232s calc_Th_ppm calc_t68_Th calc_Pb206r_Th calc_R68r_Th_std""".split()

GRAIN_METHODS = """print_general_info print_tracer_info print_blank_info print_initial_info
print_measurement_info print_radiogenic_quantities print_molar_quantities print_partials print_ages
calc_all""".split()

TOP_LEVEL = ["UPb_grain", "constants", "UPbR", "utils", "load_grains", "load_spike_data",
             "check_measurement_quality", "check_ratio_errors", "DataQualityError"]

DEMO_TH = dict(Th230_correction_type="D", D_Th_U=0.2, D_Th_U_std=0.05,
               Th_U_magma=3.0, Th_U_magma_std=0.05, a_Th230_U238=1.0)


class PublicSurfaceTests(unittest.TestCase):
    def test_top_level_names(self):
        for name in TOP_LEVEL:
            self.assertTrue(hasattr(IDTIMS_UPbRPy, name), name)
        self.assertEqual(sorted(IDTIMS_UPbRPy.__all__), sorted(TOP_LEVEL))

    def test_utils_names(self):
        missing = [n for n in UTILS_NAMES if not callable(getattr(utils, n, None))]
        self.assertEqual(missing, [])

    def test_grain_methods(self):
        missing = [n for n in GRAIN_METHODS if not callable(getattr(UPb_grain, n, None))]
        self.assertEqual(missing, [])

    def test_constants(self):
        for name in ["lambda_235", "lambda_238", "lambda_232", "lambda_230", "common_U238_U235",
                     "AWPb204", "AWPb206", "AWPb207", "AWPb208", "AWU235", "AWU238"]:
            self.assertIsInstance(getattr(constants, name), float, name)


class ReadmeCallsTests(unittest.TestCase):
    def test_dates_from_ratios(self):
        age68 = utils.calc_t68(0.105)
        age76 = utils.calc_t76(0.061)
        sigma = utils.calc_t76_uncertainty(age76, 0.000025)
        self.assertTrue(600 < age68 < 700 and 600 < age76 < 700 and 0 < sigma < 5)

    def test_mcr_notebook_imports(self):
        from IDTIMS_UPbRPy.utils import (calc_t68, calc_t75, calc_t76, calc_t68_uncertainty,
                                         calc_t75_uncertainty, calc_t76_uncertainty)
        t68 = calc_t68(0.18)
        self.assertGreater(calc_t68_uncertainty(t68, 0.0001), 0)
        t75 = calc_t75(1.9)
        self.assertGreater(calc_t75_uncertainty(t75, 0.001), 0)
        self.assertGreater(calc_t76(0.075), 0)
        self.assertGreater(calc_t76_uncertainty(1000, 0.0001), 0)

    def test_quality_check(self):
        quality = check_measurement_quality(pd.read_csv(EXAMPLE))
        for column in ["grain", "identity", "implied_correlation", "passed",
                       "x_error_pct", "x_error_lower_pct", "x_error_upper_pct"]:
            self.assertIn(column, quality.columns)

    def test_spike_tables(self):
        self.assertIn("value", UPbR.load_spike_data("BSU1B").index)
        self.assertIn("value", UPbR.load_spike_data("ET535", "v3").index)


class DemoNotebookTests(unittest.TestCase):
    """examples/zircon_CA-ID-TIMS_UPbR_demo.ipynb, cell by cell."""

    def test_demo_calls(self):
        spike = pd.read_csv(ROOT / "src/IDTIMS_UPbRPy/spike_compositions/BSU1B_v1.csv")
        self.assertFalse(spike.empty)
        data = pd.read_csv(EXAMPLE)
        # The notebook calls load_grains without strict_covariance. Today that
        # raises for the BSU1B example tracer (documented in README); the
        # diagnostic mode is the call that reduces. Both behaviours are kept.
        with self.assertRaisesRegex(ValueError, "impossible covariance"):
            UPbR.load_grains(data, F, B, C, DEMO_TH)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            grains = UPbR.load_grains(data, F, B, C, DEMO_TH, strict_covariance=False)
            same = load_grains(data, F, B, C, DEMO_TH, spike_version=None, strict_covariance=False)
        self.assertEqual([g.id for g in grains], list(data["Grain ID"]))
        self.assertEqual(grains[0].t68, same[0].t68)
        g = grains[0]
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            for method in GRAIN_METHODS[:-1]:
                getattr(g, method)()
        self.assertIn("z1", buffer.getvalue())
        self.assertTrue(np.isfinite(g.Pb208r) and np.isfinite(g.Pb208r_std))
        for attr in ["t68", "t75", "t76", "t68_std", "t75_std", "t76_std", "t68_Th_corr",
                     "t76_Th_corr", "R68r", "R75r", "R76r", "rho_7568_r", "data_quality_passed",
                     "uncertainty_assumptions", "input_covariance"]:
            self.assertTrue(hasattr(g, attr), attr)

    def test_variant_configs_reduce(self):
        data = pd.read_csv(EXAMPLE)
        for th in VARIANTS.values():
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                self.assertEqual(len(load_grains(data, F, B, C, th, strict_covariance=False)), len(data))


class QtFreeTests(unittest.TestCase):
    def test_engine_imports_without_gui_toolkits(self):
        code = ("import sys, IDTIMS_UPbRPy, IDTIMS_UPbRPy.UPbR, IDTIMS_UPbRPy.utils, "
                "IDTIMS_UPbRPy.quality, IDTIMS_UPbRPy.uncertainty, IDTIMS_UPbRPy.export, "
                "IDTIMS_UPbRPy.fractions, IDTIMS_UPbRPy.settings\n"
                "bad = [m for m in sys.modules if m.split('.')[0] in "
                "('PySide6', 'PyQt5', 'PyQt6', 'shiboken6', 'matplotlib', 'openpyxl')]\n"
                "print(','.join(bad))")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             check=True, env=None, cwd=ROOT)
        self.assertEqual(out.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
