"""Joint first-order propagation for the supported 535 and 2535 reduction models.

Tracer amounts and natural U ratio are treated as fixed; this is not an X/Y/Z
calibration uncertainty model. Unspecified input covariances are assumed zero.

For 202Pb-205Pb double-spiked (2535) fractions FPb keeps its primitive slot.
Its value and variance come from measured and tracer 202/205 (see
``utils.calc_FPb_2535``); its covariance with the other measured x/205 ratios
and with the other tracer ratios is zero unless supplied through
``covariance_overrides`` keyed on ``"FPb"``. With ``dF/dR25m = R25t/(3 R25m**2)``
and ``dF/dR25t = -1/(3 R25m)``, ``Cov(FPb, X) = dF/dR25m*Cov(R25m, X) +
dF/dR25t*Cov(R25t, X)``. The input covariance layout is identical to 535.
"""
import numpy as np
import warnings


def propagate(grain):
    """Propagate primitive errors once, preserving shared-variable covariance."""
    g = grain
    names = ["Pb_R65m", "Pb_R46m", "Pb_R76m", "Pb_R85m", "FPb",
             "Pb_R65t", "Pb_R45t", "Pb_R76t", "Pb_R85t",
             "R64b", "R76b", "R86b", "R64c", "R76c", "R84c", "Pb206b",
             "U_R85m", "U_R35m", "U_R85t", "U_R35t", "U238b"]
    x = np.array([getattr(g, n) for n in names], dtype=float)
    std = np.array([getattr(g, n + "_std") for n in names], dtype=float)
    readable = ["measured 206Pb/205Pb", "measured 204Pb/206Pb", "measured 207Pb/206Pb",
                "measured 208Pb/205Pb", "Pb fractionation factor", "tracer 206Pb/205Pb",
                "tracer 204Pb/205Pb", "tracer 207Pb/206Pb", "tracer 208Pb/205Pb",
                "blank 206Pb/204Pb", "blank 207Pb/206Pb", "blank 208Pb/206Pb",
                "initial 206Pb/204Pb", "initial 207Pb/206Pb", "initial 208Pb/204Pb", "blank 206Pb amount",
                "measured 238U/235U", "measured 233U/235U", "tracer 238U/235U",
                "tracer 233U/235U", "blank 238U amount"]
    invalid = [label + suffix for values, suffix in ((x, " value"), (std, " 1σ"))
               for label, value in zip(readable, values) if not np.isfinite(value)]
    if invalid:
        raise ValueError(f"Grain {g.id}: non-finite reduction inputs: " + ", ".join(invalid))
    covariance = np.diag(std**2)
    g.uncertainty_assumptions = list(getattr(g, "tracer_derivations", []))
    if getattr(g, 'spike_type', 535) == 2535:
        g.uncertainty_assumptions.append(
            f"{g.id}: FPb is computed from measured and tracer 202Pb/205Pb (2535); its covariance with "
            "other measured x/205 ratios and with other tracer ratios is taken as zero unless "
            "supplied through covariance_overrides")
    def pair(a, b, cov):
        i, j = names.index(a), names.index(b)
        overrides = getattr(g, 'covariance_overrides', {})
        cov = overrides.get((a,b), overrides.get((b,a), cov))
        if abs(cov) > std[i]*std[j]*(1+1e-6):
            if not getattr(g, 'strict_covariance', True):
                message = f"{g.id}: inconsistent uncertainties for {a}, {b}; their covariance is assumed zero (diagnostic approximation)"
                warnings.warn(message, RuntimeWarning, stacklevel=2)
                g.uncertainty_assumptions.append(message)
                cov = 0.0
            else:
                raise ValueError(f"Grain {g.id}: impossible covariance for {a}, {b}")
        covariance[i, j] = covariance[j, i] = cov
    pair("Pb_R65m", "Pb_R46m", g.cov_65_46_m)
    pair("Pb_R65m", "Pb_R76m", g.cov_76_65_m)
    pair("Pb_R65t", "Pb_R45t", g.cov_45_65_t)
    pair("Pb_R65t", "Pb_R76t", g.cov_76_65_t)
    pair("U_R85m", "U_R35m", g.cov_85_35_m)
    pair("U_R85t", "U_R35t", g.cov_85_35_t)
    # Ratios sharing 206Pb in the denominator are not independent of 206/204.
    pair("R64b", "R76b", g.R76b * (g.rho_6474_b*g.R64b_std*g.R74b_std/g.R74b - g.R64b_std**2/g.R64b))
    pair("R64b", "R86b", g.cov_86_64_b)
    pair("R64c", "R76c", g.R76c * (g.rho_6474_c*g.R64c_std*g.R74c_std/g.R74c - g.R64c_std**2/g.R64c))
    # Complete missing three-ratio covariances by conditional independence.
    # This is an explicit assumption, not a recovered Tripoli measurement.
    for a,center,b in [('Pb_R46m','Pb_R65m','Pb_R76m'),
                       ('Pb_R45t','Pb_R65t','Pb_R76t'),
                       ('R76b','R64b','R86b')]:
        i,j,k = (names.index(n) for n in (a,center,b))
        covariance[i,k] = covariance[k,i] = covariance[i,j]*covariance[j,k]/covariance[j,j] if covariance[j,j] else 0.0
        g.uncertainty_assumptions.append(f"Cov({a},{b}) assumes conditional independence given {center}")
    # Measured 204/205 is represented here by (206/205)*(204/206).
    # Retain the quotient-derived 208/205 versus 204/205 covariance by
    # projecting it onto those primitives. Other links are completed by
    # conditional independence given 204/205, rather than discarded.
    for target, weights, cov in [
        ('Pb_R85m', {'Pb_R65m': g.Pb_R46m, 'Pb_R46m': g.Pb_R65m}, g.cov_85_45_m),
        ('Pb_R85t', {'Pb_R45t': 1.0}, g.cov_85_45_t),
    ]:
        gradient = np.zeros(len(names))
        for name, weight in weights.items():
            gradient[names.index(name)] = weight
        q_cov = covariance @ gradient
        variance = gradient @ q_cov
        if not np.isfinite(variance):
            raise ValueError(f"Grain {g.id}: non-finite variance for 204/205 projection")
        if variance > 0:
            for j, name in enumerate(names):
                if name != target:
                    pair(target, name, cov*q_cov[j]/variance)
        elif cov != 0:
            raise ValueError(f"Grain {g.id}: nonzero covariance with constant 204/205")
        g.uncertainty_assumptions.append(
            f"Cov({target},other Pb inputs) assumes conditional independence given 204/205; "
            "derived 208/204 errors assume independent 208/205 and 204/205 unless overridden")
    for (a,b),cov in getattr(g,'covariance_overrides',{}).items():
        pair(a,b,cov)
    g.input_covariance = covariance
    g.input_covariance_names = tuple(names)
    g.input_values = x
    active = std > 0
    correlation = covariance[np.ix_(active,active)] / np.outer(std[active],std[active])
    if not np.all(np.isfinite(correlation)) or (active.any() and np.linalg.eigvalsh(correlation).min() < -1e-6):
        raise ValueError(f"Grain {g.id}: input covariance is not positive semidefinite")
    output_names = ["Pb206r", "Pb207r", "Pb208r", "U238s", "U235s",
                    "R68r", "R75r", "R76r", "R86r", "R87r"]
    # Anchor the local model to the partition's exact zero. Keep its existing
    # first-order sensitivities: clamping the perturbed amount to a constant
    # would change the radiogenic uncertainty model as well as its centre.
    initial204_offset = ((x[0]*x[1]*(1-x[4])-x[6])*g.Pb205t-x[15]/x[9]
                         if g.Pb204c == 0 else 0.0)
    def evaluate(v):
        (r65, r46, r76, r85, f, t65, t45, t76, t85,
         b64, b76, b86, c64, c76, c84, b206,
         u85, u35, ut85, ut35, ub) = v
        c204 = (r65*r46*(1-f) - t45)*g.Pb205t - b206/b64
        if g.Pb204c == 0:
            c204 -= initial204_offset
        p206 = (r65*(1+f)-t65)*g.Pb205t - b206 - c64*c204
        p207 = (r65*r76*(1+2*f)-t65*t76)*g.Pb205t - b76*b206 - c64*c76*c204
        p208 = (r85*(1+3*f)-t85)*g.Pb205t - b86*b206 - c84*c204
        u = g.common_U238_U235
        fu = (ut35*(u-u85)+u35*(ut85-u))/(2*u35*(ut85-u)+3*ut35*u85)
        u238 = (g.U235t*u85*(1+3*fu)-ut85*g.U235t-ub)/(1-u85/u*(1+3*fu))
        u235 = u238/u
        return np.array([p206, p207, p208, u238, u235,
                         p206/u238, p207/u235, p207/p206, u238/p206, u238/p207])
    # Complex-step differentiation avoids subtractive cancellation at mol scale.
    jacobian = np.empty((len(output_names), len(x)))
    for i in range(len(x)):
        v = x.astype(complex)
        v[i] += 1e-30j
        jacobian[:, i] = evaluate(v).imag / 1e-30
    result = jacobian @ covariance @ jacobian.T
    diagonal = np.diag(result)
    if np.any(diagonal < 0) or not np.all(np.isfinite(result)):
        raise ValueError(f"Grain {g.id}: inconsistent input covariance produces invalid variance")
    for name, error in zip(output_names, np.sqrt(diagonal)):
        setattr(g, name + "_std", float(error))
    g.reduction_covariance = result
    g.reduction_covariance_names = tuple(output_names)
    def rho(a, b):
        i, j = output_names.index(a), output_names.index(b)
        denom = np.sqrt(result[i, i]*result[j, j])
        value = result[i, j]/denom if denom else 0.0
        if abs(value) > 1 + 1e-8:
            raise ValueError(f"Grain {g.id}: invalid propagated correlation {a}, {b}")
        return float(np.clip(value, -1, 1))
    g.rho_7568_r = rho("R75r", "R68r")
    g.rho_8676_r = rho("R86r", "R76r")
    g.cov_R76r = result[0, 1]


