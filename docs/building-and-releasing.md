# Building and releasing

This document is for anyone who wants to build locally or ship a new version. Everything is free. The repo is public, so GitHub Actions costs nothing and anyone can read releases without a sign-in. No secrets are necessary.

## The version: the tag is the source

- A release has the name `vX.Y.Z` (for example `v1.2.0`). A pre-release has the name `vX.Y.Z-rc.N` (for example `v1.2.0-rc.1`). It becomes a GitHub *prerelease*. The update check ignores it.
- The tag is independent of the `vX.Y.Z` tags of the Huurklaar app itself. The app is a different repo with its own series, which starts at `v0.1.0`.
- `scripts/set-version.py <tag>` writes the number into `src/huurklaar_notifier/_version.py`. In git, that file always contains the placeholder `0.0.0` (older than any release). Only the build fills in the number. In this way, the number is never in two places.
- If a tag does not have the form `vX.Y.Z` or `vX.Y.Z-rc.N`, the workflow stops before it builds anything. To try this locally, run `python3 scripts/set-version.py <tag> --check`.
- After the build, the workflow checks in the built package that the app reports the same number (`--version`, `Info.plist`).

## Which Macs

- The Mac app is for **Apple silicon** only (M1 or newer, macOS 11 or newer). Intel Macs are not supported. This was decided in KAN-289 (option C). Apple ends support for Intel Macs after macOS 26.
- The build runs on `macos-latest` (arm64) with the lock file `requirements/release-mac.txt` (`aarch64-apple-darwin`).
- `scripts/build-mac.sh` sets `LSMinimumSystemVersion` to `11.0` in `Info.plist`.
- The step "Controles in het gebouwde pakket" (checks in the built package) of the `mac` job in `release.yml` does two checks. It checks that `lipo -archs` reports exactly `arm64`. It also checks that `LSMinimumSystemVersion` is `11.0`.

## Making a release

1. Make sure `main` is green and contains everything for the release.
2. In IntelliJ, start the run configuration **Release maken (tag op main)** (`scripts/release.sh`). The script does these steps:
   1. It checks that you are on a clean, up-to-date `main`.
   2. It asks if the release is a minor or a major. If you give no answer in 10 s, the release is a patch. The script asks the Minor and Major questions itself (`--ask`). `j` or `y` means yes.
   3. It shows `Soort release: patch (v0.3.0 wordt v0.3.1)` (release type: patch, v0.3.0 becomes v0.3.1).
   4. It shows the new version and asks for confirmation.
   5. It pushes the tag.

   For a specific version or a pre-release, run `scripts/release.sh v1.2.0-rc.1`. You can also do these steps by hand. This starts the `Release` workflow:

   ```bash
   git checkout main && git pull
   git tag v1.2.0
   git push origin v1.2.0
   ```

3. Watch the run under **Actions**. The workflow does these steps:
   1. It checks the tag. It checks that the tag is on `main`. It checks that no release with that name exists.
   2. It builds the `.dmg` (ad hoc signed) on `macos-latest`. It builds the `.exe` and `setup.exe` on `windows-latest`. Each job first runs lint, tests and `--selftest`. Afterwards, it runs `--selftest` and a version check in the built package.
   3. It publishes everything in **one** release with `gh release create --generate-notes`. The release notes come from the merged pull requests and commits.
4. Check the release on the releases page. Edit the notes if necessary.

To correct a wrong release, ship a new, higher version. Do not reuse a release. The update check compares version numbers.

## Dry run without publishing

Go to **Actions > Release > Run workflow** and choose a tag name (for example `v0.0.1-rc.1`). The workflow builds and tests everything, but it publishes nothing. GitHub keeps the files for 7 days as an artifact of the run. The workflow does not create a tag or a release.

## Pinned dependencies in releases

`pyproject.toml` contains only lower bounds (`keyring>=25`, ...). Without a lock, every release would bundle the newest version that PyPI has at that moment. A compromised or broken package could then get into an unsigned `.dmg` or `.exe` without notice. A release would also not be reproducible. For this reason, `release.yml` installs from lock files with exact versions and hashes:

- `requirements/release-mac.txt` (Python 3.13, `aarch64-apple-darwin`) and `requirements/release-windows.txt` (Python 3.13, `x86_64-pc-windows-msvc`). Each file has the extras of the platform plus `dev` (PyInstaller, ruff, pytest) and all transitive dependencies.
- `requirements/release-build.in` adds `setuptools`, the build backend of the project. In this way, `pip install --no-build-isolation` does not need to get anything from PyPI without a hash.
- The workflow runs `pip install --require-hashes -r requirements/release-<platform>.txt` and then `pip install --no-deps --no-build-isolation -e .`. In the release, `scripts/build-windows.ps1` gets `-SkipInstall`. Without it, the script would install everything again without hashes. Locally (without that switch), the script works as before.
- The Mac lock is for Apple silicon. The reason is that `macos-latest` is Apple silicon and `scripts/build-mac.sh` builds for its own architecture (no universal2). This is a deliberate choice (KAN-289, option C): Intel Macs are not supported. To support Intel or universal2 later, you must do at least these steps:
  - Use a universal2 Python (python.org) in the workflow.
  - Pass `--target-arch universal2` to PyInstaller.
  - Make sure that every binary wheel is universal2. For example, exclude or replace Pillow.
  - Change the `lipo` check in `release.yml`.
  - Update the README, the download page and `LSMinimumSystemVersion`.

  A separate Intel build needs its own runner and its own lock for `x86_64-apple-darwin`.
