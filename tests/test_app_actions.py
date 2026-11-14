"""Gedeelde menu-acties en instellingenflow (NTF-07), met een nep-`ui` en het nep-platform."""

import queue
import threading

import pytest

from huurklaar_notifier.core.api import InvalidKeyError, InvalidUrlError
from huurklaar_notifier.core.app_actions import AppActions
from huurklaar_notifier.core.config import ConfigStore
from huurklaar_notifier.core.controller import Controller, tomorrow_morning
from huurklaar_notifier.core.defaults import DEFAULT_BASE_URL
from huurklaar_notifier.core.i18n import translate
from huurklaar_notifier.core.menu import (
    AUTOSTART,
    KIND_PREFIX,
    LANGUAGE_PREFIX,
    PAUSE_PREFIX,
    QUIT,
    REFRESH,
    REMINDER,
    SETTINGS,
    Entry,
)
from huurklaar_notifier.core.state import Delivery, Toast
from huurklaar_notifier.testing.fake_server import FAKE_KEY
from huurklaar_notifier.testing.fakes import FakePlatform, RecordingNotifier

WACHT = 2  # seconden: threads in tests wachten nooit onbeperkt
VERBONDEN = "Verbonden. 2 open, 1 te laat."  # de tellers van SAMPLE in de nep-server


class NepUi:
    def __init__(self) -> None:
        self.opened: list[str] = []
        self.alerts: list[str] = []
        self.rebuilds = 0
        self.quits = 0
        self.answer: tuple[str, str] | None = None
        self.asked: list[tuple[str, str, bool]] = []
        self.entered = threading.Event()  # gezet zodra ask_settings is binnengegaan
        self.release: threading.Event | None = None  # als gezet, wacht ask_settings hierop

    def open_url(self, url):
        self.opened.append(url)

    def ask_settings(self, lang, base_url, key_saved):
        self.asked.append((lang, base_url, key_saved))
        self.entered.set()
        if self.release is not None:
            assert self.release.wait(timeout=WACHT)
        return self.answer

    def alert(self, message):
        self.alerts.append(message)

    def request_rebuild(self):
        self.rebuilds += 1

    def quit(self):
        self.quits += 1


@pytest.fixture
def ui():
    return NepUi()


@pytest.fixture
def controller(tmp_path):
    return Controller(FakePlatform(tmp_path))


@pytest.fixture
def acties(controller, ui):
    return AppActions(controller, ui)


# -- handle ---------------------------------------------------------------------------------------
def test_url_opent_via_de_ui(acties, ui):
    acties.handle(Entry("Open", url="https://app.example.test/x"))
    assert ui.opened == ["https://app.example.test/x"]


def test_refresh_wekt_de_poller(acties, controller):
    assert not controller.wake.is_set()
    acties.handle(Entry("Vernieuwen", action=REFRESH))
    assert controller.wake.is_set()


def test_autostart_wisselt_en_vraagt_herbouwen(acties, controller, ui):
    acties.handle(Entry("Start", action=AUTOSTART))
    assert controller.platform.autostart.enabled is True
    acties.handle(Entry("Start", action=AUTOSTART))
    assert controller.platform.autostart.enabled is False
    assert ui.rebuilds == 2


def test_taal_wordt_bewaard_en_vraagt_herbouwen(acties, controller, ui):
    acties.handle(Entry("FR", action=LANGUAGE_PREFIX + "fr"))
    assert controller.config.language == "fr"
    assert ui.rebuilds == 1


def test_quit_roept_de_ui_aan(acties, ui):
    acties.handle(Entry("Stop", action=QUIT))
    assert ui.quits == 1


def test_onbekende_actie_en_label_zonder_actie_doen_niets(acties, ui):
    acties.handle(Entry("Onbekend", action="iets-nieuws"))
    acties.handle(Entry("Titel"))
    assert (ui.opened, ui.rebuilds, ui.quits, ui.alerts) == ([], 0, 0, [])


