#!/usr/bin/env python3
"""Generate coloured filament artwork and install the chosen v2c app icon.

Run: .venv/bin/python tools/make_app_icon.py --install
Without --install, generate review variants and the suite preview sheet.
No application imports, downloads, or writes to sibling repos.
Existing v2a/v2b, selected root exports, and family_sheet.png are preserved.
SVG filters use local rsvg-convert when available. The offline QtSvg/numpy
fallback explicitly composites the shared shadow (QtSvg ignores SVG filters).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QImageReader, QLinearGradient, QPainter, QPen
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/icon_options/filament_v2"
SIBLINGS = ROOT.parent
SIZES = (16, 32, 64, 128, 256, 512, 1024)
# Apple export mapping copied from UPbRPy/GUI/icon.py: ICONSET_EXPORT_SPECS.
ICONSET = (
    (16, "icon_16x16.png"), (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"), (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"), (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"), (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"), (1024, "icon_512x512@2x.png"),
)

# Shared HEAD/PANEL numbers copied from grainatlas/tauri/icon/zircons.py,
# also reproduced in UPbRPy/GUI/assets/icons/make_icon.py. Bracketeer's
# src-tauri/icon/make_icon.py explicitly cites the same HEAD template.
# 512 viewBox; tile 36/36/440/440/r88, 10 border; paper 96/96/320/320/r22,
# 3 border; 2 grid; shadow dy9/sigma10/#0f1b2d/25%. Do not import those repos.
DEFS = '''<defs>
  <linearGradient id="tile" x2="0.8" y2="1"><stop stop-color="#ffffff"/><stop offset="1" stop-color="#e9eef5"/></linearGradient>
  <linearGradient id="paper" x2="0.8" y2="1"><stop stop-color="#ffffff"/><stop offset="1" stop-color="#f1f5f9"/></linearGradient>
  <linearGradient id="metal" x2="0.8" y2="1"><stop stop-color="#e3e9f0"/><stop offset="0.5" stop-color="#c9d3df"/><stop offset="1" stop-color="#a9b6c5"/></linearGradient>
  <linearGradient id="post" x2="0.8" y2="1"><stop stop-color="#c9d3df"/><stop offset="1" stop-color="#a9b6c5"/></linearGradient>
  <linearGradient id="sample" x2="0.8" y2="1"><stop stop-color="#efa39d"/><stop offset="1" stop-color="#cb3c33"/></linearGradient>
  <radialGradient id="heat"><stop stop-color="#f6d29a" stop-opacity="0.7"/><stop offset="0.5" stop-color="#cb3c33" stop-opacity="0.15"/><stop offset="1" stop-color="#cb3c33" stop-opacity="0"/></radialGradient>
  <linearGradient id="beam" x2="0" y1="1" y2="0"><stop stop-color="#4063d8" stop-opacity="0.17"/><stop offset="1" stop-color="#7dd3fc" stop-opacity="0"/></linearGradient>
  <filter id="shadow" x="-25%" y="-25%" width="150%" height="150%"><feDropShadow dx="0" dy="9" stdDeviation="10" flood-color="#0f1b2d" flood-opacity="0.25"/></filter>
</defs>'''
TILE = '''<rect x="36" y="36" width="440" height="440" rx="88" fill="url(#tile)"/>
<rect x="36" y="36" width="440" height="440" rx="88" fill="none" stroke="#d9e1ec" stroke-width="10"/>'''
CARD = '<rect x="96" y="96" width="320" height="320" rx="22" fill="url(#paper)" stroke="#cbd5e1" stroke-width="3"/>'
GRID = '<path d="M160 128 V384 M224 128 V384 M288 128 V384 M352 128 V384 M128 160 H384 M128 224 H384 M128 288 H384 M128 352 H384" stroke="#e2e8f0" stroke-width="2"/>'

# Blue gradient/edge: Studio and grainatlas; RGB rays: bracketeer's dots.
# Warm colors: shared grainatlas/Studio amber crystal PALETTE and edge.
# Radial falloffs give soft light without renderer-specific blur filters.
COLOUR_DEFS = '''<defs>
  <linearGradient id="bluePost" x2="0.8" y2="1"><stop stop-color="#a8b8f2"/><stop offset="1" stop-color="#4063d8"/></linearGradient>
  <radialGradient id="warmSample" cx="0.35" cy="0.3" r="0.8"><stop stop-color="#f6d29a"/><stop offset="0.45" stop-color="#eab25a"/><stop offset="1" stop-color="#c8683a"/></radialGradient>
  <radialGradient id="warmHalo"><stop stop-color="#f6d29a" stop-opacity="0.75"/><stop offset="0.5" stop-color="#eab25a" stop-opacity="0.22"/><stop offset="1" stop-color="#c8683a" stop-opacity="0"/></radialGradient>
  <radialGradient id="warmBeam" cx="0.5" cy="1" r="1"><stop stop-color="#eab25a" stop-opacity="0.42"/><stop offset="0.55" stop-color="#eab25a" stop-opacity="0.14"/><stop offset="1" stop-color="#f6d29a" stop-opacity="0"/></radialGradient>
  <linearGradient id="warmRay" x2="0" y1="1" y2="0"><stop stop-color="#eab25a" stop-opacity="0.65"/><stop offset="1" stop-color="#eab25a" stop-opacity="0.1"/></linearGradient>
</defs>'''
NEUTRAL_BEAD = '''<circle cx="256" cy="198" r="38" fill="url(#heat)"/>
<ellipse cx="256" cy="197" rx="18" ry="15" fill="url(#sample)" stroke="#8f2a24" stroke-width="4" stroke-opacity="0.8"/>
<ellipse cx="251" cy="192" rx="7" ry="4.5" fill="#f6d29a"/>'''


def motif(variant: str = "v2a", small: bool = False) -> str:
    # Neutral GREY palette copied from UPbRPy/GUI/assets/icons/make_icon.py:
    # #c9d3df/#a9b6c5/#e3e9f0. Subject edges use the shared #334155 axes
    # color and 4-unit silhouette / 2.6-unit translucent face-edge hierarchy.
    # Sample red/edge and warm highlight come from the existing family.
    parts = ['''<path d="M248 201 L229 132 Q256 121 283 132 L264 201 Z" fill="url(#beam)"/>
<path d="M256 178 V144" stroke="#4063d8" stroke-width="3" stroke-linecap="round" opacity="0.18"/>''']
    if variant == "v2c":
        # Preserve the original 3-unit ray weight in the large master.
        parts = ['''<g fill="none" stroke-width="3" stroke-linecap="round" opacity="0.9">
<path d="M256 197 L221 132" stroke="#cb3c33"/>
<path d="M256 197 V126" stroke="#389826"/>
<path d="M256 197 L291 132" stroke="#4063d8"/>
</g>''']
        if small:
            # Only the rays change: 1 px strokes at 32 px, wider divergence.
            # All other geometry, colours, opacity and layers stay identical.
            parts[0] = (parts[0].replace('stroke-width="3"', 'stroke-width="16"')
                        .replace('L221 132', 'L204 132').replace('L291 132', 'L308 132'))
    elif variant == "v2d":
        parts = ['''<ellipse cx="256" cy="161" rx="13" ry="40" fill="url(#warmBeam)"/>
<path d="M256 197 V128" stroke="url(#warmRay)" stroke-width="3" stroke-linecap="round"/>''']
    for x in (137, 329):
        post = f'''<rect x="{x}" y="287" width="46" height="83" rx="5" fill="url(#post)" stroke="#334155" stroke-width="4" stroke-opacity="0.8"/>
<path d="M{x+31} 293 V366 H{x+42} V293 Z" fill="#a9b6c5"/>
<ellipse cx="{x+23}" cy="287" rx="23" ry="10" fill="#e3e9f0" stroke="#334155" stroke-width="4" stroke-opacity="0.8"/>
<path d="M{x+11} 309 V358" stroke="#e3e9f0" stroke-width="2.6" opacity="0.8"/>'''
        if variant in ("v2c", "v2d"):
            post = (post.replace("url(#post)", "url(#bluePost)")
                    .replace("#334155", "#24408f").replace("#a9b6c5", "#4063d8")
                    .replace("#e3e9f0", "#c3cff6"))
        parts.append(post)
    # A flat ribbon, not a wire: distinct upper face, front thickness, and two
    # downturned ends bent over the posts. No invented chart axes or base rail.
    parts.append('''<path d="M143 294 L192 205 Q197 197 209 197 H303 Q315 197 320 205 L369 294 L352 308 L303 223 H209 L160 308 Z" fill="url(#metal)"/>
<path d="M160 308 L209 223 H303 L352 308 L352 321 L303 236 H209 L160 321 Z" fill="#a9b6c5" stroke="#334155" stroke-width="2.6" stroke-opacity="0.55" stroke-linejoin="round"/>
<path d="M143 294 L192 205 Q197 197 209 197 H303 Q315 197 320 205 L369 294 L352 308 L352 321 L303 236 H209 L160 321 L160 308 Z" fill="none" stroke="#334155" stroke-width="4" stroke-opacity="0.8" stroke-linejoin="round"/>
<path d="M158 291 L201 211 Q204 207 213 207 H299 Q308 207 311 211 L354 291" fill="none" stroke="#ffffff" stroke-width="2.6" stroke-opacity="0.65" stroke-linejoin="round"/>
''' + NEUTRAL_BEAD + "\n")
    artwork = "\n".join(parts)
    if variant == "v2c":
        artwork = artwork.replace(NEUTRAL_BEAD, '''<circle cx="256" cy="198" r="48" fill="url(#warmHalo)"/>
<ellipse cx="256" cy="197" rx="23" ry="19" fill="url(#warmSample)" stroke="#5b2a12" stroke-width="4" stroke-opacity="0.8"/>
<ellipse cx="249" cy="190" rx="8" ry="5" fill="#f6d29a"/>''')
    return artwork


def wrap(body: str, variant: str, colour: bool = False) -> str:
    description = ("A rhenium ribbon bent over two posts with a glowing "
                   "central sample bead and faint rising ion beam, on the shared lab suite tile.")
    if variant.startswith("v2c"):
        description = ("A grey rhenium ribbon over blue posts, with a glowing amber-orange "
                       "bead and three diverging red, green and blue ion rays on the shared lab suite tile.")
    elif variant.startswith("v2d"):
        description = ("A grey rhenium ribbon over blue posts, with a red sample bead "
                       "and a soft amber ion beam on the shared lab suite tile.")
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" '
            'viewBox="0 0 512 512" role="img" aria-labelledby="title desc">\n'
            f'<title id="title">ID-TIMS filament {variant}</title>\n'
            f'<desc id="desc">{description}</desc>\n'
            + DEFS + ("\n" + COLOUR_DEFS if colour else "") + "\n" + body + "\n</svg>\n")


def content(grid: bool, variant: str = "v2a", small: bool = False) -> str:
    return CARD + "\n" + (GRID if grid else "") + "\n" + motif(variant, small)


def svg(grid: bool, variant: str = "v2a", small: bool = False) -> str:
    title = {"v2c": "v2c · coloured isotopes", "v2d": "v2d · quiet colour"}.get(
        variant, "v2a · paper grid" if grid else "v2b · plain paper")
    return wrap(TILE + '\n<g filter="url(#shadow)">\n' + content(grid, variant, small) + '\n</g>',
                title, variant in ("v2c", "v2d"))


def qt_render(source: str, size: int) -> QImage:
    renderer = QSvgRenderer(QByteArray(source.encode("utf-8")))
    if not renderer.isValid():
        raise ValueError("Invalid SVG")
    result = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return result


def qt_with_shadow(grid: bool, size: int, variant: str = "v2a", small: bool = False) -> QImage:
    """Preserve the SVG shadow using local numpy, including subpixel sizes."""
    work_size = max(size, 128)
    foreground = qt_render(wrap(content(grid, variant, small), "foreground",
                                variant in ("v2c", "v2d")), work_size)
    rgba = foreground.convertToFormat(QImage.Format.Format_RGBA8888)
    pixels = np.frombuffer(rgba.constBits(), dtype=np.uint8).reshape(work_size, work_size, 4)
    alpha = pixels[:, :, 3].astype(float) / 255
    sigma = 10 * work_size / 512
    radius = int(np.ceil(4 * sigma))
    coords = np.arange(-radius, radius + 1)
    kernel = np.exp(-coords * coords / (2 * sigma * sigma))
    kernel /= kernel.sum()
    for axis in (0, 1):
        alpha = np.apply_along_axis(lambda v: np.convolve(v, kernel, mode="same"), axis, alpha)
    shadow_pixels = np.zeros((work_size, work_size, 4), dtype=np.uint8)
    shadow_pixels[:, :, :3] = (15, 27, 45)
    shadow_pixels[:, :, 3] = np.clip(np.rint(alpha * 255 * 0.25), 0, 255).astype(np.uint8)
    shadow = QImage(shadow_pixels.data, work_size, work_size, work_size * 4,
                    QImage.Format.Format_RGBA8888).copy()
    result = qt_render(wrap(TILE, "tile"), work_size)
    painter = QPainter(result)
    painter.drawImage(QRectF(0, 9 * work_size / 512, work_size, work_size), shadow)
    painter.drawImage(0, 0, foreground)
    painter.end()
    return result.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)


def save(image: QImage, path: Path) -> None:
    if image.isNull() or not image.save(str(path), "PNG"):
        raise RuntimeError(f"Failed to write {path}")


def export(directory: Path, grid: bool, converter: str | None,
           variant: str = "v2a") -> dict[int, QImage]:
    directory.mkdir(parents=True, exist_ok=True)
    master = directory / "icon.svg"
    master.write_text(svg(grid, variant), encoding="utf-8")
    if variant == "v2c":
        (directory / "icon_small.svg").write_text(svg(grid, variant, small=True), encoding="utf-8")
    images = {}
    for size in SIZES:
        target = directory / f"icon_{size}.png"
        small = variant == "v2c" and size in (16, 32)
        source = directory / "icon_small.svg" if small else master
        if converter:
            subprocess.run([converter, "-w", str(size), "-h", str(size),
                            "-o", str(target), str(source)], check=True)
            images[size] = QImage(str(target))
            if images[size].isNull():
                raise RuntimeError(f"Cannot load {target}")
        else:
            images[size] = qt_with_shadow(grid, size, variant, small)
            save(images[size], target)
    iconset = directory / "filament.iconset"
    iconset.mkdir(exist_ok=True)
    # An iconset contains exactly Apple's ten PNG filenames, no previews/SVGs.
    for path in iconset.iterdir():
        if path.is_file() and path.name not in {name for _, name in ICONSET}:
            path.unlink()
    for size, filename in ICONSET:
        validate_png(directory / f"icon_{size}.png", size)
        shutil.copyfile(directory / f"icon_{size}.png", iconset / filename)
    return images


def validate_png(path: Path, size: int) -> None:
    """Require 8-bit RGBA PNGs, including exact physical pixel dimensions."""
    data = path.read_bytes()
    if (data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR"
            or struct.unpack(">IIBB", data[16:26]) != (size, size, 8, 6)):
        raise ValueError(f"Expected {size} px 8-bit RGBA PNG: {path}")


def package_icns(iconset: Path, target: Path) -> None:
    """Try iconutil, falling back to a deterministic standard PNG ICNS container.

    icp4/icp5 are Apple's PNG entries for 16/32 px (not legacy ic04/ic05).
    ic11/ic12/ic13/ic14 preserve the distinct Retina representations.
    """
    iconutil = shutil.which("iconutil")
    if iconutil:
        result = subprocess.run([iconutil, "-c", "icns", str(iconset), "-o", str(target)],
                                capture_output=True, text=True)
        if result.returncode == 0:
            validate_icns(target)
            print("iconutil succeeded:", target)
            return
        print("iconutil failed:", result.stderr.strip())
    types = (b"icp4", b"ic11", b"icp5", b"ic12", b"ic07",
             b"ic13", b"ic08", b"ic14", b"ic09", b"ic10")
    chunks = []
    for kind, (size, name) in zip(types, ICONSET):
        validate_png(iconset / name, size)
        png = (iconset / name).read_bytes()
        chunks.append(kind + struct.pack(">I", len(png) + 8) + png)
    body = b"".join(chunks)
    target.write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)
    validate_icns(target)
    print("Wrote Python PNG-chunk ICNS:", target)


def validate_icns(path: Path) -> None:
    """Read every ICNS representation back through Qt's independent decoder."""
    reader = QImageReader(str(path))
    if not reader.canRead() or reader.imageCount() != len(ICONSET):
        raise ValueError(f"Unreadable or incomplete ICNS: {path}")
    sizes = []
    for index in range(reader.imageCount()):
        image = reader.read()
        if image.isNull() or image.width() != image.height():
            raise ValueError(f"Invalid ICNS image {index}: {path}: {reader.errorString()}")
        sizes.append(image.width())
        if index + 1 < reader.imageCount() and not reader.jumpToNextImage():
            raise ValueError(f"Missing ICNS image {index + 1}: {path}")
    if sorted(sizes) != sorted(size for size, _ in ICONSET):
        raise ValueError(f"Unexpected ICNS sizes: {sizes}")


