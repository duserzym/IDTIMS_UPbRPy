"""Chosen icon assets, small artwork selection and frozen-app icon wiring."""
import ast
import hashlib
import os
import struct
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
from pathlib import Path

import pytest

from idtims_app import branding

ROOT = Path(__file__).resolve().parents[1]
CHOSEN = ROOT / "docs/icon_options/pb_peaks"
HISTORICAL = ROOT / "docs/icon_options/filament_v2/filament_v2c"
# Pre-refinement v2c exports: these representations must remain byte-identical.
LARGE_HASHES = {
    64: "772487cbb6bd55a86f267d269da78eeef91b2241bc52e20bd7ff6e31a2fad5bc",
    128: "e39edad66cc87aeaffb78c7700671580069044a0297715954dc7cd11abb231b4",
    256: "7a0b17192668dc6b4d8900761574786f328074269a0b3ecac4b6c45a454cffc4",
    512: "d9b65c66287bdf40be1701196f758a95a3057055830849dba639c21211219312",
    1024: "776a1ac29eb133d89aec1d4bdd6c155237ff79e070d41139ad527fc09cede543",
}
# Five-bar zircon exports: tiny at 16, small at 32/64, labelled at 128+.
PEAK_HASHES = {
    16: "439c3e76ee89f4d5b25849fb89ab7828e6f524d0d99265a7ad60568fa6e6f968",
    32: "ea37876aa92a13282eb0895d66cfdcec4a73bdb95c914fe67b190b49176c3581",
    64: "16abb96cdc6bba7eb2c43e18f450d4b9d82c88f1c4ade595c3f75fe6dac33ce2",
    128: "6936dad1bb38e844760ea8b6419aae0ac95dbf3c44eec779c7f8e33054ed6e01",
    256: "d410b300f2837f55c378d3106f156d3b6bc23dd84a5ee2cbdaf99db0a5f7eef6",
    512: "da268de39256aef1f818db92e8f46978660b7c8f23d416115ab82e98922fe0e0",
    1024: "d4ae26eb19a15a07011e545e18eed453eb0658ab475f583bc46725a5097d34e3",
}
ENTRIES = {
    b"icp4": (16, "icon_16x16.png"),   # PNG fallback; iconutil uses ic04/ARGB
    b"ic11": (32, "icon_16x16@2x.png"),
    b"icp5": (32, "icon_32x32.png"),   # PNG fallback; iconutil uses ic05/ARGB
    b"ic12": (64, "icon_32x32@2x.png"),
    b"ic07": (128, "icon_128x128.png"),
    b"ic13": (256, "icon_128x128@2x.png"),
    b"ic08": (256, "icon_256x256.png"),
    b"ic14": (512, "icon_256x256@2x.png"),
    b"ic09": (512, "icon_512x512.png"),
    b"ic10": (1024, "icon_512x512@2x.png"),
}


def _check_png(data, size):
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    assert struct.unpack(">IIBBBBB", data[16:29]) == (size, size, 8, 6, 0, 0, 0)


def test_branding_icon_paths_exist():
    assert set(branding.ICON_PNGS) == {16, 32, 64, 128, 256, 512, 1024}
    for path in (branding.ICON_PATH, branding.ICNS_PATH, *branding.ICON_PNGS.values()):
        assert path.is_file(), path


def test_installed_icons_match_chosen_artwork():
    assert branding.ICON_PATH.read_bytes() == (CHOSEN / "icon.svg").read_bytes()
    assert branding.ICNS_PATH.read_bytes() == (CHOSEN / "icon.icns").read_bytes()
    for size, path in branding.ICON_PNGS.items():
        data = path.read_bytes()
        _check_png(data, size)
        assert data == (CHOSEN / f"icon_{size}.png").read_bytes()


def test_large_artwork_is_byte_identical_to_original_v2c():
    for size, expected in LARGE_HASHES.items():
        assert hashlib.sha256((HISTORICAL / f"icon_{size}.png").read_bytes()).hexdigest() == expected


def test_installed_pngs_match_approved_five_bar_renders():
    for size, expected in PEAK_HASHES.items():
        assert hashlib.sha256(branding.ICON_PNGS[size].read_bytes()).hexdigest() == expected


