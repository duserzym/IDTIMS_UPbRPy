import unittest
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from IDTIMS_UPbRPy import UPbR, utils, constants

ROOT = Path(__file__).resolve().parents[1]
F = dict(FPb_Faraday=0.1, FPb_Faraday_std=0.02, FPb_Daly=0.18, FPb_Daly_std=0.03)
B = dict(Pb_blank_total=10, Pb_blank_total_std_rel=25,
         U_blank_total=0.013, U_blank_total_std_rel=25,
         R64b=18.0421945908634, R64b_std_rel=0.607139377926844,
         R74b=15.5371020776877, R74b_std_rel=0.517837380732101,
         R84b=37.6863067377047, R84b_std_rel=0.629661232098709,
         rho_6474_b=0.98, rho_6484_b=0.98)
C = dict(R64c=17.1761972269812, R64c_std_rel=0.0069,
         R74c=15.4453687937006, R74c_std_rel=0.0103,
         R84c=36.6115109186091, R84c_std_rel=0.0094,
         rho_6474_c=0.999, rho_6484_c=0.999)
T = dict(Th230_correction_type='D', D_Th_U=0.2, D_Th_U_std=0.05,
         Th_U_magma=3, Th_U_magma_std=0.05)


class AgeTests(unittest.TestCase):
    def test_concordant_ages_round_trip(self):
        for age in [0,0.0001,0.1,1,638,1100,1400,3000,4600]:
            r68 = np.expm1(constants.lambda_238*age*1e6)
            r75 = np.expm1(constants.lambda_235*age*1e6)
            r76 = r75/r68/constants.common_U238_U235 if age else constants.lambda_235/constants.lambda_238/constants.common_U238_U235
            self.assertAlmostEqual(utils.calc_t68(r68),age,places=9)
            self.assertAlmostEqual(utils.calc_t75(r75),age,places=9)
            self.assertAlmostEqual(utils.calc_t76(r76),age,places=8)

    def test_pb_age_sigma_against_finite_difference(self):
        for age in [0,0.001,1,640,1100,3000]:
            a,b,u = constants.lambda_235*1e6,constants.lambda_238*1e6,constants.common_U238_U235
            def ratio(t):
                return np.expm1(a*t)/np.expm1(b*t)/u if t else a/b/u
            h = 1e-3
            derivative = (ratio(age+h)-ratio(age-h))/(2*h)
            actual = utils.calc_t76_uncertainty(age,0.00001)
            self.assertAlmostEqual(actual/(0.00001/derivative),1,places=6)

    def test_invalid_ages_rejected(self):
        for ratio in [float('nan'),float('inf'),-1,0.01,1]:
            with self.assertRaises(ValueError):
                utils.calc_t76(ratio)
        with self.assertRaises(ValueError):
            utils.calc_t68(-0.1)

    def test_no_th_deficit_identity(self):
        r = 0.104
        self.assertEqual(utils.calc_t68_Th(r,D_Th_U=1),utils.calc_t68(r))

    def test_magma_correction_mass_balance(self):
        age = 640
        r = np.expm1(constants.lambda_238*age*1e6)
        u238 = 1e-12
        th_u = 0.6
        total_u = u238*(1+1/constants.common_U238_U235)
        pb208 = th_u*total_u*np.expm1(constants.lambda_232*age*1e6)
        corrected = utils.calc_t68_Th(r,type='magma',Pb208r=pb208,U238s=u238,Th_U_magma=3)
        recovered_th_u = pb208/total_u/np.expm1(constants.lambda_232*corrected*1e6)
        corrected_r = np.expm1(constants.lambda_238*corrected*1e6)
        self.assertAlmostEqual(corrected_r, r-constants.lambda_238/constants.lambda_230*(recovered_th_u/3-1),places=14)

    def test_d_sigma_independent_of_magma_ratio(self):
        a = utils.calc_R68r_Th_std(1e-5,D_Th_U_std=0.05,Th_U_magma_std=0)
        b = utils.calc_R68r_Th_std(1e-5,D_Th_U_std=0.05,Th_U_magma_std=100)
        self.assertEqual(a,b)


