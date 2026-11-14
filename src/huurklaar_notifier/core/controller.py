"""Verbindt instellingen, sleutelopslag, client en toestand. GUI-vrij: een platform roept enkel deze klasse aan."""

from __future__ import annotations

import copy
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from .. import __version__
from ..platform.base import Platform
from .api import ApiClient, AuthError, InvalidKeyError, validate_base_url, validate_key
from .config import MAX_MUTED_KINDS, Config, ConfigStore
from .i18n import resolve_language
from .state import Delivery, FetchResult, State, Toast
from .updates import DAY, Release, UpdateCheckError, fetch_latest_release, newer_than_current, release_url


@dataclass(frozen=True, slots=True)
class PollResult:
    toasts: list[Toast]


@dataclass(frozen=True, slots=True)
class View:
    """Een consistente kopie van wat de UI nodig heeft om het menu te tekenen."""

    state: State
    language: str
    language_setting: str
    update: Release | None
    base_url: str  # het bewaarde API-adres; het menu kiest daarop de juiste app-omgeving
    paused_until: float = 0.0  # enkel gezet als de pauze nu nog loopt
    muted_kinds: tuple[str, ...] = ()
    daily_reminder: bool = True


REMINDER_HOUR = 9  # lokale tijd van de dagelijkse herinnering (KAN-285), elke dag


def tomorrow_morning(now: float, hour: int = 8) -> float:
    """08:00 lokale tijd op de dag na `now`. `mktime` met `tm_isdst=-1` houdt rekening met het zomeruur."""
    t = time.localtime(now)
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday + 1, hour, 0, 0, 0, 0, -1))


def next_local_time(now: float, hour: int) -> float:
    """Het eerstvolgende `hour`:00 lokale tijd strikt na `now`: vandaag als dat nog komt, anders morgen."""
    t = time.localtime(now)
    today = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, hour, 0, 0, 0, 0, -1))
    return today if today > now else tomorrow_morning(now, hour)


