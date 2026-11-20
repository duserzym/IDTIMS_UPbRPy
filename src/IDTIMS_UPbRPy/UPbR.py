import warnings

import pandas as pd
import numpy as np
from importlib.resources import files
from . import spike_compositions
from .spikes import SPIKES
from .tracer import complete_tracer, TracerCompositionError

from .UPb_grain import UPb_grain


class Missing202Pb205PbError(ValueError, NotImplementedError):
    """A 2535 (202Pb-205Pb double spike) fraction lacks measured or tracer 202Pb/205Pb.

    A ValueError; also a NotImplementedError, which is what earlier versions
    raised for every non-535 fraction.
    """

def load_spike_data(spike_name: str, version: str | None = None,
                    spike_key: str | None = None) -> pd.DataFrame:
    """Read a legacy tracer, or an exact registry key (which overrides version).

    Exact keys never fall back to a legacy mapping or bundled CSV.
    """
    from .spike_registry import get_registry, to_legacy_frame

    if spike_key is not None:
        registry = get_registry()
        selected = registry.by_key(spike_key)
        spike = registry.spikes[selected.spike_id]
        names = {spike.id, spike.name, *spike.aliases,
                 *(n for v in spike.versions for n, _ in v.legacy)}
        if spike_name not in names:
            raise ValueError(f"Spike {spike_name!r} disagrees with registry key {spike_key}.")
        return to_legacy_frame(selected)
    try:
        registry = get_registry()
    except (OSError, ValueError, TypeError, KeyError) as error:
        warnings.warn(f"Cannot read spike registry; falling back to bundled CSVs: {error}",
                      RuntimeWarning, stacklevel=2)
    else:
        if spike_name in registry.names:
            return to_legacy_frame(registry.resolve(spike_name, version))
    if version is None:
        version = "v3" if spike_name == "ET2535" else "v1"
    try:
        filename = SPIKES[spike_name][version]
    except KeyError:
        raise ValueError(f"Unknown spike/version: {spike_name} {version}")

    path = files(spike_compositions) / filename
    with path.open("rb") as stream:
        return pd.read_csv(stream, index_col=0)

def assign_spike_to_sample(UPb_grain):
    '''
    Assign spike data to a UPb_grain object based on its spike_name attribute.
    '''
    spike_name = UPb_grain.spike_name
    spike_weight = UPb_grain.spike_weight
    spike_data = load_spike_data(spike_name, UPb_grain.spike_version, UPb_grain.spike_key)
    spike_data = spike_data.loc[["value", "uncertainty"]].apply(pd.to_numeric, errors="coerce")
    version = UPb_grain.spike_version or ("v3" if spike_name == "ET2535" else "v1")
    label = UPb_grain.spike_key or f"{spike_name} {version}"
    spike_data, UPb_grain.tracer_derivations = complete_tracer(
        spike_data, label, key=UPb_grain.spike_key)
    spike_data = spike_data.reindex(columns=list(dict.fromkeys(
        [*spike_data.columns, "202Pb/205Pb", "238U/233U"])))

    UPb_grain.Pb205t = spike_data.loc['value', 'Pb205'] * spike_weight
    UPb_grain.U235t = spike_data.loc['value', 'U235'] * spike_weight
    UPb_grain.Pb_R25t = spike_data.loc['value', '202Pb/205Pb']
    UPb_grain.Pb_R25t_std = spike_data.loc['value', '202Pb/205Pb'] * spike_data.loc['uncertainty', '202Pb/205Pb'] / 100
    UPb_grain.Pb_R65t = spike_data.loc['value', '206Pb/205Pb']
    UPb_grain.Pb_R65t_std = spike_data.loc['value', '206Pb/205Pb'] * spike_data.loc['uncertainty', '206Pb/205Pb'] / 100
    UPb_grain.Pb_R75t = spike_data.loc['value', '207Pb/205Pb']
    UPb_grain.Pb_R75t_std = spike_data.loc['value', '207Pb/205Pb'] * spike_data.loc['uncertainty', '207Pb/205Pb'] / 100
    UPb_grain.Pb_R45t = spike_data.loc['value', '204Pb/205Pb']
    UPb_grain.Pb_R45t_std = spike_data.loc['value', '204Pb/205Pb'] * spike_data.loc['uncertainty', '204Pb/205Pb'] / 100
    UPb_grain.Pb_R85t = spike_data.loc['value', '208Pb/205Pb']
    UPb_grain.Pb_R85t_std = spike_data.loc['value', '208Pb/205Pb'] * spike_data.loc['uncertainty', '208Pb/205Pb'] / 100
    UPb_grain.Pb_R84t = UPb_grain.Pb_R85t / UPb_grain.Pb_R45t
    UPb_grain.Pb_R84t_std = np.sqrt((UPb_grain.Pb_R85t_std / UPb_grain.Pb_R45t)**2 + (UPb_grain.Pb_R85t / UPb_grain.Pb_R45t**2 * UPb_grain.Pb_R45t_std)**2 )
    UPb_grain.Pb_R76t = spike_data.loc['value', '207Pb/206Pb']
    UPb_grain.Pb_R76t_std = spike_data.loc['value', '207Pb/206Pb'] * spike_data.loc['uncertainty', '207Pb/206Pb'] / 100
    UPb_grain.Pb_R46t = spike_data.loc['value', '204Pb/206Pb']
    UPb_grain.Pb_R46t_std = spike_data.loc['value', '204Pb/206Pb'] * spike_data.loc['uncertainty', '204Pb/206Pb'] / 100
    UPb_grain.U_R85t = spike_data.loc['value', '238U/235U']
    UPb_grain.U_R85t_std = spike_data.loc['value', '238U/235U'] * spike_data.loc['uncertainty', '238U/235U'] / 100
    UPb_grain.U_R35t = spike_data.loc['value', '233U/235U']
    UPb_grain.U_R35t_std = spike_data.loc['value', '233U/235U'] * spike_data.loc['uncertainty', '233U/235U'] / 100
    UPb_grain.U_R83t = spike_data.loc['value', '238U/233U']
    UPb_grain.U_R83t_std = spike_data.loc['value', '238U/233U'] * spike_data.loc['uncertainty', '238U/233U'] / 100

