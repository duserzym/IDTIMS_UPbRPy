# UI round handoff · 2026-11-14

All seven pieces are implemented on `app`. No commit, push, checkout, stash,
reset, network access, installation, packaged build or full-tier test run was
performed. `src/IDTIMS_UPbRPy/` has no changes. The protected untracked spreadsheet
and notebook were not accessed or changed. Packaging, final audit and commits
remain with the supervisor as requested.

## Pieces and validation

Every row below names a completed `.venv/bin/python scripts/run_tests.py quick`
run. Each run also passed **9,495 subtests**, with the existing **33 warnings**.
Files overlap between pieces because the shared controls are integrated into
the same window and pages; the working tree is uncommitted.

| Piece | Result | Files and outcome |
| --- | --- | --- |
| 1 · Review A only | 387 passed | `src/idtims_app/main.py`, `window.py`, `ui/tables.py`, `widgets/review_page.py`, `concordia.py`, `weighted_mean.py`; `tests/test_gui_import.py`, `test_gui_review.py`; `docs/screenshots/variants/README.md`. Deleted `widgets/review_layouts.py` and `scripts/render_review_variants.py`. Plots above the table, separate frozen Fraction/On/off, elided identities with tooltips, consistent selection, large mean and contained issues drawer. Copied the 15 original PNGs unchanged before editing. |
| 2 · Review panel controls | 389 passed | New `src/idtims_app/ui/panels.py`; `widgets/review_page.py`, `window.py`. Full-area maximise/restore, header buttons/double-click, Cmd/Ctrl+Shift+Return, conditional Esc, remembered splitters, handle double-click reset, View › Reset Layout, 62/38 default row split, four-row table minimum and 360 px concordia minimum. Mouse transitions use 180 ms OutCubic; keyboard actions and reduced motion are instant. |
| 3 · Rail persistence | 389 passed | `src/idtims_app/window.py`. A new narrow window starts collapsed below 1440 px; wide windows use the remembered preference. Explicit toggles persist. Reset Layout restores the width-based default. |
| 4 · Other multi-panel pages | 389 passed | `src/idtims_app/ui/panels.py`, `ui/theme.py`, `window.py`; `widgets/import_page.py`, `tracer_page.py`, `reduce_page.py`, `export_page.py`, `forms.py`, `settings_pages.py`; `tests/test_gui_import.py`. Existing work panels use the same splitters, reset and maximise controls. Import has the fraction table and issues; no attention means a header badge. Other steps use a contained issues drawer. Explanatory text remains reachable inside panels. |
| 5 · Settings hierarchy | 389 passed | `src/idtims_app/widgets/settings_pages.py`, `ui/theme.py`. Active project fractionation comes first; common Pb precedes laboratory composition, blank masses precede blank composition within that panel, and Th correction precedes quiet decay constants. Tracer reference values are muted. Field bindings, validation and values are unchanged. |
| 6 · Offscreen regressions | 418 passed | New `tests/test_gui_panels.py` and `scripts/ui_round_support.py`; `tests/test_gui_import.py`, `docs/testing.md`; fixes in `ui/panels.py`, `ui/tables.py`, `widgets/review_page.py`, `window.py`. Added 29 tests covering all steps at all three sizes, every work panel's exact round trip, focus/pointer/keyboard targeting, Esc passthrough, both reset paths, table hiding, every page's persistence, close while maximised/hidden, rail preference, new-issue identity, short/reduced motion, tab switches, 40 long IDs, frozen checkbox clicks/scroll/selection and theme refresh. The 40-fraction means equal `dates.sample_dates` for every date kind and two include sets. |
| 7 · Screenshots and visual refinement | 418 passed | New `scripts/render_ui_round.py`; `docs/screenshots/*.png`, this handoff and `docs/testing.md`; visual refinements in `window.py`, `ui/panels.py`, `ui/theme.py`, `widgets/review_page.py`, `forms.py`, `settings_pages.py`, `tracer_page.py`, `issues_panel.py`, and additional assertions in `tests/test_gui_panels.py`. Fixed the rail's old splitter allocation, expanded the mean date selector, retained press feedback, top-aligned settings contents, made both tracer reference rows readable, removed the duplicate Import issues heading/frame and kept long issue identities inside their cards with full tooltips. |

Early runs caught failures that were resolved before advancing: piece 1 had
stale summary/rail assertions and a concordia tick-width layout shift; piece 2
had minimum-height fit regressions; piece 6 had a fixed 200 ms animation wait
that was timing-sensitive in the full suite. The latter now checks the 180 ms
configured duration/easing and waits for Qt's completion signal. The Import
test helper now flushes DeferredDelete, as the other GUI helpers already do.
The final visual pass also caught the unused rail allocation; it has explicit
geometry regression assertions. No remaining failed checks are accepted.

## Screenshots

All after images use light theme and isolated temporary settings/autosaves.
The normal `--export`/`--size` path renders them; the maximised case uses the
same startup/export helpers and the real panel action. Reproduce with:

```sh
.venv/bin/python scripts/render_ui_round.py
```

Every final PNG was opened and visually inspected. All 19 files have their
requested pixel dimensions. SHA-256 checks confirm all 15 archived before
images match the original `HEAD` bytes. The archive was copied with metadata
preserved before the UI edits.

