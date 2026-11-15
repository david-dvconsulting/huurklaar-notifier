# Building and releasing

For anyone who wants to build locally or ship a new version. Everything is free: the repo is public, so GitHub Actions costs nothing and releases can be read without signing in. No secrets are needed.

## The version: the tag is the source

- A release is called `vX.Y.Z` (e.g. `v1.2.0`). A pre-release is called `vX.Y.Z-rc.N` (e.g. `v1.2.0-rc.1`) and becomes a GitHub *prerelease*; the update check ignores it.
- The tag is independent of the `vX.Y.Z` tags of the Huurklaar app itself (a different repo, its own series, starting at `v0.1.0`).
- `scripts/set-version.py <tag>` writes the number into `src/huurklaar_notifier/_version.py`. In git, that file always contains the placeholder `0.0.0` (older than any release); only the build fills it in. That way the number is never kept in two places.
- A tag that does not have the form `vX.Y.Z` or `vX.Y.Z-rc.N` stops the workflow before anything is built (`python3 scripts/set-version.py <tag> --check` tries it locally).
- Afterwards the workflow checks in the built package that the app reports the same number (`--version`, `Info.plist`).

## Which Macs

- The Mac app is for **Apple silicon** only (M1 or newer, macOS 11 or newer). Intel Macs are not supported: decided in KAN-289 (option C). Apple ends support for Intel Macs after macOS 26.
- The build runs on `macos-latest` (arm64) with the lock file `requirements/release-mac.txt` (`aarch64-apple-darwin`).
- `scripts/build-mac.sh` sets `LSMinimumSystemVersion` to `11.0` in `Info.plist`.
- The step "Controles in het gebouwde pakket" (checks in the built package) of the `mac` job in `release.yml` checks that `lipo -archs` reports exactly `arm64` and that `LSMinimumSystemVersion` is `11.0`.

## Making a release

1. Make sure `main` is green and contains everything that should be in the release.
2. In IntelliJ, start the run configuration **Release maken (tag op main)** (`scripts/release.sh`). The script checks that you are on a clean, up-to-date `main`, first asks whether it is a minor or a major (no answer within 10 s = patch), shows the new version, asks for confirmation and pushes the tag. The script asks the Minor and Major questions itself (`--ask`; `j` or `y` means yes); it then shows `Soort release: patch (v0.3.0 wordt v0.3.1)` (release type: patch, v0.3.0 becomes v0.3.1) and asks for confirmation. A specific version or a pre-release: `scripts/release.sh v1.2.0-rc.1`. You can also do it by hand (this starts the `Release` workflow):

   ```bash
   git checkout main && git pull
   git tag v1.2.0
   git push origin v1.2.0
   ```

3. Follow the run under **Actions**. The workflow:
   1. checks the tag, that it is on `main`, and that no release with that name exists yet;
   2. builds the `.dmg` (ad hoc signed) on `macos-latest` and the `.exe` and `setup.exe` on `windows-latest`; each job first runs lint, tests and `--selftest`, and afterwards `--selftest` and a version check in the built package;
   3. publishes everything in **one** release with `gh release create --generate-notes` (the release notes come from the merged pull requests and commits).
4. Check the release on the releases page and edit the notes if needed.

A wrong release is fixed by shipping a new, higher version. Never reuse a release: the update check compares version numbers.

## Dry run without publishing

Under **Actions > Release > Run workflow** you choose a tag name (e.g. `v0.0.1-rc.1`). The workflow builds and tests everything but publishes nothing; the files are kept for 7 days as an artifact of the run. No tag or release is created.

## Pinned dependencies in releases

`pyproject.toml` contains only lower bounds (`keyring>=25`, ...). Without a lock, every release would bundle the newest version PyPI has at that moment: a compromised or broken package could end up unnoticed in an unsigned `.dmg` or `.exe`, and a release would not be reproducible. That is why `release.yml` installs from lock files with exact versions and hashes:

- `requirements/release-mac.txt` (Python 3.13, `aarch64-apple-darwin`) and `requirements/release-windows.txt` (Python 3.13, `x86_64-pc-windows-msvc`), each with the extras of the platform plus `dev` (PyInstaller, ruff, pytest) and with all transitive dependencies.
- `requirements/release-build.in` adds `setuptools`, the build backend of the project. That way `pip install --no-build-isolation` does not have to fetch anything from PyPI without a hash.
- The workflow runs `pip install --require-hashes -r requirements/release-<platform>.txt` and then `pip install --no-deps --no-build-isolation -e .`. In the release, `scripts/build-windows.ps1` gets `-SkipInstall`, otherwise the script would install everything once more without hashes. Locally (without that switch) the script works as before.
- The Mac lock is for Apple silicon because `macos-latest` is Apple silicon and `scripts/build-mac.sh` builds for its own architecture (no universal2). That is a deliberate choice (KAN-289, option C): Intel Macs are not supported. To support Intel or universal2 later, you need at least to: use a universal2 Python (python.org) in the workflow, pass `--target-arch universal2` to PyInstaller, make sure every binary wheel is universal2 (Pillow, for example, you exclude or replace), adjust the `lipo` check in `release.yml`, and update the README, the download page and `LSMinimumSystemVersion`. A separate Intel build would need its own runner and its own lock for `x86_64-apple-darwin`.
- The **regular CI (`ci.yml`) deliberately uses the ranges** from `pyproject.toml`: that way you notice early when a new version breaks something, even while the release is still on the old version.
- Dependabot (`.github/dependabot.yml`, ecosystem `pip`, directory `/requirements`, monthly) proposes updates of the locks as pull requests. Because `ci.yml` does not use the locks, `.github/workflows/release-locks.yml` tests them separately: on every change to `requirements/**` or `pyproject.toml`, that workflow installs the lock on Mac and Windows the way the release does, and runs `pip check`, the tests and the self-test. In a Dependabot PR, check that the hashes were updated too; if they were not, regenerate the lock yourself (see below).
- Not covered: Inno Setup, which the Windows job installs through Chocolatey.

