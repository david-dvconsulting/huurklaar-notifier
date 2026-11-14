"""De koppellink `huurklaar-meldingen://koppel?api=...&key=...` (KAN-267): parsen, de host tonen en de bevestigingsflow."""

import threading
from urllib.parse import quote

import pytest

from huurklaar_notifier.core.app_actions import AppActions
from huurklaar_notifier.core.controller import Controller
from huurklaar_notifier.core.i18n import translate
from huurklaar_notifier.core.link import SCHEME, link_host, parse_link
from huurklaar_notifier.testing.fake_server import FAKE_KEY
from huurklaar_notifier.testing.fakes import FakePlatform

SLEUTEL = "hkn_nep_sleutel_voor_tests"
API = "https://api.example.com/v1"
WACHT = 2  # seconden: threads in tests wachten nooit onbeperkt


def maak_link(api: str = API, key: str = SLEUTEL, schema: str = SCHEME, pad: str = "koppel") -> str:
    return f"{schema}://{pad}?api={quote(api, safe='')}&key={key}"


class LinkUi:
    """Nep-UI voor `apply_link`: `confirm` geeft een vooraf ingesteld antwoord en bewaart de vragen."""

    def __init__(self, antwoord: bool = True, fout: Exception | None = None) -> None:
        self.antwoord = antwoord
        self.fout = fout
        self.vragen: list[str] = []
        self.alerts: list[str] = []
        self.rebuilds = 0
        self.gevraagd = 0  # aantal keer dat het instellingenvenster openging

    def open_url(self, url):
        pass

    def ask_settings(self, lang, base_url, key_saved):
        self.gevraagd += 1
        return None

    def confirm(self, message):
        self.vragen.append(message)
        if self.fout is not None:
            raise self.fout
        return self.antwoord

    def alert(self, message):
        self.alerts.append(message)

    def request_rebuild(self):
        self.rebuilds += 1

    def quit(self):
        pass


@pytest.fixture
def ui():
    return LinkUi()


@pytest.fixture
def controller(tmp_path):
    return Controller(FakePlatform(tmp_path))


@pytest.fixture
def acties(controller, ui):
    return AppActions(controller, ui)


# -- parse_link ---------------------------------------------------------------------------------
def test_geldige_link_met_pad_en_gecodeerd_adres():
    assert parse_link(maak_link()) == (API, SLEUTEL)


def test_geldige_link_met_lokale_http_op_localhost():
    assert parse_link(maak_link("http://localhost:3000")) == ("http://localhost:3000", SLEUTEL)


def test_geldige_link_met_lokale_http_op_127_0_0_1():
    assert parse_link(maak_link("http://127.0.0.1:3000")) == ("http://127.0.0.1:3000", SLEUTEL)


def test_schema_in_hoofdletters_is_geldig():
    assert parse_link(maak_link(schema="HUURKLAAR-MELDINGEN")) == (API, SLEUTEL)


def test_slash_na_koppel_is_geldig():
    assert parse_link(f"{SCHEME}://koppel/?api={quote(API, safe='')}&key={SLEUTEL}") == (API, SLEUTEL)


