"""AppKit-kant van het instellingenvenster op de Mac: één NSAlert met adres en sleutel, en het Edit-menu
dat plakken mogelijk maakt. Alles hier draait op de hoofdthread. Dun gehouden; de teksten en de
overdracht naar de hoofdthread staan in `settings_dialog.py`."""

from __future__ import annotations

from AppKit import (
    NSAlert,
    NSApp,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
    NSSecureTextField,
    NSTextField,
    NSView,
)

from .settings_dialog import Answer, SettingsTexts

WIDTH = 400
FIELD_HEIGHT = 24
GAP = 4
SECTION_GAP = 12
FIRST_BUTTON = 1000  # NSAlertFirstButtonReturn

# (titel, actie, sneltoets): target nil, zodat de actie via de responder chain bij het tekstveld uitkomt.
EDIT_ITEMS = (
    ("Cut", "cut:", "x"),
    ("Copy", "copy:", "c"),
    ("Paste", "paste:", "v"),
    ("Select All", "selectAll:", "a"),
)


def ensure_edit_menu() -> None:
    """Een app zonder hoofdmenu (LSUIElement) geeft Cmd+V niet door aan een tekstveld. Voeg eenmalig een
    Edit-menu toe; rumps beheert enkel de statusbalk, dus een bestaand hoofdmenu blijft ongemoeid."""
    app = NSApp()
    main = app.mainMenu()
    if main is None:
        main = NSMenu.alloc().initWithTitle_("")
        # macOS behandelt het eerste item van het hoofdmenu als het app-menu: houd die plaats vrij, zodat
        # Edit een gewoon menu blijft.
        app_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        app_item.setSubmenu_(NSMenu.alloc().initWithTitle_(""))
        main.addItem_(app_item)
        app.setMainMenu_(main)
    for i in range(main.numberOfItems()):
        sub = main.itemAtIndex_(i).submenu()
        if sub is not None and sub.indexOfItemWithTarget_andAction_(None, "paste:") >= 0:
            return  # al aanwezig
    edit = NSMenu.alloc().initWithTitle_("Edit")
    for title, action, key in EDIT_ITEMS:
        edit.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key))
    top = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Edit", None, "")
    top.setSubmenu_(edit)
    main.addItem_(top)


def _label(text: str, y: float) -> tuple[NSTextField, float]:
    label = NSTextField.wrappingLabelWithString_(text)
    height = label.sizeThatFits_((WIDTH, 10000)).height
    label.setFrame_(NSMakeRect(0, y, WIDTH, height))
    return label, y + height


def build_alert(texts: SettingsTexts, base_url: str):
    """Bouwt de NSAlert zonder te tonen. Geeft (alert, adresveld, sleutelveld)."""
    alert = NSAlert.alloc().init()
    alert.setMessageText_(texts.title)
    alert.addButtonWithTitle_(texts.save)  # eerste knop: standaard, dus Enter
    cancel = alert.addButtonWithTitle_(texts.cancel)
    cancel.setKeyEquivalent_("\x1b")  # Escape

    # Onderaan beginnen (AppKit-coördinaten tellen van onder naar boven).
    key_field = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, FIELD_HEIGHT))
    key_label, y = _label(texts.key_label, FIELD_HEIGHT + GAP)
    url_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, y + SECTION_GAP, WIDTH, FIELD_HEIGHT))
    url_field.setStringValue_(base_url)
    url_label, top = _label(texts.url_label, y + SECTION_GAP + FIELD_HEIGHT + GAP)

    view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, top))
    for sub in (key_field, key_label, url_field, url_label):
        view.addSubview_(sub)
    url_field.setNextKeyView_(key_field)
    key_field.setNextKeyView_(url_field)
    alert.setAccessoryView_(view)
    alert.layout()
    alert.window().setInitialFirstResponder_(url_field)
    return alert, url_field, key_field


def show_settings(texts: SettingsTexts, base_url: str) -> Answer:
    """Toont het venster modaal op de hoofdthread. `None` = geannuleerd."""
    ensure_edit_menu()
    alert, url_field, key_field = build_alert(texts, base_url)
    NSApp().activateIgnoringOtherApps_(True)  # geen Dock-icoon: anders verschijnt het achter andere apps
    if alert.runModal() != FIRST_BUTTON:
        return None
    return str(url_field.stringValue()), str(key_field.stringValue())
