"""Menu-model: een platformonafhankelijke beschrijving die de menubalk (Mac) of tray (Windows) tekent."""

from __future__ import annotations

import re
from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from .. import __version__
from .api import is_openable
from .defaults import app_url_for
from .i18n import LANGUAGES, NL, translate
from .models import Item
from .state import State, Status
from .state import app_url as _app_url
from .updates import Release

MAX_MENU_ITEMS = 10
MAX_LABEL = 70
MAX_ACCOUNT = 24  # een lange accountnaam wordt ingekort, zodat de vervaldatum heel blijft

# Acties die een platform afhandelt
REFRESH, SETTINGS, AUTOSTART, QUIT = "refresh", "settings", "autostart", "quit"
LANGUAGE_PREFIX = "language:"


@dataclass(frozen=True, slots=True)
class Entry:
    label: str
    url: str | None = None  # opent in de browser
    action: str | None = None
    enabled: bool = True
    checked: bool | None = None
    children: tuple[Entry, ...] = ()
    separator: bool = False
    default: bool = False  # het standaarditem: een linksklik op het tray-icoon voert dit uit (Windows)


SEPARATOR = Entry("", separator=True)


def _shorten(text: str) -> str:
    return text if len(text) <= MAX_LABEL else text[: MAX_LABEL - 1] + "…"


def title_for(state: State) -> str:
    """Tekst naast het logo in de menubalk: het aantal (te doen), '!' bij een probleem, anders leeg."""
    if state.status is Status.ATTENTION and state.snapshot:
        return str(state.snapshot.action_required or state.snapshot.total)
    if state.status in (Status.OFFLINE, Status.AUTH_FAILED, Status.NOT_CONFIGURED):
        return "!"
    return ""


def title_style(state: State) -> Literal["normal", "alert"]:
    """Kleur van de titel (Mac): 'alert' (rood) enkel als er iets te laat is, zoals de rode badge op Windows.

    Bij OFFLINE blijft het 'normal': de titel is dan '!' en de oude snapshot kan verouderd zijn, dus rood zou
    een te-laatmelding tonen die we niet meer kunnen bevestigen. Het menu zelf toont de oude items nog wel.
    """
    if state.status is Status.ATTENTION and state.snapshot and state.snapshot.overdue > 0:
        return "alert"
    return "normal"


def status_line(state: State, lang: str) -> str:
    if state.status is Status.ATTENTION and state.snapshot:
        text = translate(lang, "status.tasks", n=state.snapshot.total)
        if state.snapshot.overdue:
            text += " · " + translate(lang, "status.overdue", n=state.snapshot.overdue)
        return text
    return translate(lang, f"status.{state.status.value}")


def kind_label(lang: str, kind: str) -> str:
    """Onbekende soorten (de server mag er nieuwe toevoegen) krijgen de generieke tekst 'kind.other'."""
    key = "kind." + kind
    return translate(lang, key if key in NL else "kind.other")


_ISO_DATUM = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def due_label(due_date: str | None, today: date, lang: str) -> str | None:
    """Relatieve vervaldatum voor het menu: 'vandaag', 'morgen', 'over n d' of 'n d te laat'.

    Geeft `None` bij een ontbrekende of ongeldige datum en bij een datum meer dan 7 dagen vooruit: dan
    toont het menu niets extra's. Werpt nooit, want een rare waarde van de server mag het menu niet breken.
    """
    if not isinstance(due_date, str) or not _ISO_DATUM.fullmatch(due_date):
        return None
    try:
        due = date.fromisoformat(due_date)
    except ValueError:  # bv. een maand 13 of een dag 40
        return None
    days = (due - today).days
    if days < 0:
        return translate(lang, "due.overdue_days", n=-days)
    if days == 0:
        return translate(lang, "due.today")
    if days == 1:
        return translate(lang, "due.tomorrow")
    if days <= 7:
        return translate(lang, "due.in_days", n=days)
    return None


_MIN_TITLE = 12  # korter maken we een titel niet; daarna komt het pand aan de beurt


