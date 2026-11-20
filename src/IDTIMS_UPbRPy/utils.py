import numpy as np
from scipy.optimize import brentq

from .constants import (
    AWPb204,
    AWPb206,
    AWPb207,
    AWPb208,
    AWTh232,
    AWU238,
    U238_rel,
    AWU235,
    U235_rel,
    lambda_230,
    lambda_232,
    lambda_235,
    lambda_238,
    common_U238_U235,
)

# general utility functions
#--------------------------------------------------

def SK75(t):
    '''
    t as in Ga, time before present
    '''
    # Initial parameters from Stacey & Kramers (1975)
    Pb206_204_i = 9.307  # Initial 206Pb/204Pb at 4.57 Ga
    Pb207_204_i = 10.294 # Initial 207Pb/204Pb at 4.57 Ga
    Pb208_204_i = 29.487 # Initial 208Pb/204Pb at 4.57 Ga
    U238_204_i = 7.19    # Initial 238U/204Pb
    U235_204_i = U238_204_i / common_U238_U235  
    # Second-stage U/Pb ratio (mantle value)
    U238_204_res = 9.735
    U235_204_res = U238_204_res / common_U238_U235  

    Th232_204_i = 33.1  # Initial 232Th/204Pb
    Th232_204_res = 36.84  # Second-stage 232Th/204Pb (mantle value)

    # Time points
    t1 = 4.57  # Start time (Ga)
    t2 = 3.7   # Transition time (Ga)
    t_end = 0.0  # Present day

    if t > t1:
        raise ValueError("Time t cannot be greater than 4.57 Ga")
    elif t2 < t <= t1:
        # first stage model
        Pb206_204_stage1 = Pb206_204_i + U238_204_i * (np.exp(lambda_238 * t1 * 1e9) - np.exp(lambda_238 * t * 1e9))

        Pb207_204_stage1 = Pb207_204_i + U235_204_i * (np.exp(lambda_235 * t1 * 1e9) - np.exp(lambda_235 * t  * 1e9))

        Pb208_204_stage1 = Pb208_204_i + Th232_204_i * (np.exp(lambda_232 * t1 * 1e9) - np.exp(lambda_232 * t * 1e9))
        return Pb206_204_stage1, Pb207_204_stage1, Pb208_204_stage1
    
    elif t_end <= t <= t2:
        # Pb values at 3.7 Ga
        Pb206_204_3_7 = Pb206_204_i + U238_204_i * (np.exp(lambda_238 * t1 * 1e9) - np.exp(lambda_238 * t2 * 1e9))
        Pb207_204_3_7 = Pb207_204_i + U235_204_i * (np.exp(lambda_235 * t1 * 1e9) - np.exp(lambda_235 * t2 * 1e9))
        Pb208_204_3_7 = Pb208_204_i + Th232_204_i * (np.exp(lambda_232 * t1 * 1e9) - np.exp(lambda_232 * t2 * 1e9))

        # Second-stage evolution (after 3.7 Ga)
        Pb206_204_stage2 = Pb206_204_3_7 + U238_204_res * (np.exp(lambda_238 * t2 * 1e9) - np.exp(lambda_238 * t * 1e9))
        Pb207_204_stage2 = Pb207_204_3_7 + U235_204_res * (np.exp(lambda_235 * t2 * 1e9) - np.exp(lambda_235 * t * 1e9))
        Pb208_204_stage2 = Pb208_204_3_7 + Th232_204_res * (np.exp(lambda_232 * t2 * 1e9) - np.exp(lambda_232 * t * 1e9))
        return Pb206_204_stage2, Pb207_204_stage2, Pb208_204_stage2
    else:
        raise ValueError("Time t cannot be in the future (negative value)")
    

def calc_U_blank_AW(AWU238=AWU238, U238_rel=U238_rel,
                    AWU235=AWU235, U235_rel=U235_rel):
    return AWU238 * U238_rel + AWU235 * U235_rel

def calc_U238b(U_blank_total, U_blank_total_std, U_blank_AW, U238_rel=U238_rel):
    '''
    Calculate U blank 238U amount based on total U blank and U atomic weight

    Parameters
    ----------
    U_blank_total : float
        Total U blank amount (pg)
    U_blank_AW : float
        Atomic weight of U blank

    Returns
    -------
    float
        238U amount in U blank (moles)
    '''
    return {"U238b":U_blank_total * 1e-12 / U_blank_AW * U238_rel,
            "U238b_std":U_blank_total_std * 1e-12 / U_blank_AW * U238_rel}
                    
def calc_Pb_blank_AW(R64b, R74b, R84b, 
                     AWPb204=AWPb204, 
                     AWPb206=AWPb206, 
                     AWPb207=AWPb207, 
                     AWPb208=AWPb208):
    '''
    Calculate Pb blank atomic weight based on measured Pb isotope ratios and atomic weights of individual isotopes

    Parameters
    ----------
    R64b : float
        204Pb/206Pb ratio of blank
    R74b : float
        207Pb/206Pb ratio of blank
    R84b : float
        208Pb/206Pb ratio of blank
    AWPb204 : float
        Atomic weight of 204Pb
    AWPb206 : float
        Atomic weight of 206Pb
    AWPb207 : float
        Atomic weight of 207Pb
    AWPb208 : float
        Atomic weight of 208Pb

    Returns
    -------
    float
        Atomic weight of Pb blank
    '''
    
    return (AWPb204+AWPb206*R64b+AWPb207*R74b+AWPb208*R84b)/(1+R64b+R74b+R84b)

def calc_rad_Pb(Pb206r, Pb207r, Pb208r, 
                AWPb206=AWPb206, 
                AWPb207=AWPb207, 
                AWPb208=AWPb208):
    '''
    calculate total radiogenic Pb amount in pg
    '''
    return (Pb206r * AWPb206 + Pb207r * AWPb207 + Pb208r * AWPb208) * 1e12

def calc_total_Pb_ppm(sample_weight, 
                      Pb204b, Pb204c, 
                      Pb206b, Pb206c, Pb206r,
                      Pb207b, Pb207c, Pb207r,
                      Pb208b, Pb208c, Pb208r,
                      AWPb204=AWPb204,
                      AWPb206=AWPb206,
                      AWPb207=AWPb207,
                      AWPb208=AWPb208):
    '''
    calculate total Pb concentration in ppm

    Parameters
    ----------
    sample_weight : float
        sample weight in milligrams
    '''
    total_Pb = (Pb204b + Pb204c) * AWPb204 + (Pb206b + Pb206c + Pb206r) * AWPb206 + (Pb207b + Pb207c + Pb207r) * AWPb207 + (Pb208b + Pb208c + Pb208r) * AWPb208 # in grams
    return total_Pb / sample_weight * 1e9

def calc_Pb_partitioning(R65m, R46m, 
                         FPb, 
                         Pb205t, 
                         R65t, R46t,
                         Pb_blank_total, 
                         Pb_blank_total_std,
                         R64b, R74b, R84b, 
                         Pb_blank_AW, 
                         AWPb204=AWPb204, 
                         AWPb206=AWPb206, 
                         AWPb207=AWPb207, 
                         AWPb208=AWPb208,
                         R64c=None, R74c=None, R84c=None):
    
    # calculate 204Pb blank + initial 
    Pb204b_c = R65m * R46m * ( 1 - FPb) * Pb205t - R65t * R46t * Pb205t # moles
    Pb204b_lab = Pb_blank_total * 1e-12 / Pb_blank_AW / (1 + R64b + R74b + R84b)
    R64c = R64b if R64c is None else R64c
    R74c = R74b if R74c is None else R74c
    R84c = R84b if R84c is None else R84c
    if Pb204b_c < 0:
        raise ValueError("Measured common Pb is negative after tracer subtraction")

    # split cases based on assumed Pb blank total amount
    if Pb204b_c < Pb204b_lab:
        # in case where all 204 is from the lab blank, e.g. zircons
        return {'Pbc_pg': (Pb204b_c * AWPb204 + Pb204b_c * R64b * AWPb206 + Pb204b_c * R74b * AWPb207 + Pb204b_c * R84b * AWPb208) * 1e12,
                'Pb204b': Pb204b_c,
                'Pb206b': Pb204b_c * R64b,
                'Pb207b': Pb204b_c * R74b,
                'Pb208b': Pb204b_c * R84b,
                'Pb204c': 0.0,
                'Pb206c': 0.0,
                'Pb207c': 0.0,
                'Pb208c': 0.0,
                'Pb206b_std': Pb204b_c * R64b * Pb_blank_total_std / Pb_blank_total if Pb_blank_total else 0.0}
    
    else:
        # in case where 204Pb needs to be partitioned between lab blank and initial Pbc from the sample
        return {'Pbc_pg': (Pb204b_lab * (AWPb204 + R64b * AWPb206 + R74b * AWPb207 + R84b * AWPb208) + (Pb204b_c - Pb204b_lab) * (AWPb204 + R64c * AWPb206 + R74c * AWPb207 + R84c * AWPb208)) * 1e12,
                'Pb204b': Pb204b_lab,
                'Pb206b': Pb204b_lab * R64b,
                'Pb207b': Pb204b_lab * R74b,
                'Pb208b': Pb204b_lab * R84b,
                'Pb204c': Pb204b_c - Pb204b_lab,
                'Pb206c': (Pb204b_c - Pb204b_lab) * R64c,
                'Pb207c': (Pb204b_c - Pb204b_lab) * R74c,
                'Pb208c': (Pb204b_c - Pb204b_lab) * R84c,
                'Pb206b_std': Pb204b_lab * R64b * Pb_blank_total_std / Pb_blank_total if Pb_blank_total else 0.0}

def calc_rho_quotient(x, sx, u, su, v, sv):
    '''
    function for calculating the error correlation between two ratios
        this is useful for calculating the error correlation between ratios such as 207Pb/235U-206Pb/238U 
        in the example 75-68 case, x = 207Pb/206Pb, u = 207Pb/235U, v = 206Pb/238U, x = u/v, constant of 58 ratio does not matter
        in terms of relative error (%), we have sx**2 = su**2 + sv**2 - 2*rho*su*sv
        where rho is the error correlation between u and v
        thus rho = (su/u)**2 + (sv/v)**2 - (sx/x)**2 * u * v /2 / (su * sv)

    Parameters
    ----------
    x : float
        ratio x
    sx : float
        absolute standard deviation of ratio x
    u : float
        ratio u
    su : float
        absolute standard deviation of ratio u
    v : float
        ratio v
    sv : float
        absolute standard deviation of ratio v
    '''
    if x > 0 and u > 0 and v > 0 and su > 0 and sv > 0 and sx > 0:
        return ((su/u)**2 + (sv/v)**2 - (sx/x)**2) * u * v /2 / (su * sv)
    else:
        return 0.0