class Controller:
    def __init__(
        self,
        platform: Platform,
        client_factory: Callable[[str, str], ApiClient] = ApiClient,
        clock: Callable[[], float] = time.time,
        update_fetch: Callable[[], Release | None] = fetch_latest_release,
        current_version: str = __version__,
    ) -> None:
        self.platform = platform
        self.store = ConfigStore(platform.data_dir())
        self.config: Config = self.store.load()
        self.state = State()
        self._client_factory = client_factory
        self._clock = clock
        self._lock = threading.Lock()  # poll-thread en UI-thread raken dezelfde toestand
        self.wake = threading.Event()  # 'nu vernieuwen' of nieuwe instellingen
        self._update_fetch = update_fetch
        self._current_version = current_version
        # Telt hoe vaak adres of sleutel veranderd is; zie `poll`.
        self._generation = 0
        # De laatst gemaakte client, met het adres en de sleutel waarmee ze gemaakt is. Zolang het adres gelijk is,
        # lezen we de sleutel niet opnieuw uit de Keychain. Alles eromheen gebeurt onder `_lock`.
        self._client_cache: tuple[str, str, ApiClient] | None = None

    # -- taal --------------------------------------------------------------
    @property
    def language(self) -> str:
        return resolve_language(self.config.language, self.platform.system_languages())

    def set_language(self, setting: str) -> None:
        with self._lock:  # de poll-thread schrijft onder dezelfde lock
            self.config.language = setting
            self.store.save(self.config)

    # -- pauzeren (KAN-283) ----------------------------------------------------
    def _active_pause(self) -> float:
        """Het einde van de lopende pauze, of 0.0. Aanroepen onder `_lock`."""
        until = self.config.paused_until
        return until if self._clock() < until else 0.0

    def set_pause(self, until: float) -> None:
        """Pauzeert de meldingen tot `until` (epochseconden); 0.0 heft de pauze op."""
        with self._lock:
            self.config.paused_until = until
            self.store.save(self.config)
        # De pollus slaapt misschien nog op een lang interval: laat ze de wachttijd opnieuw bepalen.
        self.wake.set()

    def pause_for_hour(self) -> None:
        self.set_pause(self._clock() + 3600)

    def pause_until_tomorrow(self) -> None:
        """Pauzeert tot 08:00 lokale tijd op de volgende kalenderdag."""
        self.set_pause(tomorrow_morning(self._clock()))

    def resume(self) -> None:
        """Heft de pauze meteen op en wekt de poller, zodat een eventuele samenvatting snel komt."""
        self.set_pause(0.0)
        self.wake.set()

    # -- meldingen per soort (KAN-284) -------------------------------------------
    def toggle_kind(self, kind: str) -> None:
        """Zet de meldingen voor een soort aan of uit. Een lege soort doet niets."""
        if not kind:
            return
        with self._lock:
            muted = self.config.muted_kinds
            if kind in muted:
                muted.remove(kind)
            elif len(muted) < MAX_MUTED_KINDS:
                muted.append(kind)
            else:
                return  # vol: niets gewijzigd, dus ook niets wegschrijven
            self.store.save(self.config)

    # -- dagelijkse herinnering (KAN-285) ------------------------------------------
    def toggle_reminder(self) -> None:
        """Zet de dagelijkse herinnering aan of uit."""
        with self._lock:
            self.config.daily_reminder = not self.config.daily_reminder
            self.store.save(self.config)
        self.wake.set()  # de pollus moet de wachttijd (met of zonder 09:00-grens) opnieuw bepalen

    # -- instellingen --------------------------------------------------------
    def configure(self, base_url: str, key: str | None) -> None:
        """Bewaart adres en (optioneel nieuwe) sleutel. Werpt InvalidUrlError of InvalidKeyError (beide ValueError) bij ongeldige invoer."""
        url = validate_base_url(base_url)
        new_key = validate_key(key) if key else None
        if new_key is None and self.platform.secrets.get() is None:
            raise InvalidKeyError("geen geldige meldingssleutel")
        with self._lock:
            if new_key is not None:
                self.platform.secrets.set(new_key)
            if new_key is not None or url != self.config.base_url:
                self.config.seen = []  # ander account of adres: alles is weer nieuw
                self.state.missed = 0  # de gemiste meldingen horen bij het vorige account
            self.config.base_url = url
            self._generation += 1  # een lopende poll met de oude client moet haar resultaat weggooien
            self._client_cache = None  # de volgende poll maakt een client met de nieuwe instellingen
            self.store.save(self.config)
        self.wake.set()

    # -- polling ---------------------------------------------------------------
    def poll(self) -> Delivery:
        with self._lock:
            client = self._client()
            hhmm = time.strftime("%H:%M", time.localtime(self._clock()))
            generation = self._generation
        # De netwerkaanvraag duurt tot 10 s: nooit met de lock, anders hangt de UI-thread erop.
        result = State.fetch(client)
        with self._lock:
            # Veranderde `configure()` intussen adres of sleutel, dan hoort dit antwoord bij het oude
            # account. Verwerken zou `seen` van dat account terugzetten (configure wist het net) en
            # de status van het oude account tonen. We gooien het weg; `configure` wekt de poller al.
            if generation != self._generation:
                return Delivery()
            if isinstance(result, AuthError):
                # Een geweigerde sleutel: de volgende poll leest de sleutel opnieuw uit de Keychain.
                self._client_cache = None
            before = list(self.config.seen)
            before_reminder = self.config.last_reminder
            now = self._clock()
            paused = now < self.config.paused_until
            lt = time.localtime(now)
            # De datum van vandaag, enkel als het uur van de herinnering bereikt is (anders `None`).
            reminder_day = time.strftime("%Y-%m-%d", lt) if lt.tm_hour >= REMINDER_HOUR else None
            delivery = self.state.apply(result, self.config, self.language, hhmm, paused, reminder_day)
            # `seen` verandert enkel als er een melding bij komt of verdwijnt, `last_reminder` enkel eens per dag.
            # Alleen dan schrijven we weg, zodat een gewone poll niets naar de schijf stuurt. Zonder wegschrijven
            # van `last_reminder` komt er na een herstart een tweede herinnering op dezelfde dag.
            if self.config.seen != before or self.config.last_reminder != before_reminder:
                self.store.save(self.config)
            return delivery

    def view(self) -> View:
        """Alles wat de UI nodig heeft, in één korte lock-sectie, zodat het menu een consistente kopie leest."""
        with self._lock:
            return View(
                copy.copy(self.state),
                self.language,
                self.config.language,
                self._newer_release(self.config.update_version),
                self.config.base_url,
                self._active_pause(),
                tuple(self.config.muted_kinds),
                self.config.daily_reminder,
            )

    def next_delay(self) -> float | None:
        with self._lock:
            delay = self.state.next_delay()
            if delay is None:
                return None  # niet ingesteld of sleutel geweigerd: een pauze verandert daar niets aan
            now = self._clock()
            if now < self.config.paused_until:
                # Het serverinterval kan uren duren (tot 6 u). Poll daarom vlak na het einde van de pauze, zodat de
                # samenvatting op tijd komt en de statusregel verdwijnt. De marge van 1 s voorkomt dat
                # `Event.wait` net te vroeg wakker wordt: die poll zou nog als gepauzeerd tellen.
                delay = min(delay, self.config.paused_until - now + 1.0)
            if self.config.daily_reminder:
                # Ook het serverinterval (tot 6 u) mag de herinnering niet uren na 09:00 laten komen. Zelfde marge
                # van 1 s als hierboven, zodat de poll na het wakker worden het uur zeker bereikt heeft.
                delay = min(delay, next_local_time(now, REMINDER_HOUR) - now + 1.0)
            return delay

    def _client(self) -> ApiClient | None:
        """Geeft de bewaarde client als het adres nog klopt, anders maakt er een met de sleutel uit de Keychain."""
        if not self.config.base_url:
            return None
        cached = self._client_cache
        if cached is not None and cached[0] == self.config.base_url:
            return cached[2]
        try:
            key = self.platform.secrets.get()
            if not key:
                return None
            client = self._client_factory(self.config.base_url, key)
        except Exception:  # Keychain geweigerd of ongeldig adres: behandel als 'niet aangemeld'
            return None  # niets cachen: de volgende poll probeert het opnieuw
        self._client_cache = (self.config.base_url, key, client)
        return client

    def test_connection(self) -> FetchResult:
        """Vraagt één keer op met de bewaarde instellingen en geeft het resultaat terug, zonder iets te wijzigen.

        Geen `apply`, geen `seen`, geen config en geen `_generation`: de poller blijft de enige die de toestand
        bijwerkt. Zonder client (niet ingesteld) is het resultaat `NotConfigured()`.
        """
        with self._lock:
            client = self._client()
        # Net als in `poll`: de aanvraag duurt tot 10 s en gebeurt dus nooit met de lock.
        return State.fetch(client)

    # -- updatecheck (KAN-121) -----------------------------------------------------
    @property
    def update(self) -> Release | None:
        """De nieuwere versie die we kennen, of `None`. Leest enkel de bewaarde waarde: nooit netwerk."""
        with self._lock:
            version = self.config.update_version
        return self._newer_release(version)

    def _newer_release(self, version: str) -> Release | None:
        if not version:
            return None
        return newer_than_current(Release(version, release_url(version)), self._current_version)

    def update_due_in(self) -> float:
        """Seconden tot de volgende updatecheck (0 of minder = nu)."""
        with self._lock:
            return self.config.update_next_check - self._clock()

    def check_for_update(self) -> bool:
        """Doet de updatecheck als die aan de beurt is. Geeft waar als de gevonden versie veranderd is.

        Mislukken is stil: bij elke fout onthouden we enkel wanneer we opnieuw proberen.
        """
        if self.update_due_in() > 0:
            return False
        retry_after = DAY
        found: str | None = None
        try:
            release = newer_than_current(self._update_fetch(), self._current_version)
            found = release.version if release else ""
        except UpdateCheckError as e:
            retry_after = e.retry_after
        except Exception:  # een updatecheck mag de app nooit hinderen
            retry_after = 3600.0
        with self._lock:
            before = self.config.update_version
            if found is not None:
                self.config.update_version = found
            self.config.update_next_check = self._clock() + retry_after
            self.store.save(self.config)
            return self.config.update_version != before
