import time
from datetime import date

import pytest

from huurklaar_notifier.core.controller import Controller
from huurklaar_notifier.core.defaults import DEFAULT_BASE_URL
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
from huurklaar_notifier.core.state import State, Status
from huurklaar_notifier.testing.fake_server import EMPTY, FAKE_KEY, SAMPLE
from huurklaar_notifier.testing.fakes import FakePlatform

VANDAAG = date(2026, 11, 14)
KLOK = 1_700_000_000.0  # vaste tijd voor de 'Bijgewerkt om'-regel

TEST_API = "https://gqncu23i4i.execute-api.eu-central-1.amazonaws.com"


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
    # Twee groepen (taak en klacht): de kopregel zegt de soort, dus geen voorvoegsel.
    assert item.label == "⚠️ Indexatie nakijken — Teststraat 1 · 13 d te laat"
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


def _pauzemenu(entries):
    return next(e for e in entries if e.label == "Meldingen pauzeren")


def test_pauzemenu_zonder_pauze_heeft_geen_hervatten(controller):
    sub = _pauzemenu(build_menu(controller.state, "nl", "auto", False)).children
    assert [(e.label, e.action) for e in sub] == [
        ("1 uur", "pause:hour"),
        ("Tot morgen 8:00", "pause:tomorrow"),
    ]


def test_pauzemenu_tijdens_pauze_heeft_hervatten_en_statusregel(controller):
    import time

    tot = time.mktime((2026, 11, 14, 15, 30, 0, 0, 0, -1))
    entries = build_menu(controller.state, "nl", "auto", False, paused_until=tot)
    assert [e.action for e in _pauzemenu(entries).children] == ["pause:hour", "pause:tomorrow", "pause:off"]
    assert entries[0].label == "Gepauzeerd tot 15:30 · Niet aangemeld"


def test_statusregel_tijdens_pauze_behoudt_het_aantal_taken(controller):
    import time

    from huurklaar_notifier.core.menu import status_line

    controller.poll()
    tot = time.mktime((2026, 11, 14, 15, 30, 0, 0, 0, -1))
    assert status_line(controller.state, "nl", tot) == "Gepauzeerd tot 15:30 · 2 open · 1 te laat"
    assert status_line(controller.state, "en", tot).startswith("Paused until 15:30")


def test_statusregel_zonder_pauze_is_ongewijzigd(controller):
    controller.poll()
    assert (
        build_menu(controller.state, "nl", "auto", False, paused_until=0.0)[0].label == "2 open · 1 te laat"
    )


# -- meldingen per soort (KAN-284) ----------------------------------------------------------------
def _soort(soort: str, i: int = 0) -> dict:
    return {**SAMPLE["items"][0], "id": f"{soort}-{i}", "kind": soort, "title": f"Nieuw {soort} {i}"}


def _submenu(entries):
    return next(e for e in entries if e.label == "Meldingen voor")


def test_submenu_meldingen_voor_volgt_de_volgorde_van_de_groepen(controller, server):
    # De server stuurt 'task' vóór 'report'; het submenu volgt toch de groepen in het menu (GROUP_ORDER).
    server.body = {
        **SAMPLE,
        "items": [_soort("invoiceAttention"), _soort("complaint"), _soort("task"), _soort("report")],
    }
    controller.poll()
    entries = build_menu(controller.state, "nl", "auto", False, muted_kinds=("report",))
    sub = _submenu(entries).children
    assert [(c.label, c.checked) for c in sub] == [
        ("Factuur", True),
        ("Klacht", True),
        ("Melding", False),
        ("Taak", True),
    ]
    assert [c.action for c in sub] == ["kind:invoiceAttention", "kind:complaint", "kind:report", "kind:task"]


def test_submenu_toont_uitgezette_soort_die_niet_meer_in_het_antwoord_staat(controller, server):
    server.body = {**SAMPLE, "items": [_soort("task")]}
    controller.poll()
    entries = build_menu(controller.state, "nl", "auto", False, muted_kinds=("complaint",))
    assert [(c.label, c.checked) for c in _submenu(entries).children] == [("Klacht", False), ("Taak", True)]


