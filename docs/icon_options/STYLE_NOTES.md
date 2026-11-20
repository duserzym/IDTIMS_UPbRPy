# Filament v2: shipped suite style audit

Reviewed locally on 2026-11-14, on branch `app`. The reference PNGs were opened
as images, including Studio's native 16/32 px and the other apps' 32 px exports.
The SVGs and generators below were read. No sibling repository was modified.

## Sources and common ancestry

Paths below are relative to `~/Github/`:

- `bracketeer/src-tauri/icon/make_icon.py` and `src-tauri/icons/icon.png`.
- `UPbRPy/regenerate_icons.py`, `GUI/icon.py`,
  `GUI/assets/icons/make_icon.py`, `GUI/assets/icons/upbrpy_studio.svg`, and
  `GUI/assets/icons/upbrpy_zircon.iconset/` (despite the older directory name,
  these PNGs contain the current Studio signal-plot icon).
- `upblab/src-tauri/icons/icon.svg` and `icon.png`.
- `grainatlas/tauri/assets-icon.svg`, `tauri/src-tauri/icons/icon.png`, and
  `tauri/icon/zircons.py`.

This is a shared template, not merely a resemblance: Studio's `make_icon.py`
says its HEAD, palettes, and projection helpers were copied from grainatlas's
`zircons.py`; bracketeer's generator explicitly cites that same HEAD. UPb Lab's
shipped SVG repeats the tile, paper, grid, gradient, and shadow definitions.
`tools/make_app_icon.py` copies the needed values with source comments; it does
not import or execute anything from another repository.

## Shared geometry, palette, and lighting

All measurements use the actual **512 × 512** SVG coordinate system.

| Feature | Shipped rule | Fraction of full icon |
|---|---|---|
| Outer tile | x/y 36, width/height 440, radius 88 | inset 7.031%; width 85.938%; radius 17.188% of canvas / 20% of tile |
| Outer frame | `#d9e1ec`, width 10, centered on tile edge | 1.953%; visible straight-edge inset is 31 = 6.055% |
| Tile gradient | `#ffffff` → `#e9eef5`, `x2="0.8" y2="1"` | upper left to lower right |
| Paper card (Studio / UPb Lab) | x/y 96, 320 square, radius 22 | inset 18.75%; width 62.5%; radius 4.297% of canvas / 6.875% of card |
| Paper frame | `#cbd5e1`, width 3 | 0.586%; card is 60 units inside tile path |
| Paper fill | `#ffffff` → `#f1f5f9`, same gradient direction | very restrained shading |
| Plot grid | `#e2e8f0`, width 2; lines at 160/224/288/352, extents 128–384 | 0.391%; 64-unit spacing |
| Content shadow | dx 0, dy 9, Gaussian sigma 10, `#0f1b2d` at 25% | offset 1.758%; blur 1.953% |
| Subject outlines | crystal silhouettes 4 at 80%; face edges 2.6 at 55%, round joins | 0.781% and 0.508% |
| Plot structure | axes `#334155`, width 7, round caps/joins | 1.367% |

The shadow belongs to the **whole content group**, not the outer tile. In the
paper designs the opaque card supplies most of its silhouette. These are pale,
opaque tiles, without a dark outer rim, an inset glass panel, a glossy upper
lip, or a large specular flare. Subject lighting comes from upper-left light
faces and darker right/lower faces. The crystal generators use light vector
`(-0.45, -0.8, 0.55)`, with discrete face shading, rather than photoreal metal.

The recurring accent family is blue `#4063d8`, red `#cb3c33`, green `#389826`,
and purple `#9558b2`. Blue gradients start at `#a8b8f2`; red gradients start
at `#efa39d`. Corresponding subject edges include blue `#24408f`, green
`#1f5f16`, red `#8f2a24` / `#7f1f1a`, purple `#5e3378`, and amber `#5b2a12`.
Laser effects use `#7dd3fc` / `#38bdf8` radial glows and `#0ea5e9` soft strokes,
with restrained blue rings. No typography is embedded in the app marks.

## Differences between the four real icons