def small_sizes_sheet(previous: dict[int, QImage], installed: dict[int, QImage]) -> QImage:
    """Compare old/new 16/32 px at 1× and 8× nearest-neighbour, light/dark."""
    panel_w, margin, gap, height = 740, 24, 24, 850
    sheet = QImage(2 * panel_w + 2 * margin + gap, height, QImage.Format.Format_RGBA8888)
    sheet.fill(QColor("#cbd5e1"))
    p = QPainter(sheet)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    for index, dark in enumerate((False, True)):
        x = margin + index * (panel_w + gap)
        bg, fg = ("#172130", "#e2e8f0") if dark else ("#eef2f7", "#334155")
        p.fillRect(QRectF(x, 20, panel_w, height - 40), QColor(bg))

        def label(left, top, width, text, px=18):
            font = QFont("Helvetica")
            font.setPixelSize(px)
            p.setFont(font)
            p.setPen(QColor(fg))
            p.drawText(QRectF(left, top, width, 32), Qt.AlignmentFlag.AlignCenter, text)

        label(x, 30, panel_w, "v2c colour rays · " + ("dark" if dark else "light"), 24)
        for column, (name, images) in enumerate((("Previous v2c", previous), ("Installed · small rays", installed))):
            center = x + 195 + column * 350
            label(center - 165, 78, 330, name, 20)
            for row, size in enumerate((16, 32)):
                top = 135 + row * 300
                image = images[size]
                image.setDevicePixelRatio(1)
                p.drawImage(center - size // 2, top, image)
                label(center - 165, top + 35, 330, f"{size} px · true size (1×)", 16)
                zoom = image.scaled(size * 8, size * 8, Qt.AspectRatioMode.IgnoreAspectRatio,
                                    Qt.TransformationMode.FastTransformation)
                p.drawImage(center - size * 4, top + 80, zoom)
                label(center - 165, top + 80 + size * 8 + 6, 330, "8× · nearest-neighbour", 16)
    p.end()
    return sheet


def install(converter: str | None) -> None:
    """Regenerate the chosen artwork, comparison, iconset and installed assets."""
    directory = OUT / "filament_v2c"
    # Recreate the previous unrefined renders directly from the unchanged master.
    previous = {}
    for size in (16, 32):
        if converter:
            result = subprocess.run([converter, "-w", str(size), "-h", str(size)],
                                    input=svg(True, "v2c").encode(), capture_output=True, check=True)
            previous[size] = QImage.fromData(result.stdout, "PNG")
        else:
            previous[size] = qt_with_shadow(True, size, "v2c")
    export(directory, True, converter, "v2c")
    icns = directory / "icon.icns"
    package_icns(directory / "filament.iconset", icns)
    assets = ROOT / "src/idtims_app/assets"
    shutil.copyfile(directory / "icon.svg", assets / "app_icon.svg")
    shutil.copyfile(icns, assets / "app_icon.icns")
    for size in SIZES:
        shutil.copyfile(directory / f"icon_{size}.png", assets / f"app_icon_{size}.png")
    # Read the installed files, so the sheet also checks the installation step.
    installed = {size: QImage(str(assets / f"app_icon_{size}.png")) for size in (16, 32)}
    save(small_sizes_sheet(previous, installed), OUT.parent / "final_small_sizes.png")


def family_images() -> list[tuple[str, dict[int, QImage]]]:
    studio = SIBLINGS / "UPbRPy/GUI/assets/icons/upbrpy_zircon.iconset"
    specs = [("Studio", studio, True)]
    for name, repository, relative in (
        ("UPb Lab", "upblab", "src-tauri/icons"),
        ("grainatlas", "grainatlas", "tauri/src-tauri/icons"),
        ("bracketeer", "bracketeer", "src-tauri/icons"),
    ):
        specs.append((name, SIBLINGS / repository / relative, False))
    result = []
    for name, directory, is_studio in specs:
        images = {}
        for size in (16, 32, 64, 128, 512):
            if is_studio:
                path = directory / ("icon_32x32@2x.png" if size == 64 else f"icon_{size}x{size}.png")
            else:
                path = directory / ("icon.png" if size == 512 else f"{size}x{size}.png")
                # Tauri sources ship 32px, not a dedicated 16px PNG.
                if size in (16, 64):
                    # 64 px Dock sample from the shipped 128 px export.
                    # These apps do not ship a dedicated 64 px PNG either.
                    path = directory / ("32x32.png" if size == 16 else "128x128.png")
            image = QImage(str(path))
            if image.isNull():
                raise RuntimeError(f"Missing family source: {path}")
            # QImage reads @2x PNG density metadata; this sheet uses physical
            # pixels, so native 64 px must occupy 64 canvas pixels, not 32.
            image.setDevicePixelRatio(1)
            images[size] = image.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation)
        result.append((name, images))
    return result


