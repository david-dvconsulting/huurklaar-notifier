"""Menu-model: een platformonafhankelijke beschrijving die de menubalk (Mac) of tray (Windows) tekent."""

from __future__ import annotations

import time
from collections.abc import Hashable, Iterable
from dataclasses import dataclass

from .. import __version__
from .api import is_openable
from .i18n import LANGUAGES, NL, translate
from .state import State, Status
from .state import app_url as _app_url
from .updates import Release

MAX_MENU_ITEMS = 10
MAX_LABEL = 70

# Acties die een platform afhandelt
REFRESH, SETTINGS, AUTOSTART, QUIT = "refresh", "settings", "autostart", "quit"
LANGUAGE_PREFIX = "language:"
PAUSE_PREFIX = "pause:"
PAUSE_HOUR, PAUSE_TOMORROW, PAUSE_OFF = "hour", "tomorrow", "off"
KIND_PREFIX = "kind:"
REMINDER = "reminder"
# Vaste volgorde van het submenu "Meldingen voor". Een soort die de server nieuw stuurt, staat hier niet en
# krijgt geen vinkje: zonder naam zou het gewoon 'Melding' heten en de gebruiker niets zeggen.
KNOWN_KINDS = ("task", "complaint", "report", "tenantTask", "myReport", "invoiceAttention")


@dataclass(frozen=True, slots=True)
class Entry:
    label: str
    url: str | None = None  # opent in de browser
    action: str | None = None
    enabled: bool = True
    checked: bool | None = None
    children: tuple[Entry, ...] = ()
    separator: bool = False


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


def status_line(state: State, lang: str, paused_until: float = 0.0) -> str:
    """De statusregel; tijdens een pauze (`paused_until` > 0) vooraan 'Gepauzeerd tot HH:MM'."""
    line = _status_text(state, lang)
    if paused_until > 0:
        until = time.strftime("%H:%M", time.localtime(paused_until))
        pause = translate(lang, "status.paused", time=until)
        return pause if state.status is Status.IDLE else f"{pause} · {line}"
    return line


def _status_text(state: State, lang: str) -> str:
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


def kind_entries(state: State, lang: str, muted_kinds: tuple[str, ...] = ()) -> tuple[Entry, ...]:
    """Het submenu per soort: de bekende soorten uit het huidige antwoord, plus de uitgezette soorten.

    Een uitgezette soort blijft staan als ze niet meer in het antwoord zit: anders kun je ze niet meer aanzetten.
    Geeft een leeg tuple als er niets te kiezen valt; dan hoort er geen submenu te komen.
    """
    present = {i.kind for i in state.snapshot.items} if state.snapshot else set()
    return tuple(
        Entry(kind_label(lang, kind), action=KIND_PREFIX + kind, checked=kind not in muted_kinds)
        for kind in KNOWN_KINDS
        if kind in present or kind in muted_kinds
    )


def build_menu(
    state: State,
    lang: str,
    language_setting: str,
    autostart: bool,
    update: Release | None = None,
    paused_until: float = 0.0,
    muted_kinds: tuple[str, ...] = (),
    daily_reminder: bool = True,
) -> list[Entry]:
    t = lambda key, **p: translate(lang, key, **p)  # noqa: E731
    entries: list[Entry] = [Entry(status_line(state, lang, paused_until), enabled=False)]
    if update is not None:  # de klik opent de releasepagina; automatisch vervangen is een latere stap
        entries.append(Entry(t("menu.update", version=update.version), url=update.url))
    if state.status is Status.OFFLINE and state.updated_at:
        entries.append(Entry(t("status.updated", time=state.updated_at), enabled=False))

    snap = state.snapshot
    if snap and state.status in (Status.ATTENTION, Status.OFFLINE) and snap.items:
        entries.append(SEPARATOR)
        for item in snap.items[:MAX_MENU_ITEMS]:
            prefix = "⚠️ " if item.overdue else ""
            where = " — " + item.property_label if item.property_label else ""
            label = _shorten(f"{prefix}{kind_label(lang, item.kind)}: {item.title}{where}")
            entries.append(Entry(label, url=item.href if is_openable(item.href) else None))
        rest = snap.total - min(len(snap.items), MAX_MENU_ITEMS)
        if rest > 0:
            entries.append(Entry(t("menu.more", n=rest), url=_app_url(list(snap.items))))
    if snap and state.status in (Status.ATTENTION, Status.IDLE):
        link = _app_url(list(snap.items))
        if link:
            entries += [SEPARATOR, Entry(t("menu.open_app"), url=link)]

    languages = tuple(
        Entry(
            t("menu.language_auto") if code == "auto" else code.upper(),
            action=LANGUAGE_PREFIX + code,
            checked=language_setting == code,
        )
        for code in ("auto", *LANGUAGES)
    )
    pause = [
        Entry(t("menu.pause_hour"), action=PAUSE_PREFIX + PAUSE_HOUR),
        Entry(t("menu.pause_tomorrow"), action=PAUSE_PREFIX + PAUSE_TOMORROW),
    ]
    if paused_until > 0:
        pause.append(Entry(t("menu.pause_off"), action=PAUSE_PREFIX + PAUSE_OFF))
    kinds = kind_entries(state, lang, muted_kinds)
    entries += [
        SEPARATOR,
        Entry(t("menu.refresh"), action=REFRESH),
        Entry(t("menu.settings"), action=SETTINGS),
        Entry(t("menu.language"), children=languages),
        Entry(t("menu.pause"), children=tuple(pause)),
    ]
    if kinds:
        entries.append(Entry(t("menu.kinds"), children=kinds))
    entries += [
        Entry(t("menu.reminder"), action=REMINDER, checked=daily_reminder),
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
