"""Windows-logica die zonder Windows te testen is: register, melding, icoon en menu-omzetting."""

import pytest

from fake_winreg import FakeWinreg
from huurklaar_notifier.core.menu import AUTOSTART, Entry, build_menu
from huurklaar_notifier.core.state import Status
from huurklaar_notifier.platform.windows_icon import Badge, badge_for, render_icon
from huurklaar_notifier.platform.windows_menu import MAX_TOOLTIP, build_items, tooltip
from huurklaar_notifier.platform.windows_notifier import MAX_BODY, WindowsNotifier
from huurklaar_notifier.platform.windows_registry import (
    AUMID,
    AUMID_KEY,
    RUN_KEY,
    RUN_VALUE,
    RunKeyAutostart,
    register_app_id,
    run_command,
)


# -- start bij aanmelden ----------------------------------------------------------------------
def test_autostart_aan_en_uit():
    w = FakeWinreg()
    a = RunKeyAutostart(lambda: '"C:\\Users\\Jan Peeters\\App\\x.exe"', winreg=w)
    assert not a.is_enabled()
    a.set_enabled(True)
    assert a.is_enabled()
    assert w.keys[("HKCU", RUN_KEY)][RUN_VALUE] == '"C:\\Users\\Jan Peeters\\App\\x.exe"'
    a.set_enabled(False)
    assert not a.is_enabled()
    a.set_enabled(False)  # nogmaals uitzetten is geen fout


def test_autostart_schrijft_nooit_onder_hklm():
    w = FakeWinreg()
    RunKeyAutostart(lambda: "x", winreg=w).set_enabled(True)
    register_app_id(winreg=w)
    assert all(root == "HKCU" for root, _ in w.keys)


def test_run_command_zet_het_pad_tussen_aanhalingstekens():
    assert run_command(True, r"C:\Users\Jan Peeters\x.exe") == r'"C:\Users\Jan Peeters\x.exe"'
    assert run_command(False, r"C:\Py\pythonw.exe").endswith("-m huurklaar_notifier")


def test_app_id_krijgt_naam_en_icoon():
    w = FakeWinreg()
    register_app_id("Huurklaar Meldingen", r"C:\x\icon.ico", winreg=w)
    values = w.keys[("HKCU", AUMID_KEY)]
    assert values == {"DisplayName": "Huurklaar Meldingen", "IconUri": r"C:\x\icon.ico"}
    assert AUMID_KEY.endswith(AUMID)


# -- meldingen --------------------------------------------------------------------------------
def test_melding_gebruikt_eigen_app_id_en_open_link():
    sent = []
    n = WindowsNotifier(lambda *a, **k: sent.append((a, k)))
    n.notify("Titel", "Tekst", "https://app.example.test/tasks/1")
    assert sent == [(("Titel", "Tekst"), {"on_click": "https://app.example.test/tasks/1", "app_id": AUMID})]


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "file:///C:/Windows/notepad.exe", "ms-settings:", None]
)
def test_melding_geeft_nooit_een_onveilige_link_door(url):
    sent = []
    WindowsNotifier(lambda *a, **k: sent.append(k)).notify("t", "b", url)
    assert sent[0]["on_click"] is None


def test_melding_kapt_lange_tekst_af_en_laat_de_app_niet_vallen():
    sent = []
    WindowsNotifier(lambda *a, **k: sent.append(a)).notify("t", "x" * 1000, None)
    assert len(sent[0][1]) == MAX_BODY

    def boom(*a, **k):
        raise OSError("winrt weigert")

    WindowsNotifier(boom).notify("t", "b", None)  # geen uitzondering


# -- icoon --------------------------------------------------------------------------------------
def test_badge_per_toestand(controller, server):
    from huurklaar_notifier.testing.fake_server import EMPTY

    controller.poll()
    b = badge_for(controller.state)
    assert b is not None and b.text == "1" and b.color == badge_for(controller.state).color  # taken: teller
    server.body = EMPTY
    controller.poll()
    assert badge_for(controller.state) is None  # niets te doen
    server.status = 500
    controller.poll()
    assert badge_for(controller.state) == Badge(
        badge_for(controller.state).color, ""
    )  # geen verbinding: stip
    controller.state.status = Status.AUTH_FAILED
    assert badge_for(controller.state).text == "!"


def test_icoon_is_een_vierkant_met_een_badge_in_de_hoek():
    plain = render_icon(None, 64)
    badged = render_icon(Badge((220, 38, 38, 255), "9+"), 64)
    assert plain.size == badged.size == (64, 64)
    assert plain.getpixel((60, 60)) != badged.getpixel((50, 50)) or plain.tobytes() != badged.tobytes()
    assert badged.getpixel((55, 55))[3] == 255  # de badge dekt de hoek


# -- menu ----------------------------------------------------------------------------------------
class Item:
    def __init__(self, label, action, checked=None, enabled=True):
        self.label, self.action, self.checked, self.enabled = label, action, checked, enabled


class Menu:
    def __init__(self, *items):
        self.items = items


def test_menu_omzetting(controller):
    controller.poll()
    clicked = []
    entries = build_menu(controller.state, "nl", "auto", True)
    items = build_items(entries, Item, Menu, "SEP", clicked.append)
    assert "SEP" in items
    autostart = next(i for i in items if i != "SEP" and i.label == "Start bij aanmelden")
    assert autostart.checked(None) is True
    autostart.action(None, None)
    assert clicked[-1].action == AUTOSTART  # de aanklikbare actie krijgt de juiste invoer
    status = items[0]
    assert status.enabled is False and status.action is None
    taal = next(i for i in items if i != "SEP" and isinstance(i.action, Menu))
    assert len(taal.action.items) == 4


def test_menu_actie_neemt_hoogstens_twee_parameters():
    # pystray weigert acties met meer dan twee parameters; een lambda met standaardwaarde telt mee.
    (item,) = build_items([Entry("x", url="https://a.example.test/")], Item, Menu, "SEP", lambda e: None)
    assert item.action.__code__.co_argcount <= 2


def test_tooltip_wordt_afgekapt():
    assert len(tooltip("x" * 500, "Huurklaar Meldingen")) == MAX_TOOLTIP