def test_iconset_has_exact_apple_names_sizes_and_rgba_format():
    iconset = CHOSEN / "pb_peaks.iconset"
    assert {p.name for p in iconset.iterdir()} == {name for _, name in ENTRIES.values()}
    for size, name in ENTRIES.values():
        data = (iconset / name).read_bytes()
        _check_png(data, size)
        assert data == branding.ICON_PNGS[size].read_bytes()


def test_icns_contains_every_standard_and_retina_representation():
    """Every size entry is present once. iconutil stores ic04/ic05 (16/32 px)
    as ARGB and re-encodes PNGs, so entries are checked by size, not bytes."""
    data = branding.ICNS_PATH.read_bytes()
    assert data[:4] == b"icns"
    assert struct.unpack(">I", data[4:8])[0] == len(data)
    offset, seen = 8, set()
    while offset < len(data):
        kind, length = struct.unpack(">4sI", data[offset:offset + 8])
        assert length > 8 and offset + length <= len(data)
        body = data[offset + 8:offset + length]
        kind = {b"ic04": b"icp4", b"ic05": b"icp5"}.get(kind, kind)
        if kind in ENTRIES:
            assert kind not in seen
            size, _ = ENTRIES[kind]
            if body[:4] == b"\x89PNG":
                _check_png(body, size)
            else:
                assert body[:4] == b"ARGB" and kind in (b"icp4", b"icp5")
            seen.add(kind)
        else:
            assert kind in (b"info", b"TOC "), kind   # metadata written by iconutil
        offset += length
    assert offset == len(data) and seen == set(ENTRIES)


@pytest.fixture(scope="module")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def test_icns_png_entries_decode_with_qt(qt_app):
    """Qt decodes the PNG fallback and iconutil output independently."""
    from PySide6.QtGui import QImageReader

    reader = QImageReader(str(branding.ICNS_PATH))
    assert reader.canRead() and reader.imageCount() >= 8
    sizes = []
    for index in range(reader.imageCount()):
        image = reader.read()
        assert not image.isNull(), reader.errorString()
        assert image.width() == image.height()
        sizes.append(image.width())
        if index < reader.imageCount() - 1:
            assert reader.jumpToNextImage()
    assert {64, 128, 256, 512, 1024} <= set(sizes)


def test_qicon_offers_all_sizes_and_selects_small_pngs(qt_app):
    from PySide6.QtGui import QImage

    from idtims_app.ui.icon import build_app_icon

    icon = build_app_icon()
    assert {s.width() for s in icon.availableSizes()} == set(branding.ICON_PNGS)
    for size in (16, 32, 64, 128, 512):
        pixmap = icon.pixmap(size, size)
        assert not pixmap.isNull() and pixmap.width() == pixmap.height() == size
        # QPixmap stores premultiplied alpha; compare in that format to avoid
        # rounding differences when converting translucent pixels back to RGB.
        actual = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        expected = QImage(str(branding.ICON_PNGS[size])).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        assert actual == expected


def test_small_png_differs_from_plain_large_downscale(qt_app):
    """Small renditions omit labels that would blur in a large PNG downscale."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    large = QImage(str(branding.ICON_PNGS[1024]))
    for size in (16, 32, 64):
        downscale = large.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        small = QImage(str(branding.ICON_PNGS[size]))
        assert small.convertToFormat(QImage.Format.Format_RGBA8888) != downscale.convertToFormat(QImage.Format.Format_RGBA8888)


def test_spec_uses_branding_icns_for_exe_and_bundle_and_bundles_assets():
    tree = ast.parse((ROOT / "packaging/IDTIMSReduction.spec").read_text())
    calls = {node.func.id: node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id in {"EXE", "BUNDLE"}}
    assert set(calls) == {"EXE", "BUNDLE"}
    for call in calls.values():
        icon = next(kw.value for kw in call.keywords if kw.arg == "icon")
        assert ast.unparse(icon) == "str(BRANDING['ICNS_PATH'])"
    data_files = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "data_files" for t in node.targets))
    assert any("idtims_app/assets" in ast.unparse(entry) for entry in data_files.elts)
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert {"assets/*.svg", "assets/*.png", "assets/*.icns"} <= set(
        config["tool"]["setuptools"]["package-data"]["idtims_app"])
