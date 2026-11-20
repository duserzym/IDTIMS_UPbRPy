# Testing

Two tiers, run with the repository venv and Qt offscreen (the runner sets
`QT_QPA_PLATFORM=offscreen` a temporary settings file and an isolated autosave folder).

```sh
.venv/bin/python scripts/run_tests.py quick
.venv/bin/python scripts/run_tests.py full            # add --build for the frozen app
.venv/bin/python scripts/run_tests.py screenshots     # refresh docs/screenshots
```

For a restricted checkout, set `IDTIMS_SCREENSHOT_DIR=/private/tmp/idtims-screenshots`
when running `full` to write its screenshot matrix to a writable directory instead
of the default user cache. This does not change the tests, sizes or screenshot checks.

## Quick (after every change)

`pytest -q` over `tests/`: the engine tests (snapshot of 9,036 reduced
numbers, public API, contract reader, ET2535, settings, quality) and the app
tests. The whole suite takes about a minute, so quick runs all of it instead of
selecting tests for changed modules.

`tests/test_adirondack_sheets.py` adds an optional private, read-only comparison
with `~/Github/Adirondack_mountains/data/geochron_new/TIMS` (override with
`IDTIMS_ADIRONDACK_DIR`). It skips with a reason when that folder or the optional
`xlrd`/`openpyxl` readers are absent. It stores only fraction, quantity and cause
identifiers, reads the workbooks in place, and fails for either a new mismatch
or a resolved/reclassified known mismatch. Its shared audit takes about 16 seconds
locally, so it runs in both quick and full without a slow marker. Working/HEAD
cell and formula comparisons are a separate audit CLI option, outside the test.
Generate data-derived evidence outside the repository:

```sh
.venv/bin/python tools/audit_bsu_legacy.py --output-dir /private/tmp/adk-audit
# Add --head-dir /path/to/read-only/committed/copies to audit both versions.
# Add --baseline-audit /path/to/previous/audit.json for before/after categories.
```

`tests/test_adirondack_engine_fixes.py` needs no private workbooks. It checks a
synthetic capped blank (exact initial-204 zero, bounded sample correlations,
unchanged dates/covariance) and independently checks every magma Jacobian input
using total natural U and a nondefault 238U/235U. The example snapshot changes
are restricted to capped sample outputs and magma corrections; D-mode date and
radiogenic covariance fields retain their previous encodings.

- `tests/test_app_services.py`: the app's Qt-free session state (open, merge,
  conflicts, edit, paste, confirmations, save) and `--verify-reduction`. Runs
  without the `gui` extra.
- `tests/test_gui_import.py`: the window offscreen, built through the copied
  `build_application` in a module fixture (no pytest-qt). Window fit at
  1280x800, 1440x900, 1180x740, 1120x700 and 1024x640 (no widget outside the
  window, no clipped button), step locking, synthetic import unlocking step 2, the
  z1/z6 linked-error markers of the BSU template, Pb-only + U-only merge, the
  inline conflict message, paste into a new table, edit and save round trip,
  live theme switching and the `--export` command. Skipped when PySide6 is not
  installed, so the engine-only CI still runs.
- `tests/test_app_reduction.py`: the numbers check of the Reduce step (Qt-free).
  The app reduces one fraction per `load_grains` call; the grains are
  bit-identical to a direct call: synthetic data with `examples/synthetic_settings.json` in
  diagnostic mode equals `tests/data/synthetic_snapshot.json` exactly for every
  fraction and Th variant (and every numeric attribute equals one batch call);
  the BSU template with `tests/data/settings_BSU_template.json` reproduces the
  t68 values of `tests/test_et2535.py`; strict mode reduces z2-z5 and reports
  z1/z6 with the reason; `require_oxide` leaves unconfirmed fractions out. Also
  settings load/save, tracer versions, the 2535 FPb view, fill down and stale
  results.
- `tests/test_gui_steps.py`: steps 2 to 6 offscreen. Every step renders and fits
  1280x800 and 1024x640, steps unlock in order, tracer edits, fill down and
  version, the 2535 FPb table, settings edit / inline problems / Save / Reset /
  Load, the Th kinds and decay constants, Reduce in the worker thread with the
  results table, full-table export, the diagnostic banner appearing and
  disappearing, and `--export` with `--settings --step --reduce`.
- `tests/test_app_review.py`: the Review numbers (Qt-free). The
  Tera-Wasserburg covariance (x = 1/R68r) equals a Monte Carlo (400,000
  draws) and a finite-difference transform of the engine's (R68r, R76r)
  covariance for one synthetic grain; the Wetherill ellipse uses the engine's R75r,
  R68r, their σ and rho_7568_r, and R75r = k·R68r·R76r reproduces them; the
  Th-corrected toggle changes 206/238 and 207/206 (so 238/206) and leaves
  207/235; the weighted mean of an include set is `dates.sample_dates`; the
  include set survives re-reduction and step 7 needs a fraction switched on.