def test_instellingen_starten_op_een_daemon_thread(acties, ui):
    ui.release = threading.Event()
    acties.handle(Entry("Instellingen", action=SETTINGS))
    try:
        assert ui.entered.wait(timeout=WACHT)
        threads = [t for t in threading.enumerate() if t.name == "settings"]
        assert len(threads) == 1 and threads[0].daemon
    finally:
        ui.release.set()
        for t in threading.enumerate():
            if t.name == "settings":
                t.join(timeout=WACHT)


# -- drain ----------------------------------------------------------------------------------------
def test_drain_stuurt_toasts_door_en_vraagt_herbouwen():
    q: queue.Queue[Delivery] = queue.Queue()
    q.put(Delivery([Toast("Titel", "Tekst", "https://app.example.test/1", "task-1", "task")]))
    q.put(Delivery([Toast("Twee", "Tekst", None, "task-2", "task")]))
    notifier = RecordingNotifier()
    acties = AppActions(None, NepUi())  # type: ignore[arg-type]
    assert acties.drain(q, notifier) is True
    assert notifier.sent == [
        ("Titel", "Tekst", "https://app.example.test/1"),
        ("Twee", "Tekst", None),
    ]
    assert [t.key for t in notifier.toasts] == ["task-1", "task-2"]
    assert q.empty()


def test_drain_trekt_in_voor_het_tonen():
    q: queue.Queue[Delivery] = queue.Queue()
    q.put(Delivery([Toast("Titel", "Tekst", None, "task-2", "task")], ["task-1"]))
    gebeurtenissen: list[str] = []

    class Volgorde(RecordingNotifier):
        def notify(self, toast):
            gebeurtenissen.append("notify")
            super().notify(toast)

        def withdraw(self, keys):
            gebeurtenissen.append("withdraw")
            super().withdraw(keys)

    notifier = Volgorde()
    assert AppActions(None, NepUi()).drain(q, notifier) is True  # type: ignore[arg-type]
    assert gebeurtenissen == ["withdraw", "notify"]
    assert notifier.withdrawn == ["task-1"]


def test_drain_met_lege_delivery_herbouwt_toch():
    q: queue.Queue[Delivery] = queue.Queue()
    q.put(Delivery())  # update gevonden: geen meldingen, wel herbouwen
    notifier = RecordingNotifier()
    assert AppActions(None, NepUi()).drain(q, notifier) is True  # type: ignore[arg-type]
    assert notifier.sent == [] and notifier.withdrawn == []


def test_drain_met_lege_queue_herbouwt_niet():
    notifier = RecordingNotifier()
    assert AppActions(None, NepUi()).drain(queue.Queue(), notifier) is False  # type: ignore[arg-type]
    assert notifier.sent == [] and notifier.withdrawn == []


# -- instellingen ---------------------------------------------------------------------------------
def test_instellingen_bewaren_adres_en_sleutel(acties, controller, ui, server):
    ui.answer = (server.url, FAKE_KEY)
    acties.settings()
    assert controller.config.base_url == server.url
    assert controller.platform.secrets.get() == FAKE_KEY
    # Na Bewaren test de app de verbinding en toont ze precies één boodschap (KAN-265).
    assert ui.alerts == [VERBONDEN] and ui.rebuilds == 1
    assert ui.asked == [("nl", DEFAULT_BASE_URL, False)]


def test_lege_sleutel_houdt_de_bewaarde_sleutel(acties, controller, ui, server):
    controller.configure(server.url, FAKE_KEY)
    ui.answer = (server.url, "")
    acties.settings()
    assert controller.platform.secrets.get() == FAKE_KEY
    assert ui.alerts == [VERBONDEN]
    assert ui.asked[0][2] is True  # de ui weet dat er al een sleutel bewaard is


def test_geen_bewaarde_sleutel_wordt_doorgegeven_als_false(acties, ui):
    acties.settings()
    assert ui.asked[0][2] is False