def calc_covariance_squared(x, sx, u, su, v, sv, type='product'):
    '''
    function for calculating the square of the covariance between two ratios
        this is useful for calculating the covariance between ratios such as 207Pb/235U-206Pb/238U 
        in the example 76-65 case, x = 207Pb/205Pb, u = 207Pb/206Pb, v = 206Pb/205Pb, x = u * v

    Parameters
    ----------
    x : float
        ratio x
    sx : float
        absolute standard deviation of ratio x
    u : float
        ratio u
    su : float
        absolute standard deviation of ratio u
    v : float
        ratio v
    sv : float
        absolute standard deviation of ratio v
    type : str
        'product' if x = u * v, 'quotient' if x = u / v
    '''
    if not (x > 0 and u > 0 and v > 0 and su >= 0 and sv >= 0 and sx >= 0):
        return 0.0
    elif type == 'product':
        return u * v * ((sx/x)**2 - (su/u)**2 - (sv/v)**2) / 2
    elif type == 'quotient':
        return u * v * (-(sx/x)**2 + (su/u)**2 + (sv/v)**2) / 2
    else:
        raise ValueError("type must be either 'product' or 'quotient'")


# intermediate terms calculations
#--------------------------------------------------
def Pb206s_partials(R65m, FPb, Pb205t):
    return {
        "dPb206s_dR65m": (1 + FPb) * Pb205t,
        "dPb206s_dR65t": -Pb205t,
        "dPb206s_dFPb": R65m * Pb205t,
        "dPb206s_dPb206b": -1.0,
    }

def Pb206r_partials(R65m, R46m, 
                    FPb, 
                    Pb205t, 
                    R45t,
                    R64b,  Pb206b,
                    R64c, 
):
    return {"dPb206r_dR65m": ((1 + FPb) - R64c * R46m * (1 - FPb)) * Pb205t,
            "dPb206r_dR46m": -R65m * R64c * (1 - FPb) * Pb205t,
            "dPb206r_dR65t": -Pb205t,
            "dPb206r_dR45t": R64c * Pb205t,
            "dPb206r_dFPb": (1 + R64c * R46m) * R65m * Pb205t,
            "dPb206r_dPb206b": R64c/R64b-1.0,
            "dPb206r_dR64b": -Pb206b * R64c / R64b**2,
            "dPb206r_dR64c": (-R46m * R65m * Pb205t * ( 1 - FPb)) + (R45t * Pb205t) + Pb206b/R64b}

def Pb207s_partials(R65m, R76m, 
                    FPb, 
                    Pb205t, 
                    R65t, 
                    R76t, 
                    R76b, 
                    Pb206b):
    return {
        "dPb207s_dR65m": R76m * (1 + 2 * FPb) * Pb205t,
        "dPb207s_dR76m": R65m * (1 + 2 * FPb) * Pb205t,
        "dPb207s_dFPb": 2 * R65m * R76m * Pb205t,
        "dPb207s_dR65t": -R76t * Pb205t,
        "dPb207s_dR76t": -R65t * Pb205t,
        "dPb207s_dPb206b": -R76b,
        "dPb207s_dR76b": -Pb206b,
    }

def Pb207r_partials(R65m, R76m, R46m,
                    FPb, 
                    Pb205t, 
                    R45t,
                    R65t, 
                    R76t, 
                    R76b, 
                    R64b,
                    Pb206b, 
                    R64c,
                    R76c):
    return {"dPb207r_dR65m": (R76m * (1 + 2 * FPb) - R64c * R76c * R46m * ( 1 - FPb)) * Pb205t,
            "dPb207r_dR76m": R65m * (1 + 2 * FPb) * Pb205t,
            "dPb207r_dR46m": -R64c * R76c * R65m * (1 - FPb) * Pb205t,
            "dPb207r_dFPb": (2 * R76m + R64c * R76c * R46m) * R65m * Pb205t,

            "dPb207r_dR65t": -R76t * Pb205t,
            "dPb207r_dR76t": -R65t * Pb205t,
            "dPb207r_dR45t": R64c * R76c * Pb205t,
            "dPb207r_dPb206b": -R76b + R64c * R76c / R64b,
            "dPb207r_dR64b": -Pb206b * R64c * R76c / R64b **2,
            "dPb207r_dR76b": -Pb206b,
            "dPb207r_dR64c": (-R46m * R65m * Pb205t * R76c * (1 - FPb)) + (R45t * R76c * Pb205t) + (Pb206b * R76c / R64b),
            "dPb207r_dR76c": (-R46m * R65m * Pb205t * R64c * (1 - FPb)) + (R45t * R64c * Pb205t) + (Pb206b * R64c / R64b),}

def Pb204c_partials(R46m, R65m, 
                    FPb, 
                    Pb205t, 
                    R46t, 
                    R65t, 
                    Pb206b, 
                    R64b):
    return {
        "dPb204c_dR46m": R65m * (1 - FPb) * Pb205t,
        "dPb204c_dR65m": R46m * (1 - FPb) * Pb205t,
        "dPb204c_dFPb": -R46m * R65m * Pb205t,
        "dPb204c_dR46t": -R65t * Pb205t,
        "dPb204c_dR65t": -R46t * Pb205t,
        "dPb204c_dPb206b": -1.0 / R64b,
        "dPb204c_dR64b": Pb206b / R64b**2,
    }

def FU_partials(R35m, R85m,
                R35t, R85t,
                common_U238_U235=common_U238_U235):
    
    denom = 2 * R35m * (R85t - common_U238_U235) + 3 * R35t * R85m

    return {
        "dFU_dR35t": (common_U238_U235 - R85m) / denom - (3 * R85m * (R35t * (common_U238_U235 - R85m) + R35m * (R85t - common_U238_U235))) / denom**2,
        "dFU_dR85m": -R35t / denom - (3 * R35t * (R35t * (common_U238_U235 - R85m) + R35m * (R85t - common_U238_U235))) / denom**2,
        "dFU_dR35m": (R85t - common_U238_U235) / denom - (2 * (R85t - common_U238_U235) * (R35t * (common_U238_U235 - R85m) + R35m * (R85t - common_U238_U235))) / denom**2,
        "dFU_dR85t": R35m / denom - (2 * R35m * (R35t * (common_U238_U235 - R85m) + R35m * (R85t - common_U238_U235))) / denom**2,
    }

def U238s_partials(R85m, FU, U235t, R85t, U238b, common_U238_U235=common_U238_U235):
    denom = 1 - R85m / common_U238_U235 * (1 + 3 * FU)
    numer = U235t * R85m * (1 + 3 * FU) - (R85t * U235t) - U238b
    return {
        "dU238s_dR85m": (U235t * (1 + 3 * FU)) / denom + numer / denom**2 * (1 + 3 * FU) / common_U238_U235,
        "dU238s_dR85t": -U235t / denom,
        "dU238s_dU238b": -1 / denom,
        "dU238s_dFU": (3 * U235t * R85m) / denom + numer / denom**2 * (3 * R85m) / common_U238_U235,
    }

def U235s_partials(common_U238_U235=common_U238_U235):
    return {
        "dU235s_dU238s": 1 / common_U238_U235,
    }

def Pb_covariance_squared(R75m, R75m_std, 
                          R76m, R76m_std, 
                          R65m, R65m_std, 
                          R45m, R45m_std,
                          R46m, R46m_std,
                          R84m, R84m_std,
                          R85m, R85m_std,
                          R75t, R75t_std,
                          R76t, R76t_std,
                          R65t, R65t_std,
                          R45t, R45t_std,
                          R46t, R46t_std,
                          R84t, R84t_std,
                          R85t, R85t_std,
                          R64b, R64b_std,
                          R84b, R84b_std,
                          R86b, R86b_std):
    return {"cov_76_65_m": calc_covariance_squared(R75m, R75m_std, R76m, R76m_std, R65m, R65m_std, type='product'),
            "cov_76_65_t": calc_covariance_squared(R75t, R75t_std, R76t, R76t_std, R65t, R65t_std, type='product'),
            "cov_65_46_m": calc_covariance_squared(R45m, R45m_std, R65m, R65m_std, R46m, R46m_std, type='product'),
            "cov_45_65_t": calc_covariance_squared(R46t, R46t_std, R45t, R45t_std, R65t, R65t_std,  type='quotient'),
            "cov_65_46_t": calc_covariance_squared(R45t, R45t_std, R65t, R65t_std, R46t, R46t_std, type='product'),
            "cov_85_45_m": calc_covariance_squared(R84m, R84m_std, R85m, R85m_std, R45m, R45m_std, type='quotient'),
            "cov_85_45_t": calc_covariance_squared(R84t, R84t_std, R85t, R85t_std, R45t, R45t_std, type='quotient'),
            "cov_86_64_b": calc_covariance_squared(R84b, R84b_std, R86b, R86b_std, R64b, R64b_std, type='product')
            }

def U_covariance_squared(R83m, R83m_std,
                         R85m, R85m_std,
                         R35m, R35m_std,
                         R83t, R83t_std,
                         R85t, R85t_std,
                         R35t, R35t_std):
        return {"cov_85_35_m": calc_covariance_squared(R83m, R83m_std, R85m, R85m_std, R35m, R35m_std, type='quotient'),
                "cov_85_35_t": calc_covariance_squared(R83t, R83t_std, R85t, R85t_std, R35t, R35t_std, type='quotient')}

# individual isotope amount calculations
#--------------------------------------------------
def calc_Pb206s(R65m, FPb, 
                Pb205t, 
                R65t, 
                Pb206b):
    """
    Calculate measured 206Pb in sample (Pb206s)

    Parameters
    ----------
    R65m : float
        Measured total 206Pb/205Pb ratio
    Pb205t : float
        Tracer solution 205Pb amount (moles_g)
    FPb : float
        Coefficient for linear Pb fractionation correction per unit mass difference
    R65t : float
        Tracer solution 206Pb/205Pb ratio
    Pb206b : float
        Blank 206Pb amount (moles_g)
    """
    Pb206s = R65m * Pb205t * (1 + FPb) - R65t * Pb205t - Pb206b
    return Pb206s

def prop_Pb206s_uncertainty(dPb206s_dR65m, R65m_std,
                            dPb206s_dFPb, FPb_std,
                            dPb206s_dR65t, R65t_std,
                            dPb206s_dPb206b, Pb206b_std):
    return np.sqrt( (dPb206s_dR65m * R65m_std)**2 +
                    (dPb206s_dFPb * FPb_std)**2 +
                    (dPb206s_dR65t * R65t_std)**2 +
                    (dPb206s_dPb206b * Pb206b_std)**2)