def test_onbekende_soort_komt_niet_in_het_submenu(controller, server):
    server.body = {**SAMPLE, "items": [_soort("nieuwesoort"), _soort("task")]}
    controller.poll()
    entries = build_menu(controller.state, "nl", "auto", False)
    assert [c.action for c in _submenu(entries).children] == ["kind:task"]


def test_zonder_items_geen_submenu_meldingen_voor(controller, server):
    server.body = EMPTY
    controller.poll()
    entries = build_menu(controller.state, "nl", "auto", False)
    assert not any(e.label == "Meldingen voor" for e in entries)


# -- dagelijkse herinnering (KAN-285) ---------------------------------------------------------------
def test_vinkje_dagelijkse_herinnering_aan_en_uit(controller):
    controller.poll()
    aan = next(
        e for e in build_menu(controller.state, "nl", "auto", False) if e.label == "Dagelijkse herinnering"
    )
    assert aan.action == "reminder" and aan.checked is True
    uit = next(
        e
        for e in build_menu(controller.state, "nl", "auto", False, daily_reminder=False)
        if e.label == "Dagelijkse herinnering"
    )
    assert uit.checked is False


def test_herinnering_staat_na_meldingen_voor_en_voor_autostart(controller):
    controller.poll()
    namen = labels(build_menu(controller.state, "nl", "auto", False))
    assert namen.index("Meldingen voor") + 1 == namen.index("Dagelijkse herinnering")
    assert namen.index("Dagelijkse herinnering") + 1 == namen.index("Start bij aanmelden")


def test_herinnering_staat_na_meldingen_pauzeren_zonder_submenu_soorten(controller, server):
    server.body = EMPTY
    controller.poll()
    namen = labels(build_menu(controller.state, "nl", "auto", False))
    assert "Meldingen voor" not in namen
    assert namen.index("Meldingen pauzeren") + 1 == namen.index("Dagelijkse herinnering")
    assert namen.index("Dagelijkse herinnering") + 1 == namen.index("Start bij aanmelden")


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


def _item(kind, n, **extra):
    return {**SAMPLE["items"][1], "id": f"{kind}-{n}", "kind": kind, "title": f"{kind} {n}", **extra}


def _toon(controller, server, items, total=None):
    total = len(items) if total is None else total
    server.body = {**SAMPLE, "items": items, "counts": {"total": total, "overdue": 0, "actionRequired": 0}}
    controller.poll()
    return build_menu(controller.state, "nl", "auto", False, today=VANDAAG)


def test_drie_groepen_in_vaste_volgorde_met_aantallen(controller, server):
    items = [
        _item("task", 1),
        _item("complaint", 1),
        _item("task", 2),
        _item("invoiceAttention", 1),
        _item("complaint", 2),
        _item("task", 3),
    ]
    entries = _toon(controller, server, items)
    assert [e.label for e in entries if not e.enabled and e.label.endswith(")")] == [
        "Facturen (1)",
        "Klachten (2)",
        "Taken (3)",
    ]
    assert labels(entries)[2:11] == [
        "Facturen (1)",
        "invoiceAttention 1",
        "Klachten (2)",
        "complaint 1",
        "complaint 2",
        "Taken (3)",
        "task 1",
        "task 2",
        "task 3",
    ]


def test_volgorde_binnen_een_groep_is_die_van_de_server(controller, server):
    items = [_item("task", 3), _item("task", 1), _item("complaint", 9), _item("task", 2)]
    lijst = labels(_toon(controller, server, items))
    assert [x for x in lijst if x.startswith("task")] == ["task 3", "task 1", "task 2"]


def test_alle_zes_bekende_soorten_en_andere_in_vaste_volgorde(controller, server):
    soorten = ["tenantTask", "nieuw1", "myReport", "task", "report", "complaint", "invoiceAttention"]
    entries = _toon(controller, server, [_item(k, 1) for k in soorten])
    koppen = [e.label for e in entries if not e.enabled and e.label.endswith("(1)")]
    assert koppen == [
        "Facturen (1)",
        "Klachten (1)",
        "Meldingen (1)",
        "Taken (1)",
        "Jouw meldingen (1)",
        "Taken voor jou (1)",
        "Andere (1)",
    ]