def _cut(text: str, room: int) -> str:
    if len(text) <= room:
        return text
    return text[: room - 1] + "…" if room > 0 else ""


def _fit(before: str, title: str, where: str = "", after: str = "") -> str:
    """`before + title + where + after` binnen MAX_LABEL.

    Eerst wordt de titel ingekort (tot `_MIN_TITLE`), daarna het pand (`where`). `after`, bv. de
    vervaldatum, blijft heel: dat is wat de gebruiker in één oogopslag moet kunnen lezen.
    """
    room = MAX_LABEL - len(before) - len(where) - len(after)
    title = _cut(title, max(room, _MIN_TITLE))
    where = _cut(where, MAX_LABEL - len(before) - len(title) - len(after))
    return _shorten(before + title + where + after)


# Vaste volgorde van de groepen in het menu; onbekende soorten komen samen onder `OTHER_GROUP`.
GROUP_ORDER = ("invoiceAttention", "complaint", "report", "task", "myReport", "tenantTask")
OTHER_GROUP = "other"


def group_items(items: Iterable[Item]) -> list[tuple[str, list[Item]]]:
    """Verdeelt de items over de groepen in de vaste volgorde. Lege groepen vallen weg.

    Binnen een groep blijft de volgorde van de server (dringendste eerst).
    """
    buckets: dict[str, list[Item]] = {key: [] for key in (*GROUP_ORDER, OTHER_GROUP)}
    for item in items:
        buckets[item.kind if item.kind in GROUP_ORDER else OTHER_GROUP].append(item)
    return [(key, group) for key, group in buckets.items() if group]


def _distribute(groups: list[tuple[str, list[Item]]], limit: int) -> list[list[Item]]:
    """Round-robin over de groepen tot `limit` items of alles getoond is: elke groep krijgt minstens één item."""
    shown: list[list[Item]] = [[] for _ in groups]
    total = 0
    depth = 0
    while total < limit and any(depth < len(g) for _, g in groups):
        for index, (_, group) in enumerate(groups):
            if total < limit and depth < len(group):
                shown[index].append(group[depth])
                total += 1
        depth += 1
    return shown


def _has_multiple_accounts(items: Iterable[Item]) -> bool:
    """`True` als er minstens twee verschillende niet-lege accountnamen zijn (over het hele antwoord)."""
    return len({item.account_name for item in items if item.account_name}) > 1


def _item_entry(item: Item, lang: str, today: date, with_kind: bool, with_account: bool) -> Entry:
    """Eén regel voor een item. `with_kind`: zet de soort ervoor (bij één groep, zonder kopregel).

    `with_account`: zet de accountnaam na het pand (bij meerdere accounts). Die blijft bij het inkorten
    na de titel en het pand, zodat de accountnaam en de vervaldatum leesbaar blijven.
    """
    before = "⚠️ " if item.overdue else ""
    if with_kind:
        before += kind_label(lang, item.kind) + ": "
    where = " — " + item.property_label if item.property_label else ""
    due = due_label(item.due_date, today, lang)
    after = " · " + due if due else ""
    if with_account and item.account_name:
        # De accountnaam mag de titel niet onder de minimale lengte drukken: de ruimte voor de titel
        # blijft dus eerst gereserveerd. Zo blijft de vervaldatum heel, ook bij een lange soort.
        room = MAX_LABEL - len(before) - _MIN_TITLE - len(" · ") - len(after)
        account = _cut(item.account_name, min(MAX_ACCOUNT, room))
        after = f" · {account}{after}"
    return Entry(_fit(before, item.title, where, after), url=item.href if is_openable(item.href) else None)


