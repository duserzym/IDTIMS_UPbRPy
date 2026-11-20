"""Synthetic coverage for the two engine fixes approved after the ADK audit."""
import copy
from types import SimpleNamespace
import warnings

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from IDTIMS_UPbRPy import UPbR, constants, utils
from IDTIMS_UPbRPy.uncertainty import propagate, propagate_th
from snapshot_support import B, C, F, VARIANTS


def synthetic_capped_grain():
    r65 = 10.0
    tracer = UPbR.load_spike_data('BSU1B', 'v1').loc['value']
    sample_u = 20.0  # natural 238U amount relative to tracer 235U
    denominator = 1+sample_u/constants.common_U238_U235
    u85 = (sample_u+float(tracer['238U/235U']))/denominator/(1+3*0.001)
    u35 = float(tracer['233U/235U'])/denominator/(1-2*0.001)
    ratios = {'206Pb/204Pb': (1/0.0003, 0.1), '206Pb/207Pb': (1/0.075, 0.02),
              '206Pb/205Pb': (r65, 0.01), '207Pb/205Pb': (r65*0.075, np.hypot(0.01, 0.02)),
              '204Pb/205Pb': (r65*0.0003, np.hypot(0.01, 0.1)), '208Pb/205Pb': (1.5, 0.05),
              '238U/235U': (u85, 0.02), '233U/235U': (u35, 0.03),
              '238U/233U': (u85/u35, np.hypot(0.02, 0.03))}
    row = {'Grain ID': 'synthetic', 'Sample Weight (mg)': 0.02, 'Spike Weight (g)': 0.005,
           'Spike Type': 535, 'Spike': 'BSU1B', 'Collector': 'D'}
    for name, (value, error) in ratios.items():
        row[name+' Mean'] = value
        row[name+' % Standard Error'] = error
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        return UPbR.load_grains(pd.DataFrame([row]), F, B, C, VARIANTS['th_D'],
                                strict_covariance=False)[0]


def test_capped_initial_pb_stays_zero_and_dates_are_unchanged():
    g = synthetic_capped_grain()
    assert g.Pb204c == g.Pb206c == g.Pb207c == g.Pb208c == 0.0
    assert g.Pbc_pg < g.Pb_blank_total  # measured common Pb fits inside the blank
    assert g.R54s == g.R84s == g.R64s == g.R74s == g.R46s == 0.0
    for name in vars(g):
        if name.startswith('rho_'):
            assert np.isfinite(getattr(g, name)) and -1 <= getattr(g, name) <= 1, name
    legacy204 = utils.calc_Pb204c(g.Pb_R46m, g.Pb_R65m, g.FPb, g.Pb205t,
                                 g.Pb_R46t, g.Pb_R65t, g.Pb206b, g.R64b)
    assert legacy204 != 0.0  # this synthetic case actually exercises the old residue
    old206 = utils.calc_Pb206r(g.Pb_R65m, g.Pb_R46m, g.FPb, g.Pb205t,
                              g.Pb_R65t, g.Pb_R45t, g.R64c, g.R64b, g.Pb206b)
    old207 = utils.calc_Pb207r(g.Pb_R65m, g.Pb_R76m, g.Pb_R46m, g.FPb, g.Pb205t,
                              g.Pb_R65t, g.Pb_R76t, g.Pb_R45t, g.R76c,
                              g.R64c, g.R64b, g.R76b, g.Pb206b)
    assert g.Pb206r == old206 and g.Pb207r == old207
    assert g.t68 == utils.calc_t68(old206/g.U238s, g.lambda_238)
    assert g.t75 == utils.calc_t75(old207/g.U235s, g.lambda_235)
    assert g.t76 == utils.calc_t76(old207/old206, lambda_235=g.lambda_235,
                                   lambda_238=g.lambda_238, common_U238_U235=g.common_U238_U235)
    assert g.t68_Th_corr == utils.calc_t68_Th(old206/g.U238s, D_Th_U=g.D_Th_U,
                                            lambda_238=g.lambda_238, lambda_230=g.lambda_230)
    # Retain the existing first-order uncertainty model, anchored at zero.
    legacy = copy.deepcopy(g)
    legacy.Pb204c = legacy204
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        propagate(legacy)
    np.testing.assert_array_equal(g.reduction_covariance, legacy.reduction_covariance)
    dates = tuple(getattr(g, name) for name in ('t68', 't75', 't76', 't68_Th_corr', 't76_Th_corr'))
    g.calc_Pb204c()  # compatibility method must also delegate to the partition
    assert g.Pb204c == 0.0
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        g.calc_all()
    assert dates == tuple(getattr(g, name) for name in ('t68', 't75', 't76', 't68_Th_corr', 't76_Th_corr'))