def test_leeg_bewaard_adres_stelt_het_productieadres_voor(acties, controller, ui):
    assert controller.config.base_url == ""
    acties.settings()
    assert ui.asked[0][1] == DEFAULT_BASE_URL


def test_bewaard_adres_wordt_ongewijzigd_voorgesteld(acties, controller, ui, server):
    controller.configure(server.url, FAKE_KEY)
    ui.answer = None
    acties.settings()
    assert ui.asked[0][1] == server.url


def test_annuleren_wijzigt_niets_en_herbouwt_niet(acties, controller, ui, tmp_path):
    ui.answer = None
    acties.settings()
    assert controller.config.base_url == "" and controller.platform.secrets.get() is None
    assert ui.alerts == [] and ui.rebuilds == 0
    assert not (tmp_path / "config.json").exists()
    assert ConfigStore(tmp_path).load().base_url == ""


def test_ongeldig_adres_toont_de_adresmelding(acties, ui):
    ui.answer = ("ftp://x.be", FAKE_KEY)
    acties.settings()
    assert ui.alerts == [translate("nl", "dialog.invalid_url")]
    assert ui.rebuilds == 1


def test_adres_dat_urlsplit_weigert_toont_de_adresmelding(acties, ui):
    # urlsplit werpt hier zelf een gewone ValueError; die mag de instellingen-thread niet stil laten sterven.
    ui.answer = ("https://[::1", FAKE_KEY)
    acties.settings()
    assert ui.alerts == [translate("nl", "dialog.invalid_url")]
    assert ui.rebuilds == 1


def test_ongeldige_sleutel_toont_de_sleutelmelding(acties, ui, server):
    ui.answer = (server.url, "abc")
    acties.settings()
    assert ui.alerts == [translate("nl", "dialog.invalid_key")]


def test_lege_sleutel_zonder_bewaarde_sleutel_toont_de_sleutelmelding(acties, ui, server):
    ui.answer = (server.url, "")
    acties.settings()
    assert ui.alerts == [translate("nl", "dialog.invalid_key")]


@pytest.mark.parametrize(
    ("fout", "sleutel"),
    [
        (InvalidUrlError("tekst zonder het woord"), "dialog.invalid_url"),
        (InvalidKeyError("adres https"), "dialog.invalid_key"),
    ],
)
def test_melding_hangt_van_het_type_af_niet_van_de_tekst(acties, controller, ui, monkeypatch, fout, sleutel):
    def configureer(url, key):
        raise fout

    monkeypatch.setattr(controller, "configure", configureer)
    ui.answer = ("https://x.example.test", FAKE_KEY)
    acties.settings()
    assert ui.alerts == [translate("nl", sleutel)]


def test_tweede_instellingenvenster_opent_niet_zolang_het_eerste_open_staat(acties, ui):
    ui.release = threading.Event()
    eerste = threading.Thread(target=acties.settings, daemon=True)
    eerste.start()
    try:
        assert ui.entered.wait(timeout=WACHT)
        acties.settings()  # tweede klik: keert meteen terug zonder dialoog
        assert len(ui.asked) == 1
    finally:
        ui.release.set()
        eerste.join(timeout=WACHT)
    assert not eerste.is_alive()
    acties.settings()  # na afloop kan het weer
    assert len(ui.asked) == 2


def test_lock_wordt_vrijgegeven_na_een_fout_in_de_dialoog(acties, ui):
    def stuk(*a):
        raise RuntimeError("dialoog crasht")

    ui.ask_settings = stuk  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        acties.settings()
    ui.ask_settings = NepUi.ask_settings.__get__(ui)  # type: ignore[method-assign]
    acties.settings()
    assert len(ui.asked) == 1


# -- pauzeren (KAN-283) ---------------------------------------------------------------------------
def test_pauze_uur_zet_de_pauze_en_vraagt_herbouwen(tmp_path, ui):
    c = Controller(FakePlatform(tmp_path), clock=lambda: 1000.0)
    AppActions(c, ui).handle(Entry("1 uur", action=PAUSE_PREFIX + "hour"))
    assert c.config.paused_until == 4600.0
    assert ui.rebuilds == 1


