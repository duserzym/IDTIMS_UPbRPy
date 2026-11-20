# IDTIMS_UPbRPy

Isotope dilution–thermal ionization mass spectrometry U–Pb data reduction in
Python. Installable with Python 3.10 or newer:

```sh
python -m pip install .
# Development and local legacy spreadsheet audits:
python -m pip install -e '.[test]'
python -m unittest discover -s tests -v
python -m build
```

## Desktop build

Install the GUI and build dependencies, then build and smoke-test the macOS app
with the lab signing identity installed in your keychain:

```sh
.venv/bin/python -m pip install -e '.[gui,build]'
APPLE_SIGNING_IDENTITY="UPb Lab Code Signing" .venv/bin/python scripts/build_desktop.py --smoke-test
```

The build signs and verifies the app before the smoke test and prints the signing
identity. With `APPLE_SIGNING_IDENTITY` unset or set to `-`, PyInstaller's existing
ad hoc signing is retained. `--no-build` tests the existing bundle without signing
it again. Build outputs go to the platform cache directory outside this checkout.

## Derivation website

Open [docs/index.html](docs/index.html) in a browser, or serve it locally:

```sh
python3 -m http.server 8877 --bind 127.0.0.1 --directory docs
```

Visit `http://127.0.0.1:8877`. The static site includes its math renderer and
fonts, works offline, and uses a white, teal, and copper neumorphic design.
The walkthrough follows Schmitz & Schoene (2007), retaining its section
progression, named isotope quantities, and equation references. It derives sample
amounts, sample ratios and correlations, radiogenic quantities and ratios, then
model ages. Repository extensions and Th correction follow in appendices. Source excerpts and explicit paper corrections are
included; the supplied reference PDF is not redistributed.

Refresh the source snapshots after reduction-code changes and check the
analytical derivatives:

```sh
python3 tools/build_derivation_sources.py
python3 tools/verify_derivation.py
```

Source links use the repository revision captured by the generator. Embedded
excerpts remain available offline. To host with GitHub Pages after committing
and pushing, choose **Deploy from a branch**, select the desired branch and
its `/docs` directory in the repository's Pages settings. No build step is
needed. The website documents the current model's uncertainty limitations;
it does not change the Python reduction algorithm.

## Dates from reduced isotope ratios

```python
from IDTIMS_UPbRPy import utils

age68_ma = utils.calc_t68(0.105)
age76_ma = utils.calc_t76(0.061)
sigma76_ma = utils.calc_t76_uncertainty(age76_ma, 0.000025)
```

All age functions take/return **Ma**, including `calc_t76_uncertainty`.
Decay constants are in inverse years. A ratio uncertainty passed to a date
function remains at its supplied sigma level: a 2σ ratio error produces a 2σ
date error. Grain `_std` attributes are **1σ** absolute uncertainties.
Pb–Pb inversion uses a bracketed root over 0–4600 Ma and rejects ratios without
a root. The historical `x0` argument is accepted for compatibility and ignored.

**Migration:** older notebooks used `calc_t76_uncertainty(age * 1e6, ...)/1e6`.
Replace that expression with `calc_t76_uncertainty(age, ...)`. The previous
derivative was also incorrect, so old Pb–Pb uncertainties must be recalculated.

## Synthetic examples and test fixtures

All distributed fraction measurements and frozen reduction outputs are synthetic.
Rebuild them with `.venv/bin/python tools/generate_synthetic_fixtures.py` (fixed
seed `20261120`). The generator reads only package tracer constants and lab
settings. It writes the example, complementary Pb/U hand-offs, offline database
metadata, ET2535 inputs (including oxide metadata), and numeric snapshots.
Sample identities are invented. Lab settings and tracer calibrations are retained.

The ET2535 fixture uses an invented narrow concordant age cluster and gives
z1/z6 impossible linked errors, while z2–z5 pass strict reduction. The 535
fixture exercises both collectors and the
legacy tracer's diagnostic covariance substitutions. Frozen expected values are
regenerated with the package; tests retain their original numeric tolerances.
Historical documentation screenshots are retained as visual references.

## Reduction from measurements

```python
from IDTIMS_UPbRPy import load_grains

grains = load_grains(data, fractionation_factors, lab_blanks, Pbc,
                     Th_corrections, spike_version="v3")
```

`data` is a pandas DataFrame with the columns demonstrated in
`examples/synthetic_zircon_CA-ID-TIMS.csv`. Sample weight is in mg; spike weight is
in g; blank amounts are in pg; measured errors are 1σ relative percentages;
Pb fractionation inputs are percent per amu. The loader derives reciprocal
Pb ratios when absent and does not modify the supplied DataFrame. Grain IDs
must be unique. `Th_corrections=None` disables Th correction.

The configuration dictionaries and units are demonstrated in
`tests/test_reduction.py`. Supported raw reduction uses **535** and **2535**
tracers and Faraday (`F`) or Daly (`D`) Pb measurements. Other spike types
raise `NotImplementedError`. ET535 defaults to v1; request v2 or v3
explicitly. ET2535's available table is v3 (its default). Tracer tables ship
in the wheel. In a mixed 535 and 2535 frame leave `spike_version=None`, since
no single version exists for every tracer.

