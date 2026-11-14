"""macOS: menubalk-app met `rumps`, meldingen via `UNUserNotificationCenter`, Keychain via `keyring`.

`UNUserNotificationCenter` is gekozen omdat enkel dat een melding onder de eigen appnaam en met een klik naar
onze URL toelaat (prototype in `prototype/`; de vergelijking met `osascript` en `rumps.notification` staat in de README). Dit bestand mag enkel op een Mac geïmporteerd worden.
"""

from __future__ import annotations

import contextlib
import logging
import queue
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

import rumps
from AppKit import (
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSLocale,
    NSWorkspace,
)
from Foundation import NSURL, NSAttributedString, NSObject
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
from ..core.menu import Entry, MenuCache, build_menu, title_for, title_style
from ..core.poller import Poller, UpdatePoller
from ..core.state import Delivery, Toast
from .keyring_store import KeyringSecretStore
from .macos_ids import request_id
from .macos_links import LinkHandler
from .macos_location import (
    enable_launch_agent,
    is_transient_location,
    program_arguments,
    repair_launch_agent,
)
from .settings_dialog import run_on_main, settings_texts

log = logging.getLogger(__name__)

APP_NAME = "Huurklaar Meldingen"
BUNDLE_ID = "be.huurklaar.meldingen"
FIRST_RUN_LINK_WAIT = 2.0  # seconden, zie MenubarApp.__init__


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
    def __init__(self, center=None) -> None:
        """`center` is enkel voor tests: een nep-center, zonder delegate en zonder toestemmingsvraag."""
        if center is not None:
            self._center = center
            self._delegate = None
            return
        self._center = UNUserNotificationCenter.currentNotificationCenter()
        self._delegate = _Delegate.alloc().init()  # sterke verwijzing: het center houdt enkel een zwakke
        self._center.setDelegate_(self._delegate)
        self._center.requestAuthorizationWithOptions_completionHandler_(
            UNAuthorizationOptionAlert | UNAuthorizationOptionSound, lambda granted, err: None
        )

    def notify(self, toast: Toast) -> None:
        """Toont een melding; dezelfde sleutel vervangt de vorige, en macOS stapelt per groep."""
        try:
            content = UNMutableNotificationContent.alloc().init()
            content.setTitle_(toast.title)
            content.setBody_(toast.body)
            content.setSound_(UNNotificationSound.defaultSound())
            content.setThreadIdentifier_(toast.group)
            content.setUserInfo_({"url": toast.url} if toast.url else {})
            request = UNNotificationRequest.requestWithIdentifier_content_trigger_(
                request_id(toast.key), content, None
            )
            self._center.addNotificationRequest_withCompletionHandler_(request, lambda err: None)
        except Exception as e:  # een fout in een melding mag de app nooit doen vallen
            log.warning("Melding tonen mislukt: %s", type(e).__name__)

    def withdraw(self, keys: list[str]) -> None:
        """Haalt de meldingen van afgewerkte items weg uit het Berichtencentrum."""
        try:
            self._center.removeDeliveredNotificationsWithIdentifiers_([request_id(k) for k in keys])
        except Exception as e:
            log.warning("Meldingen intrekken mislukt: %s", type(e).__name__)


class LaunchAgentAutostart:
    """'Start bij aanmelden' met een LaunchAgent in de map van de gebruiker (geen beheerdersrechten nodig).

    Het pad is injecteerbaar voor tests. `on_transient` wordt aangeroepen als de gebruiker het aanzet vanaf
    een tijdelijk pad (dmg, translocatie): dan schrijven we niets, want na een herstart bestaat dat pad niet.
    """

    default_path = Path.home() / "Library/LaunchAgents" / f"{BUNDLE_ID}.plist"

    def __init__(self, path: Path | None = None, on_transient: Callable[[], None] | None = None) -> None:
        self.path = path or self.default_path
        self._on_transient = on_transient

    def is_enabled(self) -> bool:
        return self.path.exists()

    def _program(self) -> list[str]:
        return program_arguments(bool(getattr(sys, "frozen", False)), sys.executable)

    def set_enabled(self, enabled: bool) -> None:
        if not enabled:
            self.path.unlink(missing_ok=True)
            return
        written = enable_launch_agent(
            self.path, BUNDLE_ID, self._program(), is_transient_location(sys.executable)
        )
        if not written and self._on_transient is not None:
            self._on_transient()

    def repair(self) -> bool:
        """Zelfherstel bij de start; enkel gebundeld, want in ontwikkeling is `sys.executable` een Python."""
        if not getattr(sys, "frozen", False):
            return False
        return repair_launch_agent(
            self.path, BUNDLE_ID, self._program(), is_transient_location(sys.executable)
        )


