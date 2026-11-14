"""Windows-meldingen via `win11toast` onder een eigen AppUserModelID.

Een klik opent de pagina zonder dat ons proces iets hoeft te doen: `on_click` als tekst wordt het
`launch`-attribuut van een 'protocol'-toast, en Windows opent het webadres zelf in de standaardbrowser. We
wachten dus niet op een callback, houden geen thread per melding open en missen niets als de app intussen stopt.
Enkel http(s)-adressen gaan mee (`is_openable`): nooit `file:` of een eigen protocol uit een serverantwoord.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable

from ..core.api import is_openable
from ..core.state import Toast
from .windows_registry import AUMID

log = logging.getLogger(__name__)
MAX_TITLE = 120
MAX_BODY = 240
# Vaste groep: `withdraw` heeft zo geen geheugen nodig. Windows beperkt tag en group tot 64 tekens.
GROUP = "hk"


def toast_tag(key: str) -> str:
    """Korte, vaste tag (32 tekens) voor een melding: dezelfde sleutel geeft dezelfde tag, ook voor lange item-id's."""
    return hashlib.sha1(key.encode()).hexdigest()[:32]


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


class WindowsNotifier:
    def __init__(
        self,
        notify_fn: Callable[..., object] | None = None,
        app_id: str = AUMID,
        clear_fn: Callable[..., object] | None = None,
    ) -> None:
        self._notify_fn = notify_fn
        self._clear_fn = clear_fn
        self._app_id = app_id

    def notify(self, toast: Toast) -> None:
        title, body, url = toast.title, toast.body, toast.url
        try:
            fn = self._notify_fn or _win11toast_notify()
            fn(
                _short(title, MAX_TITLE),
                _short(body, MAX_BODY),
                on_click=url if url and is_openable(url) else None,
                app_id=self._app_id,
                tag=toast_tag(toast.key),
                group=GROUP,
            )
        except Exception:  # een melding mag de app nooit doen vallen; geen titel of tekst in het log
            log.warning("melding tonen mislukt", exc_info=True)

    def withdraw(self, keys: list[str]) -> None:
        """Haalt de meldingen met deze sleutels uit het Actiecentrum; werpt nooit.

        Elke sleutel krijgt een eigen try/except: een melding die de gebruiker al wegklikte mag geen fout geven en
        één fout houdt de andere niet tegen. Nooit zonder tag: `clear_toast` wist dan de hele groep. Geen sleutel in het log.
        """
        for key in keys:
            try:
                fn = self._clear_fn or _win11toast_clear()
                fn(app_id=self._app_id, tag=toast_tag(key), group=GROUP)
            except Exception as exc:
                log.debug("melding intrekken mislukt: %s", type(exc).__name__)


def _win11toast_notify() -> Callable[..., object]:
    from win11toast import notify

    return notify


def _win11toast_clear() -> Callable[..., object]:
    from win11toast import clear_toast

    return clear_toast
