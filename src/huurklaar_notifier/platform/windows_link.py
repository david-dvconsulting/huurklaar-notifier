"""Een link van het URL-schema doorgeven aan de draaiende instantie, via een named pipe.

Windows start voor `huurklaar-meldingen://...` een nieuw proces met de link als argument. Omdat er maar één
instantie mag draaien, stuurt dat proces de link door en stopt. Alles hier is ook zonder Windows te testen
(`family="AF_UNIX"`); op Windows is de familie `AF_PIPE`.

Enkel bytes over de lijn, nooit `send()`/`recv()`: die gebruiken pickle, waarmee een client code zou kunnen
laten uitvoeren. De link, de sleutel en het adres worden nooit gelogd.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from multiprocessing.connection import Client, Listener

from ..core.link import SCHEME

log = logging.getLogger(__name__)

MAX_LINK_BYTES = 4096


def link_from_argv(argv: list[str]) -> str | None:
    """Het eerste argument dat met het schema begint (hoofdletterongevoelig)."""
    prefix = f"{SCHEME}:"
    for arg in argv:
        if arg.lower().startswith(prefix):
            return arg
    return None


def pipe_address(user: str) -> str:
    """De pipenaam voor één gebruiker. Enkel letters, cijfers, `-`, `_` en `.`: de rest wordt `_`."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", user) or "_"
    return rf"\\.\pipe\HuurklaarMeldingen-{safe}"


def _is_link(text: str) -> bool:
    return text.lower().startswith(f"{SCHEME}:")


def send_link(url: str, address: str, family: str = "AF_PIPE", timeout: float = 5.0) -> bool:
    """Stuurt de link naar de draaiende instantie. `False` bij elke fout (niemand luistert, time-out).

    `Client()` heeft geen time-out; daarom gebeurt het versturen op een daemon-thread waar we op wachten.
    """
    ok = threading.Event()

    def send() -> None:
        try:
            with Client(address, family=family) as conn:
                conn.send_bytes(url.encode())
            ok.set()
        except Exception as e:  # geen luisteraar, pipe bezet, ...: enkel het type loggen
            log.info("link doorgeven mislukt: %s", type(e).__name__)

    worker = threading.Thread(target=send, name="link-send", daemon=True)
    worker.start()
    worker.join(timeout)
    return ok.is_set()


class LinkServer:
    """Luistert op een pipe en geeft elke geldige link door aan `on_link` (op de luisterthread)."""

    def __init__(
        self,
        address: str,
        on_link: Callable[[str], None],
        family: str = "AF_PIPE",
        read_timeout: float = 2.0,
    ) -> None:
        self._address = address
        self._on_link = on_link
        self._family = family
        self._read_timeout = read_timeout  # een client die niets stuurt mag de lus niet blokkeren
        self._listener: Listener | None = None
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()

    def start(self) -> None:
        """Maakt de luisteraar (kan falen, bv. als de naam bezet is) en start de thread."""
        self._listener = Listener(self._address, family=self._family)
        self._thread = threading.Thread(target=self._loop, name="link-server", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Stopt de lus. `accept()` blokkeert, dus zetten we de vlag en verbinden we zelf één keer."""
        self._stopping.set()
        thread, listener = self._thread, self._listener
        if thread is not None and thread.is_alive():
            try:
                Client(self._address, family=self._family).close()  # wekt accept()
            except Exception as e:  # de lus kan al weg zijn
                log.info("link-server wekken mislukt: %s", type(e).__name__)
            thread.join(timeout)
        if listener is not None:
            try:
                listener.close()
            except Exception as e:
                log.info("link-server sluiten mislukt: %s", type(e).__name__)
        self._thread = self._listener = None

    def _loop(self) -> None:
        listener = self._listener
        while listener is not None and not self._stopping.is_set():
            try:
                with listener.accept() as conn:
                    if self._stopping.is_set():
                        return
                    self._handle(conn)
            except Exception as e:  # een foute client mag de lus niet stoppen; enkel het type loggen
                if self._stopping.is_set():
                    return
                log.warning("link-server: %s", type(e).__name__)
                self._stopping.wait(0.2)  # geen drukke lus als `accept()` blijft falen

    def _handle(self, conn) -> None:
        if not conn.poll(self._read_timeout):
            return
        text = conn.recv_bytes(maxlength=MAX_LINK_BYTES).decode()  # te lang of geen utf-8: exceptie
        if _is_link(text):
            self._on_link(text)