class MacPlatform:
    def __init__(self) -> None:
        self.secrets = KeyringSecretStore()
        self.language: Callable[[], str] = lambda: "nl"  # `run()` zet de taal van de controller
        self.autostart = LaunchAgentAutostart(on_transient=self.warn_transient)
        self.notifier = MacNotifier()

    def data_dir(self) -> Path:
        return Path.home() / "Library/Application Support" / APP_NAME

    def system_languages(self) -> list[str]:
        return [str(x) for x in NSLocale.preferredLanguages()]

    def open_url(self, url: str) -> None:
        open_url(url)

    def running_from_transient_location(self) -> bool:
        return bool(getattr(sys, "frozen", False)) and is_transient_location(sys.executable)

    def warn_transient(self) -> None:
        """`alert` blokkeert tot de gebruiker klikt: op een daemon-thread, zodat de hoofdthread (rumps-runloop)
        en de menubalk niet vastlopen."""

        def show() -> None:
            try:
                alert(self.language(), translate(self.language(), "location.move_to_applications"))
            except Exception as e:  # een mislukte boodschap mag niets stoppen
                log.warning("boodschap tonen mislukt: %s", type(e).__name__)

        threading.Thread(target=show, name="location-warning", daemon=True).start()


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


def confirm(lang: str, message: str) -> bool:
    """Een ja/nee-vraag via osascript. De teksten gaan als argument mee (geen scriptinjectie).
    `True` = bevestigd; annuleren (of sluiten) geeft een andere exitcode."""
    script = (
        "on run argv\n"
        "display dialog (item 1 of argv) with title (item 2 of argv) "
        "buttons {item 3 of argv, item 4 of argv} default button (item 4 of argv) "
        "cancel button (item 3 of argv)\n"
        "end run"
    )
    args = [
        message,
        translate(lang, "dialog.title"),
        translate(lang, "dialog.cancel"),
        translate(lang, "dialog.link_button"),
    ]
    return subprocess.run(["osascript", "-e", script, *args], capture_output=True).returncode == 0


def _ask_settings_osascript(lang: str, base_url: str, key_saved: bool) -> tuple[str, str] | None:
    """Terugval: twee opeenvolgende osascript-vragen, adres en sleutel (verborgen). `None` = geannuleerd."""
    url = ask(lang, translate(lang, "dialog.url_prompt"), base_url)
    if url is None:
        return None
    key = ask(lang, settings_texts(lang, key_saved).key_label, "", hidden=True)
    if key is None:
        return None
    return url, key


