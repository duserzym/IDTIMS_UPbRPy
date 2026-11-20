# Notes on the BSU UPbR spreadsheet (UPbR26XML)

## Adirondack UPbR21/22/24 workbooks (2026-11-20)

`tools/audit_bsu_legacy.py` reads the private Adirondack workbooks in place with
`xlrd`, locates inputs/settings/outputs by labels, and compares the engine,
output tables, CSVs and publication cells. Reports and cell-level evidence stay
outside this repository. No source workbook was edited or recalculated.

With each workbook's selected BSU1B table, constants, fractionation, blanks and
explicit initial-Pb composition, the fully reducible fractions reproduce the
uncorrected radiogenic central ratios and the corresponding U–Pb dates to the
audit's exact tolerance (relative difference below 1e-10). Pb–Pb dates agree
within the sheet's approximately 1.8 ka bisection resolution. Two engine fixes
were approved after the initial comparison:

- Preserve the exact zero assigned by an all-blank Pb partition. A later
  recomputation had produced a rounding residue, enormous sample/initial-204
  ratios and nonphysical sample correlations. The partition now owns that zero,
  including radiogenic helpers and the centre of joint propagation; existing
  first-order sensitivities are retained. Dates are unchanged.
- Use atomic Th/(238U+235U) in magma-mode correction and its Jacobian, matching
  exported mineral Th/U and melt Th/U. Corrected t68 and 206Pb/238U now reproduce
  exactly; t76 retains the bisection tolerance. D-mode values, date errors and
  covariance arrays retain their previous floating-point values.

The following are **sheet errors**, not engine targets. References below are
on `Data Reduction Engine`, column C; other fraction columns carry the same
formulas. The audit resolves labels rather than assuming these row positions.
These older layouts differ from the UPbR26 errors described below.

| Cells | Decoded legacy formula | Error |
| --- | --- | --- |
| C469 | `C16*(1+2*C222)*C172` | `dPb207r/dR76m` needs measured 206/205 (`C12`), not measured 207/206 (`C16`). |
| C254 | `SQRT((C253/C22)^2+(C251/C18)^2)` | Measured 208/204 sigma omits the quotient magnitude. |
| C264 | `SQRT((C263/C160)^2+(C262/C158)^2)` | Analogous tracer 208/204 sigma error. |
| C641 | `C22*C18*((C253/C22)^2-(C251/C18)^2-(C254/(C22/C18))^2)/2` | Quotient covariance requires the sum of the first two variances. C645 has the analogous tracer error. |
| C476 | `C475*C262` | The weighted `dPb207r/dR76t` term uses sigma(204/205)t instead of sigma(207/206)t. |
| C488 | `C487*C266` | The weighted `dPb207r/dR64c` term uses sigma(204/206)t instead of sigma(206/204)c. |
| C207 | `SQRT(C203^2+C199^2*(-2*C209*C203*C199))` | Misgrouped blank 208/206 relative-error/correlation term. |
| C361, C365 | `N'/K + (N/K)*q` | In these decoded quotient derivatives, `N=C173*C26*(1+3*C224)-C166*C173-C219`, `K=1-C26*(1+3*C224)/C245`; the second term needs `N/K^2`. `N'` and `q` are respectively `C173*(1+3*C224)` and `(1+3*C224)/C245` in C361, or `3*C173*C26` and `3*C26/C245` in C365. |
| C102 | `2*SQRT(C132*C132+C126*C126)` | Reports a nonzero percent error even when the guarded sample 235U/204Pb ratio is zero. |

The output common-Pb mass also differs internally: C213 uses summed initial
isotope amounts times the nominal-mass average C195; C60 uses isotope masses
directly. Decoded C195 is
`(204+206*C185+207*C187+208*C189)/(1+SUM(C185,C187,C189))`.
The two definitions give different Pbc values. The audit's local
formula interventions quantify each correction and the remaining residual;
they do not recalculate the workbook in Excel.

Uncertainty agreement is deliberately limited. The engine retains shared
variables through joint `J Σ Jᵀ` propagation; the sheet sums individual terms
and contains the errors above. Fixing sheet typos does not make those models
identical. Missing covariances and diagnostic substitutions remain the documented
README assumptions. Supplemental sample-208Pb covariance outputs in the
UPbR22/24 sheets are not yet propagated by the engine.

The selected BSU1B tracer errors are themselves inconsistent with
`204/206 = (204/205)/(206/205)`. If `e45`, `e65` and `e46` denote their relative
errors, the implied correlation between 204/205 and 206/205 is
`(e45^2+e65^2-e46^2)/(2*e45*e65) = 1.446774029`, outside [-1, 1]. Thus every
otherwise reducible fraction is refused in strict mode, unless a measured-error
check rejects it first. Diagnostic uncertainties are not certified results.