def family_sheet(rows: list[tuple[str, dict[int, QImage]]]) -> QImage:
    panel_w, gap, margin, row_h = 990, 26, 24, 552
    height = 126 + row_h * len(rows) + 52
    sheet = QImage(2 * panel_w + gap + 2 * margin, height,
                   QImage.Format.Format_ARGB32_Premultiplied)
    sheet.fill(QColor("#cbd5e1"))
    p = QPainter(sheet)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    columns = ((16, 0, 104), (32, 104, 160), (128, 264, 166), (512, 430, 536))

    def label(x: float, y: float, w: float, h: float, text: str,
              color: str, px: int = 14, bold: bool = False) -> None:
        font = QFont("Helvetica")
        font.setPixelSize(px)
        font.setBold(bold)
        p.setFont(font)
        p.setPen(QColor(color))
        p.drawText(QRectF(x, y, w, h), Qt.AlignmentFlag.AlignCenter, text)

    for panel, dark in enumerate((False, True)):
        origin = margin + panel * (panel_w + gap)
        bg, fg, muted, line = (("#172130", "#e2e8f0", "#a9b6c5", "#334155") if dark
                               else ("#eef2f7", "#334155", "#64748b", "#cbd5e1"))
        p.fillRect(QRectF(origin, 20, panel_w, height - 40), QColor(bg))
        label(origin, 28, panel_w, 36,
              "LAB SUITE  /  " + ("DARK DOCK BACKGROUND" if dark else "LIGHT BACKGROUND"), fg, 22, True)
        for size, offset, width in columns:
            label(origin + 12 + offset, 76, width, 24, f"{size} px", fg, 16, True)
        for row, (name, images) in enumerate(rows):
            top = 112 + row * row_h
            p.setPen(QPen(QColor(line), 1))
            p.drawLine(origin + 18, top, origin + panel_w - 18, top)
            label(origin + 12, top + 6, 420, 30, name, fg, 17, True)
            for size, offset, width in columns:
                center = origin + 12 + offset + width / 2
                image = images[size]
                if size in (16, 32):
                    p.drawImage(round(center - size / 2), top + 133, image)
                    label(center - width / 2, top + 173, width, 24, "true size · 1×", muted, 13)
                    zoom = image.scaled(size * 4, size * 4, Qt.AspectRatioMode.IgnoreAspectRatio,
                                        Qt.TransformationMode.FastTransformation)
                    p.drawImage(round(center - size * 2), top + 258, zoom)
                    label(center - width / 2, top + 402, width, 40, "4× · nearest", muted, 13)
                else:
                    p.drawImage(round(center - size / 2), top + 274 - size // 2, image)
                    if size == 128:
                        label(center - width / 2, top + 355, width, 24, "true size · 1×", muted, 13)
        label(origin + 8, height - 63, panel_w - 16, 36,
              "Same artwork on both backgrounds · Tauri 16 px from shipped 32 px PNG · review only",
              muted, 12)
    p.end()
    return sheet


def preview_sheet(family: list[tuple[str, dict[int, QImage]]],
                  variants: list[tuple[str, dict[int, QImage]]]) -> QImage:
    """True-size grid followed by light/dark mock Docks, all in device pixels."""
    grid = family_sheet(family + variants)
    header_h, dock_h = 84, 664
    dock_y = header_h + grid.height()
    sheet = QImage(grid.width(), dock_y + dock_h, QImage.Format.Format_ARGB32_Premultiplied)
    sheet.fill(QColor("#cbd5e1"))
    p = QPainter(sheet)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

    def label(x: float, y: float, w: float, h: float, text: str,
              color: str = "#334155", px: int = 16, bold: bool = False) -> None:
        font = QFont("Helvetica")
        font.setPixelSize(px)
        font.setBold(bold)
        p.setFont(font)
        p.setPen(QColor(color))
        p.drawText(QRectF(x, y, w, h), Qt.AlignmentFlag.AlignCenter, text)

    label(24, 8, sheet.width() - 48, 36, "01  /  SIZE GRID — SHIPPED SUITE + FILAMENT READINGS", px=24, bold=True)
    label(24, 46, sheet.width() - 48, 26,
          "View at 100% for native pixels · 16/32 px also enlarged 4× without smoothing", px=16)
    p.drawImage(0, header_h, grid)
    label(24, dock_y, sheet.width() - 48, 36, "02  /  MOCK DOCK — 64 PX ICONS, EVEN SPACING", px=24, bold=True)
    label(24, dock_y + 38, sheet.width() - 48, 26,
          "Studio native 64 px · Tauri suite reduced from shipped 128 px · filament native 64 px", px=15)
    for panel, dark in enumerate((False, True)):
        origin, top = 24 + panel * 1016, dock_y + 80
        desktop = QLinearGradient(origin, top, origin + 990, top + 560)
        desktop.setColorAt(0, QColor("#24364b" if dark else "#e5ecf4"))
        desktop.setColorAt(1, QColor("#101a29" if dark else "#bdcde1"))
        p.fillRect(QRectF(origin, top, 990, 560), desktop)
        fg, muted = ("#e2e8f0", "#a9b6c5") if dark else ("#334155", "#475569")
        label(origin, top + 8, 990, 28, "DARK DESKTOP" if dark else "LIGHT DESKTOP", fg, 18, True)
        for row, (name, images) in enumerate(variants):
            row_top = top + 44 + row * 168
            label(origin + 16, row_top + 51, 152, 32, name, fg, 20, True)
            bar = QRectF(origin + 186, row_top + 18, 774, 94)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(15, 27, 45, 45 if dark else 28))
            p.drawRoundedRect(bar.translated(0, 6), 26, 26)
            p.setBrush(QColor(235, 243, 255, 30) if dark else QColor(255, 255, 255, 135))
            p.setPen(QPen(QColor(255, 255, 255, 70 if dark else 180), 1))
            p.drawRoundedRect(bar, 26, 26)
            for index, (app_name, app_images) in enumerate(family + [(name, images)]):
                center = bar.left() + 79 + index * 154
                p.drawImage(round(center - 32), row_top + 33, app_images[64])
                label(center - 75, row_top + 119, 150, 26, app_name, muted, 15)
    p.end()
    return sheet


