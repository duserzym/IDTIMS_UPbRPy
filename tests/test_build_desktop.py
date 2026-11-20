"""Desktop signing commands and their position before the frozen smoke test."""
import importlib.util
from pathlib import Path
import subprocess

import pytest


SPEC = importlib.util.spec_from_file_location(
    "build_desktop", Path(__file__).resolve().parents[1] / "scripts/build_desktop.py")
build_desktop = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_desktop)


@pytest.mark.parametrize("identity", [None, "", "-", "UPb Lab Code Signing",
                                    "  UPb Lab Code Signing  "])
def test_signing_commands(monkeypatch, tmp_path, capsys, identity):
    monkeypatch.setattr(build_desktop.sys, "platform", "darwin")
    if identity is None:
        monkeypatch.delenv("APPLE_SIGNING_IDENTITY", raising=False)
    else:
        monkeypatch.setenv("APPLE_SIGNING_IDENTITY", identity)
    calls = []
    monkeypatch.setattr(build_desktop.subprocess, "run",
                        lambda command, **kw: calls.append((command, kw)))
    application = tmp_path / "test.app"
    build_desktop.sign_application(application)
    if identity and identity.strip() != "-":
        assert calls == [
            (["codesign", "--force", "--deep", "--timestamp=none", "--sign",
              identity.strip(), str(application)], {"check": True}),
            (["codesign", "--verify", "--deep", "--strict", str(application)],
             {"check": True}),
        ]
        assert capsys.readouterr().out == "Signed with: UPb Lab Code Signing\n"
    else:
        assert calls == []
        assert capsys.readouterr().out == ""


def test_signing_skipped_outside_macos(monkeypatch, tmp_path):
    monkeypatch.setattr(build_desktop.sys, "platform", "linux")
    monkeypatch.setenv("APPLE_SIGNING_IDENTITY", "UPb Lab Code Signing")
    monkeypatch.setattr(build_desktop.subprocess, "run",
                        lambda *a, **kw: pytest.fail("codesign requires macOS"))
    build_desktop.sign_application(tmp_path / "app")


@pytest.mark.parametrize("failed_command", [None, "sign", "verify"])
def test_build_signs_and_verifies_before_smoke(monkeypatch, tmp_path, failed_command):
    monkeypatch.setattr(build_desktop.sys, "platform", "darwin")
    monkeypatch.setenv("APPLE_SIGNING_IDENTITY", "UPb Lab Code Signing")
    monkeypatch.setattr(build_desktop, "BUILD_ROOT", tmp_path)
    monkeypatch.setattr(build_desktop, "require_build_dependencies", lambda: None)
    monkeypatch.setattr(build_desktop, "directory_size", lambda app: 0)
    events = []

    def build(*args, **kwargs):
        events.append("build")
        return tmp_path / "test.app"

    def run(command, **kwargs):
        assert command[0] == "codesign"
        assert kwargs == {"check": True}
        event = "verify" if "--verify" in command else "sign"
        events.append(event)
        if event == failed_command:
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(build_desktop, "run_pyinstaller", build)
    monkeypatch.setattr(build_desktop.subprocess, "run", run)
    monkeypatch.setattr(build_desktop, "smoke_test_application",
                        lambda *args: events.append("smoke"))
    if failed_command:
        with pytest.raises(subprocess.CalledProcessError):
            build_desktop.main(["--smoke-test"])
        assert events == ["build", "sign"] + (["verify"] if failed_command == "verify" else [])
    else:
        assert build_desktop.main(["--smoke-test"]) == 0
        assert events == ["build", "sign", "verify", "smoke"]


def test_no_build_does_not_resign(monkeypatch, tmp_path):
    monkeypatch.setattr(build_desktop, "BUILD_ROOT", tmp_path)
    application = tmp_path / "existing-app"
    application.touch()
    monkeypatch.setattr(build_desktop, "application_path", lambda dist: application)
    monkeypatch.setattr(build_desktop, "application_executable", lambda app: app)
    monkeypatch.setattr(build_desktop, "sign_application",
                        lambda app: pytest.fail("--no-build must preserve the existing bundle"))
    tested = []
    monkeypatch.setattr(build_desktop, "smoke_test_application", lambda *args: tested.append(args))
    assert build_desktop.main(["--no-build", "--smoke-test"]) == 0
    assert tested == [(application, tmp_path / "work" / "smoke")]