def calc_Pb206s_uncertainty(R65m, R65m_std, 
                            FPb, FPb_std, 
                            Pb205t, 
                            R65t_std, Pb206b_std):
    """
    Calculate uncertainty of measured 206Pb in sample (Pb206s)

    Parameters
    ----------
    R65m : float
        Measured total 206Pb/205Pb ratio
    R65m_std : float
        Standard deviation of measured total 206Pb/205Pb ratio
    Pb205t : float
        Tracer solution 205Pb amount (moles_g)
    Pb205t_std : float
        Standard deviation of tracer solution 205Pb amount (moles_g)
    FPb : float
        Coefficient for linear Pb fractionation correction per unit mass difference
    FPb_std : float
        Standard deviation of coefficient for linear Pb fractionation correction per unit mass difference
    R65t : float
        Tracer solution 206Pb/205Pb ratio
    R65t_std : float
        Standard deviation of tracer solution 206Pb/205Pb ratio
    Pb206b : float
        Blank 206Pb amount (moles_g)
    Pb206b_std : float
        Standard deviation of blank 206Pb amount (moles_g)
    """
    term1 = (Pb205t * (1 + FPb) * R65m_std) ** 2
    term2 = (Pb205t * R65t_std) ** 2
    term3 = (R65m * Pb205t * FPb_std) ** 2
    term4 = Pb206b_std ** 2

    Pb206s_std = np.sqrt(term1 + term2 + term3 + term4)
    return Pb206s_std

def calc_Pb207s(R65m, R76m, 
                FPb, 
                Pb205t, R65t, R76t, 
                R76b, Pb206b):
    """
    Calculate measured 207Pb in sample (Pb207s)

    Parameters
    ----------
    R65m : float
        Measured total 206Pb/205Pb ratio
    R76m : float
        Measured total 207Pb/206Pb ratio
    FPb : float
        Coefficient for linear Pb fractionation correction per unit mass difference
    Pb205t : float
        Tracer solution 205Pb amount (moles_g)
    R65t : float
        Tracer solution 206Pb/205Pb ratio
    R76t : float
        Tracer solution 207Pb/206Pb ratio
    R76b : float
        Blank 207Pb/206Pb ratio
    Pb206b : float
        Blank 206Pb amount (moles_g)
    """
    Pb207s = R65m * R76m * Pb205t * (1 + 2 * FPb) - R65t * R76t * Pb205t - R76b * Pb206b
    return Pb207s

def prop_Pb207s_uncertainty(dPb207s_dR65m, R65m_std,
                            dPb207s_dR76m, R76m_std,
                            dPb207s_dFPb, FPb_std,
                            dPb207s_dR65t, R65t_std,
                            dPb207s_dR76t, R76t_std,
                            dPb207s_dPb206b, Pb206b_std,
                            dPb207s_dR76b, R76b_std, 
                            cov_76_65_m, cov_76_65_t):
    return np.sqrt( (dPb207s_dR65m * R65m_std)**2 +
                    (dPb207s_dR76m * R76m_std)**2 +
                    (dPb207s_dFPb * FPb_std)**2 +
                    (dPb207s_dR65t * R65t_std)**2 +
                    (dPb207s_dR76t * R76t_std)**2 +
                    (dPb207s_dPb206b * Pb206b_std)**2 +
                    (dPb207s_dR76b * R76b_std)**2 + 
                    2 * cov_76_65_m * dPb207s_dR76m * dPb207s_dR65m +
                    2 * cov_76_65_t * dPb207s_dR76t * dPb207s_dR65t )

def calc_Pb207s_uncertainty(R65m, R65m_std, 
                           R76m, R76m_std, 
                           R75m, R75m_std,
                           FPb, FPb_std, 
                           Pb205t, 
                           R65t, R65t_std, 
                           R76t, R76t_std, 
                           R76b, R76b_std, 
                           Pb206b, Pb206b_std, *, R75t=None, R75t_std=None):
    """
    Calculate uncertainty of measured 207Pb in sample (Pb207s)

    Parameters
    ----------
    R65m : float
        Measured total 206Pb/205Pb ratio
    R65m_std : float
        Standard deviation of measured total 206Pb/205Pb ratio
    R76m : float
        Measured total 207Pb/206Pb ratio
    R76m_std : float
        Standard deviation of measured total 207Pb/206Pb ratio
    R75m : float
        Measured total 207Pb/205Pb ratio
    R75m_std : float
        Standard deviation of measured total 207Pb/205Pb ratio
    FPb : float
        Coefficient for linear Pb fractionation correction per unit mass difference
    FPb_std : float
        Standard deviation of coefficient for linear Pb fractionation correction per unit mass difference
    Pb205t : float
        Tracer solution 205Pb amount (moles_g)
    R65t : float
        Tracer solution 206Pb/205Pb ratio
    R65t_std : float
        Standard deviation of tracer solution 206Pb/205Pb ratio
    R76t : float
        Tracer solution 207Pb/206Pb ratio
    R76t_std : float
        Standard deviation of tracer solution 207Pb/206Pb ratio
    R76b : float
        Blank 207Pb/206Pb ratio
    R76b_std : float
        Standard deviation of blank 207Pb/206Pb ratio
    Pb206b : float
        Blank 206Pb amount (moles_g)
    Pb206b_std : float
        Standard deviation of blank 206Pb amount (moles_g)
    """
    # uncorrelated error propagation
    term1 = (R76m * Pb205t * (1 + 2 * FPb) * R65m_std) ** 2
    term2 = (R65m * Pb205t * (1 + 2 * FPb) * R76m_std) ** 2
    term3 = (2 * R65m * R76m * Pb205t * FPb_std) ** 2
    term4 = (R76t * Pb205t * R65t_std) ** 2
    term5 = (R65t * Pb205t * R76t_std) ** 2
    term6 = (R76b_std * Pb206b) ** 2
    term7 = (R76b * Pb206b_std) ** 2

    # covariant error propagation
    cov_76_65_m = calc_covariance_squared(R75m, R75m_std, R76m, R76m_std, R65m, R65m_std, type='product')
    # A measured 207/205 error cannot determine tracer 207/206–206/205
    # covariance. When no tracer 207/205 error is supplied, assume zero.
    if (R75t is None) != (R75t_std is None):
        raise ValueError("Supply both R75t and R75t_std")
    cov_76_65_t = (calc_covariance_squared(R75t, R75t_std, R76t, R76t_std,
                                         R65t, R65t_std, type='product')
                   if R75t is not None else 0.0)

    term8 = 2 * cov_76_65_m * (R76m * Pb205t * (1 + 2 * FPb)) * R65m * Pb205t * (1 + 2 * FPb)
    term9 = 2 * cov_76_65_t * (R65t * Pb205t) * R76t * Pb205t

    Pb207s_std = np.sqrt(term1 + term2 + term3 + term4 + term5 + term6 + term7 + term8 + term9)

    return Pb207s_std

def calc_Pb204c(R46m, R65m, 
               FPb, 
               Pb205t, R46t, R65t, 
               Pb206b, R64b):
    """
    Calculate initial 204Pb in sample (Pb204c)

    Parameters
    ----------
    R46m : float
        Measured total 204Pb/206Pb ratio
    R65m : float
        Measured total 206Pb/205Pb ratio
    FPb : float
        Coefficient for linear Pb fractionation correction per unit mass difference
    Pb205t : float
        Tracer solution 205Pb amount (moles_g)
    R46t : float
        Tracer solution 204Pb/206Pb ratio
    R65t : float
        Tracer solution 206Pb/205Pb ratio
    Pb206b : float
        Blank 206Pb amount (moles_g)
    R64b : float
        Blank 204Pb/206Pb ratio
    """
    Pb204c = R46m * R65m * Pb205t * (1 - FPb) - R46t * R65t * Pb205t - Pb206b / R64b
    return Pb204c

def prop_Pb204c_uncertainty(dPb204c_dR46m, R46m_std,
                            dPb204c_dR65m, R65m_std,
                            dPb204c_dFPb, FPb_std,
                            dPb204c_dR46t, R46t_std,
                            dPb204c_dR65t, R65t_std,
                            dPb204c_dPb206b, Pb206b_std,
                            dPb204c_dR64b, R64b_std,
                            cov_65_46_m, cov_65_46_t):
    return np.sqrt( (dPb204c_dR46m * R46m_std)**2 +
                    (dPb204c_dR65m * R65m_std)**2 +
                    (dPb204c_dFPb * FPb_std)**2 +
                    (dPb204c_dR46t * R46t_std)**2 +
                    (dPb204c_dR65t * R65t_std)**2 +
                    (dPb204c_dPb206b * Pb206b_std)**2 +
                    (dPb204c_dR64b * R64b_std)**2 +
                    2 * cov_65_46_m * dPb204c_dR65m * dPb204c_dR46m +
                    2 * cov_65_46_t * dPb204c_dR65t * dPb204c_dR46t )

def calc_Pb204c_uncertainty(R46m, R46m_std,
                           R65m, R65m_std,
                           R45m, R45m_std,
                           FPb, FPb_std,
                           Pb205t,
                           R46t, R46t_std,
                           R65t, R65t_std,
                           R45t, R45t_std,
                           Pb206b, Pb206b_std,
                           R64b, R64b_std):
    """
    Calculate uncertainty of initial 204Pb in sample (Pb204c)

    Parameters
    ----------
    R46m : float
        Measured total 204Pb/206Pb ratio
    R46m_std : float
        Standard deviation of measured total 204Pb/206Pb ratio
    R65m : float
        Measured total 206Pb/205Pb ratio
    R65m_std : float
        Standard deviation of measured total 206Pb/205Pb ratio
    R45m : float
        Measured total 204Pb/205Pb ratio
    R45m_std : float
        Standard deviation of measured total 204Pb/205Pb ratio
    FPb : float
        Coefficient for linear Pb fractionation correction per unit mass difference
    FPb_std : float
        Standard deviation of coefficient for linear Pb fractionation correction per unit mass difference
    Pb205t : float
        Tracer solution 205Pb amount (moles_g)
    R46t : float
        Tracer solution 204Pb/206Pb ratio
    R46t_std : float
        Standard deviation of tracer solution 204Pb/206Pb ratio
    R65t : float
        Tracer solution 206Pb/205Pb ratio
    R65t_std : float
        Standard deviation of tracer solution 206Pb/205Pb ratio
    R45t : float
        Tracer solution 204Pb/205Pb ratio
    R45t_std : float
        Standard deviation of tracer solution 204Pb/205Pb ratio
    Pb206b : float
        Blank 206Pb amount (moles_g)
    Pb206b_std : float
        Standard deviation of blank 206Pb amount (moles_g)
    R64b : float
        Blank 204Pb/206Pb ratio
    R64b_std : float
        Standard deviation of blank 204Pb/206Pb ratio
    """
    # uncorrelated error propagation
    term1 = (R46m * Pb205t * (1 - FPb) * R65m_std) ** 2
    term2 = (R65m * Pb205t * (1 - FPb) * R46m_std) ** 2
    term3 = (R46t * Pb205t * R65t_std) ** 2
    term4 = (R65t * Pb205t * R46t_std) ** 2
    term5 = (R46m * R65m * Pb205t * FPb_std) ** 2
    term6 = (Pb206b_std / R64b) ** 2
    term7 = (Pb206b * R64b_std / R64b ** 2) ** 2

    # covariant error propagation
    cov_65_46_m = calc_covariance_squared(R45m, R45m_std, R65m, R65m_std, R46m, R46m_std, type='product')
    cov_65_46_t = calc_covariance_squared(R45t, R45t_std, R65t, R65t_std, R46t, R46t_std, type='product')

    term8 = 2 * cov_65_46_m * (R65m * Pb205t * (1 - FPb)) * R46m * Pb205t * (1 - FPb)
    term9 = 2 * cov_65_46_t * (R65t * Pb205t) * (R46t * Pb205t)


    Pb204c_std = np.sqrt(term1 + term2 + term3 + term4 + term5 + term6 + term7 + term8 + term9)
    return Pb204c_std


