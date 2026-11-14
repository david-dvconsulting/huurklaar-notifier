"""Controller: de lock mag nooit vastgehouden worden tijdens de netwerkaanvraag (NTF-04)."""

import threading
import time

import pytest

from huurklaar_notifier.core.api import ApiClient, ApiError
from huurklaar_notifier.core.controller import Controller
from huurklaar_notifier.core.state import NotConfigured, State, Status
from huurklaar_notifier.testing.fake_server import FAKE_KEY
from huurklaar_notifier.testing.fakes import FakePlatform

ANTWOORD_BINNEN = 0.1  # seconden: de UI-thread mag nooit langer wachten


class TrageClient:
    """Echte client met een vertraging in `fetch`; `gestart` meldt dat de aanvraag loopt."""

    def __init__(self, base_url: str, key: str, gestart: threading.Event, vrijgeven: threading.Event) -> None:
        self._echt = ApiClient(base_url, key)
        self._gestart = gestart
        self._vrijgeven = vrijgeven

    def fetch(self):
        self._gestart.set()
        self._vrijgeven.wait(timeout=1.0)  # de test geeft vrij, of na 1 s vanzelf
        return self._echt.fetch()


@pytest.fixture
def trage(tmp_path, server):
    gestart, vrijgeven = threading.Event(), threading.Event()
    c = Controller(
        FakePlatform(tmp_path),
        client_factory=lambda url, key: TrageClient(url, key, gestart, vrijgeven),
    )
    c.configure(server.url, FAKE_KEY)
    c.gestart, c.vrijgeven = gestart, vrijgeven
    return c


def _poll_in_thread(c: Controller) -> tuple[threading.Thread, list]:
    uit: list = []
    t = threading.Thread(target=lambda: uit.append(c.poll()), daemon=True)
    t.start()
    assert c.gestart.wait(timeout=2), "de fetch is niet gestart"
    return t, uit


def _duur(f) -> float:
    start = time.perf_counter()
    f()
    return time.perf_counter() - start


def test_update_antwoordt_snel_tijdens_een_trage_fetch(trage):
    t, _ = _poll_in_thread(trage)
    try:
        assert _duur(lambda: trage.update) < ANTWOORD_BINNEN
    finally:
        trage.vrijgeven.set()
        t.join(timeout=5)
    assert not t.is_alive()


def test_view_antwoordt_snel_tijdens_een_trage_fetch(trage):
    t, _ = _poll_in_thread(trage)
    try:
        assert _duur(trage.view) < ANTWOORD_BINNEN
        assert trage.view().state.status is Status.NOT_CONFIGURED  # nog niets verwerkt
    finally:
        trage.vrijgeven.set()
        t.join(timeout=5)
    assert not t.is_alive()


def test_view_is_een_kopie_en_geeft_taal_en_update(controller):
    controller.poll()
    v = controller.view()
    assert v.state is not controller.state
    assert v.state.status is controller.state.status is Status.ATTENTION
    assert v.language == controller.language
    assert v.language_setting == controller.config.language
    assert v.update is None
    controller.state.status = Status.OFFLINE
    assert v.state.status is Status.ATTENTION  # latere wijziging raakt de kopie niet


def test_view_geeft_een_bekende_update(tmp_path, server):
    c = Controller(FakePlatform(tmp_path), current_version="1.0.0")
    c.config.update_version = "9.9.9"
    assert c.view().update is not None and c.view().update.version == "9.9.9"


def test_poll_na_trage_fetch_geeft_nog_altijd_de_melding(trage):
    t, uit = _poll_in_thread(trage)
    trage.vrijgeven.set()
    t.join(timeout=5)
    assert [x.title for x in uit[0]] == ["Indexatie nakijken"]
    assert "task-1" in trage.config.seen


def test_configure_tijdens_fetch_zet_oude_seen_niet_terug(trage):
    t, uit = _poll_in_thread(trage)
    trage.configure(trage.config.base_url, "hkn_een_andere_sleutel_123")  # wist `seen`
    trage.vrijgeven.set()
    t.join(timeout=5)
    assert not t.is_alive()
    assert uit == [[]]  # resultaat van het oude account is weggegooid
    assert trage.config.seen == []
    assert trage.state.status is Status.NOT_CONFIGURED  # ook de status van het oude account niet


def test_fetch_wijzigt_de_toestand_niet(controller):
    state = State()
    client = ApiClient(controller.config.base_url, FAKE_KEY)
    result = state.fetch(client)
    assert (state.status, state.snapshot, state.failures, state.updated_at) == (
        Status.NOT_CONFIGURED,
        None,
        0,
        None,
    )
    assert not isinstance(result, Exception)


def test_fetch_geeft_verwachte_fouten_terug_in_plaats_van_ze_te_werpen(controller, server):
    server.status = 500
    result = State.fetch(ApiClient(controller.config.base_url, FAKE_KEY))
    assert isinstance(result, ApiError)


def test_fetch_zonder_client_geeft_not_configured(controller):
    assert isinstance(State.fetch(None), NotConfigured)
    state = State()
    state.status = Status.IDLE
    assert state.apply(NotConfigured(), controller.config, "nl", "12:00") == []
    assert state.status is Status.NOT_CONFIGURED and state.snapshot is None


def test_fetch_en_apply_geven_hetzelfde_als_poll(controller, server):
    from huurklaar_notifier.core.config import Config

    client = ApiClient(controller.config.base_url, FAKE_KEY)
    a, b = State(), State()
    ca, cb = Config(base_url="x"), Config(base_url="x")
    toasts_a = a.poll(client, ca, "nl", "12:00")
    toasts_b = b.apply(b.fetch(client), cb, "nl", "12:00")
    assert toasts_a == toasts_b and toasts_a
    assert (a.status, a.snapshot, a.failures, a.updated_at) == (
        b.status,
        b.snapshot,
        b.failures,
        b.updated_at,
    )
    assert ca.seen == cb.seen != []
    # ook bij een fout
    server.status = 500
    assert a.poll(client, ca, "nl", "12:01") == b.apply(b.fetch(client), cb, "nl", "12:01") == []
    assert (a.status, a.failures) == (b.status, b.failures) == (Status.OFFLINE, 1)