def test_pauze_tot_morgen_zet_de_pauze_op_tomorrow_morning(tmp_path, ui):
    nu = 1_700_000_000.0
    c = Controller(FakePlatform(tmp_path), clock=lambda: nu)
    AppActions(c, ui).handle(Entry("Morgen", action=PAUSE_PREFIX + "tomorrow"))
    assert c.config.paused_until == tomorrow_morning(nu)
    assert ui.rebuilds == 1


def test_pauze_uit_hervat_en_wekt_de_poller(tmp_path, ui):
    c = Controller(FakePlatform(tmp_path), clock=lambda: 1000.0)
    c.set_pause(5000.0)
    AppActions(c, ui).handle(Entry("Hervatten", action=PAUSE_PREFIX + "off"))
    assert c.config.paused_until == 0.0 and c.wake.is_set()
    assert ui.rebuilds == 1


def test_onbekende_pauzekeuze_doet_niets(tmp_path, ui):
    c = Controller(FakePlatform(tmp_path), clock=lambda: 1000.0)
    AppActions(c, ui).handle(Entry("?", action=PAUSE_PREFIX + "week"))
    assert c.config.paused_until == 0.0 and ui.rebuilds == 0


# -- meldingen per soort (KAN-284) ---------------------------------------------------------------
def test_kind_zet_en_wist_de_soort_en_vraagt_herbouwen(tmp_path, ui):
    c = Controller(FakePlatform(tmp_path), clock=lambda: 1000.0)
    acties = AppActions(c, ui)
    acties.handle(Entry("Klacht", action=KIND_PREFIX + "complaint"))
    assert c.config.muted_kinds == ["complaint"] and ui.rebuilds == 1
    acties.handle(Entry("Klacht", action=KIND_PREFIX + "complaint"))
    assert c.config.muted_kinds == [] and ui.rebuilds == 2


# -- dagelijkse herinnering (KAN-285) ----------------------------------------------------------------
def test_reminder_wisselt_het_vinkje_en_vraagt_herbouwen(tmp_path, ui):
    c = Controller(FakePlatform(tmp_path), clock=lambda: 1000.0)
    acties = AppActions(c, ui)
    acties.handle(Entry("Dagelijkse herinnering", action=REMINDER))
    assert c.config.daily_reminder is False and ui.rebuilds == 1
    acties.handle(Entry("Dagelijkse herinnering", action=REMINDER))
    assert c.config.daily_reminder is True and ui.rebuilds == 2


# -- eerste start ---------------------------------------------------------------------------------
def test_eerste_start_zonder_instellingen_opent_de_flow_een_keer(acties, ui):
    thread = acties.first_run()
    assert thread is not None
    thread.join(timeout=WACHT)
    assert not thread.is_alive()
    assert len(ui.asked) == 1 and ui.asked[0][1] == DEFAULT_BASE_URL


def test_eerste_start_met_adres_zonder_sleutel_opent_de_flow(acties, controller, ui, server):
    controller.config.base_url = server.url
    thread = acties.first_run()
    assert thread is not None
    thread.join(timeout=WACHT)
    assert not thread.is_alive()
    assert len(ui.asked) == 1 and ui.asked[0][1] == server.url


def test_eerste_start_met_adres_en_sleutel_opent_niets(acties, controller, ui, server):
    controller.configure(server.url, FAKE_KEY)
    thread = acties.first_run()
    assert thread is not None
    thread.join(timeout=WACHT)
    assert not thread.is_alive()
    assert ui.asked == []


def test_eerste_start_gebeurt_hoogstens_een_keer(acties, ui):
    eerste = acties.first_run()
    assert acties.first_run() is None  # tweede oproep start niets
    assert eerste is not None
    eerste.join(timeout=WACHT)
    assert len(ui.asked) == 1
