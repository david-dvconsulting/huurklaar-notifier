"""De pollus blijft draaien na een onverwachte fout (zoals een volle schijf bij het opslaan)."""

import threading

from huurklaar_notifier.core.poller import Poller


class FlakyController:
    """`poll` werpt de eerste keer een OSError en geeft daarna geen meldingen."""

    def __init__(self) -> None:
        self.wake = threading.Event()
        self.calls = 0
        self.first_failed = threading.Event()

    def poll(self):
        self.calls += 1
        if self.calls == 1:
            self.first_failed.set()
            raise OSError("schijf vol")
        return []

    def next_delay(self):
        return None  # wachten tot 'wake' gezet wordt


def test_pollus_overleeft_een_fout_en_pollt_opnieuw(caplog):
    c = FlakyController()
    second = threading.Event()
    results = []

    def on_result(toasts):
        results.append(toasts)
        second.set()

    poller = Poller(c, on_result, error_delay=60.0)  # lang: de test komt enkel door 'wake' verder
    poller.start()
    try:
        assert c.first_failed.wait(timeout=2)
        c.wake.set()  # 'nu vernieuwen'
        assert second.wait(timeout=2), "geen tweede poll na de fout"
    finally:
        poller.stop()
        poller._thread.join(timeout=2)  # _thread: de test controleert dat de lus netjes stopt
    assert not poller._thread.is_alive()
    assert results == [[]]
    assert "OSError" in caplog.text
    assert "schijf vol" not in caplog.text  # logs bevatten enkel het fouttype
