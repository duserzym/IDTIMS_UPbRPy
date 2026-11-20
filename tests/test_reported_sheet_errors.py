"""Regressions for the user's historical UPbR-sheet uncertainty errors."""
import unittest
import warnings
import numpy as np
import pandas as pd
from IDTIMS_UPbRPy import UPbR, utils
from IDTIMS_UPbRPy.uncertainty import propagate
from test_reduction import ROOT, F, B, C, T


class ReportedSheetErrorTests(unittest.TestCase):
    def grain(self):
        data = pd.read_csv(ROOT/'examples/synthetic_zircon_CA-ID-TIMS.csv').iloc[:1]
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            return UPbR.load_grains(data, F, B, C, T, strict_covariance=False)[0]

    def test_r84_quotient_standard_deviations(self):
        g = self.grain()
        for suffix in ['m', 't']:
            u, v = getattr(g, 'Pb_R85'+suffix), getattr(g, 'Pb_R45'+suffix)
            su, sv = getattr(g, 'Pb_R85'+suffix+'_std'), getattr(g, 'Pb_R45'+suffix+'_std')
            expected = abs(u/v)*np.sqrt((su/u)**2+(sv/v)**2)
            self.assertAlmostEqual(getattr(g, 'Pb_R84'+suffix+'_std')/expected, 1, places=14)

    def test_u238_derivatives_against_numerical_differentiation(self):
        g = self.grain()
        def amount(r, f):
            return (g.U235t*r*(1+3*f)-g.U_R85t*g.U235t-g.U238b)/(1-r/g.common_U238_U235*(1+3*f))
        partials = utils.U238s_partials(g.U_R85m, g.FU, g.U235t, g.U_R85t, g.U238b, g.common_U238_U235)
        for key, value in [('dU238s_dR85m', g.U_R85m), ('dU238s_dFU', g.FU)]:
            h = max(abs(value)*1e-5, 1e-7)
            if key.endswith('R85m'):
                numeric = (amount(value+h, g.FU)-amount(value-h, g.FU))/(2*h)
            else:
                numeric = (amount(g.U_R85m, value+h)-amount(g.U_R85m, value-h))/(2*h)
            self.assertAlmostEqual(partials[key]/numeric, 1, places=7)

    def test_pb207_measured_ratio_derivative(self):
        g = self.grain()
        def amount(r76):
            return utils.calc_Pb207r(g.Pb_R65m, r76, g.Pb_R46m, g.FPb, g.Pb205t,
                                    g.Pb_R65t, g.Pb_R76t, g.Pb_R45t, g.R76c,
                                    g.R64c, g.R64b, g.R76b, g.Pb206b)
        h = g.Pb_R76m*1e-5
        numeric = (amount(g.Pb_R76m+h)-amount(g.Pb_R76m-h))/(2*h)
        self.assertAlmostEqual(g.dPb207r_dR76m/numeric, 1, places=9)

    def test_blank_r76_uncertainty_is_retained(self):
        g = self.grain()
        for name in g.input_covariance_names:
            setattr(g, name+'_std', 0.0)
        for name in ['cov_65_46_m', 'cov_76_65_m', 'cov_45_65_t', 'cov_76_65_t',
                     'cov_85_35_m', 'cov_85_35_t', 'cov_86_64_b', 'cov_85_45_m', 'cov_85_45_t']:
            setattr(g, name, 0.0)
        g.R76b_std = 0.01
        propagate(g)
        self.assertAlmostEqual(g.Pb207r_std/(abs(g.Pb206b)*g.R76b_std), 1, places=14)

    def test_pb208_common_ratio_derivative_includes_fractionation(self):
        g = self.grain()
        def amount(r45):
            common204 = (r45*(1-g.FPb)-g.Pb_R45t)*g.Pb205t-g.Pb206b/g.R64b
            return utils.calc_Pb208r(g.Pb_R85m, g.FPb, g.Pb205t, g.Pb_R85t,
                                     g.Pb206b*g.R86b, common204*g.R84c)
        h = g.Pb_R45m*1e-4
        numeric = (amount(g.Pb_R45m+h)-amount(g.Pb_R45m-h))/(2*h)
        self.assertAlmostEqual(g.dPb208r_dR45m/numeric, 1, places=7)

    def test_quotient_and_inverse_blank_covariance_rules(self):
        u, v, su, sv = 35.0, 2.0, 0.2, 0.03
        for rho in [-0.4, 0.4]:
            expected = rho*su*sv
            sigma = np.sqrt((su/v)**2+(u*sv/v**2)**2-2*u/v**3*expected)
            quotient = utils.calc_covariance_squared(u/v, sigma, u, su, v, sv, type='quotient')
            self.assertAlmostEqual(quotient, expected, places=14)
            # For blank R46=1/R64, Cov(R86,R46)=-Cov(R86,R64)/R64^2.
            product_cov = utils.calc_covariance_squared(u/v, sigma, u, su, 1/v, sv/v**2, type='product')
            self.assertAlmostEqual(product_cov, -expected/v**2, places=14)

    def test_nonzero_85_45_covariances_reach_joint_pb208(self):
        g = self.grain()
        names = g.input_covariance_names
        q = np.zeros(len(names))
        q[names.index('Pb_R65m')] = g.Pb_R46m
        q[names.index('Pb_R46m')] = g.Pb_R65m
        sigma45 = np.sqrt(q @ g.input_covariance @ q)
        g.cov_85_45_m = 0.2*g.Pb_R85m_std*sigma45
        g.cov_85_45_t = 0.2*g.Pb_R85t_std*g.Pb_R45t_std
        propagate(g)
        self.assertAlmostEqual((g.input_covariance[names.index('Pb_R85m')] @ q)/g.cov_85_45_m, 1, places=13)
        self.assertAlmostEqual(g.input_covariance[names.index('Pb_R85t'), names.index('Pb_R45t')]/g.cov_85_45_t, 1, places=13)
        std = np.sqrt(np.diag(g.input_covariance))
        active = std > 0
        corr = g.input_covariance[np.ix_(active, active)]/np.outer(std[active], std[active])
        samples = np.broadcast_to(g.input_values, (100000, len(names))).copy()
        samples[:, active] += np.random.default_rng(77).multivariate_normal(np.zeros(active.sum()), corr, size=len(samples))*std[active]
        r65,r46,_,r85,f,_,t45,_,t85,b64,_,b86,_,_,c84,b206,*_ = samples.T
        c204 = (r65*r46*(1-f)-t45)*g.Pb205t-b206/b64
        pb208 = (r85*(1+3*f)-t85)*g.Pb205t-b86*b206-c84*c204
        self.assertLess(abs(np.std(pb208, ddof=1)/g.Pb208r_std-1), 0.02)

    def test_legacy_pb207r_matches_partial_propagation(self):
        g = self.grain()
        actual = utils.calc_Pb207r_uncertainty(
            g.Pb_R65m,g.Pb_R65m_std,g.Pb_R76m,g.Pb_R76m_std,g.Pb_R75m,g.Pb_R75m_std,
            g.Pb_R46m,g.Pb_R46m_std,g.FPb,g.FPb_std,g.Pb205t,g.Pb_R45t,g.Pb_R45t_std,
            g.Pb_R65t,g.Pb_R65t_std,g.Pb_R76t,g.Pb_R76t_std,g.R76b,g.R76b_std,
            g.Pb_R75t,g.Pb_R75t_std,g.R64b,g.R64b_std,g.Pb206b,g.Pb206b_std,
            g.R64c,g.R64c_std,g.R76c,R76c_std=g.R76c_std,
            R45m=g.Pb_R45m,R45m_std=g.Pb_R45m_std,R46t=g.Pb_R46t,R46t_std=g.Pb_R46t_std)
        g.prop_Pb207r_uncertainty()
        self.assertAlmostEqual(actual/g.Pb207r_std, 1, places=14)

    def test_legacy_pb207s_matches_partial_propagation(self):
        g = self.grain()
        actual = utils.calc_Pb207s_uncertainty(
            g.Pb_R65m,g.Pb_R65m_std,g.Pb_R76m,g.Pb_R76m_std,g.Pb_R75m,g.Pb_R75m_std,
            g.FPb,g.FPb_std,g.Pb205t,g.Pb_R65t,g.Pb_R65t_std,g.Pb_R76t,g.Pb_R76t_std,
            g.R76b,g.R76b_std,g.Pb206b,g.Pb206b_std,R75t=g.Pb_R75t,R75t_std=g.Pb_R75t_std)
        self.assertAlmostEqual(actual/g.Pb207s_std, 1, places=14)

    def test_disequilibrium_inputs_are_independent_between_grains(self):
        a, b = self.grain(), self.grain()
        original_b = b.t68_Th_corr
        a.D_Th_U = 0.8
        a.calc_all()
        b.calc_all()
        self.assertNotEqual(a.t68_Th_corr, b.t68_Th_corr)
        self.assertEqual(b.t68_Th_corr, original_b)


if __name__ == '__main__':
    unittest.main()
