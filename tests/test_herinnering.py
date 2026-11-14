"""Dagelijkse herinnering (KAN-285): nep-klok, één keer per dag vanaf 9:00, niet tijdens een pauze."""

import time

import pytest

from huurklaar_notifier.core.controller import REMINDER_HOUR, Controller, next_local_time
from huurklaar_notifier.core.state import State
from huurklaar_notifier.testing.fake_server import EMPTY, FAKE_KEY, SAMPLE
from huurklaar_notifier.testing.fakes import FakePlatform


def _om(dag: int, uur: int, minuut: int = 0, seconde: int = 0) -> float:
    """Lokale tijd op een dag in november 2026; de verwachtingen hangen niet van een tijdzone af."""
    return time.mktime((2026, 11, dag, uur, minuut, seconde, 0, 0, -1))


def _datum(dag: int) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(_om(dag, 12)))


class NepKlok:
    def __init__(self, nu: float) -> None:
        self.nu = nu

    def __call__(self) -> float:
        return self.nu


def _item(i: int, soort: str = "task", te_laat: bool = False, vervalt: str | None = None) -> dict:
    return {
        **SAMPLE["items"][0],
        "id": f"item-{soort}-{i}",
        "kind": soort,
        "title": f"Taak {i}",
        "overdue": te_laat,
        "actionRequired": False,  # enkel de herinnering mag een melding geven
        "dueDate": vervalt,
    }


def _antwoord(*items: dict, te_laat: int | None = None, enabled: bool = True) -> dict:
    n_laat = sum(1 for i in items if i["overdue"]) if te_laat is None else te_laat
    return {
        **SAMPLE,
        "enabled": enabled,
        "items": list(items),
        "counts": {"total": len(items), "overdue": n_laat, "actionRequired": 0},
    }


@pytest.fixture
def klok():
    return NepKlok(_om(14, 10))


@pytest.fixture
def c(tmp_path, server, klok):
    ctl = Controller(FakePlatform(tmp_path), clock=klok)
    ctl.configure(server.url, FAKE_KEY)
    return ctl


def _titels(toasts) -> list[str]:
    return [t.title for t in toasts]


def test_voor_negen_uur_geen_herinnering_en_erna_wel(c, server, klok):
    server.body = _antwoord(_item(1, te_laat=True))
    klok.nu = _om(14, 8, 59)
    assert c.poll().toasts == []
    klok.nu = _om(14, REMINDER_HOUR)
    toasts = c.poll().toasts
    assert _titels(toasts) == ["Nog 1 te laat"]
    assert toasts[0].body == "Open Huurklaar om ze af te werken."
    assert toasts[0].url == "https://app.example.test/"
    assert (toasts[0].key, toasts[0].group) == ("reminder", "summary")


def test_enkel_te_laat_meervoud(c, server):
    server.body = _antwoord(_item(1, te_laat=True), _item(2, te_laat=True))
    assert _titels(c.poll().toasts) == ["Nog 2 te laat"]


def test_enkel_vandaag_enkelvoud_en_meervoud(c, server):
    server.body = _antwoord(_item(1, vervalt=_datum(14)))
    assert _titels(c.poll().toasts) == ["1 vervalt vandaag"]
    c.config.last_reminder = ""
    server.body = _antwoord(_item(1, vervalt=_datum(14)), _item(2, vervalt=_datum(14)))
    assert _titels(c.poll().toasts) == ["2 vervallen vandaag"]


def test_beide_samen(c, server):
    server.body = _antwoord(
        _item(1, te_laat=True), _item(2, vervalt=_datum(14)), _item(3, vervalt=_datum(15))
    )
    assert _titels(c.poll().toasts) == ["Nog 1 te laat · 1 vervalt vandaag"]


def test_te_laat_gebruikt_de_servertelling_ook_buiten_de_lijst(c, server):
    server.body = _antwoord(_item(1, te_laat=True), te_laat=7)
    assert _titels(c.poll().toasts) == ["Nog 7 te laat"]


def test_een_te_late_taak_van_vandaag_telt_enkel_als_te_laat(c, server):
    server.body = _antwoord(_item(1, te_laat=True, vervalt=_datum(14)))
    assert _titels(c.poll().toasts) == ["Nog 1 te laat"]


def test_twee_polls_op_dezelfde_dag_geven_er_een(c, server, klok):
    server.body = _antwoord(_item(1, te_laat=True))
    assert len(c.poll().toasts) == 1
    klok.nu += 3600
    assert c.poll().toasts == []


def test_de_volgende_dag_komt_er_weer_een(c, server, klok):
    server.body = _antwoord(_item(1, te_laat=True))
    assert len(c.poll().toasts) == 1
    klok.nu = _om(15, 8, 0)
    assert c.poll().toasts == []
    klok.nu = _om(15, 9, 1)
    assert _titels(c.poll().toasts) == ["Nog 1 te laat"]


