# Versioned spike registry

Public EARTHTIME master compositions live in `upb-standards/spikes/`.
The bundled **private** overlay lives in `src/IDTIMS_UPbRPy/spike_registry/`.
Both use format 1. BSU-1, MIT-1L, laboratory bottles and unpublished
calibrations stay here because the public repository accepts only values
verified in a published EARTHTIME table. No complete legacy CSV calibration
matches Condon et al. (2015) Table 3, p. 474; sharing its tracer name does
not establish that a calibration is the published master composition.

`spike_registry.py` defines typed spikes, sub-fractions, versions and
measurements. `load_registry(public=None, overlays=None)` discovers a public
registry, always merges the bundled private overlay, then adds optional
extra overlays. Pass `public=False` for an explicitly private-only load.
Discovery checks `$UPB_SPIKES_DIR`, `$UPB_STANDARDS_DIR/spikes`,
`~/UPbRPy/upb-standards/spikes`, then `~/Github/upb-standards/spikes`.
Missing public data is normal: all six legacy calibrations are bundled.
A malformed or unreadable registry makes `load_spike_data` warn and fall
back to the existing CSVs. An unresolved name also uses the CSV fallback.

`registry.resolve(name, version=None, subfraction=None)` and module-level
`resolve(...)` accept IDs, aliases and legacy keys. `ET535` without a version
still selects legacy v1; `ET2535` selects legacy v3. `BSU1B/v1` maps to
`BSU-1/B/v1`, and `MIT1L/v1` to `MIT-1L/unassigned/v1`. Use the registry API
to select a physical sub-fraction explicitly, for example:

```python
from IDTIMS_UPbRPy.spike_registry import load_registry, to_legacy_frame
registry = load_registry()
published = registry.resolve("ET2535", "v3", subfraction="master")
legacy = registry.resolve("ET2535", "v3")
frame = to_legacy_frame(legacy)
```

`to_legacy_frame` preserves the old CSV index name `species`, rows `unit`,
`value`, `uncertainty`, column order, strings and missing cells for all
legacy mappings. It preserves TOML numeric token spellings for pandas
conversion, avoiding changes from floating-point round trips. Unknown
uncertainty remains NaN. For public source values, the compatibility view
converts absolute/two-sigma uncertainty to relative one-sigma percent;
the registry itself retains the source convention and never derives missing
ratios. The engine completes the required quotients separately, as described below.

The standalone checker logic is vendored in `_spike_registry_check.py`,
with only a `tomli` fallback for Python 3.10. Package data and the desktop
bundle include the private overlay. The data directory has no `__init__.py`
and is excluded from namespace discovery to avoid masking the Python module.

```sh
python ../upb-standards/spikes/check.py --overlay src/IDTIMS_UPbRPy/spike_registry
python -m IDTIMS_UPbRPy._spike_registry_check --overlay-only --overlay src/IDTIMS_UPbRPy/spike_registry
```

To add a calibration, append a new version under its actual sub-fraction,
record the source and locator, and append its lock entry with `--update-lock`.
Never edit an old version's measurements. Only top-level `status` and `notes`
are excluded from the canonical version hash. The public registry README
defines the exact canonical JSON. The checker rejects version redefinition
across any two layers, changed hashes, deleted locked versions, invalid
sources, aliases or references, and supersession cycles. An overlay may
extend a public sub-fraction and refer to its previous public version with
`supersedes`. Keep locks under the same visibility as their values.

## Published compositions without cross-ratios

Condon et al. (2015) Table 3 prints only x/205 ratios. The reduction also
needs tracer 207Pb/206Pb and 204Pb/206Pb, and uses 238U/233U for one
covariance. `tracer.complete_tracer` fills an absent cross-ratio at the
reduction boundary, in this order:

1. A ratio the registry version lists is used as it is, never replaced.
2. Otherwise, if `spike_registry/cross_ratios.toml` (private, bundled) has an
   entry for that exact registry key, its value and 1σ are used.
3. Otherwise the ratio is derived as a quotient, for example
   207Pb/206Pb = (207Pb/205Pb)/(206Pb/205Pb), with 1σ the quadrature sum of
   the two relative errors (zero covariance).

The registry view stays unchanged. Each filled ratio is recorded in the
grain's `uncertainty_assumptions` and marked in the Tracer step as
"(BSU sheet)" or "(derived)". A missing required value or uncertainty
blocks reduction and database-spike confirmation; nothing is invented.
Concentrations need finite values only, because propagation treats them as
fixed. 238U/233U is optional.

**Decision (Yiming, 2026-11-20).** ET535/master/v3 takes 207/206 and 204/206
from the BSU sheet table "ET535 v2.1, McLean 2012". 238U/233U is still
derived. ET2535/master/v3 still derives all three: the sheets' "McLean ET2535"
table does not match the public record (206/205 0.000927 against 0.00048;
204/205 0.00013 against 0.000105).

