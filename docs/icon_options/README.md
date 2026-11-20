# ID-TIMS app icon options

Review-only artwork. No installed app icon or branding files are changed.

Regenerate offline from the repository root:

```sh
.venv/bin/python tools/make_icon_options.py
```

Requires the existing environment's numpy and PySide6/QtSvg; no downloads.
The script sets Qt to offscreen, writes SVGs from code, and renders each PNG
directly at its target resolution using QSvgRenderer into a transparent QImage.
It also regenerates this README and the contact sheet. Output is confined here.

## Options

- **a — Realistic concordia:** copper curve, two tight teal precision ellipses,
  navy axes and faint grid, with a frosted tile and softly shadowed card.
- **b — Small-size concordia:** the same computed curve with thicker strokes,
  one ellipse, and no grid or ticks. Best concordia candidate at 16–32 px.
- **c — TIMS filament:** a broad rhenium ribbon bent over two posts, a warm
  sample bead and a faint rising teal ion beam. The filament was chosen over
  three beakers because its single bridge silhouette, paired supports and
  central bead remain distinct at 32 px; three tiny vessels would need more
  repeated edges and can read as a generic bar chart. This is a schematic,
  not an engineering drawing; the ribbon uses warm neutral metal shading.

Each composition has light and dark versions. Dark versions retain navy
outlines, with pale blue keylines around the axes/support rail for contrast.
No zircon/crystal appears; the copper/teal palette distinguishes these options
from UPb Lab. The suite references informed the framing, not traced artwork.

## Scientific construction

Wetherill concordia, with t in **years** and decay constants in **yr⁻¹**:

```text
x = ²⁰⁷Pb/²³⁵U = exp(λ235 × t) − 1
y = ²⁰⁶Pb/²³⁸U = exp(λ238 × t) − 1
λ235 = 9.8485e-10 yr⁻¹
λ238 = 1.55125e-10 yr⁻¹
```

Both constants are imported from `IDTIMS_UPbRPy.constants`, not hard-coded in
the generator. The age range is **0–4.0 Ga** (0–4,000,000,000 years).
The ratio ranges are x = 0–50.38775939 and y = 0–0.85985774.
Both axes are mapped **linearly**, independently normalized to these maxima:

```text
screen_x = 128 + 258 × x / x_max
screen_y = 384 − 250 × y / y_max
```

Both curves are identical 641-point polylines at uniform time intervals,
using numpy.expm1 for numerical precision. There is no arbitrary Bezier fit.
In data coordinates the curve is concave down: dy/dx is proportional to
exp((λ238 − λ235) × t), and therefore decreases with age.
SVG's downward y axis reverses the sign of the displayed second derivative.
Ellipse orientations follow the analytic tangent after axis scaling.
The ellipses are visual precision glyphs, not measured errors or a stated
confidence level: a has glyphs at 1.9 and 3.25 Ga, b has one at 2.8 Ga.

## Files and review

- `a_light.svg` … `c_dark.svg`: six editable vector options (512-unit viewBox).
- `<variant>_<theme>_<size>.png`: transparent renders at 16, 32, 128, 512 px.
- `contact_sheet.png`: light and dark panels, each with variant rows a/b/c and
  columns 16/32/128/512. Every original is shown at true pixel size; 16 and
  32 px are also shown separately at 4× using nearest-neighbour scaling.

View the contact sheet at 100% to assess the true-size samples. Its native
dimensions are 2054 × 1814 px; previews in other tools may scale the whole sheet.
No selection or installation is performed by this script.