def ask_settings(
    lang: str, base_url: str, key_saved: bool, *, start_timeout: float = 30.0
) -> tuple[str, str] | None:
    """Eén venster met adres en sleutel, op de hoofdthread. Wordt aangeroepen vanaf de instellingenthread.
    Lukt het venster niet, dan vallen we terug op osascript. `None` = geannuleerd."""
    from PyObjCTools import AppHelper

    from .macos_settings import show_settings

    texts = settings_texts(lang, key_saved)
    try:
        return run_on_main(
            lambda: show_settings(texts, base_url), AppHelper.callAfter, start_timeout=start_timeout
        )
    except Exception as e:  # enkel het type loggen: de invoer bevat een sleutel
        log.warning("instellingenvenster mislukt, terugval op osascript: %s", type(e).__name__)
        return _ask_settings_osascript(lang, base_url, key_saved)


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
        self._results: queue.Queue[Delivery] = queue.Queue()
        self._rebuild_needed = True
        self._menu_cache = MenuCache()
        self._poller = Poller(controller, self._results.put)
        # Een gevonden update tekent het menu opnieuw (een lege `Delivery` = geen meldingen, wel herbouwen).
        self._updates = UpdatePoller(controller, lambda: self._results.put(Delivery()))
        self._timer = rumps.Timer(self._tick, 1)
        # Bij een koude start via een koppellink komt het Apple Event pas na de eerste tik: de eerste start
        # wacht er even op, anders verdringt het instellingenvenster de koppelvraag (gezien met een lokale build).
        self.actions = AppActions(controller, _MacUi(self), first_run_delay=FIRST_RUN_LINK_WAIT)

    def run(self, **kwargs) -> None:  # type: ignore[override]
        self._poller.start()
        self._updates.start()
        self._timer.start()
        # Op de hoofdthread en vóór de run-loop: macOS levert het link-event pas na het starten van de app.
        self._link_handler = LinkHandler(lambda url: self.actions.apply_link(url))
        self._link_handler.register()
        super().run(**kwargs)

    # Alles hieronder draait op de hoofdthread.
    def _tick(self, _) -> None:
        self.actions.first_run()  # na de eerste tik niets meer: het start zelf maar één keer een thread
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
            v.state,
            v.language,
            v.language_setting,
            self.c.platform.autostart.is_enabled(),
            v.update,
            base_url=v.base_url,
            paused_until=v.paused_until,
            muted_kinds=v.muted_kinds,
            daily_reminder=v.daily_reminder,
        )
        title = title_for(v.state)
        style = title_style(v.state)
        if not self._menu_cache.changed(entries, (title, style)):  # ook een kleurwissel tekent opnieuw
            return  # niets veranderd: het menu niet opnieuw bouwen
        try:
            self.title = title
            self._style_title(title, style)  # vangt eigen fouten op: kleuren mag het tekenen niet stoppen
            forget_callbacks(self.menu.values())
            self.menu.clear()
            self.menu.update(self._items(entries))
        except Exception:
            self._menu_cache.reset()  # tekenen mislukt: de volgende poging moet opnieuw tekenen
            raise

    def _style_title(self, title: str, style: str) -> None:
        """Kleurt de titel rood bij 'alert'; bij 'normal' zet het de gewone tekst terug.

        `self.title = ...` (rumps) zet enkel de gewone tekst van het statusitem. Een eerder gezette
        attributed title blijft daardoor mogelijk hangen, dus bij 'normal' zetten we expliciet de gewone
        titel opnieuw. rumps-internals (`_nsapp.nsstatusitem`) zijn niet publiek: faalt iets, dan blijft de
        gewone titel staan en loggen we enkel het fouttype.
        """
        try:
            button = self._nsapp.nsstatusitem.button()
            if style == "alert" and title:
                # systemRedColor past zich aan het lichte en donkere thema aan; zonder het lettertype van de
                # menubalk zou de attributed title kleiner ogen dan de gewone titel.
                attributes = {
                    NSForegroundColorAttributeName: NSColor.systemRedColor(),
                    NSFontAttributeName: NSFont.menuBarFontOfSize_(0),
                }
                button.setAttributedTitle_(
                    NSAttributedString.alloc().initWithString_attributes_(title, attributes)
                )
            else:
                button.setTitle_(title)  # vervangt een eventuele attributed title
        except Exception as e:
            log.warning("titel kleuren mislukt: %s", type(e).__name__)

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
    """De Mac-kant van `AppUi`: instellingenvenster via AppKit, alerts via osascript; de rest delegeert naar
    de menubalk-app."""

    def __init__(self, app: MenubarApp) -> None:
        self._app = app

    def open_url(self, url: str) -> None:
        open_url(url)

    def ask_settings(self, lang: str, base_url: str, key_saved: bool) -> tuple[str, str] | None:
        return ask_settings(lang, base_url, key_saved)

    def alert(self, message: str) -> None:
        alert(self._app.c.language, message)

    def confirm(self, message: str) -> bool:
        return confirm(self._app.c.language, message)

    def request_rebuild(self) -> None:
        self._app._rebuild_needed = True

    def quit(self) -> None:
        self._app.shutdown()


def run() -> None:
    platform = MacPlatform()
    controller = Controller(platform)
    platform.language = lambda: controller.language
    platform.autostart.repair()  # een LaunchAgent met een verouderd pad (app verplaatst) terug goed zetten
    if platform.running_from_transient_location():
        platform.warn_transient()  # eenmaal per start
    MenubarApp(controller).run()