def magma_reference(v, uranium):
    """Independent implicit equation, using atomic Th / (238U + 235U)."""
    p206, p207, p208, u238, melt = v
    a, b, c = constants.lambda_238*1e6, constants.lambda_232*1e6, constants.lambda_238/constants.lambda_230
    total = u238*(1+1/uranium)
    def residual(t):
        return np.expm1(a*t)-p206/u238+c*(p208/np.expm1(b*t)/total/melt-1)
    uncorrected = np.log1p(p206/u238)/a
    t = brentq(residual, uncorrected/2, uncorrected*2, xtol=1e-11)
    ratio = np.expm1(a*t)
    # Implicit derivative of the same mass-balance equation, independently
    # checked against finite differences below.
    growth = np.expm1(b*t)
    ft = a*np.exp(a*t)-c*p208*b*np.exp(b*t)/(growth**2*total*melt)
    fx = np.array([-1/u238, 0, c/(growth*total*melt),
                   p206/u238**2-c*p208/(growth*total*melt*u238),
                   -c*p208/(growth*total*melt**2)])
    dr = -a*np.exp(a*t)*fx/ft
    d76 = -p207/(u238*ratio**2)*dr
    d76[1] += 1/(u238*ratio)
    d76[3] -= p207/(u238**2*ratio)
    return np.array([ratio, p207/(u238*ratio)]), np.array([dr, d76])


def test_magma_jacobian_uses_total_u_and_grain_natural_ratio():
    # A nondefault natural ratio ensures propagation passes the grain setting.
    uranium = 91.0
    x = np.array([1.2e-13, 8.4e-15, 4.1e-14, 1e-12, 3.2])
    values, analytic = magma_reference(x, uranium)
    finite_difference = np.empty_like(analytic)
    for i in range(len(x)):
        step = x[i]*2e-5
        hi, lo = x.copy(), x.copy()
        hi[i] += step
        lo[i] -= step
        finite_difference[:, i] = (magma_reference(hi, uranium)[0]-magma_reference(lo, uranium)[0])/(2*step)
    np.testing.assert_allclose(finite_difference, analytic, rtol=2e-5, atol=1e-12)
    t = utils.calc_t68_Th(x[0]/x[3], type='magma', Pb208r=x[2], U238s=x[3],
                          Th_U_magma=x[4], common_U238_U235=uranium)
    np.testing.assert_allclose(np.expm1(constants.lambda_238*t*1e6), values[0], rtol=1e-13)
    # Rank-one input covariance isolates every column of the implemented
    # Jacobian, including melt Th/U. It cannot hide a bad derivative in a sum.
    for i in range(len(x)):
        sigma = x[i]*0.01
        reduced = np.zeros((10, 10))
        if i < 4:
            reduced[i, i] = sigma**2
        g = SimpleNamespace(Pb206r=x[0], Pb207r=x[1], Pb208r=x[2], U238s=x[3],
                            Th230_correction_type='magma', Th_U_magma=x[4],
                            Th_U_magma_std=sigma if i == 4 else 0.0,
                            lambda_238=constants.lambda_238, lambda_230=constants.lambda_230,
                            lambda_232=constants.lambda_232, common_U238_U235=uranium,
                            reduction_covariance=reduced)
        propagate_th(g)
        expected = np.outer(finite_difference[:, i], finite_difference[:, i])*sigma**2
        np.testing.assert_allclose(g.th_correction_covariance, expected, rtol=2e-5, atol=1e-30)
