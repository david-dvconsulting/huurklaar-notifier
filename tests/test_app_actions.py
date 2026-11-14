"""Gedeelde menu-acties en instellingenflow (NTF-07), met een nep-`ui` en het nep-platform."""

import queue
import threading

import pytest

from huurklaar_notifier.core.api import InvalidKeyError, InvalidUrlError
from huurklaar_notifier.core.app_actions import AppActions
from huurklaar_notifier.core.controller import Controller
from huurklaar_notifier.core.i18n import translate
from huurklaar_notifier.core.menu import AUTOSTART, LANGUAGE_PREFIX, QUIT, REFRESH, SETTINGS, Entry
from huurklaar_notifier.core.state import Toast
from huurklaar_notifier.testing.fake_server import FAKE_KEY
from huurklaar_notifier.testing.fakes import FakePlatform, RecordingNotifier

WACHT = 2  # seconden: threads in tests wachten nooit onbeperkt


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
    q: queue.Queue[list[Toast]] = queue.Queue()
    q.put([Toast("Titel", "Tekst", "https://app.example.test/1")])
    q.put([Toast("Twee", "Tekst", None)])
    notifier = RecordingNotifier()
    acties = AppActions(None, NepUi())  # type: ignore[arg-type]
    assert acties.drain(q, notifier) is True
    assert notifier.sent == [
        ("Titel", "Tekst", "https://app.example.test/1"),
        ("Twee", "Tekst", None),
    ]
    assert q.empty()


def test_drain_met_lege_lijst_herbouwt_toch():
    q: queue.Queue[list[Toast]] = queue.Queue()
    q.put([])  # update gevonden: geen meldingen, wel herbouwen
    notifier = RecordingNotifier()
    assert AppActions(None, NepUi()).drain(q, notifier) is True  # type: ignore[arg-type]
    assert notifier.sent == []


def test_drain_met_lege_queue_herbouwt_niet():
    notifier = RecordingNotifier()
    assert AppActions(None, NepUi()).drain(queue.Queue(), notifier) is False  # type: ignore[arg-type]
    assert notifier.sent == []


# -- instellingen ---------------------------------------------------------------------------------
def test_instellingen_bewaren_adres_en_sleutel(acties, controller, ui, server):
    ui.answer = (server.url, FAKE_KEY)
    acties.settings()
    assert controller.config.base_url == server.url
    assert controller.platform.secrets.get() == FAKE_KEY
    assert ui.alerts == [] and ui.rebuilds == 1
    assert ui.asked == [("nl", "", False)]


def test_lege_sleutel_houdt_de_bewaarde_sleutel(acties, controller, ui, server):
    controller.configure(server.url, FAKE_KEY)
    ui.answer = (server.url, "")
    acties.settings()
    assert controller.platform.secrets.get() == FAKE_KEY
    assert ui.alerts == []
    assert ui.asked[0][2] is True  # de ui weet dat er al een sleutel bewaard is


def test_geen_bewaarde_sleutel_wordt_doorgegeven_als_false(acties, ui):
    acties.settings()
    assert ui.asked[0][2] is False


def test_annuleren_wijzigt_niets_en_herbouwt_niet(acties, controller, ui):
    ui.answer = None
    acties.settings()
    assert controller.config.base_url == "" and controller.platform.secrets.get() is None
    assert ui.alerts == [] and ui.rebuilds == 0


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