@pytest.mark.parametrize(
    "url",
    [
        pytest.param(f"https://koppel?api={quote(API, safe='')}&key={SLEUTEL}", id="ander-schema"),
        pytest.param(maak_link(pad="anders"), id="andere-host"),
        pytest.param(
            f"{SCHEME}://user@koppel?api={quote(API, safe='')}&key={SLEUTEL}", id="gebruiker-voor-koppel"
        ),
        pytest.param(f"{SCHEME}://koppel:123?api={quote(API, safe='')}&key={SLEUTEL}", id="poort-op-koppel"),
        pytest.param(f"{SCHEME}://koppel/x?api={quote(API, safe='')}&key={SLEUTEL}", id="pad-/x"),
        pytest.param(f"{SCHEME}://koppel?api={quote(API, safe='')}", id="ontbrekende-key"),
        pytest.param(f"{SCHEME}://koppel?key={SLEUTEL}", id="ontbrekende-api"),
        pytest.param(f"{maak_link()}&key={SLEUTEL}", id="dubbele-key"),
        pytest.param(f"{maak_link()}&extra=1", id="extra-parameter"),
        pytest.param(f"{maak_link()}#fragment", id="fragment"),
        pytest.param(f"{maak_link()}#", id="losse-hash"),
        pytest.param(maak_link("http://api.example.com/v1"), id="http-naar-niet-lokaal"),
        pytest.param(
            maak_link("https://gebruiker:geheim@api.example.com/v1"), id="api-met-gebruikersgegevens"
        ),
        pytest.param(maak_link("https://api.example.com/v1?x=1"), id="api-met-query"),
        pytest.param(maak_link(key="nep_sleutel_voor_tests"), id="sleutel-zonder-hkn"),
        pytest.param(maak_link(key="hkn_nep+sleutel_voor_tests"), id="sleutel-met-plus"),
        pytest.param(
            f"{SCHEME}://koppel?api={quote(API, safe='')}&key=hkn_nep%20sleutel_voor_tests",
            id="sleutel-met-spatie",
        ),
        pytest.param("", id="lege-string"),
        pytest.param(f"{SCHEME}://koppel?" + "x" * 2048, id="te-lange-url"),
        pytest.param(None, id="geen-str-none"),
        pytest.param(123, id="geen-str-getal"),
    ],
)
def test_ongeldige_link_geeft_none(url):
    assert parse_link(url) is None


def test_ongeldige_poort_geeft_none_zonder_exceptie():
    assert parse_link(maak_link("https://api.example.com:99999/v1")) is None


# -- link_host ----------------------------------------------------------------------------------
def test_link_host_toont_de_hostnaam():
    assert link_host("https://api.example.com/v1") == "api.example.com"


def test_link_host_toont_de_poort():
    assert link_host("http://localhost:3000") == "localhost:3000"


def test_link_host_zet_ipv6_tussen_haken_met_poort():
    assert link_host("http://[::1]:3000") == "[::1]:3000"


def test_link_host_toont_nooit_gebruikersgegevens():
    assert link_host("https://gebruiker:geheim@api.example.com:8443/v1") == "api.example.com:8443"


# -- apply_link ---------------------------------------------------------------------------------
def test_bevestigd_bewaart_adres_en_sleutel_en_toont_de_verbindingstest(acties, controller, ui, server):
    acties.apply_link(maak_link(server.url, FAKE_KEY))
    assert controller.config.base_url == server.url
    assert controller.platform.secrets.get() == FAKE_KEY
    assert ui.rebuilds == 1
    # Zelfde boodschap als na Bewaren (KAN-265).
    assert ui.alerts == [translate("nl", "dialog.connected", detail="2 open, 1 te laat")]


def test_geweigerde_sleutel_na_koppelen_toont_key_rejected(acties, ui, server):
    acties.apply_link(maak_link(server.url, "hkn_verkeerde_sleutel_123"))
    assert ui.alerts == [translate("nl", "dialog.key_rejected")]


def test_de_vraag_bevat_de_host_en_niet_de_sleutel(acties, ui):
    ui.antwoord = False  # enkel de vraag telt; geen verbindingstest naar het verzonnen adres
    acties.apply_link(maak_link())
    assert len(ui.vragen) == 1
    vraag = ui.vragen[0]
    assert "api.example.com" in vraag
    assert SLEUTEL not in vraag
    assert "https://" not in vraag


def test_geweigerd_wijzigt_niets(acties, controller, ui):
    ui.antwoord = False
    acties.apply_link(maak_link())
    assert len(ui.vragen) == 1
    assert controller.config.base_url == ""
    assert controller.platform.secrets.get() is None
    assert ui.rebuilds == 0


