"""Pinned vendor provenance, app identity and window-free offline CLI checks."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from idtims_app import __version__, branding
from idtims_app.labupdate.config import platform_key
from idtims_app.labupdate.minisign import parse_public_key
from idtims_app.labupdate.selftest import SELF_TEST_DATA
from idtims_app.update_config import PUBLIC_KEY, release_notes, update_config
from labupdate_signing import sign

ROOT = Path(__file__).resolve().parents[1]


def test_config_and_notes():
    config = update_config()
    assert config.repo == "duserzym/IDTIMS_UPbRPy"
    assert config.app_name == branding.DISPLAY_NAME
    assert (config.settings_org, config.settings_app) == (branding.ORGANISATION, branding.SLUG)
    assert config.feed_url == "https://github.com/duserzym/IDTIMS_UPbRPy/releases/latest/download/latest.json"
    assert len(parse_public_key(PUBLIC_KEY).key) == 32
    from idtims_app.labupdate import tls
    assert config.opener is tls.urlopen
    assert config.release_notes is release_notes
    assert release_notes("../escape") is None
    assert release_notes("..\\escape") is None
    assert release_notes("missing") is None
    assert release_notes(__version__)
    for path in (ROOT / "release-notes").glob("*.md"):
        text = path.read_text()
        assert 0 < len(text) <= 600
        assert len(text.splitlines()) <= 5
        assert all(line.startswith("- ") for line in text.splitlines())
        assert (ROOT / "src/idtims_app/release-notes" / path.name).read_bytes() == path.read_bytes()
        assert release_notes(path.stem) == text.strip()


def test_vendor_ast_and_byte_manifest():
    folder = ROOT / "src/idtims_app/labupdate"
    lines = (folder / "VENDORED").read_text().splitlines()
    assert lines[0] == ("Vendored from duserzym/UPbRPy GUI/labupdate at 13b1ff2 on 2026-11-20. "
                        "Do not edit; change the canonical copy and recopy.")
    hashes = dict(line.split("  ", 1)[::-1] for line in lines[3:])
    assert set(hashes) == {p.name for p in folder.iterdir() if p.suffix in {".py", ".md"}}
    assert {"SOURCE.md", "API.md", "qt.py", "release.py", "selftest.py"} <= hashes.keys()
    for name, expected in hashes.items():
        source = (folder / name).read_bytes()
        assert hashlib.sha256(source).hexdigest() == expected, f"Vendored file changed: {name}"
        if name.endswith(".py"):
            ast.parse(source, filename=name)


def write_manifest(tmp_path, tampered=False):
    archive = tmp_path / "self-test.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("Self Test.app/Contents/MacOS/Self Test", SELF_TEST_DATA)
    signature = sign(archive.read_bytes())
    if tampered:
        with archive.open("ab") as stream:
            stream.write(b"tampered")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"version": "9.0.0", "notes": "A lab update",
        "platforms": {platform_key(): {"url": archive.as_uri(), "signature": signature}}}))
    return manifest


@pytest.mark.parametrize("manifest_kind", ["none", "valid", "tampered"])
def test_cli_self_test_offline_before_qt(tmp_path, manifest_kind):
    manifest = None if manifest_kind == "none" else write_manifest(tmp_path, manifest_kind == "tampered")
    output = tmp_path / "report.json"
    # Use the actual CLI in a new process, replacing only transport: all HTTPS
    # is offline and local files still use urllib. No local server or Qt needed.
    script = '''
import sys, urllib.error, urllib.request
from dataclasses import replace
from idtims_app import main, update_config
original = update_config.update_config
def offline(request, *, timeout):
    if request.full_url.startswith("https:"):
        raise urllib.error.URLError("offline test")
    return urllib.request.urlopen(request, timeout=timeout)
update_config.update_config = lambda: replace(original(), opener=offline)
result = main.main(sys.argv[1:])
assert "PySide6" not in sys.modules
assert "idtims_app.window" not in sys.modules
raise SystemExit(result)
'''
    args = ["--update-self-test", *([manifest.as_uri()] if manifest else []),
            "--update-self-test-output", str(output)]
    result = subprocess.run([sys.executable, "-c", script, *args], capture_output=True, text=True,
                            cwd=ROOT, timeout=30)
    assert result.returncode == (1 if manifest_kind == "tampered" else 0), result.stderr
    report = json.loads(output.read_text())
    assert report["verification_ran"]
    assert report["signature"] == {"status": "ok", "tampered_rejected": True}
    assert report["public_key"]["status"] == "ok"
    assert report["https"]["status"] == "network"
    if manifest:
        assert report["manifest"]["status"] == ("error" if manifest_kind == "tampered" else "ok")
        if manifest_kind == "valid":
            assert report["manifest"]["archive_verified"]


def test_other_headless_cli_does_not_build_update_config(monkeypatch, capsys):
    from idtims_app import main, update_config as config_module
    monkeypatch.setattr(config_module, "update_config", lambda: pytest.fail("unneeded config"))
    assert main.main(["--print-engine-fingerprint"]) == 0
    assert json.loads(capsys.readouterr().out)["match"]