def calc_FPb_2535(R25m, R25m_std, R25t, R25t_std):
    """Pb mass fractionation per amu from a 202Pb-205Pb double spike.

    Linear law over the 3 amu from 202 to 205, as in the BSU UPbR sheet
    ('Data Reduction Engine' rows 332-338) and ET_Redux AlphaPb:
    ``FPb = (1 - R25t/R25m)/3``. Returns ``(FPb, FPb_std)``; the 1σ treats
    the measured and tracer 202/205 as independent, as the sheet does.
    """
    FPb = (1 - R25t / R25m) / 3
    dFPb_dR25t = -1 / (3 * R25m)
    dFPb_dR25m = R25t / (3 * R25m**2)
    FPb_std = np.sqrt((dFPb_dR25t * R25t_std)**2 + (dFPb_dR25m * R25m_std)**2)
    return FPb, FPb_std

def calc_FU(R35m, R85m,
            R35t, R85t, 
           common_U238_U235=common_U238_U235):
    """
    Calculate U fractionation factor F_U

    Parameters
    ----------
    R35t : float
        Tracer solution 235U/238U ratio
    R35m : float
        Measured total 235U/238U ratio
    R85t : float
        Tracer solution 238U/235U ratio
    R85m : float
        Measured total 238U/235U ratio
    """
    FU = (R35t * (common_U238_U235 - R85m) + R35m * (R85t - common_U238_U235)) / (2 * R35m * (R85t - common_U238_U235) + 3 * R35t * R85m)
    return FU

def prop_FU_uncertainty(dFU_dR35t, R35t_std,
                        dFU_dR85m, R85m_std,
                        dFU_dR35m, R35m_std,
                        dFU_dR85t, R85t_std,
                        cov_85_35_m, cov_85_35_t):
    return np.sqrt( (dFU_dR35t * R35t_std)**2 +
                    (dFU_dR85m * R85m_std)**2 +
                    (dFU_dR35m * R35m_std)**2 +
                    (dFU_dR85t * R85t_std)**2 +
                    2 * cov_85_35_m * dFU_dR85m * dFU_dR35m +
                    2 * cov_85_35_t * dFU_dR85t * dFU_dR35t )

def calc_FU_uncertainty(R35m, R35m_std,
                        R85m, R85m_std,
                        R83m, R83m_std,
                        R35t, R35t_std,
                        R85t, R85t_std,
                        R83t, R83t_std,
                        common_U238_U235=common_U238_U235):
    """
    Calculate uncertainty of U fractionation factor F_U

    Parameters
    ----------
    R35t : float
        Tracer solution 235U/238U ratio
    R35t_std : float
        Standard deviation of tracer solution 235U/238U ratio
    R35m : float
        Measured total 235U/238U ratio
    R35m_std : float
        Standard deviation of measured total 235U/238U ratio
    R85t : float
        Tracer solution 238U/235U ratio
    R85t_std : float
        Standard deviation of tracer solution 238U/235U ratio
    R85m : float
        Measured total 238U/235U ratio
    R85m_std : float
        Standard deviation of measured total 238U/235U ratio
    """
    # partial derivatives
    dFU_dR35t = (common_U238_U235 - R85m) / (2 * R35m * (R85t - common_U238_U235) + 3 * R35t * R85m) - (3 * R85m * (R35t * (R85m - common_U238_U235) + R35m * (common_U238_U235 - R85t))) / (2 * R35m * (R85t - common_U238_U235) + 3 * R35t * R85m) ** 2 

    dFU_dR85m = -R35t / (2 * R35m * (R85t - common_U238_U235) + 3 * R35t * R85m) - (3 * R35t * (R35t * (common_U238_U235 - R85m) + R35m * (R85t - common_U238_U235))) / (2 * R35m * (R85t - common_U238_U235) + 3 * R35t * R85m) ** 2

    dFU_dR35m = (R85t - common_U238_U235) / (2 * R35m * (R85t - common_U238_U235) + 3 * R35t * R85m) - (2 * (R85t - common_U238_U235) * (R35t * (common_U238_U235 - R85m) + R35m * (R85t - common_U238_U235))) / (2 * R35m * (R85t - common_U238_U235) + 3 * R35t * R85m) ** 2

    dFU_dR85t = R35m / (2 * R35m * (R85t - common_U238_U235) + 3 * R35t * R85m) - (2 * R35m * (R35t * (common_U238_U235 - R85m) + R35m * (R85t - common_U238_U235))) / (2 * R35m * (R85t - common_U238_U235) + 3 * R35t * R85m) ** 2 

    # covariance terms
    cov_85_35_m = calc_covariance_squared(R83m, R83m_std, R85m, R85m_std, R35m, R35m_std, type='quotient')
    cov_85_35_t = calc_covariance_squared(R83t, R83t_std, R85t, R85t_std, R35t, R35t_std, type='quotient')

    term1 = (dFU_dR35t * R35t_std) ** 2
    term2 = (dFU_dR85m * R85m_std) ** 2
    term3 = (dFU_dR35m * R35m_std) ** 2
    term4 = (dFU_dR85t * R85t_std) ** 2
    term5 = 2 * cov_85_35_m * dFU_dR85m * dFU_dR35m
    term6 = 2 * cov_85_35_t * dFU_dR85t * dFU_dR35t

    FU_std = np.sqrt(term1 + term2 + term3 + term4 + term5 + term6)
    return FU_std

def calc_U238s(R85m, FU, U235t, R85t, U238b, common_U238_U235=common_U238_U235):
    """
    Calculate measured 238U in sample (U238s)

    Parameters
    ----------
    R85m : float
        Measured total 238U/235U ratio
    FU : float
        Coefficient for linear U fractionation correction per unit mass difference
    U235t : float
        Tracer solution 235U amount (moles_g)
    R85t : float
        Tracer solution 238U/235U ratio
    U238b : float
        Blank 238U amount (moles_g)
    common_U238_U235 : float, optional
        Natural 238U/235U ratio, by default common_U238_U235
    """
    U238s = (U235t * R85m * (1 + 3 * FU) - (R85t * U235t) - U238b) / (1 - R85m / common_U238_U235 * (1 + 3 * FU))
    return U238s

def prop_U238s_uncertainty(dU238s_dR85m, R85m_std,
                           dU238s_dFU, FU_std,
                           dU238s_dR85t, R85t_std,
                           dU238s_dU238b, U238b_std):
    return np.sqrt( (dU238s_dR85m * R85m_std)**2 +
                    (dU238s_dFU * FU_std)**2 + 
                    (dU238s_dR85t * R85t_std)**2 +
                    (dU238s_dU238b * U238b_std)**2 )

def calc_U238s_uncertainty(R85m, R85m_std, 
                          FU, FU_std, 
                          U235t, 
                          R85t, R85t_std, 
                          U238b, U238b_std,
                          common_U238_U235=common_U238_U235):
    """
    Calculate uncertainty of measured 238U in sample (U238s)

    Parameters
    ----------
    R85m : float
        Measured total 238U/235U ratio
    R85m_std : float
        Standard deviation of measured total 238U/235U ratio
    FU : float
        Coefficient for linear U fractionation correction per unit mass difference
    FU_std : float
        Standard deviation of coefficient for linear U fractionation correction per unit mass difference
    U235t : float
        Tracer solution 235U amount (moles_g)
    R85t : float
        Tracer solution 238U/235U ratio
    R85t_std : float
        Standard deviation of tracer solution 238U/235U ratio
    U238b : float
        Blank 238U amount (moles_g)
    U238b_std : float
        Standard deviation of blank 238U amount (moles_g)
    common_U238_U235 : float, optional
        Natural 238U/235U ratio, by default common_U238_U235
    """
    # partial derivatives
    dU238s_dR85m = (U235t * (1 + 3 * FU)) / (1 - R85m / common_U238_U235 * (1 + 3 * FU)) + (U235t * R85m * (1 + 3 * FU) - R85t * U235t - U238b) / (1 - R85m / common_U238_U235 * (1 + 3 * FU)) ** 2 * (1 + 3 * FU) / common_U238_U235

    dU238s_dR85t = -U235t / (1 - R85m / common_U238_U235 * (1 + 3 * FU))

    dU238s_dU238b = -1 / (1 - R85m / common_U238_U235 * (1 + 3 * FU))

    dU238s_dFU = (3 * U235t * R85m) / (1 - R85m / common_U238_U235 * (1 + 3 * FU)) + (U235t * R85m * (1 + 3 * FU) - R85t * U235t - U238b) / (1 - R85m / common_U238_U235 * (1 + 3 * FU)) ** 2 * (3 * R85m) / common_U238_U235

    # uncorrelated error propagation
    term1 = (dU238s_dR85m * R85m_std) ** 2
    term2 = (dU238s_dR85t * R85t_std) ** 2
    term3 = (dU238s_dU238b * U238b_std) ** 2
    term4 = (dU238s_dFU * FU_std) ** 2

    U238s_std = np.sqrt(term1 + term2 + term3 + term4)
    return U238s_std

def calc_U235s(U238s, common_U238_U235=common_U238_U235):
    """
    Calculate measured 235U in sample (U235s)

    Parameters
    ----------
    U238s : float
        Measured 238U in sample (moles_g)
    common_U238_U235 : float, optional
        Natural 238U/235U ratio, by default common_U238_U235
    """
    U235s = U238s / common_U238_U235
    return U235s

def prop_U235s_uncertainty(dU235s_dU238s, U238s_std):
    return np.sqrt( (dU235s_dU238s * U238s_std) ** 2 )

def calc_U235s_uncertainty(U238s_std, common_U238_U235=common_U238_U235):
    """
    Calculate uncertainty of measured 235U in sample (U235s)

    Parameters
    ----------
    U238s : float
        Measured 238U in sample (moles_g)
    U238s_std : float
        Standard deviation of measured 238U in sample (moles_g)
    common_U238_U235 : float, optional
        Natural 238U/235U ratio, by default common_U238_U235
    """
    U235s_std = np.sqrt( (U238s_std / common_U238_U235) ** 2 )
    return U235s_std