def test_grens_en_verdeling_met_veel_taken_en_twee_kleine_groepen(controller, server):
    items = [_item("task", i) for i in range(12)] + [_item("complaint", 1), _item("invoiceAttention", 1)]
    entries = _toon(controller, server, items)
    getoond = [
        e for e in entries if e.url and e.label.split(" ")[0] in {"task", "complaint", "invoiceAttention"}
    ]
    assert len(getoond) == 10  # kopregels tellen niet mee
    assert sum(e.label.startswith("task") for e in getoond) == 8
    assert "complaint 1" in labels(entries) and "invoiceAttention 1" in labels(entries)
    assert "Taken (12)" in labels(entries)  # het aantal in het antwoord, niet het getoonde
    assert "… en nog 4 in Huurklaar" in labels(entries)


def test_verdeling_over_twee_grote_groepen_is_eerlijk(controller, server):
    items = [_item("task", i) for i in range(9)] + [_item("complaint", i) for i in range(9)]
    lijst = labels(_toon(controller, server, items))
    assert sum(x.startswith("complaint") for x in lijst) == 5
    assert sum(x.startswith("task") for x in lijst) == 5
    assert "Klachten (9)" in lijst and "Taken (9)" in lijst
    assert "… en nog 8 in Huurklaar" in lijst


def test_een_groep_heeft_geen_kopregel_en_houdt_het_voorvoegsel(controller, server):
    entries = _toon(controller, server, [_item("task", 1), _item("task", 2)])
    lijst = labels(entries)
    assert "Taak: task 1" in lijst and "Taak: task 2" in lijst
    assert not any(x.startswith("Taken (") for x in lijst)


def test_onbekende_soorten_komen_samen_onder_andere_achteraan(controller, server):
    items = [_item("nieuw1", 1), _item("task", 1), _item("nieuw2", 1), _item("nieuw1", 2)]
    lijst = labels(_toon(controller, server, items))
    assert lijst[2:8] == ["Taken (1)", "task 1", "Andere (3)", "nieuw1 1", "nieuw2 1", "nieuw1 2"]


def test_kopregels_zijn_uitgeschakeld_zonder_url_of_actie(controller, server):
    entries = _toon(controller, server, [_item("task", 1), _item("complaint", 1), _item("nieuw1", 1)])
    koppen = [e for e in entries if e.label in {"Klachten (1)", "Taken (1)", "Andere (1)"}]
    assert len(koppen) == 3
    for kop in koppen:
        assert kop.enabled is False
        assert kop.url is None and kop.action is None and not kop.children and not kop.separator


@pytest.mark.parametrize("lang", LANGUAGES)
def test_kopregels_bestaan_in_elke_taal(controller, server, lang):
    _toon(controller, server, [_item("task", 1), _item("complaint", 1)])
    entries = build_menu(controller.state, lang, "auto", False, today=VANDAAG)
    koppen = [e.label for e in entries if not e.enabled and e.label.endswith("(1)")]
    assert len(koppen) == 2
    assert not any(k.startswith("group.") for k in koppen)


def _met_account(kind, n, account, **extra):
    return _item(kind, n, accountName=account, **extra)


def test_een_account_toont_geen_accountnaam(controller, server):
    # Alle items dezelfde accountnaam: dat is één account, dus geen accountdeel in de labels.
    items = [_met_account("task", 1, "Verhuur Peeters"), _met_account("complaint", 1, "Verhuur Peeters")]
    lijst = labels(_toon(controller, server, items))
    assert "Taak: task 1" not in lijst  # twee groepen: de kopregel zegt de soort
    assert "task 1" in lijst and "complaint 1" in lijst
    assert not any("Verhuur Peeters" in x for x in lijst)


