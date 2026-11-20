# Huurklaar Meldingen

This is a menu bar app (Mac) and a tray app (Windows). It shows notifications for tasks and required actions in Huurklaar (KAN-117). The two apps use one Python codebase. The app sends requests to the Huurklaar API with a read-only **notification key** (`GET /me/notifications`, see `docs/meldingen.md` in the Huurklaar repo).

> Do not put a real key, a customer address or personal data in code, tests or fixtures. This repo is public. The tests use made-up data (`testing/fake_server.py`).

## Setup

1. Choose **Instellingen…** (Settings) in the menu.
2. Enter the **Huurklaar API address**.
3. Enter the **notification key** (Huurklaar > My profile > Notifications).

The app fills in the production address by default. If you use the test environment or a local environment, replace the address with the address from the table below. The app stores the address in `~/Library/Application Support/Huurklaar Meldingen/config.json` (Mac) or `%APPDATA%\Huurklaar Meldingen\config.json` (Windows). The app stores the key only in the Keychain (Mac) or the Windows Credential Manager. It never stores the key in a file or a log. The app accepts only `https`, except for localhost.

| Environment | App | API address to enter |
|---|---|---|
| Production (PRD) | https://app.huurklaar.be | `https://zf02fcpfvi.execute-api.eu-central-1.amazonaws.com` |
| Test (DEV) | https://app-dev.huurklaar.be | `https://gqncu23i4i.execute-api.eu-central-1.amazonaws.com` |
| Local development | http://localhost:5173 | `http://localhost:3000` |

A key belongs to one environment. Create the key in the app of the same environment as the address. The page Huurklaar > My profile > Notifications also shows the correct address, with a copy button.

## One-click linking

