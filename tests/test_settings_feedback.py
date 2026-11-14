"""Instellingenflow na Bewaren (KAN-265): de verbinding wordt getest en het resultaat getoond."""

import threading

import pytest

from huurklaar_notifier.core.api import ApiClient
from huurklaar_notifier.core.app_actions import AppActions
from huurklaar_notifier.core.controller import Controller
from huurklaar_notifier.core.i18n import translate
from huurklaar_notifier.testing.fake_server import EMPTY, FAKE_KEY, SAMPLE, FakeServer
from huurklaar_notifier.testing.fakes import FakePlatform

WACHT = 2  # seconden: threads in tests wachten nooit onbeperkt
LANG = "nl"


class NepUi:
    def __init__(self) -> None:
        self.alerts: list[str] = []
        self.rebuilds = 0
        self.answer: tuple[str, str] | None = None

    def open_url(self, url):
        pass

    def ask_settings(self, lang, base_url, key_saved):
        return self.answer

    def alert(self, message):
        self.alerts.append(message)

    def request_rebuild(self):
        self.rebuilds += 1

    def quit(self):
        pass


class TellendeFactory:
    """Telt de gemaakte clients: een client betekent dat er een netwerkaanvraag kan volgen."""

    def __init__(self) -> None:
        self.aantal = 0

    def __call__(self, base_url: str, key: str) -> ApiClient:
        self.aantal += 1
        return ApiClient(base_url, key)


@pytest.fixture
def ui():
    return NepUi()


@pytest.fixture
def factory():
    return TellendeFactory()


@pytest.fixture
def actions(tmp_path, ui, factory):
    controller = Controller(FakePlatform(tmp_path), client_factory=factory)
    return AppActions(controller, ui)


def _doe_settings(actions: AppActions) -> None:
    """Draait de flow op een eigen thread, zoals de app, en wacht met een time-out."""
    t = threading.Thread(target=actions.settings, daemon=True)
    t.start()
    t.join(timeout=WACHT * 3)
    assert not t.is_alive()


def _tekst(sleutel: str) -> str:
    return translate(LANG, sleutel)


def test_goed_antwoord_toont_verbonden_met_de_tellers(actions, ui, server):
    ui.answer = (server.url, FAKE_KEY)
    _doe_settings(actions)
    assert ui.alerts == [translate(LANG, "dialog.connected", detail="2 open, 1 te laat")]
    assert ui.alerts[0] == "Verbonden. 2 open, 1 te laat."


def test_geen_open_taken_toont_niets_te_doen(actions, ui, server):
    server.body = EMPTY
    ui.answer = (server.url, FAKE_KEY)
    _doe_settings(actions)
    assert ui.alerts == ["Verbonden. Niets te doen."]


def test_zonder_te_late_taken_staat_er_geen_te_laat(actions, ui, server):
    server.body = {**SAMPLE, "counts": {**SAMPLE["counts"], "overdue": 0}}
    ui.answer = (server.url, FAKE_KEY)
    _doe_settings(actions)
    assert ui.alerts == ["Verbonden. 2 open."]


def test_meldingen_tijdelijk_uit_wordt_vermeld(actions, ui, server):
    server.body = {**SAMPLE, "enabled": False}
    ui.answer = (server.url, FAKE_KEY)
    _doe_settings(actions)
    assert ui.alerts == ["Verbonden. Meldingen staan tijdelijk uit."]


def test_geweigerde_sleutel_toont_key_rejected(actions, ui, server):
    ui.answer = (server.url, "hkn_verkeerde_sleutel_123")
    _doe_settings(actions)
    assert ui.alerts == [_tekst("dialog.key_rejected")]


def test_onbereikbaar_adres_toont_unreachable(actions, ui):
    with FakeServer() as gesloten:
        adres = gesloten.url
    ui.answer = (adres, FAKE_KEY)
    _doe_settings(actions)
    assert ui.alerts == [_tekst("dialog.unreachable")]


def test_vreemd_antwoord_toont_unexpected(actions, ui, server):
    server.body = {"onbekend": True}
    ui.answer = (server.url, FAKE_KEY)
    _doe_settings(actions)
    assert ui.alerts == [_tekst("dialog.unexpected")]


def test_onverwachte_statuscode_toont_unexpected(actions, ui, server):
    server.status = 404
    ui.answer = (server.url, FAKE_KEY)
    _doe_settings(actions)
    assert ui.alerts == [_tekst("dialog.unexpected")]


def test_annuleren_doet_geen_aanvraag_en_toont_niets(actions, ui, server, factory):
    ui.answer = None
    _doe_settings(actions)
    assert ui.alerts == []
    assert factory.aantal == 0
    assert server.requests == []


@pytest.mark.parametrize(
    ("answer", "sleutel"),
    [
        (("http://geen-https.example.test", FAKE_KEY), "dialog.invalid_url"),
        (("", FAKE_KEY), "dialog.invalid_url"),
        (("https://api.example.test", "geen-sleutel"), "dialog.invalid_key"),
    ],
)
def test_ongeldige_invoer_toont_enkel_de_bestaande_melding(actions, ui, server, factory, answer, sleutel):
    ui.answer = answer
    _doe_settings(actions)
    assert ui.alerts == [translate(LANG, sleutel)]
    assert factory.aantal == 0
    assert server.requests == []


def test_zonder_sleutel_en_zonder_bewaarde_sleutel_geen_aanvraag(actions, ui, server, factory):
    ui.answer = (server.url, "")  # geen nieuwe sleutel en er is er geen bewaard
    _doe_settings(actions)
    assert ui.alerts == [translate(LANG, "dialog.invalid_key")]
    assert server.requests == []


def test_onverwachte_exceptie_toont_unexpected_en_de_flow_loopt_door(
    actions, ui, server, monkeypatch, caplog
):
    def kapot():
        raise RuntimeError("geheim adres hkn_xyz")

    monkeypatch.setattr(actions.c, "test_connection", kapot)
    ui.answer = (server.url, FAKE_KEY)
    with caplog.at_level("DEBUG"):
        _doe_settings(actions)
    assert ui.alerts == [_tekst("dialog.unexpected")]
    assert ui.rebuilds == 1  # de flow liep verder
    assert "geheim" not in caplog.text and "hkn_xyz" not in caplog.text
    assert "RuntimeError" in caplog.text
    # de settings-lock is weer vrij: een tweede keer lukt
    monkeypatch.undo()
    ui.alerts.clear()
    _doe_settings(actions)
    assert ui.alerts[0].startswith("Verbonden.")


def test_precies_een_boodschap_en_een_herbouw_na_bewaren(actions, ui, server):
    ui.answer = (server.url, FAKE_KEY)
    _doe_settings(actions)
    assert len(ui.alerts) == 1
    assert ui.rebuilds == 1


def test_de_test_wijzigt_de_toestand_van_de_poller_niet(actions, ui, server):
    ui.answer = (server.url, FAKE_KEY)
    _doe_settings(actions)
    assert actions.c.state.snapshot is None  # enkel de poller werkt de toestand bij
    assert actions.c.config.seen == []
