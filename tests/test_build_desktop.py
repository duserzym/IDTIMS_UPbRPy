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


@pytest.mark.parametrize("key_source", ["argument", "environment", "unsigned"])
def test_archive_symlinks_signing_feed_and_checksums(monkeypatch, tmp_path, key_source):
    import hashlib
    import json
    import tarfile
    import zipfile
    from idtims_app import update_config
    from labupdate_signing import public_key, sign

    monkeypatch.setattr(build_desktop.sys, "platform", "darwin")
    monkeypatch.setattr(build_desktop.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(update_config, "PUBLIC_KEY", public_key())
    monkeypatch.delenv("IDTIMS_UPDATER_KEY", raising=False)
    key = tmp_path / "disposable.key"
    if key_source == "environment":
        monkeypatch.setenv("IDTIMS_UPDATER_KEY", str(key))
    app = tmp_path / f"{build_desktop.APPLICATION_NAME}.app"
    executable = app / "Contents/MacOS/app"
    executable.parent.mkdir(parents=True)
    executable.write_text("test executable")
    (app / "alias").symlink_to("Contents/MacOS/app")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs["check"]
        if command[0] == "ditto":
            with zipfile.ZipFile(command[-1], "w") as archive:
                archive.writestr(f"{app.name}/placeholder", "legacy zip")
        else:
            assert command[:4] == ["cargo", "tauri", "signer", "sign"]
            assert command[4:8] == ["-f", str(key), "-p", ""]
            path = Path(command[-1])
            Path(str(path) + ".sig").write_text(sign(path.read_bytes()))

    monkeypatch.setattr(build_desktop.subprocess, "run", run)
    archive = build_desktop.archive_application(
        app, tmp_path, sign_with=key if key_source == "argument" else None)
    stem = f"{build_desktop.APPLICATION_NAME}-{build_desktop.project_version()}-macOS-arm64"
    assert archive.name == f"{stem}.zip" and archive.exists()
    tarball = tmp_path / f"{stem}.app.tar.gz"
    with tarfile.open(tarball) as bundle:
        assert bundle.getmember(f"{app.name}/alias").issym()
        assert bundle.extractfile(f"{app.name}/Contents/MacOS/app").read() == b"test executable"
    if key_source != "unsigned":
        feed = json.loads((tmp_path / "latest.json").read_text())
        assert feed["version"] == build_desktop.project_version()
        assert feed["notes"] == (build_desktop.PROJECT_ROOT / "release-notes" / f"{feed['version']}.md").read_text()
        assert feed["platforms"]["darwin-aarch64"]["url"].endswith(tarball.name.replace(" ", "%20"))
        assert "/duserzym/IDTIMS_UPbRPy/" in feed["platforms"]["darwin-aarch64"]["url"]
        assert Path(str(tarball) + ".sig").exists()
        assert len(calls) == 2
    else:
        assert not (tmp_path / "latest.json").exists()
        assert len(calls) == 1
    sums = (tmp_path / "SHA256SUMS.txt").read_text().splitlines()
    assert len(sums) == (2 if key_source == "unsigned" else 4)
    for line in sums:
        digest, name = line.split("  ", 1)
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == digest
    assert not (tmp_path / "updater.pub").exists()


@pytest.mark.parametrize("notes", [None, "", "x" * 601])
def test_release_refuses_invalid_notes(tmp_path, notes):
    from idtims_app.labupdate.release import build_feed
    path = tmp_path / "notes.md"
    if notes is not None:
        path.write_text(notes)
    with pytest.raises((OSError, ValueError)):
        build_feed(repo="duserzym/IDTIMS_UPbRPy", version="0.2.2", notes_file=path,
                   archives={}, pubkey_file=tmp_path / "not-read.pub", out=tmp_path / "latest.json")
    assert not (tmp_path / "latest.json").exists()


@pytest.mark.parametrize("failed", [None, "ok", "verification_ran", "signature", "public_key",
                                    "manifest", "archive", "tls", "https", "exit"])
def test_frozen_update_smoke_requires_all_checks(monkeypatch, tmp_path, failed):
    import json
    from idtims_app.labupdate.config import platform_key
    from idtims_app.labupdate.minisign import verify_file
    from idtims_app.labupdate.selftest import SELF_TEST_PUBKEY

    def frozen(application, args, work, **kwargs):
        assert args[0] == "--update-self-test"
        assert args[1] == (work / "update-self-test.json").as_uri()
        manifest = json.loads((work / "update-self-test.json").read_text())
        verify_file(work / "update-self-test.zip",
                    manifest["platforms"][platform_key()]["signature"], SELF_TEST_PUBKEY)
        assert kwargs["check"] is False
        for name in ("SSL_CERT_FILE", "SSL_CERT_DIR"):
            assert not Path(kwargs["environment_overrides"][name]).exists()
        report = {"ok": True, "verification_ran": True,
                  "signature": {"status": "ok", "tampered_rejected": True},
                  "public_key": {"status": "ok"},
                  "manifest": {"status": "ok", "archive_verified": True},
                  "tls": {"source": "truststore"}, "https": {"status": "network"}}
        if failed in {"ok", "verification_ran"}:
            report[failed] = False
        elif failed in {"signature", "public_key", "manifest", "https", "tls"}:
            report[failed]["status"] = "error"
        elif failed == "archive":
            report["manifest"]["archive_verified"] = False
        Path(args[3]).write_text(json.dumps(report))
        return subprocess.CompletedProcess(args, 1 if failed == "exit" else 0, "", "")

    monkeypatch.setattr(build_desktop, "_run_frozen", frozen)
    if failed:
        with pytest.raises(RuntimeError, match="self-test failed"):
            build_desktop.verify_update_self_test(tmp_path / "app", tmp_path)
    else:
        build_desktop.verify_update_self_test(tmp_path / "app", tmp_path)


def test_frozen_update_hides_homebrew_certificates(monkeypatch, tmp_path):
    monkeypatch.setattr(build_desktop.sys, "platform", "darwin")
    monkeypatch.setattr(build_desktop.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
    def run(command, **kwargs):
        assert command[:2] == ["/usr/bin/sandbox-exec", "-f"]
        profile = Path(command[2]).read_text()
        assert '(subpath "/opt/homebrew/etc/openssl@3")' in profile
        assert '(subpath "/usr/local/etc/openssl@3")' in profile
        assert kwargs["env"]["SSL_CERT_FILE"] == str(tmp_path / "missing.pem")
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(build_desktop.subprocess, "run", run)
    build_desktop._run_frozen(tmp_path / "app", ["--update-self-test"], tmp_path,
                             environment_overrides={"SSL_CERT_FILE": str(tmp_path / "missing.pem")})