Private workbook/export comparisons are performed by the optional local audit.
No measured comparison values are distributed. The public regression fixtures
are generated from invented ratios with a fixed seed.

## UPbR26XML template and the private ET535 workbook

The following are facts found while checking the engine against `BSULab_UPbR26XML.xls` (the template with
six ET2535 fractions, z1 to z6) and against a private ET535 workbook.

- Both workbooks were read from copies with `xlrd`. Formulas were decoded from the BIFF records with
  `tools/audit_xls.py` (`formulas()`). Neither spreadsheet was changed.
- Cell references are on the `Data Reduction Engine` sheet. Column C is the template's first fraction;
  column E is the private ET535 workbook's first fraction.
- The engine does not reproduce these formulas. Its uncertainties come from joint first-order
  propagation (README, "Uncertainty model and validation limits").

## 1. Row 470: dPb207r/dR76m uses 207/206 where 206/205 belongs

The two formulas, side by side:

| Cell | Label | Decoded formula |
|---|---|---|
| C297 | dPb207s/dR76m | `((C12*(1+(2*C222)))*C172)` |
| C470 | dPb207r/dR76m | `((C16*(1+(2*C222)))*C172)` |

The cells they use:
- `C12` is measured 206Pb/205Pb.
- `C16` is measured 207Pb/206Pb.
- `C222` is F(Pb).
- `C172` is the moles of tracer 205Pb.

The radiogenic 207Pb amount depends on measured 207/206 through
207Pb = (206/205)·(207/206)·(1+2F)·205Pb_tracer − …. Its derivative with respect to 207/206 is therefore
(206/205)·(1+2F)·205Pb_tracer. Row 297 (the sample 207Pb amount) has this right; row 470 puts `C16` in
place of `C12`.

The same formula is in the private ET535 workbook (`E470 = ((E16*(1+(2*E222)))*E172)`).

**Effect.** The incorrect derivative scales the 207/206 contribution by
(207/206)/(206/205). This changes radiogenic 207Pb uncertainty and its derived
date uncertainties. Synthetic derivative tests check the formula.

## 2. Row 255: σ(208Pb/204Pb) has the ratio inside the square root

The decoded formula is
`SQRT((C22/C18)*((C254/C22)^2+(C252/C18)^2))`, where `C22` and `C18` are
measured 208Pb/205Pb and 204Pb/205Pb, and `C254` and `C252` are their standard
deviations. The quotient rule instead requires
`ABS(C22/C18)*SQRT((C254/C22)^2+(C252/C18)^2)`.

**Effect.** The quotient's standard deviation has the wrong magnitude.
`tests/test_reported_sheet_errors.py` checks the engine's quotient rule and
propagation into 208Pb, Th/U and the magma correction using synthetic inputs.

## 3. Rows 333 and 335: sign of the F(Pb) partial derivatives (2535)

Both partial derivatives of F(Pb) with respect to measured and tracer 202/205 carry the wrong sign. The
sheet combines them as independent squared terms, so σ(F(Pb)) is unaffected; the engine reproduces it
exactly (0.0 relative difference).

## 4. Smaller definitional points

- **Output column O.** `U-Pb Data Table Output`!O8 is `'Data Reduction Engine'!$C85`: the
  Th-corrected 206Pb/238U % error. It always appears next to column N, which shows the uncorrected
  206Pb/238U unless the Th switch is on (`'Raw Data Input'!AU53`).
  - `export.bsu_table` pairs each ratio with its own error instead.
  - A ratio must be paired with the error for the same correction choice.
- **Th-corrected % discordance.** C50 uses the Th-corrected t76 (C44) but keeps the uncorrected
  ratios C71 and C69, the same ones C40 uses. The definition (distance to concordia at t76 relative to
  that concordia point's distance from the origin) is:

  `100*SQRT((EXP(λ238*C34)-1-C71)^2+(EXP(λ235*C34)-1-C69)^2)/SQRT((EXP(λ238*C34)-1)^2+(EXP(λ235*C34)-1)^2)`

  The decay constants are hard-coded in the cells. `dates.percent_discordance` reproduces both cells
  as they are, for compatibility.

## Synthetic linked-error coverage (z1, z6)

`tests/data/synthetic_template_2535.csv` deliberately assigns impossible errors
at z1 and z6 for 204/205 = (206/205)·(204/206). Strict mode refuses those rows;
diagnostic mode records its substitution. The other four rows pass. All values
are invented by `tools/generate_synthetic_fixtures.py`.

## How the engine relates to the sheet

- **Values.** Private workbook comparisons use strict numeric tolerances (see `tools/audit_xls.py`
  and `tools/audit_xls_2535.py`). t76 agrees within the sheet's bisection step (1.8 ka).
- **Uncertainties.** The engine propagates jointly and does not contain the errors above, so its
  uncertainties differ from the sheet's. The app's export footnotes say so; no number in the engine
  was tuned to match the sheet.
