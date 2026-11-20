# ID-TIMS reduction app: specification (Phase 0)

Status: draft for review by the coordinating session; no GUI code exists yet.
Branch: `app` (cut from `MCR_data_comparison` at `b7c53d8`). Date: 2026-11-14.

The app turns this repository into the ID-TIMS reduction app of the UPb Lab suite.
It does the job of Schmitz's BSU reduction spreadsheet (`BSULab_UPbR26XML.xls`) and of ET_Redux's
ID-TIMS reduction. The repository stays a notebook library first: the app is an optional layer on
top of the unchanged engine.

The app's name and icon are Yiming's to choose. Until then this document says "the app". In code,
everything that carries the name (display name, bundle id, URL scheme, icon path, settings
organisation, entry-point script) lives in a single module, `idtims_app/branding.py`. The working
placeholder there is `ID-TIMS Reduction (working name)`.

---

## 0. Guarantees that frame every phase

1. **The notebook API stays unchanged.** `load_grains`, `load_spike_data`, `check_measurement_quality`,
   `UPb_grain` and its `print_*` methods, every function in `utils`, `constants` and the spike tables
   keep their names, signatures and defaults. `tests/test_public_api.py` freezes this surface and
   replays every call in the README, in `examples/zircon_CA-ID-TIMS_UPbR_demo.ipynb` (cell by cell)
   and in the local `MCR_data/*.ipynb`.
2. **Reduced numbers do not change.** `tests/test_snapshot.py` compares 9,036 numbers (every numeric
   attribute of every grain, including covariance matrices) for `examples/synthetic_zircon_CA-ID-TIMS.csv`
   under D, magma and no Th correction, at a relative tolerance of 1e-12. It was written before any
   app work, in commit `Snapshot every reduced number…`. The existing spreadsheet regressions
   (`tests/test_reported_sheet_errors.py`, `tools/verify_derivation.py`) stay green. A deliberate
   change to the numbers needs its own reviewed commit that regenerates the snapshot with
   `tools/make_snapshot.py`.
3. **The engine stays Qt-free.** Importing `IDTIMS_UPbRPy` must not load PySide6, PyQt, shiboken or
   matplotlib (this is tested). GUI dependencies come only with an optional `gui` extra.
4. **New engine capability goes in new modules or new code paths.** The existing 535 path is not
   edited. ET2535 is a new branch selected by `Spike Type`, and the snapshot proves 535 is untouched.
5. **Yiming's files are never modified.** The untracked `BSULab_UPbR26XML.xls` and demo notebook stay
   untracked and untouched. Spreadsheet comparisons read copies.

---

## 1. Coverage: engine vs BSU spreadsheet vs ET_Redux

Sources followed (the methods are re-implemented, not translated line by line):

- Schmitz, M.D. and Schoene, B. (2007), *Derivation of isotope ratios, errors, and error correlations
  for U-Pb geochronology using 205Pb-235U-(233U)-spiked isotope dilution thermal ionization mass
  spectrometric data*, Geochem. Geophys. Geosyst. 8, Q08006, doi:10.1029/2006GC001492. This is the
  basis of the BSU sheet and of this engine (see `docs/index.html`).
- McLean, N.M., Bowring, J.F. and Bowring, S.A. (2011), *An algorithm for U-Pb isotope dilution data
  reduction and uncertainty propagation*, Geochem. Geophys. Geosyst. 12, Q0AA18,
  doi:10.1029/2010GC003478. This is ET_Redux's covariance framework.
