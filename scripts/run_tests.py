"""Test tiers for the engine and the app (see docs/testing.md).

    python scripts/run_tests.py quick         # every pytest test, offscreen (about 15 s)
    python scripts/run_tests.py full          # quick + verify_derivation + screenshot exports
    python scripts/run_tests.py full --build  # ... + the frozen-app build and smoke test
    python scripts/run_tests.py screenshots   # write docs/screenshots/app_*_1280x800.png

Run with the repository venv (.venv/bin/python). GUI tests skip themselves
when PySide6 is not installed.
"""
from __future__ import annotations

import argparse
import os
import runpy
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRANDING = runpy.run_path(str(ROOT / "src" / "idtims_app" / "branding.py"))
INPUTS = {
    "empty": [],
    "MA1": [ROOT / "examples" / "synthetic_zircon_CA-ID-TIMS.csv"],
    "template2535": [ROOT / "tests" / "data" / "synthetic_template_2535_oxide.csv"],
}
_SYNTHETIC = [ROOT / "examples" / "synthetic_zircon_CA-ID-TIMS.csv", "--settings",
        ROOT / "examples" / "synthetic_settings.json"]
_TEMPLATE = [ROOT / "tests" / "data" / "synthetic_template_2535.csv", "--settings",
             ROOT / "tests" / "data" / "settings_BSU_template.json"]
# Steps 2 to 8: name -> app arguments (the --export options are added).
STEP_SHOTS = {
    "export_template2535": [ROOT / "tests/data/synthetic_template_2535_oxide.csv", "--settings",
                            ROOT / "tests/data/settings_BSU_template.json",
                            "--reduce", "--step", "8"],
    "export_SYNTHETIC_diagnostic": [*_SYNTHETIC, "--confirm-no-oxide", "--diagnostic", "--reduce", "--step", "8"],
    "tracer_SYNTHETIC": [*_SYNTHETIC, "--step", "2"],
    "fractionation_template2535": [*_TEMPLATE, "--step", "3"],
    "blanks_SYNTHETIC": [*_SYNTHETIC, "--step", "4"],
    "th_SYNTHETIC": [*_SYNTHETIC, "--step", "5"],
    "reduce_template2535_strict": [*_TEMPLATE, "--confirm-no-oxide", "--reduce"],
    "reduce_template2535_diagnostic": [*_TEMPLATE, "--confirm-no-oxide", "--diagnostic",
                                       "--reduce"],
    "review_SYNTHETIC_diagnostic_wetherill": [*_SYNTHETIC, "--confirm-no-oxide", "--diagnostic", "--reduce",
                                        "--step", "7"],
    "review_SYNTHETIC_diagnostic_tw": [*_SYNTHETIC, "--confirm-no-oxide", "--diagnostic", "--reduce",
                                 "--step", "7", "--review-mode", "tw"],
    "review_template2535_strict": [*_TEMPLATE, "--confirm-no-oxide", "--reduce", "--step", "7"],
    "review_template2535_strict_z3_z5_off": [*_TEMPLATE, "--confirm-no-oxide", "--reduce",
                                             "--step", "7", "--exclude", "z3,z5"],
}


def environment(settings_dir):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
               IDTIMS_APP_SETTINGS=str(Path(settings_dir) / "app.ini"),
               IDTIMS_AUTOSAVE_DIR=str(Path(settings_dir) / "autosave"))
    env["PYTHONPATH"] = os.pathsep.join(p for p in [str(ROOT / "src"),
                                                    os.environ.get("PYTHONPATH", "")] if p)
    return env


def run(command, env):
    print("$", " ".join(str(c) for c in command), flush=True)
    return subprocess.run([str(c) for c in command], cwd=ROOT, env=env).returncode


def export_screenshots(output, sizes, env):
    """Write <output>/app_import_<name>_<W>x<H>.png and app_<step shot>_<W>x<H>.png."""
    output.mkdir(parents=True, exist_ok=True)
    failures = 0
    shots = {f"import_{name}": paths for name, paths in INPUTS.items()}
    shots.update(STEP_SHOTS)
    for width, height in sizes:
        for name, arguments in shots.items():
            png = output / f"app_{name}_{width}x{height}.png"
            code = run([sys.executable, "-m", "idtims_app", "--theme", "light", *arguments,
                        "--export", png, "--size", f"{width}x{height}"], env)
            if code != 0 or not png.exists() or png.stat().st_size < 10_000:
                print(f"FAILED: {png}")
                failures += 1
            else:
                print(f"  {png} ({png.stat().st_size // 1024} kB)")
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tier", choices=["quick", "full", "screenshots"])
    parser.add_argument("--build", action="store_true",
                        help="full: also build the frozen app and run its smoke test")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as settings_dir:
        env = environment(settings_dir)
        if args.tier == "screenshots":
            return 1 if export_screenshots(ROOT / "docs" / "screenshots", [(1280, 800)], env) else 0
        code = run([sys.executable, "-m", "pytest", "-q"], env)
        if args.tier == "quick" or code:
            return code
        code = run([sys.executable, "tools/verify_derivation.py"], env)
        if code:
            return code
        cache = Path.home() / "Library" / "Caches" if sys.platform == "darwin" else \
            Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
        output = Path(os.environ["IDTIMS_SCREENSHOT_DIR"]).expanduser() \
            if os.environ.get("IDTIMS_SCREENSHOT_DIR") else cache / BRANDING["SLUG"] / "screenshots"
        if export_screenshots(output, [(1280, 800), (1440, 900)], env):
            return 1
        if args.build:
            return run([sys.executable, "scripts/build_desktop.py", "--smoke-test"], env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
