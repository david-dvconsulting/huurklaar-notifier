# Huurklaar Meldingen (huurklaar-notifier)

Menu bar app (Mac) and tray app (Windows) in a single Python 3.13 codebase. The app requests `GET /me/notifications` from the Huurklaar API with a read-only notification key. Setup, development and releases are described in `README.md`, versions and builds in `docs/building-and-releasing.md`.

**This repo is public.** Never put a real key, a customer address or personal data in code, tests, fixtures, commit messages or PR texts. Tests use made-up data: `SAMPLE` in `src/huurklaar_notifier/testing/fake_server.py`.

## Commands

```bash
uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -e ".[mac,dev]"   # or: python3 -m venv .venv && .venv/bin/pip install -e ".[mac,dev]"
```

Verification, the same steps as CI. Run them before you say something is done:

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest -q && .venv/bin/python -m huurklaar_notifier --selftest
```

- **In a worktree** you reuse the `.venv` of the main checkout. Thanks to `pythonpath = ["src"]`, `pytest` already tests the worktree's own code. The self-test needs `PYTHONPATH=src`, otherwise it runs the installed copy from the main checkout:
  `PYTHONPATH=src ../../huurklaar-notifier/.venv/bin/python -m huurklaar_notifier --selftest`
- **Release locks**: `release.yml` installs only from `requirements/release-mac.txt` and `requirements/release-windows.txt` (exact versions with hashes, generated with uv by `scripts/lock-release.sh`). If you change the dependencies in `pyproject.toml`, run that script and commit the locks as well. `.github/workflows/release-locks.yml` tests the locks on both platforms; `ci.yml` deliberately uses the ranges.
- **CI** (`.github/workflows/ci.yml`) runs lint, tests and the self-test for a pull request only on `ubuntu-latest` (macOS minutes cost ten times as much), and after a merge to main on `windows-latest` and `macos-latest`. If you change code that differs per platform (`platform/`, `tls.py`, `__main__.py`, the self-test), start a manual CI run on the branch before merging (Actions > CI > Run workflow): it runs on Windows and macOS. A test that fails only on Linux (e.g. because of a path or a socket) is either fixed or explicitly skipped there. `platform/windows.py` cannot run locally on a Mac: keep Windows logic testable in `platform/windows_*.py` and keep Windows differences in mind (file locking, `os.replace` failing when another process or another thread holds the target).
- **Local Mac build** (e.g. to test the URL scheme or a dialog):
  - In a worktree, `scripts/build-mac.sh` needs a `.venv`. Temporarily create a symlink to the `.venv` of the main checkout (`.venv` is in `.gitignore`). Thanks to `--paths src`, the build bundles the code of the worktree.
  - Register the build with `lsregister -f "<path>.app"` (`/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister`).
  - The build uses the same bundle id, Keychain service (`be.huurklaar.meldingen`) and data folder (`~/Library/Application Support/Huurklaar Meldingen`) as an installed app. Check beforehand whether they exist. Clean up afterwards: stop the app, `lsregister -u`, delete `build/`, `dist/` and the symlink, and delete the data folder and the Keychain item if your test created them. Whether the item is yours, you can tell from `cdat` in `security find-generic-password -s be.huurklaar.meldingen` (without `-w`, so it does not show the key).
  - An osascript dialog comes to the front and takes over the keyboard: an Enter or a click from whoever is working at the Mac answers it. Say so beforehand, and list open dialogs with `ps -axo pid,command | grep '[o]sascript'`. `screencapture` does not work without the screen recording permission. You can close a dialog without confirming it with `pkill -x osascript` (exit code ≠ 0, so "cancelled").

## Architecture

- `core/` never imports a GUI.
  - `api.py`: HTTP client.
  - `models.py`: `parse_snapshot` deliberately stays tolerant of new fields.
  - `state.py`: `State` with the statuses, back-off (`BACKOFF_MAX`) and the `seen` logic (`_new_toasts`, `MAX_SEEN`). A poll returns a `Delivery(toasts, withdraw)`: the new notifications (`Toast` with `key` = item id and `group` = kind; for a summary both are `"summary"`) and the ids that disappeared from `seen`. With a truncated list or an error it withdraws nothing. `missed` counts the notifications missed during a pause (in memory only); `_daily_reminder` creates the daily reminder (key `"reminder"`). The summary after a pause has key `"paused"`; both have group `"summary"`.
  - `controller.py`: `Controller` with `_lock`, `poll`, `configure`, `set_language` and `test_connection` (one request with the stored settings, without changing the state or `seen`), and the settings from the menu: `set_pause`/`resume`, `toggle_kind` and `toggle_reminder`. Each one takes `_lock` and then saves. `next_delay()` never waits longer than until the end of a pause or until the next 09:00 (`REMINDER_HOUR`), plus 1 s in both cases.
  - `poller.py`: `Poller` and `UpdatePoller`, each on its own thread.
  - `menu.py`: `build_menu` groups the items per kind (`group_items`; `_distribute` divides the 10 slots round-robin), adds the due date (`due_label`) and, with multiple accounts, the account name at the end, and shortens labels with `_fit` (first the title, then the property; date and account stay whole). `Entry.default` is the default item that a left click on the tray icon runs. `title_for` and `title_style` give the text and the colour (red when overdue, Mac) next to the logo. `MenuCache` skips redrawing when menu and title stayed the same. New parameters of `build_menu` are added as keyword arguments with a default value (like `base_url`), so existing calls keep working. Settings in the menu are a prefix action (`LANGUAGE_PREFIX`, `PAUSE_PREFIX`, `KIND_PREFIX`) or a fixed action (`REMINDER`), handled in `AppActions.handle`. The values come from `View`, which the controller fills under the lock. The submenu "Meldingen voor" (Notifications for; `kind_entries`) follows `GROUP_ORDER`.
  - `defaults.py`: the default API address (production) and, per known API address, the web address of the app (`app_url_for`). If the API domain changes, change it here only. Also `AUTHOR` (DV Consulting) and `PROJECT_URL` (the GitHub repo, opened by the menu item "Over" (About)); the same details are in `pyproject.toml`, `scripts/build-mac.sh` (`NSHumanReadableCopyright`), `scripts/make-version-file.py` (`LegalCopyright`) and the installer. Deliberately no email address: the repo is public.
  - `app_actions.py`: `AppActions`, what Mac and Windows share: handling menu clicks (`handle`), draining the result queue (`drain`), the first start (`first_run`: opens the settings once per process if the address or the key is missing, and reads the key storage on its own thread) and the settings flow (`settings`, with a lock so that only one window is open at a time; after Bewaren (Save) it tests the connection and shows exactly one message). The platform only supplies an `AppUi` with the dialog, the alert, the rebuild and the quit. Choose an error message by exception type (`InvalidUrlError`, `InvalidKeyError`, `AuthError`, `NetworkError` from `api.py`; `AuthError` and `NetworkError` are subclasses of `ApiError`, so test them first), never by the error text.
  - `link.py`: `parse_link` and `link_host` for the link URL `huurklaar-meldingen://koppel?api=…&key=…` (KAN-267). A link comes from outside and is untrusted, because any web page can open one. That is why `parse_link` validates strictly, and `AppActions.apply_link` always asks for confirmation first, showing only the host (`AppUi.confirm`). After linking it shows the same connection test as Bewaren (Save). A link also counts as a first start: `first_run` then no longer opens a settings window, because on a cold start through the link that window would push the link question aside. Never log the link.
  - `i18n.py`: catalogue in NL, FR and EN, with NL as the source.
  - `config.py`: `ConfigStore` writes atomically. Every field loads tolerantly: a missing or invalid value gives the default (`_number`, `_kinds`, `_reminder_flag`, `_date`), because the file may come from an older version or may have been edited by hand.
  - Also: `updates.py`, `tls.py`, `version.py`, `selftest.py`.
