"""Acties die Mac en Windows delen: menu-klikken afhandelen, resultaten verwerken en de instellingenflow.

Enkel het tonen van dialogen, het afsluiten en het tekenen blijven per platform; die komen binnen via `AppUi`.
GUI-vrij: deze module importeert nooit AppKit, pystray of tkinter.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Protocol

from .api import AuthError, InvalidKeyError, InvalidUrlError, NetworkError
from .controller import Controller
from .defaults import DEFAULT_BASE_URL
from .i18n import translate
from .link import link_host, parse_link
from .menu import AUTOSTART, LANGUAGE_PREFIX, QUIT, REFRESH, SETTINGS, Entry
from .models import Snapshot
from .state import NotConfigured, Toast

log = logging.getLogger(__name__)


class AppUi(Protocol):
    """Wat een platform zelf invult."""

    def open_url(self, url: str) -> None: ...

    def ask_settings(self, lang: str, base_url: str, key_saved: bool) -> tuple[str, str] | None:
        """Toont adres en sleutel (verborgen). Een lege sleutel betekent 'bewaarde sleutel houden'.
        `None` = geannuleerd."""

    def alert(self, message: str) -> None:
        """Toont een (al vertaalde) boodschap."""

    def confirm(self, message: str) -> bool:
        """Toont een (al vertaalde) ja/nee-vraag. `True` = bevestigd. Blokkeert; nooit op de UI-thread."""

    def request_rebuild(self) -> None:
        """Het menu moet bij de volgende tik opnieuw getekend worden."""

    def quit(self) -> None:
        """Stopt de pollers en sluit de app af."""


class Notifier(Protocol):
    def notify(self, title: str, body: str, url: str | None) -> None: ...


class AppActions:
    def __init__(self, controller: Controller, ui: AppUi, first_run_delay: float = 0.0) -> None:
        self.c = controller
        self.ui = ui
        # Niet-blokkerend: een tweede klik op Instellingen terwijl het venster open staat doet niets.
        self._settings_lock = threading.Lock()
        self._first_run_lock = threading.Lock()
        self._first_run_done = False
        self._link_received = (
            threading.Event()
        )  # een koppellink kwam binnen: de eerste start opent niets meer
        # Zo lang wacht de eerste start op een koppellink. Op de Mac komt die bij een koude start als Apple Event
        # pas na de eerste tik binnen; zonder wachten neemt het instellingenvenster de lock en valt de link weg.
        self._first_run_delay = first_run_delay

    def handle(self, entry: Entry) -> None:
        action = entry.action
        if entry.url:
            self.ui.open_url(entry.url)
        elif action == REFRESH:
            self.c.wake.set()
        elif action == SETTINGS:
            # Een dialoog blokkeert; nooit op de UI-thread.
            threading.Thread(target=self.settings, name="settings", daemon=True).start()
        elif action == AUTOSTART:
            autostart = self.c.platform.autostart
            autostart.set_enabled(not autostart.is_enabled())
            self.ui.request_rebuild()
        elif action and action.startswith(LANGUAGE_PREFIX):
            self.c.set_language(action[len(LANGUAGE_PREFIX) :])
            self.ui.request_rebuild()
        elif action == QUIT:
            self.ui.quit()

    def drain(self, results: queue.Queue[list[Toast]], notifier: Notifier) -> bool:
        """Leest de queue leeg en toont de meldingen. Geeft terug of het menu herbouwd moet worden.

        Ook een lege lijst telt: die betekent 'update gevonden, geen meldingen, wel herbouwen'.
        """
        rebuild = False
        while True:
            try:
                toasts = results.get_nowait()
            except queue.Empty:
                return rebuild
            for t in toasts:
                notifier.notify(t.title, t.body, t.url)
            rebuild = True

    def apply_link(self, url: str) -> None:
        """Stelt adres en sleutel in vanuit een `huurklaar-meldingen://koppel`-link, na bevestiging.

        Blokkerend (dialogen): het platform roept dit op een eigen daemon-thread op. Staat er al een
        instellingenvenster of een andere koppeldialoog open, dan doen we niets.

        Een link telt ook als eerste start. Start de app door de link (koude start), dan zou `first_run` anders
        het instellingenvenster openen, dat de lock neemt en de koppelvraag verdringt.
        """
        with self._first_run_lock:
            self._first_run_done = True
            self._link_received.set()
        if not self._settings_lock.acquire(blocking=False):
            return
        try:
            lang = self.c.language
            link = parse_link(url)
            if link is None:
                self.ui.alert(translate(lang, "dialog.invalid_link"))
                return
            api, key = link
            # Zonder bevestiging zou een webpagina die een link opent de app stil naar een vreemde server sturen
            # en de bewaarde sleutel overschrijven. De vraag toont enkel de host, nooit de sleutel of de URL.
            if not self.ui.confirm(translate(lang, "dialog.link_confirm", host=link_host(api))):
                return
            try:
                self.c.configure(api, key)
            except (InvalidUrlError, InvalidKeyError):
                self.ui.alert(translate(lang, "dialog.invalid_link"))
                return
            self._show_connection_result(lang)  # zelfde test en boodschap als na Bewaren (KAN-265)
            self.ui.request_rebuild()
        except Exception as e:  # een kapotte link mag de app niet laten vastlopen; enkel het type loggen
            log.warning("Koppelen mislukt: %s", type(e).__name__)
        finally:
            self._settings_lock.release()

    def first_run(self) -> threading.Thread | None:
        """Opent één keer per proces de instellingen als er nog geen adres of sleutel is.

        Geeft de controle-thread terug (of `None` bij een volgende oproep). De Keychain wordt op die thread gelezen,
        niet op de UI-thread: op de Mac kan dat een systeemvenster tonen.
        """
        with self._first_run_lock:
            if self._first_run_done:
                return None
            self._first_run_done = True
        thread = threading.Thread(target=self._first_run_check, name="first-run", daemon=True)
        thread.start()
        return thread

    def _first_run_check(self) -> None:
        try:
            if self._link_received.wait(self._first_run_delay):
                return  # een koppellink stelt de app in
            # Nog eens ná het lezen van de sleutelopslag: dat kan even duren, en kwam er intussen een koppellink,
            # dan mag een instellingenvenster de koppelvraag niet verdringen.
            missing = not self.c.config.base_url or not self.c.platform.secrets.get()
            if missing and not self._link_received.is_set():
                self.settings()
        except Exception as e:  # de eerste start mag de app nooit laten stoppen; enkel het type loggen
            log.warning("eerste start mislukt: %s", type(e).__name__)

    def settings(self) -> None:
        """De instellingenflow. Draait op een eigen thread, want de dialoog blokkeert."""
        if not self._settings_lock.acquire(blocking=False):
            return  # er staat al een instellingenvenster open
        try:
            lang = self.c.language
            base_url = self.c.config.base_url or DEFAULT_BASE_URL
            answer = self.ui.ask_settings(lang, base_url, bool(self.c.platform.secrets.get()))
            if answer is None:
                return  # geannuleerd: niets wijzigen
            url, key = answer
            try:
                self.c.configure(url, key or None)
            except InvalidUrlError:
                self.ui.alert(translate(lang, "dialog.invalid_url"))
            except InvalidKeyError:
                self.ui.alert(translate(lang, "dialog.invalid_key"))
            else:
                self._show_connection_result(lang)
            self.ui.request_rebuild()
        finally:
            self._settings_lock.release()

    def _show_connection_result(self, lang: str) -> None:
        """Test de nieuwe instellingen en toont precies één boodschap. Mag de flow nooit breken."""
        try:
            result = self.c.test_connection()
        except Exception as e:  # een onverwachte fout in de test mag de instellingenflow niet breken
            log.warning("verbinding testen mislukt: %s", type(e).__name__)  # enkel het type, nooit gegevens
            self.ui.alert(translate(lang, "dialog.unexpected"))
            return
        if isinstance(result, NotConfigured):
            return  # er was niets om te testen: geen melding
        # Kies op type, nooit op de fouttekst. AuthError en NetworkError zijn subklassen van ApiError: eerst die.
        if isinstance(result, Snapshot):
            message = translate(lang, "dialog.connected", detail=_snapshot_detail(result, lang))
        elif isinstance(result, AuthError):
            message = translate(lang, "dialog.key_rejected")
        elif isinstance(result, NetworkError):
            message = translate(lang, "dialog.unreachable")
        else:  # ApiError, ProtocolError of een andere uitkomst: het adres antwoordt niet zoals de API
            message = translate(lang, "dialog.unexpected")
        self.ui.alert(message)


def _snapshot_detail(snapshot: Snapshot, lang: str) -> str:
    """De tellers zoals `status_line`: open en te laat, 'Niets te doen' bij nul, of 'tijdelijk uit'."""
    if not snapshot.enabled:
        return translate(lang, "status.disabled")
    if snapshot.total <= 0:
        return translate(lang, "status.idle")
    detail = translate(lang, "status.tasks", n=snapshot.total)
    if snapshot.overdue:
        detail += ", " + translate(lang, "status.overdue", n=snapshot.overdue)
    return detail