- `tests/test_gui_review.py`: step 7 offscreen. The panel's weighted mean
  equals `dates.sample_dates` exactly for four include sets and every date
  kind (synthetic, diagnostic); toggling in the table updates the concordia, the
  ranked plot and the mean, and Ctrl/Cmd-click or E on the concordia and the
  ranked plot update the table; the Th toggle and T-W switch; fits 1280x800
  and 1024x640 (also with the table hidden); the BSU template in strict mode
  lists z1/z6 greyed with their reasons and means z2-z5; `--export` with
  `--step 7 --review-mode --review-th --date-kind --exclude`.
- `tests/test_app_project.py`: Qt-free projects and exports. synthetic diagnostic and
  BSU template strict round-trip every reduced-grain attribute bit for bit,
  including covariance arrays, edited identities, settings, confirmations and
  include decisions. Validation messages, failed atomic serialization and
  replacement preserving the previous file, scientific dirty tracking, source
  hashes, changed-engine notes, source-copy and raw-PYZ fingerprint stability,
  CSV/XLSX BSU values and notes, merged XLSX groups, 17-digit full CSV, contract
  CSV and sidecar names/newer scientific recovery candidates.
- `tests/test_gui_export.py`: step 8 at 1280x800 and 1024x640, save completion,
  Export options, project CLI save/reopen (including content routing), inline
  recovery Restore/Discard, two-second autosave, sidecar removal on Save,
  title/modified state, single Save/Discard/Cancel guards, weighted-mean zoom
  preservation and concordia zoom excluded from dirty tracking.
- `tests/test_packaged_imports.py`: no module-level `__getattr__` in either
  package, and every public name imported explicitly (Studio's frozen-only
  bugs).
- `tests/test_tracer_completion.py`: real public ET535/ET2535 reductions,
  quotient errors and assumptions, unchanged private/legacy compositions,
  missing-input refusal and database gates, strict app status, and readable
  non-finite propagation errors. Real-public checks skip only when discovery
  finds no checkout; refusal coverage also uses an in-memory fixture.
  `tests/test_gui_database_link.py` checks derived headers/tooltips and specific
  validation messages offscreen.

## Full (before a build or install, and after changes to numerics, the contract, the project format or pyproject)

Quick, then `tools/verify_derivation.py`, then `--export` screenshots of the
empty window, `examples/synthetic_zircon_CA-ID-TIMS.csv` and
`tests/data/synthetic_template_2535.csv` on the Import step, and of steps 2 to 8
(`STEP_SHOTS` in `scripts/run_tests.py`: `--settings FILE --step N --reduce
[--diagnostic] [--confirm-no-oxide] [--review-mode tw] [--exclude IDS]`), at 1280x800 and 1440x900 into
`~/Library/Caches/idtims-reduction/screenshots/` (each must be at least
10 kB). With `--build` it also runs `scripts/build_desktop.py --smoke-test`.

## Packaging smoke test

`scripts/build_desktop.py --smoke-test` builds with PyInstaller into
`~/Library/Caches/idtims-reduction/<checkout hash>/` (never inside the
repository), then runs the frozen app offscreen: `--export` for the same three
windows plus the Review step of the BSU template (reduced, z3 switched off) (each PNG at least 10 kB) and `--verify-reduction
tests/data/synthetic_snapshot.json`, which reduces the bundled synthetic example inside the
frozen app and compares every number at rel 1e-12. `--no-build` re-runs the
smoke test on the last build; `--clean` removes the build directory.

The smoke test also runs the source app with `--save-project` into its cache
folder, opens that project in the frozen app and captures Export (step 8).
The hidden `--print-engine-fingerprint` flag computes the fingerprint twice in
one process; smoke requires non-empty, equal fingerprints and `frozen: true`.
The source and frozen fingerprints may differ (source bytes versus PYZ bytes);
opening such a project displays an inline recomputation note.

## Project and autosave contract

`idtims_app.project` owns the Qt-free v1 format; the engine stays unchanged.
Top-level keys are `format`, `version`, `fractions_csv`, `no_oxide_confirmed`,
`settings`, `covariance_mode`, `include`, `review`, `sources`, `app_version`,
`engine_version`, `engine_fingerprint`, and `origin` (reserved in v1, null or the
`idtims database link` object with `format_version: 1`; see APP_SPEC §3.2).
The embedded contract CSV uses full-precision input text; confirmed spike
names/types live in that table. `sources` records import names and SHA-256 at
import time. `review` holds the weighted-mean date, concordia mode and Th toggle.
No results, plot ranges or other transient widget state are stored. Reopening
always reduces the embedded inputs. Saves use a same-directory temporary file,
flush/fsync and `os.replace` with cleanup on failure.

Source fingerprints hash sorted relative `.py` paths, a NUL separator and the
source bytes of `IDTIMS_UPbRPy`. Frozen fingerprints hash sorted engine PYZ
entry names and their raw extracted bytes. No code object is re-marshalled.
Scientific dirty tracking hashes embedded inputs, confirmations, settings,
covariance mode, include decisions and review choices; zoom/pan is view-only.