def calc_rad_U(U238s, U235s, AWU238=AWU238, AWU235=AWU235):
    '''
    calculate total radiogenic U in sample (in ng)
    '''
    return (U238s * AWU238 + U235s * AWU235) * 1e9


def calc_total_U_ppm(sample_weight, U_ng):
    '''
    calculate total U in sample (in ppm)

    Parameters
    ----------
    sample_weight : float
        Sample weight (in milligrams)
    U_ng : float
        Total U in sample (in nanograms)
    '''
    return U_ng / sample_weight
                      
# isotope ratio calculations
#--------------------------------------------------
def calc_PbPb_Rs(Pb206s, Pb207s, Pb204c):
    """
    Calculate sample Pb-Pb ratios

    Parameters
    ----------
    Pb206s : float
        Measured 206Pb in sample (moles)
    Pb207s : float
        Measured 207Pb in sample (moles)
    Pb204c : float
        Initial 204Pb in sample (moles)
    """
    if Pb204c > 0:
        return {"R46s": Pb204c / Pb206s,
                "R47s": Pb204c / Pb207s,
                "R74s": Pb207s / Pb204c,
                "R76s": Pb207s / Pb206s}
    elif Pb204c == 0:
        return {"R46s": Pb204c / Pb206s,
                "R47s": Pb204c / Pb207s,
                "R74s": 0.0,
                "R76s": Pb207s / Pb206s}
    else:
        raise ValueError("Pb204c must be non-negative")

def calc_UPb_Rs(U238s, U235s, Pb206s, Pb207s, Pb204c):
    """
    calculate sample U-Pb ratios

    Parameters
    ----------
    U238s : float
        Measured 238U in sample (moles)
    U235s : float
        Measured 235U in sample (moles)   
    Pb206s : float
        Measured 206Pb in sample (moles)
    Pb207s : float
        Measured 207Pb in sample (moles)
    Pb204c : float
        Initial 204Pb in sample (moles)
    """
    if Pb204c > 0:
        return {"R54s": U235s / Pb204c,
                "R57s": U235s / Pb207s,
                "R84s": U238s / Pb204c,
                "R86s": U238s / Pb206s,
                "R87s": U238s / Pb207s}
    elif Pb204c == 0:
        return {"R54s": 0.0,
                "R57s": U235s / Pb207s,
                "R84s": 0.0,
                "R86s": U238s / Pb206s,
                "R87s": U238s / Pb207s}
    else:
        raise ValueError("Pb204c must be non-negative")

def calc_R76r(Pb206r, Pb207r):
    return Pb207r / Pb206r

def calc_UPb_Rr(U238s, U235s, Pb206r, Pb207r):
    '''
    calculate radiogenic U-Pb ratios with the assumption that all U measured is from the sample

    Parameters
    ----------
    U238s : float
        Measured 238U in sample (moles)
    U235s : float
        Measured 235U in sample (moles)   
    Pb206r : float
        Radiogenic 206Pb in sample (moles)
    Pb207r : float
        Radiogenic 207Pb in sample (moles)
    '''
    return {"R68r": Pb206r / U238s,
            "R86r": U238s / Pb206r,
            "R75r": Pb207r / U235s,
            "R87r": U238s / Pb207r}


# isotope ratio error propagations
#--------------------------------------------------
def prop_cov_Pb_R76s_squared(dPb207s_dR65m, dPb206s_dR65m, R65m_std,
                             dPb207s_dFPb, dPb206s_dFPb, FPb_std,
                             dPb207s_dR65t, dPb206s_dR65t, R65t_std,
                             dPb207s_dPb206b, dPb206s_dPb206b, Pb206b_std):
    
    return ((dPb207s_dR65m * dPb206s_dR65m) * R65m_std**2 +
            (dPb207s_dFPb * dPb206s_dFPb) * FPb_std**2 +
            (dPb207s_dR65t * dPb206s_dR65t) * R65t_std**2 +
            (dPb207s_dPb206b * dPb206s_dPb206b) * Pb206b_std**2)

def calc_cov_Pb_R76s_squared(R65m, R65m_std,
                             R76m, 
                             FPb, FPb_std,
                             Pb205t,
                             R65t,
                             R76b, 
                             Pb206b_std):
    
    return (R76m * (1 + 2 * FPb) * Pb205t) * ((1 + FPb) * Pb205t) * R65m_std**2 + R76t * Pb205t**2 * R65t_std**2 + 2 * R76m * (R65m * Pb205t)**2 * FPb_std**2 + R76b * Pb206b_std**2

def prop_cov_Pb_R46s_squared(dPb204c_dR65m, dPb206s_dR65m, R65m_std,
                             dPb204c_dFPb, dPb206s_dFPb, FPb_std,
                             dPb204c_dR65t, dPb206s_dR65t, R65t_std,
                             dPb204c_dPb206b, dPb206s_dPb206b, Pb206b_std):
    
    return ((dPb204c_dR65m * dPb206s_dR65m) * R65m_std**2 +
            (dPb204c_dFPb * dPb206s_dFPb) * FPb_std**2 +
            (dPb204c_dR65t * dPb206s_dR65t) * R65t_std**2 +
            (dPb204c_dPb206b * dPb206s_dPb206b) * Pb206b_std**2)

def calc_cov_Pb_R46s_squared(R65m, R65m_std, 
                             R46m, 
                             FPb, FPb_std,
                             Pb205t,
                             R46t,
                             R65t_std,
                             R64b,
                             Pb206b_std):
    
    return (R46m * (1 - FPb) * Pb205t) * ( (1 + FPb) * Pb205t * R65m_std**2) + ( -R46t * Pb205t) * (-Pb205t) * R65t_std**2 + (-R46m * R65m * Pb205t) * (R65m * Pb205t) * FPb_std**2 + ( -1/R64b) * (-1 * Pb206b_std ** 2) 

def prop_cov_Pb_R47s_squared(dPb207s_dR65m, dPb204c_dR65m, R65m_std,
                             dPb207s_dFPb, dPb204c_dFPb, FPb_std,
                             dPb207s_dR65t, dPb204c_dR65t, R65t_std,
                             dPb207s_dPb206b, dPb204c_dPb206b, Pb206b_std):
    
    return ((dPb207s_dR65m * dPb204c_dR65m) * R65m_std**2 +
            (dPb207s_dFPb * dPb204c_dFPb) * FPb_std**2 +
            (dPb207s_dR65t * dPb204c_dR65t) * R65t_std**2 +
            (dPb207s_dPb206b * dPb204c_dPb206b) * Pb206b_std**2)

def calc_cov_Pb_R47s_squared(R65m, R65m_std, 
                             R76m, 
                             R46m, 
                             FPb, FPb_std,
                             Pb205t,
                             R46t,
                             R65t_std,
                             R76t,
                             R76b,
                             R64b,
                             Pb206b_std):   
    return (R46m * (1 - FPb) * Pb205t) * (R76m * (1 + 2 * FPb) * Pb205t * R65m_std**2) + (-R46t * Pb205t) * ( -R76t * Pb205t) * R65t_std**2 + (-R46m * R65m * Pb205t) * ( 2 * R76m * R65m * Pb205t * FPb_std**2) + ( -1/ R64b * (-R76b) * Pb206b_std ** 2)

def calc_PbPb_uncertainty(Pb20X, Pb20Y, Pb20X_std, Pb20Y_std, cov_Pb_RXY_squared):
    '''
    calculate relative and absolute uncertainty of a Pb isotope ratio
    applies to both sample total Pb-Pb ratios and radiogenic Pb-Pb ratios

    Parameters
    ----------
    Pb20X : float
        Measured 20X Pb isotope in sample (moles_g)
    Pb20Y : float
        Measured 20Y Pb isotope in sample (moles_g)
    Pb20X_std : float
        Standard deviation of measured 20X Pb isotope in sample (moles_g)
    Pb20Y_std : float
        Standard deviation of measured 20Y Pb isotope in sample (moles_g)
    cov_Pb_RXY_squared : float
        Covariance squared between Pb20X and Pb20Y
    '''
    if Pb20X > 0 and Pb20Y > 0:
        rel_std_Pb_RXY = np.sqrt( (Pb20X_std / Pb20X) ** 2 + (Pb20Y_std / Pb20Y) ** 2 - 2 * cov_Pb_RXY_squared / (Pb20X * Pb20Y) )

        abs_std_Pb_RXY = Pb20X / Pb20Y * rel_std_Pb_RXY

    else:
        rel_std_Pb_RXY = 0.0
        abs_std_Pb_RXY = 0.0

    return {"rel_std": rel_std_Pb_RXY,
            "abs_std": abs_std_Pb_RXY}

def calc_UPb_uncertainty(U23X, Pb20Y, U23X_std, Pb20Y_std):
    '''
    calculate relative and absolute uncertainty of a U-Pb isotope ratio 
    applies to both sample total U-Pb ratios and radiogenic U-Pb ratios

    Parameters
    ----------
    U23X : float
        Measured 23X U isotope in sample (moles_g)
    Pb20Y : float
        Measured 20Y Pb isotope in sample (moles_g)
    U23X_std : float
        Standard deviation of measured 23X U isotope in sample (moles_g)
    Pb20Y_std : float
        Standard deviation of measured 20Y Pb isotope in sample (moles_g)
    '''
    if Pb20Y > 0 and U23X > 0:
        rel_std_UPb_RXY = np.sqrt( (U23X_std / U23X) ** 2 + (Pb20Y_std / Pb20Y) ** 2)

        abs_std_UPb_RXY = U23X / Pb20Y * rel_std_UPb_RXY
    else:
        rel_std_UPb_RXY = 0.0
        abs_std_UPb_RXY = 0.0
    return {"rel_std": rel_std_UPb_RXY,
            "abs_std": abs_std_UPb_RXY}

def calc_PbPbs_rhos(R74s, R74s_std,
                   R64s, R64s_std,
                   R76s, R76s_std,
                   R46s, R46s_std):
    '''
    Calculate correlation coefficients (rhos) between Pb-Pb isotope ratios

    Parameters
    ----------
    R74s : float
        Sample 207Pb/204Pb ratio
    R74s_std : float
        Absolute standard deviation of sample 207Pb/204Pb ratio
    R64s : float
        Sample 206Pb/204Pb ratio
    R64s_std : float
        Absolute standard deviation of sample 206Pb/204Pb ratio
    R76s : float
        Sample 207Pb/206Pb ratio
    R76s_std : float
        Absolute standard deviation of sample 207Pb/206Pb ratio
    R46s : float
        Sample 204Pb/206Pb ratio
    R46s_std : float
        Absolute standard deviation of sample 204Pb/206Pb ratio
    '''

    rho_7464_s = calc_rho_quotient(R76s, R76s_std,
                                 R74s, R74s_std,
                                 R64s, R64s_std)
    
    rho_7646_s = calc_rho_quotient(R74s, R74s_std,
                                 R76s, R76s_std,
                                 R46s, R46s_std)
    
    return {"rho_7464_s": rho_7464_s,
            "rho_7646_s": rho_7646_s}

