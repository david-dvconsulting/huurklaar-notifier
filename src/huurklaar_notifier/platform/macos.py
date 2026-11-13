"""macOS: menubalk-app met `rumps`, meldingen via `UNUserNotificationCenter`, Keychain via `keyring`.

`UNUserNotificationCenter` is gekozen omdat enkel dat een melding onder de eigen appnaam en met een klik naar
onze URL toelaat (prototype in `prototype/`; de vergelijking met `osascript` en `rumps.notification` staat in de README). Dit bestand mag enkel op een Mac geïmporteerd worden.
"""

from __future__ import annotations

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
from ..core.controller import Controller
from ..core.i18n import translate
from ..core.menu import (
    AUTOSTART,
    LANGUAGE_PREFIX,
    QUIT,
    REFRESH,
    SETTINGS,
    Entry,
    build_menu,
    title_for,
)
from ..core.poller import Poller, UpdatePoller
from ..core.state import Toast
from .keyring_store import KeyringSecretStore

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


class MenubarApp(rumps.App):
    def __init__(self, controller: Controller) -> None:
        super().__init__(
            "Huurklaar", title="", icon=str(resource("menubar.png")), template=True, quit_button=None
        )
        self.c = controller
        self._results: queue.Queue[list[Toast]] = queue.Queue()
        self._rebuild_needed = True
        self._poller = Poller(controller, self._results.put)
        # Een gevonden update tekent het menu opnieuw (een lege lijst = geen meldingen, wel herbouwen).
        self._updates = UpdatePoller(controller, lambda: self._results.put([]))
        self._timer = rumps.Timer(self._tick, 1)

    def run(self, **kwargs) -> None:  # type: ignore[override]
        self._poller.start()
        self._updates.start()
        self._timer.start()
        super().run(**kwargs)

    # Alles hieronder draait op de hoofdthread.
    def _tick(self, _) -> None:
        try:
            while True:
                for t in self._results.get_nowait():
                    self.c.platform.notifier.notify(t.title, t.body, t.url)
                self._rebuild_needed = True
        except queue.Empty:
            pass
        if self._rebuild_needed:
            self._rebuild_needed = False
            self._render()

    def _render(self) -> None:
        entries = build_menu(
            self.c.state,
            self.c.language,
            self.c.config.language,
            self.c.platform.autostart.is_enabled(),
            self.c.update,
        )
        self.title = title_for(self.c.state)
        self.menu.clear()
        self.menu.update(self._items(entries))

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
        def run(_):
            if e.url:
                open_url(e.url)
            elif e.action == REFRESH:
                self.c.wake.set()
            elif e.action == SETTINGS:
                import threading

                threading.Thread(target=self._settings, daemon=True).start()
            elif e.action == AUTOSTART:
                a = self.c.platform.autostart
                a.set_enabled(not a.is_enabled())
                self._rebuild_needed = True
            elif e.action and e.action.startswith(LANGUAGE_PREFIX):
                self.c.set_language(e.action[len(LANGUAGE_PREFIX) :])
                self._rebuild_needed = True
            elif e.action == QUIT:
                self._poller.stop()
                self._updates.stop()
                rumps.quit_application()

        return run

    def _settings(self) -> None:
        lang = self.c.language
        url = ask(lang, translate(lang, "dialog.url_prompt"), self.c.config.base_url)
        if url is None:
            return
        key_prompt = translate(lang, "dialog.key_prompt")
        if self.c.platform.secrets.get():
            key_prompt += "\n" + translate(lang, "dialog.key_keep")
        key = ask(lang, key_prompt, "", hidden=True)
        if key is None:
            return
        try:
            self.c.configure(url, key or None)
        except ValueError as e:
            msg = "dialog.invalid_url" if "adres" in str(e) or "https" in str(e) else "dialog.invalid_key"
            alert(lang, translate(lang, msg))
        self._rebuild_needed = True


def run() -> None:
    controller = Controller(MacPlatform())
    MenubarApp(controller).run()
