"""Instellingenvenster op de Mac, deel zonder AppKit: de teksten en de overdracht naar de hoofdthread.

Apart gehouden zodat het ook in CI op Windows getest kan worden. De AppKit-code staat in
`macos_settings.py`.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from ..core.i18n import translate

Answer = tuple[str, str] | None


@dataclass(frozen=True)
class SettingsTexts:
    title: str
    url_label: str
    key_label: str
    save: str
    cancel: str


def settings_texts(lang: str, key_saved: bool) -> SettingsTexts:
    """De teksten van het venster. Is er al een sleutel bewaard, dan zegt het label dat leeg laten volstaat."""
    key_label = translate(lang, "dialog.key_prompt")
    if key_saved:
        key_label += "\n" + translate(lang, "dialog.key_keep")
    return SettingsTexts(
        title=translate(lang, "dialog.title"),
        url_label=translate(lang, "dialog.url_prompt"),
        key_label=key_label,
        save=translate(lang, "dialog.save"),
        cancel=translate(lang, "dialog.cancel"),
    )


def run_on_main(
    show: Callable[[], Answer],
    call_after: Callable[[Callable[[], None]], None],
    *,
    start_timeout: float = 30.0,
    poll: float = 0.5,
) -> Answer:
    """Laat `show` op de hoofdthread draaien en wacht op het antwoord. Vanaf een andere thread aan te roepen.

    Time-out: de gebruiker mag zo lang typen als hij wil, dus na het openen wachten we zonder limiet (in
    korte stappen van `poll`). Enkel het *openen* heeft een limiet (`start_timeout`): neemt de hoofdthread
    de taak niet op, dan geven we op en laten we de aanroeper vrij, zodat de lock van de instellingenflow
    niet voor altijd vastzit. Een taak die we hebben opgegeven, toont later geen venster meer (`abandoned`),
    dus er blijft nooit een venster staan waarvan het resultaat verloren gaat.

    Een exceptie in `show` wordt hier opnieuw opgegooid, zodat de aanroeper kan terugvallen.
    """
    state = threading.Lock()
    started = threading.Event()
    done = threading.Event()
    box: dict[str, object] = {}
    abandoned = False

    def task() -> None:
        nonlocal abandoned
        with state:
            if abandoned:
                return
            started.set()
        try:
            box["answer"] = show()
        except BaseException as e:  # doorgeven aan de wachtende thread
            box["error"] = e
        finally:
            done.set()

    call_after(task)
    if not started.wait(timeout=start_timeout):
        with state:
            if not started.is_set():
                abandoned = True
                raise TimeoutError("instellingenvenster niet gestart")
    while not done.wait(timeout=poll):
        pass
    error = box.get("error")
    if isinstance(error, BaseException):
        raise error
    return box.get("answer")  # type: ignore[return-value]
