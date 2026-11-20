"""Build and smoke-test the frozen ID-TIMS reduction app (placeholder name).

    python scripts/build_desktop.py               # build only
    python scripts/build_desktop.py --smoke-test  # build, then exercise the frozen app
    python scripts/build_desktop.py --smoke-test --no-build   # test the last build
    python scripts/build_desktop.py --clean       # remove the build directory

Run it with the interpreter whose packages should be bundled (the repository
venv with the gui and build extras). Output goes to
~/Library/Caches/<slug>/<checkout hash>/ on macOS (the platform cache folder
elsewhere, or $IDTIMS_BUILD_ROOT), never inside the repository. Modelled on
UPbRPy Studio's scripts/build_desktop.py (commit f8c561f).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import runpy
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_FILE = PROJECT_ROOT / "packaging" / "IDTIMSReduction.spec"
BRANDING = runpy.run_path(str(PROJECT_ROOT / "src" / "idtims_app" / "branding.py"))
APPLICATION_NAME = BRANDING["BUNDLE_NAME"]
if sys.platform == "win32":
    CACHE_BASE = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
elif sys.platform == "darwin":
    CACHE_BASE = Path.home() / "Library/Caches"
else:
    CACHE_BASE = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
CHECKOUT_KEY = hashlib.sha256(str(PROJECT_ROOT).encode()).hexdigest()[:12]
BUILD_ROOT = Path(os.environ.get("IDTIMS_BUILD_ROOT",
                                 str(CACHE_BASE / BRANDING["SLUG"] / CHECKOUT_KEY)))
SMOKE_INPUTS = {
    "empty": [],
    "MA1": [PROJECT_ROOT / "examples" / "synthetic_zircon_CA-ID-TIMS.csv"],
    "template2535": [PROJECT_ROOT / "tests" / "data" / "synthetic_template_2535.csv"],
    # Review (step 7): reduction, concordia and weighted mean inside the frozen app.
    "review_template2535": [PROJECT_ROOT / "tests" / "data" / "synthetic_template_2535.csv",
                            "--settings",
                            PROJECT_ROOT / "tests" / "data" / "settings_BSU_template.json",
                            "--confirm-no-oxide", "--reduce", "--step", "7",
                            "--exclude", "z3"],
}
SNAPSHOT = PROJECT_ROOT / "tests" / "data" / "synthetic_snapshot.json"


def application_path(dist):
    """The bundled app for this platform."""
    if sys.platform == "darwin":
        return dist / f"{APPLICATION_NAME}.app"
    suffix = ".exe" if sys.platform == "win32" else ""
    return dist / APPLICATION_NAME / f"{APPLICATION_NAME}{suffix}"


def application_executable(application):
    if sys.platform == "darwin":
        return application / "Contents" / "MacOS" / APPLICATION_NAME
    return application


def sign_application(application):
    """Use the lab identity when configured; retain ad hoc signing otherwise."""
    identity = os.environ.get("APPLE_SIGNING_IDENTITY", "").strip()
    if sys.platform != "darwin" or not identity or identity == "-":
        return
    subprocess.run(["codesign", "--force", "--deep", "--timestamp=none", "--sign",
                    identity, str(application)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(application)],
                   check=True)
    print(f"Signed with: {identity}")


def require_build_dependencies():
    missing = [n for n in ("PyInstaller", "PySide6", "pyqtgraph", "truststore", "certifi")
               if importlib.util.find_spec(n) is None]
    if missing:
        raise RuntimeError(f"Missing build dependencies: {', '.join(missing)}. Install them with "
                           "`python -m pip install -e '.[gui,build]'` and rerun with that Python.")


def run_pyinstaller(dist, work, *, clean):
    # Import from this checkout before freezing; PYZ bytes differ from source bytes.
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from idtims_app.project import engine_fingerprint

    source_fingerprint = work / "engine_source_fingerprint.txt"
    source_fingerprint.write_text(engine_fingerprint() + "\n", encoding="utf-8")
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(dist),
               "--workpath", str(work)]
    if clean:
        command.append("--clean")
    command.append(str(SPEC_FILE))
    environment = os.environ.copy()
    config = work / "config"
    config.mkdir(parents=True, exist_ok=True)
    environment["PYINSTALLER_CONFIG_DIR"] = str(config)
    environment["IDTIMS_ENGINE_SOURCE_FINGERPRINT"] = str(source_fingerprint.resolve())
    subprocess.run(command, cwd=PROJECT_ROOT, env=environment, check=True)
    application = application_path(dist)
    if not application_executable(application).exists():
        raise RuntimeError(f"PyInstaller finished without producing {application}")
    return application


def _run_frozen(application, arguments, work, *, environment_overrides=None, check=True):
    """Run the frozen app offscreen with isolated settings; fail on error or traceback."""
    environment = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME"):
        environment.pop(name, None)
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["IDTIMS_AUTOSAVE_DIR"] = str(work / "autosave")
    environment["IDTIMS_APP_SETTINGS"] = str(work / "smoke-settings.ini")
    environment.update(environment_overrides or {})
    command = [str(application_executable(application)), *arguments]
    sandbox = shutil.which("sandbox-exec") if sys.platform == "darwin" and "--update-self-test" in arguments else None
    if sandbox:
        profile = work / "no-homebrew-ca.sb"
        profile.write_text(
            '(version 1)\n(allow default)\n'
            '(deny file-read* (subpath "/opt/homebrew/etc/openssl@3") '
            '(subpath "/usr/local/etc/openssl@3"))\n', encoding="utf-8")
        command = [sandbox, "-f", str(profile), *command]
    result = subprocess.run(command, cwd=work,
                            env=environment, capture_output=True, text=True, timeout=300)
    if check and (result.returncode != 0 or "Traceback" in result.stderr):
        raise RuntimeError(f"The frozen app failed on {' '.join(arguments)} "
                           f"(exit {result.returncode}):\n{result.stderr[-4000:]}")
    return result


def smoke_test_application(application, work):
    """Verify screenshots, source-project replay, fingerprint stability and frozen numerics."""
    work.mkdir(parents=True, exist_ok=True)
    shots = []
    for name, paths in SMOKE_INPUTS.items():
        png = work / f"smoke-{name}.png"
        if png.exists():
            png.unlink()
        _run_frozen(application, ["--theme", "light", *map(str, paths), "--export", str(png),
                                  "--size", "1280x800"], work)
        if not png.exists() or png.stat().st_size < 10_000:
            raise RuntimeError(f"The frozen app did not write a valid {name} screenshot: {png}")
        shots.append(png)
        print(f"Smoke screenshot ({name}): {png} ({png.stat().st_size // 1024} kB)")
    # Cross-loader project: source serialization, frozen recomputation and Export.
    project = work / "source-template.idtr"
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                       IDTIMS_APP_SETTINGS=str(work / "source-settings.ini"),
                       IDTIMS_AUTOSAVE_DIR=str(work / "source-autosave"))
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    subprocess.run([sys.executable, "-m", "idtims_app",
                    str(PROJECT_ROOT / "tests/data/synthetic_template_2535.csv"),
                    "--settings", str(PROJECT_ROOT / "tests/data/settings_BSU_template.json"),
                    "--confirm-no-oxide", "--reduce", "--step", "8",
                    "--save-project", str(project), "--export", str(work / "source-export.png")],
                   cwd=PROJECT_ROOT, env=environment, check=True, timeout=300)
    png = work / "smoke-project-export.png"
    png.unlink(missing_ok=True)
    _run_frozen(application, [str(project), "--step", "8", "--theme", "light",
                              "--export", str(png), "--size", "1280x800"], work)
    if not png.exists() or png.stat().st_size < 10_000:
        raise RuntimeError(f"Frozen source-project Export screenshot failed: {png}")
    shots.append(png)
    source_status = subprocess.run(
        [sys.executable, "-m", "idtims_app", "--print-project-status", str(project)],
        cwd=PROJECT_ROOT, env=environment, capture_output=True, text=True, check=True, timeout=300)
    source_status = json.loads(source_status.stdout)
    frozen_status = json.loads(_run_frozen(
        application, ["--print-project-status", str(project)], work).stdout)
    if (source_status.get("engine_note") or frozen_status.get("engine_note")
            or frozen_status.get("reduced") != source_status.get("reduced")
            or not isinstance(frozen_status.get("reduced"), list)
            or frozen_status.get("included") != source_status.get("included")):
        raise RuntimeError(f"Frozen source-project replay differs: source={source_status}, "
                           f"frozen={frozen_status}")
    print("Frozen app reopened a source-saved project: same engine, "
          f"{len(frozen_status['reduced'])} fractions reduced")
    stability = json.loads(_run_frozen(application, ["--print-engine-fingerprint"], work).stdout)
    if not (stability.get("frozen") and stability.get("engine")
            and stability.get("frozen_code_first") and stability.get("match")
            and stability["frozen_code_first"] == stability.get("frozen_code_second")):
        raise RuntimeError(f"Frozen engine fingerprint is unstable: {stability}")
    print("Frozen engine fingerprint: two computations match")
    result = _run_frozen(application, ["--verify-reduction", str(SNAPSHOT)], work)
    report = json.loads(result.stdout)
    if not report.get("frozen") or report.get("mismatches") != 0:
        raise RuntimeError(f"The frozen reduction check failed: {report}")
    print(f"Frozen reduction check: {report['numbers_compared']} numbers match "
          f"{SNAPSHOT.name} (rel 1e-12)")
    verify_update_self_test(application, work)
    return shots


def project_version():
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    return tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def platform_label():
    system = {"darwin": "macOS", "win32": "Windows"}.get(sys.platform, "Linux")
    machine = platform.machine().lower()
    arch = {"aarch64": "arm64", "amd64": "x86_64"}.get(machine, machine)
    return f"{system}-{arch}"


def verify_update_self_test(application: Path, work_directory: Path) -> None:
    """Verify a local signed feed and mandatory tamper rejection in the frozen app."""
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from idtims_app.labupdate.config import platform_key
    from idtims_app.labupdate.selftest import SELF_TEST_DATA

    # The disposable private test key stays in the source-side test helper.
    # It is never bundled or used by the production updater.
    helper = importlib.util.spec_from_file_location("labupdate_smoke_signing", PROJECT_ROOT / "tests/labupdate_signing.py")
    signing = importlib.util.module_from_spec(helper)
    helper.loader.exec_module(signing)
    archive = work_directory / "update-self-test.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("Self Test.app/Contents/MacOS/Self Test", SELF_TEST_DATA)
    signature = signing.sign(archive.read_bytes())
    manifest = work_directory / "update-self-test.json"
    manifest.write_text(json.dumps({"version": project_version(), "notes": "Frozen update check",
        "platforms": {platform_key(): {"url": archive.as_uri(), "signature": signature}}}), encoding="utf-8")
    output = work_directory / "update-self-test-result.json"
    output.unlink(missing_ok=True)
    result = _run_frozen(application,
        ["--update-self-test", manifest.as_uri(), "--update-self-test-output", str(output)],
        work_directory, environment_overrides={
            "SSL_CERT_FILE": str(work_directory / "nonexistent-cert.pem"),
            "SSL_CERT_DIR": str(work_directory / "nonexistent-certs"),
        }, check=False)
    try:
        report = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Frozen update self-test did not return JSON: {result.stderr[-4000:]}") from exc
    required = (report.get("ok") is True, report.get("verification_ran") is True,
                report.get("signature", {}).get("tampered_rejected") is True,
                report.get("signature", {}).get("status") == "ok",
                report.get("public_key", {}).get("status") == "ok",
                report.get("manifest", {}).get("status") == "ok",
                report.get("manifest", {}).get("archive_verified") is True,
                report.get("https", {}).get("status") in {"ok", "network"},
                bool(report.get("tls", {}).get("source")),
                report.get("tls", {}).get("status") != "error")
    if result.returncode != 0 or "Traceback" in result.stderr or not all(required):
        raise RuntimeError(f"Frozen update self-test failed: {report}")
    if report["https"]["status"] == "network":
        print(f"Warning: frozen update HTTPS check unavailable: {report['https'].get('message', '')}")


def archive_application(
    application: Path,
    dist_directory: Path,
    *, sign_with: Path | None = None,
) -> Path:
    """Create a ZIP plus an update tarball, verified feed and checksums."""
    archive_stem = (
        f"{APPLICATION_NAME}-{project_version()}-{platform_label()}"
    )
    archive = dist_directory / f"{archive_stem}.zip"
    if archive.exists():
        archive.unlink()
    Path(str(archive) + ".sig").unlink(missing_ok=True)
    if sys.platform == "darwin":
        subprocess.run(
            [
                "ditto",
                "-c",
                "-k",
                "--sequesterRsrc",
                "--keepParent",
                str(application),
                str(archive),
            ],
            check=True,
        )
    else:
        bundle_directory = (
            application.parent
            if application.is_file()
            else application
        )
        generated = shutil.make_archive(
            str(archive.with_suffix("")),
            "zip",
            root_dir=bundle_directory.parent,
            base_dir=bundle_directory.name,
        )
        archive = Path(generated)
    assets = [archive]
    signed_archive = archive
    target = "windows-x86_64" if sys.platform == "win32" else None
    if sys.platform == "darwin":
        tarball = dist_directory / f"{archive_stem}.app.tar.gz"
        # Regenerating an archive invalidates any signature from an earlier build.
        Path(str(tarball) + ".sig").unlink(missing_ok=True)
        with tarfile.open(tarball, "w:gz", dereference=False) as bundle:
            bundle.add(application, arcname=application.name)
        assets.append(tarball)
        signed_archive = tarball
        target = "darwin-aarch64" if platform_label() == "macOS-arm64" else None
    key = sign_with or os.environ.get("IDTIMS_UPDATER_KEY")
    if key:
        if target is None:
            raise ValueError("Signed ID-TIMS feeds support macOS arm64 and Windows x86_64")
        sys.path.insert(0, str(PROJECT_ROOT / "src"))
        from idtims_app.labupdate.release import build_feed
        from idtims_app.update_config import PUBLIC_KEY
        public_key = dist_directory / "updater.pub"
        public_key.write_text(PUBLIC_KEY, encoding="utf-8")
        try:
            feed = dist_directory / "latest.json"
            build_feed(repo="duserzym/IDTIMS_UPbRPy", version=project_version(),
                notes_file=PROJECT_ROOT / "release-notes" / f"{project_version()}.md",
                archives={target: signed_archive}, pubkey_file=public_key,
                out=feed, sign_with=Path(key).expanduser())
        finally:
            public_key.unlink(missing_ok=True)
        assets.extend([Path(str(signed_archive) + ".sig"), feed])
    checksums = dist_directory / "SHA256SUMS.txt"
    lines = []
    for asset in assets:
        with asset.open("rb") as stream:
            hasher = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
            digest = hasher.hexdigest()
        lines.append(f"{digest}  {asset.name}\n")
    checksums.write_text("".join(lines), encoding="utf-8")
    return archive


def directory_size(path):
    return sum(p.stat().st_size for p in Path(path).rglob("*") if p.is_file()
               and not p.is_symlink())


def clean_build():
    """Remove this checkout's build directory and report the space freed."""
    if not BUILD_ROOT.exists():
        print(f"Nothing to remove: {BUILD_ROOT}")
        return 0
    size = directory_size(BUILD_ROOT)
    shutil.rmtree(BUILD_ROOT)
    print(f"Removed {BUILD_ROOT} ({size / 1e6:.0f} MB)")
    return 0


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description="Build the frozen ID-TIMS reduction app.")
    parser.add_argument("--smoke-test", action="store_true",
                        help="After building, run the frozen app on example data")
    parser.add_argument("--no-build", action="store_true",
                        help="Skip PyInstaller and smoke-test the existing build")
    parser.add_argument("--pyinstaller-clean", action="store_true",
                        help="Clear PyInstaller's caches before analysis")
    parser.add_argument("--clean", action="store_true",
                        help=f"Remove the build directory ({BUILD_ROOT}) and exit")
    parser.add_argument("--archive", action="store_true",
                        help="Create platform ZIP, update tarball and checksums")
    parser.add_argument("--sign-with", type=Path,
                        help="Updater private key (or IDTIMS_UPDATER_KEY)")
    return parser.parse_args(argv)


def main(argv=None):
    arguments = parse_arguments(argv)
    if arguments.clean:
        return clean_build()
    dist, work = BUILD_ROOT / "dist", BUILD_ROOT / "work"
    for output in (dist, work):
        if output.resolve() == PROJECT_ROOT or PROJECT_ROOT in output.resolve().parents:
            raise ValueError("Build outputs must be outside the source repository")
    if arguments.no_build:
        application = application_path(dist)
        if not application_executable(application).exists():
            raise RuntimeError(f"No build at {application}; run without --no-build first")
    else:
        require_build_dependencies()
        dist.mkdir(parents=True, exist_ok=True)
        work.mkdir(parents=True, exist_ok=True)
        application = run_pyinstaller(dist, work, clean=arguments.pyinstaller_clean)
        sign_application(application)
    print(f"Application: {application} ({directory_size(application) / 1e6:.0f} MB)")
    if arguments.smoke_test:
        smoke_test_application(application, work / "smoke")
        print("Smoke test passed.")
    if arguments.archive:
        archive = archive_application(application, dist, sign_with=arguments.sign_with)
        print(f"Archive: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
