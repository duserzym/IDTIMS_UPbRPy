"""Command line for the app.

    idtims-app [PATH ...] [--open PATH] [--theme light|dark|system]
               [--settings JSON] [--confirm-no-oxide] [--diagnostic]
               [--step N] [--reduce]
               [--review-mode wetherill|tw] [--review-th on|off]
               [--date-kind KIND] [--exclude ID,ID,...]
               [--save-project PATH] [--export PNG [--size WxH]] [--verify-reduction SNAPSHOT_JSON]

Paths are projects or fraction CSVs (contract or legacy; content decides). `--settings`
loads reduction settings, `--confirm-no-oxide` confirms "no oxide correction
applies" for every fraction lacking the U oxide value, `--diagnostic` turns on
diagnostic covariance mode, `--step N` (1-8) opens that step if it is unlocked
and `--reduce` runs the reduction synchronously and shows the Reduce step
(unless `--step` names another). `--review-mode`, `--review-th`, `--date-kind`
(a key of IDTIMS_UPbRPy.dates.DATE_KINDS, e.g. "206Pb/238U") and `--exclude`
(fraction ids switched off) set the Review step (7) before it is shown, e.g.
`--reduce --step 7 --review-mode tw --exclude z3,z7`. `--export` renders the
window offscreen-ready to a PNG and exits, non-zero when a file or the settings could not be read or
a requested step is locked. `--verify-reduction` reduces the bundled synthetic example with
the snapshot settings and compares every number with the JSON (rel 1e-12),
non-zero on any mismatch; it needs no display.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def parse_size(text):
    """'1280x800' -> (1280, 800)."""
    try:
        width, height = (int(part) for part in text.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"size must look like 1280x800 (got {text!r})") from None
    if width < 200 or height < 200:
        raise argparse.ArgumentTypeError("size must be at least 200x200")
    return width, height


def build_parser():
    from idtims_app import branding

    parser = argparse.ArgumentParser(prog="idtims-app", description=branding.DISPLAY_NAME)
    parser.add_argument("paths", nargs="*", metavar="PATH",
                        help="Project or fraction CSV paths (content decides)")
    parser.add_argument("--open", action="append", default=[], metavar="PATH",
                        help="Open a project or fraction CSV on startup (may be repeated)")
    parser.add_argument("--theme", choices=["system", "light", "dark"],
                        help="Override the saved theme")
    parser.add_argument("--export", metavar="PNG",
                        help="Render the window to a PNG and exit (non-zero on load errors)")
    parser.add_argument("--size", type=parse_size, default=(1280, 800), metavar="WxH",
                        help="Window size for --export (default 1280x800)")
    parser.add_argument("--settings", metavar="JSON",
                        help="Load reduction settings (idtims-reduction-settings JSON)")
    parser.add_argument("--confirm-no-oxide", action="store_true",
                        help="Confirm that no oxide correction applies to fractions lacking it")
    parser.add_argument("--diagnostic", action="store_true",
                        help="Use diagnostic covariance mode (results not certified)")
    parser.add_argument("--step", type=int, metavar="N",
                        help="Open workflow step N (1-8) when it is unlocked")
    parser.add_argument("--reduce", action="store_true",
                        help="Reduce synchronously after loading (for --export)")
    parser.add_argument("--review-mode", choices=["wetherill", "tw"],
                        help="Concordia diagram on the Review step")
    parser.add_argument("--review-th", choices=["on", "off"],
                        help="Plot Th-corrected ratios on the concordia (when a Th correction "
                             "is set)")
    parser.add_argument("--date-kind", metavar="KIND",
                        help="Weighted-mean date on the Review step, e.g. '206Pb/238U'")
    parser.add_argument("--exclude", metavar="IDS",
                        help="Comma-separated fraction ids to switch off on the Review step")
    parser.add_argument("--verify-reduction", metavar="SNAPSHOT_JSON",
                        help="Reduce the bundled synthetic example and compare with the snapshot")
    parser.add_argument("--save-project", metavar="PATH", help="Save the prepared session as a project")
    parser.add_argument("--print-engine-fingerprint", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--print-project-status", metavar="PROJECT",
                        help="Open a project without a window and print its recomputed status")
    from idtims_app.labupdate.selftest import add_self_test_argument
    add_self_test_argument(parser)
    return parser


def export_window(window, output_path):
    """Show the window, let layouts settle and save a grab of it."""
    from PySide6 import QtCore, QtWidgets

    window.show()
    for _ in range(6):
        QtWidgets.QApplication.processEvents()
        # Widgets replaced by rebuilt panels are deleted only on DeferredDelete.
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    if not window.grab().save(str(output_path)):
        raise OSError(f"Could not write {output_path}")


def prepare_window(window, args, paths):
    """Apply the startup options in order; returns a list of error messages."""
    errors = []
    error = window.open_paths(paths) if paths else None
    if error:
        errors.append(error)
    session = window.session
    if args.confirm_no_oxide and session.has_table:
        session.confirm_all("missing_oxide")
        window._after_confirm()
    if args.settings:
        error = window.load_settings(args.settings)
        if error:
            errors.append(error)
    if args.diagnostic:
        session.set_strict_covariance(False)
        window.on_session_changed()
    if args.reduce:
        if not window.set_step(5):
            errors.append("Cannot reduce: an earlier step is not complete.")
        elif window.reduce_page.run_sync() is None:
            errors.append(window.reduce_page.banner.text() or "Reduction did not run.")
    errors += apply_review_options(window, args)
    if args.step is not None:
        if not window.set_step(args.step - 1):
            errors.append(f"Step {args.step} is locked or does not exist.")
    if args.save_project and not errors:
        if not window.save_project(args.save_project):
            errors.append(window.window_banner.text() or "Could not save project.")
    return errors


def apply_review_options(window, args):
    """Set the Review step's include set, diagram, Th toggle and date kind."""
    from IDTIMS_UPbRPy.dates import DATE_KINDS

    errors = []
    session = window.session
    if args.exclude:
        present = {r.fraction_id for r in session.reduction.results} \
            if session.reduction is not None else set()
        for fid in (part.strip() for part in args.exclude.split(",")):
            if not fid:
                continue
            if fid not in present:
                errors.append(f"--exclude: no reduced fraction {fid!r}.")
            session.set_included(fid, False)
    if args.review_mode:
        session.review_diagram = args.review_mode
    if args.review_th:
        session.review_th_ratios = args.review_th == "on"
    if args.date_kind:
        if args.date_kind not in DATE_KINDS:
            errors.append(f"--date-kind must be one of {', '.join(DATE_KINDS)}.")
        else:
            session.review_kind = args.date_kind
    if any((args.exclude, args.review_mode, args.review_th, args.date_kind)):
        window.review_page.run = None  # rebuild the page from the new state
        window.on_session_changed()
    return errors


