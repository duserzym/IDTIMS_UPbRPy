# Installed icon: six labelled Pb measurement bars (2026-11-19)

Yiming requested six measurement bars in mass order **202, 204, 205, 206,
207, 208**, with coloured mass numbers above them. The natural Pb isotopes
are 204/206/207/208; 202 and 205 represent the added synthetic ET2535 tracer
isotopes. Heights are illustrative: 206 is tallest, 204 smallest, 202/205
medium-tall, and 207/208 retain their former heights.

The suite tile, card, grid, axes, drop shadow, flat-topped `peak()` paths and
0.85 gradient fill opacity retain the existing drawing language. Six bars
use 40-unit even spacing and 22-unit widths within the x 128–384 plot.
The 206 height is shortened from 228 to 224 units to leave label clearance.
Mass labels are centred, bold SVG `<text>`, 28 units (7 px at 128 px), in
the corresponding dark stroke colour, with the font stack
`Helvetica Neue, Helvetica, Arial, sans-serif`. True-size and 1024 px
renders were inspected: all six labels fit within the card, clear of the
axes, adjacent bars and each other.

| Mass | Colour | Gradient, light → dark | Stroke and label |
| --- | --- | --- | --- |
| 202 | Amber/gold (new) | `#f5d58a` → `#ce941f` | `#805a10` |
| 204 | Purple (unchanged) | `#d3b4e3` → `#9558b2` | `#5e3378` |
| 205 | Teal (new) | `#9cded8` → `#209b92` | `#12645f` |
| 206 | Blue (unchanged) | `#a8b8f2` → `#4063d8` | `#24408f` |
| 207 | Red (unchanged) | `#efa39d` → `#cb3c33` | `#8f2a24` |
| 208 | Green (unchanged) | `#a9dd9c` → `#389826` | `#1f5f16` |

## Small-size rule and review

- **128/256/512/1024 px:** labelled `pb_peaks/icon.svg` master.
- **32/64 px:** `pb_peaks/icon_small.svg` drops only the six text elements.
- **16 px:** `pb_peaks/icon_tiny.svg` also omits the grid, widens bars from
  22 to 24 units and reduces their dark outlines from 4 to 2 units, keeping
  all six colours, mass order, heights, flat tops, tile, card, axes and shadow.

The cut-off is **below 128 px**. At true 64 px the 28-unit font becomes
3.5 px and the numbers are specks; at 32/16 px they are still less legible.
At 128 px the 7 px labels read individually. At 16 px the plot is only
8 pixels wide: the six bars reduce to coloured marks (especially short
204), so the wider fills and thinner outlines reduce muddy dark blending,
and removing the grid clears background noise. Individual mass identification
is not possible at that size. These decisions follow true-size inspection on
both light and dark backgrounds, not magnification alone.

`pb_peaks/final_small_sizes.png` compares the preserved **previous four
peaks** against the **installed six bars** at **16, 32, 64 and 128 px**,
true size and **8× nearest-neighbour**, on light and dark backgrounds.
Open at 100% to assess native pixels; the sheet is 4552 × 2800 px.
The large preview is `pb_peaks/icon_1024.png`.

