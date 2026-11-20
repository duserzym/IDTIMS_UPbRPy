#!/usr/bin/env python3
"""Generate/install five Pb bars of a nominal zircon on ET535, entirely offline.

Matches the approved 2026-11-20 make_zircon_icon.py draft: five labelled
bars (204, 205, 206, 207, 208), with no 202 bar.
The original four-peak master is preserved as icon_four_peaks.svg.
The flat-topped peak(), suite tile, card, grid, axes and shadow are unchanged.
Shared suite template credit (as tools/make_app_icon.py): HEAD/PANEL from
grainatlas/tauri/icon/zircons.py, also reproduced in
UPbRPy/GUI/assets/icons/make_icon.py; bracketeer/src-tauri/icon/make_icon.py
cites the same template. Tile 36/36/440/440/r88; paper 96/96/320/320/r22;
shadow dy9/sigma10/#0f1b2d/25%. No sibling imports or writes.
The historical v2c generator is retained unchanged in make_app_icon.py.
Run: QT_QPA_PLATFORM=offscreen env -u PYTHONPATH .venv/bin/python tools/make_pb_peaks_icon.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from make_app_icon import ICONSET, SIZES, package_icns, save, validate_png
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/icon_options/pb_peaks"
REVIEW_SIZES = (16, 32, 64, 128)
# True-size review: 28-unit labels read at 128 px, but become specks at 64 px.
SMALL_SIZES = (16, 32, 64)

DEFS = """
<linearGradient id="tile" x2="0.8" y2="1"><stop stop-color="#ffffff"/><stop offset="1" stop-color="#e9eef5"/></linearGradient>
<linearGradient id="paper" x2="0.8" y2="1"><stop stop-color="#ffffff"/><stop offset="1" stop-color="#f1f5f9"/></linearGradient>
<linearGradient id="blue" x2="0.8" y2="1"><stop stop-color="#a8b8f2"/><stop offset="1" stop-color="#4063d8"/></linearGradient>
<linearGradient id="red" x2="0.8" y2="1"><stop stop-color="#efa39d"/><stop offset="1" stop-color="#cb3c33"/></linearGradient>
<linearGradient id="green" x2="0.8" y2="1"><stop stop-color="#a9dd9c"/><stop offset="1" stop-color="#389826"/></linearGradient>
<linearGradient id="purple" x2="0.8" y2="1"><stop stop-color="#d3b4e3"/><stop offset="1" stop-color="#9558b2"/></linearGradient>
<linearGradient id="amber" x2="0.8" y2="1"><stop stop-color="#f5d58a"/><stop offset="1" stop-color="#ce941f"/></linearGradient>
<linearGradient id="teal" x2="0.8" y2="1"><stop stop-color="#9cded8"/><stop offset="1" stop-color="#209b92"/></linearGradient>
<filter id="shadow" x="-25%" y="-25%" width="150%" height="150%"><feDropShadow dx="0" dy="9" stdDeviation="10" flood-color="#0f1b2d" flood-opacity="0.25"/></filter>
"""
TILE = """<rect x="36" y="36" width="440" height="440" rx="88" fill="url(#tile)"/>
<rect x="36" y="36" width="440" height="440" rx="88" fill="none" stroke="#d9e1ec" stroke-width="10"/>"""
CARD = '<rect x="96" y="96" width="320" height="320" rx="22" fill="url(#paper)" stroke="#cbd5e1" stroke-width="3"/>'
GRID = '<path d="M160 128 V384 M224 128 V384 M288 128 V384 M352 128 V384 M128 160 H384 M128 224 H384 M128 288 H384 M128 352 H384" stroke="#e2e8f0" stroke-width="2"/>'
AXES = '<path d="M128 128 V384 H384" fill="none" stroke="#334155" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>'


def svg(title, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img">'
        f'<title>{title}</title><defs>{DEFS}</defs>{TILE}<g filter="url(#shadow)">{body}</g></svg>'
    )


def peak(x0, w, h, base=384):
    """Flat-topped TIMS peak path centred on x0."""
    top = base - h
    s = w * 0.28
    return (
        f"M{x0 - w / 2 - s} {base} C{x0 - w / 2 - s * 0.2} {base}, {x0 - w / 2 - s * 0.3} {top}, {x0 - w / 2 + s * 0.2} {top} "
        f"H{x0 + w / 2 - s * 0.2} C{x0 + w / 2 + s * 0.3} {top}, {x0 + w / 2 + s * 0.2} {base}, {x0 + w / 2 + s} {base} Z"
    )


def b_peaks(*, small=False, tiny=False):
    """Five Pb bars of a nominal zircon on ET535, in mass order."""
    parts = [CARD, "" if tiny else GRID, AXES]
    spec = [
        (204, 172, 12, "purple", "#5e3378"),
        (205, 220, 206, "teal", "#12645f"),
        (206, 268, 222, "blue", "#24408f"),
        (207, 316, 104, "red", "#8f2a24"),
        (208, 364, 62, "green", "#1f5f16"),
    ]
    width, stroke = (30, 2) if tiny else (28, 4)
    for mass, x, h, fill, edge in spec:
        parts.append(
            f'<path d="{peak(x, width, h)}" fill="url(#{fill})" fill-opacity="0.85" stroke="{edge}" stroke-width="{stroke}" stroke-linejoin="round"/>'
        )
        if not (small or tiny):
            parts.append(
                f'<text x="{x}" y="{384 - h - 12}" fill="{edge}" '
                'font-family="Helvetica Neue, Helvetica, Arial, sans-serif" '
                f'font-size="28" font-weight="bold" text-anchor="middle">{mass}</text>'
            )
    parts.append(AXES)
    return svg("Five Pb bars of a nominal zircon on ET535: 204, 205, 206, 207, 208", "".join(parts))


def render(converter: str, source: Path, size: int, target: Path) -> QImage:
    subprocess.run(
        [converter, "-w", str(size), "-h", str(size), "-o", str(target), str(source)],
        check=True,
    )
    validate_png(target, size)
    return QImage(str(target))


def small_sizes_sheet(
    previous: dict[int, QImage], installed: dict[int, QImage]
) -> QImage:
    """Four peaks vs five zircon bars at 16/32/64/128 px, 1× and 8×, light/dark."""
    panel_w, margin, gap = 2240, 24, 24
    height = 160 + sum(size * 9 + 120 for size in REVIEW_SIZES)
    sheet = QImage(
        2 * panel_w + 2 * margin + gap, height, QImage.Format.Format_RGBA8888
    )
    sheet.fill(QColor("#cbd5e1"))
    p = QPainter(sheet)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    for index, dark in enumerate((False, True)):
        x = margin + index * (panel_w + gap)
        bg, fg = ("#172130", "#e2e8f0") if dark else ("#eef2f7", "#334155")
        p.fillRect(QRectF(x, 20, panel_w, height - 40), QColor(bg))

        def label(left, top, width, text, px=18, fg=fg):
            font = QFont("Helvetica")
            font.setPixelSize(px)
            p.setFont(font)
            p.setPen(QColor(fg))
            p.drawText(QRectF(left, top, width, 32), Qt.AlignmentFlag.AlignCenter, text)

        label(
            x, 30, panel_w, "Pb measurement bars · " + ("dark" if dark else "light"), 24
        )
        for column, (name, images) in enumerate(
            (("Previous · four peaks", previous), ("Installed · five zircon bars", installed))
        ):
            center = x + 560 + column * 1120
            label(center - 540, 78, 1080, name, 20)
            top = 135
            for size in REVIEW_SIZES:
                image = images[size]
                image.setDevicePixelRatio(1)
                p.drawImage(center - size // 2, top, image)
                label(center - 540, top + size + 4, 1080, f"{size} px · true size (1×)", 16)
                zoom = image.scaled(
                    size * 8,
                    size * 8,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )
                zoom_top = top + size + 48
                p.drawImage(center - size * 4, zoom_top, zoom)
                label(
                    center - 540,
                    zoom_top + size * 8 + 6,
                    1080,
                    "8× · nearest-neighbour",
                    16,
                )
                top += size * 9 + 120
    p.end()
    return sheet


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    converter = shutil.which("rsvg-convert")
    if not converter:
        raise RuntimeError("rsvg-convert is required to preserve the suite SVG shadow")
    print("PNG renderer:", converter)
    OUT.mkdir(parents=True, exist_ok=True)
    master = OUT / "icon.svg"
    master.write_text(b_peaks(), encoding="utf-8")
    small = OUT / "icon_small.svg"
    small.write_text(b_peaks(small=True), encoding="utf-8")
    tiny = OUT / "icon_tiny.svg"
    tiny.write_text(b_peaks(tiny=True), encoding="utf-8")
    for size in SIZES:
        source = tiny if size == 16 else small if size in SMALL_SIZES else master
        render(converter, source, size, OUT / f"icon_{size}.png")
    iconset = OUT / "pb_peaks.iconset"
    iconset.mkdir(exist_ok=True)
    for size, name in ICONSET:
        shutil.copyfile(OUT / f"icon_{size}.png", iconset / name)
    package_icns(iconset, OUT / "icon.icns")
    assets = ROOT / "src/idtims_app/assets"
    for suffix in (".svg", ".icns", *(f"_{s}.png" for s in SIZES)):
        shutil.copyfile(OUT / f"icon{suffix}", assets / f"app_icon{suffix}")
    installed = {s: QImage(str(assets / f"app_icon_{s}.png")) for s in REVIEW_SIZES}
    with tempfile.TemporaryDirectory(prefix="idtims-four-peaks-") as temp:
        previous = {
            s: render(converter, OUT / "icon_four_peaks.svg", s, Path(temp) / f"{s}.png")
            for s in REVIEW_SIZES
        }
    save(small_sizes_sheet(previous, installed), OUT / "final_small_sizes.png")
    print(
        "Installed five-bar zircon SVG, unlabelled 16/32/64 px, seven PNGs and ICNS; wrote",
        OUT / "final_small_sizes.png",
    )
    del app


if __name__ == "__main__":
    main()