### Notebook use of database-linked CSVs

The optional database link and chemistry columns in `idtims-fractions/1` are
offline copies. Reading them does not select a tracer or change existing notebook
results. To use the database's exact spike/subfraction/version, inspect and confirm
the proposal yourself, then opt in explicitly:

```python
from IDTIMS_UPbRPy.fractions import read_fractions

fractions = read_fractions("fractions.csv")
data, columns = fractions.load_grains_frame()
grains = load_grains(data, fractionation_factors, lab_blanks, Pbc,
                     Th_corrections, **columns, spike_from="Spike Solution")
```

A filled key such as `ET535/master/v3` overrides `spike_version` for that row;
empty cells keep the existing name/version behavior. Missing exact keys and
disagreeing spike names raise an error, without fallback. `spike_key=...` selects
one exact key for the whole call instead. `spike_registry.get_registry().by_key(key)`
inspects the exact local registry entry. No database connection or credentials are
used. The desktop app preselects each proposal and requires confirmation in Tracer.

For **2535** (202Pb-205Pb-233U-235U, e.g. ET2535) rows the Pb fractionation
factor is not taken from `fractionation_factors`. It is computed per fraction
from the measured `202Pb/205Pb Mean` and `% Standard Error` columns (renamed
through `Pb_R25m` and `Pb_R25m_std_rel`) and the tracer 202/205, using the
linear law over 3 amu: `FPb = (1 - R25t/R25m)/3`, as the BSU sheet does. Its
1σ treats measured and tracer 202/205 as independent. Everything downstream
matches 535. FPb's covariance with the other measured x/205 ratios and tracer
ratios is taken as zero unless you supply it through `covariance_overrides`
(keyed on `"FPb"`). This assumption is recorded in
`grain.uncertainty_assumptions`. A 2535 row without a valid 202/205, or with a
tracer that has none, raises `UPbR.Missing202Pb205PbError` (a `ValueError`).
535 rows ignore the 202/205 columns.

## Uncertainty model and validation limits

Measurement quality checks run automatically before each grain reduction.
They infer correlations from the linked errors in:

- 207/205 = (206/205)*(207/206)
- 204/205 = (206/205)*(204/206)
- 238/233 = (238/235)/(233/235)

Inferred correlations outside −1 to +1, allowing a 1e-6 rounding tolerance,
raise `DataQualityError` with the grain, ratio identity, supplied errors and
allowed error interval. This happens before tracer covariance propagation.
Checks rerun on `grain.calc_all()`. Results are retained as
`grain.data_quality_checks` and `grain.data_quality_passed`. Covariance
overrides do not suppress a failure in the original measurement errors.
Explicit `strict_covariance=False` permits diagnostic reduction with warnings;
the original errors and failed quality checks remain intact.

Check every grain before attempting reduction, without loading a tracer:

```python
from IDTIMS_UPbRPy import check_measurement_quality

quality = check_measurement_quality(data)
print(quality.loc[~quality["passed"],
                  ["grain", "identity", "implied_correlation",
                   "x_error_pct", "x_error_lower_pct", "x_error_upper_pct"]])
```

This uses the standard CSV error columns. Custom names are supported with
`columns={"id": "fraction", "Pb_R65m_std_rel": "custom65_error"}`.
Reciprocal Pb ratios retain the same relative errors to first order. When an
input error is zero, the correlation is undefined; its variance identity is
still checked. This first-order check assumes a common sigma level and
consistent accepted blocks/cycles and weighting. A failure can flag inconsistent
Tripoli filtering or exported errors; it does not identify a unique cause.
A passing result does not prove all filtering or reduction steps are correct.

Radiogenic isotope amounts, ratios and dates use joint first-order propagation
`J Σ Jᵀ`, retaining shared Pb variables and uranium mass fractionation
dependence. Th correction is propagated through Pb and U jointly. The model
uses a linear fractionation law and the long-time Th disequilibrium correction;
it is not a general young-sample decay-chain solver.

In magma mode, `Th_U_magma` is the atomic Th/U of the melt relative to total U,
as in the BSU sheets. Mineral Th/U inferred from 208Pb* uses
`Th232s / (U238s + U235s)`, with `U235s = U238s / common_U238_U235`, just as
the exported mineral Th/U does. Both the implicit corrected-age solve and its
joint Jacobian use this convention. The natural U ratio is fixed during
propagation. D-mode correction and its derivatives are unchanged.

Input errors that imply impossible covariance or a non-positive-semidefinite
covariance matrix are rejected by default. The supplied BSU1B example tracer
errors contain such an inconsistency. For diagnostic comparisons only,
`strict_covariance=False` substitutes zero for impossible pair covariances,
emits warnings, and records them in `grain.uncertainty_assumptions`. Results
from this mode must not be treated as certified uncertainties.

Missing three-ratio covariances are completed by **conditional independence**,
recorded in `uncertainty_assumptions`; remaining unspecified covariances are
zero. This is a model assumption, not measured Tripoli covariance. Override
known covariances in absolute ratio units with, for example,
`covariance_overrides={("Pb_R46m", "Pb_R76m"): measured_covariance}`.
Input and output covariance matrices and their ordering are available on each
grain. Supply the original measurement covariance to remove these assumptions.