| Image | Before | After |
| --- | --- | --- |
| `app_blanks_MA1_1280x800.png` | [before](screenshots/before_ui_round/app_blanks_MA1_1280x800.png) | [after](screenshots/app_blanks_MA1_1280x800.png) |
| `app_export_MA1_diagnostic_1280x800.png` | [before](screenshots/before_ui_round/app_export_MA1_diagnostic_1280x800.png) | [after](screenshots/app_export_MA1_diagnostic_1280x800.png) |
| `app_export_template2535_1280x800.png` | [before](screenshots/before_ui_round/app_export_template2535_1280x800.png) | [after](screenshots/app_export_template2535_1280x800.png) |
| `app_fractionation_template2535_1280x800.png` | [before](screenshots/before_ui_round/app_fractionation_template2535_1280x800.png) | [after](screenshots/app_fractionation_template2535_1280x800.png) |
| `app_import_MA1_1280x800.png` | [before](screenshots/before_ui_round/app_import_MA1_1280x800.png) | [after](screenshots/app_import_MA1_1280x800.png) |
| `app_import_empty_1280x800.png` | [before](screenshots/before_ui_round/app_import_empty_1280x800.png) | [after](screenshots/app_import_empty_1280x800.png) |
| `app_import_template2535_1280x800.png` | [before](screenshots/before_ui_round/app_import_template2535_1280x800.png) | [after](screenshots/app_import_template2535_1280x800.png) |
| `app_reduce_template2535_diagnostic_1280x800.png` | [before](screenshots/before_ui_round/app_reduce_template2535_diagnostic_1280x800.png) | [after](screenshots/app_reduce_template2535_diagnostic_1280x800.png) |
| `app_reduce_template2535_strict_1280x800.png` | [before](screenshots/before_ui_round/app_reduce_template2535_strict_1280x800.png) | [after](screenshots/app_reduce_template2535_strict_1280x800.png) |
| `app_review_MA1_diagnostic_tw_1280x800.png` | [before](screenshots/before_ui_round/app_review_MA1_diagnostic_tw_1280x800.png) | [after](screenshots/app_review_MA1_diagnostic_tw_1280x800.png) |
| `app_review_MA1_diagnostic_wetherill_1280x800.png` | [before](screenshots/before_ui_round/app_review_MA1_diagnostic_wetherill_1280x800.png) | [after](screenshots/app_review_MA1_diagnostic_wetherill_1280x800.png) |
| `app_review_template2535_strict_1280x800.png` | [before](screenshots/before_ui_round/app_review_template2535_strict_1280x800.png) | [after](screenshots/app_review_template2535_strict_1280x800.png) |
| `app_review_template2535_strict_z3_z5_off_1280x800.png` | [before](screenshots/before_ui_round/app_review_template2535_strict_z3_z5_off_1280x800.png) | [after](screenshots/app_review_template2535_strict_z3_z5_off_1280x800.png) |
| `app_th_MA1_1280x800.png` | [before](screenshots/before_ui_round/app_th_MA1_1280x800.png) | [after](screenshots/app_th_MA1_1280x800.png) |
| `app_tracer_MA1_1280x800.png` | [before](screenshots/before_ui_round/app_tracer_MA1_1280x800.png) | [after](screenshots/app_tracer_MA1_1280x800.png) |

Additional requested views:

| New after image | Earlier visual reference |
| --- | --- |
| [Maximised concordia, 1280×800](screenshots/app_review_template2535_strict_maximised_concordia_1280x800.png) | New state; no previous maximised implementation. |
| [40 fractions, 1280×800](screenshots/app_review_40fractions_1280x800.png) | [Prototype A, 40 fractions](screenshots/variants/review_variant_A_40fractions_1280x800.png) |
| [Review, 1024×640](screenshots/app_review_template2535_strict_1024x640.png) | [Prototype A, 1024×640](screenshots/variants/review_variant_A_1024x640.png) |
| [Review, 1440×900](screenshots/app_review_template2535_strict_1440x900.png) | New size in the main screenshot set. |

The 40-row CSV cycles through the six template rows and changes only Grain ID.
It is created in a temporary directory and removed afterward. It is a layout
stress fixture, not a scientific sample: 27 rows reduce and 13 have known
linked-error failures. Its different aggregate mean is expected from the
repeated data.

Nothing in the requested UI work is intentionally deferred. The supervisor's
packaging/build, final audit and commits remain outstanding by assignment.

## Supervisor follow-up · repeated informational notes

`widgets/issues_panel.py` now groups identical informational notes by kind and
message without the fraction prefix. Matching Pb/U cycle explanations with the
same affected fractions share one compact line in a bottom Notes section, with
the complete explanations and fraction IDs in a tooltip. Blocking issues and
linked-error failures remain separate cards at the top. Different note values
and actionable oxide confirmation controls remain per fraction. `window.py`
uses the displayed note groups for the badge count.

Two regressions in `tests/test_gui_import.py` cover the template's single cycle
note and exactly two failure cards (z1, z6), distinct oxide notes, retained
blocking cards, and display-only grouping across steps. The quick suite passed
**420 tests and 9,495 subtests**, with **33 warnings**. The focused Import suite
also passed **24 tests**. Both Import template/MA1 PNGs above were regenerated
at 1280×800 and opened for visual inspection. No engine or `fractions.py` edits
and no git operations were performed for this follow-up.
