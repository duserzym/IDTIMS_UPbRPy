#!/usr/bin/env python3
"""Build review-only ID-TIMS icon options with local numpy and QtSvg.

Run from any directory with this repository's .venv/bin/python. The installed
application icon is never read or modified. All output goes to docs/icon_options.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import sys

# Importing the scientific package must not leave bytecode outside our output.
sys.dont_write_bytecode = True
os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
from IDTIMS_UPbRPy.constants import lambda_235, lambda_238
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen
from PySide6.QtSvg import QSvgRenderer


OUT = ROOT / "docs" / "icon_options"
SIZES = (16, 32, 128, 512)
MAX_AGE_YR = 4.0e9
SAMPLES = 641
PLOT_LEFT, PLOT_BOTTOM = 128.0, 384.0
PLOT_WIDTH, PLOT_HEIGHT = 258.0, 250.0
X_MAX = float(np.expm1(lambda_235 * MAX_AGE_YR))
Y_MAX = float(np.expm1(lambda_238 * MAX_AGE_YR))

PALETTES = {
    "light": {
        "tile_top": "#fcfdff", "tile_bottom": "#e8eef5", "border": "#d5dfeb",
        "card_top": "#ffffff", "card_bottom": "#f2f6fb", "card_edge": "#cbd7e5",
        "navy": "#23394f", "axis_halo": "#23394f", "grid": "#d8e3ef",
        "copper": "#e57c3b", "copper_high": "#ffd29a", "teal": "#168e98",
        "ellipse": "#b5ece8", "post": "#9bb1c7", "post_top": "#e5eef6",
        "ribbon": "#c5bdaf", "ribbon_high": "#fff0d6", "shadow": "#253b53",
    },
    "dark": {
        "tile_top": "#293b51", "tile_bottom": "#162337", "border": "#51667e",
        "card_top": "#2c4057", "card_bottom": "#203147", "card_edge": "#607892",
        "navy": "#10283f", "axis_halo": "#a5bed8", "grid": "#50667f",
        "copper": "#ffad70", "copper_high": "#ffe5b4", "teal": "#53d4d1",
        "ellipse": "#75e1da", "post": "#8faac4", "post_top": "#ccdae7",
        "ribbon": "#bdb7aa", "ribbon_high": "#fff0d6", "shadow": "#020b16",
    },
}


def point(age_yr: float) -> tuple[float, float]:
    """Linear, independently normalized Wetherill axes; SVG y points down."""
    x = float(np.expm1(lambda_235 * age_yr))
    y = float(np.expm1(lambda_238 * age_yr))
    return (PLOT_LEFT + PLOT_WIDTH * x / X_MAX,
            PLOT_BOTTOM - PLOT_HEIGHT * y / Y_MAX)


def tangent_angle(age_yr: float) -> float:
    dx = PLOT_WIDTH * lambda_235 * math.exp(lambda_235 * age_yr) / X_MAX
    dy = -PLOT_HEIGHT * lambda_238 * math.exp(lambda_238 * age_yr) / Y_MAX
    return math.degrees(math.atan2(dy, dx))


def frame(p: dict[str, str], grid: bool) -> list[str]:
    parts = [f'''<defs>
      <linearGradient id="tile" x1="0" y1="0" x2="0.8" y2="1">
        <stop stop-color="{p['tile_top']}"/><stop offset="1" stop-color="{p['tile_bottom']}"/>
      </linearGradient>
      <linearGradient id="card" x1="0" y1="0" x2="0.7" y2="1">
        <stop stop-color="{p['card_top']}"/><stop offset="1" stop-color="{p['card_bottom']}"/>
      </linearGradient>
      <linearGradient id="metal" x1="0" y1="0" x2="0" y2="1">
        <stop stop-color="{p['ribbon_high']}"/>
        <stop offset="0.45" stop-color="{p['ribbon']}"/>
        <stop offset="1" stop-color="{p['post']}"/>
      </linearGradient>
      <radialGradient id="glow">
        <stop stop-color="{p['copper_high']}" stop-opacity="0.65"/>
        <stop offset="0.45" stop-color="{p['copper']}" stop-opacity="0.24"/>
        <stop offset="1" stop-color="{p['copper']}" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="beam" x1="0" y1="1" x2="0" y2="0">
        <stop stop-color="{p['teal']}" stop-opacity="0.42"/>
        <stop offset="1" stop-color="{p['teal']}" stop-opacity="0.02"/>
      </linearGradient>
    </defs>
    <rect x="36" y="36" width="440" height="440" rx="88"
      fill="url(#tile)" stroke="{p['border']}" stroke-width="10"/>''']
    # QtSvg has no portable blur filter: nested low-opacity silhouettes give a
    # reproducible soft shadow without external image or SVG filter support.
    for spread in range(14, 0, -1):
        s = spread * 0.85
        parts.append(f'<rect x="{95-s:.2f}" y="{102-s:.2f}" '
                     f'width="{322+2*s:.2f}" height="{322+2*s:.2f}" '
                     f'rx="{25+s:.2f}" fill="{p["shadow"]}" opacity="0.018"/>')
    parts.append(f'<rect x="95" y="95" width="322" height="322" rx="25" '
                 f'fill="url(#card)" stroke="{p["card_edge"]}" stroke-width="3"/>')
    if grid:
        for pos in (192, 256, 320, 384):
            parts.append(f'<path d="M {pos} 127 V 385 M 127 {pos} H 386" '
                         f'fill="none" stroke="{p["grid"]}" stroke-width="1.5"/>')
    return parts


def concordia(p: dict[str, str], simplified: bool, dark: bool) -> list[str]:
    parts = []
    axis = "M 128 132 V 384 H 386"
    axis_width = 14 if simplified else 8
    if dark:
        parts.append(f'<path d="{axis}" fill="none" stroke="{p["axis_halo"]}" '
                     f'stroke-width="{axis_width+4}" stroke-linecap="round" '
                     'stroke-linejoin="round"/>')
    parts.append(f'<path d="{axis}" fill="none" stroke="{p["navy"]}" '
                 f'stroke-width="{axis_width}" stroke-linecap="round" '
                 'stroke-linejoin="round"/>')
    ages = np.linspace(0.0, MAX_AGE_YR, SAMPLES)
    coordinates = " ".join(f"{x:.4f},{y:.4f}" for x, y in map(point, ages))
    # Both variants use the very same sampled scientific curve, never a Bezier.
    for color, width in ((p["navy"], 28 if simplified else 16),
                         (p["copper"], 18 if simplified else 9)):
        parts.append(f'<polyline points="{coordinates}" fill="none" '
                     f'stroke="{color}" stroke-width="{width}" '
                     'stroke-linecap="round" stroke-linejoin="round"/>')
    # These glyphs indicate precision; they do not encode measured covariance.
    ellipses = ((2.8e9, 24, 9),) if simplified else ((1.9e9, 16, 5.5), (3.25e9, 18, 5.5))
    for age, rx, ry in ellipses:
        x, y = point(age)
        parts.append(f'<ellipse cx="0" cy="0" rx="{rx}" ry="{ry}" '
                     f'transform="translate({x:.4f} {y:.4f}) rotate({tangent_angle(age):.4f})" '
                     f'fill="{p["ellipse"]}" stroke="{p["navy"]}" '
                     f'stroke-width="{4 if simplified else 3}"/>')
    return parts


def filament(p: dict[str, str], dark: bool) -> list[str]:
    """A single warm rhenium ribbon bridge, two posts, bead and rising ions."""
    parts = [
        # Deliberately faint beam, widening upward from the sample bead.
        '<path d="M 249 250 L 226 135 Q 256 120 286 135 L 263 250 Z" '
        'fill="url(#beam)"/>',
        f'<path d="M 256 222 V 145" stroke="{p["teal"]}" stroke-width="6" '
        'stroke-linecap="round" opacity="0.45"/>',
        f'<path d="M 245 213 L 239 157 M 267 213 L 273 157" '
        f'stroke="{p["teal"]}" stroke-width="3" stroke-linecap="round" opacity="0.22"/>',
        '<circle cx="256" cy="246" r="52" fill="url(#glow)"/>',
    ]
    # Dark outlines and broad metal surfaces survive small-size rasterization.
    for x in (139, 327):
        parts.extend([
            f'<rect x="{x}" y="293" width="46" height="76" rx="10" '
            f'fill="{p["post"]}" stroke="{p["navy"]}" stroke-width="8"/>',
            f'<ellipse cx="{x+23}" cy="295" rx="23" ry="10" '
            f'fill="{p["post_top"]}" stroke="{p["navy"]}" stroke-width="7"/>',
            f'<path d="M {x+12} 315 V 352" stroke="{p["post_top"]}" '
            'stroke-width="5" stroke-linecap="round" opacity="0.65"/>',
        ])
    parts.extend([
        # A wide flat strip bent over both supports, rather than a wire loop.
        '<path d="M 157 308 L 195 250 Q 200 242 212 242 H 300 '
        'Q 312 242 317 250 L 355 308 L 340 321 L 303 268 H 209 L 172 321 Z" '
        f'fill="url(#metal)" stroke="{p["navy"]}" stroke-width="8" stroke-linejoin="round"/>',
        f'<path d="M 174 297 L 205 252 H 307 L 337 297" fill="none" '
        f'stroke="{p["ribbon_high"]}" stroke-width="4" stroke-linejoin="round" opacity="0.8"/>',
        f'<ellipse cx="256" cy="246" rx="18" ry="16" fill="{p["copper"]}" '
        f'stroke="{p["navy"]}" stroke-width="5"/>',
        f'<ellipse cx="251" cy="240" rx="7" ry="5" fill="{p["copper_high"]}"/>',
    ])
    if dark:
        parts.append(f'<path d="M 137 382 H 375" stroke="{p["axis_halo"]}" '
                     'stroke-width="13" stroke-linecap="round"/>')
    parts.append(f'<path d="M 137 382 H 375" stroke="{p["navy"]}" '
                 'stroke-width="9" stroke-linecap="round"/>')
    return parts


def make_svg(variant: str, theme: str) -> str:
    p = PALETTES[theme]
    titles = {"a": "Realistic Wetherill concordia", "b": "Small-size Wetherill concordia",
              "c": "TIMS filament and sample bead"}
    desc = f"{theme.title()} review option; ID-TIMS reduction. No crystal motif. "
    if variant in ("a", "b"):
        desc += (f"Concordia: x=expm1(lambda_235*t), y=expm1(lambda_238*t), "
                 f"0 to {MAX_AGE_YR:g} years, lambda_235={lambda_235:g}/yr, "
                 f"lambda_238={lambda_238:g}/yr.")
    else:
        desc += "Rhenium ribbon over two posts, glowing sample bead and faint rising ion beam."
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" '
             'viewBox="0 0 512 512" role="img" aria-labelledby="title desc">',
             f'<title id="title">Option {variant}: {titles[variant]} — {theme}</title>',
             f'<desc id="desc">{desc}</desc>']
    parts.extend(frame(p, grid=variant != "b"))
    if variant in ("a", "b"):
        parts.extend(concordia(p, simplified=variant == "b", dark=theme == "dark"))
    else:
        parts.extend(filament(p, dark=theme == "dark"))
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def render(svg: str, size: int) -> QImage:
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    if not renderer.isValid():
        raise RuntimeError("QtSvg rejected generated SVG")
    result = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return result


def save_png(img: QImage, path: Path) -> None:
    if not img.save(str(path), "PNG"):
        raise RuntimeError(f"Could not save {path}")


def contact_sheet(images: dict[tuple[str, str, int], QImage]) -> QImage:
    # Two theme panels, each with the four requested size columns. 512 px
    # images are drawn 1:1; small icons have separate 1:1 and nearest-4x views.
    panel_w, gap, margin = 990, 26, 24
    sheet = QImage(2 * panel_w + gap + 2 * margin, 1814,
                   QImage.Format.Format_ARGB32_Premultiplied)
    sheet.fill(QColor("#d5deea"))
    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    columns = ((16, 0, 104), (32, 104, 160), (128, 264, 166), (512, 430, 536))

    def label(x: float, y: float, w: float, h: float, text: str,
              color: str, px: int = 14, bold: bool = False) -> None:
        font = QFont("Helvetica")
        font.setPixelSize(px)
        font.setBold(bold)
        painter.setFont(font)
        painter.setPen(QColor(color))
        painter.drawText(QRectF(x, y, w, h), Qt.AlignmentFlag.AlignCenter, text)

    for index, theme in enumerate(("light", "dark")):
        origin = margin + index * (panel_w + gap)
        bg = "#eef2f7" if theme == "light" else "#111e2f"
        fg = "#23394f" if theme == "light" else "#dbe7f5"
        muted = "#596d83" if theme == "light" else "#96acc5"
        painter.fillRect(QRectF(origin, 20, panel_w, 1774), QColor(bg))
        label(origin, 28, panel_w, 36, f"ID–TIMS  /  {theme.upper()} OPTIONS", fg, 22, True)
        for size, offset, width in columns:
            label(origin+12+offset, 76, width, 24, f"{size} px", fg, 16, True)
        for row, variant in enumerate(("a", "b", "c")):
            top = 112 + row * 552
            names = {"a": "a · Real concordia", "b": "b · Simplified concordia",
                     "c": "c · TIMS filament"}
            painter.setPen(QPen(QColor("#cfdae7" if theme == "light" else "#31475e"), 1))
            painter.drawLine(origin+18, top, origin+panel_w-18, top)
            label(origin+12, top+6, 420, 30, names[variant], fg, 17, True)
            for size, offset, width in columns:
                center = origin + 12 + offset + width / 2
                img = images[(variant, theme, size)]
                if size in (16, 32):
                    painter.drawImage(round(center-size/2), top+133, img)
                    label(center-width/2, top+173, width, 24, "true size · 1×", muted, 13)
                    zoom = img.scaled(size*4, size*4,
                                      Qt.AspectRatioMode.IgnoreAspectRatio,
                                      Qt.TransformationMode.FastTransformation)
                    painter.drawImage(round(center-size*2), top+258, zoom)
                    label(center-width/2, top+402, width, 40, "4× · nearest", muted, 13)
                else:
                    painter.drawImage(round(center-size/2), round(top+274-size/2), img)
                    if size == 128:
                        label(center-width/2, top+355, width, 24, "true size · 1×", muted, 13)
        label(origin, 1771, panel_w, 20, "Review options only · current application icon unchanged", muted, 12)
    painter.end()
    return sheet


def write_readme() -> None:
    text = f"""# ID-TIMS app icon options

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
λ235 = {lambda_235:.8g} yr⁻¹
λ238 = {lambda_238:.8g} yr⁻¹
```

Both constants are imported from `IDTIMS_UPbRPy.constants`, not hard-coded in
the generator. The age range is **0–4.0 Ga** (0–4,000,000,000 years).
The ratio ranges are x = 0–{X_MAX:.8f} and y = 0–{Y_MAX:.8f}.
Both axes are mapped **linearly**, independently normalized to these maxima:

```text
screen_x = 128 + 258 × x / x_max
screen_y = 384 − 250 × y / y_max
```

Both curves are identical {SAMPLES}-point polylines at uniform time intervals,
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
"""
    (OUT / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    OUT.mkdir(parents=True, exist_ok=True)
    images = {}
    for variant in ("a", "b", "c"):
        for theme in ("light", "dark"):
            svg = make_svg(variant, theme)
            (OUT / f"{variant}_{theme}.svg").write_text(svg, encoding="utf-8")
            for size in SIZES:
                img = render(svg, size)
                images[(variant, theme, size)] = img
                save_png(img, OUT / f"{variant}_{theme}_{size}.png")
    save_png(contact_sheet(images), OUT / "contact_sheet.png")
    write_readme()
    print(f"Generated 6 SVGs, 24 PNG renders, contact_sheet.png and README.md in {OUT}")
    # Keep the application alive until all painters and image writers finish.
    del app


if __name__ == "__main__":
    main()
