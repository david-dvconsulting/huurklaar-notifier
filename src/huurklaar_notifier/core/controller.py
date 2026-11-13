"""Verbindt instellingen, sleutelopslag, client en toestand. GUI-vrij: een platform roept enkel deze klasse aan."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from ..platform.base import Platform
from .api import ApiClient, validate_base_url, validate_key
from .config import Config, ConfigStore
from .i18n import resolve_language
from .state import State, Toast


@dataclass(frozen=True, slots=True)
class PollResult:
    toasts: list[Toast]


class Controller:
    def __init__(
        self,
        platform: Platform,
        client_factory: Callable[[str, str], ApiClient] = ApiClient,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.platform = platform
        self.store = ConfigStore(platform.data_dir())
        self.config: Config = self.store.load()
        self.state = State()
        self._client_factory = client_factory
        self._clock = clock
        self._lock = threading.Lock()  # poll-thread en UI-thread raken dezelfde toestand
        self.wake = threading.Event()  # 'nu vernieuwen' of nieuwe instellingen

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
