"""Meldingen pauzeren (KAN-283): nep-klok, geen meldingen tijdens de pauze, één samenvatting erna."""

import time

import pytest

from huurklaar_notifier.core.controller import Controller, tomorrow_morning
from huurklaar_notifier.core.state import Delivery, State
from huurklaar_notifier.testing.fake_server import EMPTY, FAKE_KEY, SAMPLE
from huurklaar_notifier.testing.fakes import FakePlatform

NU = time.mktime((2026, 11, 14, 10, 0, 0, 0, 0, -1))


class NepKlok:
    def __init__(self, nu: float = NU) -> None:
        self.nu = nu

    def __call__(self) -> float:
        return self.nu


def _item(i: int) -> dict:
    return {**SAMPLE["items"][0], "id": f"nieuw-{i}", "title": f"Nieuwe taak {i}"}


def _antwoord(n: int) -> dict:
    items = [_item(i) for i in range(n)]
    return {**SAMPLE, "items": items, "counts": {"total": n, "overdue": 0, "actionRequired": n}}


@pytest.fixture
def klok():
    return NepKlok()


@pytest.fixture
def c(tmp_path, server, klok):
    ctl = Controller(FakePlatform(tmp_path), clock=klok)
    ctl.configure(server.url, FAKE_KEY)
    return ctl


def test_geen_meldingen_tijdens_de_pauze_maar_seen_wordt_bijgewerkt(c, server):
    server.body = EMPTY
    c.poll()
    c.pause_for_hour()
    server.body = _antwoord(2)
    assert c.poll().toasts == []
    assert {"nieuw-0", "nieuw-1"} <= set(c.config.seen)
    assert c.state.missed == 2


def test_een_samenvatting_na_het_einde_van_de_pauze(c, server, klok):
    server.body = EMPTY
    c.poll()
    c.pause_for_hour()
    server.body = _antwoord(2)
    c.poll()
    klok.nu += 3600
    toasts = c.poll().toasts
    assert [t.title for t in toasts] == ["Tijdens de pauze: 2 nieuwe meldingen"]
    assert toasts[0].url == "https://app.example.test/"
    assert (toasts[0].key, toasts[0].group) == ("paused", "summary")
    assert c.state.missed == 0
    assert c.poll().toasts == []  # niet opnieuw


def test_geen_samenvatting_als_er_niets_gemist_is(c, server, klok):
    server.body = EMPTY
    c.poll()
    c.pause_for_hour()
    assert c.poll().toasts == []
    klok.nu += 3600
    assert c.poll().toasts == []


def test_pauze_loopt_nog_vlak_voor_het_einde(c, server, klok):
    server.body = EMPTY
    c.poll()
    c.pause_for_hour()
    server.body = _antwoord(1)
    klok.nu += 3599
    assert c.poll().toasts == []
    assert c.view().paused_until == NU + 3600
    klok.nu += 1
    assert [t.title for t in c.poll().toasts] == ["Tijdens de pauze: 1 nieuwe melding"]
    assert c.view().paused_until == 0.0


def test_hervatten_stopt_de_pauze_meteen(c, server):
    server.body = EMPTY
    c.poll()
    c.pause_for_hour()
    server.body = _antwoord(1)
    c.poll()
    c.wake.clear()
    c.resume()
    assert c.wake.is_set() and c.view().paused_until == 0.0
    assert [t.title for t in c.poll().toasts] == ["Tijdens de pauze: 1 nieuwe melding"]


def test_nieuw_in_de_eerste_poll_na_de_pauze_komt_gewoon_mee(c, server, klok):
    server.body = EMPTY
    c.poll()
    c.pause_for_hour()
    server.body = _antwoord(1)
    c.poll()
    server.body = _antwoord(2)  # nieuwe taak komt binnen vlak na de pauze
    klok.nu += 3600
    titels = [t.title for t in c.poll().toasts]
    assert titels == ["Tijdens de pauze: 1 nieuwe melding", "Nieuwe taak 1"]


def test_herstart_tijdens_de_pauze_houdt_de_pauze_aan(c, server, klok, tmp_path):
    server.body = EMPTY
    c.poll()
    c.pause_for_hour()
    nieuw = Controller(FakePlatform(tmp_path), clock=klok)
    nieuw.platform.secrets.set(FAKE_KEY)
    assert nieuw.config.paused_until == NU + 3600
    assert nieuw.view().paused_until == NU + 3600
    server.body = _antwoord(1)
    nieuw.config.base_url = server.url
    assert nieuw.poll().toasts == []