def existing_variant(name: str) -> dict[int, QImage]:
    images = {size: QImage(str(OUT / name / f"icon_{size}.png")) for size in SIZES}
    if any(image.isNull() or image.width() != size or image.height() != size
           for size, image in images.items()):
        raise RuntimeError(f"Missing or invalid preserved variant: {name}")
    return images


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--icns", action="store_true", help="also package the chosen v2c Apple iconset")
    parser.add_argument("--install", action="store_true", help="generate and install chosen v2c assets and small-size comparison only")
    args = parser.parse_args()
    app = QGuiApplication.instance() or QGuiApplication([])
    converter = shutil.which("rsvg-convert")
    print("PNG renderer:", converter or "QtSvg + numpy shadow composite")
    if args.install:
        install(converter)
        print("Installed v2c master, small 16/32 px, seven PNGs and ICNS; wrote final_small_sizes.png")
        return
    variants = [("v2a", existing_variant("filament_v2a"))]
    for variant in ("v2c", "v2d"):
        variants.append((variant, export(OUT / f"filament_{variant}", True, converter, variant)))
    save(preview_sheet(family_images(), variants), OUT.parent / "preview_sheet.png")
    if args.icns:
        chosen = OUT / "filament_v2c"
        package_icns(chosen / "filament.iconset", chosen / "icon.icns")
    print("Wrote v2c/v2d review SVGs, seven PNG sizes and iconset mirrors each, and preview_sheet.png")
    print("Preserved existing v2a/v2b, root exports, and family_sheet.png")
    del app


if __name__ == "__main__":
    main()