| App | Inner panel and subject | Stroke / light differences | Approximate subject footprint, excluding shadow |
|---|---|---|---|
| Studio | Paper card, fine grid, signal plot, blue integration window, upper-right blue zircon | 9-unit red/green/purple signals; blue window at 14%, 3-unit dashed edges at 55%; 4/2.6 crystal edges; small cyan laser glow | Plot + crystal about 261 × 262: 82% of card width/height |
| UPb Lab | Same paper, border, and grid; concordia with two ellipses and green zircon | Curve `#4b4b4b`, width 10; axes 7; ellipses 4 with 45–50% fills; crystal edges scaled by its 1.35 transform | About 265 × 260: 83% × 81% of card |
| grainatlas | Same 96/96/320/r22 panel geometry, but **no 3-unit paper border**; four clipped SEM-like tiles, white seams; five crystals, spot, scale bar | SEM gradients `#dfe6f7` → `#b9c6ec` and `#e9edf9` → `#c9d3f0`; 3-unit white seams at 90%; central amber crystal, four colored companions; scale `#1e293b` | Ensemble about 287 × 287: 90% of panel; main crystal itself about 153 × 204 |
| bracketeer | **No inner card, grid, or paper shadow**; blue brackets and RGB dots directly on shared outer tile | 28-unit blue brackets (5.469% of canvas), square caps and rounded joins; dots r24; the content itself casts the shared shadow | Brackets about 308 × 220: 70% × 50% of outer tile; no card denominator |

## What really happens at 16 and 32 px

The inspected primary generators do **not** switch to special 16/32 px subject
drawings. Studio renders the same SVG directly at every target size;
`regenerate_icons.py` prefers local `rsvg-convert` to preserve filters. Its
Qt fallback warns that QtSvg ignores filters. `GUI/icon.py` has an older navy
crystal fallback with a `size >= 48` detail branch, but that fallback is not the
shipped Studio master and was not used as the style reference here.

At 32 px, Studio's signals and Lab's curve survive, but facets and laser rings
merge. At 16 px, their grids mostly disappear through rasterization and the
subjects become compact colored silhouettes. Grainatlas's fine seams/facets
merge at small sizes; the amber diagonal and colored companions persist.
Bracketeer's pre-existing simple brackets and dots remain especially clear.
There is no evidence in these generators of a deliberate small-size redesign.

The sheet uses Studio's actual iconset files at all four sizes. For the three
Tauri apps, 32/128/512 px use their shipped PNGs; their 16 px sheet cells are
smooth reductions of the shipped 32 px PNG (not claimed to be a separately
shipped native 16 px asset). The 4× samples are nearest-neighbour magnifications
of those final 16/32 px rasters. View the sheet at 100% for true-size judgment.

## Dark variants

No dark **application-icon** variant was found among the inspected source
masters, generators, and packaged icon files for any of the four. Studio does
have dark UI-control SVGs and an older dark fallback renderer; these are not
alternate shipped app icons. Both halves of the sheet therefore use identical
light icon artwork on different backgrounds, not invented dark app variants.
The new filament follows that rule too.

## Filament choices and recommendation

**Recommend `filament_v2a` (the fine paper grid).** The root `filament_v2/icon.svg`
and PNG/iconset exports are byte-for-byte copies of that variant. `filament_v2b`
changes only the grid: its paper is plain. Both are shown in the one family
sheet because the plot-oriented paper and bracketeer's ungridded treatment
are both reasonable precedents. The grid makes the link to the two reduction
apps clearest at 128/512 px; the variants converge visually at 16/32 px.

The new subject is a broad neutral rhenium ribbon with a visible upper surface,
front thickness, and downturned ends over two posts. It uses the shared
generator's neutral GREY colors `#e3e9f0`, `#c9d3df`, and `#a9b6c5`, with the
suite's `#334155` structural outline. Metal silhouettes use 4 units at 80%;
internal edges use 2.6 at 55%, matching the crystal hierarchy. A small red
sample bead uses `#efa39d` → `#cb3c33`, `#8f2a24` outline, and `#f6d29a` warm
highlight (from the shared amber palette). Its limited halo and faint blue ion
beam follow the suite's restrained glow vocabulary. No support rail, heavy
navy cartoon border, glass effect, or unrelated copper/teal theme was added.

Hardware is about 242 units wide (76% of card) and 190 high (59%); the faint beam
extends the full subject to roughly 244 high (76%). The open arch is deliberate
negative space that separates the supports at small sizes. After inspecting
the first family sheet, the ribbon center and bead were raised 20 units to
reduce bottom-heavy placement. The final sheet was reopened and visually
checked. At 32 px the bent strip and paired posts read; at 16 px they reduce
to an arch with two legs and a small warm central pixel. The weak beam and grid
mostly vanish naturally. All requested sizes are rendered from the same SVG,
matching the shipped icons' behavior; no unsupported small-size rule is claimed.

## Files, regeneration, and verification

Run offline with the existing environment:

```sh
.venv/bin/python tools/make_app_icon.py
```

- `filament_v2/icon.svg`: recommended editable master, 512-unit viewBox.
- `filament_v2/icon_{16,32,64,128,256,512,1024}.png`: transparent RGBA exports.
- `filament_v2/filament.iconset/`: ten Apple filenames including Retina slots.
- `filament_v2/filament_v2a/` and `filament_v2/filament_v2b/`: each variant's
  master, seven PNG sizes, and complete Apple iconset.
