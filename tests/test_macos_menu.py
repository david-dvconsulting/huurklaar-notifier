"""Het register van rumps mag niet groeien als het menu telkens opnieuw gebouwd wordt (enkel op de Mac)."""

import sys

import pytest

if sys.platform != "darwin":
    pytest.skip("rumps en AppKit bestaan enkel op macOS", allow_module_level=True)
pytest.importorskip("rumps")

import rumps  # noqa: E402

from huurklaar_notifier.core.menu import MenuCache  # noqa: E402
from huurklaar_notifier.platform.macos import MenubarApp, forget_callbacks  # noqa: E402

ITEMS_PER_MENU = 13  # 10 items, het submenu en 2 kinderen


def registry():
    return rumps.rumps.NSApp._ns_to_py_and_callback


def make_items(n: int, tag: str):
    """Een menu met n items met callback, plus een submenu met twee kinderen met callback."""
    parent = rumps.MenuItem(f"taal {tag}")
    for i in range(2):
        child = rumps.MenuItem(f"kind {tag}{i}")
        child.set_callback(lambda _: None)
        parent.add(child)
    items = []
    for i in range(n):
        item = rumps.MenuItem(f"item {tag}{i}")
        item.set_callback(lambda _: None)
        items.append(item)
    return [*items, None, parent]


def test_forget_callbacks_ruimt_ook_submenus_op():
    items = [i for i in make_items(3, "x") if i is not None]
    before = len(registry())
    assert all(i._menuitem in registry() for i in items[:3])
    forget_callbacks(items)
    assert len(registry()) == before - 6  # 3 items, het submenu en 2 kinderen (elk met een callback)
    forget_callbacks(items)  # nogmaals oproepen mag niet falen


def test_register_groeit_niet_bij_1000_herbouwingen():
    menu = rumps.App("test-register", quit_button=None).menu
    base = len(registry())
    for i in range(1000):
        forget_callbacks(menu.values())
        menu.clear()
        menu.update(make_items(10, str(i)))
    assert len(registry()) - base <= ITEMS_PER_MENU


class _FakeApp(MenubarApp):
    """Zonder `rumps.App.__init__` (dat zou de app opzetten): enkel wat `_render` gebruikt."""

    title = ""  # overschrijft de rumps-property

    def __init__(self, controller):
        self.c = controller
        self._menu_cache = MenuCache()
        self._menu = rumps.rumps.Menu()
        self.renders = 0
        clear = self._menu.clear

        def counted_clear():
            self.renders += 1  # elke herbouw begint met clear()
            clear()

        self._menu.clear = counted_clear

    @property
    def menu(self):
        return self._menu


def test_render_herbouwt_enkel_bij_verandering_en_laat_geen_register_achter(controller):
    controller.poll()
    app = _FakeApp(controller)
    base = len(registry())
    app._render()
    app._render()  # zelfde toestand: geen herbouw
    assert app.renders == 1
    for i in range(1000):  # wisselende inhoud: de taal wisselt telkens
        controller.set_language(("nl", "fr", "en")[i % 3])
        app._render()
    assert app.renders == 1001
    assert len(registry()) - base <= ITEMS_PER_MENU + 5  # één menu met items, submenu en 7 talen
