"""Statuslogica: wat de app nu toont, wanneer ze opnieuw vraagt en welke meldingen nieuw zijn."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlsplit

from .api import ApiClient, ApiError, AuthError, NetworkError, is_openable
from .config import Config
from .i18n import NL, translate
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
    key: str  # id van het item waarbij de melding hoort; "summary" voor een samenvatting
    group: str  # `kind` van het item; "summary" voor een samenvatting


@dataclass(frozen=True, slots=True)
class Delivery:
    """Wat een poll aan het platform meegeeft: nieuwe meldingen en de sleutels van opgeloste meldingen."""

    toasts: list[Toast] = field(default_factory=list)
    withdraw: list[str] = field(default_factory=list)


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
        # Nieuwe meldingen die tijdens een pauze gemist zijn. Enkel in het geheugen: na een herstart is `seen`
        # al bijgewerkt en weten we niet meer wat er gemist is.
        self.missed = 0
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

    def apply(
        self, result: FetchResult, config: Config, lang: str, now_hhmm: str, paused: bool = False
    ) -> Delivery:
        """Verwerkt het resultaat van `fetch`: werkt de toestand bij en geeft de meldingen die nu getoond of ingetrokken moeten worden.

        Tijdens een pauze (`paused`, bepaald door de controller met zijn klok) komen er geen meldingen: `seen`
        wordt wel bijgewerkt en `missed` telt wat er gemist is. De eerste poll erna meldt dat in één samenvatting.
        Intrekken van afgewerkte meldingen gaat tijdens een pauze gewoon door.
        """
        if isinstance(result, NotConfigured):
            self.status, self.snapshot = Status.NOT_CONFIGURED, None
            return Delivery()
        if isinstance(result, AuthError):
            self.status, self.snapshot, self.failures = Status.AUTH_FAILED, None, 0
            return Delivery()
        if isinstance(result, Exception):  # NetworkError, ProtocolError, ApiError
            self.status, self.failures = Status.OFFLINE, self.failures + 1
            return Delivery()
        self.failures = 0
        self.snapshot, self.status, self.updated_at = result, status_for(result), now_hhmm
        before = list(config.seen)
        toasts = self._new_toasts(result, config, lang, paused)
        # Een id die verdwenen is uit `seen` is afgewerkt. Bij een afgekapte lijst weten we dat niet zeker:
        # het item kan gewoon buiten de lijst vallen.
        after = set(config.seen)
        withdraw = [] if result.truncated else list(dict.fromkeys(s for s in before if s not in after))
        return Delivery(toasts, withdraw)

    def poll(
        self, client: ApiClient | None, config: Config, lang: str, now_hhmm: str, paused: bool = False
    ) -> Delivery:
        """Doet één poll: `fetch` en daarna `apply`."""
        return self.apply(self.fetch(client), config, lang, now_hhmm, paused)

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

    def _new_toasts(self, snap: Snapshot, config: Config, lang: str, paused: bool = False) -> list[Toast]:
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
        if not snap.enabled:
            return []
        # Items van een uitgezette soort tellen niet mee voor melding, samenvatting en `missed`. Ze stonden
        # hierboven al in `seen`, dus aanzetten geeft later geen stortvloed van oude items.
        fresh = [i for i in fresh if i.kind not in config.muted_kinds]
        if paused:
            self.missed += len(fresh)
            return []
        toasts: list[Toast] = []
        if self.missed > 0:  # de pauze is voorbij: eenmalig melden wat er intussen binnenkwam
            toasts.append(
                Toast(
                    # Geen meervoudsregels in de catalogus: één gemiste melding krijgt een eigen tekst.
                    translate(
                        lang,
                        "toast.paused_summary_one" if self.missed == 1 else "toast.paused_summary",
                        n=self.missed,
                    ),
                    translate(lang, "toast.summary_body"),
                    app_url(list(snap.items)),
                    "paused",
                    "summary",
                )
            )
            self.missed = 0
        if len(fresh) > MAX_TOASTS:
            toasts.append(
                Toast(
                    translate(lang, "toast.summary", n=len(fresh)),
                    summary_body(fresh, lang),
                    app_url(fresh),
                    "summary",
                    "summary",
                )
            )
        else:
            toasts += [item_toast(i, lang) for i in fresh]
        return toasts


def app_url(items: list[Item]) -> str | None:
    """Voor een samenvatting: het hoofdadres van de app, afgeleid uit de links van de items."""
    for i in items:
        parts = urlsplit(i.href)
        if is_openable(i.href):
            return f"{parts.scheme}://{parts.netloc}/"
    return None


def summary_body(items: list[Item], lang: str) -> str:
    """De tekst van een samenvatting: het aantal per soort, meest voorkomende eerst, en hoeveel er te laat zijn.

    Bij gelijke aantallen blijft de volgorde van eerste voorkomen, want de server sorteert op dringendheid.
    Een onbekende soort telt mee in één groep 'other', zodat er nooit een ruwe sleutel in de tekst komt.
    """
    counts: dict[str, int] = {}  # dict behoudt de volgorde van eerste voorkomen
    for item in items:
        # Zonder eigen telvorm (ook een soort die later in `kind.*` bijkomt) valt ze onder 'other'.
        kind = item.kind if f"count.{item.kind}.one" in NL else "other"
        counts[kind] = counts.get(kind, 0) + 1
    # sorted is stabiel: bij gelijke aantallen blijft de volgorde van eerste voorkomen
    parts = []
    for kind, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        form = "one" if n == 1 else "many"
        parts.append(translate(lang, f"count.{kind}.{form}", n=n))
    text = ", ".join(parts)
    overdue = sum(1 for item in items if item.overdue)
    if overdue:
        text += " " + translate(lang, "toast.summary_overdue", n=overdue)
    return text


def item_toast(item: Item, lang: str) -> Toast:
    head = translate(lang, "toast.overdue" if item.overdue else "toast.action")
    where = " · ".join(p for p in (item.property_label, item.account_name) if p)
    return Toast(
        item.title,
        f"{head}" + (f" · {where}" if where else ""),
        item.href if is_openable(item.href) else None,
        item.id,
        item.kind,
    )
