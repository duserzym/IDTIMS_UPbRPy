"""Offscreen GUI tests of the main window and the Import step.

The app is built through the copied `build_application` in a module fixture
(Studio's convention; no pytest-qt). Skipped when PySide6 or pyqtgraph is not
installed, so the engine-only CI still runs.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6 import QtCore, QtWidgets  # noqa: E402

from IDTIMS_UPbRPy.fractions import CONTRACT, read_fractions  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data"
SYNTHETIC = ROOT / "examples" / "synthetic_zircon_CA-ID-TIMS.csv"
TEMPLATE = DATA / "synthetic_template_2535.csv"


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

    def factory(size=(1280, 800), paths=()):
        window = MainWindow(confirm_close=False)
        window.resize(*size)
        window.show()
        settle()
        if paths:
            assert window.open_paths([str(p) for p in paths]) is None
            settle()
        windows.append(window)
        return window

    yield factory
    for window in windows:
        window.close()
        window.deleteLater()
    settle()


def _in_scrolled_content(widget):
    parent = widget.parentWidget()
    while parent is not None:
        grand = parent.parentWidget()
        if isinstance(grand, QtWidgets.QAbstractScrollArea) and grand.viewport() is parent:
            return True
        parent = grand
    return False


def _layout_problems(window):
    problems = []
    bounds = window.rect()
    for widget in window.findChildren(QtWidgets.QWidget):
        if not widget.isVisible() or widget.window() is not window or _in_scrolled_content(widget):
            continue
        rect = QtCore.QRect(widget.mapTo(window, QtCore.QPoint(0, 0)), widget.size())
        if not bounds.contains(rect):
            problems.append(f"{type(widget).__name__} {widget.objectName()!r} at {rect} "
                            f"outside {bounds}")
        if isinstance(widget, QtWidgets.QAbstractButton) and widget.text():
            if widget.width() + 1 < widget.minimumSizeHint().width():
                problems.append(f"button {widget.text()!r} clipped: {widget.width()} < "
                                f"{widget.minimumSizeHint().width()}")
    return problems


@pytest.mark.parametrize("size", [(1280, 800), (1440, 900), (1024, 640), (1120, 700), (1180, 740)])
@pytest.mark.parametrize("paths", [(), (TEMPLATE,)], ids=["empty", "template"])
def test_window_fits(make_window, size, paths):
    window = make_window(size, paths)
    assert (window.width(), window.height()) == size
    # In the layout chosen for this size, nothing asks for more room than there is.
    assert window.minimumSizeHint().width() <= size[0]
    assert window.minimumSizeHint().height() <= size[1]
    assert _layout_problems(window) == []


def test_rail_collapses_and_inspector_hides_on_small_windows(make_window):
    wide = make_window((1280, 800))
    assert not wide.workflow_list.property("compactRail")  # Laptop defaults now show labels.
    assert not wide.import_page.issues_card.isVisible()
    small = make_window((1024, 640))
    assert small.workflow_list.property("compactRail")
    assert not small.inspector.isVisible()
    small.set_inspector_visible(True)
    settle()
    assert small.inspector.isVisible() and _layout_problems(small) == []


def test_steps_locked_until_import_complete(make_window):
    window = make_window()
    assert window.workflow_list.count() == 8
    assert not window.next_button.isEnabled()
    for row in range(1, 8):
        assert not window.workflow_list.item(row).flags() & QtCore.Qt.ItemFlag.ItemIsEnabled
    window.go_to_step(1)
    assert window.workflow_list.currentRow() == 0


def test_open_synthetic_unlocks_step_two(make_window):
    window = make_window(paths=[SYNTHETIC])
    assert window.import_page.model.rowCount() == 12
    assert window.workflow_list.item(1).flags() & QtCore.Qt.ItemFlag.ItemIsEnabled
    # Default settings: Blanks (step 4) is incomplete, so step 5 stays locked.
    assert window.workflow_list.item(3).flags() & QtCore.Qt.ItemFlag.ItemIsEnabled
    assert not window.workflow_list.item(4).flags() & QtCore.Qt.ItemFlag.ItemIsEnabled
    assert window.next_button.isEnabled()
    window.next_action.trigger()
    assert window.workflow_list.currentRow() == 1 and window.pages.currentIndex() == 1
    window.back_action.trigger()
    assert window.workflow_list.currentRow() == 0


def test_template_marks_z1_and_z6(make_window):
    from idtims_app.widgets.fraction_table import QUALITY_ROLE

    window = make_window(paths=[TEMPLATE])
    model = window.import_page.model
    marked = {}
    for row in range(model.rowCount()):
        index = model.index(row, 0)
        fid = model.data(index)
        marked[fid] = model.data(index, QUALITY_ROLE)
        if marked[fid]:
            assert model.data(index, QtCore.Qt.ItemDataRole.DecorationRole) is not None
            tip = model.data(index, QtCore.Qt.ItemDataRole.ToolTipRole)
            assert "204/205 = (206/205)*(204/206)" in tip and "must lie between" in tip
    assert {f for f, bad in marked.items() if bad} == {"z1", "z6"}
    column = model.columns.index("204Pb/205Pb % Standard Error")
    z1 = window.session.row_of("z1")
    assert model.data(model.index(z1, column), QtCore.Qt.ItemDataRole.BackgroundRole) is not None
    card = window.issues_panel.card_for("z1")
    assert card is not None
    texts = " ".join(label.text() for label in card.findChildren(QtWidgets.QLabel))
    assert "Linked-error check failed" in texts and "0.166805" in texts


def test_confirm_controls(make_window, tmp_path):
    path = tmp_path / "inferred.fractions.csv"
    path.write_text(f"Contract,Fraction ID,202Pb/205Pb Mean,202Pb/205Pb % Standard Error\n"
                    f"{CONTRACT},z1,0.5,0.01\n", encoding="utf-8")
    window = make_window(paths=[path])
    card = window.issues_panel.card_for("z1")
    button = card.findChild(QtWidgets.QPushButton, "ConfirmSpikeType")
    button.click()
    settle()
    assert window.session.value(0, "Spike Type") == "2535"
    assert not any(i.kind == "unconfirmed_spike_type" for i in window.session.issues())

    other = make_window(paths=[SYNTHETIC])
    bulk = other.issues_panel.findChild(QtWidgets.QPushButton, "ConfirmAll_missing_oxide")
    bulk.click()
    settle()
    assert not any(i.kind == "missing_oxide" for i in other.session.issues())


def test_template_issues_group_cycle_notes_below_two_failure_cards(make_window):
    window = make_window(paths=[DATA / "synthetic_template_2535_oxide.csv"])
    panel = window.issues_panel
    original = window.session.issues()
    assert set(panel._cards) == {"z1", "z6"}
    assert [panel.cards_layout.itemAt(i).widget().property("fraction") for i in range(2)] == ["z1", "z6"]
    for card in panel._cards.values():
        text = " ".join(label.text() for label in card.findChildren(QtWidgets.QLabel))
        assert "Linked-error check failed" in text
        assert "accepted-cycle" not in text
    notes = panel.findChildren(QtWidgets.QLabel, "GroupedNote")
    assert len(notes) == 1
    assert notes[0].text() == "Cycle selection not recorded (Pb and U): all 6 fractions"
    assert window.issue_notes.text() == "1 note"
    assert "Pb the accepted-cycle selection is not recorded" in notes[0].toolTip()
    assert "U the accepted-cycle selection is not recorded" in notes[0].toolTip()
    assert "shared mask avoids this" in notes[0].toolTip()
    assert panel.cards_layout.itemAt(2).widget().objectName() == "GroupedNotes"
    # The same inspector is used in the other steps; grouping is display-only.
    window.go_to_step(1)
    settle()
    assert window.issues_panel is panel
    assert len(panel.findChildren(QtWidgets.QLabel, "GroupedNote")) == 1
    assert window.session.issues() == original


def test_issue_grouping_keeps_distinct_notes_and_blocking_issues_local(make_window, monkeypatch):
    from IDTIMS_UPbRPy.fractions import FractionIssue

    window = make_window(paths=[DATA / "synthetic_template_2535_oxide.csv"])
    issues = [FractionIssue(fid, "mean_statistic_note", f"{fid}: Shared explanation.")
              for fid in ("z1", "z2")]
    issues += [FractionIssue(fid, "oxide_formula_note", f"{fid}: Oxide value is {value}.")
               for fid, value in (("z3", "0.002"), ("z4", "0.003"))]
    issues += [FractionIssue(fid, "missing_setup", f"{fid}: Required input is missing.")
               for fid in ("z5", "z6")]
    monkeypatch.setattr(window.session, "issues", lambda: issues)
    monkeypatch.setattr(window.session, "quality_failures", lambda: [])
    panel = window.issues_panel
    panel.rebuild()
    settle()
    assert set(panel._cards) == {"z3", "z4", "z5", "z6"}
    assert [panel.cards_layout.itemAt(i).widget().property("fraction") for i in range(2)] == ["z5", "z6"]
    for fid, value in (("z3", "0.002"), ("z4", "0.003")):
        assert value in " ".join(label.text() for label in panel.card_for(fid).findChildren(QtWidgets.QLabel))
    notes = panel.findChildren(QtWidgets.QLabel, "GroupedNote")
    assert len(notes) == 1 and notes[0].text() == "Shared explanation: z1, z2"
    assert "Required input" not in notes[0].toolTip()


def test_merge_pb_only_and_u_only(make_window):
    window = make_window(paths=[DATA / "synthetic_pb_only.fractions.csv"])
    assert not window.next_button.isEnabled()
    assert window.open_paths([str(DATA / "synthetic_u_only.fractions.csv")]) is None
    settle()
    assert window.import_page.model.rowCount() == 2
    assert window.session.summary()["ready"] == 2
    assert window.next_button.isEnabled()


def test_conflict_shown_inline(make_window, tmp_path):
    window = make_window(paths=[DATA / "synthetic_pb_only.fractions.csv"])
    other = tmp_path / "other.fractions.csv"
    other.write_text(f"Contract,Fraction ID,Sample\n{CONTRACT},z1,SYN-2\n", encoding="utf-8")
    error = window.open_paths([str(other)])
    settle()
    banner = window.import_page.banner
    assert error and banner.isVisible()
    assert "z1" in banner.text() and "Sample" in banner.text()
    assert QtWidgets.QApplication.activeModalWidget() is None
    assert window.import_page.model.rowCount() == 2


def test_paste_into_new_table(make_window, app):
    window = make_window()
    page = window.import_page
    page.new_table()
    settle()
    column = page.model.columns.index("206Pb/204Pb Mean")
    page.table.setCurrentIndex(page.model.index(0, column))
    QtWidgets.QApplication.clipboard().setText("2400.0\t0.15\n1800.5\t0.2\n")
    page.table.paste_clipboard()
    settle()
    session = window.session
    if session.value(0, "206Pb/204Pb Mean") != 2400.0:
        # Some offscreen platforms have no clipboard; paste the same text directly.
        page.paste_text(0, column, "2400.0\t0.15\n1800.5\t0.2\n")
    assert session.value(0, "206Pb/204Pb Mean") == 2400.0
    assert session.value(1, "206Pb/204Pb % Standard Error") == 0.2
    assert page.model.data(page.model.index(1, column)) == "1800.5"


def test_edit_and_save_round_trip(make_window, tmp_path):
    window = make_window(paths=[SYNTHETIC])
    model = window.import_page.model
    column = model.columns.index("Sample")
    assert model.setData(model.index(0, column), "SYN-1-edited")
    ratio = model.columns.index("206Pb/205Pb Mean")
    assert not model.flags(model.index(0, ratio)) & QtCore.Qt.ItemFlag.ItemIsEditable
    assert not model.setData(model.index(0, model.columns.index("Spike Weight (g)")), "x")
    assert "not a number" in window.import_page.banner.text()
    target = tmp_path / "saved.fractions.csv"
    assert window.import_page.save_to(str(target))
    saved = read_fractions(target)
    assert saved.frame.loc[0, "Sample"] == "SYN-1-edited"
    assert saved.frame.loc[0, "206Pb/205Pb Mean"] == read_fractions(SYNTHETIC).frame.loc[0, "206Pb/205Pb Mean"]


def test_theme_switch_live(make_window, app):
    window = make_window(paths=[TEMPLATE])
    window.set_theme_mode("dark")
    settle()
    assert app.property("upbrpy.resolved_theme") == "dark"
    window.set_theme_mode("light")
    settle()
    assert app.property("upbrpy.resolved_theme") == "light"


def test_provenance_columns_edit_session_and_rebuild_issues(make_window, tmp_path):
    window = make_window(paths=[TEMPLATE])
    page, session = window.import_page, window.session
    model = page.model
    columns = ['U Oxide 18O/16O', 'U Oxide Formula', 'Pb Mean Statistic', 'U Mean Statistic']
    assert model.columns[1:5] == columns
    delegate = page.table.itemDelegate()
    for column, choices in [
        ('U Oxide Formula', ['', 'isobar_233_18O', 'tripoli_java_00dc941', 'instrument']),
        ('Pb Mean Statistic', ['', 'arithmetic', 'geometric']),
        ('U Mean Statistic', ['', 'arithmetic', 'geometric'])]:
        index = model.index(0, model.columns.index(column))
        editor = delegate.createEditor(page.table, QtWidgets.QStyleOptionViewItem(), index)
        assert isinstance(editor, QtWidgets.QComboBox)
        assert [editor.itemText(i) for i in range(editor.count())] == choices
        delegate.setEditorData(editor, index)
        editor.setCurrentText('instrument' if column == 'U Oxide Formula' else 'geometric')
        delegate.setModelData(editor, model, index)
        assert session.value(0, column) == editor.currentText()
        editor.deleteLater()
    index = model.index(0, model.columns.index('U Oxide 18O/16O'))
    assert model.setData(index, '0.00206')
    # Rebuilt issue cards/buttons use deleteLater; flush them as --export does.
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    settle()
    messages = ' '.join(i.message for i in session.issues('z1'))
    assert 'raw file' in messages and 'Pb ratios are geometric' in messages
    assert 'U ratios are geometric' in messages
    card = window.issues_panel.card_for('z1')
    assert 'geometric' in ' '.join(label.text() for label in card.findChildren(QtWidgets.QLabel))
    assert page.table.columnViewportPosition(4) + page.table.columnWidth(4) <= page.table.viewport().width()
    formula_column = model.columns.index('U Oxide Formula')
    assert page.table.columnWidth(formula_column) >= page.table.fontMetrics().horizontalAdvance('instrument') + 18
    assert _layout_problems(window) == []
    for column in ('Pb Mean Statistic', 'U Mean Statistic'):
        index = model.index(0, model.columns.index(column))
        assert model.setData(index, '')
        assert index.data() == 'arithmetic'
        assert index.data(QtCore.Qt.ItemDataRole.EditRole) == ''
    assert not any(i.kind == 'mean_statistic_note' for i in session.issues('z1'))
    target = tmp_path / 'provenance.csv'
    assert page.save_to(target)
    back = read_fractions(target)
    assert back.frame.loc[0, 'U Oxide Formula'] == 'instrument'
    assert back.mean_statistic('z1', 'Pb') == 'arithmetic'


def _run_app(*arguments):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
               PYTHONPATH=os.pathsep.join([str(ROOT / "src"), os.environ.get("PYTHONPATH", "")]))
    return subprocess.run([sys.executable, "-m", "idtims_app", "--theme", "light", *arguments],
                          capture_output=True, text=True, cwd=ROOT, env=env, timeout=120)


def test_export_command(tmp_path):
    png = tmp_path / "template.png"
    result = _run_app(str(TEMPLATE), "--export", str(png), "--size", "1280x800")
    assert result.returncode == 0, result.stderr
    assert png.stat().st_size >= 10_000
    bad = tmp_path / "bad.csv"
    bad.write_text("Sample\nSYNTHETIC\n", encoding="utf-8")
    failed = _run_app(str(bad), "--export", str(tmp_path / "bad.png"))
    assert failed.returncode == 1 and "Grain ID" in failed.stderr