def calc_UPbs_rhos(R64s, R64s_std,
                  R74s, R74s_std,
                  R76s, R76s_std,
                  R46s, R46s_std,
                  R84s, R84s_std, 
                  R54s, R54s_std,
                  R57s, R57s_std,
                  R86s, R86s_std,
                  R87s, R87s_std):
    '''
    Calculate correlation coefficients (rhos) between sample total U-Pb isotope ratios

    Parameters
    ----------
    R64s : float
        Sample 206Pb/204Pb ratio
    R64s_std : float
        Absolute standard deviation of sample 206Pb/204Pb ratio
    R74s : float
        Sample 207Pb/204Pb ratio
    R74s_std : float
        Absolute standard deviation of sample 207Pb/204Pb ratio
    R76s : float
        Sample 207Pb/206Pb ratio
    R76s_std : float
        Absolute standard deviation of sample 207Pb/206Pb ratio
    R46s : float
        Sample 204Pb/206Pb ratio
    R46s_std : float
        Absolute standard deviation of sample 204Pb/206Pb ratio
    R84s : float
        Sample 238U/204Pb ratio
    R84s_std : float
        Absolute standard deviation of sample 238U/204Pb ratio
    R54s : float
        Sample 235U/204Pb ratio
    R54s_std : float
        Absolute standard deviation of sample 235U/204Pb ratio
    R86s : float
        Sample 238U/206Pb ratio
    R86s_std : float
        Absolute standard deviation of sample 238U/206Pb ratio
    '''

    rho_8464_s = calc_rho_quotient(R86s, R86s_std,
                                 R84s, R84s_std,
                                 R64s, R64s_std)
    
    rho_5474_s = calc_rho_quotient(R57s, R57s_std,
                                 R54s, R54s_std,
                                 R74s, R74s_std)
    
    rho_8676_s = calc_rho_quotient(R87s, R87s_std,
                                 R86s, R86s_std,
                                 R76s, R76s_std)
    
    rho_8646_s = calc_rho_quotient(R84s, R84s_std,
                                 R86s, R86s_std,
                                 R46s, R46s_std)
    
    return {"rho_8464_s": rho_8464_s,
            "rho_5474_s": rho_5474_s,
            "rho_8676_s": rho_8676_s,
            "rho_8646_s": rho_8646_s}

def calc_Pb206r(R65m, R46m,
                FPb,
                Pb205t,
                R65t,
                R45t,
                R64c,
                R64b,
                Pb206b, *, Pb204c=None):
    '''
    calculate radiogenic 206Pb in sample (Pb206r)

    Parameters
    ----------
    R65m : float
        Measured total 206Pb/205Pb ratio
    R46m : float
        Measured total 204Pb/206Pb ratio
    FPb : float
        Coefficient for linear Pb fractionation correction per unit mass difference
    Pb205t : float
        Tracer solution 205Pb amount (moles)
    R65t : float
        Tracer solution 206Pb/205Pb ratio
    R45t : float
        Tracer solution 204Pb/205Pb ratio
    R64c : float
        Initial 204Pb/206Pb ratio in sample
    R64b : float
        Blank 204Pb/206Pb ratio
    Pb206b : float
        Blank 206Pb amount (moles)
    '''
    # A supplied partitioned amount, particularly exact zero, owns this value.
    # Standalone notebook calls retain the historical unconstrained equation.
    if Pb204c is None:
        Pb204c = R46m * R65m * Pb205t * (1 - FPb) - R45t * Pb205t - Pb206b/R64b
    return R65m * Pb205t * (1 + FPb) - (R65t * Pb205t) - Pb206b - R64c * Pb204c

def prop_Pb206r_uncertainty(dPb206r_dR65m, R65m_std,
                             dPb206r_dR46m, R46m_std,
                             dPb206r_dFPb, FPb_std,
                             dPb206r_dR65t, R65t_std,
                             dPb206r_dR45t, R45t_std,
                             dPb206r_dR64c, R64c_std,
                             dPb206r_dR64b, R64b_std,
                             dPb206r_dPb206b, Pb206b_std,
                             cov_65_46_m, cov_45_65_t):
    return np.sqrt( (dPb206r_dR65m * R65m_std)**2 +
                    (dPb206r_dR46m * R46m_std)**2 +
                    (dPb206r_dFPb * FPb_std)**2 +
                    (dPb206r_dR65t * R65t_std)**2 +
                    (dPb206r_dR45t * R45t_std)**2 +
                    (dPb206r_dR64c * R64c_std)**2 +
                    (dPb206r_dR64b * R64b_std)**2 +
                    (dPb206r_dPb206b * Pb206b_std)**2 +
                    2 * cov_65_46_m * dPb206r_dR65m * dPb206r_dR46m +
                    2 * cov_45_65_t * dPb206r_dR45t * dPb206r_dR65t )

def calc_Pb206r_uncertainty(R65m, R65m_std,
                            R46m, R46m_std,
                            FPb, FPb_std,
                            Pb205t, 
                            R65t, R65t_std,
                            R45t, R45t_std,
                            R46t, R46t_std,
                            R64c, R64c_std,
                            R64b, R64b_std,
                            Pb206b, Pb206b_std,
                            R45m=None, R45m_std=None):
    # uncorrelated error propagation
    term1 = (((1 + FPb) - R64c * R46m * (1 - FPb)) * Pb205t) ** 2 * R65m_std**2
    term2 = (-R65m * R64c * (1 - FPb) * Pb205t) ** 2 * R46m_std**2
    term3 = (-Pb205t) ** 2 * R65t_std**2
    term4 = (R64c * Pb205t) ** 2 * R45t_std**2
    term5 = ((1 + R64c * R46m) * R65m * Pb205t) ** 2 * FPb_std**2
    term6 = (R64c/R64b-1.0) ** 2 * Pb206b_std**2
    term7 = (-Pb206b * R64c / R64b**2) ** 2 * R64b_std**2
    term8 = ((-R46m * R65m * Pb205t * ( 1 - FPb)) + (R45t * Pb205t) + Pb206b/R64b) ** 2 * R64c_std**2

    # covariance terms
    cov_65_46_m = calc_covariance_squared(R45m, R45m_std, R65m, R65m_std, R46m, R46m_std, type='product') if R45m is not None and R45m_std is not None else 0.0
    cov_45_65_t = calc_covariance_squared(R46t, R46t_std, R45t, R45t_std, R65t, R65t_std, type='quotient')

    term9 = 2 * cov_65_46_m * ( (1 + FPb) - R64c * R46m * (1 - FPb)) * Pb205t * ( -R65m * R64c * (1 - FPb) * Pb205t) 
    term10 = 2 * cov_45_65_t * ( -Pb205t) * (R64c * Pb205t)

    Pb206r_std = np.sqrt(term1 + term2 + term3 + term4 + term5 + term6 + term7 + term8 + term9 + term10)
    return Pb206r_std

def calc_Pb207r(R65m, R76m, R46m,
                FPb,
                Pb205t,
                R65t,
                R76t,
                R45t,
                R76c,
                R64c,
                R64b,
                R76b,
                Pb206b, *, Pb204c=None):
    if Pb204c is None:
        Pb204c = R46m * R65m * Pb205t * (1 - FPb) - R45t * Pb205t - Pb206b / R64b
    return (R65m * R76m * (1 + 2 * FPb) - R65t * R76t) * Pb205t - (R76b * Pb206b) - R64c * R76c * Pb204c

def prop_Pb207r_uncertainty(dPb207r_dR65m, R65m_std,
                             dPb207r_dR76m, R76m_std,
                             dPb207r_dR46m, R46m_std,
                             dPb207r_dFPb, FPb_std,
                             dPb207r_dR65t, R65t_std,
                             dPb207r_dR76t, R76t_std,
                             dPb207r_dR45t, R45t_std,
                             dPb207r_dR76c, R76c_std,
                             dPb207r_dR64c, R64c_std,
                             dPb207r_dR64b, R64b_std,
                             dPb207r_dR76b, R76b_std,
                             dPb207r_dPb206b, Pb206b_std,
                             cov_65_76_m, cov_65_46_m,
                             cov_65_76_t, cov_45_65_t):
    return np.sqrt( (dPb207r_dR65m * R65m_std)**2 +
                    (dPb207r_dR76m * R76m_std)**2 +
                    (dPb207r_dR46m * R46m_std)**2 +
                    (dPb207r_dFPb * FPb_std)**2 +
                    (dPb207r_dR65t * R65t_std)**2 +
                    (dPb207r_dR76t * R76t_std)**2 +
                    (dPb207r_dR45t * R45t_std)**2 +
                    (dPb207r_dR76c * R76c_std)**2 +
                    (dPb207r_dR64c * R64c_std)**2 +
                    (dPb207r_dR64b * R64b_std)**2 +
                    (dPb207r_dR76b * R76b_std)**2 +
                    (dPb207r_dPb206b * Pb206b_std)**2 +
                    2 * cov_65_76_m * dPb207r_dR65m * dPb207r_dR76m +
                    2 * cov_65_46_m * dPb207r_dR65m * dPb207r_dR46m +
                    2 * cov_65_76_t * dPb207r_dR65t * dPb207r_dR76t +
                    2 * cov_45_65_t * dPb207r_dR45t * dPb207r_dR65t )