def build_menu(
    state: State,
    lang: str,
    language_setting: str,
    autostart: bool,
    update: Release | None = None,
    *,
    base_url: str = "",
    today: date | None = None,
) -> list[Entry]:
    if today is None:
        today = date.today()
    t = lambda key, **p: translate(lang, key, **p)  # noqa: E731
    entries: list[Entry] = [Entry(status_line(state, lang), enabled=False)]
    if state.status in (Status.NOT_CONFIGURED, Status.AUTH_FAILED):
        # Zonder (geldige) sleutel: de gebruiker moet er eentje aanmaken in de juiste omgeving.
        entries.append(Entry(t("menu.get_key"), url=app_url_for(base_url) + "/profile/notifications"))
    if update is not None:  # de klik opent de releasepagina; automatisch vervangen is een latere stap
        entries.append(Entry(t("menu.update", version=update.version), url=update.url))
    # Ook bij ATTENTION en IDLE: zo ziet de gebruiker hoe recent de lijst is.
    if state.status in (Status.OFFLINE, Status.ATTENTION, Status.IDLE) and state.updated_at:
        entries.append(Entry(t("status.updated", time=state.updated_at), enabled=False))

    snap = state.snapshot
    if snap and state.status in (Status.ATTENTION, Status.OFFLINE) and snap.items:
        entries.append(SEPARATOR)
        groups = group_items(snap.items)
        shown = _distribute(groups, MAX_MENU_ITEMS)
        # Over het hele antwoord, niet enkel de getoonde items: ook dan zijn er meerdere accounts.
        with_account = _has_multiple_accounts(snap.items)
        for (key, group), visible in zip(groups, shown, strict=True):
            if len(groups) > 1 and visible:  # bij één groep zegt het voorvoegsel de soort al
                entries.append(Entry(t(f"group.{key}", n=len(group)), enabled=False))
            entries += [
                _item_entry(item, lang, today, with_kind=len(groups) == 1, with_account=with_account)
                for item in visible
            ]
        rest = snap.total - sum(len(v) for v in shown)
        if rest > 0:
            entries.append(Entry(t("menu.more", n=rest), url=_app_url(list(snap.items))))
    if snap and state.status in (Status.ATTENTION, Status.IDLE):
        # Het standaarditem: pystray voert bij een linksklik het item met default=True uit. De link uit de
        # items wijst naar de juiste omgeving; een lege lijst heeft er geen, dan volgt de app uit het API-adres.
        link = _app_url(list(snap.items)) or app_url_for(base_url) + "/"
        entries += [SEPARATOR, Entry(t("menu.open_app"), url=link, default=True)]

    languages = tuple(
        Entry(
            t("menu.language_auto") if code == "auto" else code.upper(),
            action=LANGUAGE_PREFIX + code,
            checked=language_setting == code,
        )
        for code in ("auto", *LANGUAGES)
    )
    # Zonder "Huurklaar openen" (niet ingesteld, sleutel ongeldig, geen verbinding) is de instelling het
    # standaarditem.
    # Er is altijd precies één: wie ook maar één `default` zet, verandert deze regel niet.
    settings = Entry(t("menu.settings"), action=SETTINGS, default=not any(e.default for e in entries))
    entries += [
        SEPARATOR,
        Entry(t("menu.refresh"), action=REFRESH),
        settings,
        Entry(t("menu.language"), children=languages),
        Entry(t("menu.autostart"), action=AUTOSTART, checked=autostart),
        SEPARATOR,
        Entry(t("menu.about", version=__version__), enabled=False),
        Entry(t("menu.quit"), action=QUIT),
    ]
    return entries


class MenuCache:
    """Onthoudt de laatst getekende staat, zodat een platform het menu enkel opnieuw opbouwt als er iets veranderde.

    Zonder dit bouwt elke poll (minstens om de 60 s) het hele menu opnieuw op, ook bij een identiek antwoord.
    `title` is wat het platform naast de items nog toont (Mac: titeltekst; Windows: bv. `(badge, tooltip)`).
    """

    def __init__(self) -> None:
        self._last: tuple[tuple[Entry, ...], Hashable] | None = None

    def changed(self, entries: Iterable[Entry], title: Hashable) -> bool:
        """`True` (en de nieuwe staat onthouden) als die verschilt van de vorige; de eerste keer altijd `True`."""
        state = (tuple(entries), title)
        if state == self._last:
            return False
        self._last = state
        return True

    def reset(self) -> None:
        """Vergeet de staat. Roep dit op als het tekenen na `changed()` mislukte, zodat de volgende poging tekent."""
        self._last = None