Measured and tracer 208/204 standard deviations use the quotient rule, with
zero 208/205–204/205 covariance assumed when that error is derived. Their
quotient-derived covariances are retained in the joint model. For measured
204/205, represented as (206/205)*(204/206), links to primitive ratios use
conditional independence given 204/205. Known primitive covariances can be
supplied through `covariance_overrides`.

The legacy `calc_Pb207r_uncertainty` helper now accepts keyword-only
`R76c_std`, `R45m`, `R45m_std`, `R46t`, and `R46t_std`; omitted initial-ratio
uncertainty and the corresponding omitted covariances default to zero.
`calc_Pb207s_uncertainty` accepts `R75t` and `R75t_std` to infer tracer
covariance; without them it assumes zero rather than using measured errors.
Use the joint grain reduction for final radiogenic uncertainty propagation.

Tracer concentration, spike weighing, natural U isotope ratio and decay
constant uncertainties are not propagated into grain dates. This is not a
complete analytical/tracer/decay-constant X/Y/Z uncertainty implementation.
Legacy individual `prop_*` helpers remain for compatibility; use `load_grains`
or `grain.calc_all()` for the joint radiogenic propagation. Intermediate
sample/common-Pb ratio helpers have not received the same joint-covariance
validation as radiogenic outputs.

The covariance framework follows [McLean et al. (2011)](https://doi.org/10.1029/2010GC003478).
Model assumptions and omitted calibration inputs must be considered when
comparing with a laboratory spreadsheet.

## Local reference checks

```sh
python tools/verify_mcr.py MCR_data/MCR_all_ages.csv --output outputs/mcr_verification.json
python tools/audit_xls.py /path/to/reference_535.xls --output outputs/reference_535_audit.json
PYTHONPATH=src python tools/audit_xls_2535.py /path/to/BSULab_UPbR26XML.xls --output outputs/bsu2535_audit.json
```

MCR data and generated audit outputs are ignored and excluded from distributions.
Removing the previously tracked MCR files from the Git index preserves their
local copies and does not erase them from existing Git history.

The MCR CSV contains reduced ratios, not raw TIMS measurements. Its six-digit
export supports ratio-to-date checks within rounding intervals, not bitwise
equality or a validation of the full raw reduction. Pb–Pb uncertainties from
the old export are checked separately and expose the old derivative error.

The legacy `.xls` audit reads cached values and BIFF formulas without changing
the workbook. It currently supports the D/t68 correction selection used in
the reference workbook, uses its constants and ET535 v3 calibration, and flags
diagnostic covariance approximations. It does not run native Excel recalculation.

`tools/audit_xls_2535.py` does the same for the BSU template's six ET2535
fractions, using the workbook's settings and constants (including its
lambda230) for the comparison only. Values agree to about 1e-15 relative
(t76 within the sheet's 1.8 ka bisection step; U and Th ppm to within the
sheet's atomic weights). Uncertainties differ because the engine propagates
jointly.

## Fraction files and settings

`IDTIMS_UPbRPy.fractions` reads the `idtims-fractions/1` CSV contract
(`docs/contract-idtims-fractions-v1.md`) and legacy CSVs such as
`examples/synthetic_zircon_CA-ID-TIMS.csv`; `IDTIMS_UPbRPy.settings` keeps every
other reduction input in one JSON round-trippable object.

```python
import json
from IDTIMS_UPbRPy import load_grains
from IDTIMS_UPbRPy.fractions import read_fractions, write_fractions
from IDTIMS_UPbRPy.settings import ReductionSettings

# Pb-only and U-only files merge by Fraction ID; legacy files work too.
table = read_fractions("run_pb.fractions.csv", "run_u.fractions.csv")
for issue in table.issues():          # missing blocks, setup fields, oxide value, ...
    print(issue.message)

settings = ReductionSettings.from_dicts(fractionation_factors, lab_blanks, Pbc,
                                        Th_corrections, strict_covariance=True)
with open("settings.json", "w") as f:
    json.dump(settings.to_dict(), f, indent=2)

args, kwargs = settings.load_grains_arguments()
data, columns = table.load_grains_frame()   # reducible fractions, id='Fraction ID'
grains = load_grains(data, *args, **kwargs, **columns)

# Measured correlations (rho columns) for one fraction, as engine covariances:
overrides = table.covariance_overrides("z1")
write_fractions(table, "edited.fractions.csv")  # contract CSV, full precision
```

Correlations are applied for pairs among 206Pb/205Pb, 208Pb/205Pb,
206Pb/204Pb (or 204Pb/206Pb) and 206Pb/207Pb (or 207Pb/206Pb), and between
238U/235U and 233U/235U. Other pairs, such as 206Pb/205Pb with 207Pb/205Pb,
are listed by `table.issues()` and left to the engine's documented assumption.
`load_grains` takes one `covariance_overrides` dict, so per-fraction overrides
mean one call per fraction.