- `platform/` contains, per platform, the key storage, the notifications, the menu bar or tray, "start at login" and the URL scheme.
  - `base.py`: the protocols. A `Notifier` has `notify(toast)` and `withdraw(keys)`, and never raises. `drain` withdraws first and shows afterwards.
  - `macos.py`: rumps. `MenubarApp._tick` runs every second on the main thread. Never read the Keychain there: that can show a system window and make the menu bar hang. Keep it thin: whatever works without AppKit lives in a pure module that CI also tests on Linux and Windows.
    - `MacNotifier` uses `request_id(key)` from `macos_ids.py` (no AppKit, so also testable on Windows) as the id, and the group as `threadIdentifier`.
    - `macos_location.py` (pure): `is_transient_location` (a dmg under `/Volumes/`, App Translocation) and writing and repairing the LaunchAgent. From a transient path, "Start bij aanmelden" (Start at login) writes nothing, and at startup `run()` repairs a LaunchAgent with an outdated path (KAN-287). Bundled builds only (`sys.frozen`): in development `sys.executable` is a Python interpreter.
    - `settings_dialog.py` (pure) and `macos_settings.py` (AppKit): the settings window in a single NSAlert (KAN-288). AppKit only on the main thread: `run_on_main` schedules the window with `AppHelper.callAfter` and waits. Only opening it has a time-out; after that the user may type for as long as they like. If the window fails, the osascript fallback follows.
    - An app without a Dock icon (`LSUIElement`) only gets Cmd+V in a text field when `NSApp.mainMenu` has an Edit menu (`ensure_edit_menu`), and a window only comes to the front after `activateIgnoringOtherApps_`.
    - `osascript` dialogs (`alert`, `ask`, `confirm`) block until the user clicks: never on the main thread while rumps is running, but on a daemon thread.
  - `macos_links.py`: receives the link as the Apple Event `kAEGetURL`. The handler is registered before the run loop, so the link also arrives on a cold start. The scheme is declared in the Info.plist (`scripts/build-mac.sh`).
  - `windows.py`: only importable on Windows. `TrayApp._loop` runs on its own thread.
  - `windows_notifier.py`: win11toast with `tag` = `toast_tag(key)` (sha1, 32 characters; Windows allows at most 64) and the fixed group `"hk"`. `clear_toast` without a tag clears the whole group, so always pass a tag. win11toast is not installed on the Mac: read its API in the source (`win11toast.py` in the GitHub repo `GitHub30/win11toast`).
  - `windows_link.py`: Windows starts a new process for a link. If the app is already running, that process forwards the link through a named pipe per user. Only bytes go over that pipe, never pickle (`send`/`recv`). The scheme lives under HKCU: the installer and `register_url_scheme` set it, the uninstaller and `--forget` remove it.
