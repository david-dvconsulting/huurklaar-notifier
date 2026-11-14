"""macOS: ontvangt `huurklaar-meldingen://`-links als Apple Event (`kAEGetURL`) en geeft ze door aan de kern.

De logica (valideren, bevestigen, bewaren) zit in `AppActions.apply_link`; hier enkel het event.
Dit bestand mag enkel op een Mac geïmporteerd worden.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from Foundation import NSAppleEventManager, NSObject

log = logging.getLogger(__name__)

# Four-char codes (big-endian ASCII); PyObjC exporteert deze constanten niet altijd.
# 'GURL' is zowel kInternetEventClass als kAEGetURL, '----' is keyDirectObject.
_GURL = 0x4755524C
_DIRECT_OBJECT = 0x2D2D2D2D


class _GetUrlHandler(NSObject):
    def initWithCallback_(self, callback):
        self = self.init()
        if self is not None:
            self._callback = callback
        return self

    def handleGetURLEvent_withReplyEvent_(self, event, reply):
        # Nooit een exceptie naar Cocoa laten gaan; nooit de link (adres of sleutel) loggen.
        try:
            url = event.paramDescriptorForKeyword_(_DIRECT_OBJECT).stringValue()
            if url:
                threading.Thread(target=self._callback, args=(str(url),), name="link", daemon=True).start()
        except Exception as e:
            log.warning("link ontvangen mislukt: %s", type(e).__name__)


class LinkHandler:
    """Registreert de handler en houdt er een sterke verwijzing naar vast (Cocoa houdt enkel een zwakke)."""

    def __init__(self, apply_link: Callable[[str], None]) -> None:
        def run(url: str) -> None:
            try:
                apply_link(url)
            except Exception as e:  # de thread mag stil sterven; enkel het type loggen
                log.warning("link verwerken mislukt: %s", type(e).__name__)

        self._handler = _GetUrlHandler.alloc().initWithCallback_(run)

    def register(self) -> None:
        NSAppleEventManager.sharedAppleEventManager().setEventHandler_andSelector_forEventClass_andEventID_(
            self._handler, b"handleGetURLEvent:withReplyEvent:", _GURL, _GURL
        )
