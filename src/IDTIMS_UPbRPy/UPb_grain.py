from dataclasses import dataclass, field
import numpy as np

from .constants import (
    lambda_230,
    lambda_232,
    lambda_235,
    lambda_238,
    lambda_235_std,
    lambda_238_std,
    common_U238_U235,
)

from .utils import (
    FU_partials,
    Pb204c_partials,
    Pb206r_partials,
    Pb206s_partials,
    Pb207r_partials,
    Pb207s_partials,
    Pb208r_partials,
    Pb_covariance_squared,
    U235s_partials,
    U238s_partials,
    U_covariance_squared,
    calc_FPb_2535,
    calc_FU,
    calc_Pb206r,
    calc_Pb206r_Th,
    calc_Pb206s,
    calc_Pb207r,
    calc_Pb207s,
    calc_Pb208r,
    calc_PbPb_uncertainty,
    calc_PbPbs_rhos,
    calc_Pb_blank_AW,
    calc_Pb_partitioning,
    calc_R68r_Th_std,
    calc_Th232s,
    calc_Th_ppm,
    calc_U235s,
    calc_U238b,
    calc_U238s,
    calc_UPb_uncertainty,
    calc_UPbr_rhos,
    calc_UPbs_rhos,
    calc_U_blank_AW,
    calc_rad_Pb,
    calc_rad_U,
    calc_t68,
    calc_t68_Th,
    calc_t68_uncertainty,
    calc_t75,
    calc_t75_uncertainty,
    calc_t76,
    calc_t76_uncertainty,
    calc_total_Pb_ppm,
    calc_total_U_ppm,
    prop_FU_uncertainty,
    prop_Pb204c_uncertainty,
    prop_Pb206r_uncertainty,
    prop_Pb206s_uncertainty,
    prop_Pb207r_uncertainty,
    prop_Pb207s_uncertainty,
    prop_Pb208r_uncertainty,
    prop_U235s_uncertainty,
    prop_U238s_uncertainty,
    prop_cov_Pb76r_squared,
    prop_cov_Pb_R46s_squared,
    prop_cov_Pb_R47s_squared,
    prop_cov_Pb_R76s_squared,
)