def assign_fractionation_factors(UPb_grain, fractionation_factors):
    '''
    Assign fractionation factors to a UPb_grain object based on its collector attribute.
    '''
    spike_type = UPb_grain.spike_type
    collector = UPb_grain.collector
    if spike_type == 535:
        # 535 spike needs a given Pb fractionation factor
        if collector == 'F':
            UPb_grain.FPb = fractionation_factors['FPb_Faraday'] / 100
            UPb_grain.FPb_std = fractionation_factors['FPb_Faraday_std'] / 100
        elif collector == 'D':
            UPb_grain.FPb = fractionation_factors['FPb_Daly'] / 100
            UPb_grain.FPb_std = fractionation_factors['FPb_Daly_std'] / 100
        else:
            raise ValueError(f"Unknown collector type: {collector}")
    elif spike_type == 2535:
        # 202Pb-205Pb double spike: FPb comes from measured and tracer 202/205,
        # not from fractionation_factors (assign_Pb_R25m must run first).
        UPb_grain.calc_FPb_2535()
    else:
        return 
    
def assign_lab_blanks(UPb_grain, lab_blanks):
    UPb_grain.Pb_blank_total = lab_blanks['Pb_blank_total']
    UPb_grain.Pb_blank_total_std = lab_blanks['Pb_blank_total'] * lab_blanks['Pb_blank_total_std_rel'] / 100
    UPb_grain.U_blank_total = lab_blanks['U_blank_total']
    UPb_grain.U_blank_total_std = lab_blanks['U_blank_total'] * lab_blanks['U_blank_total_std_rel'] / 100

    UPb_grain.R64b = lab_blanks['R64b']
    UPb_grain.R64b_std = lab_blanks['R64b'] * lab_blanks['R64b_std_rel'] / 100
    # UPb_grain.R46b = 1 / UPb_grain.R64b
    # UPb_grain.R46b_std = lab_blanks['R64b_std_rel'] * UPb_grain.R46b / 100
    UPb_grain.R74b = lab_blanks['R74b']
    UPb_grain.R74b_std = lab_blanks['R74b'] * lab_blanks['R74b_std_rel'] / 100
    UPb_grain.R76b = UPb_grain.R74b / UPb_grain.R64b
    UPb_grain.R76b_std = np.sqrt(lab_blanks['R74b_std_rel']**2 + lab_blanks['R64b_std_rel']**2 - 2 * lab_blanks['R74b_std_rel'] * lab_blanks['R64b_std_rel'] * lab_blanks['rho_6474_b']) * UPb_grain.R76b / 100
    UPb_grain.R84b = lab_blanks['R84b']
    UPb_grain.R84b_std = lab_blanks['R84b'] * lab_blanks['R84b_std_rel'] / 100
    UPb_grain.R86b = lab_blanks['R84b'] / lab_blanks['R64b']
    UPb_grain.R86b_std = np.sqrt(lab_blanks['R84b_std_rel']**2 + lab_blanks['R64b_std_rel']**2 - 2 * lab_blanks['R84b_std_rel'] * lab_blanks['R64b_std_rel'] * lab_blanks['rho_6484_b']) * UPb_grain.R86b / 100
    UPb_grain.rho_6474_b = lab_blanks['rho_6474_b']
    UPb_grain.rho_6484_b = lab_blanks['rho_6484_b']

