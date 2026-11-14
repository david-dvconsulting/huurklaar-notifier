import json

from huurklaar_notifier.core.state import Delivery, Status
from huurklaar_notifier.testing.fake_server import EMPTY, FAKE_KEY, SAMPLE


def test_eerste_poll_geeft_een_melding_voor_de_actie(controller):
    toasts = controller.poll().toasts
    assert controller.state.status is Status.ATTENTION
    assert [t.title for t in toasts] == ["Indexatie nakijken"]
    assert toasts[0].url == "https://app.example.test/tasks/task-1"


def test_zelfde_melding_niet_twee_keer_ook_na_herstart(controller, tmp_path):
    controller.poll()
    assert controller.poll() == Delivery()
    from huurklaar_notifier.core.config import ConfigStore

    assert "task-1" in ConfigStore(tmp_path).load().seen


def test_afgekapte_lijst_meldt_terugkerende_melding_niet_opnieuw(controller, server):
    controller.poll()
    server.body = {**SAMPLE, "items": [], "truncated": True}
    assert controller.poll() == Delivery()
    assert "task-1" in controller.config.seen
    server.body = {**SAMPLE, "truncated": True}
    assert controller.poll() == Delivery()


def test_niet_afgekapte_lijst_meldt_terugkerende_melding_opnieuw(controller, server):
    controller.poll()
    server.body = {**SAMPLE, "items": [], "truncated": False}
    assert controller.poll() == Delivery(withdraw=["task-1"])
    server.body = {**SAMPLE, "truncated": False}
    assert [t.title for t in controller.poll().toasts] == ["Indexatie nakijken"]


def test_veel_nieuwe_meldingen_geven_een_samenvatting(controller, server):
    many = [{**SAMPLE["items"][0], "id": f"t{i}"} for i in range(5)]
    server.body = {**SAMPLE, "items": many, "counts": {"total": 5, "overdue": 5, "actionRequired": 5}}
    toasts = controller.poll().toasts
    assert len(toasts) == 1 and "5" in toasts[0].title
    assert toasts[0].url == "https://app.example.test/"


def test_niets_te_doen(controller, server):
    server.body = EMPTY
    assert controller.poll() == Delivery() and controller.state.status is Status.IDLE


def test_noodknop_geeft_geen_meldingen(controller, server):
    server.body = {**SAMPLE, "enabled": False}
    assert controller.poll() == Delivery() and controller.state.status is Status.DISABLED


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


def test_toast_heeft_sleutel_en_groep_per_item(controller):
    toast = controller.poll().toasts[0]
    assert (toast.key, toast.group) == ("task-1", "task")


def test_samenvatting_heeft_sleutel_en_groep_summary(controller, server):
    many = [{**SAMPLE["items"][0], "id": f"t{i}"} for i in range(5)]
    server.body = {**SAMPLE, "items": many, "counts": {"total": 5, "overdue": 5, "actionRequired": 5}}
    toast = controller.poll().toasts[0]
    assert (toast.key, toast.group) == ("summary", "summary")


def test_opgelost_item_wordt_een_keer_ingetrokken(controller, server):
    assert controller.poll().withdraw == []
    server.body = {**SAMPLE, "items": []}
    assert controller.poll().withdraw == ["task-1"]
    assert controller.poll().withdraw == []  # niet opnieuw


def test_intrekken_behoudt_volgorde_van_seen_zonder_dubbelen(controller, server):
    items = [{**SAMPLE["items"][0], "id": f"t{i}"} for i in range(3)]
    server.body = {**SAMPLE, "items": items}
    controller.poll()
    controller.config.seen = ["t2", "t0", "t2", "t1"]
    server.body = {**SAMPLE, "items": []}
    assert controller.poll().withdraw == ["t2", "t0", "t1"]


def test_niets_intrekken_bij_afgekapte_lijst(controller, server):
    controller.poll()
    server.body = {**SAMPLE, "items": [], "truncated": True}
    assert controller.poll().withdraw == []