- ET_Redux (CIRDLES), local clone `~/Github/ET_Redux` at `01fc486` (2022-07-31). License:
  **Apache License 2.0** (repo-root `LICENSE`; headers read "Copyright 2006-2018 James F. Bowring,
  CIRDLES.org, and Earth-Time.org"). Files consulted, all under
  `src/main/java/org/earthtime/`:
  - value models in `UPb_Redux/valueModels/definedValueModels/`: `AlphaPb.java`, `AlphaU.java`,
    `MolU235b.java`, `MolU238b.java`, `Age206_238r_Th.java`, `Age207_235r_Pa.java`;
  - reduction: `UPb_Redux/fractions/UPbReduxFractions/fractionReduction/UPbFractionReducer.java`,
    `…/ReductionHandler.java`, `dataDictionaries/MatrixSpecifications.java`;
  - models: `ratioDataModels/tracers/TracerUPbModel.java`,
    `ratioDataModels/pbBlankICModels/PbBlankICModel.java`,
    `ratioDataModels/initialPbModelsET/StaceyKramersInitialPbModelET.java`;
  - sample dates and plots: `UPb_Redux/valueModels/SampleDateModel.java`,
    `UPb_Redux/dateInterpretation/concordia/{ConcordiaGraphPanel,YorkLineFit,ErrorEllipse}.java`;
  - report columns: `dataDictionaries/reportSpecifications/ReportSpecificationsUPb.java`.

  Apache-2.0 would permit porting with attribution. The decision is still to re-implement from the
  papers and cite the class whose method each feature follows.
- BSU sheet: `BSULab_UPbR26XML.xls`, sheets `Raw Data Input`, `Data Reduction Engine`,
  `U-Pb Data Table Output`, `GeoChron xml`. It is read with `xlrd` by `tools/audit_xls.py`. The
  template ships with six example fractions (z1 to z6, **ET2535**, Daly) and cached results.

### 1.1 What each one does

| Topic | Engine today | BSU sheet | ET_Redux |
|---|---|---|---|
| Tracers | 535 only: ET535 v1-3, BSU1B, MIT1L tables (ET2535 table present, not usable) | 535 and 2535 (ET535, ET2535) | ET535, ET2535 (2012 v3, hard-coded with full correlations incl. ρ(conc205, conc235)=0.9957), 205-233-236 types |
| Pb fractionation | Linear, user α per collector (Faraday/Daly) ± | Linear; 535 user α, 2535 α = (1 − R25t/R25m)/3 | Same linear law (`AlphaPb`); mean α for single spike |
| U fractionation | 233/235 double spike, linear (`calc_FU`), with natural 238/235 = 137.818 | Same | Same closed form (`AlphaU`) |
| UO2 oxide correction | None (expects corrected ratios) | None in the sheet; done by Tripoli ("238/235 oxide R18 0.00205") | In reduction, from r18O/16O |
| Pb blank IC | Fixed ratios ± with ρ 6/4–7/4 and 6/4–8/4 | Same | Blank IC model with three ρ |
| Common Pb split | All blank if 204Pb ≤ blank 204Pb; otherwise lab blank + initial Pb | Same rule | Same rule (zircon flag) |
| Initial Pb model | Stacey-Kramers (`utils.SK75`) or user ratios | SK calculator at an estimated age | SK at estimated date, not iterated |
| U blank | Mass ± % in pg, natural composition | Same | Mass + r238/235b |
| 230Th disequilibrium | D(Th/U) or Th/U magma (from 208Pb*), long-time approximation | Th/U magma, [230Th/238U] | Th/U magma, Newton solve |
| 231Pa | None | None | [231Pa/235U] activity ratio |
| Measured covariance | Inferred from linked three-ratio identities, quality check, strict rejection | Partly | Inferred from three-ratio closure |
| Propagation | Joint first-order J Σ Jᵀ, Pb + U + Th (analytical only) | Partial derivatives, diagonal plus selected terms | Full Jacobian chain with separate analytical, tracer and λ sub-matrices |
| Tracer and λ systematic terms | Not propagated | Not propagated | Propagated: X (internal), Y (+tracer), Z (+λ) |
| Dates | 206/238, 207/235, 207/206, Th-corrected; % discordance not stored | Same plus % discordance | Same plus 208/232, Pa variants |
| Weighted means | None | None (done in Isoplot or by hand) | WM with shared tracer and λ covariance (McLean 2011 note), MSWD |
| Concordia | None (notebooks plot their own) | PlotDat sheets for Isoplot | Wetherill, T-W, 2σ ellipses, λ envelope, include/exclude |
| Discordia | None | None | York fit, intercepts with asymmetric errors |
| Exports | Python objects; `print_*` | U-Pb Data Table Output, GeoChron XML sheet | Excel and CSV reports, Aliquot XML, Geochron upload |

### 1.2 Known differences between engine and sheet (kept as they are)

- **Uncertainties differ by design.** The engine propagates jointly and the sheet
  does not. Private workbook audit results remain outside this repository;
  synthetic fixtures test the public reduction and export paths.
- **ET535 v2 tracer table.** Its 206/205 and 207/205 "uncertainty" entries read 43.49 and 47.37 %.
  They look like a unit slip, but this was not investigated and the table is unchanged.
- **Strict covariance by default.** The BSU1B example tracer errors imply an impossible covariance.
  `load_grains(...)` without `strict_covariance=False` therefore raises. This includes the call in
  the demo notebook as written today. The test records this behaviour; nothing is changed.
- **λ230.** The engine uses 9.195e-6 /y (Cheng et al. 2000). The BSU template uses 9.158e-6 /y, and
  its constants block also lists λ234 = 2.8262e-6. The engine default stays, and the app will show
  the value in use (see open questions).

### 1.3 Gap list

**Must-have, for the app to replace the sheet for Yiming's data:**

1. **ET2535 reduction.** αPb from measured 202/205 against the tracer, with its uncertainty and its
   correlation to the other x/205 ratios in the joint covariance. The BSU template's six fractions
   are the check. This needs measured `202Pb/205Pb` (already in the contract). It is a new code path;
   535 stays unchanged.
2. **Fraction import and export in the agreed contract** (section 2), with legacy CSV, manual entry
   and paste from Tripoli. This is a new engine module, `IDTIMS_UPbRPy.fractions`.
3. **Per-fraction identifiers** (sample, fraction, beaker, source mount, grain and spot), carried
   through reduction and export.
4. **Weighted means** of 206/238 (Th-corrected and not), 207/206 and 207/235. Each reports value,
   MSWD, n, probability of fit and an analytical (X) uncertainty, with fractions switched on and
   off. New module `IDTIMS_UPbRPy.dates`; inverse-variance weighting.
5. **Y and Z uncertainties for weighted means.** Tracer calibration (205Pb and 235U concentrations
   and their correlation) and decay constants, carried as shared systematic terms across fractions,
   following McLean et al. 2011 and ET_Redux's `SampleDateModel` weighted mean. Per-fraction Y and Z
   are "later". This needs tracer concentration uncertainties in the tracer tables. The ET535 and
   ET2535 CSVs carry ratio errors but leave the concentration error blank (`uncertainty,,` in
   `ET2535_v3.csv`), so the values must be supplied. See open questions.
6. **Concordia view.** Wetherill and Tera-Wasserburg, 2σ ellipses, Th-corrected option, fractions
   on and off in sync with the table and the weighted mean.
7. **BSU-style data table export.** Columns of `U-Pb Data Table Output` (listed in section 3, step 8)
   with footnotes. Also a full-precision CSV of every reduced attribute, and a project file.
8. **Settings visible and saved**: tracer and version, fractionation, blanks, initial Pb, Th
   correction, constants in use (λ230 among them), strict vs diagnostic covariance. The diagnostic
   mode shows a persistent warning, as the README requires.
9. **% discordance** per fraction, as the sheet reports it. This is a new derived output in the
   export layer and does not change any stored number.

**Later:**

- 231Pa correction ([231Pa/235U] activity ratio, as ET_Redux).
- UO2 oxide correction inside reduction, if the raw-data app does not apply it (see contract).
- Per-fraction overrides of blank, initial Pb and fractionation (the engine applies one setting to
  all fractions; the app can reduce per row when needed).
- Per-fraction Y and Z uncertainties; uncertainty-contribution view (ET_Redux "Kwiki"-like).
- Sample isochron ratios (238/204, 206/204, 235/204, 207/204 with ρ) for non-zircon minerals; the
  sheet carries these columns, mostly zero for zircon.
- Discordia (York fit) intercepts.
- 208/232 dates.
- ET_Redux-compatible export (Aliquot XML; its schema is fetched from the EARTHTIME/Schema repository
  and is not in the clone, so this is not cheap). Geochron upload.
- 205-233-236 tracers, U-only or Pb-only fractions.
- Database mode and opening from UPb Lab (section 4).

**Not needed:**

- Raw IsoprobeT ingestion and cycle filtering (raw-data app).
- Exponential or power fractionation laws (neither the sheet nor ET_Redux uses them).
- ET_Redux's LA-ICP-MS paths and its symbolic expression trees.
- The sheet's PlotDat sheets for Isoplot (the app plots natively).

---

## 2. Input contract: `idtims-fractions/1`

Status: **agreed** with the raw-data session (filament) on 2026-11-14. The full text is
[`docs/contract-idtims-fractions-v1.md`](contract-idtims-fractions-v1.md); filament keeps the same
file.

Filament's amendments, accepted:
- A row may carry only the Pb block or only the U block. Rows are merged across files by
  `Fraction ID`, and conflicting values are an error.
- New optional columns `Pb Method`, `U Method`, `Raw App Session` (with its SHA-256) and
  `Pb Collector Detail`.
- `Collector` names the detector the Pb fractionation factor applies to.
- `202Pb/205Pb` is required for 2535. When the spike type is missing, its presence makes the reader
  infer 2535 and ask the user to confirm.

Filament also answered the open questions:
- it owns the oxide correction (BSU uses 18O/16O = 0.00206; 238/233 needs no correction);
- it computes the correlations from cycles;
- it pairs Pb and U runs by `Fraction ID`.

Summary:

- One CSV row per fraction. UTF-8, comma-separated, one header row, full precision, no comment
  lines. Column `Contract` = `idtims-fractions/1` on every row. Unknown columns are ignored and
  kept. Adding an optional column keeps the version; renaming a column or changing its meaning
  makes `/2`.
- Required: `Fraction ID`, and each ratio as `<ratio> Mean` with `<ratio> % Standard Error`. The
  error is 1σ standard error of the mean over accepted cycles, in percent, as Tripoli reports it.
  - Pb ratios: 206/204, 206/207, 206/205, 207/205, 204/205, 208/205, and 202/205 for 2535.
  - U ratios: 238/235, 233/235, 238/233.
  - The ratios are baseline-, detector- and oxide-corrected and cycle-filtered, but **not** mass
    fractionation corrected. The reduction app does that.
- Optional fields:
  - identity: `Sample`, `Beaker`, `Source Mount`, `Source Grain`, `Source Spot`, `Aliquot`;
  - setup: `Sample Weight (mg)`, `Spike Weight (g)`, `Spike`, `Spike Type`, `Collector`;
  - within-run correlations, `rho <A>|<B>`;
  - provenance: Pb and U raw file names and SHA-256, run starts, cycles used and total, filter
    rule, `U Oxide 18O/16O`, writer name and version, export time.
- **Legacy files** without `Contract` are read as today's layout, with `Grain ID` taken as the
  fraction label. This keeps Tripoli-reduced data, `examples/` and notebooks working.
  `load_grains` keeps `id='Grain ID'` as its default; the app passes the contract names explicitly.
- **Manual entry and paste.** The app's import table has exactly these columns. Pasting a Tripoli
  block fills them, and saving writes a contract CSV.
- **Optional correlations** become `covariance_overrides`, which the engine already supports.
  Missing correlations keep the documented conditional-independence assumption.

---

## 3. Workflow

The left-hand rail follows Studio's model. Steps are data (`WorkflowStep(title, summary, hint)`),
not classes. A step unlocks once the previous one is complete. Back and Next use Ctrl+[ and Ctrl+].
There is one main column per step and an inspector on the right.

1. **Import fractions.**
   - Sources: open a contract CSV (from the raw-data app), a legacy Tripoli/IDTIMS_UPbRPy CSV, or
     an empty table for manual entry and paste. Content decides which reader runs (UX rule 4).
   - The quality check (`check_measurement_quality`) runs on import. Its failures are listed per
     fraction with the allowed error interval.
   - The identity columns can be edited.
2. **Tracer and weights.**
   - Per fraction: sample weight (mg), spike weight (g), tracer, version, type (535 or 2535),
     collector (F or D).
   - The tracer table is shown read-only with values and 1σ %, and its source file is named.
3. **Fractionation.**
   - 535: αPb per collector, ± absolute, in %/amu.
   - 2535: αPb computed per fraction from 202/205, shown with its uncertainty.
   - U: αU from 233/235, shown per fraction.
4. **Blanks and common Pb.**
   - Pb blank: mass in pg ± %, composition 6/4, 7/4 and 8/4 ± %, and two ρ.
   - U blank: mass in pg ± %.
   - Initial Pb: Stacey-Kramers at an estimated age (`utils.SK75`), or user ratios ± %, ρ.
   - The rule used per fraction ("all blank" or "blank + initial") is shown after reduction.
5. **Th correction.** None, D(Th/U) ± with Th/U magma, or Th/U magma ± (from 208Pb*). The λ230 in
   use is shown.
6. **Reduce.**
   - Runs `load_grains` with the contract column names, in a worker thread.
   - Shows per-fraction status, data-quality results and the `uncertainty_assumptions`.
   - Strict mode is the default. Diagnostic mode (`strict_covariance=False`) is an explicit,
     labelled choice with a persistent banner.
7. **Review.**
   - A table of dates ± 2σ (206/238, 207/235, 207/206, Th-corrected), % discordance, Pb*/Pbc and
     Th/U.
   - A concordia panel (Wetherill or T-W; ellipses; Th-corrected toggle).
   - A weighted-mean panel with fraction on/off, MSWD, n, probability of fit and X/Y/Z.
   - 206/238 is the default date (UX rule 9).
   - On/off syncs across the table, the concordia and the weighted mean, and is saved.
8. **Export.**
   - **BSU data table**, CSV and XLSX, with the columns of `U-Pb Data Table Output`:
     - compositional parameters: Sample/fraction, Th/U, 206Pb* (×10⁻¹³ mol), mol % 206Pb*,
       Pb*/Pbc, Pbc (pg);
     - radiogenic isotope ratios: 206Pb/204Pb, 208Pb/206Pb, 207Pb/206Pb ± %, 207Pb/235U ± %,
       206Pb/238U ± %, corr. coef.;
     - dates (Ma): 207Pb/206Pb ±, 207Pb/235U ±, 206Pb/238U ±;
     - 238U/206Pb ± %, 207Pb/206Pb ± %, corr. coef.;
     - the sample isochron ratio block (238/204, 206/204, 235/204, 207/204, 204/206 with ρ);
     - Wt. (mg), U (ppm), Pb (ppm);
     - footnotes (a) to (j) adapted to the settings in use.
   - **Full CSV** of every reduced attribute.
   - **Contract CSV** of the inputs as edited.
   - **Project file.**
   - ET_Redux export is "later".

### 3.1 Per-fraction identifiers (designed now, used by database mode later)

| Field | Example | Meaning |
|---|---|---|
| `sample` | SYN-1 | Sample name |
| `fraction_id` | z1 | Fraction label, unique per project (BSU "Fraction ID") |
| `beaker` | K1 / B1677 | Dissolution beaker or capsule (BSU "Barrel number") |
| `source_mount` | M23-04 | LA-ICP-MS mount |
| `source_grain` | g117 | Grain plucked, as labelled in grainatlas/upbdb |
| `source_spot` | s117-1 | LA-ICP-MS spot on that grain |
| `aliquot` | main | Free grouping label |
| `source_grain_uid`, `source_spot_uid` | uuid | Confirmed UPbDB source identifiers copied in the hand-off CSV |

All fields are optional except `fraction_id`. They map one-to-one to the contract columns
(`Sample`, `Fraction ID`, `Beaker`, `Source Mount`, `Source Grain`, `Source Spot`, `Aliquot`).

### 3.2 Project file

- JSON with extension `.idtr` (placeholder, kept in branding), `format` = "ID-TIMS reduction
  project", `version` = 1.
- Contents:
  - the input fraction table **embedded** (it is small), plus source file names and SHA-256;
  - all settings;
  - fraction on/off and the chosen weighted-mean date;
  - engine version and code fingerprint;
  - an optional `origin` block reserved for database mode (Studio's version-2 pattern).
- Opening a project recomputes from the embedded inputs; results are not trusted from disk.
- Written atomically. Autosave sidecar in `~/<app>/autosave/` as Studio does.
- Unsaved-change tracking compares a scientific fingerprint of the document.

The reserved `origin` object now accepts the offline CSV database link, without
changing project `version = 1`. It is null when no fraction has `Fraction UID`;
otherwise its shape is:

```json
{
  "format": "idtims database link",
  "format_version": 1,
  "server": "https://upbdb.example.invalid/lab",
  "fractions": {
    "z1": {
      "fraction_uid": "uuid",
      "chemistry_batch_uid": "uuid or null",
      "spike_solution": "ET535/master/v3",
      "spike_version_uid": "uuid or null",
      "database_read_at": "2026-11-20T10:00:00-07:00",
      "spike_confirmed_at": null
    }
  }
}
```

Unknown origin formats or unsupported origin versions are refused with a readable
error. The CSV remains authoritative for copied link/chemistry values. Source
lists preserve empty entries; unequal filled list lengths are reported as an
informational issue. Multiple database servers are refused at import/merge.

In Tracer, each `Spike Solution` is a proposal for an exact local registry key.
Its source, status and composition are shown before a per-fraction Confirm action.
Missing keys, conflicting `Spike` names/types, or an explicit contradictory project
version block that fraction. Before confirmation, choose Default per tracer or a
matching version; after confirmation, that exact per-fraction key overrides the
project-wide `settings.spike_version`, even if that setting changes later. The
Tracer reference labels this override. Clearing `Spike Solution` explicitly in
Import allows a manual tracer choice. Other copied link fields remain available.

Confirmation timestamps participate in scientific dirty tracking. Reopening
restores consent only when the origin key and spike-version UID match the embedded
CSV (and fraction UID/server still match). Editing a spike key, version UID, name,
type, fraction UID or database server in the app clears that fraction's confirmation. Reopening recomputes with
the exact confirmed key and does not contact a database. Review shows capsule
label/set, chemistry and source labels with elided text/full tooltips, plus a
database marker whose tooltip includes `Database Read At`. Publication exports
include filled chemistry and source labels, never database UIDs/server/read time;
full numeric exports retain their existing numeric-only scope. The contract CSV
and project origin retain database provenance.

---

## 4. Architecture

**Decisions from the coordinating session, checked against what the spec needs.** All hold. One
refinement: the reusable logic (contract I/O, weighted means, exports, project format) goes into
the Qt-free engine package as new modules, so notebooks gain them too. The GUI package only lays
out and calls.

- **Packages.** The app is a sibling top-level package `src/idtims_app/` in the same distribution.
  `pyproject` gains:
  - `[project.optional-dependencies] gui = ["PySide6>=6.11.1", "pyqtgraph>=0.14.0"]`, plus `build`
    (PyInstaller) and `dev` extras;
  - an entry point (placeholder `idtims-app = "idtims_app.main:main"`);
  - `python -m idtims_app`.

  Studio uses the top-level name `GUI`. This app uses a distinct name so both can be installed in
  one environment.
- **New engine modules (Qt-free, no changes to existing ones):**
  - `IDTIMS_UPbRPy.fractions`: contract and legacy read/write, validation, mapping to `load_grains`
    keyword names;
  - `IDTIMS_UPbRPy.settings`: a dataclass for all reduction settings that round-trips to JSON and
    produces the four dictionaries `load_grains` takes today;
  - `IDTIMS_UPbRPy.dates`: weighted mean, MSWD, probability of fit, X/Y/Z;
  - `IDTIMS_UPbRPy.export`: BSU table, full CSV;
  - `IDTIMS_UPbRPy.project`: project format;
  - ET2535 as a new branch in `UPbR`/`UPb_grain`, chosen by `spike_type == 2535`. The current
    `NotImplementedError` is the only line that changes behaviour, and only for 2535 rows.
- **GUI package `idtims_app/`**, mirroring Studio's split:
  - `main.py`: args (`--open`, `--theme`, `--export PNG`, `--verify-reduction`, `--smoke-test`
    hooks);
  - `window.py`: rail, main column, inspector;
  - `steps.py`: `WorkflowStep` rows;
  - `services.py`: Qt-free state, unlocking, reduction calls;
  - `workers.py`;
  - `widgets/`: fraction table, settings forms, concordia, weighted mean;
  - `ui/`: copied design files (see below);
  - `branding.py`;
  - `launch.py`: single instance and, later, the URL scheme.
- **Sharing Studio's design system means copying for now.** `GUI/theme.py` (ThemeSpec, palette,
  QSS, wallpaper, `NeumorphicFrame`, `build_application`, `apply_theme` with its gc guard), the
  workflow-rail delegate and stage icons from `icon.py`, `BusyIndicator`, and the rounded pyqtgraph
  canvas plus ellipse batch from `widgets.py` are copied into `idtims_app/ui/`. Each copied file
  gets a header naming its Studio source path and commit. Copies are taken from **committed**
  Studio code only, because `UPbRPy/AGENTS.md` says theme.py, icon.py and assets hold the owner's
  uncommitted work. App and organisation names in `build_application` come from `branding.py`.
  Studio itself is not touched.
- **Proposal for later: one shared design package.** Make a small package (placeholder name
  `labkit`), with its own repository and no science, holding theme, icons, rail, busy indicator,
  rounded plot canvas, ellipse batch, single-instance and URL-scheme helpers, and the update
  widgets. Studio, this app and filament depend on it through a `gui` extra. Migrate Studio last,
  behind its screenshot tests. Until then, record the copied commit in each header and diff the
  copies at each Studio release.
- **Standalone first.** Database mode later reuses Studio's mechanisms:
  - a Qt-free REST client under `IDTIMS_UPbRPy.integration`;
  - keychain tokens;
  - a one-time code exchanged at open;
  - an inbox notice file for UPb Lab;
  - a "Submit to database" rail row that stays disabled, with an explanation, while the extra is
    absent.

  Its URL scheme (placeholder `idtims://fraction-set/<id>?server=&code=&via=upblab`) is to be
  added to `upblab/docs/WORKFLOW.md` and `deep-links.md` when that phase starts. None of it is
  built now.
- **Layout fits 1280×800** (UX rule 7; minimum 1024×640). The rail is collapsible and the inspector
  can be toggled, as Studio's small-screen work requires. Light theme by default with dark and
  System; live switching (rule 1).
- **Packaging** follows Studio:
  - `packaging/<App>.spec` (PyInstaller 6) and `scripts/build_desktop.py`, building into
    `~/Library/Caches/<app>/`;
  - a **smoke test from the first GUI step**: run the frozen app with `--export PNG` (empty window,
    the example CSV, a saved project; each PNG at least 10 kB) and `--verify-reduction`, which
    compares the frozen app's reduction of the example data with `tests/data/synthetic_snapshot.json`.
  - Guards against Studio's two frozen-only bugs:
    1. no lazy module `__getattr__` in either package. If one is ever added, it must turn
       `ImportError` into `AttributeError`, and `tests/test_packaged_imports.py` imports every
       public name the way the frozen loader does;
    2. any code fingerprint hashes source or PYZ raw bytes, never re-marshalled code objects.
- **Test tiers from the start:**
  - *Quick* (each change): engine tests (about 1.5 s today, including the snapshot and API tests)
    plus GUI tests for touched modules, offscreen.
  - *Full* (before a build or install, and after any change to numerics, the contract, the project
    format or pyproject): all tests, `tools/verify_derivation.py`, offscreen screenshot tests at
    1280×800 and 1440×900, and the packaging smoke test.
  - A `scripts/run_tests.py quick|full` wrapper as in Studio. GUI tests build the app through the
    copied `build_application`, without pytest-qt (Studio's convention).
- **CI** runs only on `v*` tags and manual dispatch (changed on this branch).

---

## 5. Phase 1 plan (after the spec is confirmed)

Small audited steps. Each one ends with the quick tier green and screenshots at 1280×800 for Yiming.
The example numbers are checked against the snapshot (535) and against the BSU template's cached
values (2535, once step b lands).

- a. Engine: `settings`, `fractions` (contract + legacy) with round-trip tests.
- b. Engine: ET2535 path, checked against the six template fractions (`tools/audit_xls.py`
  extended for 2535).
- c. App skeleton:
  - copied theme, rail and branding;
  - Import step with fraction table and quality check;
  - packaged smoke test working at this point.
- d. Settings steps 2 to 5 and Reduce; full-precision CSV export.
- e. Engine `dates` (weighted mean, X), then the Review step (table, concordia, weighted mean,
  on/off).
- f. BSU table export, project save/restore, autosave.
- g. Y and Z, once tracer concentration uncertainties are supplied.

---

## 6. Open questions for Yiming

1. **Tracer.** Which tracer and version are your Boise fractions spiked with: ET535 or ET2535? The
   BSU template is set up for ET2535 with measured 202/205, and that decides what is built first.
2. **λ230.** The engine uses 9.195e-6 /y and the BSU sheet 9.158e-6 /y. Keep the engine's default
   (no numbers change), or switch the app's default to the sheet's value?
3. **Tracer calibration uncertainties for Y and Z.** Where should the 205Pb and 235U concentration
   uncertainties (and their correlation) for your tracer come from: the EARTHTIME ET535/ET2535
   calibration, or BSU's own values?
4. **The demo notebook.** As written, it calls `load_grains` without `strict_covariance=False`, so
   it stops with "impossible covariance" for the BSU1B example tracer. Do you want to add the flag
   in your copy? It is your untracked file and we leave it alone.
5. **Name and icon** for the app (one place: `idtims_app/branding.py`).

## 7. Not verified

- **2535 match.** That the engine's 2535 path will match the sheet: the formula is confirmed
  (αPb = 0.002578 for template z1 from (1 − R25t/R25m)/3), but nothing is implemented yet.
- **ET_Redux details.** These come from reading the code (an assisted survey, spot-checked on
  `AlphaPb.java`); ET_Redux was not run.
- **Example data in a spreadsheet.** No spreadsheet holds the synthetic example, so step checks for 535
  use the synthetic snapshot and the optional private workbook audit.
- **Real IsoprobeT files.** None are on this machine, so the contract has not been exercised on real
  raw output yet. Whether Pb and U runs pair naturally per fraction is unknown; filament pairs them
  by `Fraction ID`.

## 8. Branches and what a merge would involve

- `main` (`5701072`) is an ancestor of `MCR_data_comparison` (`b7c53d8`, 22 commits ahead). Those
  22 commits hold the packaged library (`ba1bd2a`), the derivation website and the MCR work.
- `app` is cut from `b7c53d8` and only adds commits. Merging `app` into `MCR_data_comparison` or
  into `main` would be a **fast-forward**.
- Merging into `main` would also bring in all 22 `MCR_data_comparison` commits. Among them, the
  untracking of `MCR_data/` (the local files stay, git history keeps the old blobs) and the src
  layout. Anything on `main` that depended on the old flat layout would need checking.
- No merge is done by this session.
