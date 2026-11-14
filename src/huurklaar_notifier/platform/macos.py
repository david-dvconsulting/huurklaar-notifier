"""macOS: menubalk-app met `rumps`, meldingen via `UNUserNotificationCenter`, Keychain via `keyring`.

`UNUserNotificationCenter` is gekozen omdat enkel dat een melding onder de eigen appnaam en met een klik naar
onze URL toelaat (prototype in `prototype/`; de vergelijking met `osascript` en `rumps.notification` staat in de README). Dit bestand mag enkel op een Mac geïmporteerd worden.
"""

from __future__ import annotations

import contextlib
import logging
import plistlib
import queue
import subprocess
import sys
import time
from pathlib import Path

import rumps
from AppKit import NSLocale, NSWorkspace
from Foundation import NSURL, NSObject
from UserNotifications import (
    UNAuthorizationOptionAlert,
    UNAuthorizationOptionSound,
    UNMutableNotificationContent,
    UNNotificationRequest,
    UNNotificationSound,
    UNUserNotificationCenter,
)

from ..core.api import is_openable
from ..core.app_actions import AppActions
from ..core.controller import Controller
from ..core.i18n import translate
from ..core.menu import Entry, MenuCache, build_menu, title_for
from ..core.poller import Poller, UpdatePoller
from ..core.state import Toast
from .keyring_store import KeyringSecretStore

log = logging.getLogger(__name__)

APP_NAME = "Huurklaar Meldingen"
BUNDLE_ID = "be.huurklaar.meldingen"


def resource(name: str) -> Path:
    """Bestanden naast de code: in de gebundelde app onder `_MEIPASS`, anders in de repo."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    return base / "assets" / name


def open_url(url: str) -> None:
    if is_openable(url):
        NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(url))


class _Delegate(NSObject):
    def userNotificationCenter_didReceiveNotificationResponse_withCompletionHandler_(
        self, center, response, handler
    ):
        url = response.notification().request().content().userInfo().get("url")
        if url:
            open_url(str(url))
        handler()

    def userNotificationCenter_willPresentNotification_withCompletionHandler_(
        self, center, notification, handler
    ):
        handler(0b1110)  # banner, lijst en geluid ook als de app vooraan staat


class MacNotifier:
    def __init__(self) -> None:
        self._center = UNUserNotificationCenter.currentNotificationCenter()
        self._delegate = _Delegate.alloc().init()  # sterke verwijzing: het center houdt enkel een zwakke
        self._center.setDelegate_(self._delegate)
        self._center.requestAuthorizationWithOptions_completionHandler_(
            UNAuthorizationOptionAlert | UNAuthorizationOptionSound, lambda granted, err: None
        )

    def notify(self, title: str, body: str, url: str | None) -> None:
        content = UNMutableNotificationContent.alloc().init()
        content.setTitle_(title)
        content.setBody_(body)
        content.setSound_(UNNotificationSound.defaultSound())
        content.setUserInfo_({"url": url} if url else {})
        request = UNNotificationRequest.requestWithIdentifier_content_trigger_(
            f"hk-{time.time_ns()}", content, None
        )
        self._center.addNotificationRequest_withCompletionHandler_(request, lambda err: None)


class LaunchAgentAutostart:
    """'Start bij aanmelden' met een LaunchAgent in de map van de gebruiker (geen beheerdersrechten nodig)."""

    path = Path.home() / "Library/LaunchAgents" / f"{BUNDLE_ID}.plist"

    def is_enabled(self) -> bool:
        return self.path.exists()

    def set_enabled(self, enabled: bool) -> None:
        if not enabled:
            self.path.unlink(missing_ok=True)
            return
        # Gebundeld: de uitvoerbare file in de .app; in ontwikkeling: de module met de huidige Python.
        program = (
            [sys.executable]
            if getattr(sys, "frozen", False)
            else [sys.executable, "-m", "huurklaar_notifier"]
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(
            plistlib.dumps({"Label": BUNDLE_ID, "ProgramArguments": program, "RunAtLoad": True})
        )


class MacPlatform:
    def __init__(self) -> None:
        self.secrets = KeyringSecretStore()
        self.autostart = LaunchAgentAutostart()
        self.notifier = MacNotifier()

    def data_dir(self) -> Path:
        return Path.home() / "Library/Application Support" / APP_NAME

    def system_languages(self) -> list[str]:
        return [str(x) for x in NSLocale.preferredLanguages()]

    def open_url(self, url: str) -> None:
        open_url(url)


_DIALOG = """on run argv
  set r to display dialog (item 1 of argv) default answer (item 2 of argv) with title (item 3 of argv) ¬
    buttons {item 4 of argv, item 5 of argv} default button (item 5 of argv) cancel button (item 4 of argv) ¬
    hidden answer (item 6 of argv is "hidden")
  return text returned of r
