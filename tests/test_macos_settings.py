"""Teksten en thread-overdracht van het Mac-instellingenvenster (zonder AppKit, draait overal)."""

import threading

import pytest

from huurklaar_notifier.core.i18n import translate
from huurklaar_notifier.platform.settings_dialog import run_on_main, settings_texts


def test_teksten_zonder_bewaarde_sleutel_hebben_geen_leeg_laten_regel():
    t = settings_texts("nl", key_saved=False)
    assert t.key_label == translate("nl", "dialog.key_prompt")
    assert translate("nl", "dialog.key_keep") not in t.key_label


def test_teksten_met_bewaarde_sleutel_zeggen_dat_leeg_laten_volstaat():
    t = settings_texts("fr", key_saved=True)
    assert t.key_label.endswith(translate("fr", "dialog.key_keep"))
    assert t.title == translate("fr", "dialog.title")
    assert (t.save, t.cancel) == (translate("fr", "dialog.save"), translate("fr", "dialog.cancel"))
    assert t.url_label == translate("fr", "dialog.url_prompt")


def make_main_thread():
    """Een nep-hoofdthread: voert de ingeplande taken uit op een eigen thread."""
    tasks: list = []
    ready = threading.Event()
    stop = threading.Event()
    names: list[str] = []

    def call_after(fn):
        tasks.append(fn)
        ready.set()

    def loop():
        while not stop.is_set():
            if ready.wait(timeout=0.05):
                ready.clear()
                while tasks:
                    fn = tasks.pop(0)
                    names.append(threading.current_thread().name)
                    fn()

    th = threading.Thread(target=loop, name="nep-main")
    th.start()
    return call_after, stop, th, names


def test_show_draait_op_de_hoofdthread_en_geeft_het_antwoord_terug():
    call_after, stop, th, names = make_main_thread()
    try:
        answer = run_on_main(lambda: ("https://x.test", "sleutel"), call_after, start_timeout=2, poll=0.01)
    finally:
        stop.set()
        th.join(timeout=2)
    assert answer == ("https://x.test", "sleutel")
    assert names == ["nep-main"]


def test_annuleren_geeft_none():
    call_after, stop, th, _ = make_main_thread()
    try:
        assert run_on_main(lambda: None, call_after, start_timeout=2, poll=0.01) is None
    finally:
        stop.set()
        th.join(timeout=2)


def test_exceptie_in_show_wordt_doorgegeven():
    call_after, stop, th, _ = make_main_thread()

    def boom():
        raise RuntimeError("kapot")

    try:
        with pytest.raises(RuntimeError):
            run_on_main(boom, call_after, start_timeout=2, poll=0.01)
    finally:
        stop.set()
        th.join(timeout=2)


def test_lang_openstaand_venster_wordt_niet_afgebroken_door_de_starttime_out():
    call_after, stop, th, _ = make_main_thread()
    started = threading.Event()
    release = threading.Event()

    def slow():
        started.set()
        release.wait(timeout=2)
        return ("a", "b")

    result: list = []
    worker = threading.Thread(
        target=lambda: result.append(run_on_main(slow, call_after, start_timeout=0.1, poll=0.01))
    )
    try:
        worker.start()
        assert started.wait(timeout=2)
        threading.Event().wait(0.3)  # ruim langer dan start_timeout
        assert worker.is_alive()  # wacht nog op de gebruiker
        release.set()
        worker.join(timeout=2)
    finally:
        release.set()
        stop.set()
        th.join(timeout=2)
    assert result == [("a", "b")]


def test_hoofdthread_die_nooit_start_geeft_de_aanroeper_vrij_en_toont_later_niets():
    pending: list = []
    shown: list = []
    with pytest.raises(TimeoutError):
        run_on_main(lambda: shown.append(1), pending.append, start_timeout=0.1, poll=0.01)
    pending[0]()  # de hoofdthread komt te laat
    assert shown == []