def test_niets_intrekken_bij_netwerkfout(controller, server):
    controller.poll()
    server.status = 500
    assert controller.poll() == Delivery()
    assert "task-1" in controller.config.seen


def test_niets_intrekken_bij_geweigerde_sleutel(controller):
    controller.poll()
    controller.platform.secrets.set("hkn_ingetrokken_sleutel_test")
    controller._client_cache = None  # de client leest de sleutel opnieuw
    assert controller.poll() == Delivery()
    assert controller.state.status is Status.AUTH_FAILED


def _soorten(*soorten: tuple[str, bool]):
    """Verzonnen items voor `summary_body`: één tuple per item, (soort, te laat)."""
    from huurklaar_notifier.core.models import Item

    return [
        Item(
            id=f"i{n}",
            kind=kind,
            title="Voorbeeld",
            account_name=None,
            property_label=None,
            status="open",
            due_date=None,
            overdue=overdue,
            action_required=True,
            href="https://app.example.test/x",
        )
        for n, (kind, overdue) in enumerate(soorten)
    ]


def test_samenvatting_telt_per_soort_in_elke_taal(controller, server):
    lijst = [
        {**SAMPLE["items"][0], "id": f"t{i}", "kind": kind, "overdue": overdue}
        for i, (kind, overdue) in enumerate(
            [("task", True), ("complaint", False), ("task", False), ("complaint", False), ("task", False)]
        )
    ]
    server.body = {**SAMPLE, "items": lijst, "counts": {"total": 5, "overdue": 1, "actionRequired": 5}}
    verwacht = {
        "nl": "3 taken, 2 klachten (1 te laat)",
        "fr": "3 tâches, 2 plaintes (1 en retard)",
        "en": "3 tasks, 2 complaints (1 overdue)",
    }
    for taal, tekst in verwacht.items():
        controller.set_language(taal)
        controller.config.seen = []  # elke taal opnieuw als nieuwe meldingen
        toasts = controller.poll().toasts
        assert [t.body for t in toasts] == [tekst], taal


def test_samenvatting_meest_voorkomende_soort_eerst():
    from huurklaar_notifier.core.state import summary_body

    assert summary_body(_soorten(("complaint", False), ("task", False), ("task", False)), "nl") == (
        "2 taken, 1 klacht"
    )


def test_gelijke_aantallen_volgen_de_volgorde_van_voorkomen():
    from huurklaar_notifier.core.state import summary_body

    lijst = _soorten(("report", False), ("task", False), ("task", False), ("report", False))
    assert summary_body(lijst, "nl") == "2 meldingen, 2 taken"
    lijst = _soorten(("task", False), ("report", False), ("report", False), ("task", False))
    assert summary_body(lijst, "nl") == "2 taken, 2 meldingen"


def test_enkelvoud_en_meervoud():
    from huurklaar_notifier.core.state import summary_body

    assert summary_body(_soorten(("task", False)), "nl") == "1 taak"
    assert summary_body(_soorten(("complaint", False), *[("task", False)] * 4), "nl") == ("4 taken, 1 klacht")
    assert summary_body(_soorten(("task", False), ("task", False)), "fr") == "2 tâches"


def test_zonder_te_late_items_geen_te_laat_tekst():
    from huurklaar_notifier.core.state import summary_body

    tekst = summary_body(_soorten(("task", False), ("complaint", False)), "nl")
    assert "te laat" not in tekst and "(" not in tekst


def test_onbekende_soort_telt_mee_als_andere_melding():
    from huurklaar_notifier.core.state import summary_body

    tekst = summary_body(_soorten(("parking", False), ("task", False), ("nieuwesoort", True)), "nl")
    assert tekst == "2 andere meldingen, 1 taak (1 te laat)"
    assert "count." not in tekst and "parking" not in tekst and "nieuwesoort" not in tekst


def test_een_onbekende_soort_geeft_enkelvoud_andere_melding():
    from huurklaar_notifier.core.state import summary_body

    assert summary_body(_soorten(("parking", False), ("task", False)), "en") == (
        "1 other notification, 1 task"
    )