end run"""


def ask(lang: str, prompt: str, default: str, hidden: bool = False) -> str | None:
    """Een tekstvraag via osascript. De tekst gaat als argument mee (geen scriptinjectie) en een sleutel
    komt enkel terug via stdout, nooit op een opdrachtregel. `None` = geannuleerd."""
    args = [
        prompt,
        default,
        translate(lang, "dialog.title"),
        translate(lang, "dialog.cancel"),
        translate(lang, "dialog.save"),
        "hidden" if hidden else "",
    ]
    r = subprocess.run(["osascript", "-e", _DIALOG, *args], capture_output=True, text=True)
    return r.stdout.rstrip("\n") if r.returncode == 0 else None


def alert(lang: str, message: str) -> None:
    subprocess.run(
        [
            "osascript",
            "-e",
            "on run argv\ndisplay alert (item 1 of argv) message (item 2 of argv)\nend run",
            translate(lang, "dialog.title"),
            message,
        ],
        capture_output=True,
    )


def ask_settings(lang: str, base_url: str, key_saved: bool) -> tuple[str, str] | None:
    """Twee opeenvolgende vragen: adres en sleutel (verborgen). `None` = geannuleerd."""
    url = ask(lang, translate(lang, "dialog.url_prompt"), base_url)
    if url is None:
        return None
    key_prompt = translate(lang, "dialog.key_prompt")
    if key_saved:
        key_prompt += "\n" + translate(lang, "dialog.key_keep")
    key = ask(lang, key_prompt, "", hidden=True)
    if key is None:
        return None
    return url, key


def forget_callbacks(items, registry=None) -> None:
    """Haalt de items (en recursief hun submenu's) uit het register van rumps.

    `MenuItem.set_callback` zet elk item met zijn callback in `NSApp._ns_to_py_and_callback`, een dict op
    klasseniveau. `Menu.clear()` ruimt die entries niet op: zonder deze stap blijven na elke herbouw alle
    oude items en closures in het geheugen staan (rumps 0.4.0).
    """
    if registry is None:
        registry = rumps.rumps.NSApp._ns_to_py_and_callback
    for item in list(items):
        children = getattr(item, "values", None)  # een MenuItem is zelf een dict met zijn submenu-items
        if children is not None:
            forget_callbacks(children(), registry)
        with contextlib.suppress(KeyError, AttributeError):  # scheidingslijnen staan niet in het register
            del registry[item._menuitem]


class MenubarApp(rumps.App):
    def __init__(self, controller: Controller) -> None:
        super().__init__(
            "Huurklaar", title="", icon=str(resource("menubar.png")), template=True, quit_button=None
        )
        self.c = controller
        self._results: queue.Queue[list[Toast]] = queue.Queue()
        self._rebuild_needed = True
        self._menu_cache = MenuCache()
        self._poller = Poller(controller, self._results.put)
        # Een gevonden update tekent het menu opnieuw (een lege lijst = geen meldingen, wel herbouwen).
        self._updates = UpdatePoller(controller, lambda: self._results.put([]))
        self._timer = rumps.Timer(self._tick, 1)
        self.actions = AppActions(controller, _MacUi(self))

    def run(self, **kwargs) -> None:  # type: ignore[override]
        self._poller.start()
        self._updates.start()
        self._timer.start()
        super().run(**kwargs)

    # Alles hieronder draait op de hoofdthread.
    def _tick(self, _) -> None:
        if self.actions.drain(self._results, self.c.platform.notifier):
            self._rebuild_needed = True
        if self._rebuild_needed:
            try:
                self._render()
            except Exception as e:  # volgende tik probeert het opnieuw; enkel het type loggen
                log.warning("menu verversen mislukt: %s", type(e).__name__)
            else:
                self._rebuild_needed = False  # pas na een geslaagde render

    def _render(self) -> None:
        v = self.c.view()  # één korte lock-sectie; daarna werken we op de kopie
        entries = build_menu(
            v.state, v.language, v.language_setting, self.c.platform.autostart.is_enabled(), v.update
        )
        title = title_for(v.state)
        if not self._menu_cache.changed(entries, title):
            return  # niets veranderd: het menu niet opnieuw bouwen
        try:
            self.title = title
            forget_callbacks(self.menu.values())
            self.menu.clear()
            self.menu.update(self._items(entries))
        except Exception:
            self._menu_cache.reset()  # tekenen mislukt: de volgende poging moet opnieuw tekenen
            raise

    def _items(self, entries: list[Entry]) -> list:
        out: list = []
        for e in entries:
            if e.separator:
                out.append(None)  # rumps: None = scheidingslijn
                continue
            item = rumps.MenuItem(e.label)
            if e.checked:
                item.state = 1
            if e.children:
                for child in self._items(list(e.children)):
                    item.add(child)
            elif e.enabled and (e.url or e.action):
                item.set_callback(self._callback(e))
            out.append(item)
        return out

    def _callback(self, e: Entry):
        return lambda _: self.actions.handle(e)

    def shutdown(self) -> None:
        """Pollers stoppen en de app afsluiten (de quit-actie)."""
        self._poller.stop()
        self._updates.stop()
        rumps.quit_application()


class _MacUi:
    """De Mac-kant van `AppUi`: dialogen via osascript, de rest delegeert naar de menubalk-app."""

    def __init__(self, app: MenubarApp) -> None:
        self._app = app

    def open_url(self, url: str) -> None:
        open_url(url)

    def ask_settings(self, lang: str, base_url: str, key_saved: bool) -> tuple[str, str] | None:
        return ask_settings(lang, base_url, key_saved)

    def alert(self, message: str) -> None:
        alert(self._app.c.language, message)

    def request_rebuild(self) -> None:
        self._app._rebuild_needed = True

    def quit(self) -> None:
        self._app.shutdown()


def run() -> None:
    controller = Controller(MacPlatform())
    MenubarApp(controller).run()
