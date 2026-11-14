"""Het Mac-instellingenvenster opbouwen zonder het te tonen (enkel op macOS)."""

import sys

import pytest

if sys.platform != "darwin":
    pytest.skip("AppKit bestaat enkel op macOS", allow_module_level=True)
pytest.importorskip("AppKit")

from AppKit import NSApplication, NSSecureTextField, NSTextField  # noqa: E402

from huurklaar_notifier.platform.macos_settings import build_alert, ensure_edit_menu  # noqa: E402
from huurklaar_notifier.platform.settings_dialog import settings_texts  # noqa: E402


@pytest.fixture(autouse=True)
def app():
    return NSApplication.sharedApplication()


def test_venster_heeft_adresveld_en_beveiligd_sleutelveld():
    alert, url, key = build_alert(settings_texts("nl", True), "https://voorbeeld.test")
    fields = [v for v in alert.accessoryView().subviews() if isinstance(v, NSTextField) and v.isEditable()]
    assert len(fields) == 2
    assert not isinstance(url, NSSecureTextField)
    assert isinstance(key, NSSecureTextField)
    assert str(url.stringValue()) == "https://voorbeeld.test"
    assert str(key.stringValue()) == ""
    assert alert.window().initialFirstResponder() is url


def test_knoppen_bewaren_standaard_en_annuleren_met_escape():
    texts = settings_texts("nl", False)
    alert, _, _ = build_alert(texts, "")
    save, cancel = alert.buttons()
    assert str(save.title()) == texts.save
    assert str(save.keyEquivalent()) == "\r"
    assert str(cancel.title()) == texts.cancel
    assert str(cancel.keyEquivalent()) == "\x1b"


def test_edit_menu_bevat_plakken_met_cmd_v_en_komt_er_maar_een_keer_in():
    ensure_edit_menu()
    ensure_edit_menu()
    main = NSApplication.sharedApplication().mainMenu()
    pastes = []
    for i in range(main.numberOfItems()):
        sub = main.itemAtIndex_(i).submenu()
        if sub is not None:
            pastes += [it for it in sub.itemArray() if str(it.keyEquivalent()) == "v"]
    assert len(pastes) == 1
    assert str(pastes[0].action()) == "paste:"
    assert pastes[0].target() is None