class ReductionTests(unittest.TestCase):
    def setUp(self):
        self.data = pd.read_csv(ROOT/'examples/synthetic_zircon_CA-ID-TIMS.csv')

    def load(self,data=None,th=T):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            return UPbR.load_grains(self.data if data is None else data,F,B,C,th,strict_covariance=False)

    def test_all_tracer_resources(self):
        from IDTIMS_UPbRPy.spikes import SPIKES
        for name,versions in SPIKES.items():
            for version in versions:
                self.assertIn('value',UPbR.load_spike_data(name,version).index)

    def test_loader_does_not_modify_input(self):
        original = self.data.copy(deep=True)
        self.load()
        pd.testing.assert_frame_equal(original,self.data)

    def test_custom_derived_columns(self):
        grains = UPbR.load_grains(self.data,F,B,C,T,Pb_R46m='custom46',
                                 Pb_R46m_std_rel='custom46se',Pb_R76m='custom76',Pb_R76m_std_rel='custom76se',strict_covariance=False)
        self.assertEqual(len(grains),len(self.data))

    def test_bad_measurement_rejected(self):
        for value in [0,-1,float('nan')]:
            data = self.data.copy()
            data.loc[0,'Spike Weight (g)'] = value
            with self.assertRaises(ValueError):
                self.load(data)

    def test_unsupported_spike_rejected(self):
        data = self.data.copy()
        data.loc[0,'Spike Type'] = 2535
        with self.assertRaises(NotImplementedError):
            self.load(data)

    def test_inconsistent_tracer_errors_rejected_by_default(self):
        with self.assertRaisesRegex(ValueError,'impossible covariance'):
            UPbR.load_grains(self.data.iloc[:1],F,B,C,T)

    def test_diagnostic_approximation_is_flagged(self):
        g = self.load()[0]
        self.assertTrue(any('diagnostic approximation' in note for note in g.uncertainty_assumptions))

    def test_no_correction(self):
        for g in self.load(th=None):
            self.assertEqual(g.t68,g.t68_Th_corr)
            self.assertEqual(g.t76,g.t76_Th_corr)
            self.assertEqual(g.t76_std,g.t76_Th_corr_std)

    def test_repeat_reduction_stable(self):
        for g in self.load():
            values = [g.t68,g.t76,g.t68_std,g.t76_std]
            g.calc_all()
            np.testing.assert_allclose(values,[g.t68,g.t76,g.t68_std,g.t76_std],rtol=1e-13)

    def test_u_chain_against_monte_carlo(self):
        g = self.load()[0]
        # Independently sample correlated primitive ratios, rather than treating
        # measured 238/235 and the derived mass fractionation as independent.
        mean = [g.U_R85m,g.U_R35m,g.U_R85t,g.U_R35t,g.U238b]
        std = np.array([g.U_R85m_std,g.U_R35m_std,g.U_R85t_std,g.U_R35t_std,g.U238b_std])
        corr = np.eye(5)
        corr[0,1]=corr[1,0]=g.cov_85_35_m/(std[0]*std[1])
        corr[2,3]=corr[3,2]=g.cov_85_35_t/(std[2]*std[3])
        noise = np.random.default_rng(20260930).multivariate_normal(np.zeros(5),corr,size=100000)
        measured = np.array(mean)+noise*std
        r85,r35,t85,t35,blank = measured.T
        u = g.common_U238_U235
        fu = (t35*(u-r85)+r35*(t85-u))/(2*r35*(t85-u)+3*t35*r85)
        amounts = (g.U235t*r85*(1+3*fu)-t85*g.U235t-blank)/(1-r85/u*(1+3*fu))
        self.assertLess(abs(np.std(amounts,ddof=1)/g.U238s_std-1),0.01)

    def test_joint_pb_u_and_th_against_monte_carlo(self):
        g = self.load()[0]
        std = np.sqrt(np.diag(g.input_covariance))
        active = std > 0
        corr = g.input_covariance[np.ix_(active,active)]/np.outer(std[active],std[active])
        rng = np.random.default_rng(42)
        samples = np.broadcast_to(g.input_values,(100000,len(std))).copy()
        samples[:,active] += rng.multivariate_normal(np.zeros(active.sum()),corr,size=100000)*std[active]
        (r65,r46,r76,r85,f,t65,t45,t76,t85,b64,b76,b86,c64,c76,c84,b206,
         u85,u35,ut85,ut35,ub) = samples.T
        common204 = (r65*r46*(1-f)-t45)*g.Pb205t-b206/b64
        p206 = (r65*(1+f)-t65)*g.Pb205t-b206-c64*common204
        p207 = (r65*r76*(1+2*f)-t65*t76)*g.Pb205t-b76*b206-c64*c76*common204
        u = g.common_U238_U235
        fu = (ut35*(u-u85)+u35*(ut85-u))/(2*u35*(ut85-u)+3*ut35*u85)
        u238 = (g.U235t*u85*(1+3*fu)-ut85*g.U235t-ub)/(1-u85/u*(1+3*fu))
        for amounts,name in [(p206/u238,'R68r'),(p207/u238*u,'R75r'),(p207/p206,'R76r')]:
            self.assertLess(abs(np.std(amounts,ddof=1)/getattr(g,name+'_std')-1),0.015)
        d = rng.normal(g.D_Th_U,g.D_Th_U_std,size=100000)
        corrected_r68 = p206/u238+g.lambda_238/g.lambda_230*(1-d)
        corrected_r76 = p207/(u238*corrected_r68)
        self.assertLess(abs(np.std(corrected_r76,ddof=1)/g.R76r_Th_std-1),0.015)

    def test_magma_reduction_end_to_end(self):
        grains = self.load(th=dict(Th230_correction_type='magma',Th_U_magma=3,Th_U_magma_std=0.5))
        for g in grains:
            self.assertTrue(np.isfinite(g.t68_Th_corr_std))
            self.assertTrue(np.isfinite(g.t76_Th_corr_std))
            self.assertGreater(g.t68_Th_corr,g.t68)

    def test_common_pb_mass_balance(self):
        b64,b74,b84 = 18,15,38
        aw = utils.calc_Pb_blank_AW(b64,b74,b84)
        for r46 in [0.0001,0.001]:
            result = utils.calc_Pb_partitioning(1,r46,0,1e-12,0,0,1,0.25,b64,b74,b84,aw,R64c=17,R74c=14,R84c=36)
            self.assertAlmostEqual(result['Pb204b']+result['Pb204c'],r46*1e-12,places=25)
            blank_mass = utils.calc_rad_Pb(result['Pb206b'],result['Pb207b'],result['Pb208b'])+result['Pb204b']*constants.AWPb204*1e12
            self.assertLessEqual(blank_mass,1+1e-12)
            common_mass = utils.calc_rad_Pb(result['Pb206c'],result['Pb207c'],result['Pb208c'])+result['Pb204c']*constants.AWPb204*1e12
            self.assertAlmostEqual(result['Pbc_pg'],blank_mass+common_mass,places=12)


if __name__ == '__main__':
    unittest.main()