def test_herinnering_komt_na_de_andere_meldingen(c, server):
    nieuw = {**_item(1), "title": "Nieuwe taak", "actionRequired": True}
    server.body = _antwoord(nieuw, _item(2, te_laat=True))
    assert _titels(c.poll().toasts) == ["Nieuwe taak", "Nog 1 te laat"]


def test_na_een_herstart_op_dezelfde_dag_geen_tweede(c, server, klok, tmp_path):
    server.body = _antwoord(_item(1, te_laat=True))
    assert len(c.poll().toasts) == 1
    assert c.config.last_reminder == _datum(14)
    nieuw = Controller(FakePlatform(tmp_path), clock=klok)
    nieuw.platform.secrets.set(FAKE_KEY)
    assert nieuw.config.last_reminder == _datum(14)
    assert nieuw.poll().toasts == []


def test_geen_herinnering_tijdens_een_pauze_wel_bij_de_eerste_poll_erna(c, server, klok):
    server.body = _antwoord(_item(1, te_laat=True))
    c.pause_for_hour()
    assert c.poll().toasts == []
    assert c.config.last_reminder == ""
    klok.nu += 3600
    assert _titels(c.poll().toasts) == ["Nog 1 te laat"]


def test_uitgeschakeld_geeft_geen_herinnering(c, server):
    c.toggle_reminder()
    assert c.config.daily_reminder is False
    server.body = _antwoord(_item(1, te_laat=True))
    assert c.poll().toasts == []
    assert c.config.last_reminder == ""


def test_zonder_iets_te_laat_of_vandaag_geen_herinnering_en_die_dag_ook_later_niet(c, server, klok):
    server.body = EMPTY
    assert c.poll().toasts == []
    klok.nu = _om(14, 14)
    server.body = _antwoord(_item(1, te_laat=True))  # later die dag verschijnt er iets
    assert c.poll().toasts == []
    klok.nu = _om(15, 9, 30)
    assert _titels(c.poll().toasts) == ["Nog 1 te laat"]


def test_uitgezette_soort_telt_niet_mee(c, server):
    c.toggle_kind("complaint")
    server.body = _antwoord(
        _item(1, "task", te_laat=True),
        _item(2, "complaint", te_laat=True),
        _item(3, "complaint", vervalt=_datum(14)),
        te_laat=2,
    )
    assert _titels(c.poll().toasts) == ["Nog 1 te laat"]


def test_enkel_uitgezette_soort_geeft_geen_herinnering(c, server):
    c.toggle_kind("complaint")
    server.body = _antwoord(_item(1, "complaint", te_laat=True))
    assert c.poll().toasts == []


def test_melding_uit_geeft_geen_herinnering_en_zet_last_reminder_niet(c, server):
    server.body = _antwoord(_item(1, te_laat=True), enabled=False)
    assert c.poll().toasts == []
    assert c.config.last_reminder == ""


def test_een_mislukte_poll_geeft_geen_herinnering(c, server):
    server.status = 500
    assert c.poll().toasts == []
    assert c.config.last_reminder == ""


def test_toggle_reminder_bewaart_en_wekt(c, tmp_path):
    c.wake.clear()
    c.toggle_reminder()
    assert c.wake.is_set() and c.view().daily_reminder is False
    assert Controller(FakePlatform(tmp_path)).config.daily_reminder is False
    c.toggle_reminder()
    assert c.view().daily_reminder is True


def test_next_local_time_is_strikt_na_nu():
    assert next_local_time(_om(14, 8, 59), 9) == _om(14, 9)
    assert next_local_time(_om(14, 9), 9) == _om(15, 9)
    assert next_local_time(_om(14, 23, 59), 9) == _om(15, 9)


def _state_met_interval(c, server, seconden: int) -> None:
    server.body = {**EMPTY, "pollAfterSeconds": seconden}
    c.state = State(rng=lambda _a, _b: 1.0)
    c.poll()


def test_next_delay_wordt_beperkt_tot_negen_uur(c, server, klok):
    _state_met_interval(c, server, 900)
    klok.nu = _om(14, 8, 59)
    assert c.next_delay() == 61.0
    c.config.daily_reminder = False
    assert c.next_delay() == 900.0


def test_next_delay_na_negen_uur_en_zonder_beperking_dichtbij(c, server, klok):
    _state_met_interval(c, server, 900)
    klok.nu = _om(14, 10)
    assert c.next_delay() == 900.0
    _state_met_interval(c, server, 6 * 3600)
    klok.nu = _om(14, 4)  # 5 uur voor 9:00: korter dan het serverinterval van 6 uur
    assert c.next_delay() == 5 * 3600 + 1.0
    klok.nu = _om(14, 23)  # 10 uur ervoor: het serverinterval blijft gelden
    assert c.next_delay() == 6 * 3600.0


def test_next_delay_zonder_instellingen_blijft_none(tmp_path):
    ctl = Controller(FakePlatform(tmp_path), clock=NepKlok(_om(14, 8, 59)))
    assert ctl.next_delay() is None