def test_twee_accounts_zetten_de_naam_na_het_pand_en_voor_de_datum(controller, server):
    items = [
        {
            **SAMPLE["items"][0],
            "id": "t1",
            "kind": "task",
            "title": "Lekkende kraan",
            "accountName": "Verhuur Peeters",
            "propertyLabel": "Kerkstraat 1",
            "dueDate": "2026-11-11",
        },
        {
            **SAMPLE["items"][1],
            "id": "c1",
            "kind": "complaint",
            "title": "Schimmel",
            "accountName": "Voorbeeld Verhuur",
            "propertyLabel": "Dorpsweg 2",
            "dueDate": "2026-11-15",
        },
    ]
    lijst = labels(_toon(controller, server, items))
    assert "⚠️ Lekkende kraan — Kerkstraat 1 · Verhuur Peeters · 3 d te laat" in lijst
    assert "Schimmel — Dorpsweg 2 · Voorbeeld Verhuur · morgen" in lijst


def test_item_zonder_accountnaam_krijgt_geen_accountdeel(controller, server):
    items = [
        _met_account("task", 1, "Verhuur Peeters"),
        _met_account("complaint", 1, "Voorbeeld Verhuur"),
        _item("complaint", 2, dueDate="2026-11-15"),  # zonder accountName
    ]
    lijst = labels(_toon(controller, server, items))
    assert "complaint 2 · morgen" in lijst
    assert not any(" · · " in x or " ·  " in x or x.endswith(" ·") for x in lijst)


def test_items_zonder_accountnaam_blijven_ongewijzigd(controller, server):
    # Geen naam, lege naam of allemaal None: twee groepen krijgen het gewone label, zonder accountdeel.
    items = [_item("task", 1, accountName=None), _item("complaint", 1, accountName="")]
    lijst = labels(_toon(controller, server, items))
    start = lijst.index("Klachten (1)")
    assert lijst[start : start + 4] == ["Klachten (1)", "complaint 1", "Taken (1)", "task 1"]


def test_accountnaam_telt_het_hele_antwoord_niet_enkel_de_getoonde_items(controller, server):
    # Tien getoonde items van één account; het elfde, verborgen item is van een ander account.
    items = [_met_account("task", i, "Verhuur Peeters") for i in range(10)]
    items.append(_met_account("task", 10, "Voorbeeld Verhuur"))
    lijst = labels(_toon(controller, server, items))
    assert "Taak: task 0 · Verhuur Peeters" in lijst
    assert "… en nog 1 in Huurklaar" in lijst


def test_lange_titel_wordt_eerst_ingekort_account_en_datum_blijven_heel(controller, server):
    items = [
        {
            **SAMPLE["items"][0],
            "id": "t1",
            "kind": "task",
            "title": "T" * 120,
            "accountName": "Verhuur Peeters",
            "propertyLabel": "Kerkstraat 1",
            "dueDate": "2026-11-11",
        },
        _met_account("complaint", 1, "Voorbeeld Verhuur"),
    ]
    label = next(e.label for e in _toon(controller, server, items) if e.url and e.label.startswith("⚠️"))
    assert label == f"⚠️ {'T' * 19}… — Kerkstraat 1 · Verhuur Peeters · 3 d te laat"
    assert len(label) == MAX_LABEL


def test_lang_pand_en_titel_met_twee_accounts_blijft_binnen_maximum(controller, server):
    items = [
        {
            **SAMPLE["items"][0],
            "id": "t1",
            "kind": "task",
            "title": "T" * 120,
            "accountName": "Verhuur Peeters",
            "propertyLabel": "P" * 120,
            "dueDate": "2026-11-11",
        },
        _met_account("complaint", 1, "Voorbeeld Verhuur"),
    ]
    label = next(e.label for e in _toon(controller, server, items) if e.url and e.label.startswith("⚠️"))
    assert len(label) <= MAX_LABEL
    assert label.startswith("⚠️ TT")
    assert label.endswith(" · Verhuur Peeters · 3 d te laat")


