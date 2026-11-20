"""PyInstaller 6 recipe for the ID-TIMS reduction app (placeholder name).

Names, bundle id and icon come from src/idtims_app/branding.py. Build with
`python scripts/build_desktop.py`, which puts everything under
~/Library/Caches/<slug>/<checkout hash>/, never inside the repository.
Modelled on UPbRPy Studio's packaging/UPbRPyStudio.spec (commit f8c561f).
"""

from __future__ import annotations

from pathlib import Path
import os
import runpy
import sys
import tomllib

from PyInstaller.utils.hooks import collect_submodules

PACKAGING_DIRECTORY = Path(SPECPATH).resolve()
PROJECT_ROOT = PACKAGING_DIRECTORY.parent
SOURCE = PROJECT_ROOT / "src"
BRANDING = runpy.run_path(str(SOURCE / "idtims_app" / "branding.py"))
PROJECT_VERSION = tomllib.loads(
    (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
)["project"]["version"]
APPLICATION_NAME = BRANDING["BUNDLE_NAME"]
FINGERPRINT_FILE = Path(os.environ["IDTIMS_ENGINE_SOURCE_FINGERPRINT"])
if FINGERPRINT_FILE.name != "engine_source_fingerprint.txt" or not FINGERPRINT_FILE.is_file():
    raise ValueError("Build requires the generated engine_source_fingerprint.txt from build_desktop.py")

data_files = [
    (str(FINGERPRINT_FILE), "idtims_app"),
    (str(SOURCE / "IDTIMS_UPbRPy" / "spike_compositions" / "*.csv"),
     "IDTIMS_UPbRPy/spike_compositions"),
    (str(SOURCE / "IDTIMS_UPbRPy" / "spike_registry"), "IDTIMS_UPbRPy/spike_registry"),
    (str(PROJECT_ROOT / "examples" / "synthetic_zircon_CA-ID-TIMS.csv"), "idtims_app/examples"),
    (str(SOURCE / "idtims_app" / "assets"), "idtims_app/assets"),
    (str(SOURCE / "idtims_app" / "ui" / "assets" / "icons"), "idtims_app/ui/assets/icons"),
]

hidden_imports = [
    "PySide6.QtSvg",
    "PySide6.QtNetwork",
    # As Studio's spec: pyqtgraph loads its exporters lazily (plot context menu).
    *collect_submodules("pyqtgraph.exporters"),
    *collect_submodules("IDTIMS_UPbRPy"),
    *collect_submodules("idtims_app"),
]

analysis = Analysis(
    [str(PACKAGING_DIRECTORY / "launch_app.py")],
    pathex=[str(SOURCE)],
    binaries=[],
    datas=data_files,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython", "bokeh", "jedi", "jupyterlab", "matplotlib", "nbformat", "notebook",
        "numba", "llvmlite", "panel", "pygments", "pytest", "selenium",
        "tkinter", "traitlets", "zmq", "xlrd",
    ],
    noarchive=False,
    optimize=1,
)

python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name=APPLICATION_NAME,
    icon=str(BRANDING["ICNS_PATH"]),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

application_directory = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APPLICATION_NAME,
)

if sys.platform == "darwin":
    application_bundle = BUNDLE(
        application_directory,
        name=f"{APPLICATION_NAME}.app",
        icon=str(BRANDING["ICNS_PATH"]),
        bundle_identifier=BRANDING["BUNDLE_ID"],
        version=PROJECT_VERSION,
        info_plist={
            "CFBundleDisplayName": BRANDING["DISPLAY_NAME"],
            "CFBundleName": APPLICATION_NAME,
            "CFBundleShortVersionString": PROJECT_VERSION,
            "CFBundleVersion": PROJECT_VERSION,
            "LSApplicationCategoryType": "public.app-category.education",
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
        },
    )
