"""Render the UI round's light screenshots using the app's normal export path.

Run with .venv/bin/python scripts/render_ui_round.py. Every child gets isolated
settings and autosaves; the 40-row stress CSV is temporary. The maximised shot
uses the same prepare_window/export_window helpers and the real panel action.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from run_tests import INPUTS, STEP_SHOTS, environment
from ui_round_support import long_fraction_fixture

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/screenshots"
TEMPLATE = [ROOT / "tests/data/synthetic_template_2535.csv", "--settings",
            ROOT / "tests/data/settings_BSU_template.json", "--confirm-no-oxide",
            "--reduce", "--step", "7"]


def maximised_export(output):
    from PySide6 import QtCore, QtWidgets
    from idtims_app.main import build_parser, prepare_window, export_window
    from idtims_app.ui.theme import build_application
    from idtims_app.window import MainWindow

    args = build_parser().parse_args([*[str(value) for value in TEMPLATE], "--theme", "light",
                                      "--export", str(output), "--size", "1280x800"])
    app = build_application([], theme_mode="light")
    window = MainWindow(theme_mode="light", confirm_close=False)
    window.resize(*args.size)
    window.show()
    app.processEvents()
    errors = prepare_window(window, args, args.paths)
    if errors:
        raise RuntimeError("; ".join(errors))
    for _ in range(6):
        app.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    page = window.review_page
    page.work_area.toggle_panel(page.concordia_card, keyboard=True)
    export_window(window, output)
    window.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--maximised-export", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--only", nargs="*", help="Render only these image stems (for iteration)")
    args = parser.parse_args()
    if args.maximised_export:
        maximised_export(args.maximised_export)
        return 0
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="idtims-ui-round-") as directory:
        temporary = Path(directory)
        fixture = long_fraction_fixture(temporary / "forty.csv")
        shots = {f"import_{name}": paths for name, paths in INPUTS.items()}
        shots.update(STEP_SHOTS)
        renders = [(f"app_{name}_1280x800", arguments, "1280x800")
                   for name, arguments in shots.items()]
        renders += [
            ("app_review_template2535_strict_1024x640", TEMPLATE, "1024x640"),
            ("app_review_template2535_strict_1440x900", TEMPLATE, "1440x900"),
            ("app_review_40fractions_1280x800", [fixture, *TEMPLATE[1:]], "1280x800"),
            ("app_review_template2535_strict_maximised_concordia_1280x800", None, "1280x800"),
        ]
        for stem, arguments, size in renders:
            if args.only is not None and stem not in args.only:
                continue
            settings = temporary / stem
            settings.mkdir()
            env = environment(settings)
            env["UPBRPY_REDUCE_MOTION"] = "1"
            output = OUTPUT / f"{stem}.png"
            command = ([sys.executable, __file__, "--maximised-export", output]
                       if arguments is None else
                       [sys.executable, "-m", "idtims_app", "--theme", "light", *arguments,
                        "--size", size, "--export", output])
            result = subprocess.run([str(value) for value in command], cwd=ROOT, env=env)
            if result.returncode or not output.exists() or output.stat().st_size < 10_000:
                raise RuntimeError(f"Screenshot failed: {stem}")
            print(output.relative_to(ROOT), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