- The **regular CI (`ci.yml`) deliberately uses the ranges** from `pyproject.toml`. In this way, you see early when a new version breaks something, even while the release is still on the old version.
- Dependabot (`.github/dependabot.yml`, ecosystem `pip`, directory `/requirements`, monthly) proposes updates of the locks as pull requests. `ci.yml` does not use the locks, so `.github/workflows/release-locks.yml` tests them separately. On every change to `requirements/**` or `pyproject.toml`, that workflow installs the lock on Mac and Windows in the same way as the release. It then runs `pip check`, the tests and the self-test. In a Dependabot PR, check that the hashes are also updated. If they are not updated, regenerate the lock yourself (see below).
- Not covered: Inno Setup. The Windows job installs it through Chocolatey.

**Choice: uv** (not pip-tools). uv can resolve for a different target platform. Because of this, you make both locks on one machine. pip-tools resolves only for the platform that it runs on. With pip-tools, you must make the Windows lock on Windows. The locks are plain requirements files. The workflows install them with pip, without uv.

To regenerate the locks, use [uv](https://docs.astral.sh/uv/):

```bash
scripts/lock-release.sh                              # everything to the newest allowed versions
scripts/lock-release.sh --upgrade-package keyring    # or just one package
```

The script runs `uv pip compile pyproject.toml requirements/release-build.in --extra <mac|windows> --extra dev --generate-hashes --python-version 3.13 --python-platform <aarch64-apple-darwin|x86_64-pc-windows-msvc> -o requirements/release-<platform>.txt`. Commit the changed lock files. Do a dry run (see above) before you push a tag. If you change the dependencies in `pyproject.toml`, also regenerate the locks.

## File names

The release contains files with a fixed name, without a version. Because of this, `https://github.com/david-dvconsulting/huurklaar-notifier/releases/latest/download/<name>` always points to the newest version:

| File | What |
|---|---|
| `Huurklaar-Meldingen.dmg` | Mac (ad hoc signed) |
| `Huurklaar-Meldingen-Setup.exe` | Windows installer (Inno Setup): Start menu, "start at login", clean uninstall. Recommended. |
| `Huurklaar-Meldingen.exe` | Windows, a single file, no installation. Use it to test the app, or on a PC where you cannot install anything. |
| `SHA256SUMS.txt` | checksums of the files above |

The releases page is `https://github.com/david-dvconsulting/huurklaar-notifier/releases/latest`.

## Building locally

You need Python 3.13.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[mac,dev]"          # Windows: ".[windows,dev]"; this uses the ranges, not the release locks
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest
.venv/bin/python -m huurklaar_notifier --selftest
scripts/build-mac.sh                            # .app and .dmg in dist/
```

`scripts/build-mac.sh` accepts a version as an argument (`scripts/build-mac.sh 1.2.0`). Without an argument, it uses `_version.py`. To test a version locally in the same way as CI, first run `python3 scripts/set-version.py v1.2.0`. Afterwards, restore `_version.py` with `git checkout src/huurklaar_notifier/_version.py`.

For Windows, you need PowerShell, Python 3.13 and Inno Setup 6. Run `scripts\build-windows.ps1 -Version 1.2.0`. The script installs the dependencies and runs the self-test. It builds `dist\Huurklaar-Meldingen.exe` and `dist\Huurklaar-Meldingen-Setup-<version>.exe`. It also tests the built `.exe` files. In the release, they get the fixed names from the table above.

## The update check

The app requests `https://api.github.com/repos/david-dvconsulting/huurklaar-notifier/releases/latest` once a day. The request has no sign-in, a time-out of 5 seconds and `User-Agent: HuurklaarMeldingen/<version>`.

- The app stores the time of the next check in `config.json` (in the data folder of the app), so the time stays after a restart. After a failed check, the app tries again after an hour. After it hits the rate limit (GitHub allows 60 requests per hour per IP), the app tries again after six hours.
- A failed check is always silent. Offline, time-out, rate limit, 404 or invalid JSON never cause a notification or a crash.
- The app ignores drafts, prereleases and tags that are not a plain `vX.Y.Z`. The comparison is semantic (`1.10` is higher than `1.9`).
- When there is a newer version, the menu shows **Nieuwe versie vX.Y.Z** (New version vX.Y.Z; nl/fr/en). A click opens the releases page. The automatic replacement of the app is a later step.
- The app builds the link to the releases page itself from the tag. It does not take an address from the response.

To try this on your own Mac, use a local build. It has version `0.0.0`, so it shows "Nieuwe versie" when a release exists.

## Fallback: installers on S3

If GitHub is not sufficient, the installers can be published for each version on S3. This uses the deployment of the Huurklaar repo (in the style of `scripts/deploy-app.sh`). This solution is not built. It is designed only on request.