def test_pauze_tot_morgen_is_acht_uur_de_volgende_dag(c, klok):
    c.pause_until_tomorrow()
    lt = time.localtime(c.config.paused_until)
    assert (lt.tm_mday, lt.tm_hour, lt.tm_min) == (15, 8, 0)
    # ook net na middernacht: letterlijk 08:00 op de volgende kalenderdag
    nacht = time.mktime((2026, 11, 14, 0, 30, 0, 0, 0, -1))
    lt = time.localtime(tomorrow_morning(nacht))
    assert (lt.tm_mday, lt.tm_hour) == (15, 8)


def test_pauze_tot_morgen_over_maandgrens_en_zomeruur():
    for jaar, maand, dag in ((2026, 11, 30), (2026, 3, 28), (2026, 10, 24)):
        nu = time.mktime((jaar, maand, dag, 22, 0, 0, 0, 0, -1))
        lt = time.localtime(tomorrow_morning(nu))
        assert (lt.tm_hour, lt.tm_min) == (8, 0)
        assert 0 < tomorrow_morning(nu) - nu < 36 * 3600


def test_pauze_uitzetten_zonder_pauze_is_veilig(c):
    c.resume()
    assert c.config.paused_until == 0.0


def test_ander_account_wist_de_gemiste_teller(c, server):
    server.body = EMPTY
    c.poll()
    c.pause_for_hour()
    server.body = _antwoord(2)
    c.poll()
    assert c.state.missed == 2
    c.configure(server.url, "hkn_een_andere_sleutel_123")
    assert c.state.missed == 0


def test_uitgeschakelde_server_telt_niet_als_gemist(c, server):
    c.pause_for_hour()
    server.body = {**_antwoord(2), "enabled": False}
    assert c.poll().toasts == []
    assert c.state.missed == 0


def _met_interval(c, server, seconden=900):
    """Zet een server-interval en een rng die 1.0 geeft, zodat `next_delay` voorspelbaar is."""
    server.body = {**EMPTY, "pollAfterSeconds": seconden}
    c.state = State(rng=lambda _a, _b: 1.0)
    c.poll()


def test_next_delay_tijdens_pauze_is_tot_net_na_het_einde(c, server, klok):
    _met_interval(c, server)
    c.set_pause(klok.nu + 120)
    assert c.next_delay() == 121.0


def test_next_delay_blijft_het_interval_als_dat_korter_is(c, server, klok):
    _met_interval(c, server, 60)
    c.set_pause(klok.nu + 3600)
    assert c.next_delay() == 60.0


def test_next_delay_zonder_pauze_is_het_serverinterval(c, server):
    _met_interval(c, server)
    assert c.next_delay() == 900.0


def test_next_delay_met_verlopen_pauze_is_het_serverinterval(c, server, klok):
    _met_interval(c, server)
    c.set_pause(klok.nu - 10)
    assert c.next_delay() == 900.0


def test_next_delay_zonder_instellingen_is_none_ook_tijdens_pauze(tmp_path, klok):
    leeg = Controller(FakePlatform(tmp_path), clock=klok)
    leeg.set_pause(klok.nu + 120)
    assert leeg.next_delay() is None


def test_pauze_instellen_wekt_de_poller(c, klok):
    c.wake.clear()
    c.set_pause(klok.nu + 3600)
    assert c.wake.is_set()


def test_poll_na_de_pauze_levert_ook_een_lege_lijst_aan_de_ui(c, server, klok):
    """De poller geeft altijd het resultaat door (ook een lege `Delivery`) en `drain` herbouwt dan het menu."""
    import queue

    from huurklaar_notifier.core.app_actions import AppActions
    from huurklaar_notifier.testing.fakes import RecordingNotifier

    server.body = EMPTY
    c.poll()
    c.pause_for_hour()
    klok.nu += 3600
    q: queue.Queue = queue.Queue()
    q.put(c.poll())
    assert q.queue[0] == Delivery()
    assert AppActions(c, None).drain(q, RecordingNotifier()) is True  # type: ignore[arg-type]
    assert c.view().paused_until == 0.0


def test_intrekken_van_afgewerkte_meldingen_gaat_door_tijdens_de_pauze(c, server):
    server.body = _antwoord(1)
    assert [t.key for t in c.poll().toasts] == ["nieuw-0"]
    c.pause_for_hour()
    server.body = EMPTY  # de taak is afgewerkt
    delivery = c.poll()
    assert delivery.toasts == [] and delivery.withdraw == ["nieuw-0"]
