"""Soort `message` (KAN-370): een gesprek met ongelezen berichten krijgt een eigen naam, groep en aan/uit-schakelaar."""

from datetime import date

from huurklaar_notifier.core.controller import Controller
from huurklaar_notifier.core.i18n import LANGUAGES, translate
from huurklaar_notifier.core.menu import GROUP_ORDER, build_menu
from huurklaar_notifier.core.models import Item
from huurklaar_notifier.core.state import summary_body
from huurklaar_notifier.testing.fake_server import EMPTY, FAKE_KEY, SAMPLE
from huurklaar_notifier.testing.fakes import FakePlatform

VANDAAG = date(2026, 11, 14)


def _soort(soort: str, i: int = 0) -> dict:
    return {**SAMPLE["items"][0], "id": f"{soort}-{i}", "kind": soort, "title": f"Nieuw {soort} {i}"}


def _antwoord(*items: dict) -> dict:
    n = len(items)
    return {**SAMPLE, "items": list(items), "counts": {"total": n, "overdue": 0, "actionRequired": n}}


def _labels(entries) -> list[str]:
    return [e.label for e in entries if not e.separator]


def _submenu(entries):
    return next(e for e in entries if e.label == translate("nl", "menu.kinds"))


def _menu(controller, **kwargs):
    kwargs.setdefault("muted_kinds", tuple(controller.config.muted_kinds))
    return build_menu(controller.state, "nl", "auto", False, today=VANDAAG, **kwargs)


def test_soort_message_heeft_eigen_naam_in_de_drie_talen():
    assert translate("nl", "kind.message") == "Nieuw bericht"
    assert translate("en", "kind.message") == "New message"
    assert translate("fr", "kind.message") == "Nouveau message"
    for lang in LANGUAGES:
        assert translate(lang, "kind.message") != translate(lang, "kind.other")


def test_groepstitel_en_tellers_van_message_in_de_drie_talen():
    assert translate("nl", "group.message", n=2) == "Berichten (2)"
    assert translate("en", "group.message", n=2) == "Messages (2)"
    assert translate("fr", "group.message", n=2) == "Messages (2)"
    assert translate("nl", "count.message.one", n=1) == "1 bericht"
    assert translate("nl", "count.message.many", n=3) == "3 berichten"
    assert translate("en", "count.message.one", n=1) == "1 message"
    assert translate("en", "count.message.many", n=3) == "3 messages"
    assert translate("fr", "count.message.one", n=1) == "1 message"
    assert translate("fr", "count.message.many", n=3) == "3 messages"


def test_message_staat_na_taak_en_voor_jouw_meldingen():
    assert GROUP_ORDER.index("task") < GROUP_ORDER.index("message") < GROUP_ORDER.index("myReport")


def test_menu_groepeert_berichten_met_teller_in_de_juiste_volgorde(controller, server):
    server.body = _antwoord(_soort("myReport"), _soort("message", 0), _soort("task"), _soort("message", 1))
    controller.poll()
    labels = _labels(_menu(controller))
    kopregels = [x for x in labels if x.startswith(("Taken (", "Berichten (", "Jouw meldingen ("))]
    assert kopregels == ["Taken (1)", "Berichten (2)", "Jouw meldingen (1)"]
    assert any("Nieuw message 0" in x for x in labels)


def test_message_met_een_enkele_groep_krijgt_de_soortnaam_als_voorvoegsel(controller, server):
    server.body = _antwoord(_soort("message", 0))
    controller.poll()
    labels = _labels(_menu(controller))
    # De items zijn te laat (SAMPLE), dus de regel begint met het waarschuwingsteken.
    assert any("Nieuw bericht: Nieuw message 0" in x for x in labels)
    assert "Berichten (1)" not in labels


def test_message_staat_in_het_submenu_en_is_standaard_aan(controller, server):
    server.body = _antwoord(_soort("message"))
    controller.poll()
    sub = _submenu(_menu(controller)).children
    assert [(c.label, c.action, c.checked) for c in sub] == [("Nieuw bericht", "kind:message", True)]


def test_message_is_uit_te_zetten_en_weer_aan(controller, server):
    server.body = EMPTY
    controller.poll()
    controller.toggle_kind("message")
    assert controller.config.muted_kinds == ["message"]
    server.body = _antwoord(_soort("message", 0))
    controller.poll()
    sub = _submenu(_menu(controller)).children
    assert [(c.label, c.checked) for c in sub] == [("Nieuw bericht", False)]
    controller.toggle_kind("message")
    assert controller.config.muted_kinds == []
    sub = _submenu(_menu(controller)).children
    assert [(c.label, c.checked) for c in sub] == [("Nieuw bericht", True)]


def test_uitgezet_message_geeft_geen_melding_maar_wordt_wel_gezien(controller, server):
    server.body = EMPTY
    controller.poll()
    controller.toggle_kind("message")
    server.body = _antwoord(_soort("message", 0), _soort("task", 0))
    assert [t.title for t in controller.poll().toasts] == ["Nieuw task 0"]
    assert "message-0" in controller.config.seen


def test_uitzetten_van_message_blijft_bewaard(tmp_path, server):
    c = Controller(FakePlatform(tmp_path), clock=lambda: 0.0)
    c.configure(server.url, FAKE_KEY)
    c.toggle_kind("message")
    nieuw = Controller(FakePlatform(tmp_path), clock=lambda: 0.0)
    assert nieuw.config.muted_kinds == ["message"]


def test_onbekende_soort_houdt_de_generieke_tekst(controller, server):
    server.body = _antwoord(_soort("nieuwesoort"))
    controller.poll()
    assert translate("nl", "kind.other") == "Melding"
    assert any("Melding: Nieuw nieuwesoort 0" in x for x in _labels(_menu(controller)))
    assert not any(e.label == translate("nl", "menu.kinds") for e in _menu(controller))


def test_samenvatting_noemt_berichten_met_hun_eigen_telvorm():
    items = [
        Item("m1", "message", "a", None, None, None, None, False, True, ""),
        Item("m2", "message", "b", None, None, None, None, False, True, ""),
        Item("t1", "task", "c", None, None, None, None, False, True, ""),
    ]
    assert summary_body(items, "nl") == "2 berichten, 1 taak"
    assert summary_body(items, "en") == "2 messages, 1 task"
