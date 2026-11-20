"""Pre-reduction checks of correlations implied by linked ratio errors.

These are first-order consistency checks, not observed correlations or a
unique diagnosis of Tripoli filtering. Errors must use the same sigma level,
accepted measurements and weighting conventions.
"""
import math
import warnings
import pandas as pd


class DataQualityError(ValueError):
    """Impossible measurement covariance, with all checks for the grain."""
    def __init__(self, checks):
        self.checks = checks
        failed = [check for check in checks if not check['passed']]
        details = []
        for check in failed:
            rho = check['implied_correlation']
            value = f'{rho:.9g}' if rho is not None else 'undefined (zero input error)'
            details.append(f"Grain {check['grain']}: {check['identity']}; implied correlation={value}; "
                           f"relative errors (%) x/u/v={check['x_error_pct']:.9g}/"
                           f"{check['u_error_pct']:.9g}/{check['v_error_pct']:.9g}; "
                           f"allowed x error=[{check['x_error_lower_pct']:.9g}, "
                           f"{check['x_error_upper_pct']:.9g}]%")
        super().__init__('Impossible covariance in measurement data: '+ '; '.join(details)+
                         '. Check the original Tripoli errors, block/cycle filtering and sigma conventions.')


def check_ratio_errors(x_error_pct, u_error_pct, v_error_pct, *,
                       relationship='product', grain=None, identity='', tolerance=1e-6):
    """Infer Corr(u,v) from errors in x=u*v or x=u/v.

    Relative errors may share any common unit or sigma level (the report
    labels them percent). Never clips an invalid inferred correlation.
    Correlation is undefined when either component error is zero; the error
    identity is still checked. Tolerance applies to correlation bounds.
    """
    sx, su, sv = map(float, (x_error_pct, u_error_pct, v_error_pct))
    if any(not math.isfinite(s) or s < 0 for s in (sx, su, sv)):
        raise ValueError(f'Grain {grain}: relative errors must be finite and nonnegative')
    if relationship not in ('product', 'quotient'):
        raise ValueError('relationship must be product or quotient')
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError('tolerance must be finite and nonnegative')
    # Scale before squaring to avoid overflow/underflow and ensure the
    # consistency decision is independent of the supplied error units.
    scale = max(sx, su, sv)
    x, u, v = (s/scale for s in (sx, su, sv)) if scale else (0.0, 0.0, 0.0)
    if u and v:
        rho = (x*x-u*u-v*v)/(2*u*v)
        if relationship == 'quotient':
            rho = -rho
        passed = abs(rho) <= 1+tolerance
        status = 'pass' if passed else 'fail'
    else:
        rho = None
        passed = abs(x*x-u*u-v*v) <= tolerance*max(x*x, u*u+v*v)
        status = 'undefined' if passed else 'fail'
    return dict(grain=grain, identity=identity, relationship=relationship,
                implied_correlation=rho, passed=passed, status=status,
                x_error_pct=sx, u_error_pct=su, v_error_pct=sv,
                x_error_lower_pct=abs(su-sv), x_error_upper_pct=su+sv)


TRIPLETS = [
    ('Pb_R75m', 'Pb_R65m', 'Pb_R76m', 'product', '207/205 = (206/205)*(207/206)'),
    ('Pb_R45m', 'Pb_R65m', 'Pb_R46m', 'product', '204/205 = (206/205)*(204/206)'),
    ('U_R83m', 'U_R85m', 'U_R35m', 'quotient', '238/233 = (238/235)/(233/235)'),
]


def check_grain_measurements(grain):
    """Record raw-error checks and enforce the grain's covariance policy."""
    def relative(name):
        value = getattr(grain, name)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f'Grain {grain.id}: {name} must be finite and positive')
        return getattr(grain, name+'_std')/value*100
    checks = [check_ratio_errors(relative(x), relative(u), relative(v),
                                relationship=kind, grain=grain.id, identity=identity)
              for x, u, v, kind, identity in TRIPLETS]
    grain.data_quality_checks = checks
    grain.data_quality_passed = all(check['passed'] for check in checks)
    if not grain.data_quality_passed:
        error = DataQualityError(checks)
        if getattr(grain, 'strict_covariance', True):
            raise error
        warnings.warn(str(error)+' Diagnostic reduction requested; inputs were not repaired.',
                      RuntimeWarning, stacklevel=2)
    return checks


def check_measurement_quality(data, *, columns=None):
    """Check every DataFrame row without reduction or tracer calibration.

    Uses the standard load_grains measurement error columns. ``columns``
    maps loader parameter names (e.g. Pb_R65m_std_rel or id) to custom column
    names. Reciprocal 206/207 and 206/204 errors are used if direct 207/206
    and 204/206 errors are absent. Returns one record per grain and triplet,
    including failures, without modifying input data or raising on rho > 1.
    Malformed errors or missing columns raise rather than being skipped.
    """
    defaults = {
        'id': 'Grain ID',
        'Pb_R75m_std_rel': '207Pb/205Pb % Standard Error',
        'Pb_R65m_std_rel': '206Pb/205Pb % Standard Error',
        'Pb_R76m_std_rel': '207Pb/206Pb % Standard Error',
        'Pb_R67m_std_rel': '206Pb/207Pb % Standard Error',
        'Pb_R45m_std_rel': '204Pb/205Pb % Standard Error',
        'Pb_R46m_std_rel': '204Pb/206Pb % Standard Error',
        'Pb_R64m_std_rel': '206Pb/204Pb % Standard Error',
        'U_R83m_std_rel': '238U/233U % Standard Error',
        'U_R85m_std_rel': '238U/235U % Standard Error',
        'U_R35m_std_rel': '233U/235U % Standard Error',
    }
    if columns:
        unknown = set(columns)-set(defaults)
        if unknown:
            raise ValueError(f'Unknown column mappings: {sorted(unknown)}')
        defaults.update(columns)
    for direct, reciprocal in [('Pb_R76m', 'Pb_R67m'), ('Pb_R46m', 'Pb_R64m')]:
        key = direct+'_std_rel'
        if defaults[key] not in data.columns:
            defaults[key] = defaults[reciprocal+'_std_rel']
    checks = []
    for _, row in data.iterrows():
        for x, u, v, kind, identity in TRIPLETS:
            checks.append(check_ratio_errors(*(row[defaults[n+'_std_rel']] for n in (x,u,v)),
                                             relationship=kind, grain=row[defaults['id']], identity=identity))
    fields = ['grain', 'identity', 'relationship', 'implied_correlation', 'passed', 'status',
              'x_error_pct', 'u_error_pct', 'v_error_pct', 'x_error_lower_pct', 'x_error_upper_pct']
    return pd.DataFrame(checks, columns=fields)