def assign_initial_Pb_composition(UPb_grain, Pbc):
    UPb_grain.R64c = Pbc['R64c']
    UPb_grain.R64c_std = Pbc['R64c'] * Pbc['R64c_std_rel'] / 100
    UPb_grain.R74c = Pbc['R74c']
    UPb_grain.R74c_std = Pbc['R74c'] * Pbc['R74c_std_rel'] / 100
    UPb_grain.R76c = Pbc['R74c'] / Pbc['R64c']
    UPb_grain.R76c_std = np.sqrt(Pbc['R74c_std_rel']**2 + Pbc['R64c_std_rel']**2 - 2 * Pbc['R74c_std_rel'] * Pbc['R64c_std_rel'] * Pbc['rho_6474_c']) * UPb_grain.R76c / 100
    UPb_grain.R84c = Pbc['R84c']
    UPb_grain.R84c_std = Pbc['R84c'] * Pbc['R84c_std_rel'] / 100
    UPb_grain.rho_6474_c = Pbc['rho_6474_c']
    UPb_grain._initial_Pb_composition = {name: getattr(UPb_grain, name) for name in
        ('R64c', 'R74c', 'R84c', 'R76c', 'R64c_std', 'R74c_std', 'R84c_std', 'R76c_std')}

def assign_Th_corrections(UPb_grain, Th_corrections):
    if Th_corrections is None or Th_corrections.get('Th230_correction_type') is None:
        UPb_grain.Th230_correction_type = None
        return
    UPb_grain.Th230_correction_type = Th_corrections['Th230_correction_type']
    if UPb_grain.Th230_correction_type == "D":
        UPb_grain.D_Th_U = Th_corrections['D_Th_U']
        UPb_grain.D_Th_U_std = Th_corrections['D_Th_U_std']
        UPb_grain.Th_U_magma = Th_corrections.get('Th_U_magma')
        UPb_grain.Th_U_magma_std = Th_corrections.get('Th_U_magma_std', 0.0)
    elif UPb_grain.Th230_correction_type == "magma":
        UPb_grain.Th_U_s = Th_corrections.get('Th_U_s')
        UPb_grain.Th_U_s_std = Th_corrections.get('Th_U_s_std')
        UPb_grain.Th_U_magma = Th_corrections['Th_U_magma']
        UPb_grain.Th_U_magma_std = Th_corrections['Th_U_magma_std']
    else:
        raise ValueError(f"Unknown Th230 correction type: {UPb_grain.Th230_correction_type}")

