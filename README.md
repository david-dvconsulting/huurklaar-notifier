# Huurklaar Meldingen

A menu bar app (Mac) and tray app (Windows) that shows notifications for tasks and required actions in Huurklaar (KAN-117). One Python codebase. The app talks to the Huurklaar API with a read-only **notification key** (`GET /me/notifications`, see `docs/meldingen.md` in the Huurklaar repo).

> This repo is public: never put a real key, a customer address or personal data in code, tests or fixtures. The tests use made-up data (`testing/fake_server.py`).

## Setup

Choose **Instellingen…** (Settings) in the menu and enter the **Huurklaar API address** (for dev see `docs/developer_info.md` in the Huurklaar repo; locally `http://localhost:3000`) and the **notification key** (Huurklaar > My profile > Notifications). The address is stored in `~/Library/Application Support/Huurklaar Meldingen/config.json` (Mac) or `%APPDATA%\Huurklaar Meldingen\config.json` (Windows). The key is stored only in the Keychain (Mac) or the Windows Credential Manager, never in a file or a log. Only `https` is allowed, except for localhost.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[mac,dev]"   # Windows: ".[windows,dev]"
.venv/bin/pytest            # tests (no GUI needed)
.venv/bin/ruff check . && .venv/bin/ruff format .
.venv/bin/python -m huurklaar_notifier --selftest
.venv/bin/python -m huurklaar_notifier   # the app itself
scripts/build-mac.sh        # .app + .dmg in dist/ (ad hoc signed)
```

CI (`.github/workflows/ci.yml`) runs lint, tests and the self-test on Windows and macOS for every push and pull request.

## Layout

- `core/`: API client, states and back-off, menu model, translations (nl/fr/en), controller, poller and update check. Never imports a GUI.
- `platform/`: per platform the key storage (`keyring`), notifications, menu bar or tray and "start at login". `macos.py`, and for Windows `windows.py` (only importable there) with the testable logic in `windows_registry.py`, `windows_notifier.py`, `windows_icon.py` and `windows_menu.py`.
- `testing/`: fake server and fake platform, also used by `--selftest`.
- `prototype/`: the notification prototype that led to the choice for `UNUserNotificationCenter`.

## Mac

The app is ad hoc signed (free, no Apple Developer account). Gatekeeper warns once: choose **Open Anyway** in System Settings > Privacy & Security.

## Windows

**How it works**
- Tray icon with `pystray`. It shows the logo with a badge: a counter (orange, red when tasks are overdue), `!` (not signed in or key invalid), a grey dot (no connection), no badge (nothing to do).
- Notifications with `win11toast` under the **AppUserModelID** `be.huurklaar.meldingen`, registered under `HKCU\Software\Classes\AppUserModelId` (name and icon), so the notification does not say "Python". A click opens the address directly through Windows (protocol toast): nothing waits for a callback.
- "Start at login": the value `HuurklaarMeldingen` under `HKCU\...\Run` (current user only, no admin rights). The installer writes the same value.
- One instance at a time (a named mutex, also used by the installer).

**Building on Windows (PowerShell)**

```powershell
py -3.13 -m venv .venv; .venv\Scripts\Activate.ps1
scripts\build-windows.ps1 -Version 0.1.0     # add -SkipInstaller if Inno Setup is not installed
```

The script runs the self-test before building and inside every built `.exe` (with a time-out), and produces `dist\Huurklaar-Meldingen.exe` (single file) and `dist\Huurklaar-Meldingen-Setup-<version>.exe` (Inno Setup 6, free). The installer installs to `%LOCALAPPDATA%\Programs` without admin rights, adds a Start menu entry and an optional "start at login", and a clean uninstall also removes the stored key. It uses a folder build (`--onedir`) rather than the single file: it starts faster and is less likely to trigger a false virus warning.

**First start (SmartScreen)**: the `.exe` and the installer are not signed (no paid certificate). Windows shows "Windows protected your PC" once. Choose **More info**, then **Run anyway**. A warning from an antivirus scanner is a false positive.

## Making a release

Releases are built and published by GitHub Actions (`.github/workflows/release.yml`). It is free (the repo is public) and needs no secrets.

1. Make sure `main` is green (CI) and contains everything that should be in the release.
2. Optional dry run: on GitHub go to **Actions > Release > Run workflow**, or run:

   ```bash
   gh workflow run release.yml --ref main -f tag=v0.0.1-rc.1
   ```

   This builds and tests everything for both platforms but publishes nothing. The files are available for 7 days as an artifact of the run.
3. Create the tag on `main` and push it. The tag is the only source of the version number:

   ```bash
   git checkout main && git pull
   git tag v0.2.0
   git push origin v0.2.0
   ```

   Use `vX.Y.Z` for a release. A pre-release is `vX.Y.Z-rc.N`; the update check ignores it.
4. Follow the run under **Actions**. It checks the tag, builds the Mac `.dmg` and the Windows `.exe` and setup (each job runs lint, tests and the self-test, and then the self-test and a version check on the built package), and publishes everything in **one** GitHub release with generated notes. If a macOS runner is busy, the Mac job can wait a long time or be cancelled: re-run the failed job with `gh run rerun <run-id> --failed`.
5. Check the release page and edit the notes if needed.

The release files have fixed names, so `https://github.com/david-dvconsulting/huurklaar-notifier/releases/latest/download/<name>` always points to the newest version:

| File | What |
|---|---|
| `Huurklaar-Meldingen.dmg` | Mac (ad hoc signed) |
| `Huurklaar-Meldingen-Setup.exe` | Windows installer (recommended) |
| `Huurklaar-Meldingen.exe` | Windows, single file, no installation |
| `SHA256SUMS.txt` | checksums of the files above |

A wrong release is fixed by publishing a new, higher version. Never reuse a version or move a tag: the update check compares version numbers. The app checks for a newer release once a day and shows "Nieuwe versie" in its menu.

More detail (version rules, local builds, the update check): [docs/bouwen-en-releasen.md](docs/bouwen-en-releasen.md) (in Dutch).
