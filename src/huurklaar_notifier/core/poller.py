"""De pollus op een eigen thread; levert resultaten via een callback (het platform zet ze op de UI-thread)."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from .controller import Controller
from .state import BACKOFF_MAX, Toast

log = logging.getLogger(__name__)


class Poller:
    def __init__(
        self,
        controller: Controller,
        on_result: Callable[[list[Toast]], None],
        error_delay: float = BACKOFF_MAX,  # wachttijd na een onverwachte fout (in tests kleiner)
    ) -> None:
        self._c = controller
        self._on_result = on_result
        self._error_delay = error_delay
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="poller", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._c.wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._c.wake.clear()
            try:
                toasts = self._c.poll()
                self._on_result(toasts)
                delay = self._c.next_delay()  # None = wachten tot er nieuwe instellingen zijn
            except Exception as e:  # een fout mag de pollus niet stoppen; enkel het type loggen
                log.warning("poll mislukt: %s", type(e).__name__)
                delay = self._error_delay
            self._c.wake.wait(timeout=delay)


class UpdatePoller:
    """Controleert eens per dag op een nieuwe versie, los van de meldingen-pollus (die soms bewust stilvalt)."""

    MAX_WAIT = 3600.0  # kijkt minstens elk uur of de check aan de beurt is (ook na slaapstand of klokwissel)

    def __init__(self, controller: Controller, on_change: Callable[[], None]) -> None:
        self._c = controller
        self._on_change = on_change
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="update-check", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if self._c.check_for_update():
                    self._on_change()
                wait = min(max(self._c.update_due_in(), 1.0), self.MAX_WAIT)
            except Exception:
                wait = self.MAX_WAIT
            self._stop.wait(timeout=wait)
