"""Windows-meldingen via `win11toast` onder een eigen AppUserModelID.

Een klik opent de pagina zonder dat ons proces iets hoeft te doen: `on_click` als tekst wordt het
`launch`-attribuut van een 'protocol'-toast, en Windows opent het webadres zelf in de standaardbrowser. We
wachten dus niet op een callback, houden geen thread per melding open en missen niets als de app intussen stopt.
Enkel http(s)-adressen gaan mee (`is_openable`): nooit `file:` of een eigen protocol uit een serverantwoord.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from ..core.api import is_openable
from .windows_registry import AUMID

log = logging.getLogger(__name__)
MAX_TITLE = 120
MAX_BODY = 240


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


class WindowsNotifier:
    def __init__(self, notify_fn: Callable[..., object] | None = None, app_id: str = AUMID) -> None:
        self._notify_fn = notify_fn
        self._app_id = app_id

    def notify(self, title: str, body: str, url: str | None) -> None:
        try:
            fn = self._notify_fn or _win11toast_notify()
            fn(
                _short(title, MAX_TITLE),
                _short(body, MAX_BODY),
                on_click=url if url and is_openable(url) else None,
                app_id=self._app_id,
            )
        except Exception:  # een melding mag de app nooit doen vallen; geen titel of tekst in het log
            log.warning("melding tonen mislukt", exc_info=True)


def _win11toast_notify() -> Callable[..., object]:
    from win11toast import notify

    return notify