def test_ongeldige_link_toont_de_foutmelding_zonder_vraag(acties, controller, ui):
    acties.apply_link(maak_link("http://api.example.com/v1"))
    assert ui.vragen == []
    assert ui.alerts == [translate("nl", "dialog.invalid_link")]
    assert controller.config.base_url == ""
    assert controller.platform.secrets.get() is None
    assert ui.rebuilds == 0


def test_bezet_lock_vraagt_niets_en_wijzigt_niets(acties, controller, ui):
    assert acties._settings_lock.acquire(blocking=False)
    try:
        acties.apply_link(maak_link())
    finally:
        acties._settings_lock.release()
    assert ui.vragen == []
    assert ui.alerts == []
    assert controller.config.base_url == ""
    assert controller.platform.secrets.get() is None


def test_lock_wordt_vrijgegeven_na_een_geweigerde_link(acties, ui):
    ui.antwoord = False
    acties.apply_link(maak_link())
    assert acties._settings_lock.acquire(blocking=False)
    acties._settings_lock.release()


def test_onverwachte_fout_gooit_niet_door_en_logt_enkel_het_type(acties, controller, ui, caplog):
    ui.fout = RuntimeError("geheim " + SLEUTEL + " " + API)
    acties.apply_link(maak_link())  # mag geen exceptie naar buiten gooien
    assert "RuntimeError" in caplog.text
    assert SLEUTEL not in caplog.text
    assert API not in caplog.text
    assert "api.example.com" not in caplog.text
    assert "geheim" not in caplog.text
    assert controller.config.base_url == ""
    assert acties._settings_lock.acquire(blocking=False)  # lock is vrijgegeven
    acties._settings_lock.release()


# -- koppellink en eerste start ------------------------------------------------------------------
def test_link_telt_als_eerste_start(acties, ui):
    ui.antwoord = False
    acties.apply_link(maak_link())
    assert acties.first_run() is None  # geen instellingenvenster meer na een link
    assert ui.gevraagd == 0


def test_link_tijdens_de_eerste_start_verdringt_de_koppelvraag_niet(acties, controller, ui, monkeypatch):
    """Koude start via de link: de eerste start leest nog de sleutelopslag als de link binnenkomt."""
    controller.config.base_url = API  # met een adres leest de eerste start de sleutelopslag
    binnen, verder = threading.Event(), threading.Event()
    echt = controller.platform.secrets.get

    def traag():
        binnen.set()
        assert verder.wait(timeout=WACHT)
        return echt()

    monkeypatch.setattr(controller.platform.secrets, "get", traag)
    thread = acties.first_run()
    assert thread is not None
    assert binnen.wait(timeout=WACHT)
    ui.antwoord = False
    acties.apply_link(maak_link())  # de koppelvraag komt, de gebruiker weigert
    verder.set()
    thread.join(timeout=WACHT)
    assert not thread.is_alive()
    assert len(ui.vragen) == 1
    assert ui.gevraagd == 0  # het instellingenvenster opende niet na de link


def test_eerste_start_wacht_op_een_koppellink_en_opent_dan_niets(controller, ui):
    """Mac, koude start via de link: het Apple Event komt pas na de eerste tik binnen."""
    acties = AppActions(controller, ui, first_run_delay=WACHT * 5)  # lang: de link moet het wachten afbreken
    thread = acties.first_run()
    assert thread is not None
    ui.antwoord = False
    acties.apply_link(maak_link())
    thread.join(timeout=WACHT)
    assert not thread.is_alive()  # de link brak het wachten af
    assert len(ui.vragen) == 1
    assert ui.gevraagd == 0


def test_eerste_start_zonder_link_opent_de_instellingen_na_het_wachten(controller, ui):
    acties = AppActions(controller, ui, first_run_delay=0.05)
    thread = acties.first_run()
    assert thread is not None
    thread.join(timeout=WACHT)
    assert not thread.is_alive()
    assert ui.gevraagd == 1