- `family_sheet.png`: one 2054 × 3490 comparison sheet, the four shipped icons
  followed by both filament readings, light and dark backgrounds, requested
  columns, and labelled nearest-neighbour 4× samples.

The local `/opt/homebrew/bin/rsvg-convert` rendered the delivered PNGs directly
at each target size, preserving the exact shared SVG shadow. The script also
has a QtSvg/numpy fallback that composites the same shadow separately instead
of silently dropping it. It never imports the scientific package or app code.

All 21 PNG exports and 30 iconset slots have the requested dimensions and alpha;
iconset slots match their source PNG bytes. The selected root exports match
v2a. SVG validity, repeatable generation, and the local fallback were checked.

`iconutil` **is present** at `/usr/bin/iconutil`. An optional packaging attempt
with `--icns` returned exit 1 and "Invalid Iconset"; no ICNS was produced. The
ten Apple filenames, RGBA PNG encoding, and all pixel dimensions were checked
independently and are correct. The cause of iconutil's rejection in this
environment is not established; successful ICNS packaging is **not verified**.
The requested source iconsets are supplied for packaging in the target build
environment. The normal generation command does not invoke iconutil.

Changes are limited to the review generator, this note, `filament_v2/`, and
the specifically requested `family_sheet.png`. Branding and installed assets
remain untouched pending user approval. No app code was edited, no network or
package installation was used, and no git commit/push/checkout/stash/reset ran.

## Colour readings: v2c and v2d

Added locally on 2026-11-14. **v2a is preserved byte for byte**, including its
SVG, seven PNGs, and iconset; the selected root exports, v2b, and original
`family_sheet.png` are also unchanged. Both new readings keep v2a's tile,
frame, card, grid, content shadow, hardware geometry, metal-grey ribbon, and
4/2.6-unit subject outlines. Every size uses the same artwork.

- **v2c:** blue posts use `#a8b8f2` → `#4063d8`, edge `#24408f`, and light
  faces/highlights `#c3cff6`, from Studio/grainatlas's blue subject palette.
  The bead grows from 18 × 15 to 23 × 19 radii, with an amber-orange radial
  core (`#f6d29a`, `#eab25a`, `#c8683a`), a soft 48-unit halo, and the suite's
  amber edge `#5b2a12`. These warm hues come from grainatlas/Studio's shared
  crystal `PALETTE`. Three thin, 3-unit diverging rays use bracketeer's exact
  dot hues: red `#cb3c33`, green `#389826`, blue `#4063d8`. Studio's signals
  also use that red and green, with its crystal/window using the same blue.
- **v2d:** identical blue posts; v2a's red bead and halo remain unchanged.
  One amber beam uses `#eab25a` and `#f6d29a` with transparent radial/linear
  falloffs, giving a quieter glow without a filter-dependent blur.

`preview_sheet.png` is **2054 × 4790**: seven size-grid rows, followed by
three mock Dock rows on both light and dark translucent strips. Each Dock
contains the four shipped icons and one filament reading at 64 physical
pixels, with 154-pixel centre spacing. Studio's native 64 px source is its
`icon_32x32@2x.png`; its Retina density metadata is normalized in memory so
it draws at the correct size. The three Tauri icons use smooth reductions
of their shipped 128 px PNGs. The size grid keeps the original sheet's
source choices, native-size samples, and nearest-neighbour 4× enlargements.

The complete sheet and full-resolution detail crops were visually reviewed;
the first Dock pass exposed Studio's half-size Retina drawing, which was
corrected. At 32 px, v2c's arch, blue posts and warm bead read clearly; the
three rays survive as faint separated coloured marks rather than crisp lines.
At 16 px those rays mostly merge/disappear. v2d's amber beam is subtle even
at 128 px and largely disappears at 16/32 px; the blue posts and red bead
remain legible. In the 64 px Dock, v2a is the most neutral, v2c has the most
colour and an upward accent, and v2d adds suite-blue weight with less activity.

The normal regeneration command above now writes only `filament_v2c/`,
`filament_v2d/`, and `preview_sheet.png`, reading the preserved v2a PNGs.
Each new folder mirrors v2a with `icon.svg`, all seven requested PNG sizes,
and the ten iconset PNG aliases. Delivered PNGs use local `rsvg-convert`;
dimensions, alpha, SVG validity, iconset copies, unchanged prior outputs,
and repeatable generation were checked. No ICNS packaging was attempted
for this addition, and no installed branding, app assets, or packaging changed.
