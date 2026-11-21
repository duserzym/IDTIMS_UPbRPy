"""Shared update controls, notes and first-run/upgrade behavior offscreen."""
import os
from pathlib import Path

import pytest

from gui_support import require_gui

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
require_gui()
from PySide6 import QtCore, QtTest

from idtims_app import __version__
from idtims_app.labupdate.manifest import Release
from idtims_app.labupdate.qt import Updater, CheckUpdatesButton, release_notes_url
from idtims_app.ui.theme import apply_theme
from idtims_app.update_config import update_config, release_notes
from idtims_app.window import MainWindow
from test_gui_import import _layout_problems
from test_gui_steps import app, settle


@pytest.fixture
def window(app, monkeypatch, tmp_path):
    monkeypatch.setenv("IDTIMS_APP_SETTINGS", str(tmp_path / "app.ini"))
    monkeypatch.setenv("IDTIMS_AUTOSAVE_DIR", str(tmp_path / "autosave"))
    widget = MainWindow(confirm_close=False)
    widget.resize(1280, 800)
    yield widget
    widget.close()
    widget.deleteLater()
    settle()
    apply_theme(app, "light")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_controls_fit_main_header(window, app, theme, tmp_path):
    apply_theme(app, theme)
    assert not window.updater._started
    window.show()
    settle()
    assert window.updater._started
    assert window.size().toTuple() == (1280, 800)
    for control in (window.check_updates_button, window.version_chip):
        assert control.isVisible()
        assert window.rect().contains(QtCore.QRect(control.mapTo(window, QtCore.QPoint()), control.size()))
    assert window.version_chip.text() == f"v{__version__}"
    assert window.check_updates_button.accessibleName() == "Check for updates"
    assert window.check_updates_button.whats_new_card.button is window.check_updates_button
    assert _layout_problems(window) == []
    window.grab().save(str(tmp_path / f"updates-{theme}.png"))
    window.close()
    assert window.updater._closing


@pytest.mark.parametrize("manual", [False, True])
@pytest.mark.parametrize("status", ["available", "ready"])
def test_new_notes_in_popover_and_settings(window, manual, status):
    window.show()
    settle()
    updater = window.updater
    updater._emit(("check_started", manual))
    info = Release("9.0.0", "- Print sheets fit A4 and Letter.\n- Review your dates.", None,
                   "https://github.com/duserzym/IDTIMS_UPbRPy/releases/download/v9.0.0/app.zip", "signature")
    updater._emit(("found", info))
    if status == "ready":
        updater._emit("download_started")
        updater._emit(("downloaded", Path("fake-archive")))
    dialog = window.open_update_settings()
    popover = window.check_updates_button.popover
    popover.show()
    settle()
    for panel in (popover, dialog):
        assert panel.notes.text() == info.notes
        assert panel.notes.isVisible() and panel.notes_link.isVisible()
        assert panel.notes.height() == panel.notes.fontMetrics().lineSpacing() * 4
        assert ("Update available: v9.0.0" if status == "available" else "v9.0.0 is ready") in panel.status.text()
        if status == "ready":
            assert panel.action.text() == "Restart to update"
    assert window.check_updates_button.property("badge")
    assert release_notes_url(updater) == "https://github.com/duserzym/IDTIMS_UPbRPy/releases/tag/v9.0.0"


@pytest.mark.parametrize("previous", [None, "0.2.1", __version__])
def test_whats_new_once_after_version_change(app, tmp_path, previous):
    settings = QtCore.QSettings(str(tmp_path / "upgrades.ini"), QtCore.QSettings.Format.IniFormat)
    if previous:
        settings.setValue("updates/last_seen_version", previous)
    settings.setValue("updates/channel", "beta")
    updater = Updater(update_config(), __version__, settings=settings)
    button = CheckUpdatesButton(updater)
    button.show()
    spy = QtTest.QSignalSpy(updater.whatsNew)
    updater.start_scheduler()
    settle()
    upgraded = previous == "0.2.1"
    card = button.whats_new_card
    assert spy.count() == int(upgraded)
    assert card.isVisible() == upgraded
    assert settings.value("updates/last_seen_version") == __version__
    assert settings.value("updates/channel") == "stable"
    if upgraded:
        assert card.notes.text() == release_notes(__version__)
        QtTest.QTest.keyClick(card, QtCore.Qt.Key.Key_Escape)
        assert not card.isVisible()
    button.popover._show_whats_new()
    assert card.isVisible()
    assert card.heading.text() == f"What's new in v{__version__}"
    card.hide()
    updater.start_scheduler()
    settle()
    assert spy.count() == int(upgraded) + 1
    updater.shutdown()
    button.close()
    button.deleteLater()
    updater.deleteLater()
    settle()


def test_whats_new_pending_notes_and_fallback(app, tmp_path):
    from dataclasses import replace
    settings = QtCore.QSettings(str(tmp_path / "pending.ini"), QtCore.QSettings.Format.IniFormat)
    settings.setValue("updates/pending_version", "9.0.0")
    settings.setValue("updates/pending_notes", "Saved from the signed release feed.")
    updater = Updater(replace(update_config(), release_notes=lambda _: None), "9.0.0", settings=settings)
    assert updater.current_notes() == "Saved from the signed release feed."
    settings.setValue("updates/pending_version", "8.0.0")
    assert updater.current_notes() == "Updated to v9.0.0."
    updater.shutdown()
    updater.deleteLater()
    settle()


def test_supported_window_schedules_after_show_and_stops(window, monkeypatch, tmp_path):
    from idtims_app.labupdate import install
    window.updater.root = tmp_path / "Test.app"
    monkeypatch.setattr(install, "can_replace", lambda root: True)
    cleaned = []
    monkeypatch.setattr(install, "cleanup_previous", cleaned.append)
    assert not window.updater._initial_timer.isActive()
    assert not window.updater._timer.isActive()
    window.show()
    settle()
    assert cleaned == [window.updater.root]
    assert window.updater._initial_timer.isActive()
    assert window.updater._initial_timer.interval() == 8000
    assert window.updater._timer.isActive()
    assert window.updater._timer.interval() == 6 * 60 * 60 * 1000
    window.close()
    assert not window.updater._initial_timer.isActive()
    assert not window.updater._timer.isActive()