The app registers the URL scheme `huurklaar-meldingen://`. "Koppel de app" in Huurklaar (My profile > Notifications) opens this scheme. After you confirm in the app, the app fills in the address and the key in one click. On the Mac, this works after you start the app once from Applications. On Windows, the installer registers the scheme. The app also registers it at every start.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[mac,dev]"   # Windows: ".[windows,dev]"
.venv/bin/pytest            # tests (no GUI needed)
.venv/bin/ruff check . && .venv/bin/ruff format .
.venv/bin/python -m huurklaar_notifier --selftest
.venv/bin/python -m huurklaar_notifier   # the app itself
scripts/build-mac.sh        # .app + .dmg in dist/ (ad hoc signed)
```

CI (`.github/workflows/ci.yml`) runs lint, tests and the self-test. For a pull request, it runs on Linux. After a merge to `main`, it runs on Windows and macOS. It also runs on Windows and macOS when you start it by hand under **Actions > CI > Run workflow**. A change that only touches documentation does not start CI.

## Layout

- `core/`: the API client, states and back-off, menu model, translations (nl/fr/en), controller, poller and update check. It never imports a GUI.
- `platform/`: for each platform, the key storage (`keyring`), notifications, menu bar or tray and "start at login". The Mac code is in `macos.py`. The Windows code is in `windows.py`, which you can import only on Windows. The logic that you can test is in `windows_registry.py`, `windows_notifier.py`, `windows_icon.py` and `windows_menu.py`.
- `testing/`: a fake server and a fake platform. `--selftest` also uses them.
- `prototype/`: the notification prototype. It led to the choice for `UNUserNotificationCenter`.

## Mac

**Requirements:** you need a Mac with an Apple chip (M1 or newer). The Mac must have macOS 11 or newer. **Intel-based Macs are not supported.** The release build is arm64 only. Apple ends support for Intel Macs after macOS 26. To check your Mac, open Apple menu > About This Mac. "Chip: Apple M…" is supported. "Processor: Intel…" is not supported.

The app is ad hoc signed (free, no Apple Developer account). Gatekeeper shows a warning once. Choose **Open Anyway** in System Settings > Privacy & Security.

## Windows

**How it works**
- The tray icon uses `pystray`. It shows the logo with a badge:
  - a counter (orange, red when tasks are overdue)
  - `!` (not signed in or key invalid)
  - a grey dot (no connection)
  - no badge (nothing to do)
- Notifications use `win11toast` under the **AppUserModelID** `be.huurklaar.meldingen`. The app registers this ID under `HKCU\Software\Classes\AppUserModelId` (name and icon), so the notification does not say "Python". A click opens the address directly through Windows (protocol toast). Nothing waits for a callback.
- "Start at login" is the value `HuurklaarMeldingen` under `HKCU\...\Run` (current user only, no admin rights). The installer writes the same value.
- Only one instance runs at a time. The app uses a named mutex for this, and the installer uses it too.

**Build on Windows (PowerShell)**

```powershell
py -3.13 -m venv .venv; .venv\Scripts\Activate.ps1
scripts\build-windows.ps1 -Version 0.1.0     # add -SkipInstaller if Inno Setup is not installed
```

The script runs the self-test before the build. It also runs the self-test inside every built `.exe` (with a time-out). The script makes `dist\Huurklaar-Meldingen.exe` (single file) and `dist\Huurklaar-Meldingen-Setup-<version>.exe` (Inno Setup 6, free). The installer installs to `%LOCALAPPDATA%\Programs` without admin rights. It adds a Start menu entry and an optional "start at login". A clean uninstall also removes the stored key. The installer uses a folder build (`--onedir`) and not the single file. The folder build starts faster and is less likely to cause a false virus warning.

**First start (SmartScreen)**: the `.exe` and the installer are not signed (no paid certificate). Windows shows "Windows protected your PC" once. Choose **More info**, then choose **Run anyway**. A warning from an antivirus scanner is a false positive.

## Making a release

GitHub Actions builds and publishes the releases (`.github/workflows/release.yml`). It is free (the repo is public) and needs no secrets.

1. Make sure `main` is green (CI) and contains everything for the release.
2. Do an optional dry run. On GitHub, go to **Actions > Release > Run workflow**, or run:

   ```bash
   gh workflow run release.yml --ref main -f tag=v0.0.1-rc.1
   ```

   The dry run builds and tests everything for both platforms, but it publishes nothing. The files are available for 7 days as an artifact of the run.
3. Create the tag on `main` and push it. The tag is the only source of the version number:

   ```bash
   git checkout main && git pull
   git tag v0.2.0
   git push origin v0.2.0
   ```

   Use `vX.Y.Z` for a release. A pre-release is `vX.Y.Z-rc.N`. The update check ignores a pre-release.
4. Watch the run under **Actions**. The run does these steps:
   1. It checks the tag.
   2. It builds the Mac `.dmg` and the Windows `.exe` and setup. Each job runs lint, tests and the self-test. Then it runs the self-test and a version check on the built package.
   3. It publishes everything in **one** GitHub release with generated notes.

   If a macOS runner is busy, the Mac job can wait a long time or the system can cancel it. In that case, run the failed job again with `gh run rerun <run-id> --failed`.
5. Check the release page. Edit the notes if necessary.

The release files have fixed names. Because of this, `https://github.com/david-dvconsulting/huurklaar-notifier/releases/latest/download/<name>` always points to the newest version:

| File | What |
|---|---|
| `Huurklaar-Meldingen.dmg` | Mac, Apple silicon only (ad hoc signed) |
| `Huurklaar-Meldingen-Setup.exe` | Windows installer (recommended) |
| `Huurklaar-Meldingen.exe` | Windows, single file, no installation |
| `SHA256SUMS.txt` | checksums of the files above |

To correct a wrong release, publish a new, higher version. Do not reuse a version and do not move a tag. The update check compares version numbers. The app checks for a newer release once a day. It shows "Nieuwe versie" in its menu.

For more detail (version rules, local builds, the update check), see [docs/building-and-releasing.md](docs/building-and-releasing.md).
