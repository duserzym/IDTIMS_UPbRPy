"""The app's name and chosen icon, in one place.

The name is still a working name; the icon is five coloured Pb bars of a
nominal zircon on ET535 (204, 205, 206, 207, 208), labelled at 128 px and above.
Every other module, the PyInstaller spec and the build script read these
values from here; renaming the app means editing this file only (plus the
entry-point name in pyproject.toml).
"""
from __future__ import annotations

from pathlib import Path

DISPLAY_NAME = "ID-TIMS Reduction (working name)"
"""Name shown in the window title, the About text and the macOS menu."""

BUNDLE_NAME = "ID-TIMS Reduction"
"""File-system name of the frozen app (no parentheses): `<BUNDLE_NAME>.app`."""

RAIL_NAME = "ID-TIMS"
"""Short name beside the icon at the top of the workflow rail."""

SLUG = "idtims-reduction"
"""Lower-case name for caches, sockets and settings files."""

ORGANISATION = "IDTIMS_UPbRPy"
"""Qt organisation name; QSettings are stored under it."""

BUNDLE_ID = "org.idtims-upbrpy.reduction"
"""macOS bundle identifier (placeholder)."""

URL_SCHEME = "idtims"
"""Future deep-link scheme (placeholder; not registered by any build yet)."""

PROJECT_EXTENSION = ".idtr"
"""Project file extension."""

ICON_PATH = Path(__file__).resolve().parent / "assets" / "app_icon.svg"
"""Five labelled zircon Pb bars; regenerate with tools/make_pb_peaks_icon.py."""

ICON_PNGS = {size: ICON_PATH.with_name(f"app_icon_{size}.png")
             for size in (16, 32, 64, 128, 256, 512, 1024)}
"""Direct SVG renders: unlabelled at 16/32/64 px, simplified further at 16 px."""

ICNS_PATH = ICON_PATH.with_suffix(".icns")
"""Chosen macOS bundle icon, including standard and Retina representations."""