def calc_Pb207r_uncertainty(R65m, R65m_std,
                            R76m, R76m_std,
                            R75m, R75m_std,
                            R46m, R46m_std,
                            FPb, FPb_std,
                            Pb205t,
                            R45t, R45t_std,
                            R65t, R65t_std,
                            R76t, R76t_std,
                            R76b, R76b_std,
                            R75t, R75t_std,
                            R64b, R64b_std,
                            Pb206b, Pb206b_std,
                            R64c, R64c_std,
                            R76c, *, R76c_std=0.0, R45m=None, R45m_std=None,
                            R46t=None, R46t_std=None):
    """Legacy partial propagation; omitted ratio covariances are zero.

    Supply measured 204/205 and tracer 204/206 errors to infer their
    covariances. Prefer grain.calc_all() for joint propagation.
    """
    if (R45m is None) != (R45m_std is None) or (R46t is None) != (R46t_std is None):
        raise ValueError("Supply both a ratio and its standard deviation")
    # uncorrelated error propagation
    term1 = ((R76m * (1 + 2 * FPb) - R64c * R76c * R46m * ( 1 - FPb)) * Pb205t) ** 2 * R65m_std**2
    term2 = (R65m * (1 + 2 * FPb) * Pb205t) ** 2 * R76m_std**2
    term3 = (-R64c * R76c * R65m * (1 - FPb) * Pb205t) ** 2 * R46m_std**2
    term4 = ((2 * R76m + R64c * R76c * R46m) * R65m * Pb205t) ** 2 * FPb_std**2
    term5 = (-R76t * Pb205t) ** 2 * R65t_std**2
    term6 = (-R65t * Pb205t) ** 2 * R76t_std**2
    term7 = (R64c * R76c * Pb205t) ** 2 * R45t_std**2
    term8 = (-R76b + R64c * R76c / R64b) ** 2 * Pb206b_std**2
    term9 = (-Pb206b * R64c * R76c / R64b **2) ** 2 * R64b_std**2
    term10 = (-Pb206b) ** 2 * R76b_std**2
    term11 = ((-R46m * R65m * Pb205t * R76c * (1 - FPb)) + (R45t * R76c * Pb205t) + (Pb206b * R76c / R64b)) ** 2 * R64c_std**2
    term12 = ((-R46m * R65m * Pb205t * R64c * (1 - FPb)) + (R45t * R64c * Pb205t) + (Pb206b * R64c / R64b)) ** 2 * R76c_std**2

    # covariance terms
    cov_76_65_m = calc_covariance_squared(R75m, R75m_std, R65m, R65m_std, R76m, R76m_std, type='product')
    cov_65_46_m = (calc_covariance_squared(R45m, R45m_std, R65m, R65m_std,
                                         R46m, R46m_std, type='product')
                   if R45m is not None else 0.0)
    cov_76_65_t = calc_covariance_squared(R75t, R75t_std, R65t, R65t_std, R76t, R76t_std, type='product')
    cov_45_65_t = (calc_covariance_squared(R46t, R46t_std, R45t, R45t_std,
                                         R65t, R65t_std, type='quotient')
                   if R46t is not None else 0.0)

    term13 = 2 * cov_76_65_m * (R76m * (1 + 2 * FPb) - R64c * R76c * R46m * ( 1 - FPb)) * Pb205t * (R65m * (1 + 2 * FPb) * Pb205t)
    term14 = 2 * cov_65_46_m * (R76m * (1 + 2 * FPb) - R64c * R76c * R46m * ( 1 - FPb)) * Pb205t * ( -R64c * R76c * R65m * (1 - FPb) * Pb205t)
    term15 = 2 * cov_76_65_t * ( -R76t * Pb205t) * ( -R65t * Pb205t)
    term16 = 2 * cov_45_65_t * ( -R76t * Pb205t) * (R64c * R76c * Pb205t)

    Pb207r_std = np.sqrt(term1 + term2 + term3 + term4 + term5 + term6 + term7 + term8 + term9 + term10 + term11 + term12 + term13 + term14 + term15 + term16)
    return Pb207r_std

def prop_cov_Pb76r_squared(dPb207r_dR65m, dPb206r_dR65m, R65m_std,
                             dPb207r_dR46m, dPb206r_dR46m, R46m_std,
                             dPb207r_dFPb, dPb206r_dFPb, FPb_std,
                             dPb207r_dR65t, dPb206r_dR65t, R65t_std,
                             dPb207r_dR45t, dPb206r_dR45t, R45t_std,
                             dPb207r_dR64c, dPb206r_dR64c, R64c_std,
                             dPb207r_dR64b, dPb206r_dR64b, R64b_std,
                             dPb207r_dPb206b, dPb206r_dPb206b, Pb206b_std):
    
    return ((dPb207r_dR65m * dPb206r_dR65m) * R65m_std**2 +
            (dPb207r_dR46m * dPb206r_dR46m) * R46m_std**2 +
            (dPb207r_dFPb * dPb206r_dFPb) * FPb_std**2 +
            (dPb207r_dR65t * dPb206r_dR65t) * R65t_std**2 +
            (dPb207r_dR45t * dPb206r_dR45t) * R45t_std**2 +
            (dPb207r_dR64c * dPb206r_dR64c) * R64c_std**2 +
            (dPb207r_dR64b * dPb206r_dR64b) * R64b_std**2 +
            (dPb207r_dPb206b * dPb206r_dPb206b) * Pb206b_std**2)

def calc_cov_Pb76r_squared(R65m, R65m_std, 
                           R76m,
                           R46m, R46m_std,
                           FPb, FPb_std,
                           Pb205t,
                           R45t, R45t_std,
                           R65t_std,
                           R76t,
                           R64b, R64b_std,
                           R76b,
                           Pb206b, Pb206b_std,
                           R64c, R64c_std,
                           R76c):
    
    term1 = ((R76m * (1 + 2 * FPb) - R64c * R76c * R46m * ( 1 - FPb)) * Pb205t) * (((1 + FPb) - R64c * R46m * (1 - FPb)) * Pb205t) * R65m_std**2
    term2 = (-R64c * R76c * R65m * (1 - FPb) * Pb205t) * ( -R65m * R64c * (1 - FPb) * Pb205t) * R46m_std**2
    term3 = (-R76t * Pb205t) * ( -Pb205t) * R65t_std**2
    term4 = (R64c * R76c * Pb205t) * (R64c * Pb205t) * R45t_std**2
    term5 = ((2 * R76m + R64c * R76c * R46m) * R65m * Pb205t) * ((1 + R64c * R46m) * R65m * Pb205t) * FPb_std**2
    term6 = (-R76b + R64c * R76c / R64b) * (R64c/R64b-1.0) * Pb206b_std**2
    term7 = (-Pb206b * R64c * R76c / R64b **2) * (-Pb206b * R64c / R64b**2) * R64b_std**2
    term8 = ((-R46m * R65m * Pb205t * R76c * (1 - FPb)) + (R45t * R76c * Pb205t) + (Pb206b * R76c / R64b)) * ((-R46m * R65m * Pb205t * ( 1 - FPb)) + (R45t * Pb205t) + Pb206b/R64b) * R64c_std**2

    return term1 + term2 + term3 + term4 + term5 + term6 + term7 + term8

def calc_UPbr_rhos(R75r, R75r_std,
                   R68r, R68r_std,
                   R76r, R76r_std,
                   R86r, R86r_std,
                   R87r, R87r_std):
    '''
    Calculate correlation coefficients (rhos) between radiogenic U-Pb radiogenic isotope ratios

    Parameters
    ----------
    R75r : float
        Radiogenic 207Pb/235U ratio
    R75r_std : float
        Absolute standard deviation of radiogenic 207Pb/235U ratio
    R68r : float
        Radiogenic 206Pb/238U ratio
    R68r_std : float
        Absolute standard deviation of radiogenic 206Pb/238U ratio
    R76r : float
        Radiogenic 207Pb/206Pb ratio
    R76r_std : float
        Absolute standard deviation of radiogenic 207Pb/206Pb ratio
    R86r : float
        Radiogenic 238U/206Pb ratio
    R86r_std : float
        Absolute standard deviation of radiogenic 238U/206Pb ratio
    R87r : float
        Radiogenic 238U/207Pb ratio
    R87r_std : float
        Absolute standard deviation of radiogenic 238U/207Pb ratio
    '''
    rho_7568_r = calc_rho_quotient(R76r, R76r_std,
                                 R75r, R75r_std,
                                 R68r, R68r_std)
    rho_8676_r = calc_rho_quotient(R87r, R87r_std,
                                 R86r, R86r_std,
                                 R76r, R76r_std)
    
    return {"rho_7568_r": rho_7568_r,
            "rho_8676_r": rho_8676_r}


def calc_t75(X, lambda_235=lambda_235):
    '''
    return age in Ma
    '''
    if np.any(~np.isfinite(X)) or np.any(np.asarray(X) < 0) or not np.isfinite(lambda_235) or lambda_235 <= 0:
        raise ValueError("Ratio must be finite and nonnegative; decay constant must be positive")
    age = np.log1p(X)/lambda_235
    return age/1e6

def calc_t68(Y, lambda_238=lambda_238):
    '''
    return age in Ma
    '''
    if np.any(~np.isfinite(Y)) or np.any(np.asarray(Y) < 0) or not np.isfinite(lambda_238) or lambda_238 <= 0:
        raise ValueError("Ratio must be finite and nonnegative; decay constant must be positive")
    age = np.log1p(Y)/lambda_238
    return age/1e6

def calc_t76(ratio,x0=1e6, tol=1e-8, 
                 lambda_235=lambda_235, lambda_238=lambda_238, 
                 common_U238_U235=common_U238_U235):
    '''
    calculates 207Pb/206Pb date given a 207Pb/206Pb ratio
    
    do not take a list of values
    
    Required Parameters:
    ---------------------
    ratio: the measured 76 ratio
    
    Optional Parameters:
    ---------------------
    x0: historical initial guess in years, accepted and ignored
    tol: root tolerance in years
    
    Return:
    ---------------------
    age in Ma
    
    '''
    if not np.isfinite(ratio) or tol <= 0 or not np.isfinite(tol):
        raise ValueError("Ratio must be finite and tolerance positive")
    if not (lambda_235 > lambda_238 > 0 and common_U238_U235 > 0):
        raise ValueError("Require lambda_235 > lambda_238 > 0 and positive U ratio")
    def ratio_diff(t):
        return _pb76_ratio(t, lambda_235, lambda_238, common_U238_U235) - ratio
    if ratio_diff(0) > 0 or ratio_diff(4600) < 0:
        raise ValueError("207Pb/206Pb ratio has no age in the supported 0–4600 Ma interval")
    return brentq(ratio_diff, 0, 4600, xtol=tol / 1e6, rtol=4*np.finfo(float).eps)


def _pb76_ratio(t_ma, l235, l238, u_ratio):
    """Stable radiogenic 207Pb/206Pb ratio, including the zero-age limit."""
    if t_ma == 0:
        return l235 / l238 / u_ratio
    return np.expm1(l235*t_ma*1e6) / np.expm1(l238*t_ma*1e6) / u_ratio

def calc_t68_uncertainty(R68r, R68r_std, lambda_238=lambda_238):
    '''
    calculate 206Pb/238U date uncertainty

    Parameters
    ----------
    R68r : float
        Radiogenic 206Pb/238U ratio
    R68r_std : float
        Absolute standard deviation of radiogenic 206Pb/238U ratio

    Returns
    -------
    68 age uncertainty in Ma
    '''
    if np.any(~np.isfinite(R68r)) or np.any(np.asarray(R68r) < 0) or np.any(~np.isfinite(R68r_std)) or np.any(np.asarray(R68r_std) < 0) or not (np.isfinite(lambda_238) and lambda_238 > 0):
        raise ValueError("Invalid ratio, uncertainty or decay constant")
    return 1 / lambda_238 * ( R68r_std / (R68r + 1) ) / 1e6