def assign_measurements(UPb_grain, df_row,
                        Pb_R45m = '204Pb/205Pb Mean',
                        Pb_R45m_std_rel = '204Pb/205Pb % Standard Error',
                        Pb_R46m = '204Pb/206Pb Mean',
                        Pb_R46m_std_rel = '204Pb/206Pb % Standard Error',
                        Pb_R64m = '206Pb/204Pb Mean',
                        Pb_R64m_std_rel = '206Pb/204Pb % Standard Error',
                        Pb_R65m = '206Pb/205Pb Mean',
                        Pb_R65m_std_rel = '206Pb/205Pb % Standard Error',
                        Pb_R67m = '206Pb/207Pb Mean',
                        Pb_R67m_std_rel = '206Pb/207Pb % Standard Error',
                        Pb_R75m = '207Pb/205Pb Mean',
                        Pb_R75m_std_rel = '207Pb/205Pb % Standard Error',
                        Pb_R76m = '207Pb/206Pb Mean',
                        Pb_R76m_std_rel = '207Pb/206Pb % Standard Error',
                        Pb_R85m = '208Pb/205Pb Mean',
                        Pb_R85m_std_rel = '208Pb/205Pb % Standard Error',
                        U_R85m = '238U/235U Mean',
                        U_R85m_std_rel = '238U/235U % Standard Error',
                        U_R35m = '233U/235U Mean',
                        U_R35m_std_rel = '233U/235U % Standard Error',
                        U_R83m = '238U/233U Mean',
                        U_R83m_std_rel = '238U/233U % Standard Error'):
    UPb_grain.Pb_R45m = df_row[Pb_R45m]
    UPb_grain.Pb_R45m_std = df_row[Pb_R45m] * df_row[Pb_R45m_std_rel] / 100
    UPb_grain.Pb_R46m = df_row[Pb_R46m]
    UPb_grain.Pb_R46m_std = df_row[Pb_R46m] * df_row[Pb_R46m_std_rel] / 100
    UPb_grain.Pb_R64m = df_row[Pb_R64m]
    UPb_grain.Pb_R64m_std = df_row[Pb_R64m] * df_row[Pb_R64m_std_rel] / 100
    UPb_grain.Pb_R65m = df_row[Pb_R65m]
    UPb_grain.Pb_R65m_std = df_row[Pb_R65m] * df_row[Pb_R65m_std_rel] / 100
    UPb_grain.Pb_R67m = df_row[Pb_R67m]
    UPb_grain.Pb_R67m_std = df_row[Pb_R67m] * df_row[Pb_R67m_std_rel] / 100
    UPb_grain.Pb_R75m = df_row[Pb_R75m]
    UPb_grain.Pb_R75m_std = df_row[Pb_R75m] * df_row[Pb_R75m_std_rel] / 100
    UPb_grain.Pb_R76m = df_row[Pb_R76m]
    UPb_grain.Pb_R76m_std = df_row[Pb_R76m] * df_row[Pb_R76m_std_rel] / 100
    UPb_grain.Pb_R85m = df_row[Pb_R85m]
    UPb_grain.Pb_R85m_std = df_row[Pb_R85m] * df_row[Pb_R85m_std_rel] / 100
    UPb_grain.Pb_R84m = UPb_grain.Pb_R85m / UPb_grain.Pb_R45m
    UPb_grain.Pb_R84m_std = np.sqrt((UPb_grain.Pb_R85m_std / UPb_grain.Pb_R45m)**2 + (UPb_grain.Pb_R85m / UPb_grain.Pb_R45m**2 * UPb_grain.Pb_R45m_std)**2 )
    
    UPb_grain.U_R85m = df_row[U_R85m]
    UPb_grain.U_R85m_std = df_row[U_R85m] * df_row[U_R85m_std_rel] / 100
    UPb_grain.U_R35m = df_row[U_R35m]
    UPb_grain.U_R35m_std = df_row[U_R35m] * df_row[U_R35m_std_rel] / 100
    UPb_grain.U_R83m = df_row[U_R83m]
    UPb_grain.U_R83m_std = df_row[U_R83m] * df_row[U_R83m_std_rel] / 100


def assign_Pb_R25m(UPb_grain, df_row,
                   Pb_R25m='202Pb/205Pb Mean',
                   Pb_R25m_std_rel='202Pb/205Pb % Standard Error'):
    """Measured 202Pb/205Pb and its 1σ for a 2535 fraction; validates the tracer value."""
    for col in (Pb_R25m, Pb_R25m_std_rel):
        if col not in df_row.index:
            raise Missing202Pb205PbError(
                f"Grain {UPb_grain.id}: Spike Type 2535 needs measured 202Pb/205Pb; column '{col}' is missing")
        value = df_row[col]
        if not np.isfinite(value) or (value <= 0 if col == Pb_R25m else value < 0):
            raise Missing202Pb205PbError(
                f"Grain {UPb_grain.id}: Spike Type 2535 needs measured 202Pb/205Pb; invalid value in {col}")
    if UPb_grain.Pb_R25t is None or not np.isfinite(UPb_grain.Pb_R25t) or UPb_grain.Pb_R25t <= 0 \
            or not np.isfinite(UPb_grain.Pb_R25t_std):
        raise Missing202Pb205PbError(
            f"Grain {UPb_grain.id}: tracer {UPb_grain.spike_name} has no 202Pb/205Pb value; "
            "Spike Type 2535 needs a 202Pb-205Pb double spike such as ET2535")
    UPb_grain.Pb_R25m = df_row[Pb_R25m]
    UPb_grain.Pb_R25m_std = df_row[Pb_R25m] * df_row[Pb_R25m_std_rel] / 100


