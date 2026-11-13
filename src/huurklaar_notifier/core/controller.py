"""Verbindt instellingen, sleutelopslag, client en toestand. GUI-vrij: een platform roept enkel deze klasse aan."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from .. import __version__
from ..platform.base import Platform
from .api import ApiClient, validate_base_url, validate_key
from .config import Config, ConfigStore
from .i18n import resolve_language
from .state import State, Toast
from .updates import DAY, Release, UpdateCheckError, fetch_latest_release, newer_than_current, release_url


@dataclass(frozen=True, slots=True)
class PollResult:
    toasts: list[Toast]


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

    # -- taal --------------------------------------------------------------
    @property
    def language(self) -> str:
        return resolve_language(self.config.language, self.platform.system_languages())

    def set_language(self, setting: str) -> None:
        self.config.language = setting
        self.store.save(self.config)

    # -- instellingen --------------------------------------------------------
    def configure(self, base_url: str, key: str | None) -> None:
        """Bewaart adres en (optioneel nieuwe) sleutel. Werpt ValueError bij ongeldige invoer."""
        url = validate_base_url(base_url)
        new_key = validate_key(key) if key else None
        if new_key is None and self.platform.secrets.get() is None:
            raise ValueError("geen geldige meldingssleutel")
        with self._lock:
            if new_key is not None:
                self.platform.secrets.set(new_key)
            if new_key is not None or url != self.config.base_url:
                self.config.seen = []  # ander account of adres: alles is weer nieuw
            self.config.base_url = url
            self.store.save(self.config)
        self.wake.set()

    # -- polling ---------------------------------------------------------------
    def poll(self) -> list[Toast]:
        with self._lock:
            client = self._client()
            hhmm = time.strftime("%H:%M", time.localtime(self._clock()))
            toasts = self.state.poll(client, self.config, self.language, hhmm)
            self.store.save(self.config)  # onthoudt welke meldingen al getoond zijn
            return toasts

    def next_delay(self) -> float | None:
        with self._lock:
            return self.state.next_delay()

    def _client(self) -> ApiClient | None:
        if not self.config.base_url:
            return None
        try:
            key = self.platform.secrets.get()
            return self._client_factory(self.config.base_url, key) if key else None
        except Exception:  # Keychain geweigerd of ongeldig adres: behandel als 'niet aangemeld'
            return None

    # -- updatecheck (KAN-121) -----------------------------------------------------
    @property
    def update(self) -> Release | None:
        """De nieuwere versie die we kennen, of `None`. Leest enkel de bewaarde waarde: nooit netwerk."""
        with self._lock:
            version = self.config.update_version
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