Why: that sheet table (UPbR21/22/24XML, Raw Data Input AL94:AN108, the same
in all seven Adirondack workbooks) matches Table 3's ET535 Pb impurity and
U ratios and their 1σ to the printed digits. It also lists
207Pb/206Pb = 0.761593363043767 ± 7.048716571 % and
204Pb/206Pb = 0.23153930860262267 ± 33.749377052 % (1σ). Deriving with zero
covariance gives 0.7712 ± 63.9 % and 0.2314 ± 44.8 %. The tabulated errors
are far below the quadrature sums (64.3 % and 44.6 %), so the impurity ratios
are strongly positively correlated. Zero covariance overstated the 207/206
error about nine times. The lab record ET535/unassigned/v2 is the same table,
transcribed separately as CSV; a test checks that the two agree.

**Correlated tracer errors are not propagated as McLean et al. (2011) do.**
McLean's algorithm, used in ET_Redux, carries the full covariance matrix of
the tracer calibration into the dates. This engine does not. Each tracer ratio
enters with its own 1σ. Covariances between tracer ratios come only from the
three-ratio identities (for example 207/205 = 207/206 × 206/205); other pairs
are completed by conditional independence. Tracer concentrations are treated
as fixed (see `uncertainty.py`). The tabulated 207/206 and 204/206 errors carry
the impurity correlation into those quotients, but they do not stand in for
the full McLean covariance. Every reduced grain records this in
`uncertainty_assumptions`.

Synthetic reductions are covered by the fixed-seed fixtures and snapshots in
`tests/data/synthetic_*`; no measured sample comparison is distributed.

Other findings from the sheet check (Raw Data Input AK79:AN140, read
2026-11-20). The seven workbooks hold the same ratio values; only the
235U/205Pb errors and one label differ in the UPbR24 sheets. The "BSU 2014
ET535" v3.1 table is labelled "McLean 205/235, 233/235; BSU minor isotopes".
It carries 7.05–47.4 % errors on the Pb impurity ratios, the same as v2.1.
The lab record ET535/unassigned/v3 (the active v3.1 block, AK79:AN92)
pairs the BSU 2014 values with impurity errors of 0.066–0.161 %. Those equal
the Condon 2007 "ET535 v1.1" table exactly, so they probably came from the
older calibration. The lab v1 CSV gives 233U/235U ± 0.05 %; the sheet's v1.1
table gives ± 0.005 %. None of the Adirondack fractions used ET535: all 100
used BSU1B.

## Source inventory and mapping

All CSV numeric tokens, including uncertainties, are retained verbatim.
Every registry version from a sheet preserves the exact binary cached cell
number via a round-tripping decimal representation. A sheet snapshot is
stored separately from its CSV transcription because their last digits and
some uncertainty precision differ. The snapshot label identifies evidence,
not a newly inferred calibration date or a known chronological successor.
Both are retained as current evidence; choose an explicit snapshot version
when needed. No sheet snapshot has a legacy mapping, so defaults are stable.

| Source | Fractions | Registry key | Reason private |
| --- | --- | --- | --- |
| `spike_compositions/BSU1B_v1.csv` | No fraction assignments in CSV | `BSU-1/B/v1` | Laboratory solution; B is given by the legacy key |
| `spike_compositions/MIT1L_v1.csv` | No fraction assignments in CSV | `MIT-1L/unassigned/v1` | Laboratory solution; bottle unknown |
| `spike_compositions/ET535_v1.csv` | No fraction assignments in CSV | `ET535/unassigned/v1` | Composition differs from published Table 3 |
| `spike_compositions/ET535_v2.csv` | No fraction assignments in CSV | `ET535/unassigned/v2` | Composition differs; concentrations normalised to near-nominal 1e-9 mol/g 235U |
| `spike_compositions/ET535_v3.csv` | No fraction assignments in CSV | `ET535/unassigned/v3` | Composition differs; concentrations normalised to near-nominal 1e-9 mol/g 235U |
| `spike_compositions/ET2535_v3.csv` | Template transcription; see separate exact snapshot below | `ET2535/unassigned/v3` | Pb impurities and uncertainties differ; nominal 1e-9 mol/g 235U |
| `BSULab_UPbR26XML.xls`, Data Reduction Engine C:H, rows 150–171 | z1–z6 | `ET2535/unassigned/sheet-template` | Exact sheet composition, not the published master |
| `~/lab-settings/tracer-settings.xls`, Data Reduction Engine C:I, rows 150–171 | z1–z7 | `ET535/unassigned/sheet-sa18-1` | Exact sheet composition, not the published master |

### Distinct compositions in the two reduction workbooks

