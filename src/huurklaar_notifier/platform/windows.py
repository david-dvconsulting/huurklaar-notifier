"""Windows: tray-app met `pystray`, meldingen met `win11toast`, sleutel in de Credential Manager via `keyring`.

Dit bestand mag enkel op Windows geïmporteerd worden; de logica die ook zonder Windows getest kan worden zit in
`windows_registry`, `windows_notifier`, `windows_icon` en `windows_menu`.
"""

from __future__ import annotations

import contextlib
import ctypes
import getpass
import logging
import os
import queue
import sys
import threading
import webbrowser
from pathlib import Path

import pystray

from ..core.api import is_openable
from ..core.app_actions import AppActions
from ..core.controller import Controller
from ..core.menu import Entry, MenuCache, build_menu, status_line
from ..core.poller import Poller, UpdatePoller
from ..core.state import Delivery
from . import windows_dialogs
from .keyring_store import KeyringSecretStore
from .windows_icon import badge_for, render_icon
from .windows_link import LinkServer, link_from_argv, pipe_address, send_link
from .windows_menu import build_items, tooltip
from .windows_notifier import WindowsNotifier
from .windows_registry import (
    APP_NAME,
    RunKeyAutostart,
    link_command,
    register_app_id,
    register_url_scheme,
    run_command,
    unregister_url_scheme,
)
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
        try:  # het URL-schema is een gemak: falen mag de app niet stoppen
            exe = sys.executable
            register_url_scheme(
                link_command(getattr(sys, "frozen", False), exe),
                exe if getattr(sys, "frozen", False) else None,
            )
        except Exception as e:
            log.warning("URL-schema registreren mislukt: %s", type(e).__name__)
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
        self._results: queue.Queue[Delivery] = queue.Queue()
        self._rebuild_needed = True
        self._menu_cache = MenuCache()
        self._stop = threading.Event()
        self._poller = Poller(controller, self._results.put)
        # Een gevonden update tekent het menu opnieuw (een lege `Delivery` = geen meldingen, wel herbouwen).
        self._updates = UpdatePoller(controller, lambda: self._results.put(Delivery()))
        self.actions = AppActions(controller, _WindowsUi(self))
        self.icon = pystray.Icon("huurklaar", render_icon(None), APP_NAME, menu=pystray.Menu())
        self._link_server: LinkServer | None = None

    def apply_link(self, url: str) -> None:
        """Past een link toe op een eigen daemon-thread: `apply_link` toont dialogen en blokkeert."""
        threading.Thread(target=self.actions.apply_link, args=(url,), name="link", daemon=True).start()

    def start_link_server(self) -> None:
        try:
            server = LinkServer(pipe_address(_user_name()), self.apply_link)
            server.start()
            self._link_server = server
        except Exception as e:  # zonder server werkt de app gewoon; enkel links van buiten niet
            log.warning("link-server starten mislukt: %s", type(e).__name__)

    def run(self) -> None:
        self._poller.start()
        self._updates.start()
        self.icon.run(setup=self._start_loop)  # blokkeert tot `icon.stop()`

    def _start_loop(self, icon: pystray.Icon) -> None:
        icon.visible = True
        self.actions.first_run()  # start zelf maar één keer een thread; de sleutelopslag wordt daar gelezen
        threading.Thread(target=self._loop, name="tray-loop", daemon=True).start()

    # De lus vervangt de menubalk-timer van de Mac: meldingen tonen en het menu en icoon vernieuwen.
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self.actions.drain(self._results, self.c.platform.notifier):
                    self._rebuild_needed = True
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
            v.state,
            v.language,
            v.language_setting,
            c.platform.autostart.is_enabled(),
            v.update,
            base_url=v.base_url,
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
        self.actions.handle(e)

    def shutdown(self) -> None:
        """Lus en pollers stoppen en het tray-icoon sluiten (de quit-actie)."""
        self._stop.set()
        self._poller.stop()
        self._updates.stop()
        if self._link_server is not None:
            self._link_server.stop()
        self.icon.stop()


class _WindowsUi:
    """De Windows-kant van `AppUi`: Tk-dialoog en MessageBox, de rest delegeert naar de tray-app."""

    def __init__(self, app: TrayApp) -> None:
        self._app = app

    def open_url(self, url: str) -> None:
        open_url(url)

    def ask_settings(self, lang: str, base_url: str, key_saved: bool) -> tuple[str, str] | None:
        return windows_dialogs.ask_settings(lang, base_url, key_saved)

    def alert(self, message: str) -> None:
        windows_dialogs.alert(self._app.c.language, message)

    def confirm(self, message: str) -> bool:
        return windows_dialogs.confirm(self._app.c.language, message)

    def request_rebuild(self) -> None:
        self._app._rebuild_needed = True

    def quit(self) -> None:
        self._app.shutdown()


def _user_name() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return os.environ.get("USERNAME", "")


def run(link: str | None = None) -> int:
    link = link_from_argv([link]) if link else None  # enkel een echte koppellink, geen los argument
    if not acquire():
        # Draait al: een tweede tray-icoon heeft geen zin. Een link geven we door aan de draaiende instantie.
        if link:
            send_link(link, pipe_address(_user_name()))
        return 0
    app = TrayApp(Controller(WindowsPlatform()))
    app.start_link_server()
    if link:
        app.apply_link(link)
    app.run()
    return 0


def forget() -> int:
    """Voor de uninstaller: bewaarde sleutel en 'start bij aanmelden' opruimen. Mislukken is niet erg."""
    p = WindowsPlatform()
    for step in (p.secrets.delete, lambda: p.autostart.set_enabled(False), unregister_url_scheme):
        with contextlib.suppress(Exception):
            step()
    return 0