def calc_t75_uncertainty(R75r, R75r_std, lambda_235=lambda_235):
    '''
    calculate 207Pb/235U date uncertainty

    Parameters
    ----------
    R75r : float
        Radiogenic 207Pb/235U ratio
    R75r_std : float
        Absolute standard deviation of radiogenic 207Pb/235U ratio

    Returns
    -------
    75 age uncertainty in Ma
    '''
    if np.any(~np.isfinite(R75r)) or np.any(np.asarray(R75r) < 0) or np.any(~np.isfinite(R75r_std)) or np.any(np.asarray(R75r_std) < 0) or not (np.isfinite(lambda_235) and lambda_235 > 0):
        raise ValueError("Invalid ratio, uncertainty or decay constant")
    return 1 / lambda_235 * ( R75r_std / (R75r + 1) ) / 1e6

def calc_t76_uncertainty(t76, 
                         R76r_std,
                         lambda_235=lambda_235, lambda_238=lambda_238,
                         common_U238_U235=common_U238_U235):
    
    if not (np.isfinite(t76) and t76 >= 0 and np.isfinite(R76r_std) and R76r_std >= 0):
        raise ValueError("Age and standard uncertainty must be finite and nonnegative")
    a, b = lambda_235 * 1e6, lambda_238 * 1e6
    if not (a > b > 0 and common_U238_U235 > 0):
        raise ValueError("Invalid decay constants or natural U isotope ratio")
    if t76 < 0.01:
        derivative = a/b/common_U238_U235 * ((a-b)/2 + (2*a*a-3*a*b+b*b)*t76/6)
    else:
        numerator, denominator = np.expm1(a*t76), np.expm1(b*t76)
        derivative = (a*np.exp(a*t76)*denominator - b*np.exp(b*t76)*numerator) / denominator**2 / common_U238_U235
    return R76r_std / abs(derivative)


# 230Th correction functions
#--------------------------------------------------

def Pb208r_partials(R85m, 
                    R45m,
                    FPb,
                    Pb205t,
                    R45t,
                    Pb206b,
                    R64b,
                    R86b,
                    R84c):
    dPb208r_dR85m = Pb205t * (1 + 3 * FPb)
    dPb208r_dR45m = - Pb205t * (1 - FPb) * R84c
    dPb208r_dFPb = 3 * R85m * Pb205t + R84c * R45m * Pb205t
    dPb208r_dR85t = - Pb205t
    dPb208r_dR45t = Pb205t * R84c
    dPb208r_dPb206b = - R86b + 1 / R64b * R84c
    dPb208r_dR64b = - Pb206b / R64b**2 * R84c
    dPb208r_dR86b = - Pb206b
    dPb208r_dR84c = -R45m * Pb205t * (1 - FPb) + R45t * Pb205t + Pb206b / R64b

    return {"dPb208r_dR85m": dPb208r_dR85m,
            "dPb208r_dR45m": dPb208r_dR45m,
            "dPb208r_dFPb": dPb208r_dFPb,
            "dPb208r_dR85t": dPb208r_dR85t,
            "dPb208r_dR45t": dPb208r_dR45t,
            "dPb208r_dPb206b": dPb208r_dPb206b,
            "dPb208r_dR64b": dPb208r_dR64b,
            "dPb208r_dR86b": dPb208r_dR86b,
            "dPb208r_dR84c": dPb208r_dR84c}


def calc_Pb208r(R85m, FPb, Pb205t, R85t, Pb208b, Pb208c):
    '''
    calculate radiogenic 208Pb in sample (Pb208r)

    Parameters
    ----------
    R85m : float
        Measured total 208Pb/205Pb ratio
    FPb : float
        Coefficient for linear Pb fractionation correction per unit mass difference
    Pb205t : float
        Tracer solution 205Pb amount (moles)
    R85t : float
        Tracer solution 208Pb/205Pb ratio
    Pb208b : float
        Blank 208Pb amount (moles)
    Pb208c : float
        Initial common 208Pb amount in sample (moles)
    '''
    return R85m * Pb205t * (1 + 3 * FPb) - R85t * Pb205t - Pb208b - Pb208c
    
def prop_Pb208r_uncertainty(dPb208r_dR85m, R85m_std,
                            dPb208r_dR45m, R45m_std,
                             dPb208r_dFPb, FPb_std,
                             dPb208r_dR85t, R85t_std,
                             dPb208r_dR45t, R45t_std,
                             dPb208r_dPb206b, Pb206b_std,
                             dPb208r_dR64b, R64b_std,
                             dPb208r_dR86b, R86b_std,
                             dPb208r_dR84c, R84c_std,
                             cov_85_45_m, cov_85_45_t, 
                             cov_86_64_b):
    return np.sqrt( (dPb208r_dR85m * R85m_std)**2 +
                    (dPb208r_dR45m * R45m_std)**2 +
                    (dPb208r_dFPb * FPb_std)**2 +
                    (dPb208r_dR85t * R85t_std)**2 +
                    (dPb208r_dR45t * R45t_std)**2 +
                    (dPb208r_dPb206b * Pb206b_std)**2 +
                    (dPb208r_dR64b * R64b_std)**2 +
                    (dPb208r_dR86b * R86b_std)**2 +
                    (dPb208r_dR84c * R84c_std)**2 +
                    2 * cov_85_45_m * dPb208r_dR85m * dPb208r_dR45m +
                    2 * cov_85_45_t * dPb208r_dR85t * dPb208r_dR45t +
                    2 * cov_86_64_b * dPb208r_dR86b * dPb208r_dR64b )
    
def calc_Th232s(Pb208r, t68_Th_corr, t75_Th_corr=None, lambda_232=lambda_232):
    '''
    calculate 232Th concentration in sample at present

    Parameters
    ----------
    Pb208r : float
        Radiogenic 208Pb amount in sample (moles)
    t68 : float
        230Th corrected 206Pb/238U age in Ma
    t75 : float, optional
        230Th corrected 207Pb/235U age in Ma, by default None
    lambda_232 : float, optional
        Decay constant of 232Th in yr-1

    Returns
    -------
    Th232s : float
        232Th concentration in sample at time of formation
    '''
    if t75_Th_corr is None:
        t = t68_Th_corr
    else:
        t = t75_Th_corr

    Th232s = Pb208r / (np.exp(lambda_232 * t * 1e6) - 1)
    return Th232s

def calc_Th_ppm(Th232s, sample_weight, AWTh232=AWTh232):
    '''
    convert 232Th concentration in sample (moles) to ppm

    Parameters
    ----------
    Th232s : float
        232Th concentration in sample at present (moles)
    sample_weight : float
        Sample weight in milligrams

    Returns
    -------
    Th_ppm : float
        232Th concentration in sample in ppm
    '''
    Th_ppm = Th232s * AWTh232 / sample_weight * 1e9
    return Th_ppm

def calc_t68_Th(R68r, 
                type='D',
                D_Th_U=None, 
                Pb208r=None, U238s=None, 
                Th_U_magma=None, 
                lambda_238=lambda_238, 
                lambda_230=lambda_230, 
                x0=1e6, tol=1e-8,
                lambda_232=lambda_232,
                common_U238_U235=common_U238_U235):
    """Th-corrected age in Ma; magma Th/U is atomic Th / total natural U.

    The natural U ratio is fixed for propagation and converts U238s to
    U238s + U235s. The historical positional arguments remain unchanged.
    """
    if type not in ('D', 'magma'):
        raise ValueError("type must be 'D' or 'magma'")

    if not (np.isfinite(lambda_230) and lambda_230 > 0 and np.isfinite(lambda_238) and lambda_238 > 0 and np.isfinite(lambda_232) and lambda_232 > 0):
        raise ValueError("Decay constants must be finite and positive")

    if type == 'D':
        if D_Th_U is None or not np.isfinite(D_Th_U) or D_Th_U < 0:
            raise ValueError("D_Th_U must be finite and nonnegative")
        return calc_t68(R68r - lambda_238 / lambda_230 * (D_Th_U - 1), lambda_238)

    else:  # magma
        # Present-day Th/U derives from 208Pb growth using lambda_232.
        if not np.isfinite(common_U238_U235) or common_U238_U235 <= 0:
            raise ValueError("Natural 238U/235U must be finite and positive")
        if not (R68r > 0 and Pb208r >= 0 and U238s > 0 and Th_U_magma > 0):
            raise ValueError("Invalid inputs for magma Th correction")
        total_u = U238s * (1 + 1/common_U238_U235)
        def residual(t):
            th_u = Pb208r / np.expm1(lambda_232*t*1e6) / total_u
            return np.expm1(lambda_238*t*1e6) - R68r + lambda_238/lambda_230*(th_u/Th_U_magma - 1)
        uncorrected = calc_t68(R68r, lambda_238)
        lo = max(uncorrected/2, 1e-9)
        hi = max(uncorrected*2, 1.0)
        return brentq(residual, lo, hi, xtol=tol/1e6)

def calc_Pb206r_Th(t68_Th, U238s, lambda_238):
    '''
    After the calculation of 230Th corrected age (t68_Th), calculate the 230Th corrected radiogenic 206Pb
    '''
    Pb206r_Th = U238s * (np.exp(lambda_238 * t68_Th * 1e6) - 1)
    return {"Pb206r_Th": Pb206r_Th,
            "R68r_Th": Pb206r_Th / U238s}

def calc_R68r_Th_std(R68r_std, 
                     type='D',
                     D_Th_U_std=None, 
                     Th_U_s=None, Th_U_s_std=None,
                     Th_U_magma=None, Th_U_magma_std=None,
                     lambda_238=lambda_238, lambda_230=lambda_230,
                    ):
    '''
    calculate 230Th corrected radiogenic 206Pb/238U ratio uncertainty
    '''
    if type not in ('D', 'magma'):
        raise ValueError("type must be 'D' or 'magma'")

    if type == 'D':
        dR68rTh_dR68r = 1.0
        dR68rTh_dDThU =  - lambda_238 / lambda_230
        R68r_Th_std = np.sqrt( (dR68rTh_dR68r * R68r_std)**2 +
                               (dR68rTh_dDThU * D_Th_U_std)**2 )
    
    else:  # magma
        dR68rTh_dR68r = 1.0
        dR68rTh_dThU_initial = - lambda_238 / lambda_230 / Th_U_magma
        dR68rTh_dTh_U_magma = lambda_238 / lambda_230 * Th_U_s / Th_U_magma**2
        R68r_Th_std = np.sqrt( (dR68rTh_dR68r * R68r_std)**2 +
                                 (dR68rTh_dThU_initial * Th_U_s_std)**2 +
                               (dR68rTh_dTh_U_magma * Th_U_magma_std)**2 )

    return R68r_Th_std
