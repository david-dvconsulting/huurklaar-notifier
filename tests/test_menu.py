import time
from datetime import date

import pytest

from huurklaar_notifier.core.controller import Controller
from huurklaar_notifier.core.i18n import CATALOG, LANGUAGES, resolve_language, translate
from huurklaar_notifier.core.menu import (
    AUTOSTART,
    MAX_LABEL,
    QUIT,
    REFRESH,
    SETTINGS,
    Entry,
    MenuCache,
    build_menu,
    due_label,
    title_for,
)
from huurklaar_notifier.core.state import Status
from huurklaar_notifier.testing.fake_server import EMPTY, FAKE_KEY, SAMPLE
from huurklaar_notifier.testing.fakes import FakePlatform

VANDAAG = date(2026, 11, 14)
KLOK = 1_700_000_000.0  # vaste tijd voor de 'Bijgewerkt om'-regel


def labels(entries):
    return [e.label for e in entries if not e.separator]


def _controller(tmp_path, server, klok=lambda: KLOK):
    c = Controller(FakePlatform(tmp_path), clock=klok)
    c.configure(server.url, FAKE_KEY)
    return c


def test_menu_met_taken(controller):
    controller.poll()
    entries = build_menu(controller.state, "nl", "auto", False, today=VANDAAG)
    assert entries[0].label == "2 open · 1 te laat"
    item = next(e for e in entries if "Indexatie nakijken" in e.label)
    assert item.label == "⚠️ Taak: Indexatie nakijken — Teststraat 1 · 13 d te laat"
    assert item.url == "https://app.example.test/tasks/task-1"
    assert {e.action for e in entries} >= {REFRESH, SETTINGS, AUTOSTART, QUIT}
    assert title_for(controller.state) == "1"


def test_menu_toestanden(controller, server):
    server.body = EMPTY
    controller.poll()
    assert build_menu(controller.state, "nl", "auto", False)[0].label == "Niets te doen"
    assert title_for(controller.state) == ""
    controller.state.status = Status.NOT_CONFIGURED
    assert build_menu(controller.state, "en", "auto", False)[0].label == "Not signed in"
    assert title_for(controller.state) == "!"


def test_menu_toont_rest_en_verbergt_onveilige_links(controller, server):
    items = [{**SAMPLE["items"][0], "id": f"t{i}", "href": "javascript:alert(1)"} for i in range(12)]
    server.body = {**SAMPLE, "items": items, "counts": {"total": 15, "overdue": 12, "actionRequired": 12}}
    controller.poll()
    entries = build_menu(controller.state, "nl", "auto", False)
    assert all(e.url is None for e in entries if e.label.startswith("⚠️"))
    assert any("nog 5" in e.label for e in entries)


def test_taalkeuze_en_vinkje(controller):
    entries = build_menu(controller.state, "nl", "fr", False)
    sub = next(e for e in entries if e.children).children
    assert [c.checked for c in sub] == [False, False, True, False]


def test_vertalingen_hebben_dezelfde_sleutels_en_plaatshouders():
    import string

    fmt = string.Formatter()
    for key, text in CATALOG["nl"].items():
        names = {f for _, f, _, _ in fmt.parse(text) if f}
        for lang in LANGUAGES:
            other = CATALOG[lang][key]
            assert {f for _, f, _, _ in fmt.parse(other) if f} == names, (lang, key)
    assert all(set(CATALOG[lang]) == set(CATALOG["nl"]) for lang in LANGUAGES)


def test_onbekende_soort_crasht_het_menu_niet(controller, server):
    server.body = {**SAMPLE, "items": [{**SAMPLE["items"][1], "kind": "nieuwesoort"}]}
    controller.poll()
    entries = build_menu(controller.state, "nl", "auto", False)
    assert "Melding: Lekkage" in labels(entries)


def test_translate_onbekende_sleutel_geeft_sleutel_terug():
    assert translate("nl", "bestaat.niet") == "bestaat.niet"
    assert translate("fr", "bestaat.niet") == "bestaat.niet"


def test_taal_volgt_systeem():
    assert resolve_language("auto", ["fr-BE", "en"]) == "fr"
    assert resolve_language("auto", ["de-DE"]) == "nl"
    assert resolve_language("en", ["fr"]) == "en"
    assert translate("fr", "menu.quit") == "Quitter"


def test_menucache_eerste_keer_en_ongewijzigd():
    cache = MenuCache()
    entries = [Entry("a"), Entry("b", url="https://x.example.test")]
    assert cache.changed(entries, "1") is True
    assert cache.changed(list(entries), "1") is False  # gelijke inhoud in een nieuwe lijst


def test_menucache_andere_entry_of_titel_is_gewijzigd():
    cache = MenuCache()
    assert cache.changed([Entry("a")], "1")
    assert cache.changed([Entry("b")], "1")
    assert cache.changed([Entry("b")], "2")
    assert not cache.changed([Entry("b")], "2")
    assert cache.changed([Entry("b", children=(Entry("kind"),))], "2")  # ook een verschil in een submenu


def test_menucache_reset_dwingt_opnieuw_tekenen():
    cache = MenuCache()
    entries = [Entry("a")]
    assert cache.changed(entries, ("badge", "tip"))
    cache.reset()
    assert cache.changed(entries, ("badge", "tip"))


def test_twee_polls_met_hetzelfde_antwoord_bouwen_het_menu_een_keer(tmp_path, server):
    # Vaste klok: anders kan de minuut tussen de twee polls wisselen en verandert 'Bijgewerkt om'.
    controller = _controller(tmp_path, server)
    cache = MenuCache()
    builds = 0
    for _ in range(2):
        controller.poll()
        entries = build_menu(controller.state, "nl", "auto", False, today=VANDAAG)
        if cache.changed(entries, title_for(controller.state)):
            builds += 1
    assert builds == 1