- `testing/` contains the fake server, the fake GitHub and the fake platform. Both the tests and `--selftest` use them.

## Threads: read this before you touch state or config

- Three threads touch the same state: the poll thread (`Poller`), the update check thread (`UpdatePoller`) and the UI (the rumps timer on the Mac, the tray thread on Windows).
- Everything that changes `controller.config` or `controller.state`, or saves the config, happens under `Controller._lock`. `ConfigStore.save` also takes a lock of its own.
- **No loop may ever stop because of an unexpected error.** Put a `try/except Exception` around the loop body, log only `type(e).__name__` and try again later. Only set `_rebuild_needed` to `False` after `_render()` has succeeded.
- Tests with threads always wait with a time-out (`Event.wait(timeout=2)`) and stop the thread at the end (`stop()` plus `join(timeout=...)`). Make waiting times configurable through a constructor parameter with a default value, so the test stays fast.
- A concurrency test must fail on the old code. Check that once.

## Time: pause, reminder and the poll interval

- Logic that depends on the clock uses the injectable `Controller._clock`, never `time.time()`. `State` gets no clock: the controller passes in `paused` and `reminder_day`.
- The poll interval comes from the server and can be hours long (the admin default is 6 h). Anything that must happen at a fixed time is therefore bounded by `Controller.next_delay()`. Without that, it can happen up to a full interval late. Calculate in local time with `time.mktime((…, tm_isdst=-1))` (`tomorrow_morning`, `next_local_time`), so daylight saving time is handled correctly.
- Tests and `--selftest` that use the real clock get 08:00 local time (`vroeg_op_de_dag` in `tests/conftest.py`). Otherwise, after 9:00 the reminder adds a notification and the result depends on the hour of the test run. Derive expectations from `time.localtime`/`time.mktime`, not from a fixed time zone (CI runs on Linux, Windows and macOS).

## Staying compatible with the server

- We cannot change versions that are already installed, so the app must tolerate new fields and values from the server.
  - An unknown `kind` shows "Melding" (Notification; `kind.other`).
  - `translate` returns the key itself when a key is missing.
  - An error in the menu must never stop the polling.
- The server sends at most 50 items, sorted by urgency. If there are more, the response contains `truncated: true`. In that case `seen` also keeps ids that fall outside the list, otherwise duplicate notifications follow.

## Conventions

- **Language**: comments, docstrings, test names, UI texts and commit messages in Dutch. Identifiers in English. The README, `docs/` and this file are in English.
- **Style**: ruff with line length 110 and the rules E, F, I, UP, B and SIM. Comments explain the *why*.
- **UI text**: add every new key in NL, FR and EN in `core/i18n.py`. A test checks that all languages have the same keys. The catalogue has no plural rules: give the singular its own key (`toast.paused_summary_one`, `count.task.one`/`count.task.many`), otherwise it says "1 nieuwe meldingen" (1 new notifications).
- **Logs**: never a key, title, address or any other data. Only the error type.
- **Menu tests**: pass `build_menu` a fixed `today` (the due dates in `SAMPLE` are in the past, so otherwise the label depends on the day). If you compare two menus one after the other, also give `Controller` a fixed `clock`: "Bijgewerkt om HH:MM" (Updated at HH:MM) is in the menu and changes every minute.
- **Workflow per Jira ticket**: one branch `kan-<task>-<short-description>` and one PR per task, with one commit per sub-task. A commit is named `KAN-<sub-task>: <what>` and explains the why in its body. The full workflow is in the `kan-ticket` skill in the app repo (`huurklaar/.claude/skills/kan-ticket/SKILL.md`). Do not put internal links (Jira site) in PR texts, because the repo is public.
- **Git identity**: commits are authored by `david <david@dvconsulting.be>`, set in the repo config (`git config user.email`). If the global git config has a different address, set the identity per repo. Check the author with `git log -1 --format='%an <%ae>'` before you push: this repo is public.
- **Releases**: see the README and `scripts/release.sh`. Never move or reuse a tag. Only make a release when explicitly asked to.
- **Apple silicon only** (KAN-289, option C): the Mac build is arm64 with `LSMinimumSystemVersion` 11.0, and `release.yml` checks both. Introducing Intel or universal2 is a new decision; what would have to change is described in `docs/building-and-releasing.md`. Prove a build or workflow change with a dry run of `Release` (workflow_dispatch on the branch, publishes nothing).