def run_verification(snapshot):
    from idtims_app.verification import verify

    try:
        report, ok = verify(snapshot)
    except (OSError, ValueError) as exc:
        print(f"Verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


def main(argv=None):
    multiprocessing.freeze_support()
    args = build_parser().parse_args(argv)
    if args.update_self_test is not None:
        from idtims_app.labupdate.selftest import handle_self_test
        from idtims_app.update_config import update_config
        return handle_self_test(args, update_config())
    if args.print_engine_fingerprint:
        from idtims_app.project import engine_fingerprint, frozen_code_fingerprint
        engine = engine_fingerprint()
        first, second = frozen_code_fingerprint(), frozen_code_fingerprint()
        frozen = bool(getattr(sys, "frozen", False))
        match = first == second and (not frozen or bool(first))
        print(json.dumps({"engine": engine, "frozen_code_first": first,
                          "frozen_code_second": second, "match": match, "frozen": frozen}))
        return 0 if match else 1
    if args.print_project_status:
        from idtims_app import project
        try:
            session = project.restore(project.read(args.print_project_status))
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"Could not open project: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"engine_note": session.engine_note,
                          "reduced": [r.fraction_id for r in session.reduction.results if r.reduced]
                                     if session.reduction else [],
                          "included": session.included_ids()}))
        return 0
    if args.verify_reduction:
        return run_verification(args.verify_reduction)

    from PySide6 import QtCore, QtWidgets

    from idtims_app.launch import FileOpenFilter, SingleInstance
    from idtims_app.ui.icon import build_app_icon
    from idtims_app.ui.theme import apply_theme, build_application
    from idtims_app.window import MainWindow, app_settings

    paths = [*args.paths, *args.open]
    settings = app_settings()
    theme_mode = args.theme or str(settings.value("theme_mode", "light") or "light")
    app = build_application(sys.argv[:1], theme_mode=theme_mode)

    instance = None if args.export else SingleInstance()
    if instance is not None and paths and instance.send(json.dumps(paths)):
        return 0

    icon = build_app_icon()
    app.setWindowIcon(icon)
    window = MainWindow(theme_mode=theme_mode, app_icon=icon, confirm_close=not args.export)

    if args.export:
        window.resize(*args.size)
        window.show()
        QtWidgets.QApplication.processEvents()
        errors = prepare_window(window, args, paths)
        for error in errors:
            print(error, file=sys.stderr)
        export_window(window, args.export)
        return 1 if errors else 0

    def follow_system(*_args):
        if window.theme_mode == "system":
            apply_theme(app, "system")
            window.refresh_theme()

    try:
        app.styleHints().colorSchemeChanged.connect(follow_system)
    except AttributeError:
        pass

    def receive(value):
        try:
            received = json.loads(value)
        except ValueError:
            received = [value]
        window.open_paths([str(p) for p in received])
        window.raise_()
        window.activateWindow()

    if instance is not None:
        instance.received.connect(receive)
        instance.listen()
    file_open_filter = FileOpenFilter(lambda value: window.open_paths([value]), app)
    app.installEventFilter(file_open_filter)

    screen = app.primaryScreen()
    available = screen.availableGeometry() if screen else QtCore.QRect(0, 0, 1280, 800)
    window.resize(min(1280, available.width()), min(800, available.height()))
    window.move(available.center() - window.rect().center())
    window.show()
    for error in prepare_window(window, args, paths):
        window.statusBar().showMessage(error, 10000)
    try:
        return app.exec()
    finally:
        if instance is not None:
            instance.close()


if __name__ == "__main__":
    raise SystemExit(main())