def test_extreme_accountnaam_kort_enkel_de_naam_in_en_datum_blijft_heel(controller, server):
    items = [
        {
            **SAMPLE["items"][0],
            "id": "t1",
            "kind": "task",
            "title": "Lekkage",
            "accountName": "X" * 120,
            "propertyLabel": "Kerkstraat 1",
            "dueDate": "2026-11-11",
        },
        _met_account("complaint", 1, "Voorbeeld Verhuur"),
    ]
    label = next(e.label for e in _toon(controller, server, items) if e.url and e.label.startswith("⚠️"))
    assert label == f"⚠️ Lekkage — Kerkstraat 1 · {'X' * 23}… · 3 d te laat"
    assert len(label) <= MAX_LABEL


def test_extreme_accountnaam_bij_één_groep_met_soortvoorvoegsel(controller, server):
    # Het langste voorvoegsel ("Taak voor jou: ") plus een lange datum: de naam moet nog steeds passen.
    items = [
        {
            **SAMPLE["items"][0],
            "id": "t1",
            "kind": "tenantTask",
            "title": "Lekkage",
            "accountName": "X" * 120,
            "propertyLabel": None,
            "dueDate": "2026-11-11",
        },
        {
            **SAMPLE["items"][0],
            "id": "t2",
            "kind": "tenantTask",
            "title": "Lekkage 2",
            "accountName": "Voorbeeld Verhuur",
            "propertyLabel": None,
            "dueDate": "2026-11-11",
        },
    ]
    lijst = [e.label for e in _toon(controller, server, items) if e.label.startswith("⚠️")]
    assert len(lijst) == 2
    for label in lijst:
        assert len(label) <= MAX_LABEL
        assert label.endswith(" · 3 d te laat")
    assert lijst[0].startswith("⚠️ Taak voor jou: Lekkage · ") and "…" in lijst[0]


# -- eerste start: hulpitem voor de sleutel ----------------------------------------------------------
def _menu(status: Status, base_url: str = "") -> list[Entry]:
    state = State()
    state.status = status
    return build_menu(state, "nl", "auto", False, base_url=base_url)


@pytest.mark.parametrize(
    ("status", "verwacht"),
    [
        (Status.NOT_CONFIGURED, True),
        (Status.AUTH_FAILED, True),
        (Status.IDLE, False),
        (Status.ATTENTION, False),
        (Status.OFFLINE, False),
        (Status.DISABLED, False),
    ],
)
def test_sleutel_hulpitem_alleen_bij_niet_aangemeld_en_sleutel_ongeldig(status, verwacht):
    heeft = any(e.label == translate("nl", "menu.get_key") for e in _menu(status, DEFAULT_BASE_URL))
    assert heeft is verwacht


@pytest.mark.parametrize("status", [Status.NOT_CONFIGURED, Status.AUTH_FAILED])
@pytest.mark.parametrize(
    ("base_url", "app"),
    [
        (DEFAULT_BASE_URL, "https://app.huurklaar.be"),
        (DEFAULT_BASE_URL + "/", "https://app.huurklaar.be"),
        (TEST_API, "https://app-dev.huurklaar.be"),
        ("https://onbekend.example.test", "https://app.huurklaar.be"),
        ("", "https://app.huurklaar.be"),
    ],
)
def test_sleutel_hulpitem_opent_de_app_van_de_omgeving(status, base_url, app):
    (entry,) = [e for e in _menu(status, base_url) if e.label == translate("nl", "menu.get_key")]
    assert entry.url == app + "/profile/notifications"
    assert entry.action is None and entry.enabled


def test_over_item_opent_de_projectpagina_en_toont_de_versie():
    from huurklaar_notifier._version import __version__
    from huurklaar_notifier.core.defaults import PROJECT_URL

    ok = State()
    ok.status = Status.ATTENTION
    for state in (State(), ok):
        over = [e for e in build_menu(state, "nl", "auto", False, today=VANDAAG) if e.url == PROJECT_URL]
        assert len(over) == 1
        assert over[0].enabled and __version__ in over[0].label
        assert over[0].label.startswith("Over Huurklaar Meldingen")
