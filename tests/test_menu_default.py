"""Het standaarditem van het menu: een linksklik op het tray-icoon voert het uit (pystray, Windows)."""

import pytest

from huurklaar_notifier.core.defaults import DEFAULT_BASE_URL
from huurklaar_notifier.core.menu import build_menu
from huurklaar_notifier.testing.fake_server import EMPTY

TEST_API = "https://gqncu23i4i.execute-api.eu-central-1.amazonaws.com"


def _alle(entries):
    for e in entries:
        yield e
        yield from _alle(e.children)


def _defaults(entries):
    return [e.label for e in _alle(entries) if e.default]


def _zet_toestand(toestand, controller, server):
    if toestand == "attention":
        controller.poll()
    elif toestand == "idle":
        server.body = EMPTY
        controller.poll()
    elif toestand == "niet_ingesteld":
        pass  # na `configure` maar vóór de eerste poll staat de status nog op NOT_CONFIGURED
    elif toestand == "auth_failed":
        server.status = 401
        controller.poll()
    elif toestand == "offline":
        server.status = 500
        controller.poll()
    elif toestand == "offline_met_items":
        controller.poll()
        server.status = 500
        controller.poll()
    else:
        raise AssertionError(toestand)


@pytest.mark.parametrize(
    ("toestand", "verwacht"),
    [
        ("attention", "Huurklaar openen"),
        # Een lege lijst heeft geen link in de items, maar "Huurklaar openen" valt dan terug op de app van
        # de omgeving (app_url_for). Zo opent een linksklik nooit de instellingen als de app te bereiken is.
        ("idle", "Huurklaar openen"),
        ("niet_ingesteld", "Instellingen…"),
        ("auth_failed", "Instellingen…"),
        ("offline", "Instellingen…"),
        ("offline_met_items", "Instellingen…"),
    ],
)
def test_standaarditem_per_toestand(toestand, verwacht, controller, server):
    _zet_toestand(toestand, controller, server)
    assert _defaults(build_menu(controller.state, "nl", "auto", False)) == [verwacht]


@pytest.mark.parametrize(
    "toestand", ["attention", "idle", "niet_ingesteld", "auth_failed", "offline", "offline_met_items"]
)
def test_hoogstens_een_standaarditem_ook_in_submenus(toestand, controller, server):
    _zet_toestand(toestand, controller, server)
    entries = build_menu(controller.state, "nl", "auto", False)
    assert len(_defaults(entries)) == 1


def test_standaarditem_is_de_app_met_de_juiste_link(controller):
    controller.poll()
    (default,) = [e for e in build_menu(controller.state, "nl", "auto", False) if e.default]
    assert default.url == "https://app.example.test/"
    assert default.action is None


@pytest.mark.parametrize(
    ("base_url", "app"),
    [
        (DEFAULT_BASE_URL, "https://app.huurklaar.be/"),
        (TEST_API, "https://app-dev.huurklaar.be/"),
    ],
)
def test_huurklaar_openen_bij_lege_lijst_opent_de_app_van_de_omgeving(base_url, app, controller, server):
    server.body = EMPTY
    controller.poll()
    (default,) = [
        e for e in build_menu(controller.state, "nl", "auto", False, base_url=base_url) if e.default
    ]
    assert default.label == "Huurklaar openen"
    assert default.url == app
    assert default.action is None


def test_link_uit_de_items_heeft_voorrang_op_app_url_for(controller):
    # ATTENTION met SAMPLE: de link uit de items wijkt af van de app van de productie-omgeving,
    # dus de test bewijst dat de items voorrang hebben op app_url_for.
    controller.poll()
    (default,) = [
        e for e in build_menu(controller.state, "nl", "auto", False, base_url=DEFAULT_BASE_URL) if e.default
    ]
    assert default.url == "https://app.example.test/"


def test_taalsubmenu_heeft_geen_standaarditem(controller):
    controller.poll()
    entries = build_menu(controller.state, "nl", "auto", False)
    sub = next(e for e in entries if e.children)
    assert sub.default is False
    assert not any(c.default for c in sub.children)