`tests/test_database_link.py` uses `tests/data/synthetic_database_link.fractions.csv`: two
linked fractions (single-source and a two-source fragment with empty list entries)
and one unlinked fraction, with a made-up server and UUIDs. It covers numeric
chemistry columns, source-list issues, complementary hand-off merging, latest
offset-aware read time, other metadata conflicts, mixed-server refusal, exact
master/unassigned spike selection, unchanged notebook results without opt-in,
explicit notebook opt-in, publication columns without UIDs, and per-fraction
confirmation gates. A synthetic public/master calibration keeps the exact-key
test independent of an installed public registry; the registry tests also exercise
the actual optional public checkout. Missing keys never fall back. An explicit
project version conflict blocks unconfirmed proposals; a confirmed key wins for
its fraction after later project version changes.

Origin tests round-trip linked projects and confirmation times, reject unknown
origin formats/newer versions, and require re-confirmation after embedded spike
key or spike-version UID changes. Unlinked projects keep null origins and project
version 1. `tests/test_gui_database_link.py` checks the Tracer composition/Confirm
action, reduction gate, Review capsule/chemistry/source cells and database marker
tooltip offscreen at 1512×982 and 1024×640. Neither path uses a database connection.

After scientific edits, a two-second single-shot QTimer snapshots the document
on the GUI thread and queues atomic writes on a single background executor.
Sidecars live in `$IDTIMS_AUTOSAVE_DIR` or `~/<branding.SLUG>/autosave/`, named
`<stem>-<sha1 of resolved absolute path, first 10 hex>.idtr`; untitled documents
use a session UUID. A newer sidecar differing scientifically is offered inline
on project open, with Restore/Discard. Restore recomputes; Save removes the
sidecar, including after any in-flight write. Autosave errors appear inline.

Required Phase 1 screenshots are `app_export_template2535_1280x800.png` and
`app_export_SYNTHETIC_diagnostic_1280x800.png` in `docs/screenshots/`. Export provides a
horizontally scrollable grouped preview and scrollable footnotes; the diagnostic
note appears first in the preview and exactly once in saved notes. BSU CSV notes
follow one blank row; XLSX notes follow the data with merged header groups.

## UI panel round

`tests/test_gui_panels.py` runs offscreen with a temporary QSettings file and
isolated autosave folder. It checks every workflow step at 1280×800, 1512×982,
1440×900 and 1024×640; full-area maximise and exact restore on every work panel;
header double-click, Cmd/Ctrl+Shift+Return, focus and pointer targeting; Esc
being delivered normally outside a maximised panel; per-handle and View reset;
table hiding without a change in plot proportions; saved sizes on a new window
(including closing while maximised or with the table hidden); rail preferences;
short ease-out animation and both environment and Qt reduced-motion paths.

The 40-long-ID fixture is generated by `scripts/ui_round_support.py`, following
`docs/screenshots/variants/README.md`. It checks both frozen columns, selection
and vertical scroll synchronization through the last row, known-failure drawer
behavior, and exact equality with `dates.sample_dates` for each date kind and
two include sets. A separate test distinguishes a new blocking issue from the
same issue being refreshed, including a second problem on the same fraction.

`tests/test_gui_rail.py` checks expanded defaults at 1280×800 and 1512×982 in
light and dark (comparing row painting with elision disabled to verify every
default label is whole), native handle dragging and its 200–360 px bounds,
double-click width reset, width and mode restoration in new windows, both toggle controls,
and automatic collapse below 1100 px only when no explicit choice exists.
The compact rail stays fixed at 84 px with its divider disabled. Expanded rows
elide to the right and expose the full numbered label in their tooltip.

`View > Reset Layout` restores panel proportions, the expanded rail width needed
for the longest numbered label at the current font (including icon and styled
padding, clamped to 200–360 px), and automatic rail mode. Double-clicking the
rail divider also restores this measured width. The unsaved default adapts to
the 11 px laptop font below 1400 px and the 12 px font on wider windows; a saved
dragged width stays unchanged across these font bands.
QSettings `layout/rail_width_v1` stores the dragged
expanded width; `layout/rail_compact_v2` stores only explicit toggle/menu choices,
which win over window width across launches. The old `layout/rail_compact_v1`
key is deliberately ignored: the forced-compact era could leave laptops with
saved compact mode, hiding labels by default. Reset removes both mode versions
and the saved width. Layout preferences are user-only values under `layout/`;
maximisation is session-only and never enters the project or reduction inputs.

The UI round screenshot set (all 15 existing 1280×800 images and the four
additional Review views) can be regenerated with
`.venv/bin/python scripts/render_ui_round.py`. Use `--only IMAGE_STEM ...` for
visual iteration. See [the handoff](ui-round.md) for test counts, changed files,
before/after pairs and the final inspection record.
