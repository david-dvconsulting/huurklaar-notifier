import json

from huurklaar_notifier.core.state import Status
from huurklaar_notifier.testing.fake_server import EMPTY, FAKE_KEY, SAMPLE


def test_eerste_poll_geeft_een_melding_voor_de_actie(controller):
    toasts = controller.poll()
    assert controller.state.status is Status.ATTENTION
    assert [t.title for t in toasts] == ["Indexatie nakijken"]
    assert toasts[0].url == "https://app.example.test/tasks/task-1"


def test_zelfde_melding_niet_twee_keer_ook_na_herstart(controller, tmp_path):
    controller.poll()
    assert controller.poll() == []
    from huurklaar_notifier.core.config import ConfigStore

    assert "task-1" in ConfigStore(tmp_path).load().seen


def test_afgekapte_lijst_meldt_terugkerende_melding_niet_opnieuw(controller, server):
    controller.poll()
    server.body = {**SAMPLE, "items": [], "truncated": True}
    assert controller.poll() == []
    assert "task-1" in controller.config.seen
    server.body = {**SAMPLE, "truncated": True}
    assert controller.poll() == []


def test_niet_afgekapte_lijst_meldt_terugkerende_melding_opnieuw(controller, server):
    controller.poll()
    server.body = {**SAMPLE, "items": [], "truncated": False}
    assert controller.poll() == []
    server.body = {**SAMPLE, "truncated": False}
    assert [t.title for t in controller.poll()] == ["Indexatie nakijken"]


def test_veel_nieuwe_meldingen_geven_een_samenvatting(controller, server):
    many = [{**SAMPLE["items"][0], "id": f"t{i}"} for i in range(5)]
    server.body = {**SAMPLE, "items": many, "counts": {"total": 5, "overdue": 5, "actionRequired": 5}}
    toasts = controller.poll()
    assert len(toasts) == 1 and "5" in toasts[0].title
    assert toasts[0].url == "https://app.example.test/"


def test_niets_te_doen(controller, server):
    server.body = EMPTY
    assert controller.poll() == [] and controller.state.status is Status.IDLE


def test_noodknop_geeft_geen_meldingen(controller, server):
    server.body = {**SAMPLE, "enabled": False}
    assert controller.poll() == [] and controller.state.status is Status.DISABLED


def test_geen_verbinding_houdt_laatste_cijfers_en_back_off(controller, server):
    controller.poll()
    server.status = 500
    controller.poll()
    assert controller.state.status is Status.OFFLINE and controller.state.snapshot is not None
    delays = []
    for _ in range(8):
        controller.poll()
        delays.append(controller.next_delay())
    assert delays == sorted(delays) or max(delays) <= 900 * 1.2
    assert max(delays) <= 900 * 1.2 and min(delays) >= 30 * 0.8


def test_succes_volgt_interval_van_de_server(controller, server):
    server.body = {**SAMPLE, "pollAfterSeconds": 600}
    controller.poll()
    assert 480 <= controller.next_delay() <= 720


def test_ingetrokken_sleutel_stopt_het_bellen(controller):
    controller.platform.secrets.set("hkn_ingetrokken_sleutel_test")
    controller.poll()
    assert controller.state.status is Status.AUTH_FAILED and controller.next_delay() is None


def test_zonder_instellingen_wacht_de_app(tmp_path):
    from huurklaar_notifier.core.controller import Controller
    from huurklaar_notifier.testing.fakes import FakePlatform

    c = Controller(FakePlatform(tmp_path))
    c.poll()
    assert c.state.status is Status.NOT_CONFIGURED and c.next_delay() is None


def test_sleutel_staat_niet_op_schijf(controller, tmp_path):
    controller.poll()
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert FAKE_KEY not in f.read_text()


def test_nieuwe_sleutel_wist_geziene_meldingen(controller):
    controller.poll()
    controller.configure(controller.config.base_url, FAKE_KEY)
    assert json.dumps(controller.config.seen) == "[]"


def test_configure_zonder_bewaarde_sleutel_en_zonder_nieuwe_faalt(tmp_path, server):
    import pytest

    from huurklaar_notifier.core.controller import Controller
    from huurklaar_notifier.testing.fakes import FakePlatform

    with pytest.raises(ValueError):
        Controller(FakePlatform(tmp_path)).configure(server.url, None)