**Choice: uv** (not pip-tools). uv can resolve for a different target platform, so you make both locks on one machine; pip-tools only resolves for the platform it runs on, so the Windows lock would have to be made on Windows. The locks themselves are plain requirements files: the workflows install them with pip, without uv.

Regenerating the locks (requires [uv](https://docs.astral.sh/uv/)):

```bash
scripts/lock-release.sh                              # everything to the newest allowed versions
scripts/lock-release.sh --upgrade-package keyring    # or just one package
```

The script runs `uv pip compile pyproject.toml requirements/release-build.in --extra <mac|windows> --extra dev --generate-hashes --python-version 3.13 --python-platform <aarch64-apple-darwin|x86_64-pc-windows-msvc> -o requirements/release-<platform>.txt`. Commit the changed lock files and do a dry run (see above) before you push a tag. If you change the dependencies in `pyproject.toml`, regenerate the locks as well.

## File names

The release contains files with a fixed name, without a version, so that `https://github.com/david-dvconsulting/huurklaar-notifier/releases/latest/download/<name>` always points to the newest version:

| File | What |
|---|---|
| `Huurklaar-Meldingen.dmg` | Mac (ad hoc signed) |
| `Huurklaar-Meldingen-Setup.exe` | Windows installer (Inno Setup): Start menu, "start at login", clean uninstall. Recommended. |
| `Huurklaar-Meldingen.exe` | Windows, a single file, no installation (to try it out, or on a PC where you are not allowed to install anything) |
| `SHA256SUMS.txt` | checksums of the files above |

The releases page itself is `https://github.com/david-dvconsulting/huurklaar-notifier/releases/latest`.

## Building locally

Python 3.13 is required.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[mac,dev]"          # Windows: ".[windows,dev]"; this uses the ranges, not the release locks
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest
.venv/bin/python -m huurklaar_notifier --selftest
scripts/build-mac.sh                            # .app and .dmg in dist/
```

`scripts/build-mac.sh` accepts a version as an argument (`scripts/build-mac.sh 1.2.0`); without an argument it uses `_version.py`. To test a version locally the way CI does, first run `python3 scripts/set-version.py v1.2.0`, and afterwards restore `_version.py` with `git checkout src/huurklaar_notifier/_version.py`.

Windows (PowerShell, Python 3.13 and Inno Setup 6): `scripts\build-windows.ps1 -Version 1.2.0`. The script installs the dependencies, runs the self-test, builds `dist\Huurklaar-Meldingen.exe` and `dist\Huurklaar-Meldingen-Setup-<version>.exe`, and tests the built `.exe` files. In the release they get the fixed names from the table above.

## The update check

Once a day the app requests `https://api.github.com/repos/david-dvconsulting/huurklaar-notifier/releases/latest`, without signing in, with a time-out of 5 seconds and `User-Agent: HuurklaarMeldingen/<version>`.

- The time of the next check is stored in `config.json` (in the app's data folder), so it survives a restart. After a failed check we try again after an hour; after hitting the rate limit (GitHub allows 60 requests per hour per IP), after six hours.
- Failing is always silent: offline, time-out, rate limit, 404 or invalid JSON never cause a notification or a crash.
- Drafts, prereleases and tags that are not a plain `vX.Y.Z` are ignored. The comparison is semantic (`1.10` is higher than `1.9`).
- When there is a newer version, the menu shows **Nieuwe versie vX.Y.Z** (New version vX.Y.Z; nl/fr/en). A click opens the releases page. Replacing the app automatically is a later step.
- The app builds the link to the releases page itself from the tag; it does not take an address from the response.

Trying it on your own Mac: a local build has version `0.0.0` and therefore shows "Nieuwe versie" as soon as a release exists.

## Fallback: installers on S3

Should GitHub ever not be enough, the installers could be published per version on S3, through the deployment of the Huurklaar repo (in the style of `scripts/deploy-app.sh`). That has not been built; it will only be worked out on request.