def propagate_th(grain):
    """Propagate the correction through Pb and U jointly, including covariance."""
    from .utils import calc_t68_Th
    g = grain
    indices = [0,1,2,3]  # Pb206r, Pb207r, Pb208r, U238s
    cov = np.zeros((5,5))
    cov[:4,:4] = g.reduction_covariance[np.ix_(indices,indices)]
    parameter = g.D_Th_U if g.Th230_correction_type == 'D' else g.Th_U_magma
    error = g.D_Th_U_std if g.Th230_correction_type == 'D' else g.Th_U_magma_std
    cov[4,4] = error**2
    x = np.array([g.Pb206r,g.Pb207r,g.Pb208r,g.U238s,parameter])
    def evaluate(v):
        p206,p207,p208,u238,param = v
        if g.Th230_correction_type == 'D':
            corrected = p206/u238 + g.lambda_238/g.lambda_230*(1-param)
        else:
            t = calc_t68_Th(p206/u238,type='magma',Pb208r=p208,U238s=u238,
                Th_U_magma=param,lambda_238=g.lambda_238,lambda_230=g.lambda_230,
                lambda_232=g.lambda_232,common_U238_U235=g.common_U238_U235)
            corrected = np.expm1(g.lambda_238*t*1e6)
        return np.array([corrected,p207/(u238*corrected)])
    jacobian = np.zeros((2,5))
    for i in range(5):
        if g.Th230_correction_type == 'D':
            v = x.astype(complex)
            v[i] += 1e-30j
            jacobian[:,i] = evaluate(v).imag/1e-30
        else:
            step = max(abs(x[i])*1e-4,1e-25)
            hi,lo = x.copy(),x.copy()
            hi[i] += step
            lo[i] -= step
            jacobian[:,i] = (evaluate(hi)-evaluate(lo))/(2*step)
    corrected_cov = jacobian @ cov @ jacobian.T
    if np.any(np.diag(corrected_cov) < 0):
        raise ValueError(f"Grain {g.id}: invalid Th correction variance")
    g.R68r_Th_std,g.R76r_Th_std = np.sqrt(np.diag(corrected_cov))
    g.th_correction_covariance = corrected_cov
