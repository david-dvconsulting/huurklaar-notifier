"""Statuslogica: wat de app nu toont, wanneer ze opnieuw vraagt en welke meldingen nieuw zijn."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit

from .api import ApiClient, ApiError, AuthError, NetworkError, is_openable
from .config import Config
from .i18n import translate
from .models import Item, ProtocolError, Snapshot


class Status(Enum):
    NOT_CONFIGURED = "not_configured"
    OFFLINE = "offline"
    AUTH_FAILED = "auth_failed"
    DISABLED = "disabled"
    IDLE = "idle"
    ATTENTION = "attention"  # er zijn open taken of acties


@dataclass(frozen=True, slots=True)
class Toast:
    title: str
    body: str
    url: str | None


BACKOFF_START = 30.0
BACKOFF_MAX = 900.0
MIN_POLL = 60.0  # ondergrens, ook als de server minder vraagt: de API-throttle is gedeeld
MAX_TOASTS = 3  # meer nieuwe meldingen in één poll worden één samenvatting
MAX_SEEN = 500


class NotConfigured(Exception):
    """Resultaat van `State.fetch` zonder client: er is niets om te bevragen."""


FetchResult = Snapshot | Exception


def status_for(snapshot: Snapshot) -> Status:
    if not snapshot.enabled:
        return Status.DISABLED
    return Status.ATTENTION if snapshot.total > 0 else Status.IDLE


class State:
    """Houdt de laatste toestand bij. Geen GUI, geen netwerk (de client wordt aangereikt)."""

    def __init__(self, rng: Callable[[float, float], float] = random.uniform) -> None:
        self.status = Status.NOT_CONFIGURED
        self.snapshot: Snapshot | None = None  # laatste geslaagde antwoord, ook getoond bij 'geen verbinding'
        self.failures = 0
        self.updated_at: str | None = None  # HH:MM van het laatste geslaagde antwoord
        self._rng = rng

    @staticmethod
    def fetch(client: ApiClient | None) -> FetchResult:
        """Doet enkel de netwerkaanvraag en wijzigt geen toestand, dus veilig buiten de lock.

        Geeft het antwoord of de verwachte fout terug (niet geworpen). Zonder client geeft ze
        `NotConfigured()` terug. Onverwachte fouten worden wel geworpen.
        """
        if client is None:
            return NotConfigured()
        try:
            return client.fetch()
        except (AuthError, NetworkError, ProtocolError, ApiError) as e:
            return e

    def apply(self, result: FetchResult, config: Config, lang: str, now_hhmm: str) -> list[Toast]:
        """Verwerkt het resultaat van `fetch`: werkt de toestand bij en geeft de meldingen die nu getoond moeten worden."""
        if isinstance(result, NotConfigured):
            self.status, self.snapshot = Status.NOT_CONFIGURED, None
            return []
        if isinstance(result, AuthError):
            self.status, self.snapshot, self.failures = Status.AUTH_FAILED, None, 0
            return []
        if isinstance(result, Exception):  # NetworkError, ProtocolError, ApiError
            self.status, self.failures = Status.OFFLINE, self.failures + 1
            return []
        self.failures = 0
        self.snapshot, self.status, self.updated_at = result, status_for(result), now_hhmm
        return self._new_toasts(result, config, lang)

    def poll(self, client: ApiClient | None, config: Config, lang: str, now_hhmm: str) -> list[Toast]:
        """Doet één poll: `fetch` en daarna `apply`."""
        return self.apply(self.fetch(client), config, lang, now_hhmm)

    def next_delay(self) -> float | None:
        """Seconden tot de volgende poll; `None` = wachten op nieuwe instellingen (geen nutteloos bellen)."""
        if self.status in (Status.NOT_CONFIGURED, Status.AUTH_FAILED):
            return None
        if self.status is Status.OFFLINE:
            base = min(BACKOFF_START * 2 ** max(self.failures - 1, 0), BACKOFF_MAX)
            return base * self._rng(0.8, 1.2)
        assert self.snapshot is not None
        # De server bepaalt het interval; wij voegen willekeur toe zodat gebruikers niet gelijk lopen.
        return max(self.snapshot.poll_after_seconds, MIN_POLL) * self._rng(0.8, 1.2)

    def _new_toasts(self, snap: Snapshot, config: Config, lang: str) -> list[Toast]:
        """Geeft de meldingen die nu nieuw zijn en werkt `config.seen` bij.

        Niet afgekapt: alleen ids die nu nog in de lijst staan blijven bewaard, dus een item dat
        verdwijnt en terugkomt wordt opnieuw gemeld. Afgekapt (meer dan de lijst toont): ids die
        even buiten de lijst vallen blijven bewaard, zodat een terugkerend item geen tweede melding krijgt.
        """
        seen = set(config.seen)
        fresh = [i for i in snap.items if i.action_required and i.id not in seen]
        fresh_ids = {i.id for i in fresh}
        current = [i.id for i in snap.items if i.id in seen or i.id in fresh_ids]
        if snap.truncated:
            in_list = {i.id for i in snap.items}
            # Oude ids die niet in de lijst staan blijven achter de huidige ids, zonder dubbelen.
            kept = [s for s in config.seen if s not in in_list]
            config.seen = list(dict.fromkeys(current + kept))[:MAX_SEEN]
        else:
            config.seen = current[:MAX_SEEN]
        if not snap.enabled or not fresh:
            return []
        if len(fresh) > MAX_TOASTS:
            return [
                Toast(
                    translate(lang, "toast.summary", n=len(fresh)),
                    translate(lang, "toast.summary_body"),
                    app_url(fresh),
                )
            ]
        return [item_toast(i, lang) for i in fresh]


def app_url(items: list[Item]) -> str | None:
    """Voor een samenvatting: het hoofdadres van de app, afgeleid uit de links van de items."""
    for i in items:
        parts = urlsplit(i.href)
        if is_openable(i.href):
            return f"{parts.scheme}://{parts.netloc}/"
    return None


def item_toast(item: Item, lang: str) -> Toast:
    head = translate(lang, "toast.overdue" if item.overdue else "toast.action")
    where = " · ".join(p for p in (item.property_label, item.account_name) if p)
    return Toast(
        item.title,
        f"{head}" + (f" · {where}" if where else ""),
        item.href if is_openable(item.href) else None,
    )