## Regeneration and packaging

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python tools/make_pb_peaks_icon.py
```

The tool writes the three SVG renditions, seven directly rendered PNGs,
ten-file Apple iconset, ICNS and comparison sheet to `pb_peaks/`, and
copies the master, seven PNGs and ICNS to `src/idtims_app/assets/app_icon*`.
The old four-peak master is a preserved input, never overwritten by the tool.
The historical v2c generator remains unchanged. Suite template attribution
is retained in the tool header.

Renderer: local `/opt/homebrew/bin/rsvg-convert` 2.62.1 (Cairo 1.18.4).
SVG text renders correctly through Pango; the suite shadow is preserved.
As in the earlier sandbox runs, `iconutil -c icns` reports `Invalid Iconset`;
the existing `make_app_icon.package_icns` fallback packages ten PNG chunks
and independently decodes all ten through Qt. No packaging code changed.
The app's multi-size PNG-backed QIcon and bundle paths remain wired through
`branding.py`; 16/32/64 px selections use the appropriate small rendition.

Validation: `.venv/bin/python scripts/run_tests.py quick` completed with
**421 passed, 33 warnings, 9495 subtests passed** (194.68 seconds).
The focused branding run passed **10 tests**, preserving all previous coverage
and extending native QIcon selection checks to 64/128 px and the small-rendition
check to 64 px. All seven current PNG hashes are pinned; historical v2c hashes
are unchanged. Ruff passed on the tool and both other changed Python files
(`ruff check --no-cache --target-version py311`). `git diff --check` passed.
A second generator run reproduced every output, including the comparison
sheet, byte-for-byte. The preserved four-peak SVG matches the previous master
exactly. `sips` recognizes the ICNS as 1024 px; `iconutil -c iconset` exports
it successfully. No application bundle was built, no visible windows were
opened, and no staging, commit or push was performed. The protected spreadsheet
and notebook still match their starting SHA-256 checksums.

---

# Historical icon: four flat-topped Pb peaks (2026-11-19)

This was the initial choice, superseded by the six labelled bars above.
The original master is preserved as `pb_peaks/icon_four_peaks.svg`; the current
comparison sheet re-renders it directly. The old PNGs at `pb_peaks/icon_*.png`
and the installed assets have been replaced. The following records describe
the four-peak delivery and its validation at the time.

Yiming chose `2-mass-peaks.svg`: purple 204 (small), blue 206 (tall), red 207,
and green 208, on the shared suite graph tile. This identifies IDTIMS with a
Pb data graph; the ribbon v2c icon moved to filament on 2026-11-19. The app
name remains a working name. The rejected noisy, repeating peak-hopping
candidate is not used.

Regenerate the chosen artwork, seven PNGs, ten-file Apple iconset, ICNS and
comparison sheet offline, without building an application:

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python tools/make_pb_peaks_icon.py
```

The source is `b_peaks()` with only its required helpers/constants copied
from `lab-builds/filament-icon-candidates-2026-11-19/make_candidates.py`.
Suite template attribution is retained in the tool header. Output lives in
`pb_peaks/` and is copied to `src/idtims_app/assets/app_icon.*` and
`app_icon_{16,32,64,128,256,512,1024}.png`. Only unused SVG definitions
were dropped; the geometry, gradients, opacity, grid, axes and shadow are
unchanged. Every generated PNG was verified byte-for-byte against a direct
render of the read-only `2-mass-peaks.svg` reference.

Reference SVG SHA-256: `6dd40f14d1a1432cbc110a67eb9ba1c3a891615de3b007a9550998391dc5c7a9`.
Installed assets are checked against the chosen exports in
`tests/test_app_branding.py`, which pins all seven new PNG SHA-256 values.
The old v2c large-PNG hash test still checks the preserved historical files.

## Small sizes and renderer

`pb_peaks/final_small_sizes.png` compares source and installed artwork at true
16/32 px and 8× nearest-neighbour on light and dark backgrounds. All four
peaks are distinct at 32 px. At 16 px, blue/red/green remain distinct and the
small purple 204 peak is a short mark just above the baseline. The graph is
recognizable on both backgrounds, so no small SVG variant or added detail
is used. Every size is rendered directly from the same approved master,
rather than downscaled from a large PNG.

Renderer: local `/opt/homebrew/bin/rsvg-convert` 2.62.1 (Cairo 1.18.4), which
preserves the suite SVG drop shadow. This tool requires that renderer and
does not substitute QtSvg output. On this run, `iconutil -c icns` again
reported `Invalid Iconset`. The unchanged `make_app_icon.package_icns`
fallback wrote ten standard/Retina PNG chunks and independently decoded all
ten through Qt. The tests accept both this fallback and Apple's ARGB small
entries; all iconset filenames, dimensions and RGBA format remain checked.

## Application and packaging

Existing `branding.ICON_PATH`, `ICON_PNGS` and `ICNS_PATH` now resolve to the
new assets. The application, windows and rail already use the multi-size
PNG-backed QIcon; tests verify native 16/32 px selection. The spec collects
the entire assets directory and passes the ICNS to EXE and macOS BUNDLE.
There is no ICO path in the current IDTIMS packaging. No bundle was built.

Validation: `.venv/bin/python scripts/run_tests.py quick` completed with
**421 passed, 33 warnings, 9495 subtests passed**. Ruff passed on every changed
Python file. `sips` recognizes the fallback as 1024 px ICNS, and Apple
`iconutil -c iconset` successfully exports all ten representations.
`git diff --check` passed. The protected spreadsheet and notebook were untouched.

The v2c generator and review assets below remain historical sources. Its
`--install` command would restore the old ribbon and is not the regeneration
command for the current IDTIMS icon.

---

# Historical icon: v2c colour rays — moved to filament on 2026-11-19

The former application icon is preserved in `filament_v2/filament_v2c/`. Earlier review
notes in this directory describe the selection history; the name remains
a working name. Regenerate the chosen artwork and installed assets offline:

```sh
.venv/bin/python tools/make_app_icon.py --install
```

The generator is the source of truth. `icon.svg` is the unchanged large
master. `icon_small.svg` changes exactly three SVG attributes: ray stroke
width 3 → 16 units, left endpoint x 221 → 204, and right endpoint x 291 → 308.
Only the 16 and 32 px PNGs use this rendition. All tile, card, grid, shadow,
bead, post and ribbon definitions remain the same. The large master and all
64/128/256/512/1024 px PNGs were compared against the pre-change files and are
byte-identical. Tests retain the original large-PNG SHA-256 values.

The delivered PNGs use the existing local `rsvg-convert`, preserving the SVG
shadow. A second `--install` run reproduced every generated asset and the
comparison sheet byte-for-byte. The existing QtSvg/numpy fallback remains
available, but a different renderer need not produce identical PNG bytes.

`final_small_sizes.png` compares installed and previous v2c artwork at true
16/32 px and 8× nearest-neighbour magnification on light and dark backgrounds.
The previous renders are recreated from the unchanged large master, with
the renderer first verified to reproduce the original PNG bytes. Visual
inspection shows separate red, green and blue rays at 32 px. At 16 px these
reduce to three distinct marks above the warm bead; the green is paler.

## ICNS diagnosis and fallback

The iconset has exactly the ten Apple filenames, correct physical pixel
dimensions, and PNG IHDR values of 8 bits per channel and colour type 6
(RGBA). No SVGs, extra files or 16-bit PNGs are present.

On this machine (macOS 27.0.1, build 26A434), `/usr/bin/iconutil -c icns`
returns exit 1 and `Invalid Iconset` for:

- The original v2c iconset.
- A fresh ten-file, solid-colour RGBA control iconset produced by Qt.
- The final iconset with the refined small artwork.
- An iconset exported by `iconutil` itself from the delivered ICNS.

The reverse conversion succeeds:

```sh
iconutil -c iconset src/idtims_app/assets/app_icon.icns \
  -o /private/tmp/idtims-roundtrip.iconset
```

`sips` also fails when encoding a standalone PNG as ICNS (exit 13), while PNG
encoding and ICNS reading succeed. These observations isolate the failure
to the local Apple ICNS encoding path, rather than the iconset names, PNG
dimensions or format. The precise OS/sandbox cause is not established, and
successful `iconutil -c icns` conversion is not claimed.

The generator therefore writes the permitted pure-Python ICNS fallback:
big-endian `icns` header and ten PNG chunks. Standard PNG chunk names are
`icp4`/`icp5` for 16/32 px and `ic07`–`ic14` for the remaining standard/Retina
representations. Qt independently reads all ten images at the expected
sizes; `sips` recognizes the file as ICNS with a 1024 px maximum size; and
`iconutil -c iconset` accepts it and exports the complete ten-file iconset.

## Application and packaging

`branding.py` provides `ICON_PATH`, `ICON_PNGS` and `ICNS_PATH`. The application,
windows and rail use the PNG-backed multi-size QIcon. The rail requests 32 px
directly. The spec passes `ICNS_PATH` to both EXE and BUNDLE and already
collects the entire assets directory; setuptools package data includes SVG,
PNG and ICNS. The installed PyInstaller BUNDLE implementation was inspected:
it copies the chosen ICNS to `Contents/Resources/app_icon.icns` and sets
`CFBundleIconFile` to `app_icon.icns`.

No packaged application was built. The supervisor performs the build and
bundle audit. No engine edits, network access, package installation or git
commit/push/checkout/stash/reset were performed. The two protected untracked
files were left untouched.

Validation command: `.venv/bin/python scripts/run_tests.py quick`.
Result: **389 passed, 33 warnings, 9495 subtests passed** (92.22 seconds).
This includes nine new branding tests. `git diff --check` also passed.

## Update: shipped ICNS comes from iconutil

Outside the Codex sandbox, `/usr/bin/iconutil -c icns` accepts the same ten-file iconset and
round-trips it with `iconutil -c iconset`. The earlier "Invalid Iconset" was a sandbox
limitation, not a fault in the iconset. The shipped `src/idtims_app/assets/app_icon.icns`
(and the copy in `filament_v2c/icon.icns`) is therefore Apple's own output:
- 16 and 32 px are stored as ARGB (`ic04`, `ic05`);
- the larger sizes are PNG.

`tools/make_app_icon.py` already prefers iconutil. It falls back to its Python writer only where
iconutil fails. The branding tests check the entries by size rather than by bytes.
