"""Menu-model: een platformonafhankelijke beschrijving die de menubalk (Mac) of tray (Windows) tekent."""

from __future__ import annotations

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


def build_menu(
    state: State, lang: str, language_setting: str, autostart: bool, update: Release | None = None
) -> list[Entry]:
    t = lambda key, **p: translate(lang, key, **p)  # noqa: E731
    entries: list[Entry] = [Entry(status_line(state, lang), enabled=False)]
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
    entries += [
        SEPARATOR,
        Entry(t("menu.refresh"), action=REFRESH),
        Entry(t("menu.settings"), action=SETTINGS),
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