@dataclass(repr=False, eq=False)
class UPb_grain:
    """A single fraction; isotope amounts are mol, dates Ma, and errors 1σ."""
    # general
    id: str
    sample_weight: float
    spike_weight: float
    spike_type: int
    spike_name: str
    collector: str
    spike_version: str | None = None
    spike_key: str | None = field(default=None, kw_only=True)
    data_quality_checks: list = field(default_factory=list, init=False)
    data_quality_passed: bool | None = field(default=None, init=False)
    FPb: float = None
    FPb_std: float = None
    FU: float = None
    FU_std: float = None
    lambda_230: float = lambda_230
    lambda_232: float = lambda_232
    lambda_235: float = lambda_235
    lambda_235_std: float = lambda_235_std
    lambda_238: float = lambda_238
    lambda_238_std: float = lambda_238_std
    common_U238_U235: float = common_U238_U235

    Th232s: float = None # 232Th amount in sample (mol)
    Th_ppm: float = None # 232Th concentration in sample (ppm)
    Th_U: float = None # calculated sample Th/U ratio
    Th230_correction_type:str = None
    D_Th_U: float = None # distribution coefficients
    D_Th_U_std: float = None
    Th_U_s: float = None # assumed initial Th/U ratio in the sample
    Th_U_s_std: float = None
    Th_U_magma: float = None # assumed magmatic Th/U ratio
    Th_U_magma_std: float = None
    a_Th230_U238: float = None # magmatic activity ratio of Th230 to U238

    t76: float = field(init=False)
    t76_std: float = field(init=False)
    t75: float = field(init=False)
    t75_std: float = field(init=False)
    t68: float = field(init=False)
    t68_std: float = field(init=False)

    t76_Th_corr: float = field(init=False)
    t76_Th_corr_std: float = field(init=False)
    t68_Th_corr: float = field(init=False)
    t68_Th_corr_std: float = field(init=False)

    # tracer data
    Pb205t: float = field(init=False) # mol
    U235t: float = field(init=False) # mol
    Pb_R25t: float = None
    Pb_R25t_std: float = None
    Pb_R65t: float = field(init=False)
    Pb_R65t_std: float = field(init=False)
    Pb_R75t: float = field(init=False)
    Pb_R75t_std: float = field(init=False)
    Pb_R45t: float = field(init=False)
    Pb_R45t_std: float = field(init=False)
    Pb_R84t: float = field(init=False)
    Pb_R84t_std: float = field(init=False)
    Pb_R85t: float = field(init=False)
    Pb_R85t_std: float = field(init=False)
    Pb_R76t: float = field(init=False)
    Pb_R76t_std: float = field(init=False)
    Pb_R46t: float = field(init=False)
    Pb_R46t_std: float = field(init=False)
    U_R85t: float = field(init=False)
    U_R85t_std: float = field(init=False)
    U_R35t: float = field(init=False)
    U_R35t_std: float = field(init=False)
    U_R83t: float = field(init=False)
    U_R83t_std: float = field(init=False)
    
    # measured ratios and uncertainties
    Pb_R25m: float = None
    Pb_R25m_std: float = None
    Pb_R45m: float = field(init=False)
    Pb_R45m_std: float = field(init=False)
    Pb_R46m: float = field(init=False)
    Pb_R46m_std: float = field(init=False)
    Pb_R64m: float = field(init=False)
    Pb_R64m_std: float = field(init=False)
    Pb_R65m: float = field(init=False)
    Pb_R65m_std: float = field(init=False)
    Pb_R75m: float = field(init=False)
    Pb_R75m_std: float = field(init=False)
    Pb_R76m: float = field(init=False)
    Pb_R76m_std: float = field(init=False)
    Pb_R84m: float = field(init=False)
    Pb_R84m_std: float = field(init=False)
    Pb_R85m: float = field(init=False)
    Pb_R85m_std: float = field(init=False)

    U_R35m: float = field(init=False)
    U_R35m_std: float = field(init=False)
    U_R83m: float = field(init=False)
    U_R83m_std: float = field(init=False)
    U_R85m: float = field(init=False)
    U_R85m_std: float = field(init=False)

    # blank data
    Pb_blank_total: float = field(init=False)
    Pb_blank_total_std: float = field(init=False)
    Pb204b: float = field(init=False)
    Pb206b: float = field(init=False)
    Pb206b_std: float = field(init=False)
    Pb207b: float = field(init=False)
    Pb208b: float = field(init=False)

    U_blank_total: float = field(init=False)
    U_blank_total_std: float = field(init=False)
    U238b: float = field(init=False)
    U238b_std: float = field(init=False)
    R46b: float = field(init=False)
    R46b_std: float = field(init=False)
    R64b: float = field(init=False)
    R64b_std: float = field(init=False)
    R74b: float = field(init=False)
    R74b_std: float = field(init=False)
    R76b: float = field(init=False)
    R76b_std: float = field(init=False)
    R84b: float = field(init=False)
    R84b_std: float = field(init=False)
    R86b: float = field(init=False)
    R86b_std: float = field(init=False)
    rho_6474_b: float = field(init=False)
    rho_6484_b: float = field(init=False)
    Pb_blank_AW: float = field(init=False)

    # initial data
    Pbc_pg: float = field(init=False) # Pb blank+initial [pg]
    Pb204c: float = field(init=False)
    Pb204c_std: float = field(init=False)
    Pb206c: float = field(init=False)
    Pb207c: float = field(init=False)
    Pb208c: float = field(init=False)
    R64c: float = field(init=False)
    R64c_std: float = field(init=False)
    R76c: float = field(init=False)
    R76c_std: float = field(init=False)
    R84c: float = field(init=False)
    R84c_std: float = field(init=False)

    # sample data
    Pb206s: float = field(init=False)
    Pb206s_std: float = field(init=False)
    Pb207s: float = field(init=False)
    Pb207s_std: float = field(init=False)
    Pb208s: float = field(init=False)
    Pb208s_std: float = field(init=False)

    U238s: float = field(init=False)
    U238s_std: float = field(init=False)
    U235s: float = field(init=False)
    U235s_std: float = field(init=False)

    Pb_ppm: float = field(init=False) # total Pb in sample (ppm)
    U_ng: float = field(init=False) # total U in sample (ng)
    U_ppm: float = field(init=False) # total U in sample (ppm)

    R46s: float = field(init=False) # (204Pb/206Pb) sample
    R46s_std: float = field(init=False)
    R47s: float = field(init=False) # (204Pb/207Pb) sample
    R47s_std: float = field(init=False)
    R54s: float = field(init=False) # (235U/204Pb) sample
    R54s_std: float = field(init=False)
    R57s: float = field(init=False) # (235U/207Pb) sample
    R57s_std: float = field(init=False)
    R64s: float = field(init=False) # (206Pb/204Pb) sample
    R64s_std: float = field(init=False)
    R74s: float = field(init=False) # (207Pb/204Pb) sample
    R74s_std: float = field(init=False)
    R76s: float = field(init=False) # (207Pb/206Pb) sample
    R76s_std: float = field(init=False)
    R84s: float = field(init=False) # (238U/204Pb) sample
    R84s_std: float = field(init=False)
    R86s: float = field(init=False) # (238U/206Pb) sample
    R86s_std: float = field(init=False)
    R87s: float = field(init=False) # (238U/207Pb) sample
    R87s_std: float = field(init=False)

    # radiogenic quantities
    Pbr_pg: float = field(init=False) # Pb radiogenic (pg)
    Pbr_Pbc: float = field(init=False) # Pb radiogenic / Pb initial+blank
    Th_U: float = field(init=False) # sample Th/U ratio
    Pb206r: float = field(init=False)
    Pb206r_std: float = field(init=False)
    Pb207r: float = field(init=False)
    Pb207r_std: float = field(init=False)
    Pb208r: float = field(init=False)
    Pb208r_std: float = field(init=False)
    R76r: float = field(init=False) # (207Pb/206Pb) radiogenic
    R76r_std: float = field(init=False)
    R68r: float = field(init=False) # (206Pb/238U) radiogenic
    R68r_std: float = field(init=False)
    R75r: float = field(init=False) # (207Pb/235U) radiogenic
    R75r_std: float = field(init=False)
    R86r: float = field(init=False) # (238U/206Pb) radiogenic
    R86r_std: float = field(init=False)
    R87r: float = field(init=False) # (238U/207Pb) radiogenic
    R87r_std: float = field(init=False)

    Pb206r_Th: float = field(init=False) # Th-corrected radiogenic 206Pb
    Pb206r_Th_std: float = field(init=False)
    R76r_Th: float = field(init=False) # (207Pb/206Pb) radiogenic, Th-corrected
    R76r_Th_std: float = field(init=False)
    R68r_Th: float = field(init=False) # (206Pb/238U) radiogenic, Th-corrected
    R68r_Th_std: float = field(init=False)
    R86r_Th: float = field(init=False) # (238U/206Pb) radiogenic, Th-corrected
    R86r_Th_std: float = field(init=False)

    # partial derivatives
    dPb206s_dR65m: float = field(init=False)
    dPb206s_dR65t: float = field(init=False)
    dPb206s_dFPb: float = field(init=False)
    dPb206s_dPb206b: float = field(init=False)
    dPb206r_dR65m: float = field(init=False)
    dPb206r_dR46m: float = field(init=False)
    dPb206r_dR65t: float = field(init=False)
    dPb206r_dR45t: float = field(init=False)
    dPb206r_dFPb: float = field(init=False)
    dPb206r_dPb206b: float = field(init=False)
    dPb206r_dR64b: float = field(init=False)
    dPb206r_dR64c: float = field(init=False)
    
    dPb207s_dR65m: float = field(init=False)
    dPb207s_dR76m: float = field(init=False)
    dPb207s_dFPb: float = field(init=False)
    dPb207s_dR65t: float = field(init=False)
    dPb207s_dR76t: float = field(init=False)
    dPb207s_dPb206b: float = field(init=False)
    dPb207s_dR76b: float = field(init=False)

    dPb207r_dR65m: float = field(init=False)
    dPb207r_dR76m: float = field(init=False)
    dPb207r_dR46m: float = field(init=False)
    dPb207r_dFPb: float = field(init=False)
    dPb207r_dR65t: float = field(init=False)
    dPb207r_dR76t: float = field(init=False)
    dPb207r_dR45t: float = field(init=False)
    dPb207r_dPb206b: float = field(init=False)
    dPb207r_dR64b: float = field(init=False)
    dPb207r_dR76b: float = field(init=False)
    dPb207r_dR64c: float = field(init=False)
    dPb207r_dR76c: float = field(init=False)

    dPb204c_dR46m: float = field(init=False)
    dPb204c_dR65m: float = field(init=False)
    dPb204c_dFPb: float = field(init=False)
    dPb204c_dR46t: float = field(init=False)
    dPb204c_dR65t: float = field(init=False)
    dPb204c_dPb206b: float = field(init=False)
    dPb204c_dR64b: float = field(init=False)
    dFU_dR85m: float = field(init=False)
    dFU_dR85t: float = field(init=False)
    dFU_dR35m: float = field(init=False)
    dFU_dR35t: float = field(init=False)
    dU235s_dU238s: float = field(init=False)
    dU238s_dR85m: float = field(init=False)
    dU238s_dR85t: float = field(init=False)
    dU238s_dU238b: float = field(init=False)
    dU238s_dFU: float = field(init=False)

    dPb208r_dR85m: float = field(init=False)
    dPb208r_dR45m: float = field(init=False)
    dPb208r_dFPb: float = field(init=False)
    dPb208r_dR85t: float = field(init=False)
    dPb208r_dR45t: float = field(init=False)
    dPb208r_dPb206b: float = field(init=False)
    dPb208r_dR64b: float = field(init=False)
    dPb208r_dR86b: float = field(init=False)
    dPb208r_dR84c: float = field(init=False)

    # covariances
    cov_45_65_t: float = field(init=False)
    cov_76_65_m: float = field(init=False)
    cov_76_65_t: float = field(init=False)
    cov_65_46_m: float = field(init=False)
    cov_65_46_t: float = field(init=False)
    cov_85_35_m: float = field(init=False)
    cov_85_35_t: float = field(init=False)
    cov_85_45_m: float = field(init=False)
    cov_85_45_t: float = field(init=False)
    cov_86_64_b: float = field(init=False) # blank 8664 covariance

    cov_R46s: float = field(init=False)
    cov_R47s: float = field(init=False)
    cov_R76s: float = field(init=False)

    cov_R76r: float = field(init=False)

    # error correlation coefficients
    rho_8464_s: float = field(init=False)
    rho_5474_s: float = field(init=False)
    rho_8676_s: float = field(init=False)
    rho_8646_s: float = field(init=False)

    rho_7464_s: float = field(init=False)
    rho_7646_s: float = field(init=False)

    rho_7568_r: float = field(init=False)
    rho_8676_r: float = field(init=False)

    def print_general_info(self):
        print(f"Grain ID: {self.id}")
        print(f"Sample weight (g): {self.sample_weight}")
        print(f"Spike weight (g): {self.spike_weight}")
        print(f"Spike type: {self.spike_type}")
        print(f"Spike name: {self.spike_name}")
        print(f"Collector: {self.collector}")

    def print_tracer_info(self):
        print(f"Pb-205 tracer amount (mol): {self.Pb205t}")
        print(f"U-235 tracer amount (mol): {self.U235t}")
        if self.Pb_R25t is not None:
            print(f"Pb-202/205 tracer ratio: {self.Pb_R25t} ± {self.Pb_R25t_std}")
        print(f"Pb-204/205 tracer ratio: {self.Pb_R45t} ± {self.Pb_R45t_std}")
        print(f"Pb-204/206 tracer ratio: {self.Pb_R46t} ± {self.Pb_R46t_std}")
        print(f"Pb-206/205 tracer ratio: {self.Pb_R65t} ± {self.Pb_R65t_std}")
        print(f"Pb-207/205 tracer ratio: {self.Pb_R75t} ± {self.Pb_R75t_std}")
        print(f"Pb-207/206 tracer ratio: {self.Pb_R76t} ± {self.Pb_R76t_std}")
        print(f"Pb-208/205 tracer ratio: {self.Pb_R85t} ± {self.Pb_R85t_std}")
        print(f"U-235/233 tracer ratio: {self.U_R35t} ± {self.U_R35t_std}")
        print(f"U-238/233 tracer ratio: {self.U_R83t} ± {self.U_R83t_std}")
        print(f"U-238/235 tracer ratio: {self.U_R85t} ± {self.U_R85t_std}")

    def print_blank_info(self):
        print(f"Total Pb blank (mol): {self.Pb_blank_total} ± {self.Pb_blank_total_std}")
        print(f"Pb-204 blank (mol): {self.Pb204b}")
        print(f"Pb-206 blank (mol): {self.Pb206b} ± {self.Pb206b_std}")
        print(f"Pb-207 blank (mol): {self.Pb207b}")
        print(f"Pb-208 blank (mol): {self.Pb208b}")
        print(f"Total U blank (mol): {self.U_blank_total} ± {self.U_blank_total_std}")
        print(f"U-238 blank (mol): {self.U238b} ± {self.U238b_std}")
        print(f"Pb-206/204 blank ratio: {self.R64b} ± {self.R64b_std}")
        print(f"Pb-207/204 blank ratio: {self.R74b} ± {self.R74b_std}")
        print(f"Pb-208/204 blank ratio: {self.R84b} ± {self.R84b_std}")

    def print_initial_info(self):
        print(f"Initial Pb-204 (mol): {self.Pb204c} ± {self.Pb204c_std}")
        print(f"Initial Pb-206 (mol): {self.Pb206c}")
        print(f"Initial Pb-207 (mol): {self.Pb207c}")
        print(f"Initial Pb-208 (mol): {self.Pb208c}")
        print(f"Initial Pb-206/204 ratio: {self.R64c} ± {self.R64c_std}")
        print(f"Initial Pb-207/206 ratio: {self.R76c} ± {self.R76c_std}")

    def print_measurement_info(self):
        if self.Pb_R25m is not None:
            print(f"Measured Pb-202/205 ratio: {self.Pb_R25m} ± {self.Pb_R25m_std}")
        print(f"Measured Pb-204/205 ratio: {self.Pb_R45m} ± {self.Pb_R45m_std}")
        print(f"Measured Pb-204/206 ratio: {self.Pb_R46m} ± {self.Pb_R46m_std}")
        print(f"Measured Pb-206/204 ratio: {self.Pb_R64m} ± {self.Pb_R64m_std}")
        print(f"Measured Pb-206/205 ratio: {self.Pb_R65m} ± {self.Pb_R65m_std}")
        print(f"Measured Pb-207/206 ratio: {self.Pb_R76m} ± {self.Pb_R76m_std}")
        print(f"Measured Pb-208/205 ratio: {self.Pb_R85m} ± {self.Pb_R85m_std}")
        print(f"Measured U-238/235 ratio: {self.U_R85m} ± {self.U_R85m_std}")
        print(f"Measured U-235/233 ratio: {self.U_R35m} ± {self.U_R35m_std}")
        print(f"Measured U-238/233 ratio: {self.U_R83m} ± {self.U_R83m_std}")

    def print_radiogenic_quantities(self):
        print(f"Radiogenic Pb-206 (mol): {self.Pb206r} ± {self.Pb206r_std}")
        print(f"Radiogenic Pb-207 (mol): {self.Pb207r} ± {self.Pb207r_std}")
        print(f"Radiogenic Pb-207/206 ratio: {self.R76r} ± {self.R76r_std}")
        print(f"Radiogenic U-238 (mol): {self.U238s} ± {self.U238s_std}")
        print(f"Radiogenic U-235 (mol): {self.U235s} ± {self.U235s_std}")
        print(f"Radiogenic 206Pb/238U ratio: {self.R68r} ± {self.R68r_std}")
        print(f"Radiogenic 207Pb/235U ratio: {self.R75r} ± {self.R75r_std}")

    def print_molar_quantities(self):
        print(f"Sample Pb-206 (mol): {self.Pb206s} ± {self.Pb206s_std}")
        print(f"Sample Pb-207 (mol): {self.Pb207s} ± {self.Pb207s_std}")
        print(f"Sample Pb-204 (mol): {self.Pb204c} ± {self.Pb204c_std}")
        print(f"Sample U-238 (mol): {self.U238s} ± {self.U238s_std}")
        print(f"Sample U-235 (mol): {self.U235s} ± {self.U235s_std}")

        print(f"Radiogenic Pb-206 (mol): {self.Pb206r} ± {self.Pb206r_std}")
        print(f"Radiogenic Pb-207 (mol): {self.Pb207r} ± {self.Pb207r_std}")
        print(f"Radiogenic Pb-208 (mol): {self.Pb208r} ± {self.Pb208r_std}")

    def print_partials(self):
        print("Partial derivatives for Pb-206s:")
        print(f"dPb206s/dR65m: {self.dPb206s_dR65m}")
        print(f"dPb206s/dR65t: {self.dPb206s_dR65t}")
        print(f"dPb206s/dFPb: {self.dPb206s_dFPb}")
        print(f"dPb206s/dPb206b: {self.dPb206s_dPb206b}")

        print("Partial derivatives for Pb-206r:")
        print(f"dPb206r/dR65m: {self.dPb206r_dR65m}")
        print(f"dPb206r/dR46m: {self.dPb206r_dR46m}")
        print(f"dPb206r/dR65t: {self.dPb206r_dR65t}")
        print(f"dPb206r/dR45t: {self.dPb206r_dR45t}")
        print(f"dPb206r/dFPb: {self.dPb206r_dFPb}")
        print(f"dPb206r/dPb206b: {self.dPb206r_dPb206b}")
        print(f"dPb206r/dR64b: {self.dPb206r_dR64b}")
        print(f"dPb206r/dR64c: {self.dPb206r_dR64c}")
        
        print("Partial derivatives for Pb-207s:")
        print(f"dPb207s/dR65m: {self.dPb207s_dR65m}")
        print(f"dPb207s/dR76m: {self.dPb207s_dR76m}")
        print(f"dPb207s/dFPb: {self.dPb207s_dFPb}")
        print(f"dPb207s/dR65t: {self.dPb207s_dR65t}")
        print(f"dPb207s/dR76t: {self.dPb207s_dR76t}")
        print(f"dPb207s/dPb206b: {self.dPb207s_dPb206b}")
        print(f"dPb207s/dR76b: {self.dPb207s_dR76b}")

        print("Partial derivatives for Pb-207r:")
        print(f"dPb207r/dR65m: {self.dPb207r_dR65m}")
        print(f"dPb207r/dR76m: {self.dPb207r_dR76m}")
        print(f"dPb207r/dR46m: {self.dPb207r_dR46m}")
        print(f"dPb207r/dFPb: {self.dPb207r_dFPb}")
        print(f"dPb207r/dR65t: {self.dPb207r_dR65t}")
        print(f"dPb207r/dR76t: {self.dPb207r_dR76t}")
        print(f"dPb207r/dR45t: {self.dPb207r_dR45t}")
        print(f"dPb207r/dPb206b: {self.dPb207r_dPb206b}")
        print(f"dPb207r/dR64b: {self.dPb207r_dR64b}")
        print(f"dPb207r/dR76b: {self.dPb207r_dR76b}")
        print(f"dPb207r/dR64c: {self.dPb207r_dR64c}")
        print(f"dPb207r/dR76c: {self.dPb207r_dR76c}")

        print("Partial derivatives for Pb-204c:")
        print(f"dPb204c/dR46m: {self.dPb204c_dR46m}")
        print(f"dPb204c/dR65m: {self.dPb204c_dR65m}")
        print(f"dPb204c/dFPb: {self.dPb204c_dFPb}")
        print(f"dPb204c/dR46t: {self.dPb204c_dR46t}")
        print(f"dPb204c/dR65t: {self.dPb204c_dR65t}")
        print(f"dPb204c/dPb206b: {self.dPb204c_dPb206b}")
        print(f"dPb204c/dR64b: {self.dPb204c_dR64b}")

        print("Partial derivatives for Pb-208r:")
        print(f"dPb208r/dR85m: {self.dPb208r_dR85m}")
        print(f"dPb208r/dR45m: {self.dPb208r_dR45m}")
        print(f"dPb208r/dFPb: {self.dPb208r_dFPb}")
        print(f"dPb208r/dR85t: {self.dPb208r_dR85t}")
        print(f"dPb208r/dR45t: {self.dPb208r_dR45t}")
        print(f"dPb208r/dPb206b: {self.dPb208r_dPb206b}")
        print(f"dPb208r/dR64b: {self.dPb208r_dR64b}")
        print(f"dPb208r/dR86b: {self.dPb208r_dR86b}")
        print(f"dPb208r/dR84c: {self.dPb208r_dR84c}")

        print("Partial derivatives for FU:")
        print(f"dFU/dR85m: {self.dFU_dR85m}")
        print(f"dFU/dR85t: {self.dFU_dR85t}")
        print(f"dFU/dR35m: {self.dFU_dR35m}")
        print(f"dFU/dR35t: {self.dFU_dR35t}")

        print("Partial derivatives for U238s:")
        print(f"dU238s/dR85m: {self.dU238s_dR85m}")
        print(f"dU238s/dR85t: {self.dU238s_dR85t}")
        print(f"dU238s/dFU: {self.dU238s_dFU}")
        print(f"dU238s/dU238b: {self.dU238s_dU238b}")

        print("Partial derivatives for U235s:")
        print(f"dU235s/dU238s: {self.dU235s_dU238s}")
                                
    def __repr__(self):
        return f"UPb_grain(id={self.id!r}, spike={self.spike_name!r}, reduced={'t68' in self.__dict__})"

    def print_ages(self, rounding=3):
        print(f"U-Pb 206/238 age (Ma, 2σ): {self.t68:.{rounding}f} ± {(self.t68_std*2):.{rounding}f}")
        print(f"U-Pb 207/235 age (Ma, 2σ): {self.t75:.{rounding}f} ± {(self.t75_std*2):.{rounding}f}")
        print(f"Pb-Pb 207/206 age (Ma, 2σ): {self.t76:.{rounding}f} ± {(self.t76_std*2):.{rounding}f}")

        if self.Th230_correction_type is not None:
            print(f"Th-corrected U-Pb 206/238 age (Ma, 2σ): {self.t68_Th_corr:.{rounding}f} ± {(self.t68_Th_corr_std*2):.{rounding}f}")
            print(f"Th-corrected Pb-Pb 207/206 age (Ma, 2σ): {self.t76_Th_corr:.{rounding}f} ± {(self.t76_Th_corr_std*2):.{rounding}f}")

    def calc_U_blank_AW(self):
        self.U_blank_AW = calc_U_blank_AW()

    def calc_U238b(self):
        U238_blanks = calc_U238b(self.U_blank_total, self.U_blank_total_std, self.U_blank_AW)
        self.U238b = U238_blanks["U238b"]
        self.U238b_std = U238_blanks["U238b_std"]

    def calc_rad_Pb(self):
        self.Pbr_pg = calc_rad_Pb(self.Pb206r, self.Pb207r, self.Pb208r)

    def calc_Pbr_Pbc(self):
        self.Pbr_Pbc = self.Pbr_pg / self.Pbc_pg

    def calc_Pb_blank_AWS(self):
        self.Pb_blank_AW = calc_Pb_blank_AW(self.R64b, self.R74b, self.R84b)

    def calc_Pb_partitioning(self):
        Pb_partitioning = calc_Pb_partitioning(self.Pb_R65m, self.Pb_R46m, 
                                                self.FPb, 
                                                self.Pb205t, 
                                                self.Pb_R65t, self.Pb_R46t,
                                                self.Pb_blank_total, 
                                                self.Pb_blank_total_std,
                                                self.R64b, self.R74b, self.R84b, 
                                                self.Pb_blank_AW,
                                                R64c=self.R64c, R74c=self.R74c, R84c=self.R84c)
        self.Pbc_pg = Pb_partitioning['Pbc_pg']
        self.Pb204b = Pb_partitioning['Pb204b']
        self.Pb206b = Pb_partitioning['Pb206b']
        self.Pb207b = Pb_partitioning['Pb207b']
        self.Pb208b = Pb_partitioning['Pb208b']
        self.Pb204c = Pb_partitioning['Pb204c']
        self.Pb206c = Pb_partitioning['Pb206c']
        self.Pb207c = Pb_partitioning['Pb207c']
        self.Pb208c = Pb_partitioning['Pb208c']
        self.Pb206b_std = Pb_partitioning['Pb206b_std']
        # No initial common Pb: use the blank composition in the radiogenic
        # formulas, and remove uncertainty in an inapplicable initial component.
        if self.Pb204c == 0:
            self.R64c, self.R74c, self.R84c = self.R64b, self.R74b, self.R84b
            self.R76c = self.R76b
            self.R64c_std = self.R74c_std = self.R84c_std = self.R76c_std = 0.0

    def calc_total_Pb_ppm(self):
        self.Pb_ppm = calc_total_Pb_ppm(self.sample_weight, 
                                                self.Pb204b, self.Pb204c, 
                                                self.Pb206b, self.Pb206c, self.Pb206r,
                                                self.Pb207b, self.Pb207c, self.Pb207r,
                                                self.Pb208b, self.Pb208c, self.Pb208r,)

    def Pb206s_partials(self):
        partials = Pb206s_partials(self.Pb_R65m, self.FPb,self.Pb205t)

        self.dPb206s_dR65m = partials["dPb206s_dR65m"]
        self.dPb206s_dR65t = partials["dPb206s_dR65t"]
        self.dPb206s_dFPb = partials["dPb206s_dFPb"]
        self.dPb206s_dPb206b = partials["dPb206s_dPb206b"]

    def Pb206r_partials(self):
        partials = Pb206r_partials(self.Pb_R65m, self.Pb_R46m, 
                                   self.FPb, 
                                   self.Pb205t, 
                                   self.Pb_R45t,
                                   self.R64b, self.Pb206b,
                                   self.R64c)

        self.dPb206r_dR65m = partials["dPb206r_dR65m"]
        self.dPb206r_dR46m = partials["dPb206r_dR46m"]
        self.dPb206r_dR65t = partials["dPb206r_dR65t"]
        self.dPb206r_dR45t = partials["dPb206r_dR45t"]
        self.dPb206r_dFPb = partials["dPb206r_dFPb"]
        self.dPb206r_dPb206b = partials["dPb206r_dPb206b"]
        self.dPb206r_dR64b = partials["dPb206r_dR64b"]
        self.dPb206r_dR64c = partials["dPb206r_dR64c"]

    def Pb207s_partials(self):
        partials = Pb207s_partials(self.Pb_R65m, self.Pb_R76m, 
                                   self.FPb, 
                                   self.Pb205t, 
                                   self.Pb_R65t, 
                                   self.Pb_R76t, 
                                   self.R76b, 
                                   self.Pb206b)

        self.dPb207s_dR65m = partials["dPb207s_dR65m"]
        self.dPb207s_dR76m = partials["dPb207s_dR76m"]
        self.dPb207s_dFPb = partials["dPb207s_dFPb"]
        self.dPb207s_dR65t = partials["dPb207s_dR65t"]
        self.dPb207s_dR76t = partials["dPb207s_dR76t"]
        self.dPb207s_dPb206b = partials["dPb207s_dPb206b"]
        self.dPb207s_dR76b = partials["dPb207s_dR76b"]

    def Pb207r_partials(self):
        partials = Pb207r_partials(self.Pb_R65m, self.Pb_R76m, self.Pb_R46m,
                                   self.FPb, 
                                   self.Pb205t, 
                                   self.Pb_R45t,
                                   self.Pb_R65t, 
                                   self.Pb_R76t, 
                                   self.R76b, 
                                   self.R64b,
                                   self.Pb206b, 
                                   self.R64c,
                                   self.R76c)

        self.dPb207r_dR65m = partials["dPb207r_dR65m"]
        self.dPb207r_dR76m = partials["dPb207r_dR76m"]
        self.dPb207r_dR46m = partials["dPb207r_dR46m"]
        self.dPb207r_dFPb = partials["dPb207r_dFPb"]
        self.dPb207r_dR65t = partials["dPb207r_dR65t"]
        self.dPb207r_dR76t = partials["dPb207r_dR76t"]
        self.dPb207r_dR45t = partials["dPb207r_dR45t"]
        self.dPb207r_dPb206b = partials["dPb207r_dPb206b"]
        self.dPb207r_dR64b = partials["dPb207r_dR64b"]
        self.dPb207r_dR76b = partials["dPb207r_dR76b"]
        self.dPb207r_dR64c = partials["dPb207r_dR64c"]
        self.dPb207r_dR76c = partials["dPb207r_dR76c"]

    def Pb204c_partials(self):
        partials = Pb204c_partials(self.Pb_R46m, self.Pb_R65m, 
                                   self.FPb, 
                                   self.Pb205t, 
                                   self.Pb_R46t, 
                                   self.Pb_R65t, 
                                   self.Pb206b, 
                                   self.R64b)

        self.dPb204c_dR46m = partials["dPb204c_dR46m"]
        self.dPb204c_dR65m = partials["dPb204c_dR65m"]
        self.dPb204c_dFPb = partials["dPb204c_dFPb"]
        self.dPb204c_dR46t = partials["dPb204c_dR46t"]
        self.dPb204c_dR65t = partials["dPb204c_dR65t"]
        self.dPb204c_dPb206b = partials["dPb204c_dPb206b"]
        self.dPb204c_dR64b = partials["dPb204c_dR64b"]

    def Pb208r_partials(self):
        partials = Pb208r_partials(self.Pb_R85m, 
                                    self.Pb_R45m,
                                    self.FPb,
                                    self.Pb205t,
                                    self.Pb_R45t,
                                    self.Pb206b,
                                    self.R64b,
                                    self.R86b,
                                    self.R84c)
        
        self.dPb208r_dR85m = partials["dPb208r_dR85m"]
        self.dPb208r_dR45m = partials["dPb208r_dR45m"]
        self.dPb208r_dFPb = partials["dPb208r_dFPb"]
        self.dPb208r_dR85t = partials["dPb208r_dR85t"]
        self.dPb208r_dR45t = partials["dPb208r_dR45t"]
        self.dPb208r_dPb206b = partials["dPb208r_dPb206b"]
        self.dPb208r_dR64b = partials["dPb208r_dR64b"]
        self.dPb208r_dR86b = partials["dPb208r_dR86b"]
        self.dPb208r_dR84c = partials["dPb208r_dR84c"]
        
    def FU_partials(self):
        partials = FU_partials(self.U_R35m, self.U_R85m,  
                              self.U_R35t, self.U_R85t, self.common_U238_U235)

        self.dFU_dR35t = partials["dFU_dR35t"]
        self.dFU_dR85t = partials["dFU_dR85t"]
        self.dFU_dR35m = partials["dFU_dR35m"]
        self.dFU_dR85m = partials["dFU_dR85m"]

    def U238s_partials(self):
        partials = U238s_partials(self.U_R85m, self.FU, self.U235t, self.U_R85t, self.U238b, self.common_U238_U235)

        self.dU238s_dR85m = partials["dU238s_dR85m"]
        self.dU238s_dR85t = partials["dU238s_dR85t"]
        self.dU238s_dU238b = partials["dU238s_dU238b"]
        self.dU238s_dFU = partials["dU238s_dFU"]

    def U235s_partials(self):
        partials = U235s_partials(self.common_U238_U235)
        self.dU235s_dU238s = partials["dU235s_dU238s"]

    def Pb_covariance_squared(self):
        covariances = Pb_covariance_squared(self.Pb_R75m, self.Pb_R75m_std, 
                                                self.Pb_R76m, self.Pb_R76m_std, 
                                                self.Pb_R65m, self.Pb_R65m_std, 
                                                self.Pb_R45m, self.Pb_R45m_std,
                                                self.Pb_R46m, self.Pb_R46m_std,
                                                self.Pb_R84m, self.Pb_R84m_std,
                                                self.Pb_R85m, self.Pb_R85m_std,
                                                self.Pb_R75t, self.Pb_R75t_std,
                                                self.Pb_R76t, self.Pb_R76t_std,
                                                self.Pb_R65t, self.Pb_R65t_std,
                                                self.Pb_R45t, self.Pb_R45t_std,
                                                self.Pb_R46t, self.Pb_R46t_std,
                                                self.Pb_R84t, self.Pb_R84t_std,
                                                self.Pb_R85t, self.Pb_R85t_std,
                                                self.R64b, self.R64b_std,
                                                self.R84b, self.R84b_std,
                                                self.R86b, self.R86b_std)

        self.cov_76_65_m = covariances["cov_76_65_m"]
        self.cov_76_65_t = covariances["cov_76_65_t"]
        self.cov_65_46_m = covariances["cov_65_46_m"]
        self.cov_45_65_t = covariances["cov_45_65_t"]
        self.cov_65_46_t = covariances["cov_65_46_t"]
        self.cov_85_45_m = covariances["cov_85_45_m"]
        self.cov_85_45_t = covariances["cov_85_45_t"]
        self.cov_86_64_b = covariances["cov_86_64_b"]

    def U_covariance_squared(self):
        covariances = U_covariance_squared(self.U_R83m, self.U_R83m_std,
                                            self.U_R85m, self.U_R85m_std,
                                            self.U_R35m, self.U_R35m_std,
                                            self.U_R83t, self.U_R83t_std,
                                            self.U_R85t, self.U_R85t_std,
                                            self.U_R35t, self.U_R35t_std)

        self.cov_85_35_m = covariances["cov_85_35_m"]
        self.cov_85_35_t = covariances["cov_85_35_t"]

    def calc_Pb206s(self):
        self.Pb206s = calc_Pb206s(self.Pb_R65m, self.FPb, 
                                  self.Pb205t, self.Pb_R65t, 
                                  self.Pb206b)
        
    def prop_Pb206s_uncertainty(self):
        self.Pb206s_std = prop_Pb206s_uncertainty(self.dPb206s_dR65m, self.Pb_R65m_std,
                                                    self.dPb206s_dFPb, self.FPb_std,
                                                    self.dPb206s_dR65t, self.Pb_R65t_std,
                                                    self.dPb206s_dPb206b, self.Pb206b_std)

    def calc_Pb207s(self):
        self.Pb207s = calc_Pb207s(self.Pb_R65m, self.Pb_R76m, 
                                  self.FPb, 
                                  self.Pb205t, self.Pb_R65t, self.Pb_R76t, 
                                  self.R76b, self.Pb206b)
        
    def prop_Pb207s_uncertainty(self):
        self.Pb207s_std = prop_Pb207s_uncertainty(self.dPb207s_dR65m, self.Pb_R65m_std,
                                                    self.dPb207s_dR76m, self.Pb_R76m_std,
                                                    self.dPb207s_dFPb, self.FPb_std,
                                                    self.dPb207s_dR65t, self.Pb_R65t_std,
                                                    self.dPb207s_dR76t, self.Pb_R76t_std,
                                                    self.dPb207s_dPb206b, self.Pb206b_std,
                                                    self.dPb207s_dR76b, self.R76b_std,
                                                    self.cov_76_65_m, self.cov_76_65_t)

    def calc_Pb204c(self):
        """Recalculate through the partition, which owns initial Pb amounts.

        In particular, an all-blank partition must stay exactly zero rather
        than acquire a floating-point residue from subtracting the blank again.
        """
        self.calc_Pb_partitioning()
        
    def prop_Pb204c_uncertainty(self):
        self.Pb204c_std = prop_Pb204c_uncertainty(self.dPb204c_dR46m, self.Pb_R46m_std,
                                                    self.dPb204c_dR65m, self.Pb_R65m_std,
                                                    self.dPb204c_dFPb, self.FPb_std,
                                                    self.dPb204c_dR46t, self.Pb_R46t_std,
                                                    self.dPb204c_dR65t, self.Pb_R65t_std,
                                                    self.dPb204c_dPb206b, self.Pb206b_std,
                                                    self.dPb204c_dR64b, self.R64b_std,
                                                    self.cov_65_46_m, self.cov_65_46_t)

    def calc_FU(self):
        self.FU = calc_FU(self.U_R35m, self.U_R85m,
                          self.U_R35t, self.U_R85t, 
                          self.common_U238_U235)

    def prop_FU_uncertainty(self):
        self.FU_std = prop_FU_uncertainty(self.dFU_dR35t, self.U_R35t_std,
                                            self.dFU_dR85m, self.U_R85m_std,
                                            self.dFU_dR35m, self.U_R35m_std,
                                            self.dFU_dR85t, self.U_R85t_std,
                                            self.cov_85_35_m, self.cov_85_35_t)

    def calc_U238s(self):
        self.U238s = calc_U238s(self.U_R85m, self.FU, self.U235t, self.U_R85t, self.U238b, self.common_U238_U235)

    def prop_U238s_uncertainty(self):
        self.U238s_std = prop_U238s_uncertainty(self.dU238s_dR85m, self.U_R85m_std,
                                                self.dU238s_dFU, self.FU_std,
                                                self.dU238s_dR85t, self.U_R85t_std,
                                                self.dU238s_dU238b, self.U238b_std)

    def calc_U235s(self):
        self.U235s = calc_U235s(self.U238s, self.common_U238_U235)

    def prop_U235s_uncertainty(self):
        self.U235s_std = prop_U235s_uncertainty(self.dU235s_dU238s, self.U238s_std)

    def calc_rad_U(self):
        self.U_ng = calc_rad_U(self.U238s, self.U235s)

    def calc_total_U_ppm(self):
        self.U_ppm = calc_total_U_ppm(self.sample_weight, 
                                            self.U_ng)
        
    def calc_PbPb_Rs(self):
        self.R46s = self.Pb204c / self.Pb206s
        self.R47s = self.Pb204c / self.Pb207s
        if self.Pb204c > 0:
            self.R64s = self.Pb206s / self.Pb204c
            self.R74s = self.Pb207s / self.Pb204c
        else:
            self.R64s = 0.0
            self.R74s = 0.0
        self.R76s = self.Pb207s / self.Pb206s

    def calc_UPb_Rs(self):
        if self.Pb204c > 0:
            self.R54s = self.U235s / self.Pb204c
            self.R84s = self.U238s / self.Pb204c
        else:
            self.R54s = 0.0
            self.R84s = 0.0
        self.R57s = self.U235s / self.Pb207s
        self.R86s = self.U238s / self.Pb206s
        self.R87s = self.U238s / self.Pb207s

    def prop_cov_Pb_Rs_squared(self):
        self.cov_R46s = prop_cov_Pb_R46s_squared(self.dPb204c_dR65m, self.dPb206s_dR65m, self.Pb_R65m_std,
                                                self.dPb204c_dFPb, self.dPb206s_dFPb, self.FPb_std,
                                                self.dPb204c_dR65t, self.dPb206s_dR65t, self.Pb_R65t_std,
                                                self.dPb204c_dPb206b, self.dPb206s_dPb206b, self.Pb206b_std)
        self.cov_R47s = prop_cov_Pb_R47s_squared(self.dPb207s_dR65m, self.dPb204c_dR65m, self.Pb_R65m_std,
                                                self.dPb207s_dFPb, self.dPb204c_dFPb, self.FPb_std,
                                                self.dPb207s_dR65t, self.dPb204c_dR65t, self.Pb_R65t_std,
                                                self.dPb207s_dPb206b, self.dPb204c_dPb206b, self.Pb206b_std)
        self.cov_R76s = prop_cov_Pb_R76s_squared(self.dPb207s_dR65m, self.dPb206s_dR65m, self.Pb_R65m_std,
                                                self.dPb207s_dFPb, self.dPb206s_dFPb, self.FPb_std,
                                                self.dPb207s_dR65t, self.dPb206s_dR65t, self.Pb_R65t_std,
                                                self.dPb207s_dPb206b, self.dPb206s_dPb206b, self.Pb206b_std)
        
    def calc_all_Pb_Rs_uncertainty(self):
        self.R46s_std = calc_PbPb_uncertainty(self.Pb204c, self.Pb206s,
                                                  self.Pb204c_std, self.Pb206s_std,
                                                  self.cov_R46s)['abs_std']
        self.R47s_std = calc_PbPb_uncertainty(self.Pb204c, self.Pb207s,
                                                  self.Pb204c_std, self.Pb207s_std,
                                                  self.cov_R47s)['abs_std']
        self.R64s_std = calc_PbPb_uncertainty(self.Pb206s, self.Pb204c,
                                                  self.Pb206s_std, self.Pb204c_std,
                                                  self.cov_R46s)['abs_std']
        self.R74s_std = calc_PbPb_uncertainty(self.Pb207s, self.Pb204c,
                                                  self.Pb207s_std, self.Pb204c_std,
                                                  self.cov_R47s)['abs_std']
        self.R76s_std = calc_PbPb_uncertainty(self.Pb207s, self.Pb206s,
                                                  self.Pb207s_std, self.Pb206s_std,
                                                  self.cov_R76s)['abs_std']
        
    def calc_all_UPb_Rs_uncertainty(self):
        self.R54s_std = calc_UPb_uncertainty(self.U235s, self.Pb204c,
                                                self.U235s_std, self.Pb204c_std)['abs_std']
        self.R57s_std = calc_UPb_uncertainty(self.U235s, self.Pb207s,
                                                self.U235s_std, self.Pb207s_std)['abs_std']
        self.R84s_std = calc_UPb_uncertainty(self.U238s, self.Pb204c,
                                                self.U238s_std, self.Pb204c_std)['abs_std']
        self.R86s_std = calc_UPb_uncertainty(self.U238s, self.Pb206s,
                                                self.U238s_std, self.Pb206s_std)['abs_std']
        self.R87s_std = calc_UPb_uncertainty(self.U238s, self.Pb207s,
                                                self.U238s_std, self.Pb207s_std)['abs_std']

    def calc_PbPbs_rhos(self):
        PbPbs_rhos = calc_PbPbs_rhos(self.R74s, self.R74s_std,
                                    self.R64s, self.R64s_std,
                                    self.R76s, self.R76s_std,
                                    self.R46s, self.R46s_std)
        self.rho_7464_s = PbPbs_rhos["rho_7464_s"]
        self.rho_7646_s = PbPbs_rhos["rho_7646_s"]

    def calc_UPbs_rhos(self):
        UPbs_rhos = calc_UPbs_rhos(self.R64s, self.R64s_std,
                                    self.R74s, self.R74s_std,
                                    self.R76s, self.R76s_std,
                                    self.R46s, self.R46s_std,
                                    self.R84s, self.R84s_std, 
                                    self.R54s, self.R54s_std,
                                    self.R57s, self.R57s_std,
                                    self.R86s, self.R86s_std,
                                    self.R87s, self.R87s_std)
        self.rho_8464_s = UPbs_rhos["rho_8464_s"]
        self.rho_5474_s = UPbs_rhos["rho_5474_s"]
        self.rho_8676_s = UPbs_rhos["rho_8676_s"]
        self.rho_8646_s = UPbs_rhos["rho_8646_s"]

    def calc_Pb206r(self):
        self.Pb206r = calc_Pb206r(self.Pb_R65m, self.Pb_R46m,
                                    self.FPb,
                                    self.Pb205t,
                                    self.Pb_R65t,
                                    self.Pb_R45t,
                                    self.R64c,
                                    self.R64b,
                                    self.Pb206b,
                                    Pb204c=0.0 if self.Pb204c == 0 else None)
    
    def prop_Pb206r_uncertainty(self):
        self.Pb206r_std = prop_Pb206r_uncertainty(self.dPb206r_dR65m, self.Pb_R65m_std,
                                                    self.dPb206r_dR46m, self.Pb_R46m_std,
                                                    self.dPb206r_dFPb, self.FPb_std,
                                                    self.dPb206r_dR65t, self.Pb_R65t_std,
                                                    self.dPb206r_dR45t, self.Pb_R45t_std,
                                                    self.dPb206r_dR64c, self.R64c_std,
                                                    self.dPb206r_dR64b, self.R64b_std,
                                                    self.dPb206r_dPb206b, self.Pb206b_std,
                                                    self.cov_65_46_m, self.cov_45_65_t)
        
    def calc_Pb207r(self):
        self.Pb207r = calc_Pb207r(self.Pb_R65m, self.Pb_R76m, self.Pb_R46m,
                                    self.FPb,
                                    self.Pb205t,
                                    self.Pb_R65t,
                                    self.Pb_R76t,
                                    self.Pb_R45t,
                                    self.R76c,
                                    self.R64c,
                                    self.R64b,
                                    self.R76b,
                                    self.Pb206b,
                                    Pb204c=0.0 if self.Pb204c == 0 else None)
        
    def prop_Pb207r_uncertainty(self):
        self.Pb207r_std = prop_Pb207r_uncertainty(self.dPb207r_dR65m, self.Pb_R65m_std,
                                                    self.dPb207r_dR76m, self.Pb_R76m_std,
                                                    self.dPb207r_dR46m, self.Pb_R46m_std,
                                                    self.dPb207r_dFPb, self.FPb_std,
                                                    self.dPb207r_dR65t, self.Pb_R65t_std,
                                                    self.dPb207r_dR76t, self.Pb_R76t_std,
                                                    self.dPb207r_dR45t, self.Pb_R45t_std,
                                                    self.dPb207r_dR76c, self.R76c_std,
                                                    self.dPb207r_dR64c, self.R64c_std,
                                                    self.dPb207r_dR64b, self.R64b_std,
                                                    self.dPb207r_dR76b, self.R76b_std,
                                                    self.dPb207r_dPb206b, self.Pb206b_std,
                                                    self.cov_76_65_m, self.cov_65_46_m,
                                                    self.cov_76_65_t, self.cov_45_65_t)
    def calc_R76r(self):
        self.R76r = self.Pb207r / self.Pb206r

    def prop_cov_R76r_squared(self):
        self.cov_R76r = prop_cov_Pb76r_squared(self.dPb207r_dR65m, self.dPb206r_dR65m, self.Pb_R65m_std,
                                                self.dPb207r_dR46m, self.dPb206r_dR46m, self.Pb_R46m_std,
                                                self.dPb207r_dFPb, self.dPb206r_dFPb, self.FPb_std,
                                                self.dPb207r_dR65t, self.dPb206r_dR65t, self.Pb_R65t_std,
                                                self.dPb207r_dR45t, self.dPb206r_dR45t, self.Pb_R45t_std,
                                                self.dPb207r_dR64c, self.dPb206r_dR64c, self.R64c_std,
                                                self.dPb207r_dR64b, self.dPb206r_dR64b, self.R64b_std,
                                                self.dPb207r_dPb206b, self.dPb206r_dPb206b, self.Pb206b_std)
    
    def calc_Pb208r(self):
        self.Pb208r = calc_Pb208r(self.Pb_R85m, 
                                  self.FPb, 
                                  self.Pb205t, 
                                  self.Pb_R85t, 
                                  self.Pb208b, 
                                  self.Pb208c)

    def prop_Pb208r_uncertainty(self):
        self.Pb208r_std = prop_Pb208r_uncertainty(self.dPb208r_dR85m, self.Pb_R85m_std,
                            self.dPb208r_dR45m, self.Pb_R45m_std,
                             self.dPb208r_dFPb, self.FPb_std,
                             self.dPb208r_dR85t, self.Pb_R85t_std,
                             self.dPb208r_dR45t, self.Pb_R45t_std,
                             self.dPb208r_dPb206b, self.Pb206b_std,
                             self.dPb208r_dR64b, self.R64b_std,
                             self.dPb208r_dR86b, self.R86b_std,
                             self.dPb208r_dR84c, self.R84c_std,
                             self.cov_85_45_m, self.cov_85_45_t, 
                             self.cov_86_64_b)


    def calc_Pb_Rr_uncertainty(self):
        self.R76r_std = calc_PbPb_uncertainty(self.Pb207r, self.Pb206r,
                                              self.Pb207r_std, self.Pb206r_std,
                                              self.cov_R76r)['abs_std']
        
    def calc_UPb_Rr(self):
        self.R68r = self.Pb206r / self.U238s
        self.R75r = self.Pb207r / self.U235s
        self.R86r = self.U238s / self.Pb206r
        self.R87r = self.U238s / self.Pb207r

    def calc_all_UPb_Rr_uncertainty(self):
        self.R68r_std = calc_UPb_uncertainty(self.Pb206r, self.U238s,
                                              self.Pb206r_std, self.U238s_std)['abs_std']
        self.R75r_std = calc_UPb_uncertainty(self.Pb207r, self.U235s,
                                              self.Pb207r_std, self.U235s_std)['abs_std']
        self.R86r_std = calc_UPb_uncertainty(self.U238s, self.Pb206r,
                                              self.U238s_std, self.Pb206r_std)['abs_std']
        self.R87r_std = calc_UPb_uncertainty(self.U238s, self.Pb207r,
                                              self.U238s_std, self.Pb207r_std)['abs_std']

    def calc_UPbr_rhos(self):
        UPbr_rhos = calc_UPbr_rhos(self.R75r, self.R75r_std,
                                    self.R68r, self.R68r_std,
                                    self.R76r, self.R76r_std,
                                    self.R86r, self.R86r_std,
                                    self.R87r, self.R87r_std)

        self.rho_7568_r = UPbr_rhos["rho_7568_r"]
        self.rho_8676_r = UPbr_rhos["rho_8676_r"]

    def calc_t75(self):
        self.t75 = calc_t75(self.R75r, self.lambda_235)
    
    def calc_t68(self):
        self.t68 = calc_t68(self.R68r, self.lambda_238)

    def calc_t76(self):
        self.t76 = calc_t76(self.R76r, x0=1e6, tol=1e-8, 
                 lambda_235=self.lambda_235, lambda_238=self.lambda_238, 
                 common_U238_U235=self.common_U238_U235)

    def calc_t76_Th_corr(self):
        self.t76_Th_corr = calc_t76(self.R76r_Th, x0=1e6, tol=1e-8,
                 lambda_235=self.lambda_235, lambda_238=self.lambda_238,
                 common_U238_U235=self.common_U238_U235)

    def calc_t75_uncertainty(self):
        self.t75_std = calc_t75_uncertainty(self.R75r, self.R75r_std, self.lambda_235)

    def calc_t68_uncertainty(self):
        self.t68_std = calc_t68_uncertainty(self.R68r, self.R68r_std, self.lambda_238)

    def calc_t76_uncertainty(self):
        self.t76_std = calc_t76_uncertainty(self.t76, self.R76r_std,
                                            self.lambda_235, self.lambda_238,
                                            self.common_U238_U235)

    def calc_Th_corrections(self):
        if self.Th230_correction_type is None:
            self.t68_Th_corr = self.t68
            self.t68_Th_corr_std = self.t68_std
            self.t76_Th_corr = self.t76
            self.t76_Th_corr_std = self.t76_std
        
        elif self.Th230_correction_type == "D":
            self.t68_Th_corr = calc_t68_Th(self.R68r, 
                                            type='D',
                                            D_Th_U=self.D_Th_U, 
                                            Pb208r=None, U238s=None, 
                                            Th_U_magma=None, 
                                            lambda_238=self.lambda_238, 
                                            lambda_230=self.lambda_230, 
                                            x0=1e6, tol=1e-8,
                                            lambda_232=self.lambda_232)
        elif self.Th230_correction_type == "magma":
            self.t68_Th_corr = calc_t68_Th(self.R68r, 
                                            type='magma',
                                            D_Th_U=None, 
                                            Pb208r=self.Pb208r, 
                                            U238s=self.U238s, 
                                            Th_U_magma=self.Th_U_magma, 
                                            lambda_238=self.lambda_238, 
                                            lambda_230=self.lambda_230, 
                                            x0=1e6, tol=1e-8,
                                            lambda_232=self.lambda_232,
                                            common_U238_U235=self.common_U238_U235)
        self.t68_Th_corr_std = self.t68_std
        self.t76_Th_corr_std = self.t76_std


    def calc_Th232s(self):
        self.Th232s = calc_Th232s(self.Pb208r, self.t68_Th_corr, lambda_232=self.lambda_232)

    def calc_Th_ppm(self):
        self.Th_ppm = calc_Th_ppm(self.Th232s, self.sample_weight)
    
    def calc_Pb206r_Th(self): 
        
        self.Pb206r_Th = calc_Pb206r_Th(self.t68_Th_corr, self.U238s, self.lambda_238)["Pb206r_Th"]
        self.R68r_Th = self.Pb206r_Th / self.U238s
        self.R76r_Th = self.Pb207r / self.Pb206r_Th

    def calc_R68r_Th_std(self):
        if self.Th230_correction_type == "D":
            self.R68r_Th_std = calc_R68r_Th_std(self.R68r_std, 
                                                type='D',
                                                D_Th_U_std=self.D_Th_U_std, 
                                                Th_U_magma_std=self.Th_U_magma_std,
                                                lambda_238=self.lambda_238, lambda_230=self.lambda_230,
                                                )
        else:
            self.R68r_Th_std = calc_R68r_Th_std(self.R68r_std, 
                                                type='magma',
                                                Th_U_s=self.Th_U_s,
                                                Th_U_s_std = self.Th_U_s_std,
                                                Th_U_magma=self.Th_U_magma,
                                                Th_U_magma_std=self.Th_U_magma_std,
                                                lambda_238=self.lambda_238, lambda_230=self.lambda_230,
                                                )

    def calc_FPb_2535(self):
        """Set FPb and FPb_std (per amu, fractions) from measured and tracer 202/205.

        Only for 202Pb-205Pb double-spiked (2535) fractions. FPb then enters
        the reduction exactly as a user-supplied 535 factor does.
        """
        for name in ('Pb_R25m', 'Pb_R25m_std', 'Pb_R25t', 'Pb_R25t_std'):
            value = getattr(self, name)
            if value is None or not np.isfinite(value) or value < 0 or (value == 0 and not name.endswith('_std')):
                raise ValueError(f"Grain {self.id}: 2535 reduction needs a finite positive {name}")
        self.FPb, self.FPb_std = calc_FPb_2535(self.Pb_R25m, self.Pb_R25m_std,
                                               self.Pb_R25t, self.Pb_R25t_std)

    def calc_all(self):
        if self.spike_type == 2535:
            self.calc_FPb_2535()
        elif self.spike_type != 535:
            raise NotImplementedError("Raw reduction supports 535 and 2535 tracers only")
        from .quality import check_grain_measurements
        check_grain_measurements(self)
        for name, value in getattr(self, '_initial_Pb_composition', {}).items():
            setattr(self, name, value)
        self.calc_Pb_blank_AWS()
        self.calc_Pb_partitioning()

        self.Pb206s_partials()
        self.Pb207s_partials()
        self.Pb204c_partials()

        self.Pb_covariance_squared()

        self.calc_Pb206s()
        self.prop_Pb206s_uncertainty()

        self.calc_Pb207s()
        self.prop_Pb207s_uncertainty()

        self.prop_Pb204c_uncertainty()

        self.prop_cov_Pb_Rs_squared()
        self.calc_all_Pb_Rs_uncertainty()

        self.calc_PbPb_Rs()
        self.calc_PbPbs_rhos()


        self.Pb206r_partials()
        self.Pb207r_partials()
        self.Pb208r_partials()

        self.calc_Pb206r()
        self.prop_Pb206r_uncertainty()

        self.calc_Pb207r()
        self.prop_Pb207r_uncertainty()

        self.calc_Pb208r()
        self.prop_Pb208r_uncertainty()

        self.calc_rad_Pb()
        self.calc_Pbr_Pbc()

        self.calc_R76r()
        self.prop_cov_R76r_squared()
        self.calc_Pb_Rr_uncertainty()

        self.calc_U_blank_AW()
        self.calc_U238b()

        self.U_covariance_squared()
        self.FU_partials()
        self.calc_FU()
        self.prop_FU_uncertainty()

        self.U238s_partials()
        self.U235s_partials()

        self.calc_U238s()
        self.prop_U238s_uncertainty()

        self.calc_U235s()
        self.prop_U235s_uncertainty()

        self.calc_UPb_Rs()
        self.calc_all_UPb_Rs_uncertainty()
        self.calc_UPbs_rhos()

        self.calc_UPb_Rr()
        self.calc_all_UPb_Rr_uncertainty()
        self.calc_UPbr_rhos()

        from .uncertainty import propagate
        propagate(self)

        self.calc_t75()
        self.calc_t68()
        self.calc_t76()

        self.calc_t75_uncertainty()
        self.calc_t68_uncertainty()
        self.calc_t76_uncertainty()

        self.calc_rad_U()
        self.calc_total_U_ppm()
        self.calc_total_Pb_ppm()

        if self.Th230_correction_type is not None:
            # if we are doing Th corrections
            # first calculate Pb208r related values
            self.calc_Th_corrections()
            self.calc_Th232s()
            self.calc_Th_ppm()
            self.calc_Pb206r_Th()
            from .uncertainty import propagate_th
            propagate_th(self)
            self.calc_t76_Th_corr()
            self.t68_Th_corr_std = calc_t68_uncertainty(self.R68r_Th, self.R68r_Th_std, self.lambda_238)
            self.t76_Th_corr_std = calc_t76_uncertainty(self.t76_Th_corr, self.R76r_Th_std,
                self.lambda_235, self.lambda_238, self.common_U238_U235)
        else:
            self.calc_Th_corrections()
            self.Pb206r_Th = self.Pb206r
            self.R68r_Th, self.R68r_Th_std = self.R68r, self.R68r_std
            self.R76r_Th, self.R76r_Th_std = self.R76r, self.R76r_std
