"""Windows: tray-app met `pystray`, meldingen met `win11toast`, sleutel in de Credential Manager via `keyring`.

Dit bestand mag enkel op Windows geïmporteerd worden; de logica die ook zonder Windows getest kan worden zit in
`windows_registry`, `windows_notifier`, `windows_icon` en `windows_menu`.
"""

from __future__ import annotations

import contextlib
import ctypes
import logging
import os
import queue
import sys
import threading
import webbrowser
from pathlib import Path

import pystray

from ..core.api import is_openable
from ..core.controller import Controller
from ..core.menu import (
    AUTOSTART,
    LANGUAGE_PREFIX,
    QUIT,
    REFRESH,
    SETTINGS,
    Entry,
    MenuCache,
    build_menu,
    status_line,
)
from ..core.poller import Poller, UpdatePoller
from ..core.state import Toast
from . import windows_dialogs
from .keyring_store import KeyringSecretStore
from .windows_icon import badge_for, render_icon
from .windows_menu import build_items, tooltip
from .windows_notifier import WindowsNotifier
from .windows_registry import APP_NAME, RunKeyAutostart, register_app_id, run_command
from .windows_single import acquire

log = logging.getLogger(__name__)


def resource(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    return base / "assets" / name


def open_url(url: str) -> None:
    if is_openable(url):
        webbrowser.open(url)


class WindowsPlatform:
    def __init__(self) -> None:
        self.secrets = KeyringSecretStore()
        self.autostart = RunKeyAutostart(lambda: run_command(getattr(sys, "frozen", False), sys.executable))
        icon = resource("AppIcon.ico")
        register_app_id(APP_NAME, str(icon) if icon.exists() else None)
        self.notifier = WindowsNotifier()

    def data_dir(self) -> Path:
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME

    def system_languages(self) -> list[str]:
        buf = ctypes.create_unicode_buffer(85)
        ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, len(buf))
        return [buf.value] if buf.value else []

    def open_url(self, url: str) -> None:
        open_url(url)


class TrayApp:
    def __init__(self, controller: Controller) -> None:
        self.c = controller
        self._results: queue.Queue[list[Toast]] = queue.Queue()
        self._rebuild_needed = True
        self._menu_cache = MenuCache()
        self._stop = threading.Event()
        self._poller = Poller(controller, self._results.put)
        # Een gevonden update tekent het menu opnieuw (een lege lijst = geen meldingen, wel herbouwen).
        self._updates = UpdatePoller(controller, lambda: self._results.put([]))
        self.icon = pystray.Icon("huurklaar", render_icon(None), APP_NAME, menu=pystray.Menu())

    def run(self) -> None:
        self._poller.start()
        self._updates.start()
        self.icon.run(setup=self._start_loop)  # blokkeert tot `icon.stop()`

    def _start_loop(self, icon: pystray.Icon) -> None:
        icon.visible = True
        threading.Thread(target=self._loop, name="tray-loop", daemon=True).start()

    # De lus vervangt de menubalk-timer van de Mac: meldingen tonen en het menu en icoon vernieuwen.
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                try:
                    while True:
                        for t in self._results.get_nowait():
                            self.c.platform.notifier.notify(t.title, t.body, t.url)
                        self._rebuild_needed = True
                except queue.Empty:
                    pass
                if self._rebuild_needed:
                    self._render()
                    self._rebuild_needed = False  # pas na een geslaagde render, anders opnieuw proberen
            except Exception as e:  # een fout mag de tray-lus niet stoppen; enkel het type loggen
                log.warning("tray-lus mislukt: %s", type(e).__name__)
            self._stop.wait(1.0)

    def _render(self) -> None:
        c = self.c
        v = c.view()  # één korte lock-sectie; daarna werken we op de kopie
        entries = build_menu(
            v.state, v.language, v.language_setting, c.platform.autostart.is_enabled(), v.update
        )
        badge = badge_for(v.state)
        title = tooltip(status_line(v.state, v.language), APP_NAME)
        if not self._menu_cache.changed(entries, (badge, title)):
            return  # niets veranderd: icoon en menu niet opnieuw bouwen
        try:
            self.icon.icon = render_icon(badge)
            self.icon.title = title
            self.icon.menu = pystray.Menu(
                *build_items(entries, pystray.MenuItem, pystray.Menu, pystray.Menu.SEPARATOR, self._on_entry)
            )
            self.icon.update_menu()
        except Exception:
            self._menu_cache.reset()  # tekenen mislukt: de volgende poging moet opnieuw tekenen
            raise

    def _on_entry(self, e: Entry) -> None:
        if e.url:
            open_url(e.url)
        elif e.action == REFRESH:
            self.c.wake.set()
        elif e.action == SETTINGS:
            threading.Thread(target=self._settings, daemon=True).start()
        elif e.action == AUTOSTART:
            a = self.c.platform.autostart
            a.set_enabled(not a.is_enabled())
            self._rebuild_needed = True
        elif e.action and e.action.startswith(LANGUAGE_PREFIX):
            self.c.set_language(e.action[len(LANGUAGE_PREFIX) :])
            self._rebuild_needed = True
        elif e.action == QUIT:
            self._stop.set()
            self._poller.stop()
            self._updates.stop()
            self.icon.stop()

    def _settings(self) -> None:
        lang = self.c.language
        answer = windows_dialogs.ask_settings(
            lang, self.c.config.base_url, bool(self.c.platform.secrets.get())
        )
        if answer is None:
            return
        url, key = answer
        try:
            self.c.configure(url, key or None)
        except ValueError as e:
            from ..core.i18n import translate

            msg = "dialog.invalid_url" if "adres" in str(e) or "https" in str(e) else "dialog.invalid_key"
            windows_dialogs.alert(lang, translate(lang, msg))
        self._rebuild_needed = True


def run() -> int:
    if not acquire():
        return 0  # draait al: een tweede tray-icoon heeft geen zin
    TrayApp(Controller(WindowsPlatform())).run()
    return 0


def forget() -> int:
    """Voor de uninstaller: bewaarde sleutel en 'start bij aanmelden' opruimen. Mislukken is niet erg."""
    p = WindowsPlatform()
    for step in (p.secrets.delete, lambda: p.autostart.set_enabled(False)):
        with contextlib.suppress(Exception):
            step()
    return 0
