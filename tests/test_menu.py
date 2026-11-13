from huurklaar_notifier.core.i18n import CATALOG, LANGUAGES, resolve_language, translate
from huurklaar_notifier.core.menu import AUTOSTART, QUIT, REFRESH, SETTINGS, build_menu, title_for
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


def test_taal_volgt_systeem():
    assert resolve_language("auto", ["fr-BE", "en"]) == "fr"
    assert resolve_language("auto", ["de-DE"]) == "nl"
    assert resolve_language("en", ["fr"]) == "en"
    assert translate("fr", "menu.quit") == "Quitter"