def test_menu_verandert_als_de_tijd_van_bijwerken_verandert(tmp_path, server):
    tijd = [KLOK]
    controller = _controller(tmp_path, server, klok=lambda: tijd[0])
    cache = MenuCache()
    controller.poll()
    assert cache.changed(build_menu(controller.state, "nl", "auto", False, today=VANDAAG), "1")
    tijd[0] += 60
    controller.poll()
    assert cache.changed(build_menu(controller.state, "nl", "auto", False, today=VANDAAG), "1")


@pytest.mark.parametrize(
    ("due", "verwacht"),
    [
        ("2026-11-13", "1 d te laat"),  # gisteren
        ("2026-11-14", "vandaag"),
        ("2026-11-15", "morgen"),
        ("2026-11-16", "over 2 d"),
        ("2026-11-21", "over 7 d"),  # de grens: nog binnen 7 dagen
        ("2026-11-22", None),  # 8 dagen: niets tonen
        ("2026-01-01", "317 d te laat"),  # ver in het verleden
    ],
)
def test_due_label_grenzen(due, verwacht):
    assert due_label(due, VANDAAG, "nl") == verwacht


@pytest.mark.parametrize("ongeldig", ["2026-13-40", "morgen", "", None, "20261114", "2026-11-14T10:00"])
def test_due_label_ongeldig_geeft_none(ongeldig):
    assert due_label(ongeldig, VANDAAG, "nl") is None


@pytest.mark.parametrize(
    ("lang", "due", "verwacht"),
    [
        ("fr", "2026-11-13", "1 j de retard"),
        ("fr", "2026-11-14", "aujourd'hui"),
        ("fr", "2026-11-15", "demain"),
        ("fr", "2026-11-18", "dans 4 j"),
        ("en", "2026-11-13", "1 d overdue"),
        ("en", "2026-11-14", "today"),
        ("en", "2026-11-15", "tomorrow"),
        ("en", "2026-11-18", "in 4 d"),
    ],
)
def test_due_label_in_fr_en(lang, due, verwacht):
    assert due_label(due, VANDAAG, lang) == verwacht


def test_label_met_datum_blijft_heel_en_binnen_maximum(tmp_path, server):
    server.body = {
        **SAMPLE,
        "items": [
            {**SAMPLE["items"][0], "title": "T" * 120, "propertyLabel": "P" * 120, "dueDate": "2026-11-11"}
        ],
    }
    controller = _controller(tmp_path, server)
    controller.poll()
    label = next(e.label for e in build_menu(controller.state, "nl", "auto", False, today=VANDAAG) if e.url)
    assert len(label) <= MAX_LABEL
    assert label.endswith(" · 3 d te laat")
    assert label.startswith("⚠️ Taak: TTT")


def test_label_met_lange_titel_kort_eerst_de_titel_in(tmp_path, server):
    server.body = {**SAMPLE, "items": [{**SAMPLE["items"][0], "title": "T" * 120, "dueDate": "2026-11-11"}]}
    controller = _controller(tmp_path, server)
    controller.poll()
    label = next(e.label for e in build_menu(controller.state, "nl", "auto", False, today=VANDAAG) if e.url)
    assert len(label) == MAX_LABEL
    assert label.endswith("T… — Teststraat 1 · 3 d te laat")  # pand en datum blijven heel


def test_label_met_lang_pand_kort_eerst_het_pand_in(tmp_path, server):
    server.body = {
        **SAMPLE,
        "items": [
            {**SAMPLE["items"][1], "kind": "task", "propertyLabel": "P" * 120, "dueDate": "2026-11-15"}
        ],
    }
    controller = _controller(tmp_path, server)
    controller.poll()
    label = next(e.label for e in build_menu(controller.state, "nl", "auto", False, today=VANDAAG) if e.url)
    assert len(label) <= MAX_LABEL
    assert label.startswith("Taak: Lekkage — ")
    assert label.endswith(" · morgen")


def test_ongeldige_datum_van_de_server_geeft_geen_fout(tmp_path, server):
    server.body = {**SAMPLE, "items": [{**SAMPLE["items"][0], "dueDate": "2026-13-40"}]}
    controller = _controller(tmp_path, server)
    controller.poll()
    entries = build_menu(controller.state, "nl", "auto", False, today=VANDAAG)
    assert "⚠️ Taak: Indexatie nakijken — Teststraat 1" in labels(entries)


def test_item_zonder_of_ver_weg_datum_blijft_ongewijzigd(tmp_path, server):
    server.body = {
        **SAMPLE,
        "items": [
            {**SAMPLE["items"][1]},  # zonder dueDate
            {**SAMPLE["items"][1], "id": "task-3", "title": "Verre taak", "dueDate": "2026-11-22"},
        ],
    }
    controller = _controller(tmp_path, server)
    controller.poll()
    entries = build_menu(controller.state, "nl", "auto", False, today=VANDAAG)
    assert "Klacht: Lekkage" in labels(entries)
    assert "Klacht: Verre taak" in labels(entries)


@pytest.mark.parametrize("status_body", [SAMPLE, EMPTY], ids=["attention", "idle"])
def test_bijgewerkt_om_staat_ook_bij_attention_en_idle(tmp_path, server, status_body):
    server.body = status_body
    controller = _controller(tmp_path, server)
    controller.poll()
    verwacht = f"Bijgewerkt om {time.strftime('%H:%M', time.localtime(KLOK))}"
    assert verwacht in labels(build_menu(controller.state, "nl", "auto", False, today=VANDAAG))
