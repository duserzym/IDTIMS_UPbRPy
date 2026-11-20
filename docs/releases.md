# Release and update builds

The updater is a verbatim copy of `duserzym/UPbRPy`'s `GUI/labupdate` at
`e3970b6`. Its source rules, API and per-file SHA256 hashes are in
`src/idtims_app/labupdate/{SOURCE.md,API.md,VENDORED}`. Change the canonical
package and recopy it when fixing shared behavior; keep app-specific changes
in `update_config.py` or `update_widgets.py`.

The latest stable feed is
`https://github.com/duserzym/IDTIMS_UPbRPy/releases/latest/download/latest.json`.
The public key is embedded in `update_config.py`; private production keys are
never copied into this repository or the app. There are no release channels;
old beta preferences migrate silently to stable.

The main work panel header places the circular-arrows update button and version
chip beside Back, Next and Issues. The button opens the shared popover and its
Update settings button opens the app's update preferences. Available and ready
updates show four lines of release notes and a link to the version's GitHub
release. The button owns an anchored What's new card, shown once after an
upgrade, including manual reinstalls, and reopenable from either popover.
The first install records the version without showing a card. A frozen app in
a writable supported location checks 8 seconds after showing its window and
every 6 hours; source checkouts can check manually. Workers stop on quit.

## Prepare the lab notes

For each version, write `release-notes/<version>.md` at the repository root.
Use plain text or at most five `- ` bullets, no heading, at most 600 characters.
Describe what lab users can do. Copy the same file to
`src/idtims_app/release-notes/<version>.md` for Python package data; tests require
these copies to match. PyInstaller bundles the root notes into that same package
location. Both wheels and frozen apps can therefore read their running notes.
The feed builder refuses missing, blank or oversized notes.

The checkout already declares version 0.2.3. Notes for the first-release 0.2.2
and the running 0.2.3 are included. For a future release, update both
`pyproject.toml` and `src/idtims_app/__init__.py` and add its notes before building.

## Build, validate and sign

Use the repository venv and install its GUI and build extras. `truststore` uses
the OS certificate store and `certifi` supplies the bundled CA fallback.

```sh
.venv/bin/python -m pip install -e '.[gui,build]'
.venv/bin/python scripts/run_tests.py quick
APPLE_SIGNING_IDENTITY="UPb Lab Code Signing" \
  .venv/bin/python scripts/build_desktop.py --smoke-test --archive \
  --sign-with "$HOME/.tauri/idtims-updater.key"
```

`IDTIMS_UPDATER_KEY` is the alternative to `--sign-with`. The feed builder uses
`cargo tauri signer sign`, which must be installed on the release machine.
`APPLE_SIGNING_IDENTITY` signs the application bundle before smoke checks and
archiving; the updater key signs the archive. Without an Apple identity,
PyInstaller's ad hoc signature is retained. `--no-build --smoke-test` validates
an existing build without signing the app again.

Output lives under the existing platform cache path printed by the script
(or `$IDTIMS_BUILD_ROOT`, outside the repository). On macOS arm64, `--archive`
produces:

- `ID-TIMS-Reduction-<version>-macOS-arm64.zip`
- `ID-TIMS-Reduction-<version>-macOS-arm64.app.tar.gz`, preserving bundle symlinks
- `SHA256SUMS.txt`

Release asset names use branding's `RELEASE_SLUG` and contain no spaces, so
`latest.json` URLs need no percent-encoding. The bundle inside each archive
remains `ID-TIMS Reduction.app`. GitHub renames uploaded assets containing
spaces, which would break feed URLs based on those names.

With an updater key, it also produces
`ID-TIMS-Reduction-<version>-macOS-arm64.app.tar.gz.sig` and `latest.json`
using the vendored `release.build_feed`. Every signature is verified against the
embedded production public key before the feed is written. Windows uses a
signed ZIP with the `windows-x86_64` target; signed feeds support macOS arm64
and Windows x86_64. Unsigned archives are useful for local inspection.

The frozen smoke test includes the offline signed-manifest test, tamper
rejection and HTTPS trust check with missing default CA paths and Homebrew
certificate folders hidden when supported. A github.com reachability warning
is allowed; trust errors and failed checks fail the build. Rerun it after
installing dependencies if working in a restricted sandbox. Before release,
also exercise the packaged restart/relaunch on the target OS and confirm the
next launch shows the notes once.

## Publish the release

Create the stable GitHub release tagged `v<version>` and upload the ZIP,
`.app.tar.gz`, its `.sig`, `latest.json` and `SHA256SUMS.txt` together. Use the
lab notes as the release description. The feed URLs point to that exact tag;
GitHub's latest stable release supplies the app's feed. Keep the archive names
unchanged. Never upload the signing key. Publishing is a separate release
operator step; the build script creates local artifacts only.