Each column below is shared by all populated fractions in its workbook.
Concentrations have no reported uncertainty in this block. Ratios are shown
as **value; 1-sigma relative percent**. These are source numbers, not
re-derived ratios. Rows 172–173 contain fraction-specific spike amounts
and are intentionally excluded from the solution compositions.

| Quantity (engine row) | Template ET2535, z1–z6 | Private ET535 solution |
| --- | --- | --- |
| 205Pb mol/g (150) | 9.97676368e-12 | 9.97676368e-12 |
| 235U mol/g (151) | 1e-09 | 1.0000000002845095e-09 |
| 202Pb/205Pb (152) | 0.999239128056085; 0.02657 | 0.0; 0.0 |
| 206Pb/205Pb (154) | 0.0007472269302184401; 0.066109034 | 0.0004781575683710043; 0.066109034 |
| 207Pb/205Pb (156) | 0.0006516655868161097; 0.122432517344936 | 0.00034217101037897974; 0.122432517344936 |
| 204Pb/205Pb (158) | 0.00011800557300536978; 0.1423800049782878 | 8.931776571667676e-05; 0.1423800049782878 |
| 208Pb/205Pb (160) | 0.0015686606158324355; 0.1611039883397542 | 0.0008800517104121559; 0.1611039883397542 |
| 207Pb/206Pb (162) | 0.8721120190697697; 0.10305007 | 0.7156030417853555; 0.10305007 |
| 204Pb/206Pb (164) | 0.15792467888017991; 0.12610179 | 0.18679567495076177; 0.12610179 |
| 238U/235U (166) | 0.003087; 0.01284 | 0.00307992839133; 0.0128427704152 |
| 233U/235U (168) | 0.995061797313838; 0.00541036 | 0.995061797313838; 0.0054103655891 |
| 238U/233U (170) | 0.00310363548620606; 0.016635 | 0.003095213181377; 0.0166353765038 |

The exact cell inventory and registry mapping are also stored in
`docs/spike-sheet-compositions.json`. Reproduce the read-only extraction:

```sh
.venv/bin/python tools/audit_spike_compositions.py BSULab_UPbR26XML.xls ~/lab-settings/tracer-settings.xls
```

### MCR evidence

The audit searched all MCR text/CSV/Python and notebook source cells,
extracted the PDFs and DOCX text, inspected the three source-table PNGs, and opened `MCR_data/Zhang2021.xls`
read-only with xlrd. No full tracer composition block was found there.

- `Zhang2021.xls`, `IDTIMS-radiogenic` row 25, identifies ET535 and cites
  Condon et al. (2015). It does not identify a bottle or version.
- `convert_to_csv.py` identifies ET535 for the Swanson-Hysell2021 and
  Zhang2021 tables. Its Smith2025 BNB-19-022D comment identifies starred
  Z1*, Z2*, Z3* as EARTHTIME 205Pb–233U–235U tracer and mentions a JSGL/ROM
  tracer for other analyses; it supplies no tracer compositions. The footnote
  in `Smith2025.png` confirms that the three starred fractions use EARTHTIME
  205Pb–233U–235U and all other rows use JSGL/ROM 205Pb–235U.
- `MGS2026.pdf` table footnotes identify ET535 U double-spike measurements,
  contemporaneous ET2535 Pb analyses, and an ET2535 tracer table. They
  give no tracer-composition calibration. These statements cannot assign
  every individual fraction to a version.
- `Swanson-Hysell2019.pdf` and `Fairchild2017.docx` mention spike correction
  or Pb double-spike use without a complete named composition.
- No additional tracer calibration was found in the MCR notebook source
  cells, generated figures or CSV tables. Corrections and common-Pb/blank
  compositions are not tracer compositions.

These name-only mentions remain unresolved evidence, not new versions.
Do not map a fraction to a calibration simply because its tracer is called
ET535 or ET2535.

## Open provenance questions

Which physical bottles/batches were used for the private ET535 and ET2535
records, and for MIT-1L? Are the CSV v1/v2/v3 records successive calibrations
of one bottle or different bottles? `unassigned` preserves this uncertainty.
CSV ET535 `supersedes` links follow the archive version sequence within the
unassigned placeholder; they do not establish bottle identity. No calibration
dates are inferred. The sheet snapshots do not assert supersession.

The CSV 206Pb/205Pb values (ET535 v1/v2/v3: 0.00029893852896,
0.00038870289689973, 0.000478157568371004; ET2535 v3:
0.00074722693021844) do not equal Table 3's 0.000389 and 0.00048.
The extra-digit U ratios, Pb impurity ratios and normalised concentrations
are not verified by that printed table. Whether they reflect bottle blanks,
a separate calibration or another source needs documentary evidence. BSU-1
and MIT-1L have no publication evidence in the supplied inputs. MCR
name-only mentions, including JSGL/ROM, need source calibration records
before they can be assigned a version or registered with a composition.
