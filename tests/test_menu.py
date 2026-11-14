from huurklaar_notifier.core.i18n import CATALOG, LANGUAGES, resolve_language, translate
from huurklaar_notifier.core.menu import (
    AUTOSTART,
    QUIT,
    REFRESH,
    SETTINGS,
    Entry,
    MenuCache,
    build_menu,
    title_for,
)
from huurklaar_notifier.core.state import Status
from huurklaar_notifier.testing.fake_server import EMPTY, SAMPLE


def labels(entries):
    return [e.label for e in entries if not e.separator]


def test_menu_met_taken(controller):
    controller.poll()
    entries = build_menu(controller.state, "nl", "auto", False)
    assert entries[0].label == "2 open · 1 te laat"
    item = next(e for e in entries if "Indexatie nakijken" in e.label)
    assert item.label.startswith("⚠️ Taak:") and item.url == "https://app.example.test/tasks/task-1"
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


def test_twee_polls_met_hetzelfde_antwoord_bouwen_het_menu_een_keer(controller):
    cache = MenuCache()
    builds = 0
    for _ in range(2):
        controller.poll()
        entries = build_menu(controller.state, "nl", "auto", False)
        if cache.changed(entries, title_for(controller.state)):
            builds += 1
    assert builds == 1
