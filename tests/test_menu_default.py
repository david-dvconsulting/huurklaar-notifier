"""Het standaarditem van het menu: een linksklik op het tray-icoon voert het uit (pystray, Windows)."""

import pytest

from huurklaar_notifier.core.menu import build_menu
from huurklaar_notifier.testing.fake_server import EMPTY


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
        # Een lege lijst geeft geen link naar de app (app_url leidt die af uit de items), dus ook geen
        # "Huurklaar openen" in het menu: dan zijn de instellingen het standaarditem.
        ("idle", "Instellingen…"),
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


def test_taalsubmenu_heeft_geen_standaarditem(controller):
    controller.poll()
    entries = build_menu(controller.state, "nl", "auto", False)
    sub = next(e for e in entries if e.children)
    assert sub.default is False
    assert not any(c.default for c in sub.children)