def load_grains(data, 
                fractionation_factors,
                lab_blanks,
                Pbc,
                Th_corrections,
                id='Grain ID',
                sample_weight = 'Sample Weight (mg)',
                spike_weight = 'Spike Weight (g)',
                spike_type='Spike Type',
                spike_name = 'Spike',
                collector = 'Collector',
                Pb_R45m = '204Pb/205Pb Mean',
                Pb_R45m_std_rel = '204Pb/205Pb % Standard Error',
                Pb_R46m = '204Pb/206Pb Mean',
                Pb_R46m_std_rel = '204Pb/206Pb % Standard Error',
                Pb_R64m = '206Pb/204Pb Mean',
                Pb_R64m_std_rel = '206Pb/204Pb % Standard Error',
                Pb_R65m = '206Pb/205Pb Mean',
                Pb_R65m_std_rel = '206Pb/205Pb % Standard Error',
                Pb_R67m = '206Pb/207Pb Mean',
                Pb_R67m_std_rel = '206Pb/207Pb % Standard Error',
                Pb_R75m = '207Pb/205Pb Mean',
                Pb_R75m_std_rel = '207Pb/205Pb % Standard Error',
                Pb_R76m = '207Pb/206Pb Mean',
                Pb_R76m_std_rel = '207Pb/206Pb % Standard Error',
                Pb_R85m = '208Pb/205Pb Mean',
                Pb_R85m_std_rel = '208Pb/205Pb % Standard Error',
                U_R85m = '238U/235U Mean',
                U_R85m_std_rel = '238U/235U % Standard Error',
                U_R35m = '233U/235U Mean',
                U_R35m_std_rel = '233U/235U % Standard Error',
                U_R83m = '238U/233U Mean',
                U_R83m_std_rel = '238U/233U % Standard Error',
                verbose=False,
                spike_version=None,
                covariance_overrides=None,
                strict_covariance=True,
                Pb_R25m='202Pb/205Pb Mean',
                Pb_R25m_std_rel='202Pb/205Pb % Standard Error',
                spike_key=None,
                spike_from=None):
    """Reduce 535- and 2535-spiked fractions without modifying the input DataFrame.

    Spike Type 535 rows use the per-collector FPb in `fractionation_factors`.
    Spike Type 2535 (202Pb-205Pb-233U-235U, e.g. ET2535) rows instead compute
    FPb = (1 - R25t/R25m)/3 per amu from the measured `Pb_R25m` column and the
    tracer 202/205, and need no fractionation_factors entries; a missing or
    invalid measured 202/205 raises Missing202Pb205PbError (a ValueError).
    Missing tracer values or uncertainties raise TracerCompositionError.
    535 rows ignore the 202/205 columns. FPb's covariance with other inputs is zero
    unless given in covariance_overrides (see grain.uncertainty_assumptions).

    Relative measurement and blank errors are 1σ percentages. Grain dates are
    Ma and their `_std` values are 1σ. Impossible input covariance is rejected
    unless explicit diagnostic approximation mode is selected. Missing joint
    covariances and calibration uncertainty limits are documented in README.
    Linked measurement-error correlations are checked before each reduction;
    see grain.data_quality_checks or check_measurement_quality(data).

    Database proposals are ignored by default. Explicitly opt in with
    ``spike_from='Spike Solution'`` to read an exact registry key per row, or
    pass ``spike_key='ET535/master/v3'`` for all rows. Filled keys override
    ``spike_version`` and never fall back; empty cells retain legacy behavior.
    Notebook callers are responsible for confirming their chosen tracer.
    """
    data = data.copy(deep=True)
    if spike_key is not None and spike_from is not None:
        raise ValueError("Choose spike_key or spike_from, not both.")
    grains = []
    for label, params in [('fractionation', fractionation_factors or {}), ('blanks', lab_blanks), ('common Pb', Pbc), ('Th correction', Th_corrections or {})]:
        for key, value in params.items():
            if isinstance(value, str) or value is None:
                continue
            if not np.isfinite(value):
                raise ValueError(f"{label}: {key} must be finite")
            if ('std' in key or 'blank_total' in key) and value < 0:
                raise ValueError(f"{label}: {key} must be nonnegative")
            if key.startswith('rho') and abs(value) > 1:
                raise ValueError(f"{label}: {key} must lie between -1 and 1")
            if key.startswith(('R64', 'R74', 'R84')) and 'std' not in key and value <= 0:
                raise ValueError(f"{label}: {key} must be positive")
    if data[id].duplicated().any() or data[id].isna().any():
        raise ValueError("Grain IDs must be present and unique")
    # because we typically get Pb64 values from Tripoli, let's calculate here the corresponding R46 values and their uncertainties
    if Pb_R46m not in data.columns:
        data[Pb_R46m] = 1 / data[Pb_R64m]
        data[Pb_R46m_std_rel] = data[Pb_R64m_std_rel]

    if Pb_R76m not in data.columns:
        data[Pb_R76m] = 1 / data[Pb_R67m]
        data[Pb_R76m_std_rel] = data[Pb_R67m_std_rel]

    for _, row in data.iterrows():
        if int(row[spike_type]) not in (535, 2535):
            raise NotImplementedError("Raw reduction currently supports 535 and 2535 tracers only")
        numeric_cols = [sample_weight, spike_weight, Pb_R45m, Pb_R46m, Pb_R64m,
                        Pb_R65m, Pb_R67m, Pb_R75m, Pb_R76m, Pb_R85m,
                        U_R85m, U_R35m, U_R83m]
        error_cols = [Pb_R45m_std_rel, Pb_R46m_std_rel, Pb_R64m_std_rel,
                      Pb_R65m_std_rel, Pb_R67m_std_rel, Pb_R75m_std_rel,
                      Pb_R76m_std_rel, Pb_R85m_std_rel, U_R85m_std_rel,
                      U_R35m_std_rel, U_R83m_std_rel]
        for col in numeric_cols + error_cols:
            if not np.isfinite(row[col]) or (row[col] <= 0 if col in numeric_cols else row[col] < 0):
                raise ValueError(f"Grain {row[id]}: invalid value in {col}")
        key = row[spike_from] if spike_from is not None else spike_key
        key = None if key is None or pd.isna(key) or key == "" else key
        grain = UPb_grain(
            id = row[id],
            sample_weight = row[sample_weight],
            spike_weight = row[spike_weight],
            spike_type = row[spike_type],
            spike_name = row[spike_name],
            collector = row[collector],
            spike_version = key.rsplit("/", 1)[-1] if key else spike_version
        )
        grain.spike_key = key
        assign_spike_to_sample(grain)
        grain.covariance_overrides = covariance_overrides or {}
        grain.strict_covariance = strict_covariance
        if verbose:
            print(f"Assigned spike data for grain {grain.id} with spike {grain.spike_name}")
        if grain.spike_type == 2535:
            assign_Pb_R25m(grain, row, Pb_R25m, Pb_R25m_std_rel)
        assign_fractionation_factors(grain, fractionation_factors)
        if verbose:
            print(f"Assigned fractionation factors for grain {grain.id} collected on {grain.collector}")
        assign_lab_blanks(grain, lab_blanks)
        if verbose:
            print(f"Assigned lab blanks for grain {grain.id}")
        assign_initial_Pb_composition(grain, Pbc)
        if verbose:
            print(f"Assigned initial Pb composition for grain {grain.id}")
        assign_Th_corrections(grain, Th_corrections)
        if verbose:
            print(f"Assigned Th corrections for grain {grain.id} using {grain.Th230_correction_type} method")
        assign_measurements(grain, row,
                            Pb_R45m,
                            Pb_R45m_std_rel,
                            Pb_R46m,
                            Pb_R46m_std_rel,
                            Pb_R64m,
                            Pb_R64m_std_rel,
                            Pb_R65m,
                            Pb_R65m_std_rel,
                            Pb_R67m,
                            Pb_R67m_std_rel,
                            Pb_R75m,
                            Pb_R75m_std_rel,
                            Pb_R76m,
                            Pb_R76m_std_rel,
                            Pb_R85m,
                            Pb_R85m_std_rel,
                            U_R85m,
                            U_R85m_std_rel,
                            U_R35m,
                            U_R35m_std_rel,
                            U_R83m,
                            U_R83m_std_rel)
        if verbose:
            print(f"Assigned measurements for grain {grain.id}")
        grain.calc_all()
        if verbose:
            print(f"Calculated all parameters for grain {grain.id}")
        grains.append(grain)
    return grains
