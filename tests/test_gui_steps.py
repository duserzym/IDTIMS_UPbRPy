"""Offscreen GUI tests of steps 2 to 6 (Tracer, Fractionation, Blanks, Th, Reduce).

Built like tests/test_gui_import.py (copied `build_application`, no
pytest-qt); skipped when PySide6 or pyqtgraph is not installed.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from gui_support import require_gui

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
require_gui()

from PySide6 import QtCore, QtWidgets  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_gui_import import _layout_problems  # noqa: E402

SYNTHETIC = ROOT / "examples" / "synthetic_zircon_CA-ID-TIMS.csv"
SYNTHETIC_SETTINGS = ROOT / "examples" / "synthetic_settings.json"
TEMPLATE = ROOT / "tests" / "data" / "synthetic_template_2535.csv"
TEMPLATE_SETTINGS = ROOT / "tests" / "data" / "settings_BSU_template.json"


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    os.environ["IDTIMS_APP_SETTINGS"] = str(tmp_path_factory.mktemp("settings") / "app.ini")
    from idtims_app.ui.theme import build_application

    return build_application(["idtims-app-tests"], theme_mode="light")


def settle(rounds=5):
    for _ in range(rounds):
        QtWidgets.QApplication.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)


@pytest.fixture
def make_window(app):
    from idtims_app.window import MainWindow

    windows = []

    def factory(size=(1280, 800), path=TEMPLATE, settings=TEMPLATE_SETTINGS, confirm=True):
        window = MainWindow(confirm_close=False)
        window.resize(*size)
        window.show()
        settle()
        if path:
            assert window.open_paths([str(path)]) is None
        if confirm:
            window._confirm_all("missing_oxide")
        if settings:
            assert window.load_settings(str(settings)) is None
        settle()
        windows.append(window)
        return window

    yield factory
    for window in windows:
        window.close()
        window.deleteLater()
    settle()


def field(page, section, name):
    return next(f for f in page.fields if (f.section, f.name) == (section, name))


@pytest.mark.parametrize("size", [(1280, 800), (1024, 640)])
def test_every_step_renders_and_fits(make_window, size):
    window = make_window(size)
    for step in range(5):
        assert window.session.step_complete(step), step
    assert window.set_step(5)
    assert window.reduce_page.run_sync() is not None
    settle()
    for step in range(6):
        assert window.set_step(step), step
        settle()
        assert window.pages.currentWidget() is window.step_pages[step]
        assert window.minimumSizeHint().width() <= size[0]
        assert window.minimumSizeHint().height() <= size[1]
        assert _layout_problems(window) == [], (step, size)


def test_steps_unlock_in_order_with_default_settings(make_window):
    window = make_window(path=SYNTHETIC, settings=None, confirm=False)
    assert window.session.unlocked(1) and window.session.unlocked(3)
    # Default initial Pb has no ratios, so Blanks is not complete and Th stays locked.
    assert not window.session.step_complete(3)
    assert not window.set_step(4)
    assert window.set_step(3)
    settle()
    page = window.blanks_page
    assert "Initial Pb 206Pb/204Pb is missing." in field(page, "common_pb", "R64c").problems.text()
    assert field(page, "common_pb", "R64c").problems.isVisible()


def test_tracer_page_edits_fill_down_and_version(make_window):
    window = make_window()
    assert window.set_step(1)
    page = window.tracer_page
    settle()
    assert page.model.rowCount() == 6
    model, selection = page.model, page.table.selectionModel()
    column = 2  # Spike Weight (g)
    assert model.setData(model.index(0, column), "0.02")
    selection.clearSelection()
    for row in range(3):
        selection.select(model.index(row, column), QtCore.QItemSelectionModel.SelectionFlag.Select)
    page.fill_down()
    assert [window.session.value(r, "Spike Weight (g)") for r in range(3)] == [0.02] * 3
    selection.clearSelection()
    for row in (4, 5):
        selection.select(model.index(row, 1), QtCore.QItemSelectionModel.SelectionFlag.Select)
    page.apply_column.setCurrentIndex(page.apply_column.findData("Sample Weight (mg)"))
    page.apply_value.setEditText("0.007")
    page.apply_to_selected()
    assert [window.session.value(r, "Sample Weight (mg)") for r in (4, 5)] == [0.007] * 2
    page.version_combo.setCurrentIndex(page.version_combo.findData("v1"))
    assert window.session.settings.spike_version == "v1"
    assert "has no table version 'v1'" in page.status.text()
    assert not window.session.step_complete(1)
    page.version_combo.setCurrentIndex(0)
    assert window.session.step_complete(1)
    assert page.tracer_source.text().endswith("ET2535_v3.csv")


def test_fractionation_shows_2535_fpb(make_window):
    window = make_window()
    assert window.set_step(2)
    table = window.fractionation_page.table_2535
    assert table.rowCount() == 6 and table.item(0, 0).text() == "z1"
    assert table.item(0, 5).text() == "0.233377"


def test_settings_edit_validate_save_load_round_trip(make_window, tmp_path):
    window = make_window()
    assert window.set_step(3)
    page = window.blanks_page
    blank = field(page, "lab_blanks", "Pb_blank_total")
    blank.setText("12.5")
    blank.commit()
    assert window.session.settings.lab_blanks.Pb_blank_total == 12.5
    blank.setText("abc")
    blank.commit()
    assert "is not a number" in blank.problems.text()
    assert window.session.settings.lab_blanks.Pb_blank_total == 12.5
    blank.setText("-1")
    blank.commit()
    assert "cannot be negative" in blank.problems.text()
    assert not window.session.step_complete(3)
    blank.setText("12.5")
    blank.commit()
    assert not blank.problems.isVisible()
    page.sk_radio.setChecked(True)
    age = field(page, "common_pb", "age_Ga")
    age.setText("0.5")
    age.commit()
    assert page.sk_labels["R64c"].text() != "–"
    path = tmp_path / "settings.json"
    assert window.save_settings(str(path))
    saved = json.loads(path.read_text())
    assert saved["lab_blanks"]["Pb_blank_total"] == 12.5
    assert saved["common_pb"]["model"] == "stacey_kramers"
    window.reset_settings()
    assert window.session.settings.lab_blanks.Pb_blank_total == 0.0
    assert blank.text() == "0.0"
    assert window.load_settings(str(path)) is None
    assert blank.text() == "12.5" and page.sk_radio.isChecked()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert window.load_settings(str(bad))
    assert window.window_banner.isVisible()
    assert window.session.settings.lab_blanks.Pb_blank_total == 12.5


def test_th_page_kinds_and_constants(make_window):
    window = make_window()
    assert window.set_step(4)
    page = window.th_page
    assert page.kind_buttons["D"].isChecked()
    assert page.constants.item(3, 0).text() == "λ230"
    assert page.constants.item(3, 1).text() == "9.195e-06"
    page.kind_buttons[None].setChecked(True)
    assert window.session.settings.th_correction.kind is None
    assert not page.d_fields[0].isEnabled()
    page.kind_buttons["magma"].setChecked(True)
    magma = field(page, "th_correction", "Th_U_magma")
    magma.setText("")
    magma.commit()
    assert "Th/U of the magma is missing." in magma.problems.text()
    assert not window.session.step_complete(4)


def test_reduce_in_worker_and_diagnostic_banner(make_window, tmp_path):
    from idtims_app.reduction import NOT_REDUCED, REDUCED

    window = make_window()
    assert window.set_step(5)
    page = window.reduce_page
    assert not page.diagnostic_banner.isVisible()
    page.start()
    assert page.wait()
    settle()
    model = page.model
    assert model.rowCount() == 6
    statuses = [model.result(r).status for r in range(6)]
    assert statuses == [NOT_REDUCED, REDUCED, REDUCED, REDUCED, REDUCED, NOT_REDUCED]
    assert "Impossible covariance" in model.data(model.index(0, 8))
    assert model.data(model.index(0, 0), QtCore.Qt.ItemDataRole.DecorationRole) is not None
    assert "z1" in page.details.text() and "per-project choice" in page.details.text()
    assert window.session.step_complete(5) and window.session.unlocked(6)
    assert page.export_to(str(tmp_path / "full.csv"))
    page.diagnostic_check.setChecked(True)
    settle()
    assert page.diagnostic_banner.isVisible()
    assert not window.session.strict_covariance
    assert "Out of date" in page.mode_label.text()
    page.run_sync()
    assert {model.result(r).status for r in range(6)} == {"reduced", "diagnostic"}
    page.diagnostic_check.setChecked(False)
    settle()
    assert not page.diagnostic_banner.isVisible()
    assert window.session.strict_covariance


def _run_app(*arguments, settings_dir):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
               IDTIMS_APP_SETTINGS=str(settings_dir / "app.ini"),
               PYTHONPATH=str(ROOT / "src"))
    return subprocess.run([sys.executable, "-m", "idtims_app", "--theme", "light", *arguments],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)


def test_export_command_with_settings_step_and_reduce(tmp_path):
    png = tmp_path / "reduce.png"
    result = _run_app(str(TEMPLATE), "--settings", str(TEMPLATE_SETTINGS), "--confirm-no-oxide",
                      "--reduce", "--diagnostic", "--export", str(png), settings_dir=tmp_path)
    assert result.returncode == 0, result.stderr
    assert png.stat().st_size > 10_000
    locked = _run_app(str(SYNTHETIC), "--step", "5", "--export", str(tmp_path / "locked.png"),
                      settings_dir=tmp_path)
    assert locked.returncode == 1 and "Step 5 is locked" in locked.stderr
